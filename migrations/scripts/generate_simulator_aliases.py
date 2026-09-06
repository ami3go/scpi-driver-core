#!/usr/bin/env python3
"""Record each driver's command headers as its manual spells them.

A simulator that dispatches on ``header.upper()`` answers only the spelling the
driver happens to send. A real instrument answers the short form too:
``SYST:ERR?`` and ``SYSTEM:ERROR?`` are the same command, and every conforming
instrument takes both. So a driver could switch to short forms, stay correct,
and fail its whole simulated suite — the suite is pinned to a spelling rather
than to a command.

Fixing that needs the split between required and optional letters, which the
uppercase route keys have thrown away. The drivers still have it: they send
``SYSTem:ALARm:ACTion:PFail``, capitals and all, exactly as the manual prints
it. This extracts those spellings into a generated module, which the simulator
uses to widen its route table at import.

Only headers with no runtime substitution are recorded. ``SOURce{ch}:VOLTage``
is not a header until the channel is filled in, and guessing the numbering is
not this script's job.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_scpi_literals import collect  # noqa: E402

#: Simulators that dispatch through a route table keyed by upper-case header.
#: The N6700 and N83624 match with if/elif chains instead; widening those means
#: rewriting their dispatch, which is a bigger and riskier change than this.
ROUTE_TABLE_DRIVERS = (
    "py_agilent33220a",
    "py_agilent34411a",
    "py_ea_ps9000t",
    "py_tbs1000c",
)

TEMPLATE = '''"""Command headers as the manual spells them. Generated; do not edit.

Written by ``migrations/scripts/generate_simulator_aliases.py`` from the
literals this driver sends. The capitals mark where each mnemonic's short form
ends, which is what lets the simulator accept ``SYST:ERR?`` as well as
``SYSTEM:ERROR?``, the way a real instrument does.

Headers containing a runtime substitution are not recorded: they are not
headers until the value is filled in.
"""

from __future__ import annotations

__all__ = ["CANONICAL_HEADERS"]

CANONICAL_HEADERS: tuple[str, ...] = (
{entries}
)
'''


def canonical_headers(project: Path) -> list[str]:
    """Every fully spelled-out header the driver sends, deduplicated."""
    package = project / project.name
    headers: set[str] = set()
    for path in sorted(package.rglob("*.py")):
        if "__pycache__" in path.parts or path.name in {"simulator.py", "scpi_aliases.py"}:
            continue
        for literal in collect(path, project.name):
            header = literal.text.split(" ", 1)[0].rstrip("?")
            if "{" in header or "}" in header or not header:
                continue
            headers.add(header)
    return sorted(headers)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    arguments = parser.parse_args()

    for name in ROUTE_TABLE_DRIVERS:
        project = arguments.root / name
        headers = canonical_headers(project)
        entries = "\n".join(f'    "{header}",' for header in headers)
        target = project / name / "scpi_aliases.py"
        target.write_text(TEMPLATE.format(entries=entries), encoding="utf-8")
        print(f"{name}: {len(headers)} headers -> {target.relative_to(arguments.root)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
