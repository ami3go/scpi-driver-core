"""Typed core driver for the Elektro-Automatik EA-PS 9000 T DC laboratory power supply.

Owns SCPI command construction and response parsing. The Robot Framework
adapter (``rf_ea_ps9000t/library.py``) is a thin layer on top of this
module and must not duplicate any of this logic (task §5). That adapter also
records every keyword call and every SCPI command/response as RFDS-008
structured evidence (``rf_ea_ps9000t/evidence.py``) by wrapping this module's
``Transport`` after ``connect_visa``/``connect_simulated`` return — nothing
in this module is aware of, or coupled to, that evidence layer.
"""

from __future__ import annotations

import logging
import re
import time

from .enums import (
    AlarmAction,
    AnalogRemsbAction,
    AnalogRemsbLevel,
    OutputRestoreMode,
    PowerStageAfterRemote,
    RemoteControlOwner,
)
from scpi_driver_core.exceptions import ResponseParseError
from scpi_driver_core.scpi import parse_csv, parse_optional_unit_float

from .exceptions import (
    EaPs9000TConnectionError,
    EaPs9000TDeviceError,
    EaPs9000TProtocolError,
    EaPs9000TValidationError,
)
from .models import (
    AdjustmentLimits,
    AlarmCounters,
    InstrumentIdentity,
    MeasuredValues,
    NominalRatings,
    ProtectionThresholds,
)
from .simulator import SimEaPs9000TInstrument
from .transport import PyvisaTransport, SimulatedTransport, Transport

logger = logging.getLogger(__name__)

_RAW_SCPI_CONFIRMATION = "ENABLE RAW SCPI"

_NUMBER_PATTERN = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _parse_number(response: str) -> str:
    """Extract the leading numeric token from a SCPI numeric response.

    Confirmed against real hardware: this instrument's firmware appends a
    trailing unit suffix to some numeric queries (e.g. ``SYSTem:NOMinal:
    VOLTage?`` replying ``"500.0 V"``) even though the bundled simulator and
    the programming guide's examples both show a bare number.

    Returns the token verbatim, because integer getters call ``int()`` on it
    and reformatting through a float would break them.
    """

    match = _NUMBER_PATTERN.search(response)
    if not match:
        raise EaPs9000TProtocolError(f"could not parse a number from response: {response!r}")
    return match.group(0)


def _parse_float(response: str) -> float:
    """Parse a numeric response that may carry a unit suffix.

    The core's ``parse_optional_unit_float`` exists for exactly this firmware
    behaviour — this driver is where it was found — and is stricter than the
    token search above: it requires the whole response to be a number with at
    most a unit suffix, rather than picking the first number out of arbitrary
    text. The fallback preserves this driver's historic leniency for replies
    that are neither.
    """

    try:
        return parse_optional_unit_float(response)
    except ResponseParseError:
        return float(_parse_number(response))


def _identity_parts(raw: str) -> list[str]:
    """Split an ``*IDN?`` reply into this instrument's five fields.

    Uses the core's CSV-aware split so a quoted comma inside the user-text
    field cannot be mistaken for a separator, then pads to five so callers keep
    their historic tolerance for short replies.
    """
    try:
        parts = parse_csv(raw)
    except ResponseParseError:
        parts = raw.strip().split(",", 4)
    if len(parts) > 5:
        parts = parts[:4] + [",".join(parts[4:])]
    return parts


class EaPs9000T:
    """A connected session with one EA-PS 9000 T instrument."""

    def __init__(self, transport: Transport) -> None:
        self.transport = transport
        self._identity: InstrumentIdentity | None = None
        self._raw_scpi_enabled = False

    # ------------------------------------------------------------------
    # Construction / lifecycle
    # ------------------------------------------------------------------
    @classmethod
    def connect_visa(cls, resource: str, timeout_s: float = 5.0) -> EaPs9000T:
        transport = PyvisaTransport(resource, timeout_s=timeout_s)
        transport.open()
        driver = cls(transport)
        driver.acquire_remote_control()
        return driver

    @classmethod
    def connect_simulated(cls, simulator: SimEaPs9000TInstrument | None = None) -> EaPs9000T:
        transport = SimulatedTransport(simulator)
        transport.open()
        driver = cls(transport)
        driver.acquire_remote_control()
        return driver

    def close(self) -> None:
        try:
            self.release_remote_control()
        except Exception:  # noqa: BLE001, S110 - best-effort: the transport is closing
            # regardless, and a real device that's already gone can't be released anyway.
            pass
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
            raise EaPs9000TConnectionError("not connected; call connect_visa/connect_simulated first")

    def _write(self, command: str) -> None:
        self._require_connected()
        self.transport.write(command)

    def _query(self, command: str) -> str:
        self._require_connected()
        return self.transport.query(command)

    def _check_events(self, context: str) -> None:
        """Raise if the instrument's SCPI error queue reports a problem after ``context``.

        Errors are never returned automatically on this instrument family
        (task §2) — they must be explicitly queried after every write that
        could plausibly fail, such as a set value that's outside the
        currently configured adjustment limits.
        """

        message = self._query("SYSTem:ERRor?").strip()
        if message.startswith("0,"):
            return
        raise EaPs9000TDeviceError(f"{context} failed: instrument reported an error: {message}")

    # ------------------------------------------------------------------
    # Remote control (task §6 items 1-2)
    # ------------------------------------------------------------------
    def acquire_remote_control(self) -> None:
        """Requests remote control and verifies the device actually granted it.

        The request can be refused (front panel in "Local" lock, already
        remote-controlled elsewhere, or the setup menu is open) and refusal
        surfaces as a SCPI error on the *next* command, not the lock request
        itself (task §2) — so this method explicitly re-queries
        ``SYSTem:LOCK:OWNer?`` after requesting the lock rather than trusting
        the write succeeded.

        Confirmed against real hardware: the front panel can already display
        "Remote: USB" while an immediate ``SYSTem:LOCK:OWNer?`` still reads
        back ``NONE`` — a brief state-propagation race between accepting the
        lock and updating what that query reports, not a genuine refusal.
        ``*OPC?`` (a mandatory IEEE-488.2 command every SCPI instrument
        supports) blocks until the lock request itself has actually
        completed, and a couple of short-interval re-checks absorb any
        remaining propagation delay beyond that — a genuine refusal (front
        panel truly in "Local", or already owned by another interface)
        stays refused across every attempt, so this doesn't weaken the
        never-trust-the-write guarantee above.
        """

        self._write("SYSTem:LOCK ON")
        self._query("*OPC?")
        owner = self.get_remote_control_owner()
        attempts = 1
        while owner != RemoteControlOwner.REMOTE and attempts < 3:
            time.sleep(0.15)
            owner = self.get_remote_control_owner()
            attempts += 1
        if owner != RemoteControlOwner.REMOTE:
            raise EaPs9000TConnectionError(
                f"remote control was refused; current owner is {owner.value!r} "
                "(check the front panel isn't in 'Local' lock condition, in the setup "
                "menu, or already remote-controlled via a different interface)"
            )

    def release_remote_control(self) -> None:
        self._write("SYSTem:LOCK OFF")

    def get_remote_control_owner(self) -> RemoteControlOwner:
        return RemoteControlOwner(self._query("SYSTem:LOCK:OWNer?").strip())

    # ------------------------------------------------------------------
    # Identity / communication (RFDS-002)
    # ------------------------------------------------------------------
    def identify(self, *, refresh: bool = True) -> InstrumentIdentity:
        if not refresh and self._identity is not None:
            return self._identity
        raw = self._query("*IDN?")
        # The core parses the conventional four fields; this instrument adds a
        # fifth user-text field, which stays a device-specific extension.
        parts = _identity_parts(raw)
        identity = InstrumentIdentity(
            manufacturer=parts[0].strip() if len(parts) > 0 else "",
            model=parts[1].strip() if len(parts) > 1 else "",
            serial=parts[2].strip() if len(parts) > 2 else "",
            firmware=parts[3].strip() if len(parts) > 3 else "",
            user_text=parts[4].strip() if len(parts) > 4 else "",
            raw=raw.strip(),
        )
        self._identity = identity
        return identity

    def check_communication(self) -> bool:
        self._query("*IDN?")
        return True

    # ------------------------------------------------------------------
    # Set values (task §8)
    # ------------------------------------------------------------------
    def set_voltage(self, value: float) -> None:
        self._write(f"VOLTage {float(value)}")
        self._check_events("Set Voltage")

    def get_voltage(self) -> float:
        return (_parse_float(self._query("VOLTage?")))

    def set_current(self, value: float) -> None:
        self._write(f"CURRent {float(value)}")
        self._check_events("Set Current")

    def get_current(self) -> float:
        return (_parse_float(self._query("CURRent?")))

    def set_power(self, value: float) -> None:
        self._write(f"POWer {float(value)}")
        self._check_events("Set Power")

    def get_power(self) -> float:
        return (_parse_float(self._query("POWer?")))

    # ------------------------------------------------------------------
    # Protection thresholds (task §8)
    # ------------------------------------------------------------------
    def set_overvoltage_protection(self, value: float) -> None:
        self._write(f"VOLTage:PROTection {float(value)}")
        self._check_events("Set Overvoltage Protection")

    def get_overvoltage_protection(self) -> float:
        return (_parse_float(self._query("VOLTage:PROTection?")))

    def set_overcurrent_protection(self, value: float) -> None:
        self._write(f"CURRent:PROTection {float(value)}")
        self._check_events("Set Overcurrent Protection")

    def get_overcurrent_protection(self) -> float:
        return (_parse_float(self._query("CURRent:PROTection?")))

    def set_overpower_protection(self, value: float) -> None:
        self._write(f"POWer:PROTection {float(value)}")
        self._check_events("Set Overpower Protection")

    def get_overpower_protection(self) -> float:
        return (_parse_float(self._query("POWer:PROTection?")))

    def get_protection_thresholds(self) -> ProtectionThresholds:
        return ProtectionThresholds(
            overvoltage=self.get_overvoltage_protection(),
            overcurrent=self.get_overcurrent_protection(),
            overpower=self.get_overpower_protection(),
        )

    # ------------------------------------------------------------------
    # Output control (task §8)
    # ------------------------------------------------------------------
    def enable_output(self) -> None:
        self._write("OUTPut ON")
        self._check_events("Enable Output")

    def disable_output(self) -> None:
        self._write("OUTPut OFF")
        self._check_events("Disable Output")

    def is_output_enabled(self) -> bool:
        return self._query("OUTPut?").strip() in ("1", "ON")

    # ------------------------------------------------------------------
    # Measuring (task §8)
    # ------------------------------------------------------------------
    def get_measured_voltage(self) -> float:
        return (_parse_float(self._query("MEASure:VOLTage?")))

    def get_measured_current(self) -> float:
        return (_parse_float(self._query("MEASure:CURRent?")))

    def get_measured_power(self) -> float:
        return (_parse_float(self._query("MEASure:POWer?")))

    def get_measured_values(self) -> MeasuredValues:
        raw = self._query("MEASure:ARRay?")
        parts = [p.strip() for p in raw.split(",")]
        values = [float(p.split()[0]) for p in parts]
        return MeasuredValues(voltage=values[0], current=values[1], power=values[2])

    # ------------------------------------------------------------------
    # General queries (task §8)
    # ------------------------------------------------------------------
    def get_nominal_ratings(self) -> NominalRatings:
        return NominalRatings(
            voltage=(_parse_float(self._query("SYSTem:NOMinal:VOLTage?"))),
            current=(_parse_float(self._query("SYSTem:NOMinal:CURRent?"))),
            power=(_parse_float(self._query("SYSTem:NOMinal:POWer?"))),
        )

    def get_device_class(self) -> str:
        return self._query("SYSTem:DEVice:CLASs?").strip()

    def get_alarm_counters(self) -> AlarmCounters:
        return AlarmCounters(
            overvoltage=int(_parse_number(self._query("SYSTem:ALARm:COUNt:OVOLtage?"))),
            overtemperature=int(_parse_number(self._query("SYSTem:ALARm:COUNt:OTEMperature?"))),
            overpower=int(_parse_number(self._query("SYSTem:ALARm:COUNt:OPOWer?"))),
            overcurrent=int(_parse_number(self._query("SYSTem:ALARm:COUNt:OCURrent?"))),
            power_fail=int(_parse_number(self._query("SYSTem:ALARm:COUNt:PFAil?"))),
        )

    # ------------------------------------------------------------------
    # Adjustment limits (task §9)
    # ------------------------------------------------------------------
    def set_voltage_limit_low(self, value: float) -> None:
        self._write(f"VOLTage:LIMit:LOW {float(value)}")
        self._check_events("Set Voltage Limit Low")

    def set_voltage_limit_high(self, value: float) -> None:
        self._write(f"VOLTage:LIMit:HIGH {float(value)}")
        self._check_events("Set Voltage Limit High")

    def get_voltage_limits(self) -> tuple[float, float]:
        return (
            (_parse_float(self._query("VOLTage:LIMit:LOW?"))),
            (_parse_float(self._query("VOLTage:LIMit:HIGH?"))),
        )

    def set_current_limit_low(self, value: float) -> None:
        self._write(f"CURRent:LIMit:LOW {float(value)}")
        self._check_events("Set Current Limit Low")

    def set_current_limit_high(self, value: float) -> None:
        self._write(f"CURRent:LIMit:HIGH {float(value)}")
        self._check_events("Set Current Limit High")

    def get_current_limits(self) -> tuple[float, float]:
        return (
            (_parse_float(self._query("CURRent:LIMit:LOW?"))),
            (_parse_float(self._query("CURRent:LIMit:HIGH?"))),
        )

    def set_power_limit_high(self, value: float) -> None:
        """No corresponding "low" limit exists on this instrument family (task §9)."""

        self._write(f"POWer:LIMit:HIGH {float(value)}")
        self._check_events("Set Power Limit High")

    def get_power_limit_high(self) -> float:
        return (_parse_float(self._query("POWer:LIMit:HIGH?")))

    def get_adjustment_limits(self) -> AdjustmentLimits:
        voltage_low, voltage_high = self.get_voltage_limits()
        current_low, current_high = self.get_current_limits()
        return AdjustmentLimits(
            voltage_low=voltage_low,
            voltage_high=voltage_high,
            current_low=current_low,
            current_high=current_high,
            power_high=self.get_power_limit_high(),
        )

    # ------------------------------------------------------------------
    # Device configuration (task §9, PST-applicable subset only)
    # ------------------------------------------------------------------
    def set_power_stage_after_remote(self, mode: PowerStageAfterRemote | str) -> None:
        mode = PowerStageAfterRemote(mode)
        self._write(f"POWer:STAGe:AFTer:REMote {mode.value}")
        self._check_events("Set Power Stage After Remote")

    def get_power_stage_after_remote(self) -> PowerStageAfterRemote:
        return PowerStageAfterRemote(self._query("POWer:STAGe:AFTer:REMote?").strip())

    def set_output_restore_mode(self, mode: OutputRestoreMode | str) -> None:
        mode = OutputRestoreMode(mode)
        self._write(f"SYSTem:CONFig:OUTPut:RESTore {mode.value}")
        self._check_events("Set Output Restore Mode")

    def get_output_restore_mode(self) -> OutputRestoreMode:
        return OutputRestoreMode(self._query("SYSTem:CONFig:OUTPut:RESTore?").strip())

    def set_user_text(self, text: str) -> None:
        if len(text) > 40:
            raise EaPs9000TValidationError("user text must be 40 characters or fewer")
        self._write(f'SYSTem:CONFig:USER:TEXT "{text}"')
        self._check_events("Set User Text")

    def get_user_text(self) -> str:
        return self._query("SYSTem:CONFig:USER:TEXT?").strip().strip('"')

    def set_communication_timeout(self, milliseconds: int) -> None:
        """Serial interfaces only (USB, RS232) — not meaningful over Ethernet (task §9);
        this driver does not client-side-gate on interface type since it has no
        reliable way to know which transport is active at the SCPI layer."""

        if not (5 <= int(milliseconds) <= 65535):
            raise EaPs9000TValidationError("communication timeout must be between 5 and 65535 ms")
        self._write(f"SYSTem:COMMunicate:TIMeout {int(milliseconds)}")
        self._check_events("Set Communication Timeout")

    def get_communication_timeout(self) -> int:
        return int(_parse_number(self._query("SYSTem:COMMunicate:TIMeout?")))

    def set_power_fail_alarm_action(self, action: AlarmAction | str) -> None:
        action = AlarmAction(action)
        self._write(f"SYSTem:ALARm:ACTion:PFail {action.value}")
        self._check_events("Set Power Fail Alarm Action")

    def get_power_fail_alarm_action(self) -> AlarmAction:
        return AlarmAction(self._query("SYSTem:ALARm:ACTion:PFail?").strip())

    def set_overtemperature_alarm_action(self, action: AlarmAction | str) -> None:
        action = AlarmAction(action)
        self._write(f"SYSTem:ALARm:ACTion:OTEMperature {action.value}")
        self._check_events("Set Overtemperature Alarm Action")

    def get_overtemperature_alarm_action(self) -> AlarmAction:
        return AlarmAction(self._query("SYSTem:ALARm:ACTion:OTEMperature?").strip())

    # ------------------------------------------------------------------
    # LAN configuration (Gate 3 extension — SYSTem:COMMunicate:LAN:*)
    # ------------------------------------------------------------------
    # Confirmed against the EA/Intepro "Programming Guide ModBus & SCPI" (Doc ID
    # PGMBEN, Rev. 17), pages 57-60 — universal across the whole device family in
    # the source document, no per-series exclusion found for PST. These are
    # ordinary device-configuration commands (like the Gate 2 device-configuration
    # keywords above), so no special safety guard is applied here beyond the
    # instrument's own universal remote-control gating.
    #
    # SYSTem:COMMunicate:LAN:1SPEed / :2SPEed (Anybus/IF-AB Ethernet module speed
    # selection) and SYSTem:COMMunicate:LAN:INDex (10000-series dual-Ethernet-port
    # selector) are deliberately NOT implemented: the PST series this driver
    # targets has a single, fixed, built-in Ethernet port — not an optional
    # multi-port Anybus/IF-AB interface module — so all three commands describe
    # hardware this driver's instrument family doesn't have (judgment call, see
    # README.md).
    def set_lan_dhcp_enabled(self, enabled: bool) -> None:
        self._write(f"SYSTem:COMMunicate:LAN:DHCP {'ON' if enabled else 'OFF'}")
        self._check_events("Set LAN DHCP Enabled")

    def get_lan_dhcp_enabled(self) -> bool:
        return self._query("SYSTem:COMMunicate:LAN:DHCP?").strip().upper() in ("1", "ON")

    def set_lan_ip_address(self, address: str) -> None:
        self._write(f'SYSTem:COMMunicate:LAN:ADDRess "{address}"')
        self._check_events("Set LAN IP Address")

    def get_lan_ip_address(self) -> str:
        return self._query("SYSTem:COMMunicate:LAN:ADDRess?").strip().strip('"')

    def set_lan_subnet_mask(self, mask: str) -> None:
        self._write(f'SYSTem:COMMunicate:LAN:SMASk "{mask}"')
        self._check_events("Set LAN Subnet Mask")

    def get_lan_subnet_mask(self) -> str:
        return self._query("SYSTem:COMMunicate:LAN:SMASk?").strip().strip('"')

    def set_lan_gateway(self, gateway: str) -> None:
        self._write(f'SYSTem:COMMunicate:LAN:GATeway "{gateway}"')
        self._check_events("Set LAN Gateway")

    def get_lan_gateway(self) -> str:
        return self._query("SYSTem:COMMunicate:LAN:GATeway?").strip().strip('"')

    def set_lan_hostname(self, hostname: str) -> None:
        if len(hostname) > 54:
            raise EaPs9000TValidationError("LAN hostname must be 54 characters or fewer")
        self._write(f'SYSTem:COMMunicate:LAN:HOSTname "{hostname}"')
        self._check_events("Set LAN Hostname")

    def get_lan_hostname(self) -> str:
        return self._query("SYSTem:COMMunicate:LAN:HOSTname?").strip().strip('"')

    def set_lan_domain(self, domain: str) -> None:
        if len(domain) > 54:
            raise EaPs9000TValidationError("LAN domain must be 54 characters or fewer")
        self._write(f'SYSTem:COMMunicate:LAN:DOMain "{domain}"')
        self._check_events("Set LAN Domain")

    def get_lan_domain(self) -> str:
        return self._query("SYSTem:COMMunicate:LAN:DOMain?").strip().strip('"')

    def set_lan_dns1(self, address: str) -> None:
        self._write(f'SYSTem:COMMunicate:LAN:DNS1 "{address}"')
        self._check_events("Set LAN DNS1")

    def get_lan_dns1(self) -> str:
        return self._query("SYSTem:COMMunicate:LAN:DNS1?").strip().strip('"')

    def set_lan_dns2(self, address: str) -> None:
        """Anybus modules only per the source document; this driver does not
        client-side-gate on module presence since it has no reliable way to know
        which interface module is fitted at the SCPI layer (same reasoning as
        ``set_communication_timeout``)."""

        self._write(f'SYSTem:COMMunicate:LAN:DNS2 "{address}"')
        self._check_events("Set LAN DNS2")

    def get_lan_dns2(self) -> str:
        return self._query("SYSTem:COMMunicate:LAN:DNS2?").strip().strip('"')

    def set_lan_control_port(self, port: int) -> None:
        port = int(port)
        if not (0 <= port <= 65535):
            raise EaPs9000TValidationError("LAN control port must be between 0 and 65535")
        if port == 502:
            raise EaPs9000TValidationError(
                "LAN control port 502 is reserved for ModBus TCP and illegal to set here"
            )
        self._write(f"SYSTem:COMMunicate:LAN:CONTrol {port}")
        self._check_events("Set LAN Control Port")

    def get_lan_control_port(self) -> int:
        return int(_parse_number(self._query("SYSTem:COMMunicate:LAN:CONTrol?")))

    def set_lan_keepalive_enabled(self, enabled: bool) -> None:
        self._write(f"SYSTem:COMMunicate:LAN:KEEPalive {'ON' if enabled else 'OFF'}")
        self._check_events("Set LAN Keepalive Enabled")

    def get_lan_keepalive_enabled(self) -> bool:
        return self._query("SYSTem:COMMunicate:LAN:KEEPalive?").strip().upper() in ("1", "ON")

    def set_lan_timeout(self, seconds: int) -> None:
        seconds = int(seconds)
        if seconds != 0 and not (5 <= seconds <= 65535):
            raise EaPs9000TValidationError(
                "LAN timeout must be 0 (disabled) or between 5 and 65535 seconds"
            )
        self._write(f"SYSTem:COMMunicate:LAN:TIMeout {seconds}")
        self._check_events("Set LAN Timeout")

    def get_lan_timeout(self) -> int:
        return int(_parse_number(self._query("SYSTem:COMMunicate:LAN:TIMeout?")))

    def get_lan_mac_address(self) -> str:
        """Read-only — when the interface is physically present."""

        return self._query("SYSTem:COMMunicate:LAN:MAC?").strip().strip('"')

    # ------------------------------------------------------------------
    # Analog interface configuration (Gate 3 extension — SYSTem:CONFig:ANAlog:*)
    # ------------------------------------------------------------------
    # Confirmed present for PST specifically, from the same source document
    # (task §2). Ordinary device-configuration commands, same treatment as the
    # LAN configuration commands above: no special safety guard beyond the
    # instrument's universal remote-control gating.
    def set_analog_reference_range(self, range_v: int) -> None:
        range_v = int(range_v)
        if range_v not in (5, 10):
            raise EaPs9000TValidationError("analog reference range must be 5 or 10 (volts)")
        self._write(f"SYSTem:CONFig:ANAlog:REFerence {range_v}")
        self._check_events("Set Analog Reference Range")

    def get_analog_reference_range(self) -> int:
        return int((_parse_float(self._query("SYSTem:CONFig:ANAlog:REFerence?"))))

    def set_analog_remsb_level(self, level: AnalogRemsbLevel | str) -> None:
        level = AnalogRemsbLevel(level)
        self._write(f"SYSTem:CONFig:ANAlog:REMSB:LEVel {level.value}")
        self._check_events("Set Analog REM-SB Level")

    def get_analog_remsb_level(self) -> AnalogRemsbLevel:
        return AnalogRemsbLevel(self._query("SYSTem:CONFig:ANAlog:REMSB:LEVel?").strip())

    def set_analog_remsb_action(self, action: AnalogRemsbAction | str) -> None:
        action = AnalogRemsbAction(action)
        self._write(f"SYSTem:CONFig:ANAlog:REMSB:ACTion {action.value}")
        self._check_events("Set Analog REM-SB Action")

    def get_analog_remsb_action(self) -> AnalogRemsbAction:
        return AnalogRemsbAction(self._query("SYSTem:CONFig:ANAlog:REMSB:ACTion?").strip())

    # ------------------------------------------------------------------
    # Raw SCPI escape hatch (task §10)
    # ------------------------------------------------------------------
    def enable_raw_scpi(self, confirmation: str) -> None:
        if confirmation != _RAW_SCPI_CONFIRMATION:
            raise EaPs9000TValidationError(
                f'raw SCPI requires the exact confirmation text "{_RAW_SCPI_CONFIRMATION}"'
            )
        self._raw_scpi_enabled = True

    def _require_raw_scpi_enabled(self) -> None:
        if not self._raw_scpi_enabled:
            raise EaPs9000TValidationError(
                "raw SCPI is disabled; call enable_raw_scpi() with the exact confirmation text first"
            )

    def raw_query(self, command: str) -> str:
        self._require_raw_scpi_enabled()
        return self._query(command)

    def raw_write(self, command: str) -> None:
        self._require_raw_scpi_enabled()
        self._write(command)
