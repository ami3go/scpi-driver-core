"""Enums for TBS1000C SCPI argument values, grounded in the programmer manual (077-1691-02)."""

from __future__ import annotations

from enum import Enum


class Coupling(str, Enum):
    """CH<x>:COUPling {AC|DC}."""

    AC = "AC"
    DC = "DC"


class TriggerCoupling(str, Enum):
    """TRIGger:A:EDGE:COUPling {DC|HFRej|LFRej|NOISErej}."""

    DC = "DC"
    HF_REJECT = "HFRej"
    LF_REJECT = "LFRej"
    NOISE_REJECT = "NOISErej"


class TriggerSlope(str, Enum):
    """TRIGger:A:EDGE:SLOpe {RISE|FALL}."""

    RISE = "RISE"
    FALL = "FALL"


class AcquisitionMode(str, Enum):
    """ACQuire:MODe {SAMPLE|PEAKDETECT|AVERAGE}."""

    SAMPLE = "SAMPLE"
    PEAK_DETECT = "PEAKDETECT"
    AVERAGE = "AVERAGE"


class AcquisitionState(str, Enum):
    """ACQuire:STATE {0|1|RUN|STOP}. The instrument accepts either form; we always send words."""

    RUN = "RUN"
    STOP = "STOP"


class ImageFormat(str, Enum):
    """SAVe:IMAge:FILEFormat {PNG|BMP|JPG}."""

    PNG = "PNG"
    BMP = "BMP"
    JPG = "JPG"


class ImageLayout(str, Enum):
    """SAVe:IMAge:LAYout {LANdscape|PORTRait}."""

    LANDSCAPE = "LANdscape"
    PORTRAIT = "PORTRait"


class MeasurementType(str, Enum):
    """MEASUrement:IMMed:TYPe argument grammar (full enumeration from the manual)."""

    AMPLITUDE = "AMPlitude"
    AREA = "AREa"
    BURST = "BURst"
    CYCLE_AREA = "CARea"
    CYCLE_MEAN = "CMEan"
    CYCLE_RMS = "CRMs"
    DELAY = "DELay"
    FALL_TIME = "FALL"
    FREQUENCY = "FREQuency"
    HIGH = "HIGH"
    LOW = "LOW"
    MAXIMUM = "MAXimum"
    MEAN = "MEAN"
    MINIMUM = "MINImum"
    NEGATIVE_DUTY = "NDUty"
    NEGATIVE_EDGE_COUNT = "NEDGECount"
    NEGATIVE_OVERSHOOT = "NOVershoot"
    NEGATIVE_PULSE_COUNT = "NPULSECount"
    NEGATIVE_WIDTH = "NWIdth"
    POSITIVE_EDGE_COUNT = "PEDGECount"
    POSITIVE_DUTY = "PDUty"
    PERIOD = "PERIod"
    PHASE = "PHAse"
    PEAK_TO_PEAK = "PK2Pk"
    POSITIVE_OVERSHOOT = "POVershoot"
    POSITIVE_PULSE_COUNT = "PPULSECount"
    POSITIVE_WIDTH = "PWIdth"
    RISE_TIME = "RISe"
    RMS = "RMS"
