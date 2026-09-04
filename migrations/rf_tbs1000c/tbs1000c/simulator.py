"""Deterministic in-process TBS1000C simulator.

Implements the command subset the core driver actually issues (task doc
§12), as a text-in/bytes-out dispatcher so the driver's real SCPI strings
are exercised exactly as they would be against hardware — no command is
special-cased away from the wire-protocol layer.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import ClassVar

from .codec import build_ieee_block

_OVERLOAD_SENTINEL = 9.9e37

_IDN = "TEKTRONIX,TBS 1052C,SIM00001,CF:91.1CT FV:v2026-01-01_00-00-00rootfs; FPGA:v1.21;"

_DEFAULT_CHANNEL = {
    "scale": 1.0,
    "position": 0.0,
    "offset": 0.0,
    "coupling": "DC",
    "bandwidth": "FULl",
    "probe_gain": 1.0,
    "label": "",
}


@dataclass
class _CalibrationState:
    running: bool = False
    results: str = "PASS"


@dataclass
class _TriggerState:
    source: str = "CH1"
    slope: str = "RISE"
    coupling: str = "DC"
    level: float = 0.0


@dataclass
class _AcquisitionState:
    mode: str = "SAMPLE"
    state: str = "RUN"
    stopafter: str = "RUNSTOP"
    numavg: int = 16
    numacq: int = 0


@dataclass
class _MeasurementState:
    type: str = "AMPlitude"
    forced_overload: bool = False


class SimTbs1000cInstrument:
    """A small, deterministic stand-in for a real TBS1000C over USBTMC."""

    def __init__(self, *, record_length: int = 500, waveform_hz: float = 1_000.0) -> None:
        self.channels: dict[str, dict[str, object]] = {
            "1": dict(_DEFAULT_CHANNEL),
            "2": dict(_DEFAULT_CHANNEL),
        }
        self.trigger = _TriggerState()
        self.acquisition = _AcquisitionState()
        self.measurement = _MeasurementState()
        self.calibration = _CalibrationState()
        self.data_source = "CH1"
        self.data_start = 1
        self.data_stop = record_length
        self.record_length = record_length
        self.waveform_hz = waveform_hz
        self.image_format = "PNG"
        self.image_layout = "LANdscape"
        self.waveform_file_format = "INTERNal"
        self.filesystem: dict[str, bytes] = {}
        self.memory_slots: dict[int, str] = {}
        self.reference_waveforms: dict[int, bytes] = {}
        self.autoset_calls = 0
        self.calibration_start_calls = 0
        self.force_trigger_calls = 0
        self._events: list[tuple[int, str]] = []

    # -- public dispatch -------------------------------------------------

    def dispatch(self, command: str) -> bytes:
        command = command.strip()
        if not command:
            return b""
        # A handful of real TBS1000C commands are space-separated pseudo-arguments
        # rather than colon-delimited sub-commands (e.g. "TRIGger FORCe", not
        # "TRIGger:FORCe") — route those explicitly before the generic splitter,
        # which would otherwise treat "TRIGger" as an unroutable bare head.
        upper_command = command.upper()
        if upper_command == "TRIGGER FORCE":
            return self._trigger_force("", False)
        if upper_command.startswith("TRIGGER:A SETLEVEL"):
            return self._trigger_a("SETLevel", False)

        if ";" in command:
            return self._dispatch_concatenated(command)

        head, _, rest = command.partition(" ")
        rest = rest.strip()
        is_query = head.endswith("?")
        handler_name = head[:-1] if is_query else head

        channel_match = re.match(r"^CH(\d):(.+)$", handler_name, re.IGNORECASE)
        if channel_match:
            return self._dispatch_channel(channel_match.group(1), channel_match.group(2), rest, is_query)

        ref_match = re.match(r"^REF(\d+)$", handler_name, re.IGNORECASE)
        if ref_match:
            return self._ref_query(int(ref_match.group(1)), is_query)

        try:
            handler = self._ROUTES[handler_name.upper()]
        except KeyError:
            self._push_event(113, f"Undefined header;{command}")
            return b""
        return handler(self, rest, is_query)

    def dispatch_binary(self, command_prefix: str, data: bytes) -> None:
        """Handles ``FILESystem:WRITEFile "<path>", <IEEE block>`` — the write
        counterpart to ``_filesystem_readfile``'s IEEE-block-encoded response.
        ``data`` is the already block-encoded payload built by ``driver.py``
        via :func:`build_ieee_block`; this method decodes it the same way a
        real instrument would.
        """

        match = re.match(r'^FILESYSTEM:WRITEFILE\s+"([^"]*)"\s*,\s*$', command_prefix.strip(), re.IGNORECASE)
        if not match:
            self._push_event(113, f"Undefined header;{command_prefix}")
            return
        if data[:1] != b"#" or len(data) < 2:
            self._push_event(-161, "Invalid block data")
            return
        n_digits = int(chr(data[1]))
        header_len = 2 + n_digits
        length = int(data[2:header_len])
        self.filesystem[match.group(1)] = data[header_len : header_len + length]

    def _dispatch_concatenated(self, command: str) -> bytes:
        """Replay a ';'-separated command sequence, e.g. a resent *LRN?/SET? string.

        Follows the manual's "Concatenating Commands" convention: a segment
        starting with ':' (or any segment whose head contains ':') is a fully
        qualified header and establishes the current command group; a bare
        "KEYWORD arg" segment inherits that group. Mirrors exactly what this
        simulator's own :meth:`_learn_string` produces, so ``Restore Setup``
        round-trips through the same dispatcher every other command uses.
        """

        group = ""
        last_response = b""
        for segment in command.split(";"):
            segment = segment.strip()
            if not segment:
                continue
            if segment.startswith(":"):
                segment = segment[1:].strip()
            head, _, rest = segment.partition(" ")
            if ":" in head:
                group = head.rsplit(":", 1)[0]
                full_command = segment
            elif group:
                full_command = f"{group}:{head}" + (f" {rest}" if rest else "")
            else:
                full_command = segment
            last_response = self.dispatch(full_command)
        return last_response

    # -- standard/common commands ----------------------------------------

    def _idn(self, _rest: str, _is_query: bool) -> bytes:
        return _IDN.encode("ascii")

    def _cls(self, _rest: str, _is_query: bool) -> bytes:
        self._events.clear()
        return b""

    def _rst(self, _rest: str, _is_query: bool) -> bytes:
        self.__init__(record_length=self.record_length, waveform_hz=self.waveform_hz)  # type: ignore[misc]
        return b""

    def _opc(self, _rest: str, _is_query: bool) -> bytes:
        return b"1"

    def _cal(self, _rest: str, _is_query: bool) -> bytes:
        return b"0"

    def _busy(self, _rest: str, _is_query: bool) -> bytes:
        return b"1" if self.calibration.running else b"0"

    def _esr(self, _rest: str, _is_query: bool) -> bytes:
        return b"0" if not self._events else b"32"

    def _event(self, _rest: str, _is_query: bool) -> bytes:
        if not self._events:
            return b"0"
        code, _ = self._events.pop(0)
        return str(code).encode("ascii")

    def _evmsg(self, _rest: str, _is_query: bool) -> bytes:
        if not self._events:
            return b'0,"No events to report - queue empty"'
        code, message = self._events[0]
        return f'{code},"{message}"'.encode("ascii")

    def _allev(self, _rest: str, _is_query: bool) -> bytes:
        if not self._events:
            return b'0,"No events to report - queue empty"'
        parts = [f'{code},"{message}"' for code, message in self._events]
        self._events.clear()
        return ";".join(parts).encode("ascii")

    def _push_event(self, code: int, message: str) -> None:
        self._events.append((code, message))

    # -- acquisition -------------------------------------------------------

    def _acquire(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b"1"
        return b""

    def _acquire_mode(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.acquisition.mode.encode("ascii")
        self.acquisition.mode = rest.upper()
        return b""

    def _acquire_state(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b"1" if self.acquisition.state == "RUN" else b"0"
        value = rest.upper()
        if value in ("1", "RUN"):
            self.acquisition.state = "RUN"
        elif value in ("0", "STOP"):
            self.acquisition.state = "STOP"
        self.acquisition.numacq += 1
        return b""

    def _acquire_stopafter(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.acquisition.stopafter.encode("ascii")
        self.acquisition.stopafter = rest.upper()
        return b""

    def _acquire_numacq(self, _rest: str, _is_query: bool) -> bytes:
        return str(self.acquisition.numacq).encode("ascii")

    def _acquire_numavg(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return str(self.acquisition.numavg).encode("ascii")
        self.acquisition.numavg = int(float(rest))
        return b""

    def _acquire_maxsamplerate(self, _rest: str, _is_query: bool) -> bytes:
        return b"1.0E9"

    # -- trigger -------------------------------------------------------------

    def _trigger_a(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return (
                f"SOURCE {self.trigger.source};COUPLING {self.trigger.coupling};"
                f"SLOPE {self.trigger.slope}"
            ).encode("ascii")
        if rest.upper().startswith("SETLEVEL"):
            self.trigger.level = 0.0
        return b""

    def _trigger_a_edge_source(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.trigger.source.encode("ascii")
        self.trigger.source = rest.upper()
        return b""

    def _trigger_a_edge_slope(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.trigger.slope.encode("ascii")
        self.trigger.slope = rest.upper()
        return b""

    def _trigger_a_edge_coupling(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.trigger.coupling.encode("ascii")
        self.trigger.coupling = rest.upper()
        return b""

    def _trigger_a_level(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.trigger.level:.4E}".encode("ascii")
        self.trigger.level = float(rest)
        return b""

    def _trigger_force(self, _rest: str, _is_query: bool) -> bytes:
        self.force_trigger_calls += 1
        self.acquisition.numacq += 1
        return b""

    def _autoset(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b"1"
        self.autoset_calls += 1
        return b""

    # -- measurement -----------------------------------------------------

    def _measurement_immed_type(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.measurement.type.encode("ascii")
        self.measurement.type = rest
        return b""

    def _measurement_immed(self, _rest: str, _is_query: bool) -> bytes:
        if self.measurement.forced_overload:
            return f"{_OVERLOAD_SENTINEL:.4E}".encode("ascii")
        value = self._synthetic_measurement(self.measurement.type)
        return f"{value:.6E}".encode("ascii")

    def _synthetic_measurement(self, measurement_type: str) -> float:
        amplitude = 1.0 * float(self.channels[self.data_source[-1]]["probe_gain"])
        table = {
            "AMPLITUDE": amplitude,
            "PK2PK": amplitude,
            "FREQUENCY": self.waveform_hz,
            "PERIOD": 1.0 / self.waveform_hz,
            "MEAN": 0.0,
            "RMS": amplitude / math.sqrt(2),
        }
        return table.get(measurement_type.upper(), amplitude)

    # -- calibration -----------------------------------------------------

    def _calibrate_internal_start(self, _rest: str, _is_query: bool) -> bytes:
        self.calibration_start_calls += 1
        self.calibration.running = True
        self.calibration.results = "PASS"
        self.calibration.running = False
        return b""

    def _calibrate_internal_status(self, _rest: str, _is_query: bool) -> bytes:
        return b"1" if self.calibration.running else b"0"

    def _calibrate_results(self, _rest: str, _is_query: bool) -> bytes:
        return self.calibration.results.encode("ascii")

    # -- waveform selection / transfer ------------------------------------

    def _data_source(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.data_source.encode("ascii")
        self.data_source = rest.upper()
        return b""

    def _data_start(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return str(self.data_start).encode("ascii")
        self.data_start = int(float(rest))
        return b""

    def _data_stop(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return str(self.data_stop).encode("ascii")
        self.data_stop = int(float(rest))
        return b""

    def _curve(self, _rest: str, is_query: bool) -> bytes:
        if not is_query:
            return b""
        codes = self._synthetic_codes()
        payload = b"".join(int(c).to_bytes(1, "big", signed=True) for c in codes)
        return build_ieee_block(payload)

    def _synthetic_codes(self) -> list[int]:
        channel = self.data_source[-1] if self.data_source[-1].isdigit() else "1"
        gain = float(self.channels.get(channel, _DEFAULT_CHANNEL)["probe_gain"])
        points = self.record_length
        sample_period = 1.0 / (self.waveform_hz * 50.0)
        codes = []
        for index in range(points):
            t = index * sample_period
            volts = gain * math.sin(2 * math.pi * self.waveform_hz * t)
            code = round(volts * 25.0)
            codes.append(max(-127, min(127, code)))
        return codes

    def _wfmoutpre_bit_nr(self, _rest: str, _is_query: bool) -> bytes:
        return b"8"

    def _wfmoutpre_bn_fmt(self, _rest: str, _is_query: bool) -> bytes:
        return b"RI"

    def _wfmoutpre_byt_nr(self, _rest: str, _is_query: bool) -> bytes:
        return b"1"

    def _wfmoutpre_encdg(self, _rest: str, _is_query: bool) -> bytes:
        return b"BINARY"

    def _wfmoutpre_nr_pt(self, _rest: str, _is_query: bool) -> bytes:
        return str(self.record_length).encode("ascii")

    def _wfmoutpre_recordlength(self, _rest: str, _is_query: bool) -> bytes:
        return str(self.record_length).encode("ascii")

    def _wfmoutpre_wfid(self, _rest: str, _is_query: bool) -> bytes:
        return f'"{self.data_source}, DC coupling, 1.0E0 V/div, {self.record_length} points"'.encode("ascii")

    def _wfmoutpre_xincr(self, _rest: str, _is_query: bool) -> bytes:
        sample_period = 1.0 / (self.waveform_hz * 50.0)
        return f"{sample_period:.6E}".encode("ascii")

    def _wfmoutpre_xunit(self, _rest: str, _is_query: bool) -> bytes:
        return b'"s"'

    def _wfmoutpre_xzero(self, _rest: str, _is_query: bool) -> bytes:
        return b"0.0E0"

    def _wfmoutpre_ymult(self, _rest: str, _is_query: bool) -> bytes:
        return b"4.0E-2"

    def _wfmoutpre_yoff(self, _rest: str, _is_query: bool) -> bytes:
        return b"0.0E0"

    def _wfmoutpre_yzero(self, _rest: str, _is_query: bool) -> bytes:
        return b"0.0E0"

    def _wfmoutpre_yunit(self, _rest: str, _is_query: bool) -> bytes:
        return b'"V"'

    # -- save/recall + filesystem -----------------------------------------

    def _save_image_fileformat(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.image_format.encode("ascii")
        self.image_format = rest.upper()
        return b""

    def _save_image_layout(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.image_layout.encode("ascii")
        self.image_layout = rest
        return b""

    def _save_image(self, rest: str, _is_query: bool) -> bytes:
        path = rest.strip().strip('"')
        placeholder = f"SIMULATED-{self.image_format}-IMAGE".encode("ascii")
        self.filesystem[path] = placeholder
        return b""

    def _save_waveform_fileformat(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.waveform_file_format.encode("ascii")
        self.waveform_file_format = rest.upper()
        return b""

    def _save_waveform(self, rest: str, _is_query: bool) -> bytes:
        parts = [p.strip().strip('"') for p in rest.split(",")]
        target = parts[-1] if parts else ""
        codes = self._synthetic_codes()
        if self.waveform_file_format == "SPREADSHEET":
            lines = ["Time,Value"] + [f"{i},{c}" for i, c in enumerate(codes)]
            data = "\n".join(lines).encode("ascii")
        else:
            data = bytes(int(c) & 0xFF for c in codes)
        ref_match = re.match(r"^REF(\d+)$", target, re.IGNORECASE)
        if ref_match:
            self.reference_waveforms[int(ref_match.group(1))] = data
        elif target:
            self.filesystem[target] = data
        return b""

    def _recall_waveform(self, rest: str, _is_query: bool) -> bytes:
        """RECAll:WAVEform <file path>,REF<x> — recall a previously-saved-to-file
        waveform into internal reference memory."""

        parts = [p.strip().strip('"') for p in rest.split(",")]
        if len(parts) < 2:
            self._push_event(-224, "Illegal parameter value;RECAll:WAVEform requires <path>,REF<x>")
            return b""
        path, ref_token = parts[0], parts[1]
        ref_match = re.match(r"^REF(\d+)$", ref_token, re.IGNORECASE)
        if not ref_match:
            self._push_event(-224, f"Illegal parameter value;{ref_token!r} is not a REF<x> destination")
            return b""
        try:
            data = self.filesystem[path]
        except KeyError:
            self._push_event(292, f"Execution error, file not found;{path}")
            return b""
        self.reference_waveforms[int(ref_match.group(1))] = (
            data if isinstance(data, bytes) else data.encode("ascii")
        )
        return b""

    def _ref_query(self, ref: int, _is_query: bool) -> bytes:
        if ref not in self.reference_waveforms:
            self._push_event(-224, f"Illegal parameter value;REF{ref} has no data")
            return b""
        return build_ieee_block(self.reference_waveforms[ref])

    def _save_setup(self, rest: str, _is_query: bool) -> bytes:
        target = rest.strip().strip('"')
        setup_string = self._learn_string()
        if target.lstrip("-").isdigit():
            self.memory_slots[int(target)] = setup_string
        elif target:
            self.filesystem[target] = setup_string.encode("ascii")
        return b""

    def _recall_setup(self, rest: str, _is_query: bool) -> bytes:
        target = rest.strip().strip('"')
        if target.upper() == "FACTORY":
            self.__init__(record_length=self.record_length, waveform_hz=self.waveform_hz)  # type: ignore[misc]
        elif target.lstrip("-").isdigit():
            self.memory_slots.get(int(target))
        return b""

    def _sav(self, rest: str, _is_query: bool) -> bytes:
        self.memory_slots[int(rest)] = self._learn_string()
        return b""

    def _rcl(self, rest: str, _is_query: bool) -> bytes:
        self.memory_slots.get(int(rest))
        return b""

    def _lrn(self, _rest: str, _is_query: bool) -> bytes:
        return self._learn_string().encode("ascii")

    def _set(self, _rest: str, _is_query: bool) -> bytes:
        return self._learn_string().encode("ascii")

    def _learn_string(self) -> str:
        return (
            f"ACQUIRE:STOPAFTER {self.acquisition.stopafter};STATE 1;MODE {self.acquisition.mode}; "
            f"NUMAVG {self.acquisition.numavg};"
            f":CH1:SCALE {self.channels['1']['scale']:.4E};POSITION {self.channels['1']['position']:.4E};"
            f"COUPLING {self.channels['1']['coupling']};"
            f":CH2:SCALE {self.channels['2']['scale']:.4E};POSITION {self.channels['2']['position']:.4E};"
            f"COUPLING {self.channels['2']['coupling']};"
            f":TRIGGER:A:EDGE:SOURCE {self.trigger.source};SLOPE {self.trigger.slope};"
            f"COUPLING {self.trigger.coupling};"
        )

    def _filesystem_readfile(self, rest: str, _is_query: bool) -> bytes:
        path = rest.strip().strip('"')
        try:
            data = self.filesystem[path]
        except KeyError:
            self._push_event(292, f"Execution error, file not found;{path}")
            return b""
        return build_ieee_block(data) if not isinstance(data, str) else build_ieee_block(data.encode("ascii"))

    def _filesystem_dir(self, _rest: str, _is_query: bool) -> bytes:
        return ",".join(sorted(self.filesystem)).encode("ascii")

    def _filesystem_freespace(self, _rest: str, _is_query: bool) -> bytes:
        return b"6242501"

    def _filesystem_cwd(self, rest: str, is_query: bool) -> bytes:
        return b'"usb0/"'

    def _filesystem_delete(self, rest: str, _is_query: bool) -> bytes:
        path = rest.strip().strip('"')
        self.filesystem.pop(path, None)
        return b""

    # -- per-channel ------------------------------------------------------

    def _dispatch_channel(self, channel: str, field_name: str, rest: str, is_query: bool) -> bytes:
        settings = self.channels.setdefault(channel, dict(_DEFAULT_CHANNEL))
        key = field_name.upper()
        if key in ("SCALE", "SCAL", "SCA"):
            return self._channel_field(settings, "scale", rest, is_query, float, "{:.4E}")
        if key in ("POSITION", "POSITIO", "POS"):
            return self._channel_field(settings, "position", rest, is_query, float, "{:.4E}")
        if key in ("OFFSET", "OFFSE", "OFF"):
            return self._channel_field(settings, "offset", rest, is_query, float, "{:.4E}")
        if key in ("COUPLING", "COUPLIN", "COUP"):
            return self._channel_field(settings, "coupling", rest, is_query, str, "{}", upper=True)
        if key in ("BANDWIDTH", "BAND", "BAN"):
            return self._channel_field(settings, "bandwidth", rest, is_query, str, "{}")
        if key in ("PROBE:GAIN", "PRO:GAIN"):
            return self._channel_field(settings, "probe_gain", rest, is_query, float, "{:.4E}")
        if key in ("LABEL", "LABE", "LAB"):
            if is_query:
                return f'"{settings["label"]}"'.encode("ascii")
            settings["label"] = rest.strip().strip('"')
            return b""
        self._push_event(113, f"Undefined header;CH{channel}:{field_name}")
        return b""

    @staticmethod
    def _channel_field(settings, key, rest, is_query, cast, fmt, *, upper=False):
        if is_query:
            value = settings[key]
            text = fmt.format(value) if not isinstance(value, str) else value
            return text.encode("ascii")
        value = rest.strip()
        settings[key] = cast(value.upper() if upper else value)
        return b""

    # -- inject test helpers ----------------------------------------------

    def force_next_measurement_overload(self, overload: bool = True) -> None:
        self.measurement.forced_overload = overload

    _ROUTES: ClassVar[dict[str, object]]


SimTbs1000cInstrument._ROUTES = {
    "*IDN": SimTbs1000cInstrument._idn,
    "*CLS": SimTbs1000cInstrument._cls,
    "*RST": SimTbs1000cInstrument._rst,
    "*OPC": SimTbs1000cInstrument._opc,
    "*CAL": SimTbs1000cInstrument._cal,
    "BUSY": SimTbs1000cInstrument._busy,
    "*ESR": SimTbs1000cInstrument._esr,
    "EVENT": SimTbs1000cInstrument._event,
    "EVMSG": SimTbs1000cInstrument._evmsg,
    "ALLEV": SimTbs1000cInstrument._allev,
    "ACQUIRE": SimTbs1000cInstrument._acquire,
    "ACQUIRE:MODE": SimTbs1000cInstrument._acquire_mode,
    "ACQUIRE:STATE": SimTbs1000cInstrument._acquire_state,
    "ACQUIRE:STOPAFTER": SimTbs1000cInstrument._acquire_stopafter,
    "ACQUIRE:NUMACQ": SimTbs1000cInstrument._acquire_numacq,
    "ACQUIRE:NUMAVG": SimTbs1000cInstrument._acquire_numavg,
    "ACQUIRE:MAXSAMPLERATE": SimTbs1000cInstrument._acquire_maxsamplerate,
    "TRIGGER:A": SimTbs1000cInstrument._trigger_a,
    "TRIGGER:A:EDGE:SOURCE": SimTbs1000cInstrument._trigger_a_edge_source,
    "TRIGGER:A:EDGE:SLOPE": SimTbs1000cInstrument._trigger_a_edge_slope,
    "TRIGGER:A:EDGE:COUPLING": SimTbs1000cInstrument._trigger_a_edge_coupling,
    "TRIGGER:A:LEVEL": SimTbs1000cInstrument._trigger_a_level,
    "AUTOSET": SimTbs1000cInstrument._autoset,
    "MEASUREMENT:IMMED:TYPE": SimTbs1000cInstrument._measurement_immed_type,
    "MEASUREMENT:IMMED": SimTbs1000cInstrument._measurement_immed,
    "CALIBRATE:INTERNAL:START": SimTbs1000cInstrument._calibrate_internal_start,
    "CALIBRATE:INTERNAL:STATUS": SimTbs1000cInstrument._calibrate_internal_status,
    "CALIBRATE:RESULTS": SimTbs1000cInstrument._calibrate_results,
    "DATA:SOURCE": SimTbs1000cInstrument._data_source,
    "DATA:START": SimTbs1000cInstrument._data_start,
    "DATA:STOP": SimTbs1000cInstrument._data_stop,
    "CURVE": SimTbs1000cInstrument._curve,
    "WFMOUTPRE:BIT_NR": SimTbs1000cInstrument._wfmoutpre_bit_nr,
    "WFMOUTPRE:BN_FMT": SimTbs1000cInstrument._wfmoutpre_bn_fmt,
    "WFMOUTPRE:BYT_NR": SimTbs1000cInstrument._wfmoutpre_byt_nr,
    "WFMOUTPRE:ENCDG": SimTbs1000cInstrument._wfmoutpre_encdg,
    "WFMOUTPRE:NR_PT": SimTbs1000cInstrument._wfmoutpre_nr_pt,
    "WFMOUTPRE:RECORDLENGTH": SimTbs1000cInstrument._wfmoutpre_recordlength,
    "WFMOUTPRE:WFID": SimTbs1000cInstrument._wfmoutpre_wfid,
    "WFMOUTPRE:XINCR": SimTbs1000cInstrument._wfmoutpre_xincr,
    "WFMOUTPRE:XUNIT": SimTbs1000cInstrument._wfmoutpre_xunit,
    "WFMOUTPRE:XZERO": SimTbs1000cInstrument._wfmoutpre_xzero,
    "WFMOUTPRE:YMULT": SimTbs1000cInstrument._wfmoutpre_ymult,
    "WFMOUTPRE:YOFF": SimTbs1000cInstrument._wfmoutpre_yoff,
    "WFMOUTPRE:YZERO": SimTbs1000cInstrument._wfmoutpre_yzero,
    "WFMOUTPRE:YUNIT": SimTbs1000cInstrument._wfmoutpre_yunit,
    "SAVE:IMAGE:FILEFORMAT": SimTbs1000cInstrument._save_image_fileformat,
    "SAVE:IMAGE:LAYOUT": SimTbs1000cInstrument._save_image_layout,
    "SAVE:IMAGE": SimTbs1000cInstrument._save_image,
    "SAVE:WAVEFORM:FILEFORMAT": SimTbs1000cInstrument._save_waveform_fileformat,
    "SAVE:WAVEFORM": SimTbs1000cInstrument._save_waveform,
    "SAVE:SETUP": SimTbs1000cInstrument._save_setup,
    "RECALL:SETUP": SimTbs1000cInstrument._recall_setup,
    "RECALL:WAVEFORM": SimTbs1000cInstrument._recall_waveform,
    "*SAV": SimTbs1000cInstrument._sav,
    "*RCL": SimTbs1000cInstrument._rcl,
    "*LRN": SimTbs1000cInstrument._lrn,
    "SET": SimTbs1000cInstrument._set,
    "FILESYSTEM:READFILE": SimTbs1000cInstrument._filesystem_readfile,
    "FILESYSTEM:DIR": SimTbs1000cInstrument._filesystem_dir,
    "FILESYSTEM:FREESPACE": SimTbs1000cInstrument._filesystem_freespace,
    "FILESYSTEM:CWD": SimTbs1000cInstrument._filesystem_cwd,
    "FILESYSTEM:DELETE": SimTbs1000cInstrument._filesystem_delete,
}
