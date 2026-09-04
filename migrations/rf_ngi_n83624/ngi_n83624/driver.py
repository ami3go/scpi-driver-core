"""Main NGI N83624 cell simulator driver."""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from typing import Any

from .exceptions import (
    CommunicationError,
    HeartbeatError,
    ProtocolError,
    RecoveryError,
    SafetyError,
    SessionStateError,
    TimeoutError,
)
from .logging_utils import get_logger
from .models import (
    BenchInterlock,
    CaptureRate,
    CommunicationObservation,
    DriverSafetyPolicy,
    HeartbeatConfig,
    InstrumentLimits,
    LanConnectionType,
    Language,
    NullBenchInterlock,
    ReconnectPolicy,
    RetryPolicy,
    SessionState,
)
from .parsing import parse_bool, parse_csv_floats, parse_int
from .safety import (
    validate_capture_rate,
    validate_channels,
    validate_ip_address,
    validate_lan_connection_type,
    validate_language,
    validate_serial_baudrate,
)
from .transports import SerialTransport, TcpTransport, Transport, UdpTransport, udp_channel

logger = get_logger("driver")


class N83624CellSimulator:
    """Unified public driver class for NGI N83624 instruments.

    The class exposes both high-level typed methods and a raw SCPI escape hatch via
    :meth:`write` and :meth:`query`. Raw SCPI methods bypass high-level validation
    and are intended only for advanced diagnostics or commands not yet represented
    by the typed API.
    """

    def __init__(
        self,
        transport: Transport,
        *,
        limits: InstrumentLimits | None = None,
        safety_policy: DriverSafetyPolicy | None = None,
        bench_interlock: BenchInterlock | None = None,
        retry_policy: RetryPolicy | None = None,
        reconnect_policy: ReconnectPolicy | None = None,
    ) -> None:
        self.transport = transport
        self.limits = limits or InstrumentLimits()
        self.safety_policy = safety_policy or DriverSafetyPolicy()
        self.bench_interlock = bench_interlock or NullBenchInterlock()
        self.retry_policy = retry_policy or RetryPolicy()
        self.reconnect_policy = reconnect_policy or ReconnectPolicy()
        self.state = SessionState.DISCONNECTED
        self.idn: str | None = None
        self._lock = threading.RLock()
        self._heartbeat_thread: threading.Thread | None = None
        self._heartbeat_stop = threading.Event()
        self._communication_observation = CommunicationObservation()
        #: Optional ``(direction, text)`` callback, ``direction`` one of
        #: ``"outbound"``/``"inbound"``, invoked for every SCPI write/query this
        #: instance performs. Lets a framework-layer caller (e.g. the Robot
        #: Framework adapter's RFDS-008 evidence engine) observe the wire
        #: protocol without this core driver knowing anything about evidence,
        #: Robot Framework, or logging policy — it just calls the hook if set.
        #: Exceptions raised by the observer propagate normally; it is not
        #: wrapped in a try/except so a broken observer fails loudly.
        self.protocol_observer: Callable[[str, str], None] | None = None

    @classmethod
    def tcp(
        cls,
        host: str = "192.168.0.123",
        port: int = 7000,
        timeout: float = 3.0,
        **kwargs: Any,
    ) -> "N83624CellSimulator":
        """Create a simulator using TCP transport."""
        return cls(TcpTransport(host=host, port=port, timeout=timeout), **kwargs)

    @classmethod
    def udp(
        cls,
        host: str = "192.168.0.123",
        port: int = 7000,
        timeout: float = 3.0,
        **kwargs: Any,
    ) -> "N83624CellSimulator":
        """Create a simulator using UDP transport.

        Port 7000 supports the multi-channel API. Ports 7001..7024 are treated as
        channel-specific and the high-level :meth:`channel` method only allows that
        matching channel.
        """
        return cls(UdpTransport(host=host, port=port, timeout=timeout), **kwargs)

    @classmethod
    def udp_channel(
        cls,
        host: str,
        channel: int,
        timeout: float = 3.0,
        **kwargs: Any,
    ) -> "N83624CellSimulator":
        """Create a simulator using the UDP port dedicated to one channel."""
        return cls(udp_channel(host, channel, timeout=timeout), **kwargs)

    @classmethod
    def serial(
        cls,
        port: str,
        baudrate: int = 115200,
        timeout: float = 3.0,
        **kwargs: Any,
    ) -> "N83624CellSimulator":
        """Create a simulator using RS232 serial transport."""
        return cls(SerialTransport(port=port, baudrate=baudrate, timeout=timeout), **kwargs)

    def connect(self) -> None:
        """Open the transport and verify identity when policy requires it."""
        with self._lock:
            if self.state == SessionState.READY and self.transport.is_open():
                return
            self.state = SessionState.CONNECTING
            try:
                self.transport.open()
                self.state = SessionState.CONNECTED_UNVERIFIED
                if self.safety_policy.require_identity_check_on_connect:
                    self.idn = self.identify()
                self.state = SessionState.READY
                self._communication_observation = CommunicationObservation.success(self._communication_observation)
            except Exception as exc:
                self.state = SessionState.FAULTED
                self._communication_observation = CommunicationObservation.failure(exc, self._communication_observation)
                raise

    def close(self) -> None:
        """Close the session.

        Heartbeat shutdown happens before the instrument lock is acquired so a
        heartbeat query waiting for the same lock cannot delay close. When
        ``output_off_on_close`` is enabled, all channels are attempted even if one
        channel fails; the transport is always closed and the aggregated failure is
        raised afterwards.
        """
        error: BaseException | None = None
        self.stop_heartbeat()
        with self._lock:
            if self.safety_policy.output_off_on_close and self.transport.is_open():
                try:
                    self.all_outputs_off()
                except BaseException as exc:  # best-effort shutdown must still close transport
                    error = exc
                    logger.exception("Best-effort output-off on close failed")
            try:
                self.transport.close()
            except BaseException as exc:
                error = error or exc
            self.state = SessionState.SHUTDOWN
        if error is not None:
            raise error

    def __enter__(self) -> "N83624CellSimulator":
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if exc is not None and self.safety_policy.output_off_on_exception:
            with contextlib.suppress(Exception):
                self.all_outputs_off()
        self.close()

    @contextlib.contextmanager
    def locked_operation(self) -> Iterator[None]:
        """Hold the instrument lock for a full compound operation.

        High-level safety-critical operations use this context so no other thread can
        interleave commands between setter and verification queries or during fault
        relay settle loops.
        """
        with self._lock:
            yield

    def channel(self, channel: int):
        """Return a channel proxy object."""
        from .channel import N83624Channel
        from .safety import validate_channel

        validate_channel(channel)
        single_channel = getattr(self.transport, "single_channel", None)
        if single_channel is not None and single_channel != channel:
            raise SafetyError(
                f"This UDP transport is bound to channel {single_channel}; cannot access channel {channel}"
            )
        return N83624Channel(self, channel)

    def all_outputs_off(self) -> None:
        """Attempt to switch all 24 outputs off.

        A failure on one channel does not prevent shutdown commands from being sent
        to the remaining channels. After all attempts, a ``SafetyError`` summarizes
        failed channels so callers can preserve the evidence while knowing the
        shutdown state may be uncertain.
        """
        failures: list[str] = []
        with self.locked_operation():
            for channel in range(1, 25):
                try:
                    self.channel(channel).output_off()
                except BaseException as exc:
                    failures.append(f"CH{channel}: {type(exc).__name__}: {exc}")
                    logger.exception("Failed to switch N83624 channel %s output off", channel)
        if failures:
            raise SafetyError("One or more N83624 outputs could not be disabled: " + "; ".join(failures))

    def write(self, command: str) -> None:
        """Send a raw SCPI command.

        This is an advanced escape hatch. It validates only that the command is a
        non-empty ASCII-compatible string; high-level safety checks are bypassed.
        """
        self._ensure_connected()
        if not isinstance(command, str) or not command.strip():
            raise ProtocolError("SCPI command must be a non-empty string")
        with self._lock:
            logger.debug("SCPI write: %s", command)
            if self.protocol_observer:
                self.protocol_observer("outbound", command)
            try:
                self.transport.write(command)
                self._communication_observation = CommunicationObservation.success(self._communication_observation)
            except Exception as exc:
                self._communication_observation = CommunicationObservation.failure(exc, self._communication_observation)
                raise

    def query(self, command: str) -> str:
        """Send a raw SCPI query and return a stripped response string."""
        self._ensure_connected()
        if not isinstance(command, str) or not command.strip():
            raise ProtocolError("SCPI query must be a non-empty string")
        with self._lock:
            return self._query_locked(command)

    def _query_locked(self, command: str) -> str:
        attempts = max(1, self.retry_policy.retries + 1)
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                logger.debug("SCPI query: %s", command)
                if self.protocol_observer:
                    self.protocol_observer("outbound", command)
                response = self.transport.query(command).strip()
                logger.debug("SCPI response to %s: %s", command, response)
                if self.protocol_observer:
                    self.protocol_observer("inbound", response)
                self._communication_observation = CommunicationObservation.success(self._communication_observation)
                return response
            except (CommunicationError, TimeoutError) as exc:
                last_error = exc
                self._communication_observation = CommunicationObservation.failure(exc, self._communication_observation)
                if attempt < attempts - 1:
                    time.sleep(self.retry_policy.delay_s)
        assert last_error is not None
        raise last_error

    def _write_locked(self, command: str) -> None:
        logger.debug("SCPI write: %s", command)
        if self.protocol_observer:
            self.protocol_observer("outbound", command)
        try:
            self.transport.write(command)
            self._communication_observation = CommunicationObservation.success(self._communication_observation)
        except Exception as exc:
            self._communication_observation = CommunicationObservation.failure(exc, self._communication_observation)
            raise

    def _ensure_connected(self) -> None:
        if not self.transport.is_open() or self.state not in {
            SessionState.READY,
            SessionState.CONNECTED_UNVERIFIED,
            SessionState.RECOVERING,
        }:
            raise SessionStateError(f"Instrument is not connected/ready; state={self.state.value}")

    def identify(self) -> str:
        """Query ``*IDN?``."""
        with self._lock:
            response = self._query_locked("*IDN?")
            self.idn = response
            return response

    def opc(self) -> int:
        """Query operation complete using ``*OPC?``."""
        return parse_int(self.query("*OPC?"), command="*OPC?")

    def wait_operation_complete(self, timeout: float | None = None) -> bool:
        """Poll ``*OPC?`` until it returns 1 or timeout expires."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            if self.opc() == 1:
                return True
            if deadline is not None and time.monotonic() > deadline:
                return False
            time.sleep(0.05)

    def factory_reset(self, confirm: bool = False) -> None:
        """Restore factory settings using ``*RST``.

        This is destructive: it can reset IP address, serial baud rate, protection
        settings, SOC/SEQ files, and other persistent parameters.
        """
        if not confirm:
            raise SafetyError("factory_reset() requires confirm=True")
        with self.locked_operation():
            self._write_locked("*RST")
            time.sleep(10.0)
            self.state = SessionState.CONNECTED_UNVERIFIED
            if self.safety_policy.require_identity_check_on_connect:
                self.idn = self.identify()
                self.state = SessionState.READY

    def clear_status(self, *, experimental_ok: bool = False) -> None:
        """Send undocumented ``*CLS`` only when explicitly allowed."""
        if not experimental_ok:
            raise NotImplementedError("*CLS is not documented in the N83624 programming guide")
        self.write("*CLS")

    def read_standard_event_status(self, *, experimental_ok: bool = False) -> int:
        """Query undocumented ``*ESR?`` only when explicitly allowed."""
        if not experimental_ok:
            raise NotImplementedError("*ESR? is not documented in the N83624 programming guide")
        return parse_int(self.query("*ESR?"), command="*ESR?")

    def read_status_byte(self, *, experimental_ok: bool = False) -> int:
        """Query undocumented ``*STB?`` only when explicitly allowed."""
        if not experimental_ok:
            raise NotImplementedError("*STB? is not documented in the N83624 programming guide")
        return parse_int(self.query("*STB?"), command="*STB?")

    def measure_voltage_channels(self, channels: Sequence[int]) -> dict[int, float]:
        return self._measure_channels("VOLTage", channels)

    def measure_current_channels(self, channels: Sequence[int]) -> dict[int, float]:
        return self._measure_channels("CURRent", channels)

    def measure_power_channels(self, channels: Sequence[int]) -> dict[int, float]:
        return self._measure_channels("POWer", channels)

    def _measure_channels(self, quantity: str, channels: Sequence[int]) -> dict[int, float]:
        channels = validate_channels(channels)
        command = "MEASure:" + quantity + "?(@" + ",".join(str(ch) for ch in channels) + ")"
        values = parse_csv_floats(self.query(command), command=command)
        if len(values) != len(channels):
            raise ProtocolError(
                f"Expected {len(channels)} values for {command!r}, got {len(values)}: {values!r}"
            )
        return dict(zip(channels, values, strict=True))

    def set_global_capture_rate(self, rate: CaptureRate | int, *, experimental_ok: bool = False) -> None:
        if not experimental_ok:
            raise NotImplementedError("MEASure0:CAPRate global behavior requires hardware verification")
        rate = validate_capture_rate(rate)
        self.write(f"MEASure0:CAPRate {int(rate)}")

    def get_global_capture_rate(self, *, experimental_ok: bool = False) -> CaptureRate:
        if not experimental_ok:
            raise NotImplementedError("MEASure0:CAPRate? global behavior requires hardware verification")
        value = parse_int(self.query("MEASure0:CAPRate?"), command="MEASure0:CAPRate?")
        return validate_capture_rate(value)

    def set_ip_address(self, ip: str, *, confirm: bool = False) -> None:
        ip = validate_ip_address(ip)
        self._require_dangerous_confirmation(confirm, "Changing IP address can break communication")
        with self.locked_operation():
            self._write_locked(f'SYSTem1:COMMand:LAN:IPADdr "{ip}"')
            self.state = SessionState.CONNECTED_UNVERIFIED

    def get_ip_address(self) -> str:
        return self.query("SYSTem1:COMMand:LAN:IPADdr?").strip().strip('"')

    def set_serial_baudrate(self, baudrate: int, *, confirm: bool = False) -> None:
        baudrate = validate_serial_baudrate(baudrate)
        self._require_dangerous_confirmation(confirm, "Changing serial baudrate can break communication")
        with self.locked_operation():
            self._write_locked(f"SYSTem1:COMMand:SERial:BAUDrate {baudrate}")
            self.state = SessionState.CONNECTED_UNVERIFIED

    def get_serial_baudrate(self) -> int:
        return parse_int(self.query("SYSTem1:COMMand:SERial:BAUDrate?"), command="SYSTem1:COMMand:SERial:BAUDrate?")

    def set_beeper(self, enabled: bool) -> None:
        self.write(f"SYSTem1:SOUNd {1 if enabled else 0}")

    def get_beeper(self) -> bool:
        return parse_bool(self.query("SYSTem1:SOUNd?"), command="SYSTem1:SOUNd?")

    def set_language(self, language: Language | int) -> None:
        language = validate_language(language)
        self.write(f"SYSTem1:LANGuage {int(language)}")

    def get_language(self) -> Language:
        value = parse_int(self.query("SYSTem1:LANGuage?"), command="SYSTem1:LANGuage?")
        return validate_language(value)

    def set_lan_connection_type(self, connection_type: LanConnectionType | int, *, confirm: bool = False) -> None:
        connection_type = validate_lan_connection_type(connection_type)
        self._require_dangerous_confirmation(confirm, "Changing LAN type can break communication")
        with self.locked_operation():
            self._write_locked(f"SYSTem1:COMMand:LAN:TYPe {int(connection_type)}")
            self.state = SessionState.CONNECTED_UNVERIFIED

    def get_lan_connection_type(self) -> LanConnectionType:
        value = parse_int(self.query("SYSTem1:COMMand:LAN:TYPe?"), command="SYSTem1:COMMand:LAN:TYPe?")
        return validate_lan_connection_type(value)

    def set_powerdown_save(self, enabled: bool, *, confirm: bool = False) -> None:
        self._require_dangerous_confirmation(confirm, "Changing power-down save affects persistent behavior")
        self.write(f"SYSTem1:POWDown:SAVe {1 if enabled else 0}")

    def get_powerdown_save(self) -> bool:
        return parse_bool(self.query("SYSTem1:POWDown:SAVe?"), command="SYSTem1:POWDown:SAVe?")

    def set_hmi_disconnect_enabled(self, enabled: bool) -> None:
        self.write(f"HMI:DISConnect:ENABle {1 if enabled else 0}")

    def get_hmi_disconnect_enabled(self) -> bool:
        return parse_bool(self.query("HMI:DISConnect:ENABle?"), command="HMI:DISConnect:ENABle?")

    def _require_dangerous_confirmation(self, confirm: bool, reason: str) -> None:
        if self.safety_policy.dangerous_system_write_requires_confirmation and not confirm:
            raise SafetyError(f"{reason}; pass confirm=True to proceed")

    def start_heartbeat(self, config: HeartbeatConfig | None = None) -> None:
        """Start a background heartbeat watchdog."""
        config = config or HeartbeatConfig()
        with self._lock:
            if self._heartbeat_thread and self._heartbeat_thread.is_alive():
                return
            self._heartbeat_stop.clear()
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop,
                args=(config,),
                name="N83624Heartbeat",
                daemon=True,
            )
            self._heartbeat_thread.start()

    def stop_heartbeat(self) -> None:
        """Stop the background heartbeat watchdog."""
        thread = self._heartbeat_thread
        if thread is None:
            return
        self._heartbeat_stop.set()
        if thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._heartbeat_thread = None

    def get_communication_observation(self) -> CommunicationObservation:
        """Return last known communication health information."""
        return self._communication_observation

    def _heartbeat_loop(self, config: HeartbeatConfig) -> None:
        while not self._heartbeat_stop.wait(config.interval_s):
            try:
                self.query(config.query)
            except Exception as exc:
                logger.warning("N83624 heartbeat failed: %s", exc)
                if self._communication_observation.consecutive_failures >= config.fail_after:
                    self.state = SessionState.FAULTED
                    logger.error("N83624 heartbeat failure threshold reached")
                    # Background thread cannot raise to caller; state/observation expose it.

    def recover(self) -> None:
        """Attempt reconnect according to :class:`ReconnectPolicy`."""
        if not self.reconnect_policy.enabled:
            raise RecoveryError("Reconnect policy is disabled")
        with self.locked_operation():
            self.state = SessionState.RECOVERING
            last_error: Exception | None = None
            for attempt in range(self.reconnect_policy.max_attempts):
                try:
                    self.transport.close()
                    time.sleep(self.reconnect_policy.delay_s if attempt else 0)
                    self.transport.open()
                    self.state = SessionState.CONNECTED_UNVERIFIED
                    if self.reconnect_policy.resync_after_reconnect:
                        self.idn = self.identify()
                    self.state = SessionState.READY
                    return
                except Exception as exc:
                    last_error = exc
                    self._communication_observation = CommunicationObservation.failure(exc, self._communication_observation)
            self.state = SessionState.FAULTED
            raise RecoveryError(f"Failed to recover N83624 session: {last_error}")

    def _raise_heartbeat_if_failed(self) -> None:
        obs = self._communication_observation
        if obs.last_error:
            raise HeartbeatError(obs.last_error)
