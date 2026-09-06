"""Command headers as the manual spells them. Generated; do not edit.

Written by ``migrations/scripts/generate_simulator_aliases.py`` from the
literals this driver sends. The capitals mark where each mnemonic's short form
ends, which is what lets the simulator accept ``SYST:ERR?`` as well as
``SYSTEM:ERROR?``, the way a real instrument does.

Headers containing a runtime substitution are not recorded: they are not
headers until the value is filled in.
"""

from __future__ import annotations

__all__ = ["CANONICAL_HEADERS"]

CANONICAL_HEADERS: tuple[str, ...] = (
    "*ESR",
    "*IDN",
    "*LRN",
    "*RCL",
    "*SAV",
    "ACQuire:MODe",
    "ACQuire:NUMACq",
    "ACQuire:STATE",
    "AUTOSet",
    "CALibrate:INTERNal:STARt",
    "CALibrate:INTERNal:STATus",
    "CALibrate:RESults",
    "DATa:SOUrce",
    "EVMsg",
    "FILESystem:DELEte",
    "FILESystem:WRITEFile",
    "MEASUrement:IMMed",
    "MEASUrement:IMMed:TYPe",
    "RECAll:SETUp",
    "RECAll:WAVEform",
    "SAVe:IMAge",
    "SAVe:IMAge:FILEFormat",
    "SAVe:IMAge:LAYout",
    "SAVe:WAVEform",
    "SAVe:WAVEform:FILEFormat",
    "TRIGger",
    "TRIGger:A",
    "TRIGger:A:EDGE:COUPling",
    "TRIGger:A:EDGE:SLOpe",
    "TRIGger:A:EDGE:SOUrce",
    "TRIGger:A:LEVel",
    "WFMOutpre:BIT_Nr",
    "WFMOutpre:BN_Fmt",
    "WFMOutpre:BYT_Nr",
    "WFMOutpre:ENCdg",
    "WFMOutpre:NR_Pt",
    "WFMOutpre:RECOrdlength",
    "WFMOutpre:WFId",
    "WFMOutpre:XINcr",
    "WFMOutpre:XUNit",
    "WFMOutpre:XZEro",
    "WFMOutpre:YMUlt",
    "WFMOutpre:YOFf",
    "WFMOutpre:YUNit",
    "WFMOutpre:YZEro",
)
