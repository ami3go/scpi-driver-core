"""Channel-level NGI N83624 API."""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import TYPE_CHECKING

from .exceptions import DeviceError, ProtocolError, SafetyError
from .models import (
    CaptureRate,
    ChannelConfiguration,
    ChannelStatus,
    CurrentRange,
    FaultSimulationMode,
    Measurement,
    OutputMode,
    SequenceStep,
    SocStep,
)
from .parsing import parse_bool, parse_float, parse_int
from .safety import (
    enforce_channel_limit,
    validate_capture_rate,
    validate_current_range,
    validate_fault_mode,
    validate_float,
    validate_int_range,
    validate_output_mode,
)

if TYPE_CHECKING:  # pragma: no cover
    from .driver import N83624CellSimulator


class N83624Channel:
    """Typed API for one NGI N83624 channel."""

    def __init__(self, instrument: "N83624CellSimulator", channel: int) -> None:
        self.instrument = instrument
        self.channel = channel

    @property
    def limits(self):
        """The limits."""
        return self.instrument.limits.for_channel(self.channel)

    def _cmd(self, root: str, leaf: str) -> str:
        return f"{root}{self.channel}:{leaf}"

    def _write(self, root: str, leaf: str, value: object | None = None) -> None:
        command = self._cmd(root, leaf) if value is None else f"{self._cmd(root, leaf)} {value}"
        self.instrument._write_locked(command)

    def _query(self, root: str, leaf: str) -> str:
        return self.instrument._query_locked(f"{self._cmd(root, leaf)}?")

    def _query_float(self, root: str, leaf: str) -> float:
        command = f"{self._cmd(root, leaf)}?"
        return parse_float(self.instrument._query_locked(command), command=command)

    def _query_int(self, root: str, leaf: str) -> int:
        command = f"{self._cmd(root, leaf)}?"
        return parse_int(self.instrument._query_locked(command), command=command)

    def _query_bool(self, root: str, leaf: str) -> bool:
        command = f"{self._cmd(root, leaf)}?"
        return parse_bool(self.instrument._query_locked(command), command=command)

    # Measurement -----------------------------------------------------------------
    def measure_current_ma(self) -> float:
        """Measure the current ma."""
        with self.instrument.locked_operation():
            return self._query_float("MEASure", "CURRent")

    def measure_voltage_v(self) -> float:
        """Measure the voltage in volts."""
        with self.instrument.locked_operation():
            return self._query_float("MEASure", "VOLTage")

    def measure_power_w(self) -> float:
        """Measure the power w."""
        with self.instrument.locked_operation():
            return self._query_float("MEASure", "POWer")

    def measure_capacity_mah(self) -> float:
        """Measure the capacity mah."""
        with self.instrument.locked_operation():
            return self._query_float("MEASure", "MAH")

    def measure_resistance_mohm(self) -> float:
        """Measure the resistance mohm."""
        with self.instrument.locked_operation():
            return self._query_float("MEASure", "Res")

    def set_capture_rate(self, rate: CaptureRate | int) -> None:
        """Set the capture rate.

        Sends ``MEASure``, ``CAPRate``.
        """
        rate = validate_capture_rate(rate)
        with self.instrument.locked_operation():
            self._write("MEASure", "CAPRate", int(rate))

    def get_capture_rate(self) -> CaptureRate:
        """Return the capture rate."""
        with self.instrument.locked_operation():
            return validate_capture_rate(self._query_int("MEASure", "CAPRate"))

    def measure_all(self) -> Measurement:
        """Measure the all."""
        with self.instrument.locked_operation():
            return Measurement(
                channel=self.channel,
                voltage_v=self._query_float("MEASure", "VOLTage"),
                current_ma=self._query_float("MEASure", "CURRent"),
                power_w=self._query_float("MEASure", "POWer"),
                capacity_mah=self._query_float("MEASure", "MAH"),
                resistance_mohm=self._query_float("MEASure", "Res"),
            )

    # Output ----------------------------------------------------------------------
    def set_mode(self, mode: OutputMode | int, *, output_off_first: bool = True, verify: bool = True) -> None:
        """Set the mode.

        Sends ``OUTPut``, ``MODE``, ``ONOFF``.
        """
        mode = validate_output_mode(mode)
        with self.instrument.locked_operation():
            if output_off_first:
                self._write("OUTPut", "ONOFF", 0)
            self._write("OUTPut", "MODE", int(mode))
            if verify:
                actual = self.get_mode()
                if actual != mode:
                    raise DeviceError(f"Mode verify failed on channel {self.channel}: expected {mode}, got {actual}")

    def get_mode(self) -> OutputMode:
        """Return the mode."""
        value = self._query_int("OUTPut", "MODE")
        return validate_output_mode(value)

    def output_on(self) -> None:
        self.set_output(True)

    def output_off(self) -> None:
        self.set_output(False)

    def set_output(self, enabled: bool) -> None:
        """Set the output.

        Sends ``OUTPut``, ``ONOFF``.
        """
        with self.instrument.locked_operation():
            if enabled:
                if self.instrument.safety_policy.require_interlock_for_output_on:
                    self.instrument.bench_interlock.assert_output_allowed(self.channel)
                if self.instrument.safety_policy.require_limits_before_output_on and not self.limits.has_output_enable_limits():
                    raise SafetyError(
                        "Output enable requires model-specific max_voltage_v and max_current_ma limits for "
                        f"channel {self.channel}"
                    )
            self._write("OUTPut", "ONOFF", 1 if enabled else 0)
            if self.instrument.safety_policy.require_status_check_after_setters:
                if self.get_output() != bool(enabled):
                    raise DeviceError(f"Output state verify failed on channel {self.channel}")

    def get_output(self) -> bool:
        """Return the output."""
        return self._query_bool("OUTPut", "ONOFF")

    def get_status(self) -> ChannelStatus:
        """Return the status."""
        return ChannelStatus.from_raw(self._query_int("OUTPut", "STATe"))

    def get_event(self) -> ChannelStatus:
        """Return the event."""
        return ChannelStatus.from_raw(self._query_int("OUTPut", "EVENt"))

    def set_on_dwell_us(self, dwell_us: int) -> None:
        """Set the on dwell us.

        Sends ``OUTPut``, ``ONDWell``.
        """
        validate_int_range("on dwell", dwell_us, 0, 0xFFFFFFFE)
        with self.instrument.locked_operation():
            self._write("OUTPut", "ONDWell", dwell_us)

    def get_on_dwell_us(self) -> int:
        """Return the on dwell us."""
        with self.instrument.locked_operation():
            return self._query_int("OUTPut", "ONDWell")

    # Source ----------------------------------------------------------------------
    def configure_source(
        self,
        voltage_v: float,
        current_limit_ma: float,
        current_range: CurrentRange | int = CurrentRange.AUTO,
        *,
        output: bool | None = None,
        output_off_first: bool = True,
        verify: bool = True,
    ) -> None:
        """Configure source.

        Sends ``OUTPut``, ``MODE``, ``SOURce``, ``VOLTage``, ``OUTCURRent``, ``RANGe``, and others.
        """
        voltage_v = self._validate_voltage(voltage_v)
        current_limit_ma = self._validate_current(current_limit_ma)
        current_range = validate_current_range(current_range)
        with self.instrument.locked_operation():
            if output_off_first:
                self._write("OUTPut", "ONOFF", 0)
            self._write("OUTPut", "MODE", int(OutputMode.SOURCE))
            self._write("SOURce", "VOLTage", voltage_v)
            self._write("SOURce", "OUTCURRent", current_limit_ma)
            self._write("SOURce", "RANGe", int(current_range))
            if verify:
                self._verify_float("SOURce", "VOLTage", voltage_v)
                self._verify_float("SOURce", "OUTCURRent", current_limit_ma)
                if self.get_source_current_range() != current_range:
                    raise DeviceError("Source current range verify failed")
            if output is not None:
                self.set_output(output)

    def set_source_voltage_v(self, voltage_v: float) -> None:
        """Set the source voltage in volts.

        Sends ``SOURce``, ``VOLTage``.
        """
        voltage_v = self._validate_voltage(voltage_v)
        with self.instrument.locked_operation():
            self._write("SOURce", "VOLTage", voltage_v)

    def get_source_voltage_v(self) -> float:
        """Return the source voltage in volts."""
        return self._query_float("SOURce", "VOLTage")

    def set_source_current_limit_ma(self, current_ma: float) -> None:
        """Set the source current limit ma.

        Sends ``SOURce``, ``OUTCURRent``.
        """
        current_ma = self._validate_current(current_ma)
        with self.instrument.locked_operation():
            self._write("SOURce", "OUTCURRent", current_ma)

    def get_source_current_limit_ma(self) -> float:
        """Return the source current limit ma."""
        return self._query_float("SOURce", "OUTCURRent")

    def set_source_current_range(self, range_: CurrentRange | int) -> None:
        """Set the source current range.

        Sends ``SOURce``, ``RANGe``.
        """
        range_ = validate_current_range(range_)
        with self.instrument.locked_operation():
            self._write("SOURce", "RANGe", int(range_))

    def get_source_current_range(self) -> CurrentRange:
        """Return the source current range."""
        return validate_current_range(self._query_int("SOURce", "RANGe"))

    # Charge ----------------------------------------------------------------------
    def configure_charge(
        self,
        voltage_v: float,
        current_limit_ma: float,
        resistance_mohm: float,
        *,
        output: bool | None = None,
        output_off_first: bool = True,
        verify: bool = True,
    ) -> None:
        """Configure charge.

        Sends ``OUTPut``, ``MODE``, ``CHARge``, ``VOLTage``, ``OUTCURRent``, ``Res``, and others.
        """
        voltage_v = self._validate_voltage(voltage_v)
        current_limit_ma = self._validate_current(current_limit_ma)
        resistance_mohm = self._validate_resistance(resistance_mohm)
        with self.instrument.locked_operation():
            if output_off_first:
                self._write("OUTPut", "ONOFF", 0)
            self._write("OUTPut", "MODE", int(OutputMode.CHARGE))
            self._write("CHARge", "VOLTage", voltage_v)
            self._write("CHARge", "OUTCURRent", current_limit_ma)
            self._write("CHARge", "Res", resistance_mohm)
            if verify:
                self._verify_float("CHARge", "VOLTage", voltage_v)
                self._verify_float("CHARge", "OUTCURRent", current_limit_ma)
                self._verify_float("CHARge", "Res", resistance_mohm)
            if output is not None:
                self.set_output(output)

    def set_charge_voltage_v(self, voltage_v: float) -> None:
        """Set the charge voltage in volts.

        Sends ``CHARge``, ``VOLTage``.
        """
        voltage_v = self._validate_voltage(voltage_v)
        with self.instrument.locked_operation():
            self._write("CHARge", "VOLTage", voltage_v)

    def get_charge_voltage_v(self) -> float:
        """Return the charge voltage in volts."""
        return self._query_float("CHARge", "VOLTage")

    def set_charge_current_limit_ma(self, current_ma: float) -> None:
        """Set the charge current limit ma.

        Sends ``CHARge``, ``OUTCURRent``.
        """
        current_ma = self._validate_current(current_ma)
        with self.instrument.locked_operation():
            self._write("CHARge", "OUTCURRent", current_ma)

    def get_charge_current_limit_ma(self) -> float:
        """Return the charge current limit ma."""
        return self._query_float("CHARge", "OUTCURRent")

    def set_charge_resistance_mohm(self, resistance_mohm: float) -> None:
        """Set the charge resistance mohm.

        Sends ``CHARge``, ``Res``.
        """
        resistance_mohm = self._validate_resistance(resistance_mohm)
        with self.instrument.locked_operation():
            self._write("CHARge", "Res", resistance_mohm)

    def get_charge_resistance_mohm(self) -> float:
        """Return the charge resistance mohm."""
        return self._query_float("CHARge", "Res")

    def read_charge_echo_voltage_v(self) -> float:
        """Read the charge echo voltage in volts."""
        return self._query_float("CHARge", "ECHO:VOLTage")

    def read_charge_echo_capacity_mah(self) -> float:
        """Read the charge echo capacity mah."""
        return self._query_float("CHARge", "ECHO:Q")

    # SOC -------------------------------------------------------------------------
    def configure_soc(
        self,
        steps: Sequence[SocStep],
        *,
        file_number: int | None = None,
        start_voltage_v: float | None = None,
        output: bool | None = None,
        output_off_first: bool = True,
        verify: bool = True,
    ) -> None:
        """Configure soc.

        Sends ``OUTPut``, ``MODE``, ``SOC``, ``EDIT:FILE``, ``EDIT:LENGth``, ``ONOFF``, and others.
        """
        step_list = list(steps)
        validate_int_range("SOC step count", len(step_list), 0, 200)
        if file_number is not None:
            validate_int_range("SOC file number", file_number, 1, 8)
        if start_voltage_v is not None:
            start_voltage_v = self._validate_voltage(start_voltage_v)
        for step in step_list:
            self._validate_capacity(step.capacity_mah)
            self._validate_voltage(step.voltage_v)
            self._validate_current(step.current_limit_ma)
            self._validate_resistance(step.resistance_mohm)
        with self.instrument.locked_operation():
            if file_number is None:
                file_number = self.get_soc_file()
                validate_int_range("current SOC file number", file_number, 1, 8)
            if output_off_first:
                self._write("OUTPut", "ONOFF", 0)
            self._write("OUTPut", "MODE", int(OutputMode.SOC))
            self._write("SOC", "EDIT:FILE", file_number)
            self._write("SOC", "EDIT:LENGth", len(step_list))
            for idx, step in enumerate(step_list, start=1):
                self._write("SOC", "EDIT:STEP", idx)
                self._write("SOC", "EDIT:Q", step.capacity_mah)
                self._write("SOC", "EDIT:VOLTage", step.voltage_v)
                self._write("SOC", "EDIT:OUTCURRent", step.current_limit_ma)
                self._write("SOC", "EDIT:Res", step.resistance_mohm)
            if start_voltage_v is not None:
                self._write("SOC", "EDIT:SVOLtage", start_voltage_v)
            if verify:
                if self.get_soc_length() != len(step_list):
                    raise DeviceError("SOC length verify failed")
            if output is not None:
                self.set_output(output)

    def set_soc_file(self, file_number: int) -> None:
        """Set the soc file.

        Sends ``SOC``, ``EDIT:FILE``.
        """
        validate_int_range("SOC file number", file_number, 1, 8)
        with self.instrument.locked_operation():
            self._write("SOC", "EDIT:FILE", file_number)

    def get_soc_file(self) -> int:
        """Return the soc file."""
        return self._query_int("SOC", "EDIT:FILE")

    def set_soc_length(self, length: int) -> None:
        """Set the soc length.

        Sends ``SOC``, ``EDIT:LENGth``.
        """
        validate_int_range("SOC length", length, 0, 200)
        with self.instrument.locked_operation():
            self._write("SOC", "EDIT:LENGth", length)

    def get_soc_length(self) -> int:
        """Return the soc length."""
        return self._query_int("SOC", "EDIT:LENGth")

    def set_soc_edit_step(self, step: int) -> None:
        """Set the soc edit step.

        Sends ``SOC``, ``EDIT:STEP``.
        """
        validate_int_range("SOC edit step", step, 1, 200)
        with self.instrument.locked_operation():
            self._write("SOC", "EDIT:STEP", step)

    def get_soc_edit_step(self) -> int:
        """Return the soc edit step."""
        return self._query_int("SOC", "EDIT:STEP")

    def set_soc_step_voltage_v(self, voltage_v: float) -> None:
        """Set the soc step voltage in volts.

        Sends ``SOC``, ``EDIT:VOLTage``.
        """
        voltage_v = self._validate_voltage(voltage_v)
        with self.instrument.locked_operation():
            self._write("SOC", "EDIT:VOLTage", voltage_v)

    def get_soc_step_voltage_v(self) -> float:
        """Return the soc step voltage in volts."""
        return self._query_float("SOC", "EDIT:VOLTage")

    def set_soc_step_current_limit_ma(self, current_ma: float) -> None:
        """Set the soc step current limit ma.

        Sends ``SOC``, ``EDIT:OUTCURRent``.
        """
        current_ma = self._validate_current(current_ma)
        with self.instrument.locked_operation():
            self._write("SOC", "EDIT:OUTCURRent", current_ma)

    def get_soc_step_current_limit_ma(self) -> float:
        """Return the soc step current limit ma."""
        return self._query_float("SOC", "EDIT:OUTCURRent")

    def set_soc_step_resistance_mohm(self, resistance_mohm: float) -> None:
        """Set the soc step resistance mohm.

        Sends ``SOC``, ``EDIT:Res``.
        """
        resistance_mohm = self._validate_resistance(resistance_mohm)
        with self.instrument.locked_operation():
            self._write("SOC", "EDIT:Res", resistance_mohm)

    def get_soc_step_resistance_mohm(self) -> float:
        """Return the soc step resistance mohm."""
        return self._query_float("SOC", "EDIT:Res")

    def set_soc_step_capacity_mah(self, capacity_mah: float) -> None:
        """Set the soc step capacity mah.

        Sends ``SOC``, ``EDIT:Q``.
        """
        capacity_mah = self._validate_capacity(capacity_mah)
        with self.instrument.locked_operation():
            self._write("SOC", "EDIT:Q", capacity_mah)

    def get_soc_step_capacity_mah(self) -> float:
        """Return the soc step capacity mah."""
        return self._query_float("SOC", "EDIT:Q")

    def set_soc_start_voltage_v(self, voltage_v: float) -> None:
        """Set the soc start voltage in volts.

        Sends ``SOC``, ``EDIT:SVOLtage``.
        """
        voltage_v = self._validate_voltage(voltage_v)
        with self.instrument.locked_operation():
            self._write("SOC", "EDIT:SVOLtage", voltage_v)

    def get_soc_start_voltage_v(self) -> float:
        """Return the soc start voltage in volts."""
        return self._query_float("SOC", "EDIT:SVOLtage")

    def get_soc_running_step(self) -> int:
        """Return the soc running step."""
        return self._query_int("SOC", "RUN:STEP")

    def get_soc_running_capacity_mah(self) -> float:
        """Return the soc running capacity mah."""
        return self._query_float("SOC", "RUN:Q")

    def get_soc_open_voltage_v(self) -> float:
        """Return the soc open voltage in volts."""
        return self._query_float("SOC", "OPEN:VOLTage")

    def get_soc_simulated_resistance_mohm(self) -> float:
        """Return the soc simulated resistance mohm."""
        return self._query_float("SOC", "SIM:RES")

    # Sequence --------------------------------------------------------------------
    def configure_sequence(
        self,
        file_number: int,
        steps: Sequence[SequenceStep],
        *,
        file_cycle: int = 1,
        output: bool | None = None,
        output_off_first: bool = True,
        verify: bool = True,
    ) -> None:
        """Configure sequence.

        Sends ``OUTPut``, ``MODE``, ``SEQuence``, ``EDIT:FILE``, ``EDIT:LENGth``, ``EDIT:CYCle``, and others.
        """
        validate_int_range("SEQ file number", file_number, 1, 10)
        validate_int_range("SEQ file cycle", file_cycle, 0, 100)
        step_list = list(steps)
        validate_int_range("SEQ step count", len(step_list), 0, 200)
        for step in step_list:
            self._validate_voltage(step.voltage_v)
            self._validate_current(step.current_limit_ma)
            self._validate_resistance(step.resistance_mohm)
            self._validate_runtime(step.runtime_s)
            validate_int_range("SEQ link start", step.link_start, -1, 200)
            validate_int_range("SEQ link end", step.link_end, -1, 200)
            validate_int_range("SEQ link cycle", step.link_cycle, 0, 100)
        with self.instrument.locked_operation():
            if output_off_first:
                self._write("OUTPut", "ONOFF", 0)
            self._write("OUTPut", "MODE", int(OutputMode.SEQUENCE))
            self._write("SEQuence", "EDIT:FILE", file_number)
            self._write("SEQuence", "EDIT:LENGth", len(step_list))
            self._write("SEQuence", "EDIT:CYCle", file_cycle)
            for idx, step in enumerate(step_list, start=1):
                self._write("SEQuence", "EDIT:STEP", idx)
                self._write("SEQuence", "EDIT:VOLTage", step.voltage_v)
                self._write("SEQuence", "EDIT:OUTCURRent", step.current_limit_ma)
                self._write("SEQuence", "EDIT:Res", step.resistance_mohm)
                self._write("SEQuence", "EDIT:RUNTime", step.runtime_s)
                self._write("SEQuence", "EDIT:LINKStart", step.link_start)
                self._write("SEQuence", "EDIT:LINKEnd", step.link_end)
                self._write("SEQuence", "EDIT:LINKCycle", step.link_cycle)
            self._write("SEQuence", "RUN:FILE", file_number)
            if verify and self.get_sequence_length() != len(step_list):
                raise DeviceError("SEQ length verify failed")
            if output is not None:
                self.set_output(output)

    def set_sequence_edit_file(self, file_number: int) -> None:
        """Set the sequence edit file.

        Sends ``SEQuence``, ``EDIT:FILE``.
        """
        validate_int_range("SEQ edit file", file_number, 1, 10)
        with self.instrument.locked_operation():
            self._write("SEQuence", "EDIT:FILE", file_number)

    def get_sequence_edit_file(self) -> int:
        """Return the sequence edit file."""
        return self._query_int("SEQuence", "EDIT:FILE")

    def set_sequence_length(self, length: int) -> None:
        """Set the sequence length.

        Sends ``SEQuence``, ``EDIT:LENGth``.
        """
        validate_int_range("SEQ length", length, 0, 200)
        with self.instrument.locked_operation():
            self._write("SEQuence", "EDIT:LENGth", length)

    def get_sequence_length(self) -> int:
        """Return the sequence length."""
        return self._query_int("SEQuence", "EDIT:LENGth")

    def set_sequence_edit_step(self, step: int) -> None:
        """Set the sequence edit step.

        Sends ``SEQuence``, ``EDIT:STEP``.
        """
        validate_int_range("SEQ edit step", step, 1, 200)
        with self.instrument.locked_operation():
            self._write("SEQuence", "EDIT:STEP", step)

    def get_sequence_edit_step(self) -> int:
        """Return the sequence edit step."""
        return self._query_int("SEQuence", "EDIT:STEP")

    def set_sequence_file_cycle(self, cycle: int) -> None:
        """Set the sequence file cycle.

        Sends ``SEQuence``, ``EDIT:CYCle``.
        """
        validate_int_range("SEQ file cycle", cycle, 0, 100)
        with self.instrument.locked_operation():
            self._write("SEQuence", "EDIT:CYCle", cycle)

    def get_sequence_file_cycle(self) -> int:
        """Return the sequence file cycle."""
        return self._query_int("SEQuence", "EDIT:CYCle")

    def set_sequence_step_voltage_v(self, voltage_v: float) -> None:
        """Set the sequence step voltage in volts.

        Sends ``SEQuence``, ``EDIT:VOLTage``.
        """
        voltage_v = self._validate_voltage(voltage_v)
        with self.instrument.locked_operation():
            self._write("SEQuence", "EDIT:VOLTage", voltage_v)

    def get_sequence_step_voltage_v(self) -> float:
        """Return the sequence step voltage in volts."""
        return self._query_float("SEQuence", "EDIT:VOLTage")

    def set_sequence_step_current_limit_ma(self, current_ma: float) -> None:
        """Set the sequence step current limit ma.

        Sends ``SEQuence``, ``EDIT:OUTCURRent``.
        """
        current_ma = self._validate_current(current_ma)
        with self.instrument.locked_operation():
            self._write("SEQuence", "EDIT:OUTCURRent", current_ma)

    def get_sequence_step_current_limit_ma(self) -> float:
        """Return the sequence step current limit ma."""
        return self._query_float("SEQuence", "EDIT:OUTCURRent")

    def set_sequence_step_resistance_mohm(self, resistance_mohm: float) -> None:
        """Set the sequence step resistance mohm.

        Sends ``SEQuence``, ``EDIT:Res``.
        """
        resistance_mohm = self._validate_resistance(resistance_mohm)
        with self.instrument.locked_operation():
            self._write("SEQuence", "EDIT:Res", resistance_mohm)

    def get_sequence_step_resistance_mohm(self) -> float:
        """Return the sequence step resistance mohm."""
        return self._query_float("SEQuence", "EDIT:Res")

    def set_sequence_step_runtime_s(self, runtime_s: float) -> None:
        """Set the sequence step runtime in seconds.

        Sends ``SEQuence``, ``EDIT:RUNTime``.
        """
        runtime_s = self._validate_runtime(runtime_s)
        with self.instrument.locked_operation():
            self._write("SEQuence", "EDIT:RUNTime", runtime_s)

    def get_sequence_step_runtime_s(self) -> float:
        """Return the sequence step runtime in seconds."""
        return self._query_float("SEQuence", "EDIT:RUNTime")

    def set_sequence_link_start(self, step: int) -> None:
        """Set the sequence link start.

        Sends ``SEQuence``, ``EDIT:LINKStart``.
        """
        validate_int_range("SEQ link start", step, -1, 200)
        with self.instrument.locked_operation():
            self._write("SEQuence", "EDIT:LINKStart", step)

    def get_sequence_link_start(self) -> int:
        """Return the sequence link start."""
        return self._query_int("SEQuence", "EDIT:LINKStart")

    def set_sequence_link_end(self, step: int) -> None:
        """Set the sequence link end.

        Sends ``SEQuence``, ``EDIT:LINKEnd``.
        """
        validate_int_range("SEQ link end", step, -1, 200)
        with self.instrument.locked_operation():
            self._write("SEQuence", "EDIT:LINKEnd", step)

    def get_sequence_link_end(self) -> int:
        """Return the sequence link end."""
        return self._query_int("SEQuence", "EDIT:LINKEnd")

    def set_sequence_link_cycle(self, cycle: int) -> None:
        """Set the sequence link cycle.

        Sends ``SEQuence``, ``EDIT:LINKCycle``.
        """
        validate_int_range("SEQ link cycle", cycle, 0, 100)
        with self.instrument.locked_operation():
            self._write("SEQuence", "EDIT:LINKCycle", cycle)

    def get_sequence_link_cycle(self) -> int:
        """Return the sequence link cycle."""
        return self._query_int("SEQuence", "EDIT:LINKCycle")

    def set_sequence_run_file(self, file_number: int) -> None:
        """Set the sequence run file.

        Sends ``SEQuence``, ``RUN:FILE``.
        """
        validate_int_range("SEQ run file", file_number, 1, 10)
        with self.instrument.locked_operation():
            self._write("SEQuence", "RUN:FILE", file_number)

    def get_sequence_run_file(self) -> int:
        """Return the sequence run file."""
        return self._query_int("SEQuence", "RUN:FILE")

    def get_sequence_running_step(self) -> int:
        """Return the sequence running step."""
        return self._query_int("SEQuence", "RUN:STEP")

    def get_sequence_running_cycle(self) -> int:
        """Return the sequence running cycle."""
        return self._query_int("SEQuence", "RUN:Cycle")

    def get_sequence_running_time_s(self) -> float:
        """Return the sequence running time in seconds."""
        return self._query_float("SEQuence", "RUN:Time")

    # Protection ------------------------------------------------------------------
    def set_ocp_current_ma(self, current_ma: float) -> None:
        """Set the ocp current ma.

        Sends ``PRO``, ``CURRent``.
        """
        current_ma = self._validate_current(current_ma)
        with self.instrument.locked_operation():
            self._write("PRO", "CURRent", current_ma)

    def get_ocp_current_ma(self) -> float:
        """Return the ocp current ma."""
        return self._query_float("PRO", "CURRent")

    def set_ovp_voltage_v(self, voltage_v: float) -> None:
        """Set the ovp voltage in volts.

        Sends ``PRO``, ``VOLTage``.
        """
        voltage_v = self._validate_voltage(voltage_v)
        with self.instrument.locked_operation():
            self._write("PRO", "VOLTage", voltage_v)

    def get_ovp_voltage_v(self) -> float:
        """Return the ovp voltage in volts."""
        return self._query_float("PRO", "VOLTage")

    def set_opp_power_mw(self, power_mw: float) -> None:
        """Set the opp power mw.

        Sends ``PRO``, ``POWEr``.
        """
        power_mw = self._validate_power(power_mw)
        with self.instrument.locked_operation():
            self._write("PRO", "POWEr", power_mw)

    def get_opp_power_mw(self) -> float:
        """Return the opp power mw."""
        return self._query_float("PRO", "POWEr")

    # CAN -------------------------------------------------------------------------
    def get_can_id(self) -> int:
        """Return the can id."""
        return self._query_int("CFG", "CANID")

    def set_can_upload_time_ms(self, time_ms: int) -> None:
        """Set the can upload time in milliseconds.

        Sends ``CFG``, ``UPTime``.
        """
        if time_ms != 0 and time_ms < 60:
            raise SafetyError("CAN upload time must be 0 or >= 60 ms")
        validate_int_range("CAN upload time", time_ms, 0, 2_147_483_647)
        with self.instrument.locked_operation():
            self._write("CFG", "UPTime", time_ms)

    def get_can_upload_time_ms(self) -> int:
        """Return the can upload time in milliseconds."""
        return self._query_int("CFG", "UPTime")

    def get_can_rate(self) -> int:
        """Return the can rate."""
        return self._query_int("CFG", "CANRate")

    def get_extended_can_id(self) -> int:
        """Return the extended can id."""
        return self._query_int("CFG", "EXTCanid")

    # Fault simulation -------------------------------------------------------------
    def set_fault_simulation(
        self,
        mode: FaultSimulationMode | int,
        *,
        require_zero_output: bool = True,
        force: bool = False,
        voltage_zero_threshold_v: float = 0.05,
        current_zero_threshold_ma: float = 1.0,
        settle_timeout_s: float = 5.0,
    ) -> None:
        """Set the fault simulation.

        Sends ``FAULt``, ``SIMUlate``, ``OUTPut``, ``ONOFF``.
        """
        mode = validate_fault_mode(mode)
        validate_float("voltage zero threshold", voltage_zero_threshold_v)
        validate_float("current zero threshold", current_zero_threshold_ma)
        validate_float("settle timeout", settle_timeout_s)
        with self.instrument.locked_operation():
            if not self.instrument.safety_policy.fault_simulation_enabled:
                raise SafetyError("Fault simulation is disabled by DriverSafetyPolicy")
            if self.instrument.safety_policy.require_interlock_for_fault_simulation:
                self.instrument.bench_interlock.assert_fault_simulation_allowed(self.channel)
            if self.get_mode() != OutputMode.SOURCE:
                raise SafetyError("Fault simulation is only allowed in source mode")
            if require_zero_output and not force:
                self._write("OUTPut", "ONOFF", 0)
                deadline = time.monotonic() + settle_timeout_s
                while True:
                    voltage = abs(self._query_float("MEASure", "VOLTage"))
                    current = abs(self._query_float("MEASure", "CURRent"))
                    if voltage <= voltage_zero_threshold_v and current <= current_zero_threshold_ma:
                        break
                    if time.monotonic() > deadline:
                        raise SafetyError(
                            "Output did not settle below fault-simulation thresholds; "
                            f"voltage={voltage} V, current={current} mA"
                        )
                    time.sleep(0.05)
            self._write("FAULt", "SIMUlate", int(mode))
            status = self.get_event()
            if status.fault_relay_voltage_current_present or status.fault_relay_wrong_mode:
                raise DeviceError(f"Fault simulation event bits indicate unsafe operation: {status}")

    def get_fault_simulation(self) -> FaultSimulationMode:
        """Return the fault simulation."""
        value = self._query_int("FAULt", "SIMUlate")
        return validate_fault_mode(value)

    # Configuration snapshot -------------------------------------------------------
    def read_channel_configuration(self) -> ChannelConfiguration:
        """Read the channel configuration."""
        with self.instrument.locked_operation():
            mode = self.get_mode()
            output = self.get_output()
            source_voltage = source_current = None
            source_range = None
            charge_voltage = charge_current = charge_resistance = None
            try:
                source_voltage = self.get_source_voltage_v()
                source_current = self.get_source_current_limit_ma()
                source_range = self.get_source_current_range()
            except ProtocolError:
                pass
            try:
                charge_voltage = self.get_charge_voltage_v()
                charge_current = self.get_charge_current_limit_ma()
                charge_resistance = self.get_charge_resistance_mohm()
            except ProtocolError:
                pass
            return ChannelConfiguration(
                channel=self.channel,
                mode=mode,
                output_enabled=output,
                source_voltage_v=source_voltage,
                source_current_limit_ma=source_current,
                source_current_range=source_range,
                charge_voltage_v=charge_voltage,
                charge_current_limit_ma=charge_current,
                charge_resistance_mohm=charge_resistance,
                ocp_current_ma=self.get_ocp_current_ma(),
                ovp_voltage_v=self.get_ovp_voltage_v(),
                opp_power_mw=self.get_opp_power_mw(),
                capture_rate=self.get_capture_rate(),
            )

    # Validation helpers -----------------------------------------------------------
    def _validate_voltage(self, value: float | int) -> float:
        value = validate_float("voltage_v", value)
        enforce_channel_limit("voltage_v", value, self.limits)
        return value

    def _validate_current(self, value: float | int) -> float:
        value = validate_float("current_ma", value)
        enforce_channel_limit("current_ma", value, self.limits)
        return value

    def _validate_resistance(self, value: float | int) -> float:
        value = validate_float("resistance_mohm", value)
        enforce_channel_limit("resistance_mohm", value, self.limits)
        return value

    def _validate_power(self, value: float | int) -> float:
        value = validate_float("power_mw", value)
        enforce_channel_limit("power_mw", value, self.limits)
        return value

    def _validate_runtime(self, value: float | int) -> float:
        value = validate_float("runtime_s", value)
        enforce_channel_limit("runtime_s", value, self.limits)
        return value

    def _validate_capacity(self, value: float | int) -> float:
        value = validate_float("capacity_mah", value)
        enforce_channel_limit("capacity_mah", value, self.limits)
        return value

    def _verify_float(self, root: str, leaf: str, expected: float, *, tolerance: float = 1e-9) -> None:
        actual = self._query_float(root, leaf)
        if abs(actual - expected) > tolerance:
            raise DeviceError(f"Verify failed for {root}{self.channel}:{leaf}: expected {expected}, got {actual}")
