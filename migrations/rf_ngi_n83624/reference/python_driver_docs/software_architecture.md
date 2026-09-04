# Software Architecture Map

This document describes the intended architecture of the `ngi-n83624` Python driver package.
The driver is organised as a layered instrumentation library: user test scripts call a typed high-level API, the API validates and sequences commands safely, and a transport abstraction sends raw SCPI over TCP, UDP, or RS232.

## High-Level Architecture

```mermaid
flowchart TB
    subgraph UserLayer[User / Test Automation Layer]
        A1[Test scripts]
        A2[pytest / CI]
        A3[Bench supervisor]
        A4[Examples]
    end

    subgraph PublicAPI[Public Driver API]
        B1[N83624CellSimulator]
        B2[N83624Channel]
        B3[Raw SCPI escape hatch\nwrite / query]
    end

    subgraph SafetyLayer[Safety and Validation Layer]
        C1[Channel validation]
        C2[InstrumentLimits / ChannelLimits]
        C3[DriverSafetyPolicy]
        C4[BenchInterlock]
        C5[Full-duration operation lock]
        C6[Fault relay settle-to-zero checks]
    end

    subgraph DomainLayer[Domain Command Layer]
        D1[Common commands]
        D2[Measurement]
        D3[Output mode / status]
        D4[Source mode]
        D5[Charge mode]
        D6[SOC profiles]
        D7[Sequence profiles]
        D8[Protection]
        D9[CAN queries]
        D10[System / HMI / fault simulation]
    end

    subgraph ProtocolLayer[SCPI Protocol Layer]
        E1[Command formatting]
        E2[Response parsing]
        E3[Error mapping]
        E4[Retry / timeout policy]
        E5[Session state machine]
        E6[Heartbeat / reconnect]
    end

    subgraph TransportLayer[Transport Layer]
        F1[Transport Protocol]
        F2[TcpTransport\nport 7000]
        F3[UdpTransport\n7000 all-channel\n7001-7024 single-channel]
        F4[SerialTransport\nRS232]
        F5[FakeTransport / Emulator\nfor tests]
    end

    subgraph HardwareLayer[Hardware Layer]
        G1[NGI N83624\ncommunication board]
        G2[Channels 1-24]
        G3[DUT / BMS / test bench]
    end

    A1 --> B1
    A2 --> F5
    A3 --> B1
    A4 --> B1
    B1 --> B2
    B1 --> B3
    B2 --> C1
    B3 --> E1
    C1 --> C2
    C2 --> C3
    C3 --> C4
    C4 --> C5
    C5 --> C6
    C6 --> D1
    D1 --> E1
    D2 --> E1
    D3 --> E1
    D4 --> E1
    D5 --> E1
    D6 --> E1
    D7 --> E1
    D8 --> E1
    D9 --> E1
    D10 --> E1
    E1 --> E2
    E2 --> E3
    E3 --> E4
    E4 --> E5
    E5 --> E6
    E6 --> F1
    F1 --> F2
    F1 --> F3
    F1 --> F4
    F1 --> F5
    F2 --> G1
    F3 --> G1
    F4 --> G1
    G1 --> G2
    G2 --> G3
```

## Package-Level Responsibility Map

```text
ngi_n83624/
├── __init__.py          Public exports and package version
├── driver.py            N83624CellSimulator, connection lifecycle, raw SCPI, heartbeat, reconnect
├── channel.py           N83624Channel high-level per-channel command API
├── transports.py        Transport Protocol, TCP, UDP, RS232 implementations
├── models.py            Enums, dataclasses, limits, retry policy, session state, measurement/status models
├── safety.py            Validation helpers, interlock interface, safe-operation policies
├── parsing.py           Numeric parsing, boolean parsing, response parsing utilities
├── exceptions.py        Typed exception hierarchy and vendor error-code mapping
├── commands.py          Shared SCPI command constants/helpers
├── logging_utils.py     Driver logging setup
└── emulator.py          Simple fake/emulated instrument for tests and examples
```

## Runtime Call Flow

Example: `ch1.configure_source(..., output=True)`

```text
User script
  ↓
N83624CellSimulator.tcp(...)
  ↓
N83624Channel.configure_source(...)
  ↓
Acquire full-duration instrument lock
  ↓
Validate channel number, units, limits, interlock, safety policy
  ↓
OUTPut1:ONOFF 0
OUTPut1:MODE 0
SOURce1:VOLTage <voltage>
SOURce1:OUTCURRent <current>
SOURce1:RANGe <range>
  ↓
Optional read-back verification
  ↓
If requested and allowed by safety policy/interlock:
OUTPut1:ONOFF 1
  ↓
Release lock
```

## Safety-Critical Locking Rule

The transport lock is not only for single `write()` or `query()` calls. It must be held for the entire duration of compound operations, including:

- configure-source / configure-charge / configure-SOC / configure-sequence command groups;
- write-then-readback verification;
- output-off-before-mode-change sequences;
- fault simulation settle-to-zero loops;
- reconnect state resynchronisation.

This prevents another thread from changing the same instrument state between safety-critical steps.

## UDP Architecture Rule

- UDP port `7000` represents the communication-board interface and may be used with the normal 24-channel API.
- UDP ports `7001` through `7024` are channel-specific fast-acquisition/control ports.
- A channel-specific UDP transport must be bound to exactly one `N83624Channel` context. The driver must reject calls to any other channel through that transport.

## Production Boundary

The driver is not a complete safety system. It must be integrated with external bench-level protections such as emergency stop, fusing, contactors, independent measurement, DUT-specific limits, and test-supervisor abort logic.
