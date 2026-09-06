"""Pure encode/decode helpers: IEEE-488.2 definite-length blocks and waveform scaling.

No transport or SCPI-command-building logic lives here — only byte/number
transforms, so they're trivially unit-testable against known values.
"""

from __future__ import annotations

import struct

from scpi_driver_core.exceptions import ScpiDriverError
from scpi_driver_core.scpi import (
    decode_definite_length_block,
    encode_definite_length_block,
    parse_identity,
)

from .exceptions import Tbs1000cProtocolError
from .models import InstrumentIdentity, WaveformPreamble


def parse_idn(raw: str) -> InstrumentIdentity:
    """Parse *IDN?, e.g. ``TEKTRONIX,TBS 1072C,CU10100,CF:91.1CT FV:v...; FPGA:v1.21;``."""

    try:
        identity = parse_identity(raw)
    except ScpiDriverError as exc:
        raise Tbs1000cProtocolError(f"unrecognized *IDN? response: {raw!r}") from exc
    return InstrumentIdentity(
        manufacturer=identity.manufacturer,
        model=identity.model,
        serial=identity.serial_number or "",
        firmware=identity.firmware_version or "",
        raw=raw.strip(),
    )


def build_ieee_block(data: bytes) -> bytes:
    """Encode ``data`` as an IEEE-488.2 definite-length block: ``#<ndigits><length><data>``."""

    return encode_definite_length_block(data)


def parse_curve_response(raw: bytes) -> bytes:
    """Return the raw sample bytes from a ``CURVe?`` response.

    Handles both the binary IEEE block form (``#<n><len><data>``) and the
    ASCII comma-separated integer form (one byte per sample encoded as text).

    The binary path never calls ``.strip()`` on sample bytes (RFDS-004: no
    generic whitespace-stripping on raw protocol data) — a sample byte can
    legitimately equal a whitespace code point (e.g. 0x0A), and stripping it
    would silently corrupt the waveform. The declared IEEE block length is
    the sole source of truth for where the payload ends; only a leading '#'
    marker check and trailing terminator bytes *after* that declared length
    are ever discarded.
    """

    if raw[:1] == b"#":
        try:
            return decode_definite_length_block(raw, allow_trailing=True)
        except ScpiDriverError as exc:
            # The declared length stays the sole source of truth for where the
            # payload ends; the core enforces that and never strips a sample byte.
            raise Tbs1000cProtocolError(f"CURVe? block: {exc}") from exc

    # ASCII form: comma-separated signed integers, one per sample. This is a
    # genuine text response, so terminator whitespace is safe to strip here.
    text = raw.strip().decode("ascii", errors="strict")
    values = [int(item) for item in text.split(",") if item.strip()]
    return bytes(struct.pack(f">{len(values)}b", *values)) if values else b""


def decode_samples(raw: bytes, preamble: WaveformPreamble) -> list[int]:
    """Convert raw sample bytes into integer codes per the preamble's width/format.

    Byte order: Tektronix's documented default is big-endian ("MSB first") for
    multi-byte binary waveform data; this is assumed here since ``BYT_Or`` was
    not part of this driver's confirmed command inventory (see task §2). If
    real-hardware testing (task §13.3) shows little-endian data, this is the
    only place that needs to change.
    """

    byt_nr = preamble.byt_nr
    signed = preamble.bn_fmt.upper().startswith("RI")
    if byt_nr not in (1, 2):
        raise Tbs1000cProtocolError(f"unsupported WFMOutpre:BYT_Nr {byt_nr!r}; expected 1 or 2")
    if len(raw) % byt_nr != 0:
        raise Tbs1000cProtocolError(
            f"CURVe? byte count {len(raw)} is not a multiple of BYT_Nr {byt_nr}"
        )
    count = len(raw) // byt_nr
    if preamble.nr_pt and count != preamble.nr_pt:
        raise Tbs1000cProtocolError(
            f"CURVe? returned {count} points but WFMOutpre:NR_Pt? reported {preamble.nr_pt}"
        )
    fmt_code = {1: "b", 2: "h"}[byt_nr] if signed else {1: "B", 2: "H"}[byt_nr]
    fmt = f">{count}{fmt_code}"
    return list(struct.unpack(fmt, raw))


def scale_waveform(codes: list[int], preamble: WaveformPreamble) -> tuple[list[float], list[float]]:
    """Apply the standard Tektronix waveform scaling formulas.

    ``volts[i] = (code[i] - y_offset) * y_multiplier + y_zero``
    ``time_s[i] = i * x_increment + x_zero``
    """

    volts = [(code - preamble.y_offset) * preamble.y_multiplier + preamble.y_zero for code in codes]
    time_s = [index * preamble.x_increment + preamble.x_zero for index in range(len(codes))]
    return time_s, volts
