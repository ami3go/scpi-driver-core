#!/usr/bin/env python3
"""Propose the read-only methods of each driver, for a human to sign off.

The hardware sweep will call whatever this file lists. Deciding that list by
hand invites the mistake this whole area is about — one wrong name and a supply
turns its output on into a circuit nobody was watching. So the list is derived,
not written: a method is proposed only when the source proves it cannot do
anything but ask questions.

A method is proposed when **all** of these hold:

* it is public, and callable with no arguments beyond ``self``;
* it sends at least one SCPI literal directly in its own body — a method that
  delegates to a helper is not proven read-only from here, so it is excluded;
* every literal it sends is a query, its header ending in ``?``;
* its name does not match :data:`DANGEROUS`, applied regardless of the above.

Everything else lands in ``needs_review``, which the sweep never calls. Promote
one of those only by moving it by hand, and only if you can say why it is safe
on your bench with your instrument connected the way it is.

The output is a TOML file per driver with an empty ``signed_off_by``. The sweep
refuses to run until a person fills that in. See ``README.md``.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from audit_scpi_literals import (  # noqa: E402
    QUERY_CALLS,
    WRITE_CALLS,
    literal_of,
    looks_like_scpi,
)

#: Name fragments that keep a method out of the allowlist whatever its body
#: says. Belt and braces: a method could reach the instrument by a route this
#: script does not model, and these are the ones that would hurt.
DANGEROUS = re.compile(
    r"output|enable|disable|\bon\b|\boff\b|reset|rst|calibrat|factory|delete|erase|"
    r"format|store|save|recall|load|write|trigger|initiate|abort|shutdown|self_test|"
    r"preset|clear|source|protect|fault|simulate|apply|configure|arm|start|stop|"
    r"close|connect|disconnect|reconnect|recover|remote|local|lock|beep|set_|program",
    re.IGNORECASE,
)


#: Modules that model an instrument rather than drive one. Their methods share
#: names with the driver's — a simulator's ``get_frequency`` returns a field
#: instead of sending ``FREQuency?`` — and merging the two makes every real
#: getter look like it sends nothing.
#:
#: Matched on the file name only, never the class name. The N83624's driver
#: class is ``N83624CellSimulator``, because the instrument is a cell
#: simulator; a class-name rule silently excluded that entire driver.
NOT_A_DRIVER = re.compile(r"simulat|emulat|\bfake|mock|stub|dummy", re.IGNORECASE)


@dataclass
class Method:
    name: str
    commands: list[str] = field(default_factory=list)
    sends_write: bool = False


def takes_no_arguments(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Whether the method can be called as ``instance.method()``."""
    args = node.args
    if args.vararg or args.kwarg:
        return True  # *args/**kwargs need nothing supplied
    positional = list(args.posonlyargs) + list(args.args)
    required = len(positional) - len(args.defaults) - 1  # -1 for self
    required_kw = sum(1 for d in args.kw_defaults if d is None)
    return required <= 0 and required_kw == 0


def scan(path: Path) -> list[Method]:
    """Every public no-argument method in a file, with the literals it sends."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []

    methods: list[Method] = []
    for parent in ast.walk(tree):
        if not isinstance(parent, ast.ClassDef):
            continue
        for node in parent.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("_") or not takes_no_arguments(node):
                continue
            method = Method(name=node.name)
            for call in ast.walk(node):
                if not isinstance(call, ast.Call):
                    continue
                name = ""
                if isinstance(call.func, ast.Attribute):
                    name = call.func.attr
                elif isinstance(call.func, ast.Name):
                    name = call.func.id
                if name not in WRITE_CALLS and name not in QUERY_CALLS:
                    continue
                for argument in call.args:
                    text = literal_of(argument)
                    if text is None or not looks_like_scpi(text):
                        continue
                    method.commands.append(text)
                    if not text.split(" ", 1)[0].endswith("?"):
                        method.sends_write = True
            methods.append(method)
    return methods


def classify(methods: list[Method]) -> tuple[list[Method], list[Method]]:
    """Split into (proposed read-only, needs human review)."""
    read_only: dict[str, Method] = {}
    review: dict[str, Method] = {}
    for method in methods:
        proven = bool(method.commands) and not method.sends_write
        if proven and not DANGEROUS.search(method.name):
            read_only.setdefault(method.name, method)
        else:
            review.setdefault(method.name, method)
    # A name proven unsafe anywhere is unsafe everywhere: same driver, same
    # instrument, and the sweep addresses methods by name.
    for name in list(read_only):
        if name in review:
            del read_only[name]
    return (
        sorted(read_only.values(), key=lambda m: m.name),
        sorted(review.values(), key=lambda m: m.name),
    )


def render(driver: str, read_only: list[Method], review: list[Method]) -> str:
    """The TOML for one driver, unsigned."""
    lines = [
        f"# Hardware sweep allowlist for {driver}.",
        "#",
        "# Generated by generate_allowlist.py, which proposes only methods the",
        "# source proves send nothing but queries. Regenerating overwrites the",
        "# proposal but never the signature block, so review the diff.",
        "#",
        "# The sweep refuses to run while signed_off_by is empty. Signing means:",
        "# you have read the read_only list, you know what is connected to this",
        "# instrument, and you accept these calls being made to it.",
        "",
        f'driver = "{driver}"',
        "",
        "# Proposed by static analysis: public, no arguments, sends only queries,",
        f"# and not name-matched as dangerous. {len(read_only)} methods.",
        "read_only = [",
    ]
    for method in read_only:
        commands = ", ".join(sorted(set(method.commands))[:4])
        lines.append(f'    "{method.name}",  # {commands}')
    lines += [
        "]",
        "",
        "# Not called by the sweep. Each either writes to the instrument, sends",
        "# nothing this script can see, or is name-matched as dangerous. Promote",
        "# one into read_only only deliberately, and only with a reason recorded",
        f"# here. {len(review)} methods.",
        "needs_review = [",
    ]
    for method in review:
        why = "writes" if method.sends_write else ("dangerous name" if DANGEROUS.search(method.name) else "no visible command")
        lines.append(f'    # "{method.name}",  # {why}')
    # The signature table goes last on purpose. In TOML every key after a
    # table header belongs to that table, so a [sign_off] section placed above
    # these arrays would swallow them and the sweep would read an empty list.
    lines += [
        "]",
        "",
        "[sign_off]",
        'signed_off_by = ""      # your name; the sweep will not run without it',
        'signed_off_date = ""    # ISO date',
        'instrument_serial = ""  # which physical unit this was signed for',
        "allow_writes = false    # leave false; see README before changing",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "allowlists")
    arguments = parser.parse_args()

    arguments.out.mkdir(parents=True, exist_ok=True)
    for project in sorted(arguments.root.glob("py_*")):
        if not project.is_dir():
            continue
        methods: list[Method] = []
        for package in sorted(project.iterdir()):
            # Only the Python driver package. The rf_* adapter wraps the same
            # method names as thin keyword delegates that send no SCPI of their
            # own, and merging those in makes every real getter look silent.
            if not package.is_dir() or not package.name.startswith("py_"):
                continue
            for path in sorted(package.rglob("*.py")):
                if "__pycache__" in path.parts or NOT_A_DRIVER.search(path.name):
                    continue
                methods.extend(scan(path))
        read_only, review = classify(methods)
        target = arguments.out / f"{project.name}.toml"
        target.write_text(render(project.name, read_only, review), encoding="utf-8")
        print(f"{project.name}: {len(read_only)} proposed read-only, {len(review)} for review")
    return 0


if __name__ == "__main__":
    sys.exit(main())
