"""The simulator answers the short forms a real instrument answers.

Added during the scpi-driver-core migration. A SCPI mnemonic is written with
its required part in capitals: ``SYSTem:ERRor`` means an instrument accepts
both ``SYST:ERR`` and ``SYSTEM:ERROR``. This simulator used to match on
``header.upper()`` alone, so it answered only the spelling the driver happened
to send, and rejected the short form every real instrument takes.

The route table is now widened at import from the driver's own spellings. These
tests pin that, and pin the limit: an abbreviation that is neither form is still
rejected, because accepting it would hide a typo the bench would catch.
"""

from __future__ import annotations

import pytest
from scpi_driver_core.scpi.mnemonics import expand_header_aliases, parse_header_pattern

from py_agilent34411a.scpi_aliases import CANONICAL_HEADERS
from py_agilent34411a.simulator import SimAgilent34411AInstrument

ROUTES = SimAgilent34411AInstrument._ROUTES


def routed(header: str) -> bool:
    return header.upper().lstrip(":").rstrip("?") in ROUTES


#: Only the headers this simulator actually models; the driver sends a few it
#: does not, and inventing handlers for those is not this change's business.
MODELLED = [h for h in CANONICAL_HEADERS if routed(h)]


def test_the_simulator_models_a_useful_number_of_headers() -> None:
    """Otherwise the parametrised tests below would be vacuous."""
    assert len(MODELLED) >= 50


@pytest.mark.parametrize("header", MODELLED)
def test_every_legal_spelling_of_a_modelled_header_routes(header: str) -> None:
    for alias in expand_header_aliases(header):
        assert alias in ROUTES, f"{alias} is a legal spelling of {header}"


@pytest.mark.parametrize("header", MODELLED)
def test_the_original_spelling_still_routes(header: str) -> None:
    """Nothing that worked before may have stopped working."""
    assert routed(header)


def test_an_abbreviation_that_is_neither_form_is_rejected() -> None:
    """The short form or the whole long form. There is nothing in between."""
    checked = 0
    for header in MODELLED:
        pattern = parse_header_pattern(header)
        for node in pattern.nodes:
            if len(node.long) - len(node.short) < 2:
                continue  # no room for an intermediate spelling
            intermediate = node.long[: len(node.short) + 1]
            wrong = header.upper().replace(node.long, intermediate, 1)
            if wrong == header.upper():
                continue
            assert wrong not in ROUTES, f"{wrong} is not a legal spelling"
            checked += 1
            if checked >= 25:
                return
    assert checked, "no header had an intermediate spelling to check"
