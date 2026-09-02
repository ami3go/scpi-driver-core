# `scpi-driver-core` — Implementation Task

## 1. Task title

**Implement `scpi-driver-core`: framework-independent shared core for SCPI/IEEE-488.2 Python instrument drivers**

---

## 2. Source baseline

This task is derived from the SCPI-oriented drivers and RFDS architecture material in:

```text
repository: https://github.com/ami3go/RobotFrameworks_hw_drivers
branch: dev
reviewed commit: a5388c5bc08da24bd981fdc5571dde43b2589890
```

The package deliberately has a narrower scope than a universal laboratory-driver framework. It should extract infrastructure that is genuinely repeated across the existing SCPI drivers while leaving manufacturer-specific and instrument-specific behavior in each concrete driver package.

---

## 3. Drivers used as design input

### Primary SCPI references

```text
rf_agilent33220a
rf_agilent34411a
rf_ea_ps9000t
rf_eresistor          # SCPI/TCP path only; HTTP fallback remains device-specific
rf_hp34401a
rf_keysight_n6700
rf_ngi_n83624
rf_tbs1000c
```

### Secondary/hybrid reference

```text
rf_bk8500b
```

The SCPI-facing infrastructure may use this package, but any legacy/binary protocol path must remain outside `scpi-driver-core`.

### Explicitly out of scope as migration targets

```text
rf_bk8500_load         proprietary binary serial protocol
rf_phidget_relay       Phidget22 SDK
rf_picoscope_scope     PicoSDK/native SDK
rf_slcan               asynchronous CAN/SLCAN
rf_votsch_climate_chamber  SimServ/TCP, not SCPI
```

Do not distort the SCPI abstraction to accommodate non-SCPI protocols.

---

# 4. Objective

Create a production-grade Python package:

```text
distribution: scpi-driver-core
import:       scpi_driver_core
```

Concrete SCPI drivers should depend on it:

```text
Agilent 33220A ---------+
Agilent 34411A ---------+
HP 34401A --------------+
EA PS9000T -------------+
Keysight N6700 ----------+
NGI N83624 -------------+
Tektronix TBS1000C -----+
E-Resistor -------------+
                         v
                 scpi-driver-core
```

The core must remain independent of:

```text
Robot Framework
HardPy
pytest at runtime
specific manufacturers
specific models
test acceptance criteria
operator UI
bench-specific wiring or safety policy
```

The same concrete Python driver must be usable unchanged from Robot Framework, HardPy/pytest, plain Python, Jupyter, a CLI, or another application.

---

# 5. Required architecture

```text
Robot Framework                       HardPy / pytest
      |                                     |
Robot adapter                           fixture
      \                                     /
       +-----------------------------------+
                       |
                       v
                Concrete driver
                       |
             device-specific logic
                       |
                       v
                scpi-driver-core
              /                  \
        SCPI client          session/runtime
              |
              v
        byte transport
       /   |    |    \
    VISA Serial TCP   UDP
```

Dependency direction must always point downward.

No module under `src/scpi_driver_core/` may import `robot`, `hardpy`, or `pytest`.

---

# 6. What belongs in the core

The package should centralize reusable SCPI infrastructure:

```text
byte-oriented transport contracts
VISA transport
serial transport
TCP transport
UDP transport
SCPI text codec and terminators
SCPI write/query execution
IEEE-488.2 common commands
IEEE-488.2 definite-length binary blocks
SCPI error-queue handling
identity parsing
generic response parsers
engineering-value parsing
named sessions and aliases
connection state
communication health
timeout and deadline handling
safe retry/replay policy
bounded polling
per-session transaction serialization
protocol tracing
JSONL protocol audit sink
redaction hooks
scripted/mock transport
raw-SCPI confirmation guard primitive
common SCPI/transport exceptions
```

---

# 7. What must stay in concrete drivers

Do not move device semantics into the core. Examples:

```text
EA remote-control acquisition/release
EA adjustment-limit behavior
NGI channel arming/output policy
N6700 module maps and SMU/load capability rules
Agilent 34411A measurement-function semantics
HP 34401A overload sentinel policy
Agilent 33220A modulation and sweep behavior
calibration procedures and security-code semantics
TBS1000C trigger/acquisition behavior
TBS1000C waveform scaling
E-Resistor calibration and resistance solving
instrument-specific protection behavior
instrument-specific LAN settings
instrument memory-slot semantics
device-specific safe shutdown
pass/fail assertions
```

Rule of thumb:

> If the code interprets physical behavior of one instrument family, or contains a manufacturer/model-specific command tree, it belongs in the concrete driver.

---

# 8. Canonical transport boundary: bytes

The low-level transport contract must be byte-oriented.

Do **not** use the following as the canonical boundary:

```python
write(command: str)
query(command: str) -> str
```

That is insufficient for waveform data, arbitrary-waveform upload, setup/file transfer, and other binary operations.

Define an interface equivalent to:

```python
from typing import Protocol

class Transport(Protocol):
    @property
    def state(self) -> TransportState: ...

    @property
    def descriptor(self) -> TransportDescriptor: ...

    def open(self) -> TransportDescriptor: ...

    def close(self) -> None: ...

    def write(
        self,
        data: bytes,
        *,
        timeout_s: float | None = None,
        operation_id: str | None = None,
    ) -> WriteResult: ...

    def read(
        self,
        request: ReadRequest,
        *,
        timeout_s: float | None = None,
        operation_id: str | None = None,
    ) -> bytes: ...

    def transact(
        self,
        outbound: bytes,
        response: ReadRequest,
        *,
        timeout_s: float | None = None,
        replay_policy: ReplayPolicy = ReplayPolicy.NEVER,
        operation_id: str | None = None,
    ) -> bytes: ...

    def flush(self, direction: FlushDirection) -> None: ...
```

Text framing belongs above this boundary.

---

# 9. Transport state model

Implement explicit transport states:

```python
class TransportState(Enum):
    CREATED = ...
    OPENING = ...
    OPEN = ...
    FAULTED = ...
    CLOSING = ...
    CLOSED = ...
```

Required behavior:

- `close()` is idempotent.
- I/O while not `OPEN` fails before transmission.
- An I/O failure that makes session validity uncertain moves the transport to `FAULTED`.
- Reopen from `FAULTED` first releases the failed backend resource.
- `is_open`/transport state indicates resource state only, not communication health.
- No transport operation may block forever.

---

# 10. Read modes

Implement explicit, bounded read semantics:

```python
class ReadMode(Enum):
    UNTIL_TERMINATOR = ...
    EXACT_LENGTH = ...
    UP_TO_LENGTH = ...
    AVAILABLE = ...
    BACKEND_DEFINED_MESSAGE = ...
```

Suggested model:

```python
@dataclass(frozen=True)
class ReadRequest:
    mode: ReadMode
    length: int | None = None
    terminator: bytes | None = None
    include_terminator: bool = False
    maximum_size: int = 1_048_576
```

Unbounded reads are prohibited.

---

# 11. Required transports

Implement:

```text
VisaTransport
SerialTransport
TcpTransport
UdpTransport
MockTransport / ScriptedScpiTransport
```

The reason UDP is included is the existing N83624 driver, which supports TCP, UDP, channel-specific UDP, RS232, and an emulator.

## 11.1 VISA

Use PyVISA as an optional dependency. Support the common VISA resource classes used by the source drivers:

```text
GPIB
USBTMC
TCPIP::INSTR
TCPIP::SOCKET
ASRL via VISA where selected by a concrete driver
```

Requirements:

- no PyVISA runtime dependency unless `[visa]` is installed;
- preserve binary data exactly;
- use finite timeouts;
- deterministic close;
- backend exception translation with exception chaining;
- no device query in the constructor;
- no implicit resource enumeration.

## 11.2 Serial

Use pyserial as an optional dependency. Support configuration equivalent to:

```python
SerialTransport(
    port="COM5",
    baudrate=9600,
    timeout_s=5.0,
    write_timeout_s=5.0,
    bytesize=8,
    parity="N",
    stopbits=1,
)
```

Support DTR/RTS and input/output flush where available. Do not add SCPI terminators at transport level.

## 11.3 TCP

Implement raw socket transport with finite connect/read/write timeout, remote-disconnect detection, partial-write handling, byte preservation, optional TCP_NODELAY, and deterministic close. Never insert a newline automatically.

## 11.4 UDP

Treat datagrams as datagrams, not a stream. Provide bounded request/response support, maximum datagram size, optional local bind, and optional source-endpoint validation. Do not automatically retry state-changing datagrams.

---

# 12. SCPI text codec

Implement a text layer above byte transports:

```python
@dataclass(frozen=True)
class ScpiTextCodec:
    encoding: str = "ascii"
    command_terminator: bytes = b"\n"
    response_terminator: bytes | None = b"\n"
```

Requirements:

- explicit encoding;
- strict decode by default;
- append outbound terminator exactly once;
- strip only the exact configured final response terminator;
- never use generic `.strip()` or `.rstrip()` on raw protocol data;
- support no terminator;
- enforce maximum command and response sizes;
- binary operations bypass the text codec.

---

# 13. `ScpiClient`

Implement the main high-level reusable component:

```python
class ScpiClient:
    ...
```

Required behavior/API:

```python
write(command: str) -> None
query(command: str) -> str
write_bytes(data: bytes) -> None
read_bytes(request: ReadRequest) -> bytes
transact_bytes(outbound: bytes, response: ReadRequest) -> bytes
query_float(command: str) -> float
query_int(command: str) -> int
query_bool(command: str) -> bool
query_csv(command: str) -> list[str]
query_binary_block(command: str) -> bytes
write_binary_block(command_prefix: str, payload: bytes) -> None
```

All SCPI traffic must pass through one execution choke point so locking, timing, tracing, timeout handling, and exception translation are consistent.

The client must not automatically drain the instrument error queue unless a concrete driver enables such a policy.

---

# 14. IEEE-488.2 common helpers

Provide a reusable helper for common commands:

```python
class Ieee4882:
    def identify(self) -> Identity: ...
    def clear_status(self) -> None: ...
    def reset(self) -> None: ...
    def operation_complete(self) -> bool: ...
    def wait_operation_complete(self, timeout_s: float) -> None: ...
    def wait(self) -> None: ...
    def trigger(self) -> None: ...
    def self_test(self) -> SelfTestResult: ...
    def read_status_byte(self) -> int: ...
    def read_event_status(self) -> int: ...
```

Typical commands:

```text
*IDN?
*CLS
*RST
*OPC?
*OPC
*WAI
*TRG
*TST?
*STB?
*ESR?
```

Do not assume every instrument supports every helper. Concrete drivers decide what to expose and use.

---

# 15. Identity

Implement:

```python
@dataclass(frozen=True)
class Identity:
    manufacturer: str
    model: str
    serial_number: str | None
    firmware_version: str | None
    raw: str
```

Provide tolerant parsing of conventional comma-separated `*IDN?` replies. The core parses; the concrete driver validates manufacturer/model/firmware compatibility.

---

# 16. Connection health versus transport state

Represent these independently.

A session can validly report:

```text
transport open = True
communication_ok = False
```

Suggested model:

```python
@dataclass
class SessionHealth:
    connected: bool
    communication_ok: bool | None
    last_success_monotonic: float | None
    last_failure_monotonic: float | None
    last_error: ScpiDriverError | None
```

A health check may use a concrete-driver-selected safe query, commonly `*IDN?`, but transport `is_open` must never perform device I/O.

---

# 17. Named sessions and aliases

Most source drivers support multiple aliases. Implement a framework-independent registry:

```python
class SessionRegistry:
    def register(self, alias, session): ...
    def get(self, alias): ...
    def remove(self, alias): ...
    def set_active(self, alias): ...
    def get_active(self): ...
    def list_aliases(self): ...
    def list_sessions(self): ...
    def disconnect(self, alias): ...
    def disconnect_all(self): ...
```

Rules:

- support a deterministic `default` alias;
- normalize aliases consistently;
- reject ambiguous duplicates;
- never select an arbitrary session;
- allocate a new session-generation identifier after reconnect;
- keep registry code free of Robot Framework concepts.

Implement a `ScpiSession` containing at least:

```text
alias
ScpiClient
transport ownership
identity cache
SessionHealth
generation ID
per-session operation lock
timeout/retry policy
trace context
```

Do not store instrument-specific output or measurement state in the generic session.

---

# 18. Connection lifecycle

Provide reusable infrastructure for the common lifecycle:

```text
normalize request
create transport
open transport
create SCPI client/session
perform bounded communication probe
optionally identify
allow concrete driver to validate identity
publish/register session
operate
close/disconnect deterministically
```

A partial connection failure must release all acquired resources.

A failed hardware connection must never silently fall back to simulation.

---

# 19. Common exceptions

Implement a hierarchy equivalent to:

```python
class ScpiDriverError(Exception): ...
class ConfigurationError(ScpiDriverError): ...
class TransportError(ScpiDriverError): ...
class NotConnectedError(TransportError): ...
class TransportTimeoutError(TransportError): ...
class ProtocolError(ScpiDriverError): ...
class ResponseParseError(ProtocolError): ...
class ScpiCommandError(ProtocolError): ...
class ScpiErrorQueueError(ScpiDriverError): ...
class IdentityError(ScpiDriverError): ...
class OperationTimeoutError(ScpiDriverError): ...
class UnsupportedOperationError(ScpiDriverError): ...
class SafetyGuardError(ScpiDriverError): ...
```

Preserve original backend exceptions with `raise ... from exc`.

Concrete drivers may subclass these errors.

Keep transport failures, protocol parsing failures, and device-reported SCPI errors distinct.

---

# 20. SCPI error queue

Centralize the repeated `SYST:ERR?` behavior:

```python
class ScpiErrorQueue:
    def read_one(self) -> ScpiError: ...
    def drain(self, max_entries: int = 32) -> list[ScpiError]: ...
    def raise_if_errors(self) -> None: ...
```

Requirements:

- configurable query command;
- parse common `code,"message"` replies;
- configurable no-error codes, normally including 0;
- retain raw response;
- bounded maximum drain count;
- fail if the queue never reaches a no-error result;
- do not automatically consume the queue after every operation unless enabled by a concrete driver.

Provide an execution policy similar to:

```python
@dataclass(frozen=True)
class ScpiExecutionPolicy:
    check_error_queue_after_write: bool = False
    check_error_queue_after_query: bool = False
```

---

# 21. Generic response parsing

Provide reusable parsers:

```python
parse_float(...)
parse_int(...)
parse_bool(...)
parse_csv(...)
parse_identity(...)
parse_scpi_error(...)
parse_optional_unit_float(...)
quote_scpi_string(...)
```

`parse_optional_unit_float()` must accept both forms such as:

```text
500.0
500.0 V
```

This is required by real-device behavior already observed in the source driver set.

Rules:

- reject malformed values visibly;
- reject NaN/Inf by default unless explicitly permitted;
- never silently convert invalid values to zero;
- include the raw response in parse errors;
- device-specific overload sentinels remain device-specific;
- use CSV-aware parsing rather than naive `.split(",")` when quoted fields are possible.

---

# 22. Engineering-value parsing

Provide an optional framework-independent utility for human-friendly values such as:

```text
12V
500mA
10uA
2.2k
500ms
```

Requirements:

- deterministic SI-prefix behavior;
- documented case rules;
- reject incompatible or ambiguous units;
- no Robot Framework dependency;
- preferably return a structured parsed result including numeric value and normalized unit/dimension.

---

# 23. IEEE-488.2 definite-length binary blocks

This is mandatory for scope/waveform/file use cases.

Implement generation and parsing of:

```text
#<n><length><payload>
```

Required helpers:

```python
encode_definite_length_block(payload: bytes) -> bytes
read_definite_length_block(
    transport: Transport,
    *,
    timeout_s: float,
    maximum_size: int,
) -> bytes
```

Requirements:

- validate header and digit count;
- validate declared payload length;
- preserve every payload byte including whitespace and zero bytes;
- no `.strip()`;
- detect truncation;
- bounded maximum size;
- optional trailing terminator support;
- useful typed exceptions.

`ScpiClient.query_binary_block()` and `write_binary_block()` must use this implementation.

---

# 24. Polling, completion, and deadlines

Implement a generic bounded polling helper using monotonic time:

```python
poll_until(predicate, *, timeout_s, interval_s, clock=...)
```

Provide `wait_operation_complete()` for `*OPC?`-style use.

Requirements:

- no infinite loops;
- use monotonic deadlines;
- report elapsed/timeout information;
- permit deterministic fake-clock testing;
- avoid long uninterruptible fixed sleeps where polling is possible.

---

# 25. Retry and replay policy

Implement:

```python
@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 1
    initial_delay_s: float = 0.0
    backoff: float = 1.0

class ReplayPolicy(Enum):
    NEVER = ...
    SAFE = ...
```

Rules:

- one attempt is the default;
- safe queries may be explicitly retried;
- writes are not retried automatically;
- never replay a transaction after data may have reached the device unless the caller explicitly classifies it safe;
- record attempts in tracing;
- preserve the final exception.

---

# 26. Transaction serialization

Every SCPI session must have a per-session operation/transaction lock.

Guarantee that:

```text
query write+read remains atomic
binary transfers do not interleave
two writes do not interleave at byte level
an associated error-queue check cannot be consumed by another thread
```

The package need not claim every concrete driver is fully thread-safe, but the transport/protocol boundary must serialize individual operations deterministically.

---

# 27. Tracing and protocol audit

Define a framework-independent observer:

```python
class TraceObserver(Protocol):
    def on_event(self, event: ProtocolTraceEvent) -> None: ...
```

Trace records should include:

```text
UTC timestamp
monotonic timestamp/duration
session alias
session generation ID
operation ID
direction: OPEN/CLOSE/TX/RX/ERROR
raw bytes
decoded text when valid
transport descriptor
success/failure
exception category
sequence number
```

Provide a transparent instrumentation layer around the transport or client so concrete drivers do not each reimplement tracing.

Provide `JsonlTraceSink` with:

- append-only JSONL;
- schema version;
- sequence number;
- timestamps;
- operation/session correlation;
- deterministic binary representation, e.g. base64 or hex;
- finite flush/finalization;
- redaction hook.

This is protocol-level audit infrastructure, not the entire RFDS-008 test-run evidence framework.

---

# 28. Redaction

Provide a redaction protocol/callback. Never assume all SCPI traffic is safe to persist.

Example:

```python
class Redactor(Protocol):
    def redact_command(self, command: str) -> str: ...
    def redact_response(self, response: str) -> str: ...
```

Concrete drivers remain responsible for configuring redaction for calibration security codes, passwords, private network settings, or sensitive strings.

---

# 29. Confirmation guards

Several source drivers protect raw SCPI and calibration functionality. Provide a reusable mechanism, not policy:

```python
class ConfirmationGuard:
    ...
```

Example:

```python
raw_guard = ConfirmationGuard("ENABLE RAW SCPI")
raw_guard.enable("ENABLE RAW SCPI")
raw_guard.require_enabled()
raw_guard.disable()
```

Requirements:

- guard state is scoped to the driver/session as selected by the concrete driver;
- no global mutable authorization;
- calibration should use a separate guard instance and phrase;
- the core does not decide which operations require a guard.

---

# 30. Simulation and testing transport

Implement a first-class scripted transport usable by concrete device simulators:

```python
class ScriptedScpiTransport:
    ...
```

It must support:

```text
open/close state
command history
exact command handlers
predicate/regex handlers
text replies
binary replies
binary-block replies
forced timeout
forced disconnect
malformed response
delayed response
SCPI error-queue behavior
```

Concrete instrument simulators remain in their own packages and may build on this reusable transport.

---

# 31. Base class: optional and small

A convenience `ScpiDriverBase` may be provided, but it must not become the architectural center or a deep inheritance tree.

Suitable responsibilities:

```text
session registry
session construction
identity/communication helper
communication timeout access
disconnect/disconnect_all
raw-SCPI plumbing hooks
tracing access
```

Avoid inheritance such as:

```text
BaseInstrument
  -> ScpiInstrument
    -> PowerSupply
      -> ProgrammablePowerSupply
        -> SpecificModel
```

Composition must remain the preferred design.

---

# 32. Common Python lifecycle API

The shared infrastructure should make it straightforward for concrete drivers to expose equivalent Python operations:

```text
connect
disconnect
disconnect_all
is_connected
check_communication
get_identity
get_connection_state
list_connections
set_active_session
get_active_session
set_communication_timeout
get_communication_timeout
```

These are Python services/methods, not Robot Framework keywords.

---

# 33. Framework boundary

No runtime code may import:

```text
robot
hardpy
pytest
```

Robot support remains a thin adapter in each current driver package until/unless a separate reusable adapter package proves useful.

HardPy should normally use the concrete driver directly through pytest fixtures.

---

# 34. Test-verdict boundary

Do not centralize assertions such as:

```text
Voltage Should Be Within Range
Current Should Be Within Range
Measurement Should Be Within
```

The core may provide measurement parsing and polling. The test framework/test procedure owns limits and verdicts.

---

# 35. Safety boundary

The core may provide generic mechanisms:

```text
finite timeouts
confirmation guards
safe replay classification
cleanup infrastructure
typed errors
```

Concrete drivers own:

```text
voltage/current/power limits
output enable/disable policy
channel arming
short-circuit authorization
calibration authorization
persistent-memory write authorization
instrument-specific safe shutdown
```

Software abstractions do not replace hardware interlocks, fuses, emergency stops, wiring review, or DUT protection.

---

# 36. Repository structure

Target structure:

```text
scpi-driver-core/
|
+-- pyproject.toml
+-- README.md
+-- LICENSE
+-- CHANGELOG.md
+-- CONTRIBUTING.md
+-- .gitignore
|
+-- .github/
|   +-- workflows/
|       +-- ci.yml
|
+-- src/
|   +-- scpi_driver_core/
|       +-- __init__.py
|       +-- py.typed
|       +-- exceptions.py
|       +-- models.py
|       +-- base.py
|       |
|       +-- transport/
|       |   +-- __init__.py
|       |   +-- base.py
|       |   +-- models.py
|       |   +-- visa.py
|       |   +-- serial.py
|       |   +-- tcp.py
|       |   +-- udp.py
|       |   +-- mock.py
|       |
|       +-- scpi/
|       |   +-- __init__.py
|       |   +-- client.py
|       |   +-- codec.py
|       |   +-- parsers.py
|       |   +-- errors.py
|       |   +-- ieee488.py
|       |   +-- binary_block.py
|       |   +-- engineering.py
|       |
|       +-- session/
|       |   +-- __init__.py
|       |   +-- session.py
|       |   +-- registry.py
|       |   +-- health.py
|       |
|       +-- execution/
|       |   +-- __init__.py
|       |   +-- retry.py
|       |   +-- polling.py
|       |   +-- guards.py
|       |
|       +-- tracing/
|       |   +-- __init__.py
|       |   +-- events.py
|       |   +-- observer.py
|       |   +-- instrumented.py
|       |   +-- jsonl.py
|       |   +-- redaction.py
|       |
|       +-- simulation/
|           +-- __init__.py
|           +-- scripted.py
|
+-- tests/
|   +-- unit/
|   +-- transport_contract/
|   +-- integration/
|
+-- examples/
+-- docs/
+-- task/
    +-- SCPI_DRIVER_CORE_IMPLEMENTATION_TASK.md
```

Do not create nonfunctional backend files merely to fill the tree; add implementation modules in the phase that implements them.

---

# 37. Packaging and supported Python

Use `pyproject.toml`, PEP 517, typed package marker `py.typed`, and normal wheel/sdist builds.

Initial compatibility target:

```text
Python >= 3.10
```

This intentionally matches the migration needs of the current SCPI driver set.

CI should cover at least 3.10–3.13. Add 3.14 when all runtime/dev dependencies used by the project support it reliably.

Optional extras:

```toml
visa = ["pyvisa>=1.14"]
serial = ["pyserial>=3.5"]
all = ["pyvisa>=1.14", "pyserial>=3.5"]
```

TCP and UDP should use the standard library.

---

# 38. Public import surface

Keep common imports stable and shallow:

```python
from scpi_driver_core import ScpiClient, ScpiSession, SessionRegistry
```

```python
from scpi_driver_core.transport import (
    Transport,
    VisaTransport,
    SerialTransport,
    TcpTransport,
    UdpTransport,
    MockTransport,
)
```

```python
from scpi_driver_core.scpi import (
    Ieee4882,
    ScpiErrorQueue,
    encode_definite_length_block,
    parse_float,
    parse_bool,
)
```

Do not force users to import normal public features from deep implementation modules.

---

# 39. Logging rules

Use standard Python logging. Package code must not call `logging.basicConfig()` or configure the root logger.

Protocol traffic should primarily use the explicit trace/audit interfaces rather than INFO-level normal logging.

Do not log secrets or sensitive configuration without passing through redaction.

---

# 40. Testing requirements

Use pytest as a development dependency only.

## Transport contract tests

Create reusable tests for all applicable transports:

```text
open
close
double close
reopen
state transitions
I/O while closed
fault transition
timeout
partial write
read size limits
transaction serialization
```

## Codec tests

Cover:

```text
terminator append
no double terminator
strict decoding
exact terminator removal
empty response
malformed encoding
maximum response size
```

## Parser tests

Cover:

```text
float/scientific notation
optional unit suffix
integer
boolean forms
quoted CSV
identity variants
SCPI errors
malformed responses
NaN/Inf policy
```

## Binary block tests

Cover:

```text
normal block
zero-length block
large block
invalid header
invalid digit count
truncated payload
maximum-size rejection
trailing terminator
payload containing whitespace and zero bytes
```

## Session tests

Cover:

```text
alias registration
active alias
duplicate alias
disconnect
disconnect_all
reconnect generation
transport-open vs communication-health distinction
```

## Retry tests

Cover:

```text
one attempt default
safe query retry
non-retryable write
backoff
final exception
trace of attempts
```

## Trace tests

Cover:

```text
TX/RX/open/close/error events
binary payload representation
operation IDs
session aliases
ordering/sequence
JSONL serialization
redaction
```

Default CI must not require physical hardware or an external network endpoint.

Target meaningful statement coverage: **>= 90%**.

---

# 41. Quality gates

CI must run equivalent checks:

```bash
ruff check .
ruff format --check .
mypy src
pytest --cov=scpi_driver_core
python -m build
```

Requirements:

- all public APIs typed;
- public APIs documented;
- no dead code;
- no hidden global mutable state;
- no framework coupling;
- no silent communication failure;
- no infinite timeout;
- no speculative abstraction without demonstrated reuse.

---

# 42. Representative migration validation

Do not declare the architecture stable after one trivial driver.

Validate against at least these five representative drivers:

## A. Agilent 34411A

Validates:

```text
VISA
large SCPI surface
measurement parsing
trigger/sample control
instrument memory
error handling
raw/calibration guards
multi-session
```

## B. Tektronix TBS1000C

Validates:

```text
VISA/USBTMC
IEEE-488.2 binary blocks
waveform transfers
setup/file transfers
trigger/acquisition
```

## C. Keysight N6700

Validates:

```text
VISA
raw TCP socket
multi-channel instrument
multi-session
strict SCPI error checking
self-test/module discovery
protocol audit
```

## D. NGI N83624

Validates:

```text
TCP
UDP
RS232
emulator
multiple aliases
communication health
raw SCPI
```

## E. EA PS9000T

Validates:

```text
VISA
remote-control handling above the core
tolerant numeric parsing with optional unit suffix
device error queue
multi-session
```

The architecture is acceptable only if these migrations do not require manufacturer-specific code inside `scpi-driver-core`.

Secondary validation:

```text
Agilent 33220A
HP 34401A
E-Resistor SCPI path
BK8500B SCPI-facing path where actually applicable
```

---

# 43. Migration rule

Migration must be an architecture extraction, not a simultaneous feature rewrite.

During each driver migration:

- preserve existing public behavior;
- preserve tested SCPI command mappings;
- preserve safety policy;
- preserve error semantics;
- preserve simulator and HIL evidence where relevant;
- move only generic duplicated infrastructure;
- keep Robot keywords compatible until a separate deliberate API change;
- add direct Python tests for the framework-independent driver core.

---

# 44. Strong candidates for generic extraction

The following repeated behaviors should be evaluated first:

```text
open/close transport
connection state
communication health
*IDN? and identity parsing
named aliases
active alias
list connections
communication timeout
raw write/query
protocol tracing
SYST:ERR? parsing/draining
strict error check
*CLS
*RST
*OPC?
*WAI
*TST?
*TRG
SCPI boolean parsing
SCPI numeric parsing
optional unit suffix parsing
quoted CSV parsing
binary block encoding/decoding
safe query retry
bounded polling
JSONL session audit
scripted simulator transport
confirmation guards
```

---

# 45. Functions that must not become generic merely because names match

Examples:

```text
Set Voltage
Set Current
Set Power
Enable Output
Disable Output
Configure Trigger
Configure Sweep
Set Measurement Range
Run Calibration
Save/Restore Setup
Set LAN IP
Clear Protection
Arm Channel Output
Measure Temperature
Load Arbitrary Waveform
```

These operations can have different command trees, state transitions, safety semantics, constraints, and side effects. The core should provide primitives, not pretend their instrument semantics are universal.

---

# 46. First release scope

Target release:

```text
v0.1.0
```

Required before v0.1.0:

```text
byte Transport protocol
transport models/state
TCP
UDP
Serial
VISA
Mock/Scripted transport
SCPI text codec
ScpiClient
identity parser
generic numeric/int/bool/CSV parsers
optional-unit numeric parser
IEEE-488.2 helpers
SCPI error queue
binary block encode/decode
session registry
communication health
timeout/deadline handling
safe retry/replay policy
polling
transaction lock
trace observer
JSONL trace sink
redaction hook
confirmation guard
documentation
CI
```

Deferred unless migration proves necessary:

```text
HTTP/REST
CAN
Modbus
vendor SDKs
full RFDS-008 run-evidence engine
RFDS plugin registry
GUI
Robot Framework base library
HardPy plugin
universal electrical capability interfaces
test assertions
measurement database
distributed resource locking
async API
remote instrument service
```

---

# 47. Implementation phases

Implement in small reviewable phases and commit each phase after tests and static checks pass.

## Phase 1 — repository/package skeleton

Already bootstrapped in this repository. Keep it minimal and buildable.

## Phase 2 — core models and exceptions

Implement:

```text
TransportState
TransportDescriptor
ReadRequest
ReadMode
WriteResult
FlushDirection
ReplayPolicy
exception hierarchy
```

## Phase 3 — Mock transport and transport contract

Define the architecture against a deterministic fake first. Build reusable transport-contract tests.

## Phase 4 — SCPI codec and parsers

Implement text codec, identity, float/int/bool/CSV, SCPI error parser, optional-unit parser, engineering-value parser.

## Phase 5 — `ScpiClient`

Implement text and byte operations, typed query helpers, operation IDs, transaction locking.

## Phase 6 — TCP and UDP

Implement socket transports plus local simulated endpoint tests.

## Phase 7 — Serial

Implement optional pyserial backend and backend-mocked tests.

## Phase 8 — VISA

Implement optional PyVISA backend and backend-mocked tests.

## Phase 9 — IEEE-488.2 helpers

Implement identity/common command service and bounded OPC handling.

## Phase 10 — binary blocks

Implement strict IEEE-488.2 definite-length block read/write support.

## Phase 11 — error queue and execution policy

Implement `ScpiErrorQueue`, strict-check policy, retry/replay, polling/deadline helpers.

## Phase 12 — session/runtime

Implement `ScpiSession`, `SessionRegistry`, `SessionHealth`, active alias, disconnect-all and reconnect generation.

## Phase 13 — tracing/audit

Implement observer, instrumentation layer, JSONL sink and redaction.

## Phase 14 — scripted simulation

Implement reusable `ScriptedScpiTransport` suitable as a foundation for device-specific simulators.

## Phase 15 — representative driver migration/prototypes

Validate with:

```text
Agilent 34411A
TBS1000C
Keysight N6700
NGI N83624
EA PS9000T
```

Do not add vendor-specific behavior to the core to make a migration easier.

## Phase 16 — architecture review

Review duplicated code remaining across migrated drivers. Extract only abstractions proven reusable by multiple implementations.

## Phase 17 — release

Create `v0.1.0` only after acceptance criteria below are met.

---

# 48. Acceptance criteria

## Framework independence

- [ ] no Robot Framework runtime dependency
- [ ] no HardPy runtime dependency
- [ ] no pytest runtime dependency
- [ ] usable directly from plain Python

## Transport

- [ ] canonical boundary uses `bytes`
- [ ] VISA backend implemented
- [ ] Serial backend implemented
- [ ] TCP backend implemented
- [ ] UDP backend implemented
- [ ] Mock/Scripted backend implemented
- [ ] explicit transport state model
- [ ] deterministic idempotent close
- [ ] all I/O bounded
- [ ] transaction serialization implemented

## SCPI/IEEE-488.2

- [ ] text codec implemented
- [ ] `write()` and `query()` implemented
- [ ] typed query helpers implemented
- [ ] identity parser implemented
- [ ] IEEE-488.2 helpers implemented
- [ ] SCPI error queue implemented
- [ ] definite-length binary block encode/decode implemented
- [ ] arbitrary binary bytes preserved exactly

## Runtime

- [ ] named sessions
- [ ] deterministic active session
- [ ] list sessions
- [ ] disconnect all
- [ ] reconnect generation IDs
- [ ] transport-open state separated from communication health
- [ ] finite timeouts/deadlines
- [ ] safe retry rules
- [ ] bounded polling

## Diagnostics

- [ ] trace observer
- [ ] OPEN/CLOSE/TX/RX/ERROR events
- [ ] operation/session correlation
- [ ] JSONL sink
- [ ] redaction hook
- [ ] command history in scripted simulation

## Quality

- [ ] meaningful unit coverage >= 90%
- [ ] ruff passes
- [ ] formatting check passes
- [ ] mypy passes
- [ ] wheel builds
- [ ] sdist builds
- [ ] `py.typed` included
- [ ] CI passes on supported Python versions

## Migration proof

- [ ] Agilent 34411A works through the core
- [ ] TBS1000C binary transfers work through the core
- [ ] N6700 VISA and TCP paths work through the core
- [ ] N83624 TCP/UDP/serial paths work through the core
- [ ] EA PS9000T works without EA-specific code in the core
- [ ] existing Robot adapters can call migrated drivers
- [ ] HardPy/pytest can call the same migrated drivers without Robot dependency

---

# 49. Definition of done

The package is successful when a concrete driver can be structured approximately as:

```python
from scpi_driver_core import ScpiClient, ScpiSession
from scpi_driver_core.transport import VisaTransport


class ExampleInstrument:
    def __init__(self, resource: str):
        transport = VisaTransport(resource=resource, timeout_s=5.0)
        client = ScpiClient(transport)
        self.session = ScpiSession(alias="default", client=client)

    def connect(self) -> None:
        self.session.open()

    def identify(self):
        return self.session.ieee488.identify()

    def measure_voltage(self) -> float:
        return self.session.client.query_float("MEAS:VOLT?")
```

and that same concrete driver is reusable unchanged from:

```text
Robot Framework
HardPy
pytest
plain Python
Jupyter
CLI applications
```

The core must eliminate duplicated SCPI/transport/runtime infrastructure without becoming a universal instrument framework or absorbing device-specific behavior.

---

# 50. Architectural summary

Use:

```text
byte-oriented transports
        +
SCPI text/client layer
        +
IEEE-488.2 helpers
        +
binary block support
        +
SCPI error queue
        +
named session registry
        +
communication health
        +
safe retry/polling
        +
trace/simulator infrastructure
```

Keep outside:

```text
device semantics
device safety policy
Robot Framework
HardPy
test assertions
vendor SDKs
non-SCPI protocols
```

The intended result is a focused, reusable foundation for the SCPI drivers already present in `RobotFrameworks_hw_drivers`, reducing duplicated code while enabling migration from Robot Framework-specific implementations toward framework-independent Python drivers.
