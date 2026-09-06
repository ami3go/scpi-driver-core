"""Typed core driver for the Agilent (Keysight) 33220A function/arbitrary waveform generator.

Owns SCPI command construction and response parsing. The Robot Framework
adapter (``rf_agilent33220a/library.py``) is a thin layer on top of this
module and must not duplicate any of this logic (task §5.2).
"""

from __future__ import annotations

import logging
from pathlib import Path

from .enums import (
    AmplitudeUnit,
    BurstMode,
    FrontPanelLockExclude,
    Function,
    GatePolarity,
    ModulatingShape,
    ModulationSource,
    OutputPolarity,
    SweepSpacing,
    TriggerSlope,
    TriggerSource,
)
from scpi_driver_core.exceptions import IdentityError
from scpi_driver_core.scpi import parse_identity

from .exceptions import (
    Agilent33220AConnectionError,
    Agilent33220ADeviceError,
    Agilent33220ASafetyError,
    Agilent33220AValidationError,
)
from .models import ArbWaveformAttributes, InstrumentIdentity, OutputSettings, TriggerSettings
from .simulator import SimAgilent33220AInstrument
from .transport import PyvisaTransport, SimulatedTransport, Transport

logger = logging.getLogger(__name__)

_RAW_SCPI_CONFIRMATION = "ENABLE RAW SCPI"
_CALIBRATION_CONFIRMATION = "ENABLE CALIBRATION"

_APPLY_SUBCOMMAND = {
    Function.SINE: "SINusoid",
    Function.SQUARE: "SQUare",
    Function.RAMP: "RAMP",
    Function.PULSE: "PULSe",
    Function.NOISE: "NOISe",
    Function.DC: "DC",
    Function.USER: "USER",
}



def _identity_fields(raw: str) -> dict[str, str]:
    """Map a parsed ``*IDN?`` reply onto this driver's identity record.

    The core parses. This driver keeps its historical tolerance for partial
    replies, where missing fields become empty strings rather than raising,
    because its callers already depend on that.
    """
    try:
        identity = parse_identity(raw)
    except IdentityError:
        parts = [part.strip() for part in raw.strip().split(",", 3)]
        parts += [""] * (4 - len(parts))
        return {
            "manufacturer": parts[0],
            "model": parts[1],
            "serial": parts[2],
            "firmware": parts[3],
        }
    return {
        "manufacturer": identity.manufacturer,
        "model": identity.model,
        "serial": identity.serial_number or "",
        "firmware": identity.firmware_version or "",
    }


class Agilent33220A:
    """A connected session with one Agilent 33220A instrument."""

    def __init__(self, transport: Transport) -> None:
        self.transport = transport
        self._identity: InstrumentIdentity | None = None
        self._raw_scpi_enabled = False
        self._calibration_enabled = False

    # ------------------------------------------------------------------
    # Construction / lifecycle
    # ------------------------------------------------------------------
    @classmethod
    def connect_visa(cls, resource: str, timeout_s: float = 5.0) -> Agilent33220A:
        """Open a VISA connection and return a connected driver."""
        transport = PyvisaTransport(resource, timeout_s=timeout_s)
        transport.open()
        return cls(transport)

    @classmethod
    def connect_simulated(cls, simulator: SimAgilent33220AInstrument | None = None) -> Agilent33220A:
        """Return a driver backed by the in-process simulator."""
        transport = SimulatedTransport(simulator)
        transport.open()
        return cls(transport)

    def close(self) -> None:
        """Close the connection and release the transport."""
        self.transport.close()

    @property
    def connected(self) -> bool:
        """Whether the transport is currently open."""
        return self.transport.is_open()

    @property
    def resource(self) -> str:
        """The resource string this driver is connected to."""
        return self.transport.resource

    @property
    def timeout_s(self) -> float:
        """The timeout in seconds."""
        return self.transport.timeout_s

    @timeout_s.setter
    def timeout_s(self, value: float) -> None:
        """The timeout in seconds."""
        self.transport.timeout_s = value

    # ------------------------------------------------------------------
    # Low-level I/O with exception translation
    # ------------------------------------------------------------------
    def _require_connected(self) -> None:
        if not self.transport.is_open():
            raise Agilent33220AConnectionError("not connected; call connect_visa/connect_simulated first")

    def _write(self, command: str) -> None:
        self._require_connected()
        self.transport.write(command)

    def _query(self, command: str) -> str:
        self._require_connected()
        return self.transport.query(command)

    def _check_events(self, context: str) -> None:
        """Raise if the instrument's event/error queue reports a problem after ``context``."""

        esr = self._query("*ESR?").strip()
        if esr in ("0", ""):
            return
        message = self._query("SYSTem:ERRor?").strip()
        raise Agilent33220ADeviceError(f"{context} failed: instrument reported an error: {message}")

    # ------------------------------------------------------------------
    # Identity / communication (RFDS-002)
    # ------------------------------------------------------------------
    def identify(self, *, refresh: bool = True) -> InstrumentIdentity:
        """Return the instrument identity.

        Sends ``*IDN?``.
        """
        if not refresh and self._identity is not None:
            return self._identity
        raw = self._query("*IDN?")
        fields = _identity_fields(raw)
        identity = InstrumentIdentity(
            manufacturer=fields["manufacturer"],
            model=fields["model"],
            serial=fields["serial"],
            firmware=fields["firmware"],
            raw=raw.strip(),
        )
        self._identity = identity
        return identity

    def check_communication(self) -> bool:
        """Check the communication.

        Sends ``*IDN?``.
        """
        self._query("*IDN?")
        return True

    # ------------------------------------------------------------------
    # Output configuration (task §8)
    # ------------------------------------------------------------------
    def _query_max_amplitude(self) -> float:
        """VOLTage? MAXimum — the instrument's own current amplitude ceiling.

        Queried live rather than hardcoded: Vmax genuinely depends on the
        current function and output-load setting (task §6 item 4), so a
        static constant would be wrong under some configurations.
        """

        return float(self._query("VOLTage? MAXimum"))

    def _validate_amplitude_offset(self, amplitude: float, offset: float) -> None:
        vmax = self._query_max_amplitude()
        if not (amplitude < 2 * (vmax - abs(offset))):
            raise Agilent33220ASafetyError(
                f"amplitude {amplitude:g} Vpp and offset {offset:g} V violate the documented "
                f"limit Vpp < 2*(Vmax-|Voffset|); Vmax={vmax:g} V for the current configuration"
            )

    def set_function(self, function: Function | str) -> None:
        """Guarded per task §6 item 5: a function change can silently reduce
        frequency/amplitude, which the instrument reports as a "Settings
        conflict" error. Surfaced here as a typed error naming the actual
        (possibly-adjusted) values, not silently swallowed."""

        function = Function(function)
        self._write(f"FUNCtion {function.value}")
        esr = self._query("*ESR?").strip()
        if esr not in ("0", ""):
            message = self._query("SYSTem:ERRor?").strip()
            adjusted_frequency = self.get_frequency()
            adjusted_amplitude = self.get_amplitude()
            raise Agilent33220ADeviceError(
                f"Set Function to {function.value} caused a settings conflict: {message}. "
                f"Instrument adjusted frequency={adjusted_frequency:g} Hz, "
                f"amplitude={adjusted_amplitude:g} {self.get_amplitude_unit().value}."
            )

    def get_function(self) -> Function:
        """Return the function.

        Sends ``FUNCtion?``.
        """
        return Function(self._query("FUNCtion?").strip())

    def set_frequency(self, frequency: float) -> None:
        """Set the frequency.

        Sends ``FREQuency …``.
        """
        frequency = float(frequency)
        if frequency <= 0:
            raise Agilent33220AValidationError("frequency must be positive")
        self._write(f"FREQuency {frequency}")

    def get_frequency(self) -> float:
        """Return the frequency.

        Sends ``FREQuency?``.
        """
        return float(self._query("FREQuency?"))

    def set_amplitude(self, amplitude: float) -> None:
        """Set the amplitude.

        Sends ``VOLTage …``.
        """
        amplitude = float(amplitude)
        if amplitude < 0:
            raise Agilent33220AValidationError("amplitude must not be negative")
        self._validate_amplitude_offset(amplitude, self.get_offset())
        self._write(f"VOLTage {amplitude}")

    def get_amplitude(self) -> float:
        """Return the amplitude.

        Sends ``VOLTage?``.
        """
        return float(self._query("VOLTage?"))

    def set_amplitude_unit(self, unit: AmplitudeUnit | str) -> None:
        """Set the amplitude unit.

        Sends ``VOLTage:UNIT …``.
        """
        unit = AmplitudeUnit(unit)
        self._write(f"VOLTage:UNIT {unit.value}")

    def get_amplitude_unit(self) -> AmplitudeUnit:
        """Return the amplitude unit.

        Sends ``VOLTage:UNIT?``.
        """
        return AmplitudeUnit(self._query("VOLTage:UNIT?").strip())

    def set_offset(self, offset: float) -> None:
        """Set the offset.

        Sends ``VOLTage:OFFSet …``.
        """
        offset = float(offset)
        self._validate_amplitude_offset(self.get_amplitude(), offset)
        self._write(f"VOLTage:OFFSet {offset}")

    def get_offset(self) -> float:
        """Return the offset.

        Sends ``VOLTage:OFFSet?``.
        """
        return float(self._query("VOLTage:OFFSet?"))

    def set_output_load(self, ohms: float | str) -> None:
        """``ohms`` is a positive number, or ``"INFinity"`` for high impedance."""

        self._write(f"OUTPut:LOAD {ohms}")

    def get_output_load(self) -> str:
        """Return the output load.

        Sends ``OUTPut:LOAD?``.
        """
        return self._query("OUTPut:LOAD?").strip()

    def set_output_polarity(self, polarity: OutputPolarity | str) -> None:
        """Set the output polarity.

        Sends ``OUTPut:POLarity …``.
        """
        polarity = OutputPolarity(polarity)
        self._write(f"OUTPut:POLarity {polarity.value}")

    def get_output_polarity(self) -> OutputPolarity:
        """Return the output polarity.

        Sends ``OUTPut:POLarity?``.
        """
        return OutputPolarity(self._query("OUTPut:POLarity?").strip())

    def set_square_duty_cycle(self, percent: float) -> None:
        """Set the square duty cycle.

        Sends ``FUNCtion:SQUare:DCYCle …``.
        """
        percent = float(percent)
        if not (0.0 <= percent <= 100.0):
            raise Agilent33220AValidationError("duty cycle must be between 0 and 100 percent")
        self._write(f"FUNCtion:SQUare:DCYCle {percent}")

    def get_square_duty_cycle(self) -> float:
        """Return the square duty cycle.

        Sends ``FUNCtion:SQUare:DCYCle?``.
        """
        return float(self._query("FUNCtion:SQUare:DCYCle?"))

    def set_ramp_symmetry(self, percent: float) -> None:
        """Set the ramp symmetry.

        Sends ``FUNCtion:RAMP:SYMMetry …``.
        """
        percent = float(percent)
        if not (0.0 <= percent <= 100.0):
            raise Agilent33220AValidationError("ramp symmetry must be between 0 and 100 percent")
        self._write(f"FUNCtion:RAMP:SYMMetry {percent}")

    def get_ramp_symmetry(self) -> float:
        """Return the ramp symmetry.

        Sends ``FUNCtion:RAMP:SYMMetry?``.
        """
        return float(self._query("FUNCtion:RAMP:SYMMetry?"))

    def configure_output(
        self,
        function: Function | str,
        frequency: float,
        amplitude: float,
        offset: float = 0.0,
        *,
        enable_output: bool = False,
    ) -> None:
        """APPLy-backed convenience keyword.

        task §6 item 1: APPLy silently enables the output as a documented
        side effect. This method restores the output to whatever state it
        was in *before* the call unless ``enable_output=True`` is explicitly
        passed — the driver's own default must not inherit that surprise.
        """

        function = Function(function)
        self._validate_amplitude_offset(float(amplitude), float(offset))
        was_enabled = self.is_output_enabled()
        subcommand = _APPLY_SUBCOMMAND[function]
        self._write(f"APPLy:{subcommand} {frequency},{amplitude},{offset}")
        self._check_events("Configure Output")
        if not enable_output and not was_enabled:
            self.disable_output()

    def enable_output(self) -> None:
        """Enable output.

        Sends ``OUTPut ON``.
        """
        logger.info("Agilent33220A: enabling output. settings=%s", self.get_output_settings())
        self._write("OUTPut ON")

    def disable_output(self) -> None:
        """Disable output.

        Sends ``OUTPut OFF``.
        """
        self._write("OUTPut OFF")

    def is_output_enabled(self) -> bool:
        """Whether the output enabled.

        Sends ``OUTPut?``.
        """
        return self._query("OUTPut?").strip() in ("1", "ON")

    def get_output_settings(self) -> OutputSettings:
        """Return the output settings."""
        return OutputSettings(
            function=self.get_function().value,
            frequency=self.get_frequency(),
            amplitude=self.get_amplitude(),
            amplitude_unit=self.get_amplitude_unit().value,
            offset=self.get_offset(),
            output_enabled=self.is_output_enabled(),
            output_load=self.get_output_load(),
            polarity=self.get_output_polarity().value,
        )

    # ------------------------------------------------------------------
    # Front panel / display (task §8)
    # ------------------------------------------------------------------
    def lock_front_panel(self) -> None:
        """Issue the lock front panel command.

        Sends ``SYSTem:KLOCk ON``.
        """
        self._write("SYSTem:KLOCk ON")

    def unlock_front_panel(self) -> None:
        """Issue the unlock front panel command.

        Sends ``SYSTem:KLOCk OFF``.
        """
        self._write("SYSTem:KLOCk OFF")

    def is_front_panel_locked(self) -> bool:
        """Whether the front panel locked.

        Sends ``SYSTem:KLOCk?``.
        """
        return self._query("SYSTem:KLOCk?").strip() in ("1", "ON")

    def set_front_panel_lock_exclude(self, exclude: FrontPanelLockExclude | str) -> None:
        """Set the front panel lock exclude.

        Sends ``SYSTem:KLOCk:EXCLude …``.
        """
        exclude = FrontPanelLockExclude(exclude)
        self._write(f"SYSTem:KLOCk:EXCLude {exclude.value}")

    def set_display_text(self, text: str) -> None:
        """Set the display text."""
        self._write(f'DISPlay:TEXT "{text}"')

    def clear_display_text(self) -> None:
        """Clear the display text.

        Sends ``DISPlay:TEXT:CLEar``.
        """
        self._write("DISPlay:TEXT:CLEar")

    def enable_display(self) -> None:
        """Enable display.

        Sends ``DISPlay ON``.
        """
        self._write("DISPlay ON")

    def disable_display(self) -> None:
        """Disable display.

        Sends ``DISPlay OFF``.
        """
        self._write("DISPlay OFF")

    # ------------------------------------------------------------------
    # Pulse (task §9)
    # ------------------------------------------------------------------
    def configure_pulse(
        self,
        period: float | None = None,
        width: float | None = None,
        duty_cycle: float | None = None,
        transition: float | None = None,
    ) -> None:
        """Configure pulse.

        Sends ``PULSe:PERiod …``, ``FUNCtion:PULSe:HOLD DCYCle``, ``FUNCtion:PULSe:DCYCle …``, ``FUNCtion:PULSe:TRANsition …``, ``FUNCtion:PULSe:HOLD WIDTh``, ``FUNCtion:PULSe:WIDTh …``.
        """
        if period is not None:
            self._write(f"PULSe:PERiod {float(period)}")
        if duty_cycle is not None:
            self._write("FUNCtion:PULSe:HOLD DCYCle")
            self._write(f"FUNCtion:PULSe:DCYCle {float(duty_cycle)}")
        elif width is not None:
            self._write("FUNCtion:PULSe:HOLD WIDTh")
            self._write(f"FUNCtion:PULSe:WIDTh {float(width)}")
        if transition is not None:
            self._write(f"FUNCtion:PULSe:TRANsition {float(transition)}")

    # ------------------------------------------------------------------
    # Modulation (task §9)
    # ------------------------------------------------------------------
    def configure_amplitude_modulation(
        self, shape: ModulatingShape | str, frequency: float, depth_percent: float,
        source: ModulationSource | str = ModulationSource.INTERNAL,
    ) -> None:
        """Configure amplitude modulation.

        Sends ``AM:INTernal:FUNCtion …``, ``AM:INTernal:FREQuency …``, ``AM:DEPTh …``, ``AM:SOURce …``.
        """
        shape = ModulatingShape(shape)
        source = ModulationSource(source)
        self._write(f"AM:INTernal:FUNCtion {shape.value}")
        self._write(f"AM:INTernal:FREQuency {float(frequency)}")
        self._write(f"AM:DEPTh {float(depth_percent)}")
        self._write(f"AM:SOURce {source.value}")

    def enable_amplitude_modulation(self) -> None:
        """Enable amplitude modulation.

        Sends ``AM:STATe ON``.
        """
        self._write("AM:STATe ON")

    def disable_amplitude_modulation(self) -> None:
        """Disable amplitude modulation.

        Sends ``AM:STATe OFF``.
        """
        self._write("AM:STATe OFF")

    def configure_frequency_modulation(
        self, shape: ModulatingShape | str, frequency: float, deviation_hz: float,
        source: ModulationSource | str = ModulationSource.INTERNAL,
    ) -> None:
        """Configure frequency modulation.

        Sends ``FM:INTernal:FUNCtion …``, ``FM:INTernal:FREQuency …``, ``FM:DEViation …``, ``FM:SOURce …``.
        """
        shape = ModulatingShape(shape)
        source = ModulationSource(source)
        self._write(f"FM:INTernal:FUNCtion {shape.value}")
        self._write(f"FM:INTernal:FREQuency {float(frequency)}")
        self._write(f"FM:DEViation {float(deviation_hz)}")
        self._write(f"FM:SOURce {source.value}")

    def enable_frequency_modulation(self) -> None:
        """Enable frequency modulation.

        Sends ``FM:STATe ON``.
        """
        self._write("FM:STATe ON")

    def disable_frequency_modulation(self) -> None:
        """Disable frequency modulation.

        Sends ``FM:STATe OFF``.
        """
        self._write("FM:STATe OFF")

    def configure_phase_modulation(
        self, shape: ModulatingShape | str, frequency: float, deviation_degrees: float,
        source: ModulationSource | str = ModulationSource.INTERNAL,
    ) -> None:
        """Configure phase modulation.

        Sends ``PM:INTernal:FUNCtion …``, ``PM:INTernal:FREQuency …``, ``PM:DEViation …``, ``PM:SOURce …``.
        """
        shape = ModulatingShape(shape)
        source = ModulationSource(source)
        self._write(f"PM:INTernal:FUNCtion {shape.value}")
        self._write(f"PM:INTernal:FREQuency {float(frequency)}")
        self._write(f"PM:DEViation {float(deviation_degrees)}")
        self._write(f"PM:SOURce {source.value}")

    def enable_phase_modulation(self) -> None:
        """Enable phase modulation.

        Sends ``PM:STATe ON``.
        """
        self._write("PM:STATe ON")

    def disable_phase_modulation(self) -> None:
        """Disable phase modulation.

        Sends ``PM:STATe OFF``.
        """
        self._write("PM:STATe OFF")

    def configure_frequency_shift_keying(
        self, hop_frequency: float, rate_hz: float,
        source: ModulationSource | str = ModulationSource.INTERNAL,
    ) -> None:
        """Configure frequency shift keying.

        Sends ``FSKey:FREQuency …``, ``FSKey:INTernal:RATE …``, ``FSKey:SOURce …``.
        """
        source = ModulationSource(source)
        self._write(f"FSKey:FREQuency {float(hop_frequency)}")
        self._write(f"FSKey:INTernal:RATE {float(rate_hz)}")
        self._write(f"FSKey:SOURce {source.value}")

    def enable_frequency_shift_keying(self) -> None:
        """Enable frequency shift keying.

        Sends ``FSKey:STATe ON``.
        """
        self._write("FSKey:STATe ON")

    def disable_frequency_shift_keying(self) -> None:
        """Disable frequency shift keying.

        Sends ``FSKey:STATe OFF``.
        """
        self._write("FSKey:STATe OFF")

    def configure_pulse_width_modulation(
        self, shape: ModulatingShape | str, frequency: float, deviation_seconds: float,
        source: ModulationSource | str = ModulationSource.INTERNAL,
    ) -> None:
        """Configure pulse width modulation.

        Sends ``PWM:INTernal:FUNCtion …``, ``PWM:INTernal:FREQuency …``, ``PWM:DEViation …``, ``PWM:SOURce …``.
        """
        shape = ModulatingShape(shape)
        source = ModulationSource(source)
        self._write(f"PWM:INTernal:FUNCtion {shape.value}")
        self._write(f"PWM:INTernal:FREQuency {float(frequency)}")
        self._write(f"PWM:DEViation {float(deviation_seconds)}")
        self._write(f"PWM:SOURce {source.value}")

    def enable_pulse_width_modulation(self) -> None:
        """Enable pulse width modulation.

        Sends ``PWM:STATe ON``.
        """
        self._write("PWM:STATe ON")

    def disable_pulse_width_modulation(self) -> None:
        """Disable pulse width modulation.

        Sends ``PWM:STATe OFF``.
        """
        self._write("PWM:STATe OFF")

    # ------------------------------------------------------------------
    # Sweep (task §9)
    # ------------------------------------------------------------------
    def configure_frequency_sweep(
        self, start: float, stop: float, spacing: SweepSpacing | str = SweepSpacing.LINEAR,
        time_s: float = 1.0,
    ) -> None:
        """Configure frequency sweep.

        Sends ``FREQuency:STARt …``, ``FREQuency:STOP …``, ``SWEep:SPACing …``, ``SWEep:TIME …``.
        """
        spacing = SweepSpacing(spacing)
        self._write(f"FREQuency:STARt {float(start)}")
        self._write(f"FREQuency:STOP {float(stop)}")
        self._write(f"SWEep:SPACing {spacing.value}")
        self._write(f"SWEep:TIME {float(time_s)}")

    def enable_sweep(self) -> None:
        """Enable sweep.

        Sends ``SWEep:STATe ON``.
        """
        self._write("SWEep:STATe ON")

    def disable_sweep(self) -> None:
        """Disable sweep.

        Sends ``SWEep:STATe OFF``.
        """
        self._write("SWEep:STATe OFF")

    def set_sweep_marker_frequency(self, frequency: float) -> None:
        """Set the sweep marker frequency.

        Sends ``MARKer:FREQuency …``.
        """
        self._write(f"MARKer:FREQuency {float(frequency)}")

    def get_sweep_marker_frequency(self) -> float:
        """Return the sweep marker frequency.

        Sends ``MARKer:FREQuency?``.
        """
        return float(self._query("MARKer:FREQuency?"))

    def enable_sweep_marker(self) -> None:
        """Enable sweep marker.

        Sends ``MARKer ON``.
        """
        self._write("MARKer ON")

    def disable_sweep_marker(self) -> None:
        """Disable sweep marker.

        Sends ``MARKer OFF``.
        """
        self._write("MARKer OFF")

    # ------------------------------------------------------------------
    # Burst (task §9)
    # ------------------------------------------------------------------
    def configure_burst(
        self, mode: BurstMode | str, cycles: float, period: float | None = None,
        phase_degrees: float = 0.0,
    ) -> None:
        """Configure burst.

        Sends ``BURSt:MODE …``, ``BURSt:NCYCles …``, ``BURSt:PHASe …``, ``BURSt:INTernal:PERiod …``.
        """
        mode = BurstMode(mode)
        self._write(f"BURSt:MODE {mode.value}")
        self._write(f"BURSt:NCYCles {cycles}")
        if period is not None:
            self._write(f"BURSt:INTernal:PERiod {float(period)}")
        self._write(f"BURSt:PHASe {float(phase_degrees)}")

    def enable_burst(self) -> None:
        """Enable burst.

        Sends ``BURSt:STATe ON``.
        """
        self._write("BURSt:STATe ON")

    def disable_burst(self) -> None:
        """Disable burst.

        Sends ``BURSt:STATe OFF``.
        """
        self._write("BURSt:STATe OFF")

    def set_burst_gate_polarity(self, polarity: GatePolarity | str) -> None:
        """Set the burst gate polarity.

        Sends ``BURSt:GATE:POLarity …``.
        """
        polarity = GatePolarity(polarity)
        self._write(f"BURSt:GATE:POLarity {polarity.value}")

    # ------------------------------------------------------------------
    # Trigger (task §9)
    # ------------------------------------------------------------------
    def set_trigger_source(self, source: TriggerSource | str) -> None:
        """Set the trigger source.

        Sends ``TRIGger:SOURce …``.
        """
        source = TriggerSource(source)
        self._write(f"TRIGger:SOURce {source.value}")

    def get_trigger_source(self) -> TriggerSource:
        """Return the trigger source.

        Sends ``TRIGger:SOURce?``.
        """
        return TriggerSource(self._query("TRIGger:SOURce?").strip())

    def set_trigger_slope(self, slope: TriggerSlope | str) -> None:
        """Set the trigger slope.

        Sends ``TRIGger:SLOPe …``.
        """
        slope = TriggerSlope(slope)
        self._write(f"TRIGger:SLOPe {slope.value}")

    def get_trigger_slope(self) -> TriggerSlope:
        """Return the trigger slope.

        Sends ``TRIGger:SLOPe?``.
        """
        return TriggerSlope(self._query("TRIGger:SLOPe?").strip())

    def get_trigger_settings(self) -> TriggerSettings:
        """Return the trigger settings."""
        return TriggerSettings(source=self.get_trigger_source().value, slope=self.get_trigger_slope().value)

    def trigger_now(self) -> None:
        """Bare TRIGger/*TRG. Only meaningful when TRIGger:SOURce is BUS."""

        if self.get_trigger_source() != TriggerSource.BUS:
            raise Agilent33220AValidationError(
                "Trigger Now requires TRIGger:SOURce to be BUS; call Set Trigger Source first"
            )
        self._write("*TRG")

    # ------------------------------------------------------------------
    # Arbitrary waveform (task §10)
    # ------------------------------------------------------------------
    def load_arbitrary_waveform(self, values: list[float]) -> None:
        """DATA VOLATILE, v1, v2, ... — always fills the VOLATILE slot (task §6 item 6).

        There is no custom name at upload time; use
        :meth:`copy_arbitrary_waveform_to_nonvolatile` to persist it under a
        chosen name.
        """

        if not values:
            raise Agilent33220AValidationError("values must not be empty")
        joined = ", ".join(str(float(v)) for v in values)
        self._write(f"DATA VOLATILE, {joined}")

    def copy_arbitrary_waveform_to_nonvolatile(self, name: str) -> None:
        """Copy the arbitrary waveform to nonvolatile.

        Sends ``DATA:COPY …``.
        """
        name = str(name).strip()
        if not name:
            raise Agilent33220AValidationError("name must not be empty")
        self._write(f"DATA:COPY {name}")
        self._check_events(f"Copy Arbitrary Waveform To Nonvolatile({name!r})")

    def select_arbitrary_waveform(self, name: str) -> None:
        """Select the arbitrary waveform.

        Sends ``FUNCtion:USER …``, ``FUNCtion USER``.
        """
        name = str(name).strip()
        self._write(f"FUNCtion:USER {name}")
        self._check_events(f"Select Arbitrary Waveform({name!r})")
        self._write("FUNCtion USER")

    def list_arbitrary_waveforms(self) -> list[str]:
        """Issue the list arbitrary waveforms command.

        Sends ``DATA:CATalog?``, ``DATA:NVOLatile:CATalog?``.
        """
        volatile = self._query("DATA:CATalog?").strip()
        nonvolatile = self._query("DATA:NVOLatile:CATalog?").strip()
        names: list[str] = []
        for raw in (volatile, nonvolatile):
            names.extend(item.strip().strip('"') for item in raw.split(",") if item.strip())
        return sorted(set(names))

    def delete_arbitrary_waveform(self, name: str) -> None:
        """Delete the arbitrary waveform.

        Sends ``DATA:DELete …``.
        """
        name = str(name).strip()
        self._write(f"DATA:DELete {name}")
        self._check_events(f"Delete Arbitrary Waveform({name!r})")

    def delete_all_arbitrary_waveforms(self) -> None:
        """Delete the all arbitrary waveforms.

        Sends ``DATA:DELete:ALL``.
        """
        self._write("DATA:DELete:ALL")

    def get_arbitrary_waveform_attributes(self, name: str) -> ArbWaveformAttributes:
        """Return the arbitrary waveform attributes."""
        name = str(name).strip()
        return ArbWaveformAttributes(
            name=name,
            average=float(self._query(f'DATA:ATTRibute:AVERage? "{name}"')),
            crest_factor=float(self._query(f'DATA:ATTRibute:CFACtor? "{name}"')),
            points=int(float(self._query(f'DATA:ATTRibute:POINts? "{name}"'))),
            peak_to_peak=float(self._query(f'DATA:ATTRibute:PTPeak? "{name}"')),
        )

    # ------------------------------------------------------------------
    # Setup save/restore (task §11)
    # ------------------------------------------------------------------
    def save_setup(self, host_path: str | Path) -> None:
        """Primary implementation: *LRN? written verbatim to a host file."""

        setup_string = self._query("*LRN?")
        host_path = Path(host_path)
        host_path.parent.mkdir(parents=True, exist_ok=True)
        host_path.write_text(setup_string, encoding="ascii")

    def restore_setup(self, host_path: str | Path) -> None:
        """Resend a *LRN?-captured setup string, then verify via the error queue."""

        host_path = Path(host_path)
        if not host_path.is_file():
            raise Agilent33220AValidationError(f"setup file not found: {host_path}")
        setup_string = host_path.read_text(encoding="ascii").strip()
        if not setup_string:
            raise Agilent33220AValidationError(f"setup file is empty: {host_path}")
        self._write(setup_string)
        self._check_events("Restore Setup")

    def save_setup_to_instrument_memory(self, slot: int) -> None:
        """Save the setup to instrument memory.

        Sends ``*SAV …``.
        """
        slot = int(slot)
        if not (0 <= slot <= 4):
            raise Agilent33220AValidationError("slot must be between 0 and 4")
        self._write(f"*SAV {slot}")

    def restore_setup_from_instrument_memory(self, slot: int) -> None:
        """Checks MEMory:STATe:VALid? first (task §11) — never blindly recalls an empty slot."""

        slot = int(slot)
        if not (0 <= slot <= 4):
            raise Agilent33220AValidationError("slot must be between 0 and 4")
        valid = self._query(f"MEMory:STATe:VALid? {slot}").strip()
        if valid not in ("1", "ON"):
            raise Agilent33220AValidationError(f"memory slot {slot} has never been saved to")
        self._write(f"*RCL {slot}")
        self._check_events(f"Restore Setup From Instrument Memory({slot})")

    def restore_factory_setup(self) -> None:
        """Issue the restore factory setup command.

        Sends ``*RST``.
        """
        self._write("*RST")

    # ------------------------------------------------------------------
    # Calibration (Gate 3)
    # ------------------------------------------------------------------
    def enable_calibration_mode(self, confirmation: str) -> None:
        """Two-tier safety guard, distinct from the raw-SCPI guard.

        A wrong calibration value can genuinely miscalibrate a real
        instrument, so calibration-affecting methods require this *separate*
        confirmation phrase — deliberately different text from
        ``_RAW_SCPI_CONFIRMATION`` so a caller can't accidentally satisfy one
        guard while meaning the other.
        """

        if confirmation != _CALIBRATION_CONFIRMATION:
            raise Agilent33220AValidationError(
                f'calibration requires the exact confirmation text "{_CALIBRATION_CONFIRMATION}"'
            )
        self._calibration_enabled = True

    def _require_calibration_enabled(self) -> None:
        if not self._calibration_enabled:
            raise Agilent33220AValidationError(
                "calibration is disabled; call enable_calibration_mode() with the exact "
                "confirmation text first"
            )

    def run_calibration(self) -> bool:
        """CAL? — performs a full self-calibration; returns True on pass, False on fail.

        Gated: unlike ``is_calibration_locked``, this command actually
        performs the calibration (using the value set via
        ``set_calibration_value``), so it requires the calibration guard.
        """

        self._require_calibration_enabled()
        response = self._query("CAL?").strip()
        self._check_events("Run Calibration")
        return response == "0"

    def unlock_calibration(self, security_code: str) -> None:
        """CAL:SECure:STATe OFF,<code> — unsecures the instrument for calibration."""

        self._require_calibration_enabled()
        self._write(f"CAL:SECure:STATe OFF,{security_code}")
        self._check_events("Unlock Calibration")

    def lock_calibration(self) -> None:
        """CAL:SECure:STATe ON — re-secures the instrument. No code is needed to lock."""

        self._require_calibration_enabled()
        self._write("CAL:SECure:STATe ON")
        self._check_events("Lock Calibration")

    def is_calibration_locked(self) -> bool:
        """CAL:SECure:STATe? — a read-only query; harmless, so no guard is required."""

        return self._query("CAL:SECure:STATe?").strip() in ("1", "ON")

    def set_calibration_security_code(self, new_code: str) -> None:
        """CAL:SECure:CODE <new_code>.

        Validated client-side before any device I/O: up to 12 characters,
        first character a letter A-Z, remaining characters letters/digits/
        underscore (task-doc "validate before I/O" pattern).
        """

        self._require_calibration_enabled()
        code = str(new_code)
        if not (1 <= len(code) <= 12):
            raise Agilent33220AValidationError("calibration security code must be 1-12 characters")
        if not code[0].isalpha() or not code[0].isascii():
            raise Agilent33220AValidationError("calibration security code must start with a letter A-Z")
        for ch in code[1:]:
            if not ((ch.isalnum() and ch.isascii()) or ch == "_"):
                raise Agilent33220AValidationError(
                    "calibration security code characters after the first must be "
                    "letters, digits, or underscore"
                )
        self._write(f"CAL:SECure:CODE {code}")
        self._check_events("Set Calibration Security Code")

    def set_calibration_step(self, step: int) -> None:
        """CAL:SETup <n> — selects a calibration step number, 0-94."""

        self._require_calibration_enabled()
        step = int(step)
        if not (0 <= step <= 94):
            raise Agilent33220AValidationError("calibration step must be between 0 and 94")
        self._write(f"CAL:SETup {step}")
        self._check_events("Set Calibration Step")

    def get_calibration_step(self) -> int:
        """Return the calibration step.

        Sends ``CAL:SETup?``.
        """
        return int(float(self._query("CAL:SETup?")))

    def set_calibration_value(self, value: float) -> None:
        """CAL:VALue <v> — the known calibration signal value for the current step."""

        self._require_calibration_enabled()
        self._write(f"CAL:VALue {float(value)}")
        self._check_events("Set Calibration Value")

    def get_calibration_value(self) -> float:
        """Return the calibration value.

        Sends ``CAL:VALue?``.
        """
        return float(self._query("CAL:VALue?"))

    def get_calibration_count(self) -> int:
        """CAL:COUNt? — read-only; no guard needed."""

        return int(float(self._query("CAL:COUNt?")))

    def set_calibration_string(self, text: str) -> None:
        """CAL:STRing "<text>" — a message stored in non-volatile calibration memory, up to 40 chars."""

        self._require_calibration_enabled()
        text = str(text)
        if len(text) > 40:
            raise Agilent33220AValidationError("calibration string must be 40 characters or fewer")
        self._write(f'CAL:STRing "{text}"')
        self._check_events("Set Calibration String")

    def get_calibration_string(self) -> str:
        """Return the calibration string.

        Sends ``CAL:STRing?``.
        """
        return self._query("CAL:STRing?").strip().strip('"')

    # ------------------------------------------------------------------
    # GPIB/LAN interface configuration (Gate 3)
    # ------------------------------------------------------------------
    def set_gpib_address(self, address: int) -> None:
        """Set the gpib address.

        Sends ``SYSTem:COMMunicate:GPIB:ADDRess …``.
        """
        self._write(f"SYSTem:COMMunicate:GPIB:ADDRess {int(address)}")

    def get_gpib_address(self) -> int:
        """Return the gpib address.

        Sends ``SYSTem:COMMunicate:GPIB:ADDRess?``.
        """
        return int(float(self._query("SYSTem:COMMunicate:GPIB:ADDRess?")))

    def set_lan_auto_ip(self, enabled: bool) -> None:
        """Set the lan auto ip.

        Sends ``SYSTem:COMMunicate:LAN:AUTOip …``.
        """
        self._write(f"SYSTem:COMMunicate:LAN:AUTOip {'ON' if enabled else 'OFF'}")

    def get_lan_auto_ip(self) -> bool:
        """Return the lan auto ip.

        Sends ``SYSTem:COMMunicate:LAN:AUTOip?``.
        """
        return self._query("SYSTem:COMMunicate:LAN:AUTOip?").strip() in ("1", "ON")

    def set_lan_ip_address(self, address: str) -> None:
        """Set the lan ip address.

        Sends ``SYSTem:COMMunicate:LAN:IPADdress …``.
        """
        self._write(f"SYSTem:COMMunicate:LAN:IPADdress {address}")

    def get_lan_ip_address(self) -> str:
        """Return the lan ip address.

        Sends ``SYSTem:COMMunicate:LAN:IPADdress?``.
        """
        return self._query("SYSTem:COMMunicate:LAN:IPADdress?").strip()

    def get_lan_logical_ip_address(self) -> str:
        """SYSTem:COMMunicate:LAN:LIPaddress? — read-only, the instrument's actual current IP."""

        return self._query("SYSTem:COMMunicate:LAN:LIPaddress?").strip()

    def get_lan_mac_address(self) -> str:
        """SYSTem:COMMunicate:LAN:MAC? — read-only."""

        return self._query("SYSTem:COMMunicate:LAN:MAC?").strip()

    def set_lan_media_sense_enabled(self, enabled: bool) -> None:
        """SYSTem:COMMunicate:LAN:MEDiasense.

        Despite the mnemonic's resemblance to "mDNS", the User's Guide
        describes this as link-loss detection: when enabled, the instrument
        detects a loss of LAN connectivity lasting more than 20 seconds and
        automatically restarts the LAN interface once connectivity returns.
        It is unrelated to multicast DNS/service discovery.
        """

        self._write(f"SYSTem:COMMunicate:LAN:MEDiasense {'ON' if enabled else 'OFF'}")

    def get_lan_media_sense_enabled(self) -> bool:
        """Return the lan media sense enabled.

        Sends ``SYSTem:COMMunicate:LAN:MEDiasense?``.
        """
        return self._query("SYSTem:COMMunicate:LAN:MEDiasense?").strip() in ("1", "ON")

    def set_lan_netbios_enabled(self, enabled: bool) -> None:
        """Set the lan netbios enabled.

        Sends ``SYSTem:COMMunicate:LAN:NETBios …``.
        """
        self._write(f"SYSTem:COMMunicate:LAN:NETBios {'ON' if enabled else 'OFF'}")

    def get_lan_netbios_enabled(self) -> bool:
        """Return the lan netbios enabled.

        Sends ``SYSTem:COMMunicate:LAN:NETBios?``.
        """
        return self._query("SYSTem:COMMunicate:LAN:NETBios?").strip() in ("1", "ON")

    def set_lan_telnet_prompt(self, text: str) -> None:
        """Set the lan telnet prompt."""
        self._write(f'SYSTem:COMMunicate:LAN:TELNet:PROMpt "{text}"')

    def get_lan_telnet_prompt(self) -> str:
        """Return the lan telnet prompt.

        Sends ``SYSTem:COMMunicate:LAN:TELNet:PROMpt?``.
        """
        return self._query("SYSTem:COMMunicate:LAN:TELNet:PROMpt?").strip().strip('"')

    def set_lan_telnet_welcome_message(self, text: str) -> None:
        """Set the lan telnet welcome message."""
        self._write(f'SYSTem:COMMunicate:LAN:TELNet:WMESsage "{text}"')

    def get_lan_telnet_welcome_message(self) -> str:
        """Return the lan telnet welcome message.

        Sends ``SYSTem:COMMunicate:LAN:TELNet:WMESsage?``.
        """
        return self._query("SYSTem:COMMunicate:LAN:TELNet:WMESsage?").strip().strip('"')

    # ------------------------------------------------------------------
    # Raw SCPI escape hatch (task §12)
    # ------------------------------------------------------------------
    def enable_raw_scpi(self, confirmation: str) -> None:
        """Enable raw scpi."""
        if confirmation != _RAW_SCPI_CONFIRMATION:
            raise Agilent33220AValidationError(
                f'raw SCPI requires the exact confirmation text "{_RAW_SCPI_CONFIRMATION}"'
            )
        self._raw_scpi_enabled = True

    def _require_raw_scpi_enabled(self) -> None:
        if not self._raw_scpi_enabled:
            raise Agilent33220AValidationError(
                "raw SCPI is disabled; call enable_raw_scpi() with the exact confirmation text first"
            )

    def raw_query(self, command: str) -> str:
        """Send a raw SCPI query, bypassing the typed API."""
        self._require_raw_scpi_enabled()
        return self._query(command)

    def raw_write(self, command: str) -> None:
        """Send a raw SCPI command, bypassing the typed API."""
        self._require_raw_scpi_enabled()
        self._write(command)
