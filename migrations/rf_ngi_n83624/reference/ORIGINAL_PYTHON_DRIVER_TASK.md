# AI Code Generation Task: Production-Ready Python Driver for NGI N83624 Cell Simulator

**Specification revision:** v1.2 — academic-review remediation revision  
**Revision purpose:** incorporate production-assurance findings plus the independent academic review remediation items: API clarification, UDP channel-port semantics, compound-operation locking, explicit transport protocol design, test decomposition, documentation toolchain, packaging metadata, and validation/detail fixes.

**Source document:** NGI N83624 Series Programming Guide — SCPI Protocol, Version V20240130  
**Target output:** Production-ready Python driver package for the NGI N83624 battery/cell simulator.

## Revision v1.1 Summary of Fixes

This revision fixes all review findings from the technical/academic assessment:

- Makes model-specific electrical limits mandatory before any output can be enabled.
- Adds a formal session state machine for disconnects, reconnects, reboot recovery, and faulted states.
- Adds heartbeat/watchdog supervision for unattended 24/7 operation.
- Adds a bench interlock interface for emergency stop, DUT contactor, chamber state, BMS state, and external output-permission logic.
- Adds explicit behavior for communication loss while output may be ON.
- Adds protocol-robustness requirements for TCP, UDP, and serial edge cases.
- Adds long-duration soak tests, fault-injection tests, reconnect tests, power-cycle tests, and memory-leak tests.
- Adds requirements traceability matrix and verification/validation deliverables.
- Fixes the `set_mode()` API so it includes `verify: bool = True`.
- Fixes the `MEASure<n>:CAPRate` channel-zero ambiguity by requiring explicit handling of `n=0`.
- Adds confirmation requirements for dangerous persistent system settings such as IP address, LAN type, baud rate, and power-down save.
- Defines `read_channel_configuration()` and the missing `ChannelConfiguration` dataclass.
- Adds residual-risk documentation for manual ambiguities and hardware behaviors that must be verified on a real instrument.

## Revision v1.2 Summary of Additional Fixes

This revision additionally fixes the independent academic review findings:

- Clarifies that `N83624CellSimulator` is one unified public class; low-level `write()` and `query()` are raw-SCPI escape hatches, not a separate class layer.
- Defines `Transport` as a `typing.Protocol` with structural subtyping for third-party transports.
- Clarifies UDP port semantics: port `7000` supports the normal multi-channel API; ports `7001–7024` are channel-bound and must reject mismatched channel access unless explicitly overridden for verified hardware behavior.
- Requires the instrument lock to cover entire compound operations, including write-verify sequences, mode-configuration sequences, reconnect/state-resync, heartbeat transitions, and fault-simulation settle loops.
- Defines `configure_soc(file_number=None)` behavior.
- Defines `Measurement` `None` semantics.
- Adds `OUTPut<n>:ONDWell` validation and enumerates parameters where negative values are explicitly allowed.
- Adds a capacitive-DUT residual-voltage safety warning for fault simulation.
- Adds property-based testing with Hypothesis for boundary validation.
- Adds explicit command-order verification using recording fake transports.
- Adds workflow-level integration tests.
- Adds documentation-generation requirements using MkDocs + mkdocstrings or Sphinx autodoc.
- Adds `pyproject.toml` metadata, dependency groups, classifiers, semantic versioning, and CI expectations.
- Requires evaluation, not blind implementation, of additional IEEE 488.2 common commands such as `*CLS`, `*ESR?`, and `*STB?`.

---

---

## 1. Project Goal

Generate a production-ready Python driver package for the **NGI N83624 Series battery/cell simulator** using the vendor SCPI programming guide **“N83624 Series Programming Guide — SCPI Protocol, V20240130.”**

The driver shall provide a safe, typed, documented, testable Python API for controlling all major N83624 functions over **LAN TCP**, **LAN UDP**, and **RS232 serial**. It shall support up to **24 independent simulator channels**, with both low-level SCPI access and high-level convenience methods for real test automation.

The driver is intended for industrial test benches where the cell simulator may be connected to a DUT, BMS, data acquisition system, thermal chamber, power supplies, electronic loads, and automated test software. The implementation must prioritize safety, predictable behavior, clear error reporting, and maintainability.

### 1.1 Suggested Generation Milestones

Because this specification is long and safety-sensitive, an AI code-generation agent should implement it in milestones rather than trying to generate the full package in one monolithic pass. Each milestone must produce code, tests, and a short self-review before the next milestone begins.

Recommended milestones:

1. **Core skeleton:** package layout, `pyproject.toml`, exceptions, enums, dataclasses, parsing utilities, and basic README.
2. **Transports:** `Transport` protocol, TCP, UDP, serial, fake transport, terminator handling, timeout/error wrapping, and transport tests.
3. **Low-level instrument class:** unified `N83624CellSimulator`, raw `write()`/`query()`, context manager, locking, logging, identify/opc/reset behavior.
4. **Channel API:** measurement, output, source, charge, SOC, SEQ, protection, CAN, HMI, system commands.
5. **Safety and production layer:** limits, interlocks, session state machine, heartbeat, reconnect, fault simulation, and safe shutdown.
6. **Verification layer:** protocol emulator, property-based tests, integration-test gates, soak tests, traceability matrix, and documentation.
7. **Final hardening:** type checking, linting, coverage, API docs, examples, changelog, residual-risk review, and acceptance-criteria checklist.

The generated code must not skip earlier milestone tests when implementing later milestones.

---


## Software Architecture Map Requirement

The generated repository documentation must include a software architecture map in the README and in `docs/software_architecture.md`.
The map must show the layered structure:

```text
User/test scripts
  -> N83624CellSimulator unified public API
  -> N83624Channel per-channel API
  -> safety and validation layer
  -> full-duration compound-operation lock
  -> domain command layer
  -> SCPI formatting/parsing/error mapping
  -> transport abstraction
  -> TCP / UDP / RS232 / fake transport
  -> NGI N83624 hardware and DUT/test bench
```

The architecture description must explicitly state that raw `write()` and `query()` are advanced escape-hatch methods on the same unified public class, not a separate low-level class.
It must also show UDP semantics: port `7000` is the all-channel communication-board port, while `7001-7024` are channel-specific ports that must not be used as a generic 24-channel transport.


## 2. Target Language and Packaging

Use **Python 3.10+**.

The package must be installable with `pip` using `pyproject.toml`.

Do **not** use a `src/` folder layout. Put the package directly in the repository root:

```text
ngi_n83624/
    __init__.py
    driver.py
    channel.py
    transports.py
    commands.py
    models.py
    exceptions.py
    parsing.py
    safety.py
    logging_utils.py
    session.py
    heartbeat.py
    interlocks.py
    traceability.py
examples/
tests/
docs/
pyproject.toml
README.md
CHANGELOG.md
LICENSE
```

Recommended package name:

```text
ngi-n83624
```

Recommended import name:

```python
import ngi_n83624
```

Main public class:

```python
from ngi_n83624 import N83624CellSimulator
```

### 2.1 Packaging Metadata and Versioning

`pyproject.toml` must include:

- PEP 621 project metadata.
- Python classifiers for all supported Python versions, minimum Python `>=3.10`.
- Runtime dependencies separated from development dependencies.
- Optional dependency groups, for example:

```toml
[project.optional-dependencies]
dev = ["pytest", "pytest-cov", "hypothesis", "ruff", "mypy"]
docs = ["mkdocs", "mkdocstrings[python]"]
serial = ["pyserial"]
```

Versioning must follow Semantic Versioning:

- `0.x` while hardware behavior is still being verified.
- `1.0.0` only after command coverage, hardware integration tests, protocol verification, and the 24/7 production-assurance checklist pass.

Include a minimal CI configuration or `docs/ci.md` describing how to run `ruff`, type checking, unit tests, coverage, and docs generation.

---

## 3. Required Dependencies

Use only widely available, stable libraries.

Required:

- `pyserial` for RS232 transport.
- `typing_extensions` only if needed for Python 3.10 compatibility.
- `pytest` for tests.
- `pytest-cov` for coverage.
- `hypothesis` for property-based validation and parser boundary tests.
- `ruff` for linting.
- `mypy` or `pyright` for type checking.
- `mkdocs` plus `mkdocstrings[python]` or Sphinx plus autodoc for generated API documentation.

Optional:

- `pydantic` is allowed only if it brings real value for configuration validation. Prefer lightweight dataclasses unless strong validation is needed.
- `pandas` must not be required by the core driver. If CSV or dataframe examples are added, keep them in optional examples only.

Do not require PyVISA. This device uses raw SCPI over TCP/UDP/serial, so the driver should work without VISA.

---

## 4. Communication Requirements

Implement a clean transport abstraction as a structural `typing.Protocol`, not merely as an informal base class. This allows third-party transports to be passed to the driver without explicit inheritance while preserving static type checking.

```python
from typing import Protocol

class Transport(Protocol):
    def open(self) -> None: ...
    def close(self) -> None: ...
    def write(self, command: str) -> None: ...
    def query(self, command: str) -> str: ...
    def is_open(self) -> bool: ...
```

Concrete built-in transports may optionally inherit from an internal ABC or mixin for shared behavior, but the public type accepted by `N83624CellSimulator` must be `Transport`.

Implement these concrete transports.

### 4.1 TCP Transport

Class:

```python
TcpTransport(host: str, port: int = 7000, timeout: float = 3.0)
```

Requirements:

- Default IP should be `192.168.0.123`.
- Default TCP port should be `7000`.
- Use standard Python `socket`.
- Commands must be terminated with line feed `\n`.
- Implement configurable timeout.
- Implement reconnect-safe close.
- Raise driver-specific exceptions, not raw socket exceptions.

### 4.2 UDP Transport

Class:

```python
UdpTransport(host: str, port: int = 7000, timeout: float = 3.0)
```

Requirements:

- Support UDP ports `7000–7024`.
- Port `7000` is the communication-board port and can control all 24 channels.
- Ports `7001–7024` correspond to channel 1 through 24 and may be used when higher acquisition speed is required.
- Document that UDP may be less reliable than TCP and should be used only when the application accepts packet loss or has retry logic.

UDP channel-port semantics are safety-critical:

- `UdpTransport(port=7000)` may be used with the normal multi-channel API: `sim.channel(1)` through `sim.channel(24)`.
- `UdpTransport(port=7001)` through `UdpTransport(port=7024)` are **channel-bound transports**. The driver must derive the bound channel as `port - 7000`.
- If a channel-bound UDP transport is used, `sim.channel(n)` must reject access when `n != bound_channel` by raising `ValidationError`, unless an explicit expert-only option such as `allow_udp_channel_mismatch=True` is provided and documented as requiring hardware verification.
- Provide a dedicated factory for channel-bound UDP to make intent explicit:

```python
@classmethod
def udp_channel(
    cls,
    host: str,
    channel: int,
    timeout: float = 3.0,
    *,
    limits: "InstrumentLimits | None" = None,
    safety_policy: "DriverSafetyPolicy | None" = None,
) -> "N83624CellSimulator": ...
```

- The documentation and examples must clearly state that per-channel UDP ports are intended for a single-channel instrument object or high-speed acquisition path, not for unrestricted multi-channel control.

### 4.3 Serial Transport

Class:

```python
SerialTransport(port: str, baudrate: int = 115200, timeout: float = 3.0)
```

Requirements:

- Default baud rate: `115200`.
- Supported baud rates: `9600`, `19200`, `38400`, `57600`, `115200`.
- Use `pyserial`.
- Commands must be terminated with `\n`.
- Query should read until line terminator or timeout.
- Raise driver-specific exceptions.

---

### 4.4 Protocol Robustness and Hardware Verification

The SCPI manual gives basic communication parameters, but it does not fully specify every transport edge case. The generated driver must therefore implement defensive behavior and document the exact behavior verified on real hardware.

Required protocol assumptions to verify during hardware integration:

- Whether the TCP socket is intended to remain open for the whole session or may be closed by the instrument after inactivity.
- Whether every query response is terminated by `LF` and whether `CRLF` may also appear.
- Maximum observed response length for every supported query.
- Whether multiple clients can connect to TCP port `7000` simultaneously.
- Whether port `7000` and per-channel ports `7001–7024` may safely be used at the same time.
- Whether UDP query responses are always returned to the sender address/port.
- Whether UDP packet loss, duplicated packets, or reordered responses can occur under load.
- Whether command execution is atomic per channel and what happens when two channels are commanded quickly.
- Whether the instrument emits inline error messages, numeric error codes, or only exposes fault/status bits.
- Whether responses are always 7-bit ASCII as implied by the manual.

Implementation requirements:

- TCP and serial `query()` must read until terminator or timeout, with a maximum response length guard.
- UDP `query()` must match a response to the issued command context where possible. If the protocol cannot guarantee this, document UDP as unsafe for concurrent queries and serialize all UDP traffic.
- All transports must reject empty, partial, or overlong responses with `ProtocolError`.
- All transports must expose the last successful communication timestamp.
- A command must never be considered successful merely because `socket.send()` succeeded; queries must parse a valid response and setters must be verified when `verify=True`.
- Hardware integration tests must record the verified response terminator, socket lifetime behavior, and maximum response sizes in `docs/protocol_verification.md`.

---

## 5. SCPI Syntax Requirements

The driver must implement SCPI command formatting according to the manual:

- Commands use colon-separated keywords.
- Commands may use long or short mnemonics.
- Queries end with `?`.
- Parameters are separated from the command by a space.
- Multiple parameters are comma-separated.
- Commands terminate with line feed `LF`.
- Mnemonics are not case-sensitive, but the driver shall emit a consistent style.

Default emitted command style must be the vendor manual long/mixed form, for example `SOURce1:VOLTage`, `MEASure1:VOLTage?`, and `OUTPut1:MODE`, because it is easier to audit in logs. Short mnemonics may be used internally only where the manual documents them and tests prove equivalence. Public API names must remain readable and unit-annotated.

Numeric response parsing must be deterministic. Implement parsing helpers in `parsing.py`:

```python
def parse_float(response: str, *, command: str) -> float: ...
def parse_int(response: str, *, command: str) -> int: ...
def parse_bool(response: str, *, command: str) -> bool: ...
```

Parsing must accept valid SCPI numeric representations including leading/trailing whitespace, leading `+`, decimal forms such as `123.`, and scientific notation such as `+1.000000E+00`. Malformed, empty, partial, `NaN`, or infinite responses must raise `ProtocolError` with command context.

Use long-form SCPI mnemonics by default while keeping public Python methods readable.

Examples:

```text
*IDN?
*OPC?
OUTPut1:MODE 0
OUTPut1:ONOFF 1
SOURce1:VOLTage 5.0
MEASure1:VOLTage?
```

Do not append comments such as `// turn on output` to real commands. The manual examples include comments for explanation only, but the device does not accept comments.

---

## 6. Public API Design

Create two API layers inside one unified public instrument class. There must be **no separate class also named `N83624CellSimulator`**.

`N83624CellSimulator` is the single public instrument class. It exposes:

1. raw low-level `write()` and `query()` escape-hatch methods for advanced users; and
2. typed high-level methods and `N83624Channel` objects for normal production use.

### 6.1 Low-Level SCPI Escape Hatch

Unified class methods:

```python
class N83624CellSimulator:
    def write(self, command: str) -> None: ...
    def query(self, command: str) -> str: ...
```

These methods send raw SCPI commands and return raw strings.

Requirements:

- Validate that command strings are non-empty.
- Add terminator automatically.
- Strip response terminators.
- Log commands and responses when debug logging is enabled.
- Never log sensitive user data if later added.
- Do not silently ignore communication errors.

### 6.2 High-Level Driver Layer

Main class:

```python
class N83624CellSimulator:
    @classmethod
    def tcp(
        cls,
        host: str = "192.168.0.123",
        port: int = 7000,
        timeout: float = 3.0,
        *,
        limits: "InstrumentLimits | None" = None,
        safety_policy: "DriverSafetyPolicy | None" = None,
    ) -> "N83624CellSimulator": ...

    @classmethod
    def udp(
        cls,
        host: str = "192.168.0.123",
        port: int = 7000,
        timeout: float = 3.0,
        *,
        limits: "InstrumentLimits | None" = None,
        safety_policy: "DriverSafetyPolicy | None" = None,
    ) -> "N83624CellSimulator": ...

    @classmethod
    def serial(
        cls,
        port: str,
        baudrate: int = 115200,
        timeout: float = 3.0,
        *,
        limits: "InstrumentLimits | None" = None,
        safety_policy: "DriverSafetyPolicy | None" = None,
    ) -> "N83624CellSimulator": ...

    def connect(self) -> None: ...
    def reconnect(self) -> None: ...
    def close(self, *, output_off: bool | None = None) -> None: ...
    def get_session_state(self) -> "SessionState": ...
    def read_channel_configuration(self, channel: int) -> "ChannelConfiguration": ...
    def read_all_channel_configurations(self) -> dict[int, "ChannelConfiguration"]: ...
    def __enter__(self) -> "N83624CellSimulator": ...
    def __exit__(self, exc_type, exc, tb) -> None: ...
    def channel(self, channel: int) -> "N83624Channel": ...
```

Channel API:

```python
class N83624Channel:
    def __init__(self, instrument: N83624CellSimulator, channel: int): ...
```

The channel object should expose all channel-specific commands.

---

## 7. Data Models and Enums

Implement enums for all fixed values.

```python
class OutputMode(IntEnum):
    SOURCE = 0
    CHARGE = 1
    SOC = 3
    SEQUENCE = 128
```

```python
class OutputState(IntEnum):
    OFF = 0
    ON = 1
```

```python
class CurrentRange(IntEnum):
    HIGH = 0
    LOW = 2
    AUTO = 3
```

```python
class CaptureRate(IntEnum):
    FAST_10MS = 0
    MEDIUM_120MS = 1
    SLOW_480MS = 2
```

```python
class FaultSimulationMode(IntEnum):
    NORMAL = 0
    OPEN_POSITIVE = 1
    OPEN_NEGATIVE = 4
    OUTPUT_SHORTED = 8
    REVERSE_POLARITY = 96
```

```python
class LanConnectionType(IntEnum):
    UDP = 0
    TCP = 1
```

```python
class Language(IntEnum):
    CHINESE = 0
    ENGLISH = 1
```

Create dataclasses:

```python
@dataclass(frozen=True)
class Measurement:
    channel: int
    voltage_v: float | None = None
    current_ma: float | None = None
    power_w: float | None = None
    capacity_mah: float | None = None
    resistance_mohm: float | None = None
```

Measurement `None` semantics:

- Individual `measure_voltage_v()`, `measure_current_ma()`, etc. must return `float` or raise a typed exception. They must not return `None`.
- `measure_all()` may return `None` for a field only when that field was intentionally not queried by the implementation for performance or because the field is not applicable to the current mode.
- Communication failure, malformed responses, unsupported commands, safety refusal, or validation failure must raise a typed exception instead of being represented as `None`.
- If the implementation always queries all five fields, then `Measurement` fields should all be populated with floats.


```python
@dataclass(frozen=True)
class ChannelStatus:
    raw: int
    output_on: bool
    ovp: bool
    ocp: bool
    opp: bool
    otp: bool
    fault_relay_voltage_current_present: bool
    fault_relay_wrong_mode: bool
    readback_range: int | None
```

```python
@dataclass(frozen=True)
class SocStep:
    capacity_mah: float
    voltage_v: float
    current_limit_ma: float
    resistance_mohm: float
```

```python
@dataclass(frozen=True)
class SequenceStep:
    voltage_v: float
    current_limit_ma: float
    resistance_mohm: float
    runtime_s: float
    link_start: int = -1
    link_end: int = -1
    link_cycle: int = 0
```


```python
class SessionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED_UNVERIFIED = "connected_unverified"
    READY = "ready"
    FAULTED = "faulted"
    RECOVERING = "recovering"
    SHUTDOWN = "shutdown"
```

```python
@dataclass(frozen=True)
class ChannelLimits:
    """Mandatory per-channel bench limits. Values must match the exact instrument model and DUT bench."""
    min_voltage_v: float = 0.0
    max_voltage_v: float | None = None
    min_current_ma: float = 0.0
    max_current_ma: float | None = None
    min_resistance_mohm: float = 0.0
    max_resistance_mohm: float | None = None
    min_power_mw: float = 0.0
    max_power_mw: float | None = None
    max_capacity_mah: float | None = None
```

```python
@dataclass(frozen=True)
class InstrumentLimits:
    """Complete model/bench safety envelope. Required before output can be enabled."""
    model_name: str
    channels: Mapping[int, ChannelLimits]
    require_all_channels_defined: bool = True

    def for_channel(self, channel: int) -> ChannelLimits: ...
```

Limit scope requirements:

- `ChannelLimits` are per-channel limits. This is mandatory because a real bench may wire different DUTs, current ranges, harnesses, or fixtures to different channels.
- `InstrumentLimits` is the complete bench/model envelope and maps channel numbers to `ChannelLimits`.
- If all channels share the same limits, the user may provide a helper constructor such as `InstrumentLimits.same_for_all(model_name, channels, limits)`, but the resulting object must still expand to explicit per-channel limits.
- Output enable must check the limit object for the exact addressed channel.


```python
@dataclass(frozen=True)
class DriverSafetyPolicy:
    require_limits_before_output_on: bool = True
    output_off_on_close: bool = False
    output_off_on_exception: bool = True
    fault_simulation_enabled: bool = False
    require_status_check_after_setters: bool = True
    require_identity_check_on_connect: bool = True
    require_state_resync_after_reconnect: bool = True
    require_interlock_for_output_on: bool = True
    require_interlock_for_fault_simulation: bool = True
    dangerous_system_write_requires_confirmation: bool = True
```

```python
@dataclass(frozen=True)
class HeartbeatConfig:
    enabled: bool = False
    interval_s: float = 5.0
    timeout_s: float = 3.0
    max_missed_heartbeats: int = 2
    poll_identity: bool = False
    poll_channel_status: bool = True
    status_channels: tuple[int, ...] = (1,)
```

```python
@dataclass(frozen=True)
class ReconnectPolicy:
    enabled: bool = False
    max_attempts: int = 3
    initial_delay_s: float = 0.5
    max_delay_s: float = 10.0
    exponential_backoff: bool = True
    resync_state_after_reconnect: bool = True
    require_operator_ack_after_unknown_output_state: bool = True
```

```python
@dataclass(frozen=True)
class ChannelConfiguration:
    channel: int
    mode: OutputMode
    output_enabled: bool
    source_voltage_v: float | None = None
    source_current_limit_ma: float | None = None
    source_current_range: CurrentRange | None = None
    charge_voltage_v: float | None = None
    charge_current_limit_ma: float | None = None
    charge_resistance_mohm: float | None = None
    ocp_current_ma: float | None = None
    ovp_voltage_v: float | None = None
    opp_power_mw: float | None = None
    capture_rate: CaptureRate | None = None
    status: ChannelStatus | None = None
```

```python
class BenchInterlock(Protocol):
    """External safety gate implemented by the test-bench application."""

    def assert_output_allowed(self, channel: int) -> None: ...
    def assert_fault_simulation_allowed(self, channel: int, mode: FaultSimulationMode) -> None: ...
    def on_driver_fault(self, error: Exception) -> None: ...
```

```python
@dataclass(frozen=True)
class CommunicationObservation:
    transport: str
    last_successful_command_monotonic_s: float | None
    last_successful_query_monotonic_s: float | None
    consecutive_timeouts: int
    session_state: SessionState
```

---

## 8. Validation Rules

Implement strict validation before sending commands.

Required validation:

- Channel number must be `1–24` for normal channel commands.
- Channel-list arguments must contain unique channels in range `1–24`.
- Special case: `MEASure<n>:CAPRate` is documented with `n = 0–24`. Implement `set_global_capture_rate()` / `get_global_capture_rate()` using `MEASure0:CAPRate` only if verified on hardware. Until verified, expose it as experimental or raise `NotImplementedError` with a clear message. Normal channel capture-rate methods must use channels `1–24`.
- SOC file number must be `1–8`.
- SEQ file number must be `1–10`.
- SOC and SEQ step count must be `0–200`.
- SOC and SEQ step index must be `1–200`.
- Sequence file cycle must be `0–100`.
- Sequence link cycle must be `0–100`.
- Sequence link start/end must be `-1–200`; `-1` is the manual-defined disabled/no-link sentinel.
- Negative values are allowed only for parameters explicitly enumerated here: `SequenceStep.link_start = -1` and `SequenceStep.link_end = -1`. All voltage, current, power, capacity, resistance, runtime, dwell, file, step, cycle, channel, and baud values must be non-negative unless another manual command explicitly says otherwise.
- Output mode must be one of `0`, `1`, `3`, `128`.
- Output ON/OFF must be `0` or `1`.
- Capture rate must be `0`, `1`, or `2`.
- Current range must be `0`, `2`, or `3`.
- Fault simulation mode must be one of `0`, `1`, `4`, `8`, `96`.
- Serial baud rate must be one of `9600`, `19200`, `38400`, `57600`, `115200`.
- LAN connection type must be `0` or `1`.
- Output ON dwell must be an integer in range `0..0xfffffffe` microseconds.
- Boolean-like settings must accept Python `bool` and convert to `0/1`. Because Python `bool` is a subclass of `int`, validators must intentionally detect and handle `bool` before generic integer validation so code review remains clear.

For voltage, current, resistance, power, capacity, and runtime values:

- Accept `int` and `float`.
- Reject `NaN` and infinite values.
- Reject negative values unless the manual explicitly allows negative values.
- Device-specific min/max ratings are not fully defined in the SCPI manual, so the driver must support user-provided limits through `InstrumentLimits` and `ChannelLimits`.
- Before any command can enable output, the driver must have valid limits for that channel unless `DriverSafetyPolicy.require_limits_before_output_on=False` is explicitly set by an expert user.
- Limits must be validated at object construction time: reject missing channels, negative maxima, maximum below minimum, and non-finite values.
- Setters must reject values outside configured channel limits before sending any SCPI command.

The driver must support user-defined safety limits and reject commands outside them. The default production behavior is conservative: output enable is refused until model-specific limits are configured.

---

## 9. Common Commands

Implement:

```python
def identify(self) -> str
def opc(self) -> int
def wait_operation_complete(self, timeout: float | None = None) -> bool
def factory_reset(self, confirm: bool = False) -> None
```

SCPI:

```text
*IDN?
*OPC
*OPC?
*RST
```

Factory reset is destructive and changes many settings. Therefore:

- `factory_reset()` must require `confirm=True`.
- Without confirmation, raise `SafetyError`.
- Document that reset may take about 10 seconds.
- After reset, optionally wait and re-query identity.

### 9.1 Additional IEEE 488.2 Common Command Evaluation

The manual explicitly documents `*IDN?`, `*OPC`, `*OPC?`, and `*RST`. It also refers generally to IEEE 488.2 common commands, but it does not clearly document a full status-byte/error-queue model.

Requirements:

- Do not blindly implement undocumented commands as production API.
- During hardware protocol verification, evaluate whether the instrument accepts and correctly responds to additional common commands such as `*CLS`, `*ESR?`, and `*STB?`.
- If verified, expose them as optional methods and document firmware version and behavior:

```python
def clear_status(self, *, experimental_ok: bool = False) -> None: ...
def read_standard_event_status(self, *, experimental_ok: bool = False) -> int: ...
def read_status_byte(self, *, experimental_ok: bool = False) -> int: ...
```

- Until verified on hardware, these methods must either not exist or must raise `NotImplementedError` unless `experimental_ok=True`.
- Record results in `docs/protocol_verification.md` and `docs/residual_risks.md`.

---

## 10. Measurement Commands

Implement on `N83624Channel`:

```python
def measure_current_ma(self) -> float
def measure_voltage_v(self) -> float
def measure_power_w(self) -> float
def measure_capacity_mah(self) -> float
def measure_resistance_mohm(self) -> float
def set_capture_rate(self, rate: CaptureRate | int) -> None
def get_capture_rate(self) -> CaptureRate
def measure_all(self) -> Measurement
```

SCPI:

```text
MEASure<n>:CURRent?
MEASure<n>:VOLTage?
MEASure<n>:POWer?
MEASure<n>:MAH?
MEASure<n>:Res?
MEASure<n>:CAPRate <0|1|2>
MEASure<n>:CAPRate?
```

Units:

- Current: mA
- Voltage: V
- Power: W
- Capacity: mAh
- Resistance: mΩ
- Capture rate: `0 = 10 ms`, `1 = 120 ms`, `2 = 480 ms`
- The manual documents capture-rate channel suffix range as `0–24`. Treat `n=0` as a possible global capture-rate setting, but require hardware verification before using it in production.

Also implement instrument-level convenience methods:

```python
def measure_voltage_channels(self, channels: Sequence[int]) -> dict[int, float]
def measure_current_channels(self, channels: Sequence[int]) -> dict[int, float]
def measure_power_channels(self, channels: Sequence[int]) -> dict[int, float]
def set_global_capture_rate(self, rate: CaptureRate | int, *, experimental_ok: bool = False) -> None
def get_global_capture_rate(self, *, experimental_ok: bool = False) -> CaptureRate
```

Batch commands may be used only where the manual explicitly supports `(@1,2,...)`. Otherwise, implement a safe loop per channel.

---

## 11. Output Commands

Implement on `N83624Channel`:

```python
def set_mode(self, mode: OutputMode | int, *, output_off_first: bool = True, verify: bool = True) -> None
def get_mode(self) -> OutputMode
def output_on(self) -> None
def output_off(self) -> None
def set_output(self, enabled: bool) -> None
def get_output(self) -> bool
def get_status(self) -> ChannelStatus
def get_event(self) -> ChannelStatus
def set_on_dwell_us(self, dwell_us: int) -> None
def get_on_dwell_us(self) -> int
```

SCPI:

```text
OUTPut<n>:MODE <0|1|3|128>
OUTPut<n>:MODE?
OUTPut<n>:ONOFF <0|1>
OUTPut<n>:ONOFF?
OUTPut<n>:STATe?
OUTPut<n>:EVENt?
OUTPut<n>:ONDWell <0..0xfffffffe>
OUTPut<n>:ONDWell?
```

Output modes:

- `0`: Source mode
- `1`: Charge mode
- `3`: SOC mode
- `128`: SEQ mode

Status/event bit decoding:

- Bit 0: output ON/OFF
- Bit 1: OVP
- Bit 2: OCP
- Bit 3: OPP
- Bit 4: OTP
- Bit 5: voltage/current present at port when operating fault simulation relay
- Bit 6: fault relay operation attempted in unsupported mode
- Bits 16–18: readback range, where `0 = high`, `1 = medium`, `2 = low`

Safety behavior:

- When changing mode, default behavior must turn output OFF first.
- Allow `output_off_first=False` only as an explicit expert option.
- After setting mode, query mode back and verify it unless `verify=False`.

---

## 12. Source Mode Commands

Implement:

```python
def configure_source(
    self,
    voltage_v: float,
    current_limit_ma: float,
    current_range: CurrentRange | int = CurrentRange.AUTO,
    *,
    output: bool | None = None,
    output_off_first: bool = True,
    verify: bool = True,
) -> None
```

Also implement individual methods:

```python
def set_source_voltage_v(self, voltage_v: float) -> None
def get_source_voltage_v(self) -> float
def set_source_current_limit_ma(self, current_ma: float) -> None
def get_source_current_limit_ma(self) -> float
def set_source_current_range(self, range_: CurrentRange | int) -> None
def get_source_current_range(self) -> CurrentRange
```

SCPI:

```text
SOURce<n>:VOLTage <NRf>
SOURce<n>:VOLTage?
SOURce<n>:OUTCURRent <NRf>
SOURce<n>:OUTCURRent?
SOURce<n>:RANGe <0|2|3>
SOURce<n>:RANGe?
```

Units:

- Voltage: V
- Current limit: mA
- Range: `0 = high`, `2 = low`, `3 = auto`

Safe configuration sequence:

```text
OUTPut<n>:ONOFF 0
OUTPut<n>:MODE 0
SOURce<n>:VOLTage <voltage>
SOURce<n>:OUTCURRent <current>
SOURce<n>:RANGe <range>
optional OUTPut<n>:ONOFF 1
```

---

## 13. Charge Mode Commands

Implement:

```python
def configure_charge(
    self,
    voltage_v: float,
    current_limit_ma: float,
    resistance_mohm: float,
    *,
    output: bool | None = None,
    output_off_first: bool = True,
    verify: bool = True,
) -> None
```

Individual methods:

```python
def set_charge_voltage_v(self, voltage_v: float) -> None
def get_charge_voltage_v(self) -> float
def set_charge_current_limit_ma(self, current_ma: float) -> None
def get_charge_current_limit_ma(self) -> float
def set_charge_resistance_mohm(self, resistance_mohm: float) -> None
def get_charge_resistance_mohm(self) -> float
def read_charge_echo_voltage_v(self) -> float
def read_charge_echo_capacity_mah(self) -> float
```

SCPI:

```text
CHARge<n>:VOLTage <NRf>
CHARge<n>:VOLTage?
CHARge<n>:OUTCURRent <NRf>
CHARge<n>:OUTCURRent?
CHARge<n>:Res <NRf>
CHARge<n>:Res?
CHARge<n>:ECHO:VOLTage?
CHARge<n>:ECHO:Q?
```

Units:

- Voltage: V
- Current limit: mA
- Resistance: mΩ
- Echo capacity: mAh

Safe configuration sequence:

```text
OUTPut<n>:ONOFF 0
OUTPut<n>:MODE 1
CHARge<n>:VOLTage <voltage>
CHARge<n>:OUTCURRent <current>
CHARge<n>:Res <resistance>
optional OUTPut<n>:ONOFF 1
```

---

## 14. SOC Mode Commands

SOC mode simulates battery discharge behavior based on capacity steps.

Implement:

```python
def configure_soc(
    self,
    steps: Sequence[SocStep],
    *,
    file_number: int | None = None,
    start_voltage_v: float | None = None,
    output: bool | None = None,
    output_off_first: bool = True,
    verify: bool = True,
) -> None
```

Individual methods:

```python
def set_soc_file(self, file_number: int) -> None
def get_soc_file(self) -> int
def set_soc_length(self, length: int) -> None
def get_soc_length(self) -> int
def set_soc_edit_step(self, step: int) -> None
def get_soc_edit_step(self) -> int
def set_soc_step_voltage_v(self, voltage_v: float) -> None
def get_soc_step_voltage_v(self) -> float
def set_soc_step_current_limit_ma(self, current_ma: float) -> None
def get_soc_step_current_limit_ma(self) -> float
def set_soc_step_resistance_mohm(self, resistance_mohm: float) -> None
def get_soc_step_resistance_mohm(self) -> float
def set_soc_step_capacity_mah(self, capacity_mah: float) -> None
def get_soc_step_capacity_mah(self) -> float
def set_soc_start_voltage_v(self, voltage_v: float) -> None
def get_soc_start_voltage_v(self) -> float
def get_soc_running_step(self) -> int
def get_soc_running_capacity_mah(self) -> float
def get_soc_open_voltage_v(self) -> float
def get_soc_simulated_resistance_mohm(self) -> float
```

SCPI:

```text
SOC<n>:EDIT:FILE <1..8>
SOC<n>:EDIT:FILE?
SOC<n>:EDIT:LENGth <0..200>
SOC<n>:EDIT:LENGth?
SOC<n>:EDIT:STEP <1..200>
SOC<n>:EDIT:STEP?
SOC<n>:EDIT:VOLTage <NRf>
SOC<n>:EDIT:VOLTage?
SOC<n>:EDIT:OUTCURRent <NRf>
SOC<n>:EDIT:OUTCURRent?
SOC<n>:EDIT:Res <NRf>
SOC<n>:EDIT:Res?
SOC<n>:EDIT:Q <NRf>
SOC<n>:EDIT:Q?
SOC<n>:EDIT:SVOLtage <NRf>
SOC<n>:EDIT:SVOLtage?
SOC<n>:RUN:STEP?
SOC<n>:RUN:Q?
SOC<n>:OPEN:VOLTage?
SOC<n>:SIM:RES?
```

Important manual inconsistency:

- The manual heading and examples indicate `SOC<n>:EDIT:FILE`, while one extracted command syntax appears as `SOC<n>:EDIT:RILE`. Implement `SOC<n>:EDIT:FILE` because it matches the heading and examples.
- Add a note in documentation saying this was interpreted from the manual and should be verified on real hardware.

`file_number=None` behavior:

- `configure_soc(..., file_number=None)` must not silently assume a file number.
- If `file_number is None`, the driver must first query `get_soc_file()` while holding the compound-operation lock, use the currently selected SOC file, and record that file number in debug/audit logs.
- If `get_soc_file()` fails, returns malformed data, or returns a value outside `1..8`, raise `ProtocolError` or `ValidationError` and do not modify SOC steps.
- Documentation must recommend passing an explicit `file_number` for deterministic production test scripts.

Safe SOC configuration sequence:

```text
OUTPut<n>:ONOFF 0
OUTPut<n>:MODE 3
SOC<n>:EDIT:FILE <file_number>      # if provided
SOC<n>:EDIT:LENGth <step_count>
for each step:
    SOC<n>:EDIT:STEP <step_index>
    SOC<n>:EDIT:Q <capacity_mah>
    SOC<n>:EDIT:VOLTage <voltage_v>
    SOC<n>:EDIT:OUTCURRent <current_limit_ma>
    SOC<n>:EDIT:Res <resistance_mohm>
SOC<n>:EDIT:SVOLtage <start_voltage_v>  # if provided
optional OUTPut<n>:ONOFF 1
```

---

## 15. Sequence Mode Commands

SEQ mode runs predefined steps with voltage, current limit, resistance, runtime, and optional links/cycles.

Implement:

```python
def configure_sequence(
    self,
    file_number: int,
    steps: Sequence[SequenceStep],
    *,
    file_cycle: int = 1,
    output: bool | None = None,
    output_off_first: bool = True,
    verify: bool = True,
) -> None
```

Individual methods:

```python
def set_sequence_edit_file(self, file_number: int) -> None
def get_sequence_edit_file(self) -> int
def set_sequence_length(self, length: int) -> None
def get_sequence_length(self) -> int
def set_sequence_edit_step(self, step: int) -> None
def get_sequence_edit_step(self) -> int
def set_sequence_file_cycle(self, cycle: int) -> None
def get_sequence_file_cycle(self) -> int
def set_sequence_step_voltage_v(self, voltage_v: float) -> None
def get_sequence_step_voltage_v(self) -> float
def set_sequence_step_current_limit_ma(self, current_ma: float) -> None
def get_sequence_step_current_limit_ma(self) -> float
def set_sequence_step_resistance_mohm(self, resistance_mohm: float) -> None
def get_sequence_step_resistance_mohm(self) -> float
def set_sequence_step_runtime_s(self, runtime_s: float) -> None
def get_sequence_step_runtime_s(self) -> float
def set_sequence_link_start(self, step: int) -> None
def get_sequence_link_start(self) -> int
def set_sequence_link_end(self, step: int) -> None
def get_sequence_link_end(self) -> int
def set_sequence_link_cycle(self, cycle: int) -> None
def get_sequence_link_cycle(self) -> int
def set_sequence_run_file(self, file_number: int) -> None
def get_sequence_run_file(self) -> int
def get_sequence_running_step(self) -> int
def get_sequence_running_cycle(self) -> int
def get_sequence_running_time_s(self) -> float
```

SCPI:

```text
SEQuence<n>:EDIT:FILE <1..10>
SEQuence<n>:EDIT:FILE?
SEQuence<n>:EDIT:LENGth <0..200>
SEQuence<n>:EDIT:LENGth?
SEQuence<n>:EDIT:STEP <1..200>
SEQuence<n>:EDIT:STEP?
SEQuence<n>:EDIT:CYCle <0..100>
SEQuence<n>:EDIT:CYCle?
SEQuence<n>:EDIT:VOLTage <NRf>
SEQuence<n>:EDIT:VOLTage?
SEQuence<n>:EDIT:OUTCURRent <NRf>
SEQuence<n>:EDIT:OUTCURRent?
SEQuence<n>:EDIT:Res <NRf>
SEQuence<n>:EDIT:Res?
SEQuence<n>:EDIT:RUNTime <NRf>
SEQuence<n>:EDIT:RUNTime?
SEQuence<n>:EDIT:LINKStart <-1..200>
SEQuence<n>:EDIT:LINKStart?
SEQuence<n>:EDIT:LINKEnd <-1..200>
SEQuence<n>:EDIT:LINKEnd?
SEQuence<n>:EDIT:LINKCycle <0..100>
SEQuence<n>:EDIT:LINKCycle?
SEQuence<n>:RUN:FILE <1..10>
SEQuence<n>:RUN:FILE?
SEQuence<n>:RUN:STEP?
SEQuence<n>:RUN:Cycle?
SEQuence<n>:RUN:Time?
```

Safe sequence configuration:

```text
OUTPut<n>:ONOFF 0
OUTPut<n>:MODE 128
SEQuence<n>:EDIT:FILE <file_number>
SEQuence<n>:EDIT:LENGth <step_count>
SEQuence<n>:EDIT:CYCle <file_cycle>
for each step:
    SEQuence<n>:EDIT:STEP <step_index>
    SEQuence<n>:EDIT:VOLTage <voltage_v>
    SEQuence<n>:EDIT:OUTCURRent <current_limit_ma>
    SEQuence<n>:EDIT:Res <resistance_mohm>
    SEQuence<n>:EDIT:RUNTime <runtime_s>
    SEQuence<n>:EDIT:LINKStart <link_start>
    SEQuence<n>:EDIT:LINKEnd <link_end>
    SEQuence<n>:EDIT:LINKCycle <link_cycle>
SEQuence<n>:RUN:FILE <file_number>
optional OUTPut<n>:ONOFF 1
```

---

## 16. Protection Commands

Implement:

```python
def set_ocp_current_ma(self, current_ma: float) -> None
def get_ocp_current_ma(self) -> float
def set_ovp_voltage_v(self, voltage_v: float) -> None
def get_ovp_voltage_v(self) -> float
def set_opp_power_mw(self, power_mw: float) -> None
def get_opp_power_mw(self) -> float
```

SCPI:

```text
PRO<n>:CURRent <NRf>
PRO<n>:CURRent?
PRO<n>:VOLTage <NRf>
PRO<n>:VOLTage?
PRO<n>:POWEr <NRf>
PRO<n>:POWEr?
```

Units:

- OCP: mA
- OVP: V
- OPP: mW

Requirements:

- Add user-defined max limits so protection values cannot be accidentally set higher than allowed by the test bench.
- Include protection settings in `read_channel_configuration()`.
- When `verify=True`, query protection values back after setting them.
- After changing protection values, optionally poll `OUTPut<n>:STATe?` and raise `DeviceError` if a protection bit unexpectedly becomes active.

---

## 17. CAN Configuration Commands

Implement only what the manual clearly supports. Do not invent undocumented setters.

Required methods:

```python
def get_can_id(self) -> int
def set_can_upload_time_ms(self, time_ms: int) -> None
def get_can_upload_time_ms(self) -> int
def get_can_rate(self) -> int
def get_extended_can_id(self) -> int
```

SCPI:

```text
CFG<n>:CANID?
CFG<n>:UPTime <NR1>
CFG<n>:UPTime?
CFG<n>:CANRate?
CFG<n>:EXTCanid?
```

Rules:

- `UPTime` accepts `0` for disabled or a minimum interval greater than or equal to `60 ms`.
- The manual states that changing CAN settings requires power-down memory to be enabled and the device rebooted. Document this.
- For `CANID`, `CANRate`, and `EXTCanid`, the manual shows query syntax. Do not implement setters unless verified on hardware or a newer manual provides the syntax.
- If optional setters are added later, mark them experimental.

---

## 18. Optional Fault Simulation

Implement optional fault simulation with strict safety.

Methods:

```python
def set_fault_simulation(
    self,
    mode: FaultSimulationMode | int,
    *,
    require_zero_output: bool = True,
    force: bool = False,
    voltage_zero_threshold_v: float = 0.05,
    current_zero_threshold_ma: float = 1.0,
    settle_timeout_s: float = 5.0,
) -> None

def get_fault_simulation(self) -> FaultSimulationMode
```

SCPI:

```text
FAULt<n>:SIMUlate <NR1>
FAULt<n>:SIMUlate?
```

Modes:

- `0`: Normal
- `1`: Open positive
- `4`: Open negative
- `8`: Output shorted
- `96`: Reverse polarity

Safety behavior:

- Fault simulation support must be disabled by default at driver policy level. It is enabled only when `DriverSafetyPolicy.fault_simulation_enabled=True`.
- If `DriverSafetyPolicy.require_interlock_for_fault_simulation=True`, call `BenchInterlock.assert_fault_simulation_allowed()` before sending any fault relay command.
- Fault simulation is only supported in source/power mode.
- Before operating the fault relay, the driver must turn output OFF unless `force=True`.
- The driver must measure voltage and current until both are below configurable thresholds before switching the relay.
- If voltage or current does not reach zero within `settle_timeout_s`, raise `SafetyError`.
- After switching, read event/status bits and raise a warning or exception if Bit 5 or Bit 6 is set.
- `force=True` must be clearly documented as dangerous and should require an explicit keyword argument.
- Default behavior must protect the relay from switching under load.

Capacitive DUT residual-voltage warning:

- Some DUTs, BMS inputs, filters, or harnesses can store energy after simulator output is switched OFF. Voltage can decay slowly even when simulator current is zero.
- The default `voltage_zero_threshold_v=0.05` and `settle_timeout_s=5.0` are conservative starting points, not universal safety limits.
- Documentation must instruct users to choose lower voltage thresholds, longer settle timeouts, or external discharge/measurement hardware when the DUT has significant input capacitance.
- Fault relay switching must be refused when measured voltage/current does not settle below threshold within timeout.

---

## 19. HMI / Interface Board Disconnect Command

Implement:

```python
def set_hmi_disconnect_enabled(self, enabled: bool) -> None
def get_hmi_disconnect_enabled(self) -> bool
```

SCPI:

```text
HMI:DISConnect:ENABle <0|1>
HMI:DISConnect:ENABle?
```

Returns:

- `0`: disabled
- `1`: enabled

---

## 20. System Commands

Implement on instrument class:

```python
def set_ip_address(self, ip: str, *, confirm: bool = False) -> None
def get_ip_address(self) -> str
def set_serial_baudrate(self, baudrate: int, *, confirm: bool = False) -> None
def get_serial_baudrate(self) -> int
def set_beeper(self, enabled: bool) -> None
def get_beeper(self) -> bool
def set_language(self, language: Language | int) -> None
def get_language(self) -> Language
def set_lan_connection_type(self, connection_type: LanConnectionType | int, *, confirm: bool = False) -> None
def get_lan_connection_type(self) -> LanConnectionType
def set_powerdown_save(self, enabled: bool, *, confirm: bool = False) -> None
def get_powerdown_save(self) -> bool
```

SCPI:

```text
SYSTem1:COMMand:LAN:IPADdr "<ip>"
SYSTem1:COMMand:LAN:IPADdr?
SYSTem1:COMMand:SERial:BAUDrate <baud>
SYSTem1:COMMand:SERial:BAUDrate?
SYSTem1:SOUNd <0|1>
SYSTem1:SOUNd?
SYSTem1:LANGuage <0|1>
SYSTem1:LANGuage?
SYSTem1:COMMand:LAN:TYPe <0|1>
SYSTem1:COMMand:LAN:TYPe?
SYSTem1:POWDown:SAVe <0|1>
SYSTem1:POWDown:SAVe?
```

Safety:

- Changing IP address, LAN type, baud rate, or power-down save may affect communication or persistent instrument behavior. Methods must document this clearly.
- `set_ip_address()`, `set_lan_connection_type()`, `set_serial_baudrate()`, and `set_powerdown_save()` must require `confirm=True` when `DriverSafetyPolicy.dangerous_system_write_requires_confirmation=True`.
- Without confirmation, raise `SafetyError` before sending any command.
- After changing IP, LAN type, or baud rate, do not assume the current connection will remain valid.
- After changing persistent communication settings, mark session state as `CONNECTED_UNVERIFIED` or `DISCONNECTED` depending on observed behavior.
- Provide warnings through logging.

---

## 21. Error Handling

Create driver-specific exceptions:

```python
class N83624Error(Exception): ...
class CommunicationError(N83624Error): ...
class TimeoutError(CommunicationError): ...
class ProtocolError(N83624Error): ...
class CommandError(N83624Error): ...
class ExecutionError(N83624Error): ...
class ValidationError(N83624Error): ...
class SafetyError(N83624Error): ...
class DeviceError(N83624Error): ...
class SessionStateError(N83624Error): ...
class InterlockError(SafetyError): ...
class HeartbeatError(CommunicationError): ...
class RecoveryError(CommunicationError): ...
class BusyError(N83624Error): ...
```

Create error-code mapping from the manual.

Command error examples:

- `-100`: Command error
- `-101`: Invalid character
- `-102`: Syntax error
- `-103`: Invalid separator
- `-104`: Data type error
- `-108`: Parameter not allowed
- `-109`: Missing parameter
- `-113`: Undefined header
- `-114`: Header suffix out of range
- `-115`: Command cannot query
- `-116`: Command must query
- `-120`: Numeric data error
- `-121`: Invalid character in number
- `-123`: Exponent too large
- `-124`: Too many digits
- `-128`: Numeric data not allowed
- `-140`: Character data error
- `-150`: String data error
- `-160`: Block data error
- `-170`: Expression error
- `-180`: Macro error

Execution error examples:

- `-200`: Execution error
- `-220`: Parameter error
- `-221`: Setting conflict
- `-222`: Data out of range
- `-224`: Illegal parameter value
- `-225`: Out of memory
- `-232`: Invalid format
- `-240`: Hardware error
- `-242`: Calibration data lost
- `-243`: No reference
- `-256`: File name not found
- `-259`: No selected file
- `-295`: Input buffer overflow
- `-296`: Output buffer overflow

If the manual does not provide a `SYSTem:ERRor?` query, do not invent one. Instead:

- Raise exceptions on transport failures.
- Detect malformed responses.
- Decode status/event bits.
- Provide an error-code enum and mapping for user-facing interpretation if the device returns an error code.

---

## 22. Logging

Use Python `logging`.

Requirements:

- Logger name: `ngi_n83624`.
- Debug logs shall include SCPI command and response.
- Production default logging level must not spam the user.
- Add an option to hide raw traffic if needed.
- Communication exceptions must include transport type, host/port or serial port, and command context.

---

## 23. Thread Safety

The driver shall be safe for multi-threaded test benches.

Requirements:

- Add one instrument-level `threading.RLock` shared by the instrument object, all channel objects, heartbeat logic, reconnect logic, and safety/interlock logic.
- Prevent interleaved commands from multiple threads.
- Document that one instrument object serializes access.
- Do not make channel objects independent connections unless explicitly requested.
- Heartbeat and reconnect logic must use the same transport lock and must not interleave with user commands.
- When the heartbeat detects failure, transition the session state to `FAULTED` or `RECOVERING` before additional user commands are accepted.
- Compound operations must hold the same instrument lock for their full duration, not only around individual `write()` and `query()` calls. This includes:
  - write-then-verify setter sequences;
  - `configure_source()`, `configure_charge()`, `configure_soc()`, and `configure_sequence()` command batches;
  - mode changes with `output_off_first=True`;
  - output enable with limit/interlock/status checks;
  - fault-simulation output-off, settle-measurement loop, relay switching, and post-status check;
  - reconnect followed by identity check and channel state resynchronization;
  - heartbeat state transitions.
- A verification query must not be separated from its preceding setter by another user command on the same instrument object.
- If a long compound operation is in progress, other threads must block or receive a documented `BusyError`; they must never interleave SCPI commands.

---

## 24. Retry and Timeout Policy

Implement optional retry support:

```python
@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 1
    delay_s: float = 0.1
    retry_on_timeout: bool = False
```

Default:

- No retry for write commands that may change instrument state.
- Optional retry for idempotent queries.
- Do not retry fault simulation commands unless explicitly enabled.
- Do not retry non-idempotent setters unless the command is followed by a successful state resynchronization.
- Reconnect behavior must be controlled by `ReconnectPolicy`, not hidden inside low-level transport methods.
- After reconnect, the driver must re-query identity and channel state before returning to `READY` if `require_state_resync_after_reconnect=True`.

---

## 25. Verification Behavior

For high-level setters, support:

```python
verify: bool = True
```

When `verify=True`:

- After setting a value, query the value back.
- Compare using tolerance for floats.
- Raise `DeviceError` if readback does not match expected value.
- If `DriverSafetyPolicy.require_status_check_after_setters=True`, query `OUTPut<n>:STATe?` after safety-critical setters and raise `DeviceError` if OVP/OCP/OPP/OTP/fault bits are active unexpectedly.

Provide default tolerances:

```python
voltage_tolerance_v = 1e-3
current_tolerance_ma = 1e-3
resistance_tolerance_mohm = 1e-3
power_tolerance_mw = 1e-3
```

Allow user override through configuration.

---


## 26. 24/7 Production Assurance Requirements

The driver is intended for unattended or semi-unattended industrial test benches. Therefore, production reliability is a first-class requirement, not an optional enhancement.

### 26.1 Session State Machine

Implement a formal session state machine in `session.py` using `SessionState`.

Required transitions:

```text
DISCONNECTED -> CONNECTING -> CONNECTED_UNVERIFIED -> READY
READY -> FAULTED                  # communication error, heartbeat failure, protocol violation, interlock failure
FAULTED -> RECOVERING             # reconnect policy starts
RECOVERING -> CONNECTED_UNVERIFIED
CONNECTED_UNVERIFIED -> READY     # identity and state resync successful
READY -> SHUTDOWN                 # explicit close/shutdown
FAULTED -> SHUTDOWN               # unrecoverable failure or operator stop
```

Rules:

- `connect()` must not enter `READY` until identity check succeeds when `require_identity_check_on_connect=True`.
- After reconnect or suspected instrument reboot, enter `CONNECTED_UNVERIFIED` and re-read channel state before entering `READY`.
- If the output state is unknown after communication loss, refuse new output-changing commands until state is resynchronized or an operator explicitly acknowledges the risk.
- User commands that require a valid connection must raise `SessionStateError` unless state is `READY`.

### 26.2 Communication Loss While Output May Be ON

When communication fails during a test, the driver must not pretend the output is off. Required behavior:

- Record the last known output state for every channel.
- Transition to `FAULTED` on timeout/protocol error after retry policy is exhausted.
- Call `BenchInterlock.on_driver_fault(error)` if an interlock object is configured.
- If `output_off_on_exception=True`, attempt a best-effort output-off command only if the transport is still usable. If communication is lost, report that output state is unknown.
- Never clear the fault state automatically without reconnect and state resynchronization.

### 26.3 Heartbeat and Watchdog

Implement optional heartbeat supervision in `heartbeat.py`.

Required API:

```python
def start_heartbeat(self, config: HeartbeatConfig | None = None) -> None: ...
def stop_heartbeat(self) -> None: ...
def get_communication_observation(self) -> CommunicationObservation: ...
```

Heartbeat requirements:

- Run in a daemon thread or caller-managed background task.
- Use lightweight queries such as channel status polling; optionally use `*IDN?` at a slower rate.
- Track missed heartbeats and consecutive timeouts.
- Transition to `FAULTED` after `max_missed_heartbeats` failures.
- Never send heartbeat commands while a user command is in progress.
- Make heartbeat disabled by default so simple scripts remain deterministic.

### 26.4 Bench Interlock Interface

Implement `BenchInterlock` as a protocol/interface. The core driver must not directly control external hardware, but it must provide safe hooks.

Interlock checks must be performed before:

- enabling output;
- running SOC or sequence output;
- changing output mode with optional re-enable;
- fault simulation;
- dangerous system setting changes when required by policy.

Example interlock conditions expected in real test benches:

- emergency stop is not active;
- DUT contactor state allows output;
- BMS communication is healthy;
- thermal chamber is inside allowed temperature window;
- external measurement system is running;
- test operator or automation framework has granted output permission.

If the interlock rejects an operation, raise `InterlockError` before any SCPI command that changes output state.

### 26.5 Mandatory Model-Specific Safety Limits

Because the SCPI programming guide does not fully define electrical ratings for every N83624 variant, production use must require explicit limits.

Required behavior:

- `InstrumentLimits` must be provided before output can be enabled unless explicitly disabled by expert policy.
- Limits must be per-channel because some benches may wire channels differently.
- Configuration examples must show limits loaded from a user-owned YAML/JSON/Python file.
- The driver must reject attempts to use unknown/unconfigured channels in output-enabled operations.
- Documentation must clearly state that software limits do not replace external fusing, contactors, or emergency stop hardware.

### 26.6 Safe Shutdown and Context Manager Behavior

`close()` and context manager exit behavior must be explicit and documented:

- Default `close()` must close communication without silently changing output state, unless `DriverSafetyPolicy.output_off_on_close=True`.
- On Python exceptions inside a context manager, if `output_off_on_exception=True`, attempt best-effort output off for channels known to be ON.
- If output-off fails, raise or chain an exception that clearly says output state is unknown.
- Do not hide the original exception from the test script.

### 26.7 Audit Trail and Test Traceability Logging

For production tests, provide optional structured audit records:

- timestamp;
- session state;
- transport identity;
- SCPI command and parsed response;
- channel number;
- high-level method name;
- verification result;
- interlock result;
- exception class and message.

The implementation may use standard `logging`, but the format must be machine-parseable when enabled.

### 26.8 Requirements Traceability Matrix

Generate `docs/traceability_matrix.md` and keep it updated.

For every public high-level method, include:

| Requirement ID | Manual command / safety note | Driver method | Unit test | Hardware test | Documentation section | Status |
|---|---|---|---|---|---|---|

Status values:

- `implemented`
- `unit-tested`
- `hardware-verified`
- `manual-ambiguous`
- `not-supported`
- `deferred`

Manual ambiguities must not be marked as fully verified until tested on a real instrument.

### 26.9 Verification and Validation Plan

Generate `docs/verification_validation_plan.md` with:

- static checks: `ruff`, type checker, package build;
- unit tests with fake transport;
- protocol emulator tests;
- optional hardware smoke tests;
- safety tests with output disabled;
- controlled output-on tests requiring explicit environment variable;
- fault-injection tests;
- long-duration soak tests;
- release criteria;
- residual risks.

### 26.10 Residual Risk Statement

Generate `docs/residual_risks.md` documenting risks that cannot be eliminated in software:

- wrong external wiring;
- missing fusing or contactors;
- unknown behavior of undocumented SCPI commands;
- communication loss while instrument output remains physically ON;
- fault relay wear or damage;
- firmware-version differences;
- UDP packet loss or stale responses;
- incorrect user-provided model limits.

This document must state that the driver is a control library and not a certified safety system.

---

## 27. Examples to Generate

Create examples in the `examples/` folder.

### 27.1 TCP Connect and Identify

```python
from ngi_n83624 import N83624CellSimulator

with N83624CellSimulator.tcp("192.168.0.123") as sim:
    print(sim.identify())
```

### 27.2 Configure Source Mode

Demonstrate:

- Connect.
- Select channel 1.
- Output OFF.
- Configure source mode: 5 V, 1000 mA, auto range.
- Output ON.
- Read voltage/current/power.
- Output OFF in `finally`.

### 27.3 Configure Charge Mode

Demonstrate:

- Charge mode.
- Voltage, current limit, internal resistance.
- Echo voltage and echo capacity.

### 27.4 SOC Profile

Demonstrate:

- Define three `SocStep` entries.
- Configure SOC mode.
- Start output.
- Poll running step and capacity.

### 27.5 Sequence Profile

Demonstrate:

- Define three `SequenceStep` entries.
- Configure sequence file.
- Run sequence.
- Poll running step and running time.

### 27.6 Safe Fault Simulation

Demonstrate:

- Configure source mode.
- Turn output off.
- Wait until measured voltage/current are zero.
- Apply `OPEN_POSITIVE`.
- Restore `NORMAL`.
- Handle `SafetyError`.

### 27.7 RS232 Example

Demonstrate serial connection:

```python
with N83624CellSimulator.serial("COM3", baudrate=115200) as sim:
    print(sim.identify())
```

### 27.8 UDP Per-Channel Example

Demonstrate connecting to UDP port `7001` for channel 1, with clear documentation about reliability limitations.

### 27.9 Production Limits and Interlock Example

Generate an example showing output enable with mandatory limits and a simple interlock.

```python
from ngi_n83624 import (
    ChannelLimits,
    DriverSafetyPolicy,
    InstrumentLimits,
    N83624CellSimulator,
)

limits = InstrumentLimits(
    model_name="N83624 bench profile - example only",
    channels={
        1: ChannelLimits(max_voltage_v=5.0, max_current_ma=1000.0, max_power_mw=5000.0),
    },
)

policy = DriverSafetyPolicy(require_limits_before_output_on=True)

with N83624CellSimulator.tcp("192.168.0.123", limits=limits, safety_policy=policy) as sim:
    ch1 = sim.channel(1)
    ch1.configure_source(5.0, 500.0, output=True)
    ch1.output_off()
```

### 27.10 Heartbeat and Reconnect Example

Generate an example showing heartbeat supervision, fault handling, and safe shutdown behavior.

---

## 28. Tests

Create tests with `pytest`.

### 28.1 Unit Tests

Use fake transports. No hardware required.

Test:

- Command formatting.
- Terminator handling.
- Channel validation.
- Enum validation.
- Numeric validation.
- IP validation.
- Serial baud validation.
- Status/event bit decoding.
- SOC command sequence generation.
- SEQ command sequence generation.
- Source mode safe sequence.
- Charge mode safe sequence.
- Fault simulation safety sequence.
- Factory reset confirmation requirement.
- Exceptions on malformed numeric responses.
- Query response parsing.
- SCPI numeric parser edge cases: leading `+`, scientific notation, whitespace, malformed, empty, `NaN`, and infinite values.
- Property-based validation tests using Hypothesis for channel numbers, file numbers, step indices, cycle counts, link sentinels, ON dwell, enum values, booleans, and numeric bounds.
- Command-order tests using a recording fake transport that asserts exact order for safety-critical sequences, not merely command presence.
- Session state transitions.
- Heartbeat failure transitions.
- Reconnect policy behavior with fake transport.
- Mandatory safety limits before output enable.
- Interlock rejection before SCPI output commands.
- Dangerous system setting confirmation requirement.
- `MEASure0:CAPRate` experimental/verification behavior.
- `read_channel_configuration()` aggregation.

### 28.2 Integration Tests

Hardware tests must be optional and skipped unless environment variables are set.

Environment variables:

```text
N83624_HOST=192.168.0.123
N83624_TCP_PORT=7000
N83624_SERIAL_PORT=COM3
N83624_RUN_HARDWARE_TESTS=1
```

Hardware tests:

- Record protocol observations in `docs/protocol_verification.md`.
- Connect and `*IDN?`.
- Read mode/output state of channel 1.
- Measure voltage/current/power.
- Set and query capture rate.
- Configure source mode with output off.
- Workflow-level tests where hardware setup allows: configure source, read back mode/settings, measure, output off; configure SOC/SEQ with output off and verify file/step settings.
- Do not turn output on automatically in integration tests unless `N83624_ALLOW_OUTPUT_ON=1`.
- Disconnect/reconnect test with output OFF.
- Power-cycle recovery test when hardware setup allows it.
- Verify whether `MEASure0:CAPRate` is a global capture-rate command. Mark result in traceability matrix.

### 28.3 Safety Tests

Test that:

- Fault simulation refuses to switch if measured voltage/current are non-zero.
- Fault simulation refuses unsupported mode unless `force=True`.
- Output is turned off before mode changes by default.
- Factory reset requires `confirm=True`.
- Dangerous system settings require `confirm=True`.
- Output enable refuses to run without configured limits by default.
- Interlock failures prevent output enable and fault simulation before any SCPI state-changing command is sent.
- Unknown output state after communication loss blocks further output-changing commands until resynchronization.

### 28.4 Protocol Emulator Tests

Create a fake SCPI server/emulator for TCP and serial-like behavior. It must simulate:

- normal LF-terminated responses;
- timeout;
- malformed numeric response;
- truncated response;
- overlong response;
- connection drop;
- stale or unexpected UDP response;
- state mismatch during verify-readback;
- attempted command interleaving during compound operations;
- channel-bound UDP mismatch attempt.

### 28.5 Long-Duration and Soak Tests

Provide optional long-duration tests that are skipped by default.

Environment variables:

```text
N83624_RUN_SOAK_TESTS=1
N83624_SOAK_HOURS=24
N83624_ALLOW_OUTPUT_ON=0
```

Required soak-test scenarios:

- 24-hour communication-only heartbeat test with output OFF.
- Repeated status/measurement polling test for memory/resource leaks.
- Reconnect stress test with controlled network interruptions where possible.
- Optional 72-hour production qualification soak test for release candidates.
- Log CPU usage, memory usage, command count, timeout count, reconnect count, and final session state.

### 28.6 Fault-Injection Tests

Implement fake-transport and optional hardware fault-injection tests:

- TCP timeout while output last known ON.
- TCP disconnect during query.
- Serial partial line response.
- UDP no response.
- Malformed status bitfield.
- Interlock rejection.
- Verification mismatch after setter.
- Instrument identity mismatch after reconnect.

### 28.7 Traceability Tests

CI must fail if a public high-level method has no entry in `docs/traceability_matrix.md`.

### 28.8 Coverage

Target:

- Minimum 90% unit-test coverage for command building, validation, parsing, and high-level API.
- Minimum 80% unit-test coverage for session/recovery/heartbeat/interlock code.
- Hardware integration tests and soak tests are not counted in required coverage.

---

## 29. Documentation

Generate:

```text
README.md
docs/quickstart.md
docs/transports.md
docs/source_mode.md
docs/charge_mode.md
docs/soc_mode.md
docs/sequence_mode.md
docs/fault_simulation.md
docs/safety.md
docs/api_reference.md
docs/production_24_7.md
docs/recovery.md
docs/interlocks.md
docs/protocol_verification.md
docs/traceability_matrix.md
docs/verification_validation_plan.md
docs/residual_risks.md
```

Documentation toolchain requirements:

- Use MkDocs + mkdocstrings or Sphinx + autodoc to generate API reference from typed docstrings.
- `docs/api_reference.md` may be generated, but it must not be a stale hand-written copy of public APIs.
- CI must include a documentation build command or a documented local equivalent.
- Every public class and method must have a docstring sufficient for generated API documentation.

README must include:

- What the package supports.
- Installation.
- TCP, UDP, and RS232 examples.
- Safety warnings.
- Basic source-mode example.
- Link to examples.
- Explanation that channel numbers are 1–24.
- Explanation that output-changing operations are safe-by-default.
- Example of mandatory model-specific limits before output enable.
- Example of heartbeat/reconnect supervision.
- Explanation of session states and unknown-output-state handling.

Docs must clearly state:

- Device ratings are not fully defined in the SCPI programming guide. Users must configure external safety limits matching their exact hardware model.
- Fault simulation can damage relay contacts if operated under voltage/current.
- `*RST` is destructive and changes IP, serial baud rate, protection values, files, and other settings.
- LAN/serial settings may require restart.
- CAN changes may require power-down memory and reboot.
- The driver is not a certified safety system and must be used with external hardware safety measures.
- UDP is not recommended for safety-critical output-changing operations unless the user has validated packet behavior in the target network.
- Per-channel UDP ports are channel-bound and must not be used with mismatched `sim.channel(n)` calls.
- Capacitive DUTs can retain residual voltage after output is switched off; fault simulation thresholds and timeouts must be selected for the real DUT and bench.
- `configure_soc(file_number=None)` uses the currently selected SOC file only after querying it; explicit `file_number` is recommended for production scripts.
- `Measurement` fields are `None` only for intentionally not queried or not applicable quantities, never for communication or parsing failures.

---

## 30. Implementation Quality Requirements

The generated code must be production-grade:

- Fully typed public API.
- Clear docstrings for every public class and method.
- No broad `except Exception` without re-raising a typed exception.
- No print statements in library code.
- No global mutable state except logger.
- No hidden sleeps except where explicitly required for safety or documented device behavior.
- No hardcoded test bench limits except defaults from the manual.
- No command comments sent to instrument.
- No silent response parsing failures.
- No automatic output enable unless explicitly requested by the caller.
- No undocumented network retry behavior.
- No hidden automatic transition from `FAULTED` to `READY` without explicit recovery and state resynchronization.
- No output enable without configured limits unless expert policy explicitly disables this protection.
- No use of `src/` package layout.
- Must pass `ruff`, type checking, and `pytest`.
- Must build documentation without errors.
- Must not expose channel-bound UDP as unrestricted multi-channel control.
- Must not release a compound-operation lock between a state-changing command and its verification query.

---

## 31. Acceptance Criteria

The task is complete only when the generated package provides:

1. Installable Python package with root-level `ngi_n83624/` package directory.
2. TCP, UDP, and RS232 transports.
3. Low-level `write()` and `query()`.
4. High-level API for all command groups in the manual.
5. Full support for 24 channels.
6. Source mode setup and query.
7. Charge mode setup and query.
8. SOC profile setup and runtime query.
9. Sequence profile setup and runtime query.
10. Measurement functions for voltage, current, power, capacity, resistance, and capture rate.
11. Protection setting methods.
12. CAN query/upload-time methods.
13. Optional fault simulation with strict safety checks.
14. System setting methods.
15. Status/event bit decoding.
16. Strong validation.
17. Typed exceptions.
18. Logging.
19. Thread-safe command access, including full-duration locking of compound operations.
20. Unit tests with fake transport.
21. Optional hardware integration tests.
22. Documentation and examples.
23. Safe-by-default behavior, especially output OFF before configuration and fault relay protection.
24. No invented SCPI commands where the manual is ambiguous.
25. Mandatory model-specific safety limits before output enable by default.
26. Formal session state machine with documented reconnect and resynchronization behavior.
27. Optional heartbeat/watchdog supervision.
28. Bench interlock interface and tests.
29. `read_channel_configuration()` and `ChannelConfiguration` implemented.
30. Dangerous persistent system settings require confirmation.
31. `MEASure0:CAPRate` ambiguity is explicitly handled and documented.
32. Protocol emulator tests for timeout, malformed response, disconnect, and stale UDP response.
33. Optional 24 h / 72 h soak-test framework.
34. Requirements traceability matrix.
35. Verification/validation plan and residual-risk document.

37. `Transport` is explicitly defined as `typing.Protocol`.
38. Channel-bound UDP transports reject mismatched channel access by default.
39. `configure_soc(file_number=None)` behavior is implemented exactly as specified.
40. `Measurement` `None` semantics are documented and tested.
41. ON dwell range and negative-value exceptions are validated and tested.
42. Hypothesis property-based tests cover validation boundaries.
43. Recording fake transport tests verify exact command ordering for safety-critical sequences.
44. Documentation is generated from docstrings using MkDocs/mkdocstrings or Sphinx/autodoc.
45. Additional IEEE 488.2 commands are documented as verified, experimental, or unsupported; no undocumented command is silently assumed.

---

## 32. Recommended Public Usage Example

The final driver should support this style:

```python
from ngi_n83624 import (
    ChannelLimits,
    CurrentRange,
    InstrumentLimits,
    N83624CellSimulator,
)

limits = InstrumentLimits(
    model_name="N83624 bench profile - example only",
    channels={1: ChannelLimits(max_voltage_v=5.0, max_current_ma=1000.0, max_power_mw=5000.0)},
)

with N83624CellSimulator.tcp("192.168.0.123", limits=limits) as sim:
    print(sim.identify())

    ch1 = sim.channel(1)

    ch1.configure_source(
        voltage_v=5.0,
        current_limit_ma=500.0,
        current_range=CurrentRange.AUTO,
        output=True,
    )

    measurement = ch1.measure_all()
    print(measurement)

    ch1.output_off()
```

---

## 33. Safety-Critical Usage Example

The final driver should support this style:

```python
from ngi_n83624 import N83624CellSimulator, FaultSimulationMode

with N83624CellSimulator.tcp("192.168.0.123") as sim:
    ch1 = sim.channel(1)

    ch1.output_off()

    ch1.set_fault_simulation(
        FaultSimulationMode.OPEN_POSITIVE,
        require_zero_output=True,
        voltage_zero_threshold_v=0.05,
        current_zero_threshold_ma=1.0,
        settle_timeout_s=5.0,
    )

    # Restore normal relay state after test.
    ch1.set_fault_simulation(FaultSimulationMode.NORMAL)
```

---

## 34. Important Manual Ambiguities to Handle Carefully

The code generator must not blindly invent behavior where the manual is inconsistent.

Known ambiguities:

- `SOC<n>:EDIT:FILE` appears as a command heading and example, while one extracted syntax line appears as `SOC<n>:EDIT:RILE`. Implement `FILE`, add a comment in documentation, and verify on hardware.
- Some CAN commands are described as settings, but only query syntax is shown for `CANID`, `CANRate`, and `EXTCanid`. Implement them as queries unless hardware verification proves setter syntax.
- Some commands include spaces inconsistently in the manual examples, such as `SOC1:EDIT: STEP`. Emit normalized SCPI without unnecessary internal spaces, for example `SOC1:EDIT:STEP 1`.
- The manual uses both long and short mnemonic forms. The driver may emit long forms for clarity, but must accept and parse responses independently of command style.
- Device-specific voltage/current/resistance/power min/max ratings are not fully listed in this SCPI guide. Require configurable external safety limits before output enable by default.
- `MEASure<n>:CAPRate` documents channel suffix range `0–24`; `n=0` may be a global capture-rate setting. Treat this as experimental until verified on real hardware.
- TCP socket lifetime, multi-client behavior, maximum response length, and UDP response matching are not fully documented. Verify and record behavior in `docs/protocol_verification.md`.
- The manual documents UDP per-channel ports, but not all interaction semantics with the multi-channel API. Treat ports `7001–7024` as channel-bound unless hardware verification proves otherwise.
- The manual does not fully document additional IEEE 488.2 status commands such as `*CLS`, `*ESR?`, and `*STB?`. Evaluate them only during protocol verification and do not assume support in production.
- The manual does not define how much residual DUT energy may remain after output-off; fault simulation must therefore rely on measured voltage/current thresholds and external bench safety design.
- Source current range values should be verified on hardware because manual examples and enumerated values may be inconsistent.
- The manual provides error-code tables but does not clearly define a universal error-query command. Do not invent `SYSTem:ERRor?` unless verified by hardware or newer documentation.

---

## 35. Final Deliverables

Generate the full repository contents:

```text
ngi_n83624/
examples/
tests/
docs/
pyproject.toml
README.md
CHANGELOG.md
LICENSE
```

Also provide:

- A short architecture explanation.
- A command coverage table.
- Instructions for running tests.
- Instructions for running optional hardware tests.
- A note listing manual ambiguities and how they were handled.
- `docs/traceability_matrix.md`.
- `docs/verification_validation_plan.md`.
- `docs/protocol_verification.md`.
- `docs/residual_risks.md`.
- Optional soak-test runner and report template.
- Protocol emulator/fake SCPI server for CI tests.
