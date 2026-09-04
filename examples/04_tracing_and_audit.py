"""Protocol tracing to a JSONL audit file, with redaction.

Any transport can be wrapped, so this works identically over TCP, VISA, or the
simulator used here.

    python examples/04_tracing_and_audit.py
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from scpi_driver_core import ScpiClient
from scpi_driver_core.simulation import ScriptedScpiTransport
from scpi_driver_core.tracing import (
    InstrumentedTransport,
    JsonlTraceSink,
    PatternRedactor,
    TraceContext,
    Tracer,
)


def main() -> None:
    audit_path = Path(tempfile.gettempdir()) / "scpi-audit.jsonl"
    audit_path.unlink(missing_ok=True)

    instrument = ScriptedScpiTransport()
    instrument.on("*IDN?", "ACME,PSU-1000,SN1,1.0")
    instrument.on("CAL:SEC:STAT ON,hunter2")

    # The driver decides what is sensitive; the core only applies the rule.
    redactor = PatternRedactor([r"CAL:SEC:STAT ON,(\S+)"])

    with JsonlTraceSink(audit_path) as sink:
        tracer = Tracer(sink, redactor=redactor, context=TraceContext("psu", 1))
        transport = InstrumentedTransport(instrument, tracer)
        transport.open()

        client = ScpiClient(transport)
        client.query("*IDN?")
        client.write("CAL:SEC:STAT ON,hunter2")
        transport.close()

    records = [json.loads(line) for line in audit_path.read_text().splitlines()]
    for record in records:
        print(
            f"#{record['sequence']:<2} {record['direction']:<5} "
            f"{record.get('text', '').strip()!r:<40} "
            f"redacted={record.get('redacted', False)}"
        )

    raw = audit_path.read_text()
    print()
    print("secret absent from the audit file :", "hunter2" not in raw)
    print("audit written to                  :", audit_path)


if __name__ == "__main__":
    main()
