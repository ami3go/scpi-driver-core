from __future__ import annotations

from pathlib import Path

import pytest

from scpi_driver_core import ScpiClient, ScpiSession
from scpi_driver_core.transport import VisaTransport

_SIM_DEFINITION = Path(__file__).with_name("fixtures") / "pyvisa_sim.yaml"


@pytest.mark.integration
@pytest.mark.visa_sim
def test_visa_transport_through_pyvisa_sim() -> None:
    transport = VisaTransport(
        "GPIB0::9::INSTR",
        timeout_s=1.0,
        visa_library=f"{_SIM_DEFINITION.resolve()}@sim",
    )
    session = ScpiSession("visa-sim", ScpiClient(transport))

    session.open()
    try:
        identity = session.get_identity()
        assert identity.manufacturer == "SCPI Core"
        assert identity.model == "Simulator"
        assert identity.serial_number == "SIM0001"
        assert identity.firmware_version == "1.0"

        session.client.write("VOLT 2.500")
        assert session.client.query_float("VOLT?") == pytest.approx(2.5)
    finally:
        session.close()
