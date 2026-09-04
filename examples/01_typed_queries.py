"""Typed SCPI queries against a scripted instrument.

Runnable as-is: no hardware, no network. Swap the transport for a real one and
the rest of the code is unchanged, which is the point of the package.

    python examples/01_typed_queries.py
"""

from __future__ import annotations

from scpi_driver_core import ScpiClient
from scpi_driver_core.simulation import ScriptedScpiTransport


def main() -> None:
    instrument = ScriptedScpiTransport()
    instrument.on("*IDN?", "KEYSIGHT,N6700C,MY56000102,D.01.09")
    instrument.on("MEAS:VOLT?", "1.04858000E+00")
    instrument.on("MEAS:CURR?", "250.0 mA")
    instrument.on("OUTP?", "ON")
    instrument.on("SENS:SWE:POIN?", "1024")
    instrument.on("SYST:CHAN:LIST?", '"CH1","CH2","CH3"')

    instrument.open()
    client = ScpiClient(instrument)

    print("identity     :", client.query("*IDN?"))
    print("voltage      :", client.query_float("MEAS:VOLT?"))
    print("output on    :", client.query_bool("OUTP?"))
    print("sweep points :", client.query_int("SENS:SWE:POIN?"))
    print("channels     :", client.query_csv("SYST:CHAN:LIST?"))

    # Instruments differ on whether they append a unit; this accepts either.
    print("current      :", client.query_optional_unit_float("MEAS:CURR?"))

    instrument.close()


if __name__ == "__main__":
    main()
