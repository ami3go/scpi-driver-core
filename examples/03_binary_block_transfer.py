"""IEEE-488.2 definite-length block transfer, in both directions.

This is the path a scope waveform or an arbitrary-waveform upload takes. The
payload here deliberately contains bytes that look like whitespace, newlines
and nulls, because those are exactly what a careless strip() would destroy.

    python examples/03_binary_block_transfer.py
"""

from __future__ import annotations

from scpi_driver_core import ScpiClient
from scpi_driver_core.scpi import decode_definite_length_block
from scpi_driver_core.simulation import ScriptedScpiTransport

# Every byte value, plus the ones that break naive parsers.
WAVEFORM = bytes(range(256)) + b"\r\n \t \x00 trailing \x00"


def main() -> None:
    instrument = ScriptedScpiTransport()
    instrument.reply_block("CURVE?", WAVEFORM)
    instrument.on("DATA:WIDTH?", "1")
    instrument.open()

    client = ScpiClient(instrument)

    recovered = client.query_binary_block("CURVE?")
    print("declared width :", client.query_int("DATA:WIDTH?"))
    print("bytes received :", len(recovered))
    print("identical      :", recovered == WAVEFORM)

    # Uploading: the header and terminator are added for you.
    client.write_binary_block("CURVE ", WAVEFORM)
    sent = instrument.inner.written.split(b"CURVE ", 1)[1]
    print("bytes sent     :", len(sent))
    print("round trips    :", decode_definite_length_block(sent) == WAVEFORM)

    instrument.close()


if __name__ == "__main__":
    main()
