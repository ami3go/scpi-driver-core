from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from scpi_driver_core import ScpiClient, ScpiSession
from scpi_driver_core.transport import VisaTransport

_SIM_DEFINITION = Path(__file__).with_name("fixtures") / "pyvisa_sim.yaml"

pytestmark = [pytest.mark.integration, pytest.mark.visa_sim]


@pytest.fixture
def visa_sim_session() -> Iterator[ScpiSession]:
    transport = VisaTransport(
        "GPIB0::9::INSTR",
        timeout_s=1.0,
        visa_library=f"{_SIM_DEFINITION.resolve()}@sim",
    )
    session = ScpiSession("visa-sim", ScpiClient(transport))
    session.open()
    try:
        yield session
    finally:
        session.close()


def test_visa_transport_identity_and_stateful_properties(visa_sim_session: ScpiSession) -> None:
    identity = visa_sim_session.get_identity()
    assert identity.manufacturer == "SCPI Core"
    assert identity.model == "Simulator"
    assert identity.serial_number == "SIM0001"
    assert identity.firmware_version == "1.0"

    visa_sim_session.client.write("VOLT 2.500")
    visa_sim_session.client.write("CURR 0.750")

    assert visa_sim_session.client.query_float("VOLT?") == pytest.approx(2.5)
    assert visa_sim_session.client.query_float("CURR?") == pytest.approx(0.75)


def test_visa_transport_typed_query_helpers(visa_sim_session: ScpiSession) -> None:
    assert visa_sim_session.client.query_bool("*OPC?") is True
    assert visa_sim_session.client.query_int("*TST?") == 0
    assert visa_sim_session.client.query_csv_floats("MEAS:ALL?") == [1.0, 2.0, 3.0]


def test_ieee488_helpers_use_same_simulated_visa_path(visa_sim_session: ScpiSession) -> None:
    visa_sim_session.ieee488.clear_status()
    assert visa_sim_session.ieee488.operation_complete() is True
    assert visa_sim_session.ieee488.self_test().code == 0


def test_visa_session_can_close_and_reopen(visa_sim_session: ScpiSession) -> None:
    first_generation = visa_sim_session.generation
    assert visa_sim_session.is_connected is True

    visa_sim_session.close()
    assert visa_sim_session.is_connected is False

    visa_sim_session.open()
    assert visa_sim_session.is_connected is True
    assert visa_sim_session.generation == first_generation + 1
    assert visa_sim_session.get_identity().model == "Simulator"
