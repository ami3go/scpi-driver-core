"""Typed core driver for the Agilent (Keysight) 34411A 6.5-digit digital multimeter.

Owns SCPI command construction and response parsing. The Robot Framework
adapter (``rf_agilent34411a/library.py``) is a thin layer on top of this
module and must not duplicate any of this logic (task §5.2). RFDS-008
evidence/logging also lives only in the RF adapter layer (via
``rf_agilent34411a/evidence.py``'s ``InstrumentedTransport``, which wraps
``self.transport`` from the outside) — this module has no evidence-related
code of its own, by design.
"""

from __future__ import annotations

import logging

from .enums import (
    AcFilter,
    AutoZeroMode,
    Function,
    MathFunction,
    SampleSource,
    TemperatureProbeType,
    TemperatureUnit,
    ThermistorType,
    TriggerSlope,
    TriggerSource,
)
from scpi_driver_core.exceptions import IdentityError
from scpi_driver_core.scpi import parse_csv, parse_float, parse_identity

from .exceptions import (
    Agilent34411AConfigurationError,
    Agilent34411AConnectionError,
    Agilent34411ADeviceError,
    Agilent34411AOverloadError,
    Agilent34411AValidationError,
)
from .models import InstrumentIdentity, MeasurementSettings, StatisticsResult, TriggerSettings
from .simulator import SimAgilent34411AInstrument
from .transport import PyvisaTransport, SimulatedTransport, Transport

logger = logging.getLogger(__name__)

_RAW_SCPI_CONFIRMATION = "ENABLE RAW SCPI"
_CALIBRATION_CONFIRMATION = "ENABLE CALIBRATION"
_NATIVE_LANGUAGE = "34411A"
_OVERLOAD_THRESHOLD = 9.8e37
_LAN_SELECTORS = {"CURRENT", "STATIC"}

# SCPI configuration-subsystem prefix for each measurement function (task §2).
_FUNCTION_PREFIX = {
    Function.DC_VOLTAGE: "VOLTage",
    Function.AC_VOLTAGE: "VOLTage:AC",
    Function.DC_CURRENT: "CURRent",
    Function.AC_CURRENT: "CURRent:AC",
    Function.RESISTANCE_2W: "RESistance",
    Function.RESISTANCE_4W: "FRESistance",
    Function.FREQUENCY: "FREQuency",
    Function.PERIOD: "PERiod",
    Function.CAPACITANCE: "CAPacitance",
    Function.TEMPERATURE: "TEMPerature",
}

_NPLC_FUNCTIONS = {
    Function.DC_VOLTAGE, Function.DC_CURRENT, Function.RESISTANCE_2W,
    Function.RESISTANCE_4W, Function.TEMPERATURE,
}
_APERTURE_FUNCTIONS = _NPLC_FUNCTIONS | {Function.FREQUENCY, Function.PERIOD}
_RANGE_FUNCTIONS = {
    Function.DC_VOLTAGE, Function.AC_VOLTAGE, Function.DC_CURRENT, Function.AC_CURRENT,
    Function.RESISTANCE_2W, Function.RESISTANCE_4W, Function.CAPACITANCE,
}
_VOLTAGE_RANGE_FUNCTIONS = {Function.FREQUENCY, Function.PERIOD}
_ZERO_AUTO_FUNCTIONS = {Function.DC_VOLTAGE, Function.DC_CURRENT, Function.RESISTANCE_2W, Function.TEMPERATURE}
_OCOMP_FUNCTIONS = {Function.RESISTANCE_2W, Function.RESISTANCE_4W, Function.TEMPERATURE}
_BANDWIDTH_FUNCTIONS = {Function.AC_VOLTAGE, Function.AC_CURRENT, Function.FREQUENCY, Function.PERIOD}
_NULL_FUNCTIONS = set(_FUNCTION_PREFIX)
_TRIGGER_INTERNAL_ELIGIBLE = {
    Function.DC_VOLTAGE, Function.AC_VOLTAGE, Function.DC_CURRENT, Function.AC_CURRENT,
    Function.RESISTANCE_2W, Function.RESISTANCE_4W,
}
_DBM_REFERENCE_OHMS = {
    50, 75, 93, 110, 124, 125, 135, 150, 250, 300, 500, 600, 800, 900, 1000, 1200, 8000,
}



def _identity_fields(raw: str) -> dict[str, str]:
    """Map a parsed ``*IDN?`` reply onto this driver's identity record.

    The core does the parsing. This driver keeps its historical tolerance for
    partial replies: missing fields become empty strings rather than raising,
    which is the behaviour its tests and callers already depend on.
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
            "raw": raw.strip(),
        }
    return {
        "manufacturer": identity.manufacturer,
        "model": identity.model,
        "serial": identity.serial_number or "",
        "firmware": identity.firmware_version or "",
        "raw": raw.strip(),
    }


class Agilent34411A:
    """A connected session with one Agilent 34411A instrument."""

    def __init__(self, transport: Transport) -> None:
        self.transport = transport
        self._identity: InstrumentIdentity | None = None
        self._raw_scpi_enabled = False
        self._calibration_enabled = False

    # ------------------------------------------------------------------
    # Construction / lifecycle
    # ------------------------------------------------------------------
    @classmethod
    def connect_visa(cls, resource: str, timeout_s: float = 5.0) -> Agilent34411A:
        transport = PyvisaTransport(resource, timeout_s=timeout_s)
        transport.open()
        return cls(transport)

    @classmethod
    def connect_simulated(cls, simulator: SimAgilent34411AInstrument | None = None) -> Agilent34411A:
        transport = SimulatedTransport(simulator)
        transport.open()
        return cls(transport)

    def close(self) -> None:
        self.transport.close()

    @property
    def connected(self) -> bool:
        return self.transport.is_open()

    @property
    def resource(self) -> str:
        return self.transport.resource

    @property
    def timeout_s(self) -> float:
        return self.transport.timeout_s

    @timeout_s.setter
    def timeout_s(self, value: float) -> None:
        self.transport.timeout_s = value

    # ------------------------------------------------------------------
    # Low-level I/O with exception translation
    # ------------------------------------------------------------------
    def _require_connected(self) -> None:
        if not self.transport.is_open():
            raise Agilent34411AConnectionError("not connected; call connect_visa/connect_simulated first")

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
        raise Agilent34411ADeviceError(f"{context} failed: instrument reported an error: {message}")

    @staticmethod
    def _prefix(function: Function | str) -> str:
        function = Function(function)
        try:
            return _FUNCTION_PREFIX[function]
        except KeyError as exc:
            raise Agilent34411AValidationError(
                f"function {function.value!r} has no configuration subsystem"
            ) from exc

    # ------------------------------------------------------------------
    # Identity / communication (RFDS-002)
    # ------------------------------------------------------------------
    def identify(self, *, refresh: bool = True) -> InstrumentIdentity:
        if not refresh and self._identity is not None:
            return self._identity
        raw = self._query("*IDN?")
        identity = InstrumentIdentity(**_identity_fields(raw))
        self._identity = identity
        return identity

    def check_communication(self) -> bool:
        self._query("*IDN?")
        language = self._query("SYSTem:LANguage?").strip().strip('"')
        if language != _NATIVE_LANGUAGE:
            raise Agilent34411AConfigurationError(
                f"instrument is in {language!r} SCPI-language emulation mode, not native "
                f"{_NATIVE_LANGUAGE!r}; most of this driver's command surface assumes native "
                f"language mode (task §6 item 7). Send SYSTem:LANguage \"{_NATIVE_LANGUAGE}\" "
                f"from the front panel or via Raw SCPI Write before connecting."
            )
        return True

    # ------------------------------------------------------------------
    # Function selection (task §8)
    # ------------------------------------------------------------------
    def set_function(self, function: Function | str) -> None:
        function = Function(function)
        self._write(f'FUNCtion "{function.value}"')

    def get_function(self) -> Function:
        return Function(self._query("FUNCtion?").strip().strip('"'))

    # ------------------------------------------------------------------
    # Per-function measurement configuration (task §8)
    # ------------------------------------------------------------------
    def set_range(self, function: Function | str, range_value: float) -> None:
        function = Function(function)
        if function in _RANGE_FUNCTIONS:
            self._write(f"{self._prefix(function)}:RANGe {float(range_value)}")
        elif function in _VOLTAGE_RANGE_FUNCTIONS:
            self._write(f"{self._prefix(function)}:VOLTage:RANGe {float(range_value)}")
        else:
            raise Agilent34411AValidationError(f"{function.value} has no range setting")

    def get_range(self, function: Function | str) -> float:
        function = Function(function)
        if function in _RANGE_FUNCTIONS:
            return float(self._query(f"{self._prefix(function)}:RANGe?"))
        if function in _VOLTAGE_RANGE_FUNCTIONS:
            return float(self._query(f"{self._prefix(function)}:VOLTage:RANGe?"))
        raise Agilent34411AValidationError(f"{function.value} has no range setting")

    def set_auto_range(self, function: Function | str, enabled: bool = True) -> None:
        function = Function(function)
        token = "ON" if enabled else "OFF"
        if function in _RANGE_FUNCTIONS:
            self._write(f"{self._prefix(function)}:RANGe:AUTO {token}")
        elif function in _VOLTAGE_RANGE_FUNCTIONS:
            self._write(f"{self._prefix(function)}:VOLTage:RANGe:AUTO {token}")
        else:
            raise Agilent34411AValidationError(f"{function.value} has no range setting")

    def get_auto_range(self, function: Function | str) -> bool:
        function = Function(function)
        if function in _RANGE_FUNCTIONS:
            return self._query(f"{self._prefix(function)}:RANGe:AUTO?").strip() in ("1", "ON")
        if function in _VOLTAGE_RANGE_FUNCTIONS:
            return self._query(f"{self._prefix(function)}:VOLTage:RANGe:AUTO?").strip() in ("1", "ON")
        raise Agilent34411AValidationError(f"{function.value} has no range setting")

    def set_integration_time_nplc(self, function: Function | str, nplc: float) -> None:
        function = Function(function)
        if function not in _NPLC_FUNCTIONS:
            raise Agilent34411AValidationError(f"{function.value} has no NPLC integration setting")
        self._write(f"{self._prefix(function)}:NPLC {float(nplc)}")

    def get_integration_time_nplc(self, function: Function | str) -> float:
        function = Function(function)
        if function not in _NPLC_FUNCTIONS:
            raise Agilent34411AValidationError(f"{function.value} has no NPLC integration setting")
        return float(self._query(f"{self._prefix(function)}:NPLC?"))

    def set_integration_time_aperture(self, function: Function | str, seconds: float) -> None:
        function = Function(function)
        if function not in _APERTURE_FUNCTIONS:
            raise Agilent34411AValidationError(f"{function.value} has no aperture integration setting")
        self._write(f"{self._prefix(function)}:APERture {float(seconds)}")

    def get_integration_time_aperture(self, function: Function | str) -> float:
        function = Function(function)
        if function not in _APERTURE_FUNCTIONS:
            raise Agilent34411AValidationError(f"{function.value} has no aperture integration setting")
        return float(self._query(f"{self._prefix(function)}:APERture?"))

    def set_auto_zero(self, function: Function | str, mode: AutoZeroMode | str) -> None:
        function = Function(function)
        if function == Function.RESISTANCE_4W:
            raise Agilent34411AValidationError(
                "4-wire resistance is always auto-zero on; there is no ZERO:AUTO command for "
                "FRESistance (task §8)"
            )
        if function not in _ZERO_AUTO_FUNCTIONS:
            raise Agilent34411AValidationError(f"{function.value} has no auto-zero setting")
        mode = AutoZeroMode(mode)
        self._write(f"{self._prefix(function)}:ZERO:AUTO {mode.value}")

    def get_auto_zero(self, function: Function | str) -> AutoZeroMode:
        function = Function(function)
        if function not in _ZERO_AUTO_FUNCTIONS:
            raise Agilent34411AValidationError(f"{function.value} has no auto-zero setting")
        raw = self._query(f"{self._prefix(function)}:ZERO:AUTO?").strip()
        return AutoZeroMode("ON" if raw in ("1", "ON") else "OFF")

    def set_offset_compensation(self, function: Function | str, enabled: bool) -> None:
        function = Function(function)
        if function not in _OCOMP_FUNCTIONS:
            raise Agilent34411AValidationError(f"{function.value} has no offset compensation setting")
        self._write(f"{self._prefix(function)}:OCOMpensated {'ON' if enabled else 'OFF'}")

    def get_offset_compensation(self, function: Function | str) -> bool:
        function = Function(function)
        if function not in _OCOMP_FUNCTIONS:
            raise Agilent34411AValidationError(f"{function.value} has no offset compensation setting")
        return self._query(f"{self._prefix(function)}:OCOMpensated?").strip() in ("1", "ON")

    def set_ac_filter_bandwidth(self, function: Function | str, filter_: AcFilter | str) -> None:
        function = Function(function)
        if function not in _BANDWIDTH_FUNCTIONS:
            raise Agilent34411AValidationError(f"{function.value} has no ac filter bandwidth setting")
        filter_ = AcFilter(filter_)
        prefix = "VOLTage:AC" if function in (Function.FREQUENCY, Function.PERIOD) else self._prefix(function)
        self._write(f"{prefix}:BANDwidth {filter_.value}")

    def get_ac_filter_bandwidth(self, function: Function | str) -> AcFilter:
        function = Function(function)
        if function not in _BANDWIDTH_FUNCTIONS:
            raise Agilent34411AValidationError(f"{function.value} has no ac filter bandwidth setting")
        prefix = "VOLTage:AC" if function in (Function.FREQUENCY, Function.PERIOD) else self._prefix(function)
        return AcFilter(self._query(f"{prefix}:BANDwidth?").strip())

    def set_input_impedance_auto(self, enabled: bool) -> None:
        """DC voltage only — Hi-Z (>10 GOhm) vs fixed 10 MOhm on the three lowest ranges."""

        self._write(f"VOLTage:IMPedance:AUTO {'ON' if enabled else 'OFF'}")

    def get_input_impedance_auto(self) -> bool:
        return self._query("VOLTage:IMPedance:AUTO?").strip() in ("1", "ON")

    def set_null(self, function: Function | str, enabled: bool) -> None:
        function = Function(function)
        if function not in _NULL_FUNCTIONS:
            raise Agilent34411AValidationError(f"{function.value} has no null setting")
        self._write(f"{self._prefix(function)}:NULL {'ON' if enabled else 'OFF'}")

    def get_null(self, function: Function | str) -> bool:
        function = Function(function)
        if function not in _NULL_FUNCTIONS:
            raise Agilent34411AValidationError(f"{function.value} has no null setting")
        return self._query(f"{self._prefix(function)}:NULL?").strip() in ("1", "ON")

    def set_null_value(self, function: Function | str, value: float) -> None:
        function = Function(function)
        if function not in _NULL_FUNCTIONS:
            raise Agilent34411AValidationError(f"{function.value} has no null setting")
        self._write(f"{self._prefix(function)}:NULL:VALue {float(value)}")

    def get_null_value(self, function: Function | str) -> float:
        function = Function(function)
        if function not in _NULL_FUNCTIONS:
            raise Agilent34411AValidationError(f"{function.value} has no null setting")
        return float(self._query(f"{self._prefix(function)}:NULL:VALue?"))

    def get_measurement_settings(self, function: Function | str | None = None) -> MeasurementSettings:
        function = Function(function) if function is not None else self.get_function()
        range_value = self.get_range(function) if function in (_RANGE_FUNCTIONS | _VOLTAGE_RANGE_FUNCTIONS) else None
        auto_range = self.get_auto_range(function) if function in (_RANGE_FUNCTIONS | _VOLTAGE_RANGE_FUNCTIONS) else None
        nplc = self.get_integration_time_nplc(function) if function in _NPLC_FUNCTIONS else None
        aperture_s = self.get_integration_time_aperture(function) if function in _APERTURE_FUNCTIONS else None
        auto_zero = self.get_auto_zero(function).value if function in _ZERO_AUTO_FUNCTIONS else None
        offset_compensation = self.get_offset_compensation(function) if function in _OCOMP_FUNCTIONS else None
        ac_filter_bandwidth_hz = (
            float(self.get_ac_filter_bandwidth(function).value) if function in _BANDWIDTH_FUNCTIONS else None
        )
        input_impedance_auto = self.get_input_impedance_auto() if function == Function.DC_VOLTAGE else None
        null_enabled = self.get_null(function) if function in _NULL_FUNCTIONS else False
        null_value = self.get_null_value(function) if function in _NULL_FUNCTIONS else 0.0
        return MeasurementSettings(
            function=function.value,
            range_value=range_value,
            auto_range=auto_range,
            nplc=nplc,
            aperture_s=aperture_s,
            auto_zero=auto_zero,
            offset_compensation=offset_compensation,
            ac_filter_bandwidth_hz=ac_filter_bandwidth_hz,
            input_impedance_auto=input_impedance_auto,
            null_enabled=null_enabled,
            null_value=null_value,
        )

    # ------------------------------------------------------------------
    # Temperature (task §8)
    # ------------------------------------------------------------------
    def set_temperature_probe_type(
        self, probe_type: TemperatureProbeType | str, thermistor_type: ThermistorType | str | None = None,
    ) -> None:
        probe_type = TemperatureProbeType(probe_type)
        self._write(f"TEMPerature:TRANsducer:TYPE {probe_type.value}")
        if probe_type == TemperatureProbeType.THERMISTOR and thermistor_type is not None:
            self._write(f"TEMPerature:TRANsducer:THERmistor:TYPE {ThermistorType(thermistor_type).value}")

    def get_temperature_probe_type(self) -> TemperatureProbeType:
        return TemperatureProbeType(self._query("TEMPerature:TRANsducer:TYPE?").strip())

    def set_temperature_units(self, unit: TemperatureUnit | str) -> None:
        unit = TemperatureUnit(unit)
        self._write(f"UNIT:TEMPerature {unit.value}")

    def get_temperature_units(self) -> TemperatureUnit:
        return TemperatureUnit(self._query("UNIT:TEMPerature?").strip())

    # ------------------------------------------------------------------
    # Taking readings (task §8)
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_readings(raw: str) -> list[float]:
        """Split a reading burst into floats, using the core's CSV parser."""
        return [parse_float(token) for token in parse_csv(raw) if token.strip()]

    @staticmethod
    def _check_overload(values: list[float]) -> None:
        for value in values:
            if abs(value) >= _OVERLOAD_THRESHOLD:
                raise Agilent34411AOverloadError(
                    f"reading is overloaded (out of range for the selected fixed range): {value:g}"
                )

    @staticmethod
    def _single_or_list(values: list[float]) -> float | list[float]:
        return values[0] if len(values) == 1 else values

    def get_immediate_measurement(self) -> float | list[float]:
        values = self._parse_readings(self._query("READ?"))
        self._check_overload(values)
        return self._single_or_list(values)

    def get_reading(self) -> float | list[float]:
        values = self._parse_readings(self._query("FETCh?"))
        self._check_overload(values)
        return self._single_or_list(values)

    # ------------------------------------------------------------------
    # Math (task §9)
    # ------------------------------------------------------------------
    def get_math_function(self) -> MathFunction:
        """Which math function is currently selected (mutually exclusive, task §6 item 5)."""

        return MathFunction(self._query("CALCulate:FUNCtion?").strip())

    def is_math_enabled(self) -> bool:
        return self._query("CALCulate:STATe?").strip() in ("1", "ON")

    def enable_db_measurement(self) -> None:
        self._write(f"CALCulate:FUNCtion {MathFunction.DB.value}")
        self._write("CALCulate:STATe ON")

    def set_db_reference(self, value: float) -> None:
        self._write(f"CALCulate:DB:REFerence {float(value)}")

    def enable_dbm_measurement(self) -> None:
        self._write(f"CALCulate:FUNCtion {MathFunction.DBM.value}")
        self._write("CALCulate:STATe ON")

    def set_dbm_reference_resistance(self, ohms: float) -> None:
        if int(ohms) not in _DBM_REFERENCE_OHMS:
            raise Agilent34411AValidationError(
                f"dBm reference resistance must be one of {sorted(_DBM_REFERENCE_OHMS)}, got {ohms!r}"
            )
        self._write(f"CALCulate:DBM:REFerence {float(ohms)}")

    def enable_statistics(self) -> None:
        self._write(f"CALCulate:FUNCtion {MathFunction.STATISTICS.value}")
        self._write("CALCulate:STATe ON")

    def get_statistics(self) -> StatisticsResult:
        return StatisticsResult(
            average=float(self._query("CALCulate:AVERage:AVERage?")),
            minimum=float(self._query("CALCulate:AVERage:MINimum?")),
            maximum=float(self._query("CALCulate:AVERage:MAXimum?")),
            std_deviation=float(self._query("CALCulate:AVERage:SDEViation?")),
            peak_to_peak=float(self._query("CALCulate:AVERage:PTPeak?")),
            count=int(float(self._query("CALCulate:AVERage:COUNt?"))),
        )

    def clear_statistics(self) -> None:
        self._write("CALCulate:AVERage:CLEar")

    def enable_limit_test(self) -> None:
        self._write(f"CALCulate:FUNCtion {MathFunction.LIMIT.value}")
        self._write("CALCulate:STATe ON")

    def set_limits(self, low: float, high: float) -> None:
        if not float(low) < float(high):
            raise Agilent34411AValidationError(f"low limit ({low}) must be less than high limit ({high})")
        self._write(f"CALCulate:LIMit:LOWer {float(low)}")
        self._write(f"CALCulate:LIMit:UPPer {float(high)}")

    def get_limits(self) -> tuple[float, float]:
        return (
            float(self._query("CALCulate:LIMit:LOWer?")),
            float(self._query("CALCulate:LIMit:UPPer?")),
        )

    def disable_math(self) -> None:
        self._write("CALCulate:STATe OFF")

    # ------------------------------------------------------------------
    # Trigger / sample (task §9)
    # ------------------------------------------------------------------
    def set_trigger_source(self, source: TriggerSource | str) -> None:
        source = TriggerSource(source)
        if source == TriggerSource.INTERNAL and self.get_function() not in _TRIGGER_INTERNAL_ELIGIBLE:
            raise Agilent34411AValidationError(
                "internal (level) triggering is only valid for ac/dc voltage, ac/dc current, "
                "and 2-/4-wire resistance (task §9)"
            )
        self._write(f"TRIGger:SOURce {source.value}")

    def get_trigger_source(self) -> TriggerSource:
        return TriggerSource(self._query("TRIGger:SOURce?").strip())

    def set_trigger_level(self, level: float) -> None:
        self._write(f"TRIGger:LEVel {float(level)}")

    def get_trigger_level(self) -> float:
        return float(self._query("TRIGger:LEVel?"))

    def set_trigger_slope(self, slope: TriggerSlope | str) -> None:
        slope = TriggerSlope(slope)
        self._write(f"TRIGger:SLOPe {slope.value}")

    def get_trigger_slope(self) -> TriggerSlope:
        return TriggerSlope(self._query("TRIGger:SLOPe?").strip())

    def set_trigger_count(self, count: float) -> None:
        self._write(f"TRIGger:COUNt {count}")

    def get_trigger_count(self) -> float:
        return float(self._query("TRIGger:COUNt?"))

    def set_trigger_delay(self, seconds: float) -> None:
        self._write(f"TRIGger:DELay {float(seconds)}")

    def set_trigger_delay_auto(self) -> None:
        self._write("TRIGger:DELay:AUTO ON")

    def get_trigger_settings(self) -> TriggerSettings:
        return TriggerSettings(
            source=self.get_trigger_source().value,
            level=self.get_trigger_level(),
            slope=self.get_trigger_slope().value,
            delay_s=float(self._query("TRIGger:DELay?")),
            delay_auto=self._query("TRIGger:DELay:AUTO?").strip() in ("1", "ON"),
            trigger_count=self.get_trigger_count(),
            sample_count=self.get_sample_count(),
            sample_source=self._query("SAMPle:SOURce?").strip(),
            sample_timer_s=float(self._query("SAMPle:TIMer?")),
            pretrigger_sample_count=float(self._query("SAMPle:COUNt:PRETrigger?")),
        )

    def set_sample_count(self, count: float) -> None:
        self._write(f"SAMPle:COUNt {count}")

    def get_sample_count(self) -> float:
        return float(self._query("SAMPle:COUNt?"))

    def set_sample_source(self, source: SampleSource | str) -> None:
        source = SampleSource(source)
        self._write(f"SAMPle:SOURce {source.value}")

    def set_sample_timer_interval(self, seconds: float) -> None:
        self._write(f"SAMPle:TIMer {float(seconds)}")

    def set_pretrigger_sample_count(self, count: float) -> None:
        if float(count) >= self.get_sample_count():
            raise Agilent34411AValidationError(
                "pre-trigger sample count must be less than the sample count (task §9)"
            )
        self._write(f"SAMPle:COUNt:PRETrigger {count}")

    def trigger_now(self) -> None:
        """Bare *TRG. Only meaningful when TRIGger:SOURce is BUS."""

        if self.get_trigger_source() != TriggerSource.BUS:
            raise Agilent34411AValidationError(
                "Trigger Now requires TRIGger:SOURce to be BUS; call Set Trigger Source first"
            )
        self._write("*TRG")

    # ------------------------------------------------------------------
    # Reading memory and data logging (task §10)
    # ------------------------------------------------------------------
    def get_latest_reading(self) -> float | list[float]:
        return self.get_reading()

    def get_most_recent_reading(self) -> float:
        value = float(self._query("DATA:LAST?"))
        self._check_overload([value])
        return value

    def get_reading_count(self) -> int:
        return int(float(self._query("DATA:POINts?")))

    def drain_readings(self, count: int) -> list[float]:
        return self._parse_readings(self._query(f"DATA:REMove? {int(count)}"))

    def copy_readings_to_nonvolatile_memory(self) -> None:
        self._write("DATA:COPY NVMEM, RDG_STORE")

    def get_nonvolatile_reading_count(self) -> int:
        return int(float(self._query("DATA:POINts? NVMEM")))

    def get_nonvolatile_readings(self) -> list[float]:
        return self._parse_readings(self._query("DATA:DATA? NVMEM"))

    def clear_nonvolatile_readings(self) -> None:
        self._write("DATA:DELete NVMEM")

    def drain_nonvolatile_readings(self, max_count: int | None = None) -> list[float]:
        command = f"R? {int(max_count)}" if max_count is not None else "R?"
        return self._parse_readings(self._query(command))

    # ------------------------------------------------------------------
    # Instrument memory state storage (task §11)
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_slot(slot: int) -> int:
        slot = int(slot)
        if not (0 <= slot <= 4):
            raise Agilent34411AValidationError("slot must be between 0 and 4")
        return slot

    def save_setup_to_instrument_memory(self, slot: int) -> None:
        slot = self._validate_slot(slot)
        self._write(f"*SAV {slot}")

    def restore_setup_from_instrument_memory(self, slot: int) -> None:
        """Checks MEMory:STATe:VALid? first (task §11) — never blindly recalls an empty slot."""

        slot = self._validate_slot(slot)
        if not self.is_instrument_memory_slot_valid(slot):
            raise Agilent34411AValidationError(f"memory slot {slot} has never been saved to")
        self._write(f"*RCL {slot}")
        self._check_events(f"Restore Setup From Instrument Memory({slot})")

    def get_instrument_memory_catalog(self) -> list[int]:
        raw = self._query("MEMory:STATe:CATalog?").strip()
        return [int(token) for token in raw.split(",") if token.strip()]

    def rename_instrument_memory_slot(self, slot: int, name: str) -> None:
        slot = self._validate_slot(slot)
        self._write(f'MEMory:STATe:NAME {slot},"{name}"')

    def get_instrument_memory_slot_name(self, slot: int) -> str:
        slot = self._validate_slot(slot)
        return self._query(f"MEMory:STATe:NAME? {slot}").strip().strip('"')

    def delete_instrument_memory_slot(self, slot: int) -> None:
        slot = self._validate_slot(slot)
        self._write(f"MEMory:STATe:DELete {slot}")

    def delete_all_instrument_memory_slots(self) -> None:
        self._write("MEMory:STATe:DELete:ALL")

    def is_instrument_memory_slot_valid(self, slot: int) -> bool:
        slot = self._validate_slot(slot)
        return self._query(f"MEMory:STATe:VALid? {slot}").strip() in ("1", "ON")

    def get_instrument_memory_slot_count(self) -> int:
        return int(float(self._query("MEMory:NSTates?")))

    def set_power_on_state_recall(self, enabled: bool) -> None:
        self._write(f"MEMory:STATe:RECall:AUTO {'ON' if enabled else 'OFF'}")

    def set_power_on_state(self, slot: int) -> None:
        slot = self._validate_slot(slot)
        self._write(f"MEMory:STATe:RECall:SELect {slot}")

    # ------------------------------------------------------------------
    # Front panel / system (task §6, §2)
    # ------------------------------------------------------------------
    def get_active_input_terminals(self) -> str:
        """Read-only — the front/rear switch cannot be set remotely (task §6 item 1)."""

        return self._query("ROUTe:TERMinals?").strip()

    def set_beeper_enabled(self, enabled: bool) -> None:
        self._write(f"SYSTem:BEEPer:STATe {'ON' if enabled else 'OFF'}")

    def get_beeper_enabled(self) -> bool:
        return self._query("SYSTem:BEEPer:STATe?").strip() in ("1", "ON")

    def set_display_enabled(self, enabled: bool) -> None:
        self._write(f"DISPlay {'ON' if enabled else 'OFF'}")

    def get_display_enabled(self) -> bool:
        return self._query("DISPlay?").strip() in ("1", "ON")

    def set_display_text(self, text: str) -> None:
        self._write(f'DISPlay:TEXT "{text}"')

    def clear_display_text(self) -> None:
        self._write("DISPlay:TEXT:CLEar")

    # ------------------------------------------------------------------
    # Calibration (Gate 3 — CALibration subsystem)
    #
    # Gated behind a dedicated two-tier guard, distinct from and in
    # addition to the raw-SCPI guard below: every calibration-affecting
    # method (everything except the three genuinely harmless read-only
    # queries noted below) refuses to run until enable_calibration_mode()
    # has been called with the exact confirmation text. This mirrors the
    # _raw_scpi_enabled / _require_raw_scpi_enabled pattern exactly, but
    # as an independent flag: enabling raw SCPI does not enable
    # calibration and vice versa.
    # ------------------------------------------------------------------
    def enable_calibration_mode(self, confirmation: str) -> None:
        if confirmation != _CALIBRATION_CONFIRMATION:
            raise Agilent34411AValidationError(
                f'calibration requires the exact confirmation text "{_CALIBRATION_CONFIRMATION}"'
            )
        self._calibration_enabled = True

    def _require_calibration_enabled(self) -> None:
        if not self._calibration_enabled:
            raise Agilent34411AValidationError(
                "calibration is disabled; call enable_calibration_mode() with the exact "
                "confirmation text first"
            )

    def unlock_calibration(self, security_code: str) -> None:
        self._require_calibration_enabled()
        self._write(f"CALibration:SECure:STATe OFF,{security_code}")
        self._check_events("Unlock Calibration")

    def lock_calibration(self) -> None:
        self._require_calibration_enabled()
        self._write("CALibration:SECure:STATe ON")
        self._check_events("Lock Calibration")

    def is_calibration_locked(self) -> bool:
        """Read-only — harmless to query without the calibration guard enabled."""

        return self._query("CALibration:SECure:STATe?").strip() in ("1", "ON")

    def set_calibration_security_code(self, new_code: str) -> None:
        self._require_calibration_enabled()
        self._write(f"CALibration:SECure:CODE {new_code}")
        self._check_events("Set Calibration Security Code")

    def run_full_calibration(self) -> bool:
        """CALibration[:ALL]? — sent as ``CALibration?``.

        Returns True on a pass. Judgment call: neither source document available
        during this driver's research (the Command Quick Reference or the
        34410-90001 User's Guide, which defers calibration procedure details to
        the separate Service Guide) spells out the response's numeric meaning
        for this instrument. This follows the convention documented for the
        equivalent command across the wider Agilent/Keysight multimeter family
        (e.g. 34401A CAL?): 0 = PASS, non-zero = FAIL/error code. Treat this as
        a documented judgment call, not a confirmed fact.
        """

        self._require_calibration_enabled()
        response = self._query("CALibration?").strip()
        self._check_events("Run Full Calibration")
        return float(response) == 0.0

    def run_adc_calibration(self) -> float:
        """CALibration:ADC? — returns the raw numeric response, uninterpreted.

        Judgment call: what this value represents (a calibration constant, an
        error/deviation figure, a pass/fail code, ...) is not documented in
        either source document available during this driver's research; the
        Service Guide referenced by the User's Guide for calibration procedure
        detail was not part of that research set. Rather than invent a
        confident-sounding interpretation, this method returns the bare float
        and leaves interpretation to the caller.
        """

        self._require_calibration_enabled()
        response = self._query("CALibration:ADC?").strip()
        self._check_events("Run ADC Calibration")
        return float(response)

    def set_calibration_line_frequency(self, hz: int) -> None:
        self._require_calibration_enabled()
        hz = int(hz)
        if hz not in (50, 60):
            raise Agilent34411AValidationError(
                f"calibration line frequency must be 50 or 60, got {hz!r}"
            )
        self._write(f"CALibration:LFRequency {hz}")
        self._check_events("Set Calibration Line Frequency")

    def get_calibration_line_frequency(self) -> int:
        self._require_calibration_enabled()
        return int(float(self._query("CALibration:LFRequency?")))

    def get_actual_calibration_line_frequency(self) -> float:
        """Read-only measurement readback — harmless without the calibration guard."""

        return float(self._query("CALibration:LFRequency:ACTual?"))

    def store_calibration(self) -> None:
        """Writes calibration constants to non-volatile memory. A consequential operation."""

        self._require_calibration_enabled()
        self._write("CALibration:STORe")
        self._check_events("Store Calibration")

    def get_calibration_count(self) -> int:
        """Read-only — harmless to query without the calibration guard enabled."""

        return int(float(self._query("CALibration:COUNt?")))

    def set_calibration_string(self, text: str) -> None:
        self._require_calibration_enabled()
        self._write(f'CALibration:STRing "{text}"')
        self._check_events("Set Calibration String")

    def get_calibration_string(self) -> str:
        self._require_calibration_enabled()
        return self._query("CALibration:STRing?").strip().strip('"')

    def set_calibration_value(self, value: float) -> None:
        self._require_calibration_enabled()
        self._write(f"CALibration:VALue {float(value)}")
        self._check_events("Set Calibration Value")

    def get_calibration_value(self) -> float:
        self._require_calibration_enabled()
        return float(self._query("CALibration:VALue?"))

    # ------------------------------------------------------------------
    # LAN configuration (Gate 3 — SYSTem:COMMunicate:LAN subsystem)
    #
    # Plain pass-through methods, no special guard: none of these can
    # damage the instrument or its calibration data, unlike the
    # CALibration subsystem above. The read query for ip address, subnet
    # mask, gateway, hostname, and domain accepts an optional selector
    # ("current" or "static") matching the [{CURRent|STATic}] form the
    # Quick Reference documents for exactly those five queries (not for
    # dns, which the reference shows with no selector form at all).
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_lan_selector(selector: str | None) -> str:
        if selector is None:
            return ""
        token = str(selector).strip().upper()
        if token not in _LAN_SELECTORS:
            raise Agilent34411AValidationError(
                f"selector must be one of {sorted(_LAN_SELECTORS)}, got {selector!r}"
            )
        return token

    def set_lan_dhcp_enabled(self, enabled: bool) -> None:
        self._write(f"SYSTem:COMMunicate:LAN:DHCP {'ON' if enabled else 'OFF'}")

    def get_lan_dhcp_enabled(self) -> bool:
        return self._query("SYSTem:COMMunicate:LAN:DHCP?").strip() in ("1", "ON")

    def set_lan_ip_address(self, address: str) -> None:
        self._write(f"SYSTem:COMMunicate:LAN:IPADdress {address}")

    def get_lan_ip_address(self, selector: str | None = None) -> str:
        token = self._validate_lan_selector(selector)
        command = "SYSTem:COMMunicate:LAN:IPADdress?" + (f" {token}" if token else "")
        return self._query(command).strip().strip('"')

    def set_lan_subnet_mask(self, mask: str) -> None:
        self._write(f"SYSTem:COMMunicate:LAN:SMASk {mask}")

    def get_lan_subnet_mask(self, selector: str | None = None) -> str:
        token = self._validate_lan_selector(selector)
        command = "SYSTem:COMMunicate:LAN:SMASk?" + (f" {token}" if token else "")
        return self._query(command).strip().strip('"')

    def set_lan_gateway(self, gateway: str) -> None:
        self._write(f"SYSTem:COMMunicate:LAN:GATEway {gateway}")

    def get_lan_gateway(self, selector: str | None = None) -> str:
        token = self._validate_lan_selector(selector)
        command = "SYSTem:COMMunicate:LAN:GATEway?" + (f" {token}" if token else "")
        return self._query(command).strip().strip('"')

    def set_lan_dns(self, address: str) -> None:
        self._write(f"SYSTem:COMMunicate:LAN:DNS {address}")

    def get_lan_dns(self) -> str:
        return self._query("SYSTem:COMMunicate:LAN:DNS?").strip().strip('"')

    def set_lan_hostname(self, name: str) -> None:
        self._write(f'SYSTem:COMMunicate:LAN:HOSTname "{name}"')

    def get_lan_hostname(self, selector: str | None = None) -> str:
        token = self._validate_lan_selector(selector)
        command = "SYSTem:COMMunicate:LAN:HOSTname?" + (f" {token}" if token else "")
        return self._query(command).strip().strip('"')

    def set_lan_domain(self, name: str) -> None:
        self._write(f'SYSTem:COMMunicate:LAN:DOMain "{name}"')

    def get_lan_domain(self, selector: str | None = None) -> str:
        token = self._validate_lan_selector(selector)
        command = "SYSTem:COMMunicate:LAN:DOMain?" + (f" {token}" if token else "")
        return self._query(command).strip().strip('"')

    def set_lan_auto_ip(self, enabled: bool) -> None:
        self._write(f"SYSTem:COMMunicate:LAN:AUTOip:STATe {'ON' if enabled else 'OFF'}")

    def get_lan_auto_ip(self) -> bool:
        return self._query("SYSTem:COMMunicate:LAN:AUTOip:STATe?").strip() in ("1", "ON")

    def set_lan_ddns_enabled(self, enabled: bool) -> None:
        self._write(f"SYSTem:COMMunicate:LAN:DDNS {'ON' if enabled else 'OFF'}")

    def get_lan_ddns_enabled(self) -> bool:
        return self._query("SYSTem:COMMunicate:LAN:DDNS?").strip() in ("1", "ON")

    def set_lan_keepalive(self, seconds: float) -> None:
        self._write(f"SYSTem:COMMunicate:LAN:KEEPalive {float(seconds)}")

    def get_lan_keepalive(self) -> float:
        return float(self._query("SYSTem:COMMunicate:LAN:KEEPalive?"))

    def get_lan_logical_ip_address(self) -> str:
        """Read-only."""

        return self._query("SYSTem:COMMunicate:LAN:LIPaddress?").strip().strip('"')

    def get_lan_mac_address(self) -> str:
        """Read-only."""

        return self._query("SYSTem:COMMunicate:LAN:MAC?").strip().strip('"')

    def get_lan_connection_status(self) -> str:
        """Read-only. SYSTem:COMMunicate:LAN:BSTatus?."""

        return self._query("SYSTem:COMMunicate:LAN:BSTatus?").strip().strip('"')

    def get_lan_control_connection_status(self) -> str:
        """Read-only. SYSTem:COMMunicate:LAN:CONTrol?."""

        return self._query("SYSTem:COMMunicate:LAN:CONTrol?").strip().strip('"')

    def set_lan_mdns_enabled(self, enabled: bool) -> None:
        """The MEDiasense command (mDNS)."""

        self._write(f"SYSTem:COMMunicate:LAN:MEDiasense {'ON' if enabled else 'OFF'}")

    def get_lan_mdns_enabled(self) -> bool:
        return self._query("SYSTem:COMMunicate:LAN:MEDiasense?").strip() in ("1", "ON")

    def set_lan_netbios_enabled(self, enabled: bool) -> None:
        self._write(f"SYSTem:COMMunicate:LAN:NETBios {'ON' if enabled else 'OFF'}")

    def get_lan_netbios_enabled(self) -> bool:
        return self._query("SYSTem:COMMunicate:LAN:NETBios?").strip() in ("1", "ON")

    def set_lan_telnet_prompt(self, text: str) -> None:
        self._write(f'SYSTem:COMMunicate:LAN:TELNet:PROMpt "{text}"')

    def get_lan_telnet_prompt(self) -> str:
        return self._query("SYSTem:COMMunicate:LAN:TELNet:PROMpt?").strip().strip('"')

    def set_lan_telnet_welcome_message(self, text: str) -> None:
        self._write(f'SYSTem:COMMunicate:LAN:TELNet:WMESsage "{text}"')

    def get_lan_telnet_welcome_message(self) -> str:
        return self._query("SYSTem:COMMunicate:LAN:TELNet:WMESsage?").strip().strip('"')

    def clear_lan_history(self) -> None:
        self._write("SYSTem:COMMunicate:LAN:HISTory:CLEar")

    def get_lan_history(self) -> str:
        return self._query("SYSTem:COMMunicate:LAN:HISTory?").strip().strip('"')

    # ------------------------------------------------------------------
    # Raw SCPI escape hatch (task §12)
    # ------------------------------------------------------------------
    def enable_raw_scpi(self, confirmation: str) -> None:
        if confirmation != _RAW_SCPI_CONFIRMATION:
            raise Agilent34411AValidationError(
                f'raw SCPI requires the exact confirmation text "{_RAW_SCPI_CONFIRMATION}"'
            )
        self._raw_scpi_enabled = True

    def _require_raw_scpi_enabled(self) -> None:
        if not self._raw_scpi_enabled:
            raise Agilent34411AValidationError(
                "raw SCPI is disabled; call enable_raw_scpi() with the exact confirmation text first"
            )

    def raw_query(self, command: str) -> str:
        self._require_raw_scpi_enabled()
        return self._query(command)

    def raw_write(self, command: str) -> None:
        self._require_raw_scpi_enabled()
        self._write(command)
