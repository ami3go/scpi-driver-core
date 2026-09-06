# API Reference

## `N83624CellSimulator`

Unified public class for the NGI N83624 driver. It exposes both raw SCPI access and typed high-level methods.

### Constructors

```python
N83624CellSimulator.tcp(host="192.168.0.123", port=7000, timeout=3.0, **kwargs)
N83624CellSimulator.udp(host="192.168.0.123", port=7000, timeout=3.0, **kwargs)
N83624CellSimulator.udp_channel(host, channel, timeout=3.0, **kwargs)
N83624CellSimulator.serial(port, baudrate=115200, timeout=3.0, **kwargs)
```

`kwargs` may include:

- `limits: InstrumentLimits`
- `safety_policy: DriverSafetyPolicy`
- `bench_interlock: BenchInterlock`
- `retry_policy: RetryPolicy`
- `reconnect_policy: ReconnectPolicy`

### Session methods

```python
connect()
close()
channel(channel: int) -> N83624Channel
all_outputs_off()
recover()
start_heartbeat(config: HeartbeatConfig | None = None)
stop_heartbeat()
get_communication_observation() -> CommunicationObservation
```

The class is a context manager:

```python
with N83624CellSimulator.tcp("192.168.0.123") as sim:
    print(sim.identify())
```

### Raw SCPI escape hatch

```python
write(command: str) -> None
query(command: str) -> str
```

Raw SCPI bypasses high-level validation and safety sequencing. Use it only for diagnostics or commands not yet wrapped by the typed API.

### Common commands

```python
identify() -> str
opc() -> int
wait_operation_complete(timeout: float | None = None) -> bool
factory_reset(confirm: bool = False) -> None
```

`factory_reset()` requires `confirm=True`.

### Instrument-level methods

```python
measure_voltage_channels(channels) -> dict[int, float]
measure_current_channels(channels) -> dict[int, float]
measure_power_channels(channels) -> dict[int, float]
set_global_capture_rate(rate, *, experimental_ok=False)
get_global_capture_rate(*, experimental_ok=False)
```

Global capture rate uses `MEASure0:CAPRate`, which must be hardware-verified before production use.

### System methods

```python
set_ip_address(ip, *, confirm=False)
get_ip_address() -> str
set_serial_baudrate(baudrate, *, confirm=False)
get_serial_baudrate() -> int
set_beeper(enabled)
get_beeper() -> bool
set_language(language)
get_language() -> Language
set_lan_connection_type(connection_type, *, confirm=False)
get_lan_connection_type() -> LanConnectionType
set_powerdown_save(enabled, *, confirm=False)
get_powerdown_save() -> bool
set_hmi_disconnect_enabled(enabled)
get_hmi_disconnect_enabled() -> bool
```

Persistent communication settings require confirmation by default.

## `N83624Channel`

### Measurement

```python
measure_current_ma() -> float
measure_voltage_v() -> float
measure_power_w() -> float
measure_capacity_mah() -> float
measure_resistance_mohm() -> float
set_capture_rate(rate) -> None
get_capture_rate() -> CaptureRate
measure_all() -> Measurement
```

### Output

```python
set_mode(mode, *, output_off_first=True, verify=True)
get_mode() -> OutputMode
output_on()
output_off()
set_output(enabled)
get_output() -> bool
get_status() -> ChannelStatus
get_event() -> ChannelStatus
set_on_dwell_us(dwell_us)
get_on_dwell_us() -> int
```

Compound operations hold the instrument lock for their full duration.

### Source mode

```python
configure_source(voltage_v, current_limit_ma, current_range=CurrentRange.AUTO, *, output=None, output_off_first=True, verify=True)
set_source_voltage_v(voltage_v)
get_source_voltage_v() -> float
set_source_current_limit_ma(current_ma)
get_source_current_limit_ma() -> float
set_source_current_range(range_)
get_source_current_range() -> CurrentRange
```

### Charge mode

```python
configure_charge(voltage_v, current_limit_ma, resistance_mohm, *, output=None, output_off_first=True, verify=True)
set_charge_voltage_v(voltage_v)
get_charge_voltage_v() -> float
set_charge_current_limit_ma(current_ma)
get_charge_current_limit_ma() -> float
set_charge_resistance_mohm(resistance_mohm)
get_charge_resistance_mohm() -> float
read_charge_echo_voltage_v() -> float
read_charge_echo_capacity_mah() -> float
```

### SOC mode

```python
configure_soc(steps, *, file_number=None, start_voltage_v=None, output=None, output_off_first=True, verify=True)
set_soc_file(file_number)
get_soc_file() -> int
set_soc_length(length)
get_soc_length() -> int
set_soc_edit_step(step)
get_soc_edit_step() -> int
set_soc_step_voltage_v(voltage_v)
get_soc_step_voltage_v() -> float
set_soc_step_current_limit_ma(current_ma)
get_soc_step_current_limit_ma() -> float
set_soc_step_resistance_mohm(resistance_mohm)
get_soc_step_resistance_mohm() -> float
set_soc_step_capacity_mah(capacity_mah)
get_soc_step_capacity_mah() -> float
set_soc_start_voltage_v(voltage_v)
get_soc_start_voltage_v() -> float
get_soc_running_step() -> int
get_soc_running_capacity_mah() -> float
get_soc_open_voltage_v() -> float
get_soc_simulated_resistance_mohm() -> float
```

When `file_number=None`, the driver queries the currently selected SOC file while holding the compound-operation lock. Production scripts should pass an explicit file number.

### Sequence mode

```python
configure_sequence(file_number, steps, *, file_cycle=1, output=None, output_off_first=True, verify=True)
set_sequence_edit_file(file_number)
get_sequence_edit_file() -> int
set_sequence_length(length)
get_sequence_length() -> int
set_sequence_edit_step(step)
get_sequence_edit_step() -> int
set_sequence_file_cycle(cycle)
get_sequence_file_cycle() -> int
set_sequence_step_voltage_v(voltage_v)
get_sequence_step_voltage_v() -> float
set_sequence_step_current_limit_ma(current_ma)
get_sequence_step_current_limit_ma() -> float
set_sequence_step_resistance_mohm(resistance_mohm)
get_sequence_step_resistance_mohm() -> float
set_sequence_step_runtime_s(runtime_s)
get_sequence_step_runtime_s() -> float
set_sequence_link_start(step)
get_sequence_link_start() -> int
set_sequence_link_end(step)
get_sequence_link_end() -> int
set_sequence_link_cycle(cycle)
get_sequence_link_cycle() -> int
set_sequence_run_file(file_number)
get_sequence_run_file() -> int
get_sequence_running_step() -> int
get_sequence_running_cycle() -> int
get_sequence_running_time_s() -> float
```

### Protection

```python
set_ocp_current_ma(current_ma)
get_ocp_current_ma() -> float
set_ovp_voltage_v(voltage_v)
get_ovp_voltage_v() -> float
set_opp_power_mw(power_mw)
get_opp_power_mw() -> float
```

### CAN

```python
get_can_id() -> int
set_can_upload_time_ms(time_ms)
get_can_upload_time_ms() -> int
get_can_rate() -> int
get_extended_can_id() -> int
```

Only documented setters are implemented. CAN ID/rate setters are intentionally omitted pending hardware/manual verification.

### Fault simulation

```python
set_fault_simulation(mode, *, require_zero_output=True, force=False, voltage_zero_threshold_v=0.05, current_zero_threshold_ma=1.0, settle_timeout_s=5.0)
get_fault_simulation() -> FaultSimulationMode
```

Fault simulation is disabled by default in `DriverSafetyPolicy`.

### Snapshot

```python
read_channel_configuration() -> ChannelConfiguration
```
