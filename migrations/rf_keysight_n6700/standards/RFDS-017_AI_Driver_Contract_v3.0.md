# RFDS-017 --- AI Driver Contract Specification

Version: 3.0 (Draft)

## Purpose

Defines the canonical AI-readable contract for a single Robot Framework
driver. An AI agent shall be able to understand, safely use, and
generate Robot Framework tests for one driver without reading its source
code.

## Scope

Covers only one driver and one instrument/library.

## Required Files

    ai/
      ai_contract.yaml
      ai_contract.lock

## Mandatory Sections

-   Identity
-   Mental model
-   State machine
-   Resources consumed/provided
-   Dependencies
-   Capabilities (one per Robot keyword)
-   Error catalogue
-   Safety rules
-   Verification objectives with pass/fail oracles
-   Setup/teardown contract
-   Limitations
-   Planning hints
-   UNKNOWN handling
-   Conformance rules

## Capability Requirements

Each Robot keyword shall define: - Signature - Purpose -
Inputs/outputs - Preconditions - Postconditions - Side effects - Risk
level - Timing - Stabilization delay - Retry policy - Errors - Exclusive
resources

## Goal

Enable AI to generate correct Robot Framework tests for a single driver
and expose machine-verifiable semantics.
