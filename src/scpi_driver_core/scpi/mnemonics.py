"""SCPI short and long form: which spellings of a header an instrument accepts.

A SCPI mnemonic is written with the required part in capitals and the rest in
lower case. ``FREQuency`` means the instrument accepts ``FREQ`` and
``FREQUENCY``. It does **not** accept ``FREQUEN``: SCPI allows the short form
or the whole long form, and nothing in between.

That rule is why this module exists. A simulator that matches on
``header.upper()`` accepts ``FREQuency`` and ``FREQUency`` alike, so a driver
that abbreviates a word wrongly passes its tests and fails on the bench — and
the same simulator rejects ``FREQ``, which every real instrument accepts. Both
halves of that are wrong, and a test suite built on it cannot see either.

The patterns here are written the way a manual writes them::

    header_matches("SYSTem:ALARm:ACTion:PFail", "syst:alar:act:pf")   # True
    header_matches("SYSTem:ALARm:ACTion:PFail", "SYSTEM:ALARM:ACTION:PFAIL")  # True
    header_matches("SYSTem:ALARm:ACTion:PFail", "SYSTem:ALARm:ACTion:PFAil")  # False

Case is otherwise irrelevant: SCPI headers are case-insensitive, and only the
split between required and optional letters carries meaning.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from scpi_driver_core.exceptions import ConfigurationError

__all__ = [
    "HeaderPattern",
    "Mnemonic",
    "expand_header_aliases",
    "header_matches",
    "parse_header_pattern",
]

#: Above this many nodes the alias set doubles past any use. Nothing real comes
#: close; the cap exists so a malformed pattern cannot allocate without bound.
MAXIMUM_ALIAS_NODES = 8

#: Letters, then an optional numeric suffix: ``OUTPut``, ``SOURce2``. The
#: underscore is here because instruments really use it — Tektronix spells the
#: waveform preamble ``WFMOutpre:BIT_Nr``, whose short form is ``BIT_N``. It is
#: not a separator: the required part still runs up to the first lower-case
#: letter, so the underscore simply belongs to whichever part it falls in.
_MNEMONIC = re.compile(r"^([A-Za-z_]+)([0-9]*)$")


@dataclass(frozen=True)
class Mnemonic:
    """One node of a header, and the spellings it accepts.

    Attributes:
        short: the required part, upper case. ``FREQ`` for ``FREQuency``.
        long: the whole word, upper case. ``FREQUENCY`` for ``FREQuency``.
        suffix: the numeric suffix, or ``""``. ``"2"`` for ``SOURce2``.
    """

    short: str
    long: str
    suffix: str = ""

    def matches(self, text: str) -> bool:
        """Whether ``text`` is a spelling this node accepts."""
        matched = _MNEMONIC.match(text)
        if matched is None:
            return False
        letters, digits = matched.group(1).upper(), matched.group(2)
        if digits != self.suffix:
            return False
        return letters in (self.short, self.long)


@dataclass(frozen=True)
class HeaderPattern:
    """A whole command header, as a manual spells it."""

    nodes: tuple[Mnemonic, ...]
    #: ``*IDN`` and friends: one node, no colons, matched whole.
    is_common: bool = False

    def matches(self, header: str) -> bool:
        """Whether ``header`` is a spelling of this command.

        A trailing ``?`` and a leading ``:`` are ignored: whether a header is a
        query, and whether it is written from the root, are not part of the
        spelling.
        """
        candidate = header.strip()
        if candidate.endswith("?"):
            candidate = candidate[:-1]
        if self.is_common:
            return candidate.upper() == "*" + self.nodes[0].long
        candidate = candidate.lstrip(":")
        parts = candidate.split(":")
        if len(parts) != len(self.nodes):
            return False
        return all(node.matches(part) for node, part in zip(self.nodes, parts, strict=True))


def _parse_mnemonic(text: str) -> Mnemonic:
    matched = _MNEMONIC.match(text)
    if matched is None:
        raise ConfigurationError(f"not a SCPI mnemonic: {text!r}")
    word, suffix = matched.group(1), matched.group(2)

    # The required part is the leading run of capitals. A capital appearing
    # after a lower-case letter means the pattern does not say where the short
    # form ends, so it is rejected rather than guessed at.
    for index, character in enumerate(word):
        if character.islower():
            leading = index
            break
    else:
        leading = len(word)
    if any(character.isupper() for character in word[leading:]):
        raise ConfigurationError(
            f"ambiguous mnemonic {text!r}: a capital follows a lower-case letter, "
            f"so the short form is not marked"
        )

    long = word.upper()
    short = long[:leading] if leading else long
    return Mnemonic(short=short, long=long, suffix=suffix)


@lru_cache(maxsize=4096)
def parse_header_pattern(pattern: str) -> HeaderPattern:
    """Parse a header as a manual spells it, e.g. ``SOURce2:VOLTage:AMPLitude``.

    Args:
        pattern: the header. A trailing ``?`` is ignored; a query and its
            setter have the same spelling.

    Returns:
        The parsed pattern, cached because simulators match in a loop.

    Raises:
        ConfigurationError: if the pattern is empty, has an empty node, or has
            a mnemonic whose short form is not marked unambiguously.
    """
    text = pattern.strip()
    if text.endswith("?"):
        text = text[:-1]
    if not text:
        raise ConfigurationError("empty header pattern")

    if text.startswith("*"):
        node = _parse_mnemonic(text[1:])
        if node.suffix:
            raise ConfigurationError(f"common command with a suffix: {pattern!r}")
        return HeaderPattern(nodes=(node,), is_common=True)

    text = text.lstrip(":")
    parts = text.split(":")
    if any(not part for part in parts):
        raise ConfigurationError(f"empty node in header pattern {pattern!r}")
    return HeaderPattern(nodes=tuple(_parse_mnemonic(part) for part in parts))


def header_matches(pattern: str, header: str) -> bool:
    """Whether ``header`` is a spelling the ``pattern`` accepts.

    Args:
        pattern: as a manual spells it, ``FREQuency``.
        header: as an instrument received it, ``freq`` or ``FREQUENCY``.

    Raises:
        ConfigurationError: if the pattern is malformed. A malformed *header*
            is simply not a match; it came off the wire and is not a mistake in
            this program.
    """
    return parse_header_pattern(pattern).matches(header)


def expand_header_aliases(pattern: str) -> frozenset[str]:
    """Every upper-case spelling an instrument would accept for ``pattern``.

    Each node contributes its short form and its long form, so
    ``SYSTem:ERRor`` yields ``SYST:ERR``, ``SYST:ERROR``, ``SYSTEM:ERR`` and
    ``SYSTEM:ERROR``. Nodes are independent: mixing forms between them is
    legal, and instruments accept it.

    This exists so a lookup table keyed by header can be widened once, at
    import, instead of every dispatch paying for a pattern match. A simulator
    that registers these aliases answers the short forms a real instrument
    answers, without changing how it dispatches.

    Args:
        pattern: the header as a manual spells it.

    Returns:
        Upper-case spellings, without a leading colon or trailing ``?``. For a
        common command the single spelling is returned, star included.

    Raises:
        ConfigurationError: if the pattern is malformed, or has more than
            :data:`MAXIMUM_ALIAS_NODES` nodes.
    """
    parsed = parse_header_pattern(pattern)
    if parsed.is_common:
        return frozenset({"*" + parsed.nodes[0].long})
    if len(parsed.nodes) > MAXIMUM_ALIAS_NODES:
        raise ConfigurationError(
            f"{pattern!r} has {len(parsed.nodes)} nodes; the alias set would be "
            f"{2 ** len(parsed.nodes)} entries"
        )

    spellings: list[str] = [""]
    for node in parsed.nodes:
        forms = {node.short + node.suffix, node.long + node.suffix}
        spellings = [
            prefix + (":" if prefix else "") + form for prefix in spellings for form in forms
        ]
    return frozenset(spellings)
