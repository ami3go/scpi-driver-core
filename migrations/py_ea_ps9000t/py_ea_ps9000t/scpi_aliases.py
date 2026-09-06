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
    "*IDN",
    "*OPC",
    "CURRent",
    "CURRent:LIMit:HIGH",
    "CURRent:LIMit:LOW",
    "CURRent:PROTection",
    "MEASure:ARRay",
    "MEASure:CURRent",
    "MEASure:POWer",
    "MEASure:VOLTage",
    "OUTPut",
    "POWer",
    "POWer:LIMit:HIGH",
    "POWer:PROTection",
    "POWer:STAGe:AFTer:REMote",
    "SYSTem:ALARm:ACTion:OTEMperature",
    "SYSTem:ALARm:ACTion:PFail",
    "SYSTem:ALARm:COUNt:OCURrent",
    "SYSTem:ALARm:COUNt:OPOWer",
    "SYSTem:ALARm:COUNt:OTEMperature",
    "SYSTem:ALARm:COUNt:OVOLtage",
    "SYSTem:ALARm:COUNt:PFAil",
    "SYSTem:COMMunicate:LAN:ADDRess",
    "SYSTem:COMMunicate:LAN:CONTrol",
    "SYSTem:COMMunicate:LAN:DHCP",
    "SYSTem:COMMunicate:LAN:DNS1",
    "SYSTem:COMMunicate:LAN:DNS2",
    "SYSTem:COMMunicate:LAN:DOMain",
    "SYSTem:COMMunicate:LAN:GATeway",
    "SYSTem:COMMunicate:LAN:HOSTname",
    "SYSTem:COMMunicate:LAN:KEEPalive",
    "SYSTem:COMMunicate:LAN:MAC",
    "SYSTem:COMMunicate:LAN:SMASk",
    "SYSTem:COMMunicate:LAN:TIMeout",
    "SYSTem:COMMunicate:TIMeout",
    "SYSTem:CONFig:ANAlog:REFerence",
    "SYSTem:CONFig:ANAlog:REMSB:ACTion",
    "SYSTem:CONFig:ANAlog:REMSB:LEVel",
    "SYSTem:CONFig:OUTPut:RESTore",
    "SYSTem:CONFig:USER:TEXT",
    "SYSTem:DEVice:CLASs",
    "SYSTem:ERRor",
    "SYSTem:LOCK",
    "SYSTem:LOCK:OWNer",
    "SYSTem:NOMinal:CURRent",
    "SYSTem:NOMinal:POWer",
    "SYSTem:NOMinal:VOLTage",
    "VOLTage",
    "VOLTage:LIMit:HIGH",
    "VOLTage:LIMit:LOW",
    "VOLTage:PROTection",
)
