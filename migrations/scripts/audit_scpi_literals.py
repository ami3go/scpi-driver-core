#!/usr/bin/env python3
"""Statically audit every SCPI command literal in the migrated drivers.

No instrument is involved. Each driver's source is parsed, every string literal
passed to a write- or query-style call is collected, and the result is checked
against rules that can be decided from the text alone.

The checks are chosen for the bug classes that a laptop can decide and a bench
session would waste time rediscovering:

``query-sent-as-write``
    A ``?`` command sent through a write call. The instrument answers, nothing
    reads the answer, and it sits in the output buffer until the next query
    collects it as *its* reply. Every reading after that point is off by one.
    This is the single most damaging thing on this list.

``command-sent-as-query``
    The mirror: a command with no ``?`` sent through a query call. The
    instrument has nothing to say, so the read blocks until it times out.

``getter-sends-no-query``
    A method named ``get_*``/``read_*``/``measure_*`` whose body sends only
    non-query commands. Usually means a missing ``?``.

``short-form-conflict``
    SCPI mnemonics have a short form (the capitals) and a long form. So
    ``VOLTage`` abbreviates to ``VOLT`` while ``VOLtage`` abbreviates to
    ``VOL`` — the same word, two different commands, and one of them is a
    typo. Flagged when one word is capitalised two ways in the same driver.

``unknown-common-command``
    A ``*XYZ`` outside IEEE-488.2. Legal as a vendor extension, worth reading.

``suspicious-whitespace`` / ``unbalanced-delimiters``
    A space before the ``?``, a doubled space, or an unclosed quote or paren.

Findings are advisory: this reads code, not manuals, so a vendor's legitimate
oddity can land here. Every one needs a human to confirm.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

#: Calls that transmit without reading a reply.
WRITE_CALLS = {
    "write", "_write", "write_raw", "raw_write", "write_scpi", "write_binary",
    "_write_locked", "send", "_send", "send_command", "command", "write_command",
}

#: Calls that transmit and read a reply.
QUERY_CALLS = {
    "query", "_query", "query_raw", "raw_query", "query_scpi", "query_binary",
    "_query_locked", "ask", "_ask", "request", "query_command",
}

#: IEEE-488.2 common commands. Anything else starting with ``*`` is a vendor
#: extension, which is legal but worth a second look.
IEEE4882_COMMON = {
    "*AAD", "*CAL", "*CLS", "*DDT", "*DLF", "*DMC", "*EMC", "*ESE", "*ESR",
    "*GMC", "*IDN", "*IST", "*LMC", "*LRN", "*OPC", "*OPT", "*PCB", "*PMC",
    "*PRE", "*PSC", "*PUD", "*RCL", "*RDT", "*RMC", "*RST", "*SAV", "*SDS",
    "*SRE", "*STB", "*TRG", "*TST", "*WAI",
}

#: Method-name prefixes that promise a value came back from the instrument.
GETTER_PREFIXES = ("get_", "read_", "measure_", "fetch_", "query_")

#: Findings checked against the code and the vendor documentation and found
#: not to be defects, each with the reason. Keyed by (kind, driver, text) so a
#: line number moving does not resurrect one. Anything not listed here is
#: unreviewed and fails the run.
ACCEPTED: dict[tuple[str, str, str], str] = {
    ("command-sent-as-query", "py_eresistor", "SYST:ERR:CLEAR"):
        "this instrument acknowledges every command with 'OK'; the driver reads "
        "and checks that acknowledgement, so query() is correct here",
    ("command-sent-as-query", "py_eresistor", "CH{}:MASK {}"):
        "same acknowledgement protocol; client.py raises if the reply is not 'OK'",
    ("command-sent-as-query", "py_eresistor", "ALL:OFF"):
        "same acknowledgement protocol; client.py accepts only 'OK' or '0'",
    ("getter-sends-no-query", "py_hp34401a",
     "SAMPle:COUNt 1, TRIGger:COUNt 1"):
        "read_once_bus() reads through self.fetch(), which sends FETCh?; this "
        "check does not follow calls into helper methods",
    ("short-form-conflict", "py_ea_ps9000t", "PFAIL"):
        "the manufacturer spells it both ways: ':PFAil?' under SYSTem:ALARm:COUNt "
        "and ':PFail' under SYSTem:ALARm:ACTion, both as printed in the vendor "
        "documentation this driver was written from",
    ("suspicious-whitespace", "py_tbs1000c", 'FILESystem:WRITEFile "{}", '):
        "the trailing space precedes the IEEE-488.2 block that write_binary "
        "appends; removing it would corrupt the command",
}

#: A mnemonic: capitals (the short form) then optional lowercase (the rest of
#: the long form), with an optional numeric suffix such as ``OUTPut1``.
MNEMONIC = re.compile(r"^([A-Za-z]+)(\d*)$")


@dataclass
class Literal:
    """One SCPI string literal, with where it came from."""

    text: str
    driver: str
    path: str
    line: int
    call: str
    enclosing: str
    is_query_call: bool


@dataclass
class Finding:
    """One thing worth a human's attention."""

    kind: str
    driver: str
    path: str
    line: int
    text: str
    detail: str


@dataclass
class Report:
    literals: list[Literal] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)


def literal_of(node: ast.expr) -> str | None:
    """The static text of a string literal or f-string, else ``None``.

    An f-string keeps its literal parts and marks each substitution ``{}``, so
    ``f"SOURce{ch}:VOLTage {v}"`` audits as ``SOURce{}:VOLTage {}`` — the
    structure is what matters here, not the runtime value.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for piece in node.values:
            if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
                parts.append(piece.value)
            else:
                parts.append("{}")
        return "".join(parts)
    return None


def looks_like_scpi(text: str) -> bool:
    """Whether a literal is plausibly a command rather than prose or a format."""
    if not text or len(text) > 120 or text.startswith(" "):
        return False
    head = text.split()[0] if text.split() else ""
    if not head:
        return False
    if head.startswith("*"):
        return True
    # A header starts with a letter and contains only header characters.
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9_:{}\[\]?]*$", head)) and head[:1].isupper()


def collect(path: Path, driver: str) -> list[Literal]:
    """Every SCPI literal passed to a write- or query-style call in one file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []

    # Map each node to the function that encloses it, for getter checks.
    enclosing: dict[int, str] = {}
    for function in ast.walk(tree):
        if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(function):
                enclosing.setdefault(id(child), function.name)

    found: list[Literal] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = ""
        if isinstance(node.func, ast.Attribute):
            name = node.func.attr
        elif isinstance(node.func, ast.Name):
            name = node.func.id
        if name not in WRITE_CALLS and name not in QUERY_CALLS:
            continue
        for argument in node.args:
            text = literal_of(argument)
            if text is None or not looks_like_scpi(text):
                continue
            found.append(
                Literal(
                    text=text,
                    driver=driver,
                    path=str(path),
                    line=argument.lineno,
                    call=name,
                    enclosing=enclosing.get(id(node), "<module>"),
                    is_query_call=name in QUERY_CALLS,
                )
            )
    return found


def header_of(text: str) -> str:
    """The command header: everything before the first space."""
    return text.split(" ", 1)[0]


def nodes_of(header: str) -> list[str]:
    """The colon-separated mnemonics of a header, without a trailing ``?``."""
    return [n for n in header.rstrip("?").split(":") if n]


def short_form(mnemonic: str) -> str | None:
    """The abbreviated form: the leading capitals, minus any numeric suffix."""
    match = MNEMONIC.match(mnemonic)
    if not match:
        return None
    word = match.group(1)
    capitals = "".join(c for c in word if c.isupper())
    return capitals or word.upper()


def audit(literals: list[Literal]) -> list[Finding]:
    """Apply every check to the collected literals."""
    findings: list[Finding] = []

    def add(kind: str, lit: Literal, detail: str) -> None:
        findings.append(
            Finding(kind, lit.driver, lit.path, lit.line, lit.text, detail)
        )

    for lit in literals:
        header = header_of(lit.text)
        is_query_text = header.endswith("?")

        if is_query_text and not lit.is_query_call:
            add(
                "query-sent-as-write", lit,
                f"{lit.call}() sends a query; the reply is never read and will "
                f"be returned as the answer to the next query",
            )
        if not is_query_text and lit.is_query_call:
            add(
                "command-sent-as-query", lit,
                f"{lit.call}() reads a reply, but this command produces none; "
                f"the read blocks until it times out",
            )

        if "  " in lit.text:
            add("suspicious-whitespace", lit, "doubled space")
        if lit.text != lit.text.rstrip():
            add("suspicious-whitespace", lit, "trailing whitespace")
        if re.search(r"\s\?", lit.text):
            add("suspicious-whitespace", lit, "space before the '?'")
        if lit.text.count('"') % 2 or lit.text.count("(") != lit.text.count(")"):
            add("unbalanced-delimiters", lit, "unbalanced quote or parenthesis")

        if header.startswith("*"):
            stem = "*" + re.sub(r"[^A-Za-z]", "", header[1:]).upper()
            if stem not in IEEE4882_COMMON:
                add("unknown-common-command", lit, f"{stem} is not in IEEE-488.2")

    # Short-form conflicts, per driver: the same word capitalised two ways.
    by_word: dict[tuple[str, str], dict[str, Literal]] = defaultdict(dict)
    for lit in literals:
        for mnemonic in nodes_of(header_of(lit.text)):
            if "{" in mnemonic:
                continue
            match = MNEMONIC.match(mnemonic)
            if not match:
                continue
            word = match.group(1)
            by_word[(lit.driver, word.upper())].setdefault(word, lit)
    for (driver, upper), spellings in sorted(by_word.items()):
        forms = {spelling: short_form(spelling) for spelling in spellings}
        if len(set(forms.values())) > 1:
            listing = ", ".join(
                f"{spelling} -> {abbrev}" for spelling, abbrev in sorted(forms.items())
            )
            lit = next(iter(spellings.values()))
            findings.append(
                Finding(
                    "short-form-conflict", driver, lit.path, lit.line, upper,
                    f"one word abbreviates two ways: {listing}",
                )
            )

    # Getters that never send a query.
    by_method: dict[tuple[str, str, str], list[Literal]] = defaultdict(list)
    for lit in literals:
        by_method[(lit.driver, lit.path, lit.enclosing)].append(lit)
    for (driver, path, method), group in sorted(by_method.items()):
        if not method.startswith(GETTER_PREFIXES):
            continue
        if any(header_of(lit.text).endswith("?") for lit in group):
            continue
        commands = ", ".join(sorted({lit.text for lit in group}))
        findings.append(
            Finding(
                "getter-sends-no-query", driver, path, group[0].line, commands,
                f"{method}() promises a value but sends no query",
            )
        )

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default="migrations", type=Path)
    parser.add_argument("--show-commands", action="store_true",
                        help="list every distinct command per driver")
    arguments = parser.parse_args()

    report = Report()
    for project in sorted(arguments.root.glob("py_*")):
        if not project.is_dir():
            continue
        driver = project.name
        for package in sorted(project.iterdir()):
            if not package.is_dir() or package.name.startswith((".", "tests", "__")):
                continue
            for path in sorted(package.rglob("*.py")):
                if "__pycache__" in path.parts:
                    continue
                report.literals.extend(collect(path, driver))

    report.findings = audit(report.literals)

    per_driver: dict[str, set[str]] = defaultdict(set)
    for lit in report.literals:
        per_driver[lit.driver].add(lit.text)

    print(f"{len(report.literals)} SCPI literals, "
          f"{len({lit.text for lit in report.literals})} distinct, "
          f"across {len(per_driver)} drivers\n")
    for driver in sorted(per_driver):
        count = sum(1 for lit in report.literals if lit.driver == driver)
        print(f"  {driver:<22} {count:>4} literals, {len(per_driver[driver]):>4} distinct")
        if arguments.show_commands:
            for text in sorted(per_driver[driver]):
                print(f"        {text}")

    accepted: list[tuple[Finding, str]] = []
    open_findings: list[Finding] = []
    for finding in report.findings:
        reason = ACCEPTED.get((finding.kind, finding.driver, finding.text))
        if reason is None:
            open_findings.append(finding)
        else:
            accepted.append((finding, reason))

    if accepted:
        print(f"\n{len(accepted)} reviewed, not defects\n")
        for finding, reason in accepted:
            print(f"   [{finding.kind}] {finding.path}:{finding.line}")
            print(f"     {finding.text!r}")
            print(f"     {reason}")
        print()

    by_kind: dict[str, list[Finding]] = defaultdict(list)
    for finding in open_findings:
        by_kind[finding.kind].append(finding)

    print(f"{len(open_findings)} findings needing review\n")
    for kind in sorted(by_kind):
        print(f"== {kind} ({len(by_kind[kind])})")
        for finding in by_kind[kind]:
            print(f"   {finding.path}:{finding.line}")
            print(f"     {finding.text!r}")
            print(f"     {finding.detail}")
        print()

    return 1 if open_findings else 0


if __name__ == "__main__":
    sys.exit(main())
