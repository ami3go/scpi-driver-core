"""Typed core driver for the Tektronix TBS1000C series.

Owns SCPI command construction, response parsing, and waveform scaling.
The Robot Framework adapter (``rf_tbs1000c/library.py``) is a thin layer on
top of this module and must not duplicate any of this logic (task §5.2).
"""

from __future__ import annotations

import logging
from pathlib import Path

from .codec import (
    build_ieee_block,
    decode_samples,
    parse_curve_response,
    parse_idn,
    scale_waveform,
)
from .enums import (
    AcquisitionMode,
    Coupling,
    ImageFormat,
    ImageLayout,
    MeasurementType,
    TriggerCoupling,
    TriggerSlope,
)
from .exceptions import (
    Tbs1000cCalibrationError,
    Tbs1000cConnectionError,
    Tbs1000cDeviceError,
    Tbs1000cValidationError,
)
from .models import (
    CalibrationStatus,
    ChannelSettings,
    InstrumentIdentity,
    TriggerSettings,
    Waveform,
    WaveformPreamble,
)
from .simulator import SimTbs1000cInstrument
from .transport import PyvisaUsbtmcTransport, SimulatedTransport, Transport

logger = logging.getLogger(__name__)

_OVERLOAD_THRESHOLD = 9.0e37
_MAX_LABEL_LENGTH = 30
_RAW_SCPI_CONFIRMATION = "ENABLE RAW SCPI"


def _validate_channel(channel: int) -> int:
    channel = int(channel)
    if channel not in (1, 2):
        raise Tbs1000cValidationError(f"channel must be 1 or 2, got {channel!r}")
    return channel


def _validate_ref(ref: int) -> int:
    ref = int(ref)
    if ref not in (1, 2):
        raise Tbs1000cValidationError(f"reference memory location must be 1 or 2, got {ref!r}")
    return ref


class Tbs1000c:
    """A connected session with one TBS1000C instrument."""

    def __init__(self, transport: Transport) -> None:
        self.transport = transport
        self._identity: InstrumentIdentity | None = None
        self._raw_scpi_enabled = False

    # ------------------------------------------------------------------
    # Construction / lifecycle
    # ------------------------------------------------------------------
    @classmethod
    def connect_usbtmc(cls, resource: str, timeout_s: float = 5.0) -> Tbs1000c:
        transport = PyvisaUsbtmcTransport(resource, timeout_s=timeout_s)
        transport.open()
        return cls(transport)

    @classmethod
    def connect_simulated(cls, simulator: SimTbs1000cInstrument | None = None) -> Tbs1000c:
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
            raise Tbs1000cConnectionError("not connected; call connect_usbtmc/connect_simulated first")

    def _write(self, command: str) -> None:
        self._require_connected()
        self.transport.write(command)

    def _query(self, command: str) -> str:
        self._require_connected()
        return self.transport.query(command)

    def _query_binary(self, command: str) -> bytes:
        self._require_connected()
        raw = self.transport.query_binary(command)
        return parse_curve_response(raw)

    def _check_events(self, context: str) -> None:
        """Raise if the instrument's event queue reports a problem after ``context``."""

        esr = self._query("*ESR?").strip()
        if esr in ("0", ""):
            return
        message = self._query("EVMsg?").strip()
        raise Tbs1000cDeviceError(f"{context} failed: instrument reported an event: {message}")

    # ------------------------------------------------------------------
    # Identity / communication (RFDS-002)
    # ------------------------------------------------------------------
    def identify(self, *, refresh: bool = True) -> InstrumentIdentity:
        if not refresh and self._identity is not None:
            return self._identity
        raw = self._query("*IDN?")
        identity = parse_idn(raw)
        self._identity = identity
        return identity

    def check_communication(self) -> bool:
        self._query("*IDN?")
        return True

    # ------------------------------------------------------------------
    # Channel configuration (task §8)
    # ------------------------------------------------------------------
    def set_channel_scale(self, channel: int, volts_per_div: float) -> None:
        channel = _validate_channel(channel)
        volts_per_div = float(volts_per_div)
        if volts_per_div <= 0:
            raise Tbs1000cValidationError("volts_per_div must be positive")
        self._write(f"CH{channel}:SCAle {volts_per_div}")

    def get_channel_scale(self, channel: int) -> float:
        channel = _validate_channel(channel)
        return float(self._query(f"CH{channel}:SCAle?"))

    def set_channel_position(self, channel: int, divisions: float) -> None:
        channel = _validate_channel(channel)
        self._write(f"CH{channel}:POSition {float(divisions)}")

    def get_channel_position(self, channel: int) -> float:
        channel = _validate_channel(channel)
        return float(self._query(f"CH{channel}:POSition?"))

    def set_channel_offset(self, channel: int, volts: float) -> None:
        channel = _validate_channel(channel)
        self._write(f"CH{channel}:OFFSet {float(volts)}")

    def get_channel_offset(self, channel: int) -> float:
        channel = _validate_channel(channel)
        return float(self._query(f"CH{channel}:OFFSet?"))

    def set_channel_coupling(self, channel: int, coupling: Coupling | str) -> None:
        channel = _validate_channel(channel)
        coupling = Coupling(coupling)
        self._write(f"CH{channel}:COUPling {coupling.value}")

    def get_channel_coupling(self, channel: int) -> Coupling:
        channel = _validate_channel(channel)
        return Coupling(self._query(f"CH{channel}:COUPling?").strip())

    def set_channel_bandwidth_limit(self, channel: int, value: str | float) -> None:
        """``value`` is ``"TWEnty"`` (20 MHz), ``"FULl"`` (unlimited), or a numeric frequency."""

        channel = _validate_channel(channel)
        self._write(f"CH{channel}:BANdwidth {value}")

    def get_channel_bandwidth_limit(self, channel: int) -> str:
        channel = _validate_channel(channel)
        return self._query(f"CH{channel}:BANdwidth?").strip()

    def set_channel_probe_gain(self, channel: int, gain: float) -> None:
        channel = _validate_channel(channel)
        gain = float(gain)
        if gain <= 0:
            raise Tbs1000cValidationError("probe gain must be positive")
        self._write(f"CH{channel}:PRObe:GAIN {gain}")

    def get_channel_probe_gain(self, channel: int) -> float:
        channel = _validate_channel(channel)
        return float(self._query(f"CH{channel}:PRObe:GAIN?"))

    def set_channel_name(self, channel: int, name: str | None) -> None:
        """CH<x>:LABel. Validated client-side: max 30 characters (task §8/manual)."""

        channel = _validate_channel(channel)
        text = "" if name is None else str(name)
        if len(text) > _MAX_LABEL_LENGTH:
            raise Tbs1000cValidationError(
                f"channel name must be at most {_MAX_LABEL_LENGTH} characters, got {len(text)}"
            )
        self._write(f'CH{channel}:LABel "{text}"')

    def get_channel_name(self, channel: int) -> str:
        channel = _validate_channel(channel)
        return self._query(f"CH{channel}:LABel?").strip().strip('"')

    def get_channel_settings(self, channel: int) -> ChannelSettings:
        channel = _validate_channel(channel)
        return ChannelSettings(
            channel=channel,
            scale=self.get_channel_scale(channel),
            position=self.get_channel_position(channel),
            offset=self.get_channel_offset(channel),
            coupling=self.get_channel_coupling(channel).value,
            bandwidth_limit=self.get_channel_bandwidth_limit(channel),
            probe_gain=self.get_channel_probe_gain(channel),
            label=self.get_channel_name(channel),
        )

    # ------------------------------------------------------------------
    # Trigger (task §8)
    # ------------------------------------------------------------------
    def set_trigger_source(self, channel: int) -> None:
        channel = _validate_channel(channel)
        self._write(f"TRIGger:A:EDGE:SOUrce CH{channel}")

    def get_trigger_source(self) -> str:
        return self._query("TRIGger:A:EDGE:SOUrce?").strip()

    def set_trigger_slope(self, slope: TriggerSlope | str) -> None:
        slope = TriggerSlope(slope)
        self._write(f"TRIGger:A:EDGE:SLOpe {slope.value}")

    def get_trigger_slope(self) -> TriggerSlope:
        return TriggerSlope(self._query("TRIGger:A:EDGE:SLOpe?").strip())

    def set_trigger_coupling(self, coupling: TriggerCoupling | str) -> None:
        coupling = TriggerCoupling(coupling)
        self._write(f"TRIGger:A:EDGE:COUPling {coupling.value}")

    def get_trigger_coupling(self) -> TriggerCoupling:
        return TriggerCoupling(self._query("TRIGger:A:EDGE:COUPling?").strip())

    def set_trigger_level(self, level_v: float) -> None:
        self._write(f"TRIGger:A:LEVel {float(level_v)}")

    def get_trigger_level(self) -> float:
        return float(self._query("TRIGger:A:LEVel?"))

    def auto_set_trigger_level(self) -> None:
        """TRIGger:A SETLevel — sets the level to 50% of the input signal's range."""

        self._write("TRIGger:A SETLevel")

    def force_trigger(self) -> None:
        logger.info("TBS1000C: forcing a trigger event; any in-progress acquisition ends now")
        self._write("TRIGger FORCe")

    def get_trigger_settings(self) -> TriggerSettings:
        return TriggerSettings(
            source=self.get_trigger_source(),
            slope=self.get_trigger_slope().value,
            coupling=self.get_trigger_coupling().value,
            level=self.get_trigger_level(),
        )

    # ------------------------------------------------------------------
    # Acquisition and autoset (task §6 item 1, §8)
    # ------------------------------------------------------------------
    def run_autoset(self) -> None:
        before = {
            "ch1": self.get_channel_settings(1),
            "ch2": self.get_channel_settings(2),
            "trigger": self.get_trigger_settings(),
        }
        self._write("AUTOSet")
        after = {
            "ch1": self.get_channel_settings(1),
            "ch2": self.get_channel_settings(2),
            "trigger": self.get_trigger_settings(),
        }
        logger.info("TBS1000C: AUTOSet changed configuration. before=%s after=%s", before, after)

    def start_acquisition(self) -> None:
        self._write("ACQuire:STATE RUN")

    def stop_acquisition(self) -> None:
        self._write("ACQuire:STATE STOP")

    def set_acquisition_mode(self, mode: AcquisitionMode | str) -> None:
        mode = AcquisitionMode(mode)
        self._write(f"ACQuire:MODe {mode.value}")

    def get_acquisition_mode(self) -> AcquisitionMode:
        return AcquisitionMode(self._query("ACQuire:MODe?").strip())

    def get_acquisition_count(self) -> int:
        return int(float(self._query("ACQuire:NUMACq?")))

    # ------------------------------------------------------------------
    # Calibration (task §6 item 2, §8)
    # ------------------------------------------------------------------
    def run_internal_calibration(self) -> None:
        if self.get_calibration_status().running:
            raise Tbs1000cCalibrationError("internal calibration is already running")
        self._write("CALibrate:INTERNal:STARt")
        status = self.get_calibration_status()
        if status.results and status.results.upper() != "PASS":
            raise Tbs1000cCalibrationError(f"internal calibration reported: {status.results}")

    def get_calibration_status(self) -> CalibrationStatus:
        running = self._query("CALibrate:INTERNal:STATus?").strip() not in ("0", "")
        results = self._query("CALibrate:RESults?").strip() if not running else ""
        return CalibrationStatus(running=running, results=results)

    def get_calibration_results(self) -> str:
        return self._query("CALibrate:RESults?").strip()

    # ------------------------------------------------------------------
    # Measurement (task §6 item 4, §9)
    # ------------------------------------------------------------------
    def get_immediate_measurement(self, measurement_type: MeasurementType | str, channel: int) -> float:
        channel = _validate_channel(channel)
        measurement_type = MeasurementType(measurement_type)
        self._select_waveform_source(channel)
        self._write(f"MEASUrement:IMMed:TYPe {measurement_type.value}")
        raw = self._query("MEASUrement:IMMed?").strip()
        value = float(raw)
        if abs(value) >= _OVERLOAD_THRESHOLD:
            raise Tbs1000cDeviceError(
                f"{measurement_type.value} measurement on CH{channel} is out of range/overloaded"
                " (instrument returned the overload sentinel, not a real value)"
            )
        return value

    # ------------------------------------------------------------------
    # Waveform transfer (task §9) — the primary, host-side path
    # ------------------------------------------------------------------
    def _select_waveform_source(self, channel: int) -> None:
        channel = _validate_channel(channel)
        self._write(f"DATa:SOUrce CH{channel}")

    def _read_preamble(self, channel: int) -> WaveformPreamble:
        self._select_waveform_source(channel)
        return WaveformPreamble(
            bit_nr=int(self._query("WFMOutpre:BIT_Nr?")),
            bn_fmt=self._query("WFMOutpre:BN_Fmt?").strip(),
            byt_nr=int(self._query("WFMOutpre:BYT_Nr?")),
            encdg=self._query("WFMOutpre:ENCdg?").strip(),
            nr_pt=int(float(self._query("WFMOutpre:NR_Pt?"))),
            record_length=int(float(self._query("WFMOutpre:RECOrdlength?"))),
            wfid=self._query("WFMOutpre:WFId?").strip().strip('"'),
            x_increment=float(self._query("WFMOutpre:XINcr?")),
            x_zero=float(self._query("WFMOutpre:XZEro?")),
            x_unit=self._query("WFMOutpre:XUNit?").strip().strip('"'),
            y_multiplier=float(self._query("WFMOutpre:YMUlt?")),
            y_offset=float(self._query("WFMOutpre:YOFf?")),
            y_zero=float(self._query("WFMOutpre:YZEro?")),
            y_unit=self._query("WFMOutpre:YUNit?").strip().strip('"'),
        )

    def get_waveform(self, channel: int) -> Waveform:
        """Fetch and decode one channel's waveform record.

        Always reads a fresh preamble immediately around the CURVe? transfer
        it applies to (task §5.2) — never reuses a cached preamble.
        """

        channel = _validate_channel(channel)
        preamble = self._read_preamble(channel)
        payload = self._query_binary("CURVe?")
        codes = decode_samples(payload, preamble)
        time_s, volts = scale_waveform(codes, preamble)
        return Waveform(time_s=time_s, volts=volts, preamble=preamble)

    # ------------------------------------------------------------------
    # File transfer: screen image, waveform export, setup save/restore (task §10)
    # ------------------------------------------------------------------
    def _read_instrument_file(self, instrument_path: str) -> bytes:
        """SAVe:... <instrument path> → FILESystem:READFile — the shared helper (task §5.2)."""

        return self._query_binary(f'FILESystem:READFile "{instrument_path}"')

    def _delete_instrument_file_best_effort(self, instrument_path: str) -> None:
        try:
            self._write(f'FILESystem:DELEte "{instrument_path}"')
        except Exception as exc:  # noqa: BLE001 - best-effort cleanup only
            logger.warning("TBS1000C: could not remove temp file %s: %s", instrument_path, exc)

    def save_screen_image(
        self,
        host_path: str | Path,
        image_format: ImageFormat | str | None = None,
        layout: ImageLayout | str | None = None,
    ) -> None:
        host_path = Path(host_path)
        fmt = ImageFormat(image_format) if image_format else ImageFormat(
            {".png": "PNG", ".bmp": "BMP", ".jpg": "JPG", ".jpeg": "JPG"}.get(
                host_path.suffix.lower(), "PNG"
            )
        )
        self._write(f"SAVe:IMAge:FILEFormat {fmt.value}")
        if layout is not None:
            self._write(f"SAVe:IMAge:LAYout {ImageLayout(layout).value}")
        instrument_path = f"tmp_rf_tbs1000c_screen.{fmt.value.lower()}"
        self._write(f'SAVe:IMAge "{instrument_path}"')
        data = self._read_instrument_file(instrument_path)
        host_path.parent.mkdir(parents=True, exist_ok=True)
        host_path.write_bytes(data)
        self._delete_instrument_file_best_effort(instrument_path)

    def save_waveform_to_csv(self, host_path: str | Path, channel: int) -> None:
        """Primary implementation: host-side decode of get_waveform(), no instrument storage."""

        waveform = self.get_waveform(channel)
        host_path = Path(host_path)
        host_path.parent.mkdir(parents=True, exist_ok=True)
        with host_path.open("w", encoding="ascii", newline="") as handle:
            handle.write("time_s,volts\n")
            for t, v in zip(waveform.time_s, waveform.volts):
                handle.write(f"{t},{v}\n")

    def save_waveform_to_csv_on_instrument(self, host_path: str | Path, channel: int) -> None:
        """Vendor-native alternate: instrument-side SAVe:WAVEform in SPREADSheet format."""

        channel = _validate_channel(channel)
        self._write("SAVe:WAVEform:FILEFormat SPREADSheet")
        instrument_path = f"tmp_rf_tbs1000c_waveform_ch{channel}.csv"
        self._write(f'SAVe:WAVEform CH{channel}, "{instrument_path}"')
        data = self._read_instrument_file(instrument_path)
        host_path = Path(host_path)
        host_path.parent.mkdir(parents=True, exist_ok=True)
        host_path.write_bytes(data)
        self._delete_instrument_file_best_effort(instrument_path)

    def _write_instrument_file(self, instrument_path: str, data: bytes) -> None:
        """FILESystem:WRITEFile <path>, <IEEE block> — the write counterpart to
        :meth:`_read_instrument_file` (Gate 3, task §2 "instrument-side waveform
        save/recall")."""

        self._require_connected()
        self.transport.write_binary(f'FILESystem:WRITEFile "{instrument_path}", ', build_ieee_block(data))

    def save_waveform_to_reference_memory(self, channel: int, ref: int) -> None:
        """Instrument-side SAVe:WAVEform CH<x>,REF<y> — no host file transfer, distinct
        from :meth:`save_waveform_to_csv_on_instrument` (Gate 3)."""

        channel = _validate_channel(channel)
        ref = _validate_ref(ref)
        self._write(f"SAVe:WAVEform CH{channel},REF{ref}")
        self._check_events(f"Save Waveform To Reference Memory(CH{channel}->REF{ref})")

    def recall_waveform_from_host_file(self, host_path: str | Path, ref: int) -> None:
        """Uploads a host file to the instrument's temp filesystem, then RECAll:WAVEform
        into reference memory — the round-trip counterpart to
        :meth:`save_waveform_to_csv_on_instrument`'s temp-file pattern (Gate 3)."""

        ref = _validate_ref(ref)
        host_path = Path(host_path)
        data = host_path.read_bytes()
        instrument_path = f"tmp_rf_tbs1000c_recall_ref{ref}{host_path.suffix or '.isf'}"
        self._write_instrument_file(instrument_path, data)
        self._write(f'RECAll:WAVEform "{instrument_path}",REF{ref}')
        self._check_events(f"Recall Waveform From Host File(ref={ref})")
        self._delete_instrument_file_best_effort(instrument_path)

    def save_setup(self, host_path: str | Path) -> None:
        """Primary implementation: *LRN? written verbatim to a host file. No instrument file."""

        setup_string = self._query("*LRN?")
        host_path = Path(host_path)
        host_path.parent.mkdir(parents=True, exist_ok=True)
        host_path.write_text(setup_string, encoding="ascii")

    def restore_setup(self, host_path: str | Path) -> None:
        """Resend a *LRN?-captured setup string, then verify via the event queue."""

        host_path = Path(host_path)
        if not host_path.is_file():
            raise Tbs1000cValidationError(f"setup file not found: {host_path}")
        setup_string = host_path.read_text(encoding="ascii").strip()
        if not setup_string:
            raise Tbs1000cValidationError(f"setup file is empty: {host_path}")
        self._write(setup_string)
        self._check_events("Restore Setup")

    def save_setup_to_instrument_memory(self, slot: int) -> None:
        slot = int(slot)
        if not (1 <= slot <= 10):
            raise Tbs1000cValidationError("slot must be between 1 and 10")
        self._write(f"*SAV {slot}")

    def restore_setup_from_instrument_memory(self, slot: int) -> None:
        slot = int(slot)
        if not (1 <= slot <= 10):
            raise Tbs1000cValidationError("slot must be between 1 and 10")
        self._write(f"*RCL {slot}")
        self._check_events("Restore Setup From Instrument Memory")

    def restore_factory_setup(self) -> None:
        self._write("RECAll:SETUp FACtory")

    # ------------------------------------------------------------------
    # Raw SCPI escape hatch (task §11)
    # ------------------------------------------------------------------
    def enable_raw_scpi(self, confirmation: str) -> None:
        if confirmation != _RAW_SCPI_CONFIRMATION:
            raise Tbs1000cValidationError(
                f'raw SCPI requires the exact confirmation text "{_RAW_SCPI_CONFIRMATION}"'
            )
        self._raw_scpi_enabled = True

    def _require_raw_scpi_enabled(self) -> None:
        if not self._raw_scpi_enabled:
            raise Tbs1000cValidationError(
                "raw SCPI is disabled; call enable_raw_scpi() with the exact confirmation text first"
            )

    def raw_query(self, command: str) -> str:
        self._require_raw_scpi_enabled()
        return self._query(command)

    def raw_write(self, command: str) -> None:
        self._require_raw_scpi_enabled()
        self._write(command)
