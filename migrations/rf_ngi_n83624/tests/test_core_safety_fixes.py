from __future__ import annotations

import time

import pytest

from ngi_n83624 import (
    ChannelLimits,
    DriverSafetyPolicy,
    InstrumentLimits,
    N83624CellSimulator,
)
from ngi_n83624.emulator import SimpleN83624Emulator
from ngi_n83624.exceptions import CommunicationError, SafetyError
from ngi_n83624.models import CommunicationObservation


class OneChannelOffFailureTransport(SimpleN83624Emulator):
    def write(self, command: str) -> None:
        if command == "OUTPut2:ONOFF 0":
            self.all_commands.append(command)
            raise CommunicationError("injected CH2 shutdown failure")
        super().write(command)


def limits() -> InstrumentLimits:
    return InstrumentLimits(
        default_channel_limits=ChannelLimits(max_voltage_v=5.0, max_current_ma=1000.0)
    )


def test_all_outputs_off_attempts_remaining_channels_after_failure() -> None:
    transport = OneChannelOffFailureTransport()
    driver = N83624CellSimulator(
        transport,
        limits=limits(),
        safety_policy=DriverSafetyPolicy(
            require_identity_check_on_connect=True,
            require_status_check_after_setters=False,
            require_interlock_for_output_on=False,
        ),
    )
    driver.connect()
    with pytest.raises(SafetyError, match="CH2"):
        driver.all_outputs_off()
    assert "OUTPut1:ONOFF 0" in transport.all_commands
    assert "OUTPut2:ONOFF 0" in transport.all_commands
    assert "OUTPut24:ONOFF 0" in transport.all_commands
    driver.transport.close()


def test_communication_observation_uses_monotonic_clock() -> None:
    before = time.monotonic()
    observation = CommunicationObservation.success()
    after = time.monotonic()
    assert observation.last_success_monotonic_s is not None
    assert before <= observation.last_success_monotonic_s <= after
