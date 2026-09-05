#!/usr/bin/env python3
"""Add docstrings to public driver methods, derived from the code itself.

These drivers were written with almost no docstrings — 445 public members
across the six with API snapshots. Writing that many by hand invites invented
prose that drifts from the code, so this derives each one from the method's own
body instead: the SCPI command a method sends is the single most useful fact
about it, and it cannot be wrong because it is read from the source.

A generated docstring names what the method does, from its name, and the exact
SCPI commands it sends, from its body:

    def get_frequency(self) -> float:
        \"\"\"Return the frequency.

        Sends ``FREQuency?``.
        \"\"\"
        return float(self._query("FREQuency?"))

Methods that already have a docstring are never touched. Nothing else in the
file is modified: the rewrite is applied by line insertion, so formatting,
comments, and code are left exactly as they were.

Run it, then re-run the API snapshots, which record which members are
documented.
"""

from __future__ import annotations

import argparse
import ast
import io
import re
import sys
from pathlib import Path

#: Verb phrases for the naming conventions these drivers actually use.
PREFIXES: list[tuple[str, str]] = [
    ("get_", "Return the {}"),
    ("set_", "Set the {}"),
    ("read_", "Read the {}"),
    ("measure_", "Measure the {}"),
    ("fetch_", "Fetch the {}"),
    ("enable_", "Enable {}"),
    ("disable_", "Disable {}"),
    ("configure_", "Configure {}"),
    ("clear_", "Clear the {}"),
    ("reset_", "Reset the {}"),
    ("start_", "Start {}"),
    ("stop_", "Stop {}"),
    ("wait_", "Wait for {}"),
    ("check_", "Check the {}"),
    ("drain_", "Drain the {}"),
    ("copy_", "Copy the {}"),
    ("delete_", "Delete the {}"),
    ("save_", "Save the {}"),
    ("recall_", "Recall the {}"),
    ("load_", "Load the {}"),
    ("store_", "Store the {}"),
    ("select_", "Select the {}"),
    ("apply_", "Apply the {}"),
    ("send_", "Send the {}"),
    ("query_", "Query the {}"),
    ("write_", "Write the {}"),
    ("run_", "Run the {}"),
    ("trigger_", "Trigger {}"),
    ("arm_", "Arm {}"),
    ("abort_", "Abort {}"),
    ("is_", "Whether the {}"),
    ("has_", "Whether the {} is present"),
]

#: Names whose derived phrasing would be poor, spelled out instead. A weak
#: docstring is worse than none, so anything the rules cannot phrase well is
#: listed here or left alone.
EXACT: dict[str, str] = {
    "connect_visa": "Open a VISA connection and return a connected driver",
    "connect_usb": "Open a USB connection and return a connected driver",
    "connect_ethernet": "Open an Ethernet connection and return a connected driver",
    "connect_simulated": "Return a driver backed by the in-process simulator",
    "connect_serial": "Open a serial connection and return a connected driver",
    "connected": "Whether the transport is currently open",
    "resource": "The resource string this driver is connected to",
    "transport": "The underlying transport",
    "simulator": "The in-process simulator backing this driver",
    "channels": "The channels this instrument exposes",
    "capabilities": "What this instrument reports it can do",
    "identity": "The cached instrument identity",
    "config": "The configuration this driver was built with",
    "name": "A human-readable name for this connection",
    "reset": "Reset the instrument to its power-on defaults",
    "close": "Close the connection and release the transport",
    "identify": "Return the instrument identity",
    "abort": "Abort the operation in progress",
    "trigger": "Send a trigger",
    "wait": "Wait for pending operations to finish",
    "initiate": "Initiate the configured operation",
    "preset": "Apply the preset configuration",
    "beep": "Sound the instrument beeper",
    "calibrate": "Run the calibration procedure",
    "self_test": "Run the instrument self-test",
    "write": "Send a command, expecting no reply",
    "query": "Send a query and return its reply",
    "open": "Open the connection",
    "connect": "Open the connection",
    "connect_usbtmc": "Open a USBTMC connection and return a connected driver",
    "clear": "Clear the instrument's device state",
    "ping": "Check that the instrument is reachable",
    "dispatch": "Handle one command and return its reply",
    "as_dict": "Return this record as a plain dictionary",
    "raw_write": "Send a raw SCPI command, bypassing the typed API",
    "raw_query": "Send a raw SCPI query, bypassing the typed API",
    "force_trigger": "Force a trigger regardless of the configured source",
    "remote_lockout": "Put the instrument into remote lockout",
    "emit_event": "Record one event in the evidence log",
    "record_error": "Record an error in the evidence log",
    "record_operation": "Record one operation in the evidence log",
    "record_device_identity": "Record the instrument identity in the evidence log",
    "log_protocol": "Record one protocol exchange in the evidence log",
    "finalize": "Finish the record and flush it",
    "export_diagnostic_bundle": "Write a diagnostic bundle for support",
    "info": "Log an informational message",
    "end_suite": "Robot Framework hook: called when a suite ends",
    "end_test": "Robot Framework hook: called when a test ends",
    "end_keyword": "Robot Framework hook: called when a keyword ends",
    "start_suite": "Robot Framework hook: called when a suite starts",
    "start_test": "Robot Framework hook: called when a test starts",
    "start_keyword": "Robot Framework hook: called when a keyword starts",
    "assert_no_error": "Raise if the instrument's error queue is not empty",
    "from_serial": "Build a driver over a serial connection",
    "from_visa_gpib": "Build a driver over a VISA GPIB connection",
    "heartbeat": "Check that the instrument is still responding",
    "recover": "Attempt to return the instrument to a usable state",
    "require_terminal": "Raise unless the instrument is in the terminal state",
    "rename_instrument_memory_slot": "Give a stored-state memory slot a name",
    "audit": "Append one record to the protocol audit log",
    "channel": "Return the channel object for a channel number",
    "load": "Return the electronic-load interface for a channel",
    "power_supply": "Return the power-supply interface for a channel",
    "smu": "Return the source-measure interface for a channel",
    "discover_modules": "Query which modules are installed and what they can do",
    "shutdown_all": "Bring every channel to a safe state",
}

#: A SCPI command looks like a header, optionally with arguments.
SCPI = re.compile(r"^\*?[A-Za-z][A-Za-z0-9:_\[\]?* .,()@%+-]*$")


def looks_like_scpi(text: str) -> bool:
    """Whether a string literal is plausibly a SCPI command rather than prose."""
    if not text or len(text) > 80 or " " in text[:1]:
        return False
    if not SCPI.match(text):
        return False
    head = text.split()[0]
    # The literal is already known to be an argument to a write/query call, so
    # the job here is only to reject the occasional format string or message.
    # A SCPI header starts with * or an uppercase letter; SCPI's short/long
    # form means "OUTPut" and "FREQuency" are headers too, not prose, so an
    # all-caps test would wrongly reject most set-style commands.
    return head.startswith("*") or head[:1].isupper()


def commands_in(node: ast.FunctionDef) -> list[str]:
    """SCPI command literals sent from this method's body, in source order."""
    found: list[str] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        name = ""
        if isinstance(child.func, ast.Attribute):
            name = child.func.attr
        elif isinstance(child.func, ast.Name):
            name = child.func.id
        if name not in {
            "_write", "_query", "write", "query", "write_scpi", "query_scpi",
            "request", "command", "_send", "send", "write_binary", "query_binary",
        }:
            continue
        for argument in child.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                if looks_like_scpi(argument.value) and argument.value not in found:
                    found.append(argument.value)
            elif isinstance(argument, ast.JoinedStr):
                literal = "".join(
                    part.value
                    for part in argument.values
                    if isinstance(part, ast.Constant) and isinstance(part.value, str)
                ).strip()
                template = (literal + " …").strip()
                if looks_like_scpi(literal) and template not in found:
                    found.append(template)
    return found


def _readable(subject: str) -> str:
    """Turn an identifier fragment into readable words."""
    words = subject.replace("_", " ").strip()
    # A trailing "s" unit suffix reads as a unit, not a plural.
    for suffix, unit in ((" s", "in seconds"), (" ms", "in milliseconds"),
                         (" hz", "in hertz"), (" v", "in volts")):
        if words.endswith(suffix):
            return f"{words[: -len(suffix)]} {unit}"
    return words


def summary_for(name: str, *, is_property: bool = False) -> str:
    """A phrase for ``name``, from the driver's naming conventions.

    Returns an empty string when nothing better than restating the name is
    available, which tells the caller to leave the method alone rather than
    attach a docstring that says nothing.
    """
    if name in EXACT:
        return EXACT[name]
    for prefix, template in PREFIXES:
        if name.startswith(prefix):
            subject = _readable(name[len(prefix) :])
            if not subject:
                return ""
            return template.format(subject)
    if is_property:
        return f"The {_readable(name)}"
    return ""


def docstring_for(
    node: ast.FunctionDef, indent: str, *, is_property: bool = False
) -> list[str] | None:
    """The lines of a generated docstring, or ``None`` if none is worth adding."""
    summary = summary_for(node.name, is_property=is_property)
    commands = commands_in(node)
    if not summary and not commands:
        # Nothing to say beyond the name itself. Silence beats noise.
        return None
    if not summary:
        summary = f"Issue the {node.name.replace('_', ' ')} command"
    if not commands:
        return [f'{indent}"""{summary}."""']
    if len(commands) == 1:
        return [
            f'{indent}"""{summary}.',
            "",
            f"{indent}Sends ``{commands[0]}``.",
            f'{indent}"""',
        ]
    listed = ", ".join(f"``{command}``" for command in commands[:6])
    if len(commands) > 6:
        listed += ", and others"
    return [
        f'{indent}"""{summary}.',
        "",
        f"{indent}Sends {listed}.",
        f'{indent}"""',
    ]


def process(path: Path, *, apply: bool) -> int:
    """Insert docstrings into ``path``. Returns how many were added."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()

    insertions: list[tuple[int, list[str]]] = []
    for parent in ast.walk(tree):
        if not isinstance(parent, ast.ClassDef):
            continue
        for node in parent.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("_"):
                continue
            if ast.get_docstring(node) is not None:
                continue
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                if first.value.value is Ellipsis:
                    # A Protocol stub: "def read(self) -> bytes: ...". Its body
                    # shares the signature's line, so there is nowhere to insert,
                    # and a stub needs no docstring anyway.
                    continue
            if first.lineno <= node.lineno:
                # Any other single-line body, for the same reason.
                continue
            decorators = {
                d.id if isinstance(d, ast.Name) else getattr(d, "attr", "")
                for d in node.decorator_list
            }
            is_property = "property" in decorators or "setter" in decorators
            body_line = node.body[0].lineno - 1
            indent = " " * (len(lines[body_line]) - len(lines[body_line].lstrip()))
            block = docstring_for(node, indent, is_property=is_property)
            if block is not None:
                insertions.append((body_line, block))

    if not insertions:
        return 0
    if apply:
        for line_number, block in sorted(insertions, reverse=True):
            lines[line_number:line_number] = block
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(insertions)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--apply", action="store_true", help="write the changes")
    arguments = parser.parse_args()

    total = 0
    for path in arguments.paths:
        added = process(path, apply=arguments.apply)
        total += added
        if added:
            print(f"  {path}: {added}")
    verb = "added" if arguments.apply else "would add"
    print(f"{verb} {total} docstrings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
