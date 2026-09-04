# AI Code Generation Task: Production Python Driver for Keysight N6700 Modular Power System

**Version:** 1.4  
**Update:** Implemented final v1.3 review findings: corrected `parse_error()` return type, clarified type-specific tests, marked flat SMU/load APIs as optional wrappers, added example energizing-safety rule, and strengthened electronic-load exact-model/source requirements.

## 1. Objective

Generate a production-grade Python package that controls a Keysight/Agilent Series N6700 low-profile modular power system mainframe over SCPI. The driver must support N6700-family mainframes with up to four independently addressed output channels and must provide safe, typed, well-tested APIs for:

- Standard DC power supply modules
- Electronic load modules
- SMU modules
- Mixed-module mainframes where different channels contain different module types

The generated software must be suitable for industrial 24/7 automation use, including robust error handling, deterministic safety behavior, logging, retries, timeouts, clean shutdown, and testability without real hardware.

## 2. Source Documentation

Use the uploaded Keysight Series N6700 Programmer’s Reference Guide as the primary SCPI reference for the N6700B/N6701A/N6702A mainframes. Implement all features only when command syntax and behavior are verified from official Keysight documentation.

Important note: the uploaded N6700B Programmer’s Reference Guide is an older reference and clearly covers standard power modules and N678xA SMU commands. Electronic-load-specific support must be implemented from the latest official Keysight documentation for the relevant load modules before coding. If a command is not verified, the driver must not silently guess it; it must raise `UnsupportedFeatureError` or mark the feature as unavailable in the channel capability model.

## 3. Required Package Name and Structure

Create an installable Python package named:

```text
keysight_n6700
```

Recommended structure:

```text
keysight_n6700/
  pyproject.toml
  README.md
  LICENSE
  CHANGELOG.md
  keysight_n6700/
      __init__.py
      driver.py
      channel.py
      transport.py
      scpi.py
      capabilities.py
      modules.py
      exceptions.py
      logging_utils.py
      datalog.py
      types.py
      simulator.py
      py.typed
  examples/
    basic_power_supply.py
    all_channels_measurement.py
    smu_voltage_priority.py
    smu_current_priority.py
    electronic_load_cc_mode.py
    electronic_load_cv_mode.py
    log_measurements_to_csv.py
    list_mode_example.py
    triggered_measurement_example.py
    ethernet_connection.py
    usb_connection.py
  tests/
    unit/
    integration/
    simulator/
  docs/
    index.md
    installation.md
    connection.md
    api_reference.md
    safety.md
    module_support.md
    examples.md
```

Use `pyproject.toml` with modern packaging. The package must be installable with:

```bash
pip install .
pip install -e ".[dev]"
```

## 4. Python and Dependency Requirements

Support:

- Python 3.10+
- Windows and Linux
- USBTMC via PyVISA
- Ethernet/LAN via PyVISA TCPIP resources and optional raw socket transport
- Optional Keysight VISA / NI-VISA / pyvisa-py backends

Runtime dependencies must be minimal.

Required runtime dependencies:

- `pyvisa`
- `typing_extensions` only when needed for older supported Python versions
- Python standard-library `dataclasses` where possible; use `pydantic` only if justified and kept optional

Development dependencies must be placed only in the `dev` optional extra:

- `pytest`
- `pytest-cov`
- `ruff`
- `mypy`
- `types-setuptools` or other type-stub packages if needed

Documentation dependencies must be placed only in the `docs` optional extra:

- `mkdocs`, `mkdocs-material`, `mkdocstrings[python]`
- or `sphinx` and required Sphinx extensions

Optional data-analysis dependencies must be placed only in a separate optional extra:

- `pandas` for CSV/log reading examples

Required `pyproject.toml` style:

```toml
[project]
name = "keysight-n6700"
requires-python = ">=3.10"
dependencies = [
  "pyvisa>=1.14",
  "typing_extensions>=4.8; python_version < '3.11'",
]

[project.optional-dependencies]
dev = [
  "pytest",
  "pytest-cov",
  "ruff",
  "mypy",
  "types-setuptools",
]
docs = [
  "mkdocs",
  "mkdocs-material",
  "mkdocstrings[python]",
]
pandas = [
  "pandas",
]
```

Rules:

- `pytest`, `pytest-cov`, `ruff`, and `mypy` must not be runtime dependencies.
- `pandas` must not be a mandatory runtime dependency.
- Documentation-generation packages must not be mandatory runtime dependencies.
- Examples that require optional extras must state the install command.

## 5. Transport Requirements

Implement a transport abstraction so the core driver is independent of the communication backend.

### 5.1 Base transport API

Create a `Transport` protocol or abstract class with:

```python
write(command: str) -> None
query(command: str) -> str
read_raw() -> bytes
write_raw(data: bytes) -> None
clear() -> None
close() -> None
is_open: bool
supports_clear: bool
```

`clear()` capability requirements:

- `supports_clear` must indicate whether device clear / interface clear is truly supported by the backend.
- `clear()` must raise `UnsupportedFeatureError` if clear is unavailable.
- Raw TCP socket transport must not fake a device clear unless an officially verified clear mechanism is implemented.
- Recovery code must check `supports_clear` before attempting a clear.
- Tests must cover transports with and without clear capability.

### 5.2 PyVISA transport

Implement `PyVisaTransport` supporting resource strings such as:

```text
USB0::0x0957::...::INSTR
TCPIP0::192.168.0.100::inst0::INSTR
TCPIP0::192.168.0.100::5025::SOCKET
```

Transport must allow configuration of:

- timeout
- termination characters
- query delay
- chunk size
- retry count
- backend selection
- command locking, enabled by default at driver level

### 5.3 Ethernet socket transport

Implement optional raw socket transport for LAN socket operation:

- default SCPI socket port: 5025
- newline command termination
- deterministic timeout handling
- reconnect support only when safe and explicitly configured
- `supports_clear=False` unless official clear behavior is implemented and verified

### 5.4 Connection helpers

Provide user-friendly constructors:

```python
N6700.connect_usb(resource: str, **options)
N6700.connect_ethernet(host: str, port: int = 5025, **options)
N6700.connect_visa(resource: str, **options)
```

## 6. Main Driver API

Create a main class:

```python
class N6700:
    ...
```

Required behavior:

- Open and close communication safely.
- Support context-manager usage.
- Be non-invasive by default.
- Do not issue `*RST` automatically on connection.
- Do not enable, disable, reset, clear protection, recall state, or write nonvolatile memory on connection.
- Query and validate `*IDN?` during connection.
- Query installed channel count with `SYSTem:CHANnel:COUNt?`.
- Query module model per channel with `SYSTem:CHANnel:MODel?`.
- Query module options with `SYSTem:CHANnel:OPTion?`.
- Query module serial number with `SYSTem:CHANnel:SERial?`.
- Query channel descriptions using `*RDT?` when useful.
- Build a per-channel capability model from module model and options.
- Reject channel numbers outside the installed range.
- Support channel lists for single channel, explicit list, and ranges.
- Use command locking enabled by default.

Required methods:

```python
idn() -> InstrumentIdentity
reset() -> None
clear_status() -> None
self_test() -> SelfTestResult
get_error() -> ScpiErrorRecord
drain_errors() -> list[ScpiErrorRecord]
operation_complete(timeout: float | None = None) -> bool
wait() -> None
status_byte() -> int
standard_event_status() -> int

get_remote_state() -> RemoteState
set_remote_state(state: Literal["local", "remote", "remote_lockout"]) -> None
remote_lockout(enabled: bool) -> None  # compatibility wrapper around set_remote_state

channel_count() -> int
channel_model(channel: int) -> str
channel_options(channel: int) -> list[str]
channel_serial(channel: int) -> str

channel(channel: int) -> BaseChannel
get_channel(channel: int) -> BaseChannel
power_supply(channel: int) -> PowerSupplyChannel
smu(channel: int) -> SMUChannel
load(channel: int) -> ElectronicLoadChannel
channels: Mapping[int, BaseChannel]

write_scpi(command: str) -> None
query_scpi(command: str) -> str
shutdown_all() -> ShutdownResult
close() -> None
```

Remote/local requirement:

- `remote_lockout(enabled)` may exist only as a compatibility convenience wrapper.
- The primary API must be `get_remote_state()` and `set_remote_state(...)`.
- If remote/local operation is backend-specific or unavailable, the driver must expose that through transport capabilities and raise `UnsupportedFeatureError` where appropriate.

## 7. Channel API

The driver must use type-specific channel objects or type-safe adapters. A single generic `Channel` class with power-supply, SMU, and electronic-load methods mixed together is not acceptable as the primary public API.

### 7.1 Base channel API

Create a `BaseChannel` for operations that are safe and meaningful for all supported module types:

```python
class BaseChannel:
    channel: int
    capabilities: ChannelCapabilities

    measure_voltage() -> float
    measure_current() -> float
    measure_power() -> PowerMeasurement
    measure() -> Measurement

    fetch_voltage() -> float
    fetch_current() -> float
    fetch_power() -> PowerMeasurement
    fetch() -> Measurement

    get_status_snapshot() -> ChannelStatusSnapshot
    get_protection_status() -> ProtectionStatus

    clear_protection(
        *,
        restore_output: bool = False,
        force_output_off_first: bool = True,
        verify_cleared: bool = True,
    ) -> ProtectionClearResult
```

Do not put `output_on()`, `output_off()`, `input_on()`, `input_off()`, generic `set_current()`, or generic `set_output()` on `BaseChannel`.

### 7.2 Power supply channel API

Create `PowerSupplyChannel(BaseChannel)`:

```python
output_on() -> None
output_off() -> None
set_output(enabled: bool) -> None
get_output() -> bool

set_voltage_setpoint(value: float, *, voltage_range: float | str | None = None) -> None
get_voltage_setpoint() -> float

set_current_limit(value: float, *, current_range: float | str | None = None) -> None
get_current_limit() -> float

set_voltage_range(value: float | str) -> None
set_current_range(value: float | str) -> None
get_voltage_range() -> float
get_current_range() -> float

set_ovp(value: float) -> None
get_ovp() -> float
set_ocp(enabled: bool) -> None
get_ocp() -> bool
```

### 7.3 SMU channel API

Create `SMUChannel(BaseChannel)`:

```python
output_on() -> None
output_off() -> None
set_output(enabled: bool) -> None
get_output() -> bool

set_smu_mode(mode: Literal["voltage", "current"]) -> None
get_smu_mode() -> Literal["voltage", "current"]

set_voltage_setpoint(value: float, *, voltage_range: float | str | None = None) -> None
get_voltage_setpoint() -> float

set_current_setpoint(value: float, *, current_range: float | str | None = None) -> None
get_current_setpoint() -> float

set_voltage_limit(value: float) -> None
get_voltage_limit() -> float
set_current_limit(value: float) -> None
get_current_limit() -> float

set_smu_output_off_mode(mode: Literal["high_z", "low_z"]) -> None
get_smu_output_off_mode() -> Literal["high_z", "low_z"]
```

SMU-only methods must raise `UnsupportedFeatureError` if the installed channel is not an SMU or the exact SMU feature is not supported by that module.

### 7.4 Electronic load channel API

Create `ElectronicLoadChannel(BaseChannel)`:

```python
input_on() -> None
input_off() -> None
set_input(enabled: bool) -> None
get_input() -> bool

set_load_mode(mode: Literal["cc", "cv", "cr", "cp"]) -> None
get_load_mode() -> Literal["cc", "cv", "cr", "cp"]

set_load_current(value: float) -> None
get_load_current() -> float

set_load_voltage(value: float) -> None
get_load_voltage() -> float

set_load_resistance(value: float) -> None
get_load_resistance() -> float

set_load_power(value: float) -> None
get_load_power() -> float
```

Electronic load APIs must use `input_on/input_off`, `load_on/load_off`, or another load-specific term. Do not use `output_on/output_off` for load channels unless the official documentation for that exact module uses output terminology and the documentation explains the mapping.

### 7.5 Measurement return types

Use these measurement models:

```python
@dataclass(frozen=True)
class PowerMeasurement:
    channel: int
    power_W: float | None
    power_source: Literal["instrument", "calculated", "unavailable"]
    timestamp_iso: str
    timestamp_unix: float

@dataclass(frozen=True)
class Measurement:
    channel: int
    voltage_V: float | None
    current_A: float | None
    power_W: float | None
    power_source: Literal["instrument", "calculated", "unavailable"]
    timestamp_iso: str
    timestamp_unix: float
```

`measure_power()` may return a `PowerMeasurement`. `measure()` must return a complete `Measurement`.

If native `MEASure:POWer?` is unsupported, the driver may calculate `V * I`, but it must set `power_source="calculated"`.

### 7.6 Safety requirement

When setting voltage/current together with ranges, send coupled commands in one SCPI message where appropriate to avoid range/level conflicts.

The generated public API must not use `range` as a parameter name. Use `voltage_range` and `current_range`.

## 8. Standard Power Supply Module Support

For normal power supply channels, implement:

- Voltage setpoint
- Current limit/setpoint
- Output enable/disable
- Voltage range
- Current range
- OVP
- OCP
- Protection clear
- Output delays if supported
- Measurement of voltage/current/power where supported
- List mode where supported
- Triggered transient operation where supported
- Remote/local state handling at mainframe level

Recommended high-level method:

```python
configure_power_supply(
    channel: int,
    voltage: float,
    current_limit: float,
    *,
    voltage_range: float | str | None = None,
    current_range: float | str | None = None,
    ovp: float | None = None,
    ocp: bool | None = None,
    output: bool = False,
    verify: bool = True,
) -> None
```

Default safety policy: never enable output automatically unless `output=True` is explicitly provided.

## 9. SMU Module Support

Implement SMU support for N678xA-style modules.

The primary public API for SMU operation must be the type-specific `SMUChannel` object API described in Section 7.3. Top-level `N6700` methods that accept a `channel: int` may be provided only as convenience wrappers around the type-specific channel object methods.

Required SMU functions:

- Select voltage-priority mode
- Select current-priority mode
- Set voltage and current setpoints
- Set positive/negative current limits where supported
- Set positive voltage limits where supported
- Support source/sink operation where documented and module-capable
- Auxiliary voltage measurement input where supported, for example N6781A/N6785A
- Output resistance support where supported
- Bidirectional measurement support
- Capability detection by exact model and option

Primary channel-object API:

```python
smu = n6700.smu(channel)
smu.set_smu_mode("voltage")
smu.configure_voltage_priority(...)
smu.configure_current_priority(...)
```

Optional main-driver wrapper API:

```python
set_smu_mode(channel: int, mode: Literal["voltage", "current"]) -> None
get_smu_mode(channel: int) -> Literal["voltage", "current"]

configure_smu_voltage_priority(
    channel: int,
    voltage: float,
    current_limit: float,
    *,
    voltage_limit: float | None = None,
    output: bool = False,
    verify: bool = True,
) -> None

configure_smu_current_priority(
    channel: int,
    current: float,
    voltage_limit: float,
    *,
    output: bool = False,
    verify: bool = True,
) -> None
```

If a channel is not an SMU, SMU methods must raise `UnsupportedFeatureError`.

Safety requirement: these methods must not enable output unless `output=True` is explicitly provided.

## 10. Electronic Load Module Support

Implement support for electronic load channels when a supported load module is installed.

The primary public API for electronic-load operation must be the type-specific `ElectronicLoadChannel` object API described in Section 7.4. Top-level `N6700` methods that accept a `channel: int` may be provided only as convenience wrappers around the type-specific channel object methods.

Electronic load support is a required target feature, but electronic-load SCPI commands must not be guessed. The generated package must not contain implemented electronic-load SCPI commands unless every command appears in `docs/scpi_command_map.md` with:

- exact official Keysight source document
- exact SCPI command syntax
- exact supported module model number or option
- capability flag
- simulator test name
- hardware test name if applicable
- safety notes

Required load modes, if supported by the exact installed module and verified from official documentation:

- Constant current mode
- Constant voltage mode
- Constant resistance mode
- Constant power mode
- Input/load enable/disable
- Current, voltage, resistance, and power setpoints
- Protection settings
- Measurement of voltage/current/power
- Dynamic/list/transient operation where supported
- Safe disable/shutdown behavior

Primary channel-object API:

```python
load = n6700.load(channel)
load.set_load_mode("cc")
load.set_load_current(...)
load.input_on()
load.input_off()
```

Optional main-driver wrapper API:

```python
set_load_mode(channel: int, mode: Literal["cc", "cv", "cr", "cp"]) -> None
get_load_mode(channel: int) -> Literal["cc", "cv", "cr", "cp"]

configure_load_cc(
    channel: int,
    current: float,
    *,
    voltage_limit: float | None = None,
    power_limit: float | None = None,
    input_on: bool = False,
    verify: bool = True,
) -> None

configure_load_cv(
    channel: int,
    voltage: float,
    *,
    current_limit: float | None = None,
    power_limit: float | None = None,
    input_on: bool = False,
    verify: bool = True,
) -> None

configure_load_cr(
    channel: int,
    resistance: float,
    *,
    current_limit: float | None = None,
    power_limit: float | None = None,
    input_on: bool = False,
    verify: bool = True,
) -> None

configure_load_cp(
    channel: int,
    power: float,
    *,
    current_limit: float | None = None,
    voltage_limit: float | None = None,
    input_on: bool = False,
    verify: bool = True,
) -> None
```

If load modules are not present or command support cannot be verified for the exact installed module, load APIs must raise `UnsupportedFeatureError`.

Safety requirement: these methods must not enable load input unless `input_on=True` is explicitly provided.

## 11. Four-Channel and Multi-Channel Support

The driver must support all installed channels, up to four channels.

Requirements:

- Validate channel number 1..4.
- Support physical channel count returned by the instrument.
- Support channel-list formatting:
  - single channel: `(@1)`
  - explicit list: `(@1,3,4)`
  - range: `(@1:4)`
- Preserve query response order exactly as requested.
- Support mixed-module mainframes where channel 1 may be a power supply, channel 2 an SMU, channel 3 a load, etc.

Provide batch operations with unambiguous names:

```python
set_power_outputs(channels: Sequence[int], enabled: bool) -> None
set_load_inputs(channels: Sequence[int], enabled: bool) -> None
set_channel_enabled(channels: Sequence[int], enabled: bool) -> None
measure_all() -> dict[int, Measurement]
configure_power_outputs(configs: Mapping[int, PowerSupplyConfig]) -> None
configure_smus(configs: Mapping[int, SMUConfig]) -> None
configure_loads(configs: Mapping[int, LoadConfig]) -> None
shutdown_all() -> ShutdownResult
```

Rules:

- `set_power_outputs()` must reject electronic load channels.
- `set_load_inputs()` must reject power supply and SMU channels.
- `set_channel_enabled()` may dispatch by channel type, but must document exactly what enable means for each module type.
- `shutdown_all()` must disable power supply outputs, SMU outputs, and electronic load inputs according to module type.
- `shutdown_all()` must use a deterministic order and attempt every channel even if one channel returns an error.
- `shutdown_all()` must return a structured result listing per-channel success/failure.

## 12. Measurement and Datalogging Requirements

Implement scalar measurement:

- voltage
- current
- power, with native-vs-calculated source flag
- min/max if supported

Required measurement models:

```python
@dataclass(frozen=True)
class PowerMeasurement:
    channel: int
    power_W: float | None
    power_source: Literal["instrument", "calculated", "unavailable"]
    timestamp_iso: str
    timestamp_unix: float

@dataclass(frozen=True)
class Measurement:
    channel: int
    voltage_V: float | None
    current_A: float | None
    power_W: float | None
    power_source: Literal["instrument", "calculated", "unavailable"]
    timestamp_iso: str
    timestamp_unix: float
```

Implement array measurement where supported:

- `MEASure:ARRay:VOLTage?`
- `MEASure:ARRay:CURRent?`
- `MEASure:ARRay:POWer?`
- `FETCh:ARRay:...`

Implement ASCII and binary/REAL array parsing, including multi-channel comma-separated binary blocks where documented.

Implement triggered acquisition flow:

```python
configure_sweep(...)
initiate_acquire(...)
trigger(...)
fetch_array(...)
abort_acquire(...)
```

Implement CSV datalogging helper:

```python
log_measurements_csv(
    path: str | Path,
    channels: Sequence[int],
    interval_s: float,
    duration_s: float | None = None,
    fields: Sequence[Literal["voltage", "current", "power"]] = ("voltage", "current", "power"),
    append: bool = True,
) -> None
```

CSV must include:

- ISO timestamp
- Unix timestamp
- channel
- voltage_V
- current_A
- power_W
- power_source
- module model
- output/input state where applicable
- error/status columns when useful

CSV must be readable by Excel and pandas.

## 13. Error Handling and Safety

Create custom exceptions without shadowing Python built-ins:

```python
N6700Error
N6700ConnectionError
N6700TimeoutError
N6700CommunicationError
N6700CommandError
UnsupportedFeatureError
InvalidChannelError
N6700ProtectionError
N6700QueryInterruptedError
SafetyInterlockError
```

Create a separate parsed SCPI error record:

```python
@dataclass(frozen=True)
class ScpiErrorRecord:
    code: int
    message: str
    raw: str
```

Rules:

- `parse_error()` must return `ScpiErrorRecord`, not an exception object.
- Python exceptions may include one or more `ScpiErrorRecord` objects in their attributes/messages.

Requirements:

- Check SCPI error queue after configuration commands when `check_errors=True`.
- Drain all errors on failure and include them in exception messages.
- Detect and handle query interrupted conditions.
- Use `*OPC?` or `*WAI` for commands that execute in parallel.
- Use timeouts for every blocking operation.
- Never leave an output/load/input enabled after a failed high-level configuration unless explicitly requested by a configurable unsafe policy.
- Provide emergency shutdown method.
- Do not use `*SAV` repeatedly in normal code because nonvolatile memory has finite write cycles.
- Provide `get_remote_state()` and `set_remote_state(...)`; keep `remote_lockout(enabled)` only as an optional compatibility wrapper.
- Default to front-panel accessible mode unless user explicitly requests remote lockout.
- Provide clear warning docstrings for calibration commands. Calibration support should be read-only or disabled by default unless explicitly enabled.

## 14. SCPI Layer Requirements

Create a small SCPI helper layer:

```python
format_bool(value: bool) -> str
format_float(value: float) -> str
format_channel_list(channels: int | Sequence[int] | range) -> str
parse_csv_floats(response: str) -> list[float]
parse_csv_strings(response: str) -> list[str]
parse_idn(response: str) -> InstrumentIdentity
parse_error(response: str) -> ScpiErrorRecord
```

Do not build SCPI strings using unsafe ad-hoc formatting scattered through the code. Centralize formatting and parsing.

## 15. Capability Model

Create module capability definitions.

Example:

```python
@dataclass(frozen=True)
class ChannelCapabilities:
    model: str
    module_type: Literal["power_supply", "smu", "electronic_load", "unknown"]
    supports_voltage_source: bool
    supports_current_source: bool
    supports_load_cc: bool
    supports_load_cv: bool
    supports_load_cr: bool
    supports_load_cp: bool
    supports_power_measurement: bool
    supports_array_measurement: bool
    supports_list_mode: bool
    supports_aux_voltage_input: bool
    supports_smu_priority_mode: bool
```

The driver must use capabilities to decide whether to expose or reject operations.

Do not rely only on model-name prefixes where official command availability differs by exact model or option. Include options returned by the instrument.

## 16. Logging Requirements

Use Python `logging`.

The driver must support:

- debug SCPI command logging with redaction if needed
- optional command/response trace log
- warning logs for protection events
- CSV measurement logs
- rotating log file support
- no `print()` inside library code

## 17. Simulator / Fake Instrument

Create a simulator for unit testing without hardware.

Simulator requirements:

- Understand enough SCPI to test all public APIs.
- Simulate four channels with configurable module models.
- Simulate standard power channel, SMU channel, and load channel behavior.
- Simulate error queue.
- Simulate protection trips.
- Simulate timeouts.
- Simulate query interrupted behavior.
- Simulate `*IDN?`, `*RDT?`, `SYST:CHAN:COUN?`, `SYST:CHAN:MOD?`, `SYST:CHAN:OPT?`, `MEAS?`, `OUTP?`, and core source commands.

## 18. Testing Requirements

Use pytest.

Minimum tests:

- SCPI channel-list formatting
- IDN parsing, including Keysight / Agilent / Hewlett-Packard manufacturer strings
- error parsing into `ScpiErrorRecord`
- module discovery
- capability classification by exact model and option
- type-specific channel adapter selection
- power supply output on/off
- SMU output on/off
- electronic load input on/off
- power supply voltage setpoint/current limit configuration
- coupled range/setpoint command generation
- SMU voltage/current priority configuration
- electronic load CC/CV/CR/CP configuration when exact commands are verified
- load mode API raises `UnsupportedFeatureError` when no load module exists
- load mode API raises `UnsupportedFeatureError` when load commands are not officially verified
- measurement parsing
- measured power vs calculated power source flag
- ASCII array parsing
- binary definite-length block parsing
- multi-channel comma-separated binary block parsing
- CSV logging
- context manager closes connection
- `shutdown_all()` attempts all channels and disables each module type correctly
- query interrupted error handling
- timeout/retry behavior
- command lock / RLock behavior
- no output/input auto-enable during configuration unless explicitly requested
- safe protection clear behavior
- transport `supports_clear` behavior
- CLI safe defaults
- SCPI command map existence and completeness

Coverage target:

```text
>= 90% line coverage for library code
```

Include optional real-hardware integration tests marked:

```python
@pytest.mark.hardware
```

These tests must be skipped unless an environment variable such as `N6700_RESOURCE` is set.

## 19. Documentation Generation Requirements

Generate documentation in Markdown and optionally MkDocs/Sphinx.

Documentation must include:

- Installation guide
- Supported hardware and module matrix
- USB connection guide
- Ethernet/LAN connection guide
- PyVISA backend setup
- Quick start
- Safety guide
- API reference
- Module capability model
- Examples page
- Troubleshooting guide
- SCPI error handling guide
- Industrial use recommendations
- Changelog

The README must include:

- package purpose
- installation command
- minimal USB example
- minimal Ethernet example
- safety warnings
- supported module table
- test instructions
- license placeholder

## 20. Example Generation Requirements

Generate runnable examples in the `examples/` folder.

General example safety rules:

- Every example must use context managers and/or `try/finally` for safe cleanup.
- Examples that enable a power output, SMU output, or electronic-load input must clearly mark the exact line that energizes the DUT.
- Examples that energize a DUT must use conservative low default values.
- Examples must not use nonvolatile writes unless the example is specifically about persistent configuration.
- Examples must not run hardware-energizing behavior automatically in CI.
- Examples must show `output=False` or `input_on=False` defaults for configuration functions.

Required examples:

### 20.1 Basic Ethernet power supply

Connect by IP, configure channel 1 as 5 V / 1 A with output initially OFF, then explicitly enable output on a clearly marked line, measure, and safely turn off.

### 20.2 Basic USB power supply

Connect by VISA USB resource, query IDN, list installed modules, measure all channels without changing output/input states.

### 20.3 Four-channel setup

Configure channels 1–4 with different voltage/current limits with outputs OFF, enable outputs in controlled order only on clearly marked lines, log measurements, then shutdown all.

### 20.4 SMU voltage-priority example

Set an N678xA SMU channel to voltage-priority mode with output OFF, configure voltage and current limit, then explicitly enable only on a clearly marked line, measure voltage/current/power, and turn output off.

### 20.5 SMU current-priority example

Set an N678xA SMU channel to current-priority mode with output OFF, configure current and voltage limit, then explicitly enable only on a clearly marked line, measure values, and turn output off.

### 20.6 Electronic load constant-current example

Configure a load module in CC mode with input OFF, set current, then explicitly enable load input on a clearly marked line, measure voltage/current/power, and disable input/load.

### 20.7 CSV measurement logger

Log voltage/current/power from selected channels every N seconds to a CSV file with timestamps. This example must not enable outputs or load inputs unless explicitly configured by the user.

### 20.8 Triggered measurement

Configure sweep parameters, initiate acquisition, trigger, fetch array data, save to CSV. It must preserve existing output/input state unless explicitly configured otherwise.

All examples must use `try/finally` or context managers to ensure outputs/loads are safely disabled on error when the example energizes a DUT.

## 21. API Style Requirements

Use clean, readable, typed Python.

Requirements:

- Type hints everywhere
- Clear docstrings
- No hidden global state
- No `time.sleep()` without a named constant or comment explaining timing
- No bare `except`
- No silent pass on communication errors
- Use enums or literals for modes
- Validate physical values before sending to instrument where limits are known
- Allow raw SCPI access for advanced users:

```python
write_scpi(command: str) -> None
query_scpi(command: str) -> str
```

Raw SCPI must still obey the transport timeout and logging policies.

## 22. Industrial Reliability Requirements

The generated driver must be appropriate for long-running automated test stations.

Implement:

- Connection health check
- Reconnect policy, configurable but disabled by default for safety-critical operations
- Periodic error queue polling option
- Watchdog callback hook
- Emergency shutdown function
- Deterministic cleanup on exceptions
- Clear separation between library code and CLI/examples
- Thread-safety note; either document as not thread-safe or implement a command lock
- Optional command lock for multi-threaded test runners
- No uncontrolled background threads unless explicitly requested by user
- No automatic retries for non-idempotent commands unless safe and documented

## 23. Command Coverage Minimum

At minimum, implement wrappers for these command groups where applicable:

- Common commands: `*IDN?`, `*RST`, `*CLS`, `*OPC?`, `*WAI`, `*STB?`, `*ESR?`, `*TST?`, `*RDT?`
- System commands: channel count/model/options/serial, error queue, remote/local state
- Output commands: output state, output protection clear, output delays where supported
- Source commands: voltage, current, ranges, protection, list mode, SMU function/priority mode
- Sense commands: measurement function enable, sweep points/interval/offset, auxiliary voltage input where supported
- Measure commands: scalar voltage/current/power, array voltage/current/power
- Fetch commands: scalar and array fetch after triggered acquisition
- Initiate/Trigger/Abort commands: acquisition and transient/list workflows
- Status commands: operation/questionable status and enable/event/condition queries

Do not implement destructive or calibration-changing commands as normal public APIs unless guarded by an explicit calibration mode class and clear warnings.

## 24. Acceptance Criteria

The generated package is acceptable when:

1. `pip install .` succeeds.
2. `pytest` passes without real hardware using the simulator.
3. `ruff check .` passes.
4. `mypy keysight_n6700` passes or documented strictness exceptions are justified.
5. README and docs are generated.
6. All required examples exist and are runnable.
7. The package can connect through both USB VISA and Ethernet.
8. The driver discovers channel count and module models automatically.
9. All four channels can be controlled independently.
10. Unsupported module features are rejected with clear exceptions.
11. Outputs/loads are not enabled by default during configuration.
12. A failed high-level operation does not leave outputs in an unsafe state.
13. SCPI errors are surfaced as Python exceptions with instrument error text.
14. The simulator covers power supply, SMU, and electronic load behavior.
15. The code contains no hard-coded lab-specific resource strings.

## 25. Suggested First Implementation Order

1. Packaging skeleton
2. Exceptions and types
3. SCPI formatting/parsing helpers
4. Transport abstraction
5. PyVISA transport
6. Raw socket transport
7. Mainframe discovery
8. Channel class
9. Standard power supply API
10. Measurement API
11. Error/status handling
12. SMU capability and API
13. Electronic load capability and API
14. CSV logger
15. Simulator
16. Unit tests
17. Examples
18. Documentation
19. Hardware integration tests
20. Final production review

---

# 26. Production Review Additions and Best-Practice Findings

This section contains additional requirements added after production-readiness review of the original task. These requirements are mandatory unless explicitly marked as SHOULD or MAY.

## 26.1 MUST / SHOULD / MAY Priority Rules

The generated code agent must treat requirements according to the following priority:

### MUST

MUST requirements are mandatory for the first production release:

- Installable Python package.
- USB and Ethernet communication.
- Four-channel support.
- Safe non-invasive connection behavior.
- Automatic channel/module discovery.
- Capability model.
- Simulator.
- Unit tests.
- Documentation.
- Examples.
- SCPI error handling.
- Safe shutdown behavior.
- No automatic output/load enable.
- No guessed electronic-load commands.
- Production logging and audit trail.

### SHOULD

SHOULD requirements are strongly recommended and should be implemented unless there is a documented technical reason:

- CLI utility.
- Hardware acceptance test scripts.
- Optional raw socket transport in addition to PyVISA.
- MkDocs/Sphinx documentation site.
- Optional pandas helper functions for reading logs.

### MAY

MAY requirements are optional future enhancements:

- Advanced GUI.
- Async API.
- Background health monitor.
- Automatic reconnect during clearly safe read-only operations only.

### OUT OF SCOPE for first release

The following must not be implemented as normal public APIs in the first production release:

- Calibration write operations.
- Unsafe automatic reset on connect.
- Unsupported or unverified electronic-load SCPI commands.
- Silent feature guessing based on incomplete model names.
- Automatic retries for non-idempotent commands.
- Uncontrolled background threads.

## 26.2 Exact Supported Module Matrix

The code generator must create and maintain a module support matrix.

The matrix must include at least:

```text
Module model/prefix | Module type | Supported modes | Required SCPI source | Status
N673x               | power_supply | CV/CC           | N6700 official docs  | implemented/simulated
N674x               | power_supply | CV/CC           | N6700 official docs  | implemented/simulated
N675x               | power_supply | CV/CC, advanced | N6700 official docs  | implemented/simulated
N676x               | precision_ps | CV/CC, digitizer| N6700 official docs  | implemented/simulated
N677x               | power_supply | CV/CC           | N6700 official docs  | implemented/simulated
N678xA              | smu          | voltage/current priority | N6700 official docs | implemented/simulated
Exact load model(s) | electronic_load | CC/CV/CR/CP if supported | latest official load-module docs required | blocked until exact model/source verified
Unknown             | unknown      | none            | none                 | unsupported
```

Electronic-load entries must not remain generic in implemented code. Before implementing load commands, the code generator must replace `Exact load model(s)` with exact module model numbers and cite the official Keysight source used for each implemented command.

The matrix must be implemented in code and documented in `docs/module_support.md`.

The driver must not rely only on broad model-name prefixes when exact command availability depends on the complete model number or installed options. It must use module model, options, serial number, and documented capabilities.

Acceptance rule:

```text
If an electronic-load module model is not explicitly listed with official command documentation, its load-control APIs must raise UnsupportedFeatureError.
```

## 26.3 Electronic Load Verification Rule

Electronic load support is a required target feature, but it must not be implemented from assumptions.

For every electronic load operation, the code generator must identify the exact official SCPI command syntax and the relevant supported load module model.

Required rule:

```text
If exact electronic-load SCPI syntax is not verified from official Keysight documentation, the API may exist but must raise UnsupportedFeatureError with a clear message explaining that the installed module or operation is not verified.
```

The driver must not silently map power-supply source commands to electronic-load behavior unless official documentation confirms that syntax for the installed load module.

Each electronic load method must have tests for:

- supported load module in simulator
- unsupported module
- unknown module
- missing capability
- invalid mode
- failure to enable/load safely

## 26.4 Non-Invasive Connection Policy

Connection must be safe by default.

On connection, the driver MUST NOT:

- send `*RST`
- enable or disable outputs
- clear protection automatically
- save or recall nonvolatile state
- change ranges, setpoints, modes, trigger settings, or inhibit settings
- change remote lockout state unless explicitly requested

On connection, the driver MAY perform read-only discovery:

- `*IDN?`
- `*OPT?`
- `*RDT?`
- `SYSTem:CHANnel:COUNt?`
- `SYSTem:CHANnel:MODel?`
- `SYSTem:CHANnel:OPTion?`
- `SYSTem:CHANnel:SERial?`
- output state query
- voltage/current setpoint query
- protection state query
- error queue read only if explicitly configured

Required configuration:

```python
N6700.connect_visa(resource, reset_on_connect=False, discover=True, clear_errors_on_connect=False)
```

`reset_on_connect` must default to `False`.

If a user requests reset on connect, the driver must document that reset may abort acquisition/transient operations and may change the live instrument state.

## 26.5 Binary Block and Array Measurement Requirements

The task must explicitly support both ASCII and binary/REAL array measurement formats where documented.

Required implementation:

```python
parse_ieee488_definite_block(data: bytes) -> bytes
parse_binary_real_array(data: bytes, byte_order: Literal["normal", "swapped"]) -> list[float]
set_data_format(format: Literal["ascii", "real"], *, byte_order: Literal["normal", "swapped"] | None = None) -> None
get_data_format() -> DataFormat
```

Requirements:

- Support ASCII comma-separated measurement arrays.
- Support IEEE/SCPI definite-length binary block parsing.
- Support REAL/binary floating-point data if documented by the instrument.
- Handle byte order explicitly.
- Validate array response length.
- Reject malformed binary blocks with a clear exception.
- Do not mix commands and unread query data.
- If ASCII array queries are limited to one channel by the instrument, reject multi-channel ASCII array queries or automatically split them per channel with documented behavior.

Tests must include:

- valid definite-length block
- truncated block
- malformed header
- ASCII array parsing
- binary REAL array parsing
- multi-channel split behavior

## 26.6 Protection and Status Decoding

Implement typed status and protection snapshots instead of exposing only raw integers.

Required API:

```python
get_operation_status(channel: int | None = None) -> OperationStatus
get_questionable_status(channel: int | None = None) -> QuestionableStatus
get_protection_status(channel: int) -> ProtectionStatus
get_full_status_snapshot() -> InstrumentStatusSnapshot
```

`ProtectionStatus` must include fields such as:

```python
@dataclass(frozen=True)
class ProtectionStatus:
    channel: int
    active: bool
    over_voltage: bool | None
    over_current: bool | None
    over_temperature: bool | None
    power_limit: bool | None
    power_fail: bool | None
    inhibit: bool | None
    oscillation: bool | None
    raw_status: int | str | None
```

`N6700ProtectionError` must include:

- affected channel
- protection type if known
- command that failed
- SCPI error queue contents
- output/load/input state before failure if known
- output/load/input state after failure if known
- recommended safe action

Status decoding must be tested against simulator responses.

## 26.7 Inhibit Input Support

Industrial racks often use inhibit/interlock wiring. The driver must expose inhibit configuration but must treat it as a mainframe-level safety feature.

Required API:

```python
set_inhibit_mode(mode: Literal["latching", "live", "off"]) -> None
get_inhibit_mode() -> Literal["latching", "live", "off"]
clear_inhibit_latch() -> None
```

Requirements:

- Do not change inhibit mode automatically.
- Document that inhibit settings may affect all channels.
- Treat inhibit configuration as a safety-critical operation.
- Include status/protection information when inhibit is active.
- Add tests for inhibit mode formatting and error handling.

## 26.8 Nonvolatile Memory Protection Policy

The driver must protect the instrument from unnecessary nonvolatile-memory writes.

Requirements:

- Do not call `*SAV` in normal operation.
- Do not repeatedly write power-on state, inhibit configuration, calibration data, or other nonvolatile settings in test loops.
- All nonvolatile write methods must use explicit names, for example:

```python
save_state_to_nonvolatile(slot: Literal[0, 1]) -> None
configure_power_on_state(...) -> None
```

- Each nonvolatile write method must have docstrings warning about finite nonvolatile-memory write cycles.
- Nonvolatile write methods must be excluded from automatic reconnect/recovery logic.
- Examples must not use nonvolatile writes unless the example is specifically about persistent configuration.

## 26.9 Audit Trail Requirement

Every high-level operation must optionally create an audit record.

Required model:

```python
@dataclass(frozen=True)
class AuditRecord:
    timestamp_iso: str
    timestamp_unix: float
    operation: str
    channels: tuple[int, ...]
    requested_values: dict[str, object]
    scpi_commands: tuple[str, ...]
    responses: tuple[str, ...]
    errors: tuple[str, ...]
    duration_s: float
    final_output_states: dict[int, bool] | None
```

Requirements:

- Audit logging must be optional but easy to enable.
- Audit logs must be compatible with JSON Lines.
- Audit logs must not include sensitive data unless explicitly enabled.
- Audit records must be written for high-level configuration, output enable/disable, load enable/disable, protection clear, and shutdown operations.
- Audit records must be tested with simulator.

## 26.10 Hardware Acceptance Test Checklist

Create optional hardware tests marked with:

```python
@pytest.mark.hardware
```

They must be skipped unless `N6700_RESOURCE` or equivalent environment variable is set.

Minimum hardware acceptance tests:

1. Connect by VISA resource.
2. Query `*IDN?`.
3. Discover channel count.
4. Discover model/options/serial for all installed channels.
5. Query output state for all channels.
6. Query voltage/current setpoints with outputs unchanged.
7. Measure voltage/current/power with outputs unchanged where supported.
8. Configure channel 1 to safe low voltage/current with output OFF.
9. Enable output only if `N6700_HARDWARE_ENABLE_OUTPUT=1`.
10. Verify measurement after explicit enable.
11. Turn channel 1 off.
12. Run `shutdown_all()` and verify all outputs/loads are disabled.
13. Drain SCPI error queue.
14. Test Ethernet resource separately when `N6700_ETHERNET_RESOURCE` is set.
15. Test USB resource separately when `N6700_USB_RESOURCE` is set.

Hardware tests must print or log discovered modules but must not expose serial numbers in public CI logs unless explicitly enabled.

## 26.11 CLI Utility Requirement

Generate a small command-line utility named:

```text
n6700ctl
```

Required commands:

```bash
n6700ctl idn --resource USB0::...::INSTR
n6700ctl discover --resource TCPIP0::192.168.0.100::inst0::INSTR
n6700ctl measure --resource ... --channels 1,2,3,4
n6700ctl output-off --resource ... --channels all
n6700ctl errors --resource ...
n6700ctl shutdown-all --resource ...
```

CLI requirements:

- Must use the same safe driver API as the library.
- Must not enable outputs unless an explicit command asks for it.
- Must require confirmation or `--yes` for potentially unsafe commands.
- Must return useful process exit codes.
- Must support JSON output for automation:

```bash
n6700ctl discover --resource ... --json
```

## 26.12 Documentation Improvements

Add the following documentation pages:

```text
docs/non_invasive_connection.md
docs/electronic_load_verification.md
docs/binary_data_format.md
docs/status_and_protection.md
docs/inhibit_interlock.md
docs/nonvolatile_memory.md
docs/hardware_acceptance_tests.md
docs/cli.md
docs/audit_logging.md
```

README must include a short safety section:

```text
By default, this driver does not reset the instrument, does not enable outputs, does not clear protection, and does not write nonvolatile memory. Any operation that can energize a DUT must be explicit in user code.
```

## 26.13 Additional Examples

Add examples:

```text
examples/non_invasive_discovery.py
examples/status_snapshot.py
examples/protection_handling.py
examples/inhibit_mode_readback.py
examples/binary_array_measurement.py
examples/cli_usage.md
examples/audit_logging.py
```

Each example must include safe cleanup using context managers and/or `try/finally`.

## 26.14 Additional Tests

Add tests for the findings in this section:

```text
tests/unit/test_non_invasive_connection.py
tests/unit/test_binary_blocks.py
tests/unit/test_status_decoding.py
tests/unit/test_inhibit.py
tests/unit/test_nonvolatile_policy.py
tests/unit/test_audit_logging.py
tests/unit/test_cli.py
tests/unit/test_load_verification_policy.py
tests/hardware/test_acceptance.py
```

## 26.15 Revised Acceptance Criteria

The generated package is acceptable only when all original acceptance criteria and these additional criteria are met:

1. Connection is non-invasive by default.
2. `reset_on_connect` defaults to `False`.
3. Electronic-load APIs do not guess commands.
4. Unknown or unverified module features raise `UnsupportedFeatureError`.
5. Binary block parsing is implemented and tested.
6. Status and protection snapshots are typed and tested.
7. Inhibit/interlock handling is implemented or explicitly documented as unavailable.
8. Nonvolatile writes are never used in normal examples or test loops.
9. Optional audit logging exists for high-level operations.
10. CLI utility exists and uses safe defaults.
11. Hardware acceptance tests are present and skipped unless explicitly enabled.
12. Documentation includes safety, electronic-load verification, binary data format, inhibit/interlock, and nonvolatile-memory pages.

---

# 27. Final Production-Hardening Findings Implemented in v1.4

This section records the final production-hardening decisions plus v1.4 cleanup decisions. Earlier sections have been directly updated for consistency, so this section should be read as a summary and additional acceptance criteria rather than as a conflicting override.

## 27.1 Safe Protection Clear Is Mandatory

The driver must not provide an unsafe simple `clear_protection()` as the only public API. Clearing protection can energize an output again on some instruments if the channel was enabled before the fault. Therefore, the default behavior must force the output/load/input off before clearing protection and must not restore it unless explicitly requested.

Required API:

```python
clear_protection(
    channel: int,
    *,
    restore_output: bool = False,
    force_output_off_first: bool = True,
    verify_cleared: bool = True,
) -> ProtectionClearResult
```

Channel object equivalent:

```python
channel.clear_protection(
    *,
    restore_output: bool = False,
    force_output_off_first: bool = True,
    verify_cleared: bool = True,
) -> ProtectionClearResult
```

Required result object:

```python
@dataclass(frozen=True)
class ProtectionClearResult:
    channel: int
    protection_before: ProtectionStatus
    protection_after: ProtectionStatus
    output_state_before: bool | None
    output_state_after: bool | None
    restored_output: bool
    errors: tuple[ScpiErrorRecord, ...]
```

Required behavior:

1. Query and store the existing output/load/input state.
2. If `force_output_off_first=True`, turn the output/load/input off before clearing protection.
3. Clear protection.
4. Query protection/status again.
5. Keep output/load/input off unless `restore_output=True`.
6. Return before/after states and errors.

Required tests:

- protection clear forces output off before clear
- protection clear does not restore output by default
- protection clear restores output only when explicitly requested
- protection clear failure leaves output/load/input off where possible

## 27.2 Separate Channel Classes for Power Supply, SMU, and Electronic Load

The driver must avoid ambiguous common APIs for different module types.

Required class model:

```python
class BaseChannel:
    channel: int
    capabilities: ChannelCapabilities
    measure_voltage() -> float
    measure_current() -> float
    measure_power() -> Measurement
    get_status_snapshot() -> ChannelStatusSnapshot
    clear_protection(...) -> ProtectionClearResult

class PowerSupplyChannel(BaseChannel):
    output_on() -> None
    output_off() -> None
    set_voltage_setpoint(...) -> None
    set_current_limit(...) -> None

class SMUChannel(BaseChannel):
    output_on() -> None
    output_off() -> None
    set_smu_mode(...) -> None
    configure_voltage_priority(...) -> None
    configure_current_priority(...) -> None

class ElectronicLoadChannel(BaseChannel):
    input_on() -> None
    input_off() -> None
    set_load_mode(...) -> None
    set_load_current(...) -> None
    set_load_voltage(...) -> None
    set_load_resistance(...) -> None
    set_load_power(...) -> None
```

The package must provide type-safe factory methods or adapters:

```python
n6700.channel(1)       # returns BaseChannel subclass
n6700.power_supply(1)  # returns PowerSupplyChannel or raises UnsupportedFeatureError
n6700.smu(2)           # returns SMUChannel or raises UnsupportedFeatureError
n6700.load(3)          # returns ElectronicLoadChannel or raises UnsupportedFeatureError
```

Electronic load APIs must use `input_on/input_off` or `load_on/load_off` terminology. Do not use `output_on/output_off` for loads unless the official documentation for that exact module uses that terminology and the docs explain the mapping.

## 27.3 Remove Ambiguous `set_current()` Naming

The generated API must not use generic `set_current()` as the primary public API.

Use explicit names:

Power supply modules:

```python
set_voltage_setpoint(value: float, *, voltage_range: float | str | None = None) -> None
set_current_limit(value: float, *, current_range: float | str | None = None) -> None
get_voltage_setpoint() -> float
get_current_limit() -> float
```

SMU modules:

```python
set_voltage_setpoint(value: float, *, voltage_range: float | str | None = None) -> None
set_current_setpoint(value: float, *, current_range: float | str | None = None) -> None
set_voltage_limit(value: float) -> None
set_current_limit(value: float) -> None
```

Electronic load modules:

```python
set_load_current(value: float) -> None
set_load_voltage(value: float) -> None
set_load_resistance(value: float) -> None
set_load_power(value: float) -> None
```

Compatibility aliases may exist only if clearly documented and only if they cannot create ambiguity.

## 27.4 Do Not Use `range` as a Public Parameter Name

The generated public APIs must not use `range` as a keyword argument because it shadows Python's built-in `range()`.

Bad:

```python
set_voltage(value: float, *, range: float | str | None = None)
```

Good:

```python
set_voltage_setpoint(value: float, *, voltage_range: float | str | None = None)
set_current_limit(value: float, *, current_range: float | str | None = None)
```

Apply this rule to public APIs, dataclasses, examples, and documentation.

## 27.5 Runtime and Development Dependency Split

Runtime dependencies must be minimal.

Required `pyproject.toml` style:

```toml
[project]
name = "keysight-n6700"
requires-python = ">=3.10"
dependencies = [
  "pyvisa>=1.14",
  "typing_extensions>=4.8; python_version < '3.11'",
]

[project.optional-dependencies]
dev = [
  "pytest",
  "pytest-cov",
  "ruff",
  "mypy",
  "types-setuptools",
]
docs = [
  "mkdocs",
  "mkdocs-material",
  "mkdocstrings[python]",
]
pandas = [
  "pandas",
]
```

Rules:

- `pytest`, `pytest-cov`, `ruff`, and `mypy` must not be runtime dependencies.
- `pandas` must be optional.
- docs tooling must be optional.
- examples using pandas must state the extra install command.

## 27.6 Exception Names Must Not Shadow Built-ins

Do not define custom exceptions named exactly `N6700ConnectionError`, `N6700TimeoutError`, `N6700CommandError`, or `N6700ProtectionError`.

Required hierarchy:

```python
class N6700Error(Exception): ...
class N6700ConnectionError(N6700Error): ...
class N6700TimeoutError(N6700Error): ...
class N6700CommunicationError(N6700Error): ...
class N6700CommandError(N6700Error): ...
class N6700ProtectionError(N6700Error): ...
class N6700QueryInterruptedError(N6700CommandError): ...
class UnsupportedFeatureError(N6700Error): ...
class InvalidChannelError(N6700Error): ...
class SafetyInterlockError(N6700ProtectionError): ...
```

Separate parsed SCPI error records from Python exceptions:

```python
@dataclass(frozen=True)
class ScpiErrorRecord:
    code: int
    message: str
    raw: str
```

`parse_error()` must return `ScpiErrorRecord`.

## 27.7 Mandatory SCPI Command Traceability Map

Generate:

```text
docs/scpi_command_map.md
```

It must contain a table with:

```text
Python API method
SCPI command/query
Manual section/page or official source
Supported module models
Capability flag required
Simulator test name
Hardware test name if applicable
Safety notes
```

Rules:

- Every public high-level method must be traceable to exact SCPI commands.
- Every SCPI command used by the driver must appear in the map.
- Electronic-load commands must include a verified official source before implementation.
- Missing electronic-load documentation means the API raises `UnsupportedFeatureError`.

## 27.8 Multi-Block Binary Array Parsing

Binary parser must support multi-channel REAL array responses formatted as:

```text
<definite_length_block>,<definite_length_block>,...
```

Requirements:

- Parse one block per requested channel.
- Preserve requested channel order.
- Validate the number of blocks equals the requested channel count.
- Detect missing comma separators.
- Detect truncated or malformed blocks.
- Support byte-order configuration.
- Return typed data:

```python
@dataclass(frozen=True)
class ArrayMeasurement:
    channel: int
    values: tuple[float, ...]
    unit: Literal["V", "A", "W"]
    format: Literal["ascii", "real"]
```

Required tests:

- single-channel binary REAL array
- four-channel binary REAL array with comma-separated blocks
- block count mismatch
- malformed separator
- byte-order swap
- ASCII fallback
- channel order preservation

## 27.9 Mandatory SCPI Transaction Locking and Query Discipline

The transport/driver layer must serialize SCPI transactions.

Requirement:

```text
Only one complete SCPI transaction may be active at a time. A query must fully read and drain its response before any new command is sent.
```

Implementation requirements:

- Command locking is enabled by default.
- Use `threading.RLock` for driver-level command locking unless the implementation proves there is no nested locking path.
- A plain non-reentrant `threading.Lock` must not be used in a way that can deadlock when high-level methods call lower-level methods that also lock.
- Use the same lock in `write()`, `query()`, `read_raw()`, `write_raw()`, high-level APIs, and raw SCPI methods.
- Document thread-safety behavior.
- Concurrent queries must be serialized.
- A query failure must attempt safe buffer cleanup if supported.
- The driver must not issue a second command until the first query response is completely consumed.
- The library must be safe for multiple Python threads sharing one driver object when command locking is enabled.

Required API:

```python
N6700(..., command_lock: bool = True)
```

Required tests:

- concurrent measurements serialize correctly
- nested high-level calls do not deadlock
- query interrupted simulator error is converted to `N6700QueryInterruptedError`
- lock is released after timeout/error
- raw SCPI methods use the same lock

## 27.10 Hardware Test Safety Levels

Hardware acceptance tests must be organized into explicit safety levels:

```text
Level 0: read-only discovery only
Level 1: configure setpoints with outputs/loads OFF
Level 2: enable outputs/loads only with explicit environment variable
Level 3: destructive, DUT-connected, or stress tests; never run automatically
```

Environment variables:

```text
N6700_RESOURCE
N6700_USB_RESOURCE
N6700_ETHERNET_RESOURCE
N6700_HARDWARE_LEVEL=0|1|2|3
N6700_HARDWARE_ENABLE_OUTPUT=1
N6700_HARDWARE_ALLOW_PROTECTION_CLEAR=1
```

Rules:

- Default hardware level is Level 0.
- Level 1 must not energize outputs/loads.
- Level 2 requires both `N6700_HARDWARE_LEVEL=2` and `N6700_HARDWARE_ENABLE_OUTPUT=1`.
- Level 3 tests must be skipped unless explicitly selected and must never be part of normal CI.
- Protection clear tests require `N6700_HARDWARE_ALLOW_PROTECTION_CLEAR=1`.

## 27.11 Additional Best-Practice Requirements

### 27.11.1 IDN compatibility

`parse_idn()` must accept at least:

```text
KEYSIGHT TECHNOLOGIES
AGILENT TECHNOLOGIES
HEWLETT-PACKARD
```

Manufacturer comparison must be case-insensitive and whitespace-tolerant.

### 27.11.2 Remote/local state

Add API:

```python
get_remote_state() -> RemoteState
set_remote_state(state: Literal["local", "remote", "remote_lockout"]) -> None
```

If exact remote/local SCPI commands are backend-specific or unavailable, document the limitation and expose the feature only through transport capabilities.

### 27.11.3 SMU output turn-off behavior

For SMU modules that support output turn-off impedance/mode, add capability-gated API:

```python
set_smu_output_off_mode(channel: int, mode: Literal["high_z", "low_z"]) -> None
get_smu_output_off_mode(channel: int) -> Literal["high_z", "low_z"]
```

If unsupported by the installed module, raise `UnsupportedFeatureError`.

### 27.11.4 Measured power vs calculated power

Power measurement must distinguish native measured power from calculated power.

```python
@dataclass(frozen=True)
class Measurement:
    channel: int
    voltage_V: float | None
    current_A: float | None
    power_W: float | None
    power_source: Literal["instrument", "calculated", "unavailable"]
    timestamp_iso: str
    timestamp_unix: float
```

If `MEASure:POWer?` is unsupported, the driver may calculate `V * I`, but it must mark `power_source="calculated"`.

### 27.11.5 Documentation build command

Documentation generation must include one working build command:

```bash
mkdocs build
```

or:

```bash
sphinx-build -b html docs docs/_build/html
```

### 27.11.6 CI workflow

Generate CI for at least:

- Windows latest
- Ubuntu latest
- Python 3.10
- Python 3.11
- Python 3.12
- Python 3.13 if dependencies support it

CI must run:

```bash
ruff check .
mypy keysight_n6700
pytest
```

Hardware tests must be skipped in CI unless explicitly configured.

### 27.11.7 Semantic versioning

Use semantic versioning:

```text
MAJOR.MINOR.PATCH
```

Document API-breaking changes in `CHANGELOG.md`.

### 27.11.8 `py.typed`

The package must include `py.typed`, and CI must verify that type information is included in the built wheel.

### 27.11.9 Default no-network/no-hardware mode

All tests and examples used in CI must run without real hardware and without network access unless explicitly marked otherwise.

## 27.12 Additional Required Files

Generate these additional files:

```text
docs/scpi_command_map.md
docs/thread_safety.md
docs/hardware_test_safety_levels.md
docs/remote_local_control.md
docs/smu_output_off_mode.md
.github/workflows/ci.yml
tests/unit/test_command_locking.py
tests/unit/test_idn_compatibility.py
tests/unit/test_power_source_flag.py
tests/unit/test_channel_type_adapters.py
tests/unit/test_safe_clear_protection.py
tests/unit/test_scpi_command_map_exists.py
```

## 27.13 Revised Final Acceptance Criteria for v1.4

The generated package is acceptable only when all previous acceptance criteria and these additional criteria are met:

1. Only one version header exists at the top of the requirement file.
2. Runtime dependencies are minimal; test/docs/data-analysis tools are optional extras only.
3. `parse_error()` returns `ScpiErrorRecord`, not an exception object or old `ScpiError` type.
4. `clear_protection()` is safe by default and does not restore output/load/input unless explicitly requested.
5. Power supply, SMU, and electronic load APIs are separated or exposed through type-safe adapters.
6. Flat `N6700` SMU/load methods are optional convenience wrappers; the primary API is the type-specific channel object API.
7. Generic ambiguous `set_current()` is not the primary public API.
8. Public APIs do not use `range` as a parameter name.
9. Custom exception names do not shadow Python built-ins.
10. Parsed SCPI error records are separated from Python exceptions.
11. `docs/scpi_command_map.md` maps every public method to SCPI commands and source documentation.
12. The generated package must not contain implemented electronic-load SCPI commands unless they appear in `docs/scpi_command_map.md` with an official source reference and exact supported model.
13. Electronic-load support must replace generic model placeholders with exact model numbers before implementation.
14. Unknown, unsupported, or unverified electronic-load features raise `UnsupportedFeatureError`.
15. Binary parser supports comma-separated multi-block REAL array responses and preserves channel order.
16. SCPI transaction locking is enabled by default and uses `threading.RLock` or a proven non-deadlocking equivalent.
17. `Transport.supports_clear` exists and `clear()` raises `UnsupportedFeatureError` when unavailable.
18. Hardware tests are split into explicit safety levels.
19. IDN parsing accepts Keysight, Agilent, and Hewlett-Packard naming.
20. Measured power and calculated power are clearly distinguished with `power_source`.
21. Examples that energize a DUT clearly mark the energizing line and use conservative low default values.
22. The primary remote/local API is `get_remote_state()` / `set_remote_state(...)`; `remote_lockout(enabled)` is only a compatibility wrapper.
23. `shutdown_all()` safely disables power outputs, SMU outputs, and load inputs according to module type.
24. CI exists for Windows and Linux.
25. Package includes `py.typed` in the built distribution.

