# RFDS-018 --- AI Test Bench Contract Specification

Version: 1.0 (Draft)

## Purpose

Defines the complete hardware test environment. It combines multiple
RFDS-017 driver contracts into one coherent laboratory model that an AI
planner can use to generate end-to-end validation plans.

## Required File

    system_ai_contract.yaml

## Mandatory Sections

### Available Drivers

List installed drivers and versions.

### Physical Topology

Describe wiring between instruments, relay matrices, DUT interfaces and
measurement points.

### Shared Resources

USB, VISA, LAN, serial ports, power rails, fixtures and any exclusive
resources.

### Signal Graph

Define producers and consumers of electrical, digital and environmental
signals.

### Preferred Measurement Sources

Specify which instrument should be preferred for each measurable
quantity.

### Requirement Coverage

Map system requirements to available drivers and verification
objectives.

### Test Templates

Reusable multi-driver workflows (e.g. PSU → Relay → DUT → DMM).

### Bench Constraints

-   Operator actions
-   Safety zones
-   Maximum simultaneous operations
-   Environmental limits

### Scheduling Rules

-   Resource conflicts
-   Driver ordering
-   Stabilization rules
-   Parallel execution limits

### Global Safety

Bench-wide forbidden sequences and emergency shutdown workflow.

## Goal

Enable an AI agent to automatically synthesize complete multi-instrument
Robot Framework test plans using RFDS-017 driver contracts together with
the laboratory description.
