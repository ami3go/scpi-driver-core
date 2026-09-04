# Robot Framework Library Guide

## Architecture

`KeysightN6700Library` is an adapter over the existing `keysight_n6700` driver. It does not reimplement SCPI commands. This separation keeps hardware policy, module capability checks, transport behavior, and simulator behavior in one tested driver layer.

## Library import

```robotframework
Library    rf_keysight_n6700.KeysightN6700Library
```

Optional constructor arguments:

```robotframework
Library    rf_keysight_n6700.KeysightN6700Library    auto_shutdown=${TRUE}    strict_errors=${TRUE}
```

The library scope is `SUITE`. Each suite receives an independent session registry.

## Connection types

### Simulator

```robotframework
Connect To Simulated N6700    sim
```

### VISA

```robotframework
Connect To N6700 Via VISA    ${N6700_RESOURCE}    main
```

### Raw Ethernet socket

```robotframework
Connect To N6700 Via Ethernet    ${N6700_HOST}    5025    main
```

### Generic connection keyword

```robotframework
Connect To N6700    ${RESOURCE}    main    visa
Connect To N6700    ${HOST}        main    ethernet    5025
Connect To N6700    ${EMPTY}       sim     simulated
```

Connection is non-invasive by default. Reset and error queue clearing are only enabled through explicit arguments to `Connect To N6700`.

## Named sessions

Use aliases when a suite controls multiple mainframes:

```robotframework
Connect To Simulated N6700    left
Connect To Simulated N6700    right
Select N6700    left
${id_left}=    Get N6700 Identity
${id_right}=   Get N6700 Identity    right
```

Most keywords accept an optional final `alias` argument.

## Numeric conversion

The library accepts normal Robot numeric values and strings using engineering prefixes:

- `12`, `12.0`, `12V`
- `500mA`
- `10uA`, `10µA`
- `2.2k`, `1M`
- timeout values: `500ms`, `10s`, `2min`

Returned physical quantities are normal Python floats in base SI units: volts, amperes, and watts.

## Return values

Driver dataclasses are converted recursively to Robot-friendly dictionaries and lists. For example:

```robotframework
${m}=    Measure N6700 Channel    1
Log    Voltage = ${m}[voltage_V] V
Log    Current = ${m}[current_A] A
Log    Power source = ${m}[power_source]
```

## Safety and teardown

At disconnect and suite end, `auto_shutdown` calls the driver's best-effort `shutdown_all()` before closing each transport. The cleanup path attempts every channel even if one channel fails.

Combined configuration keywords leave the output or load input off unless an enable argument is explicitly true.

Recommended suite structure:

```robotframework
*** Settings ***
Library           rf_keysight_n6700.KeysightN6700Library
Suite Setup       Connect To N6700 Via VISA    ${N6700_RESOURCE}
Suite Teardown    Disconnect All N6700
Test Teardown     Shutdown All N6700 Channels
```

## Raw SCPI

Use `Write N6700 SCPI` and `Query N6700 SCPI` only for commands not yet represented by a typed keyword. Raw commands bypass module-type and capability checks.

## Generated keyword documentation

After installation:

```bash
python -m robot.libdoc KeysightN6700Library docs/KeysightN6700Library.html
```
