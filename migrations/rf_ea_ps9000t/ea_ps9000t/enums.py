"""Enums for EA-PS 9000 T SCPI argument values, grounded in the EA/Intepro Systems
"Programming Guide ModBus & SCPI" (Doc ID PGMBEN, Rev. 17) — every value here was
checked against that document's PST compatibility column specifically.

Real SCPI accepts both a command's long form and its abbreviated mnemonic
(e.g. "REMote" or "REM") — the same generic case-insensitive prefix-matching
``_missing_`` hook already proven in ``agilent33220a``/``agilent34411a`` is
reused verbatim here.
"""

from __future__ import annotations

from enum import Enum


class _ScpiEnum(str, Enum):
    """Base class: accepts a value's long SCPI form as well as its canonical short mnemonic."""

    @classmethod
    def _missing_(cls, value: object) -> _ScpiEnum | None:
        if not isinstance(value, str):
            return None
        token = value.strip().upper()
        for member in cls:
            if member.value.upper() == token:
                return member
        for member in cls:
            if token.startswith(member.value.upper()):
                return member
        return None


class RemoteControlOwner(_ScpiEnum):
    """SYSTem:LOCK:OWNer? {REMOTE|NONE|LOCAL}.

    A different vocabulary from the plain ON/OFF request one sends to
    SYSTem:LOCK — this is a readback of *who currently holds* remote
    control, not an echo of the last request (task §5).
    """

    REMOTE = "REMOTE"
    NONE = "NONE"
    LOCAL = "LOCAL"


class PowerStageAfterRemote(_ScpiEnum):
    """POWer:STAGe:AFTer:REMote {AUTO|OFF} — DC output state after leaving remote control."""

    AUTO = "AUTO"
    OFF = "OFF"


class OutputRestoreMode(_ScpiEnum):
    """SYSTem:CONFig:OUTPut:RESTore {AUTO|OFF} — DC output state after power-on."""

    AUTO = "AUTO"
    OFF = "OFF"


class AlarmAction(_ScpiEnum):
    """SYSTem:ALARm:ACTion:PFail / :OTEMperature {AUTO|OFF} — DC output state after
    a power-fail or overtemperature alarm clears."""

    AUTO = "AUTO"
    OFF = "OFF"


class AnalogRemsbLevel(_ScpiEnum):
    """SYSTem:CONFig:ANAlog:REMSB:LEVel {NORMAL|INVERTED} — how pin REM-SB of the
    analog interface is interpreted. Factory default NORMAL (Gate 3, task §2/§9)."""

    NORMAL = "NORMAL"
    INVERTED = "INVERTED"


class AnalogRemsbAction(_ScpiEnum):
    """SYSTem:CONFig:ANAlog:REMSB:ACTion {OFF|AUTO} — what pin REM-SB of the analog
    interface can do to the DC output: OFF = switch off only, AUTO = switch off and
    back on if it was previously enabled via front panel or digital command. Factory
    default OFF (Gate 3, task §2/§9)."""

    OFF = "OFF"
    AUTO = "AUTO"
