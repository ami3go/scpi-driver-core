# RFDS-019 — Robot Framework Driver Call and Protocol Conformance Test Specification

**Version:** 1.1  
**Document ID:** RFDS-019  
**Status:** Project requirement  
**Applies to:** All RFDS Robot Framework driver packages

---

## 1. Purpose

This specification defines the mandatory test used to verify the interface path between:

```text
Robot Framework test
        ↓
public driver keyword
        ↓
driver protocol operation
        ↓
physical device or approved protocol simulator
        ↓
device response
        ↓
driver-parsed Robot Framework result
```

The test shall prove that every supported public Robot Framework keyword:

1. is discoverable;
2. can be called through Robot Framework with valid arguments;
3. invokes the intended driver operation;
4. sends the expected device protocol command, query, request, frame, or SDK call;
5. receives the expected device response when a response is applicable;
6. parses and returns that response correctly to Robot Framework;
7. reports protocol errors, malformed responses, and timeouts correctly;
8. remains traceable to recorded protocol evidence.

RFDS-019 verifies **driver callability and driver-to-device protocol conformance only**.

---

## 2. Scope Boundary

### 2.1 In scope

RFDS-019 covers:

- enumeration of exported public Robot Framework keywords;
- invocation of each supported public keyword through Robot Framework;
- validation of keyword names, arguments, defaults, aliases, and return values;
- mapping of each device-facing keyword to its expected protocol operation;
- capture and comparison of transmitted protocol data;
- capture and comparison of received protocol data;
- verification of response parsing and Robot Framework-compatible return values;
- command-only operations that intentionally have no response;
- query and read operations;
- connection and disconnection protocol operations;
- documented protocol errors;
- protocol timeouts;
- malformed or incomplete protocol responses;
- protocol recovery sufficient to execute a subsequent valid keyword;
- approved simulator-based protocol verification;
- real-device protocol verification where safe and practical.

### 2.2 Out of scope

RFDS-019 does not verify:

- whether the driver implements every function available in the vendor manual;
- internal driver architecture or source-code quality;
- private methods and implementation helpers;
- unit-test line or branch coverage;
- package structure, wheel creation, installation, CI, or release packaging;
- README, GitHub Pages, examples, or general documentation completeness;
- physical measurement accuracy;
- instrument calibration accuracy;
- electrical performance;
- waveform quality;
- long-duration stability, stress, or throughput;
- multi-session concurrency unless it changes the protocol exchange under test;
- complete safety certification;
- full driver production readiness.

These matters shall be covered by other RFDS requirements and device-specific implementation tasks.

---

## 3. Normative Terminology

- **shall / shall not** — mandatory requirement;
- **should / should not** — recommended requirement; deviations require justification;
- **may** — permitted implementation choice.

---

## 4. Required Test Artifacts

Each driver package shall provide, directly or through equivalent files:

```text
rf_<driver_name>/
└── tests/
    └── conformance/
        ├── driver_call_protocol_conformance.robot
        ├── resources/
        │   ├── conformance_keywords.resource
        │   └── conformance_variables.resource
        ├── data/
        │   ├── keyword_inventory.yaml
        │   ├── protocol_vectors.yaml
        │   └── exclusions.yaml
        └── expected/
            └── response_schemas/
```

The package shall also provide a repeatable command or script that executes the conformance suite and creates a timestamped results directory.

---

## 5. Keyword Inventory

The test shall generate the public Robot Framework keyword inventory using Robot Framework Libdoc, runtime introspection, or an equivalent deterministic method.

Each inventory entry shall contain at least:

- public keyword name;
- canonical keyword name;
- aliases, when applicable;
- driver method or adapter target;
- argument names;
- required arguments;
- optional arguments and defaults;
- return type;
- device-facing classification: `yes` or `no`;
- protocol vector reference;
- execution status;
- exclusion reason, when applicable.

A public keyword shall not be silently omitted.

Private methods and methods intentionally excluded from Robot Framework shall not be included in the public keyword denominator.

---

## 6. Conformance Levels

### 6.1 Level 0 — Keyword Discovery

Verify that:

- the library imports;
- Robot Framework loads the library;
- public keywords can be enumerated;
- keyword names are unique after Robot Framework normalization;
- aliases are identified;
- signatures and defaults are valid;
- every device-facing keyword has a protocol vector or approved exclusion.

### 6.2 Level 1 — Robot Framework Callability

Invoke every supported public keyword through Robot Framework with at least one valid argument set.

This level shall detect:

- missing keywords;
- incorrect keyword names;
- incorrect argument counts;
- invalid defaults;
- Robot Framework conversion failures;
- unexpected `AttributeError` or `TypeError`;
- non-serializable return values;
- deadlock or unbounded execution.

### 6.3 Level 2 — Outbound Protocol Verification

For each device-facing keyword, verify the transmitted protocol operation.

Supported operation types include:

- SCPI command or query;
- serial ASCII command;
- serial binary frame;
- VISA write or query;
- HTTP request;
- Modbus transaction;
- CAN frame;
- USB request;
- vendor SDK function call;
- GPIO or relay command exposed through an SDK.

The test shall compare the actual transmitted operation with the expected operation defined by the protocol vector.

### 6.4 Level 3 — Inbound Protocol and Return Verification

Where a device response is expected, verify:

1. the raw response received from the device or simulator;
2. protocol framing and termination;
3. response parsing;
4. conversion to the documented Python type;
5. conversion to a Robot Framework-compatible result;
6. returned value, schema, or tolerance.

For command-only operations, the vector shall explicitly declare that no response is expected and shall define any required acknowledgement or error check.

### 6.5 Level 4 — Protocol Error and Recovery Verification

Verify the driver behavior for applicable protocol failures:

- timeout;
- empty response;
- malformed response;
- incomplete frame;
- unexpected response type;
- device error code;
- transport disconnection;
- unsupported command response;
- checksum or frame-integrity failure.

After a documented recoverable failure, the suite shall execute a subsequent valid keyword and verify that protocol communication still works or is correctly re-established.

---

## 7. Protocol Vector Requirements

Every device-facing public keyword shall have at least one protocol vector.

A vector shall define equivalent information to:

```yaml
keyword: Set DC Voltage
canonical_keyword: Set DC Voltage
driver_method: set_dc_voltage
arguments:
  channel: 1
  voltage: 5.0
preconditions:
  - connected
expected_outbound:
  transport: scpi
  operation: "VOLT 5.0,(@1)"
expected_inbound:
  response_required: false
expected_return:
  type: null
protocol_error_check:
  operation: "SYST:ERR?"
  expected: '0,"No error"'
timeout_s: 10
cleanup_keywords:
  - Set DC Voltage    1    0.0
```

For a query:

```yaml
keyword: Get Identity
canonical_keyword: Get Identity
driver_method: get_identity
arguments: {}
preconditions:
  - connected
expected_outbound:
  transport: scpi
  operation: "*IDN?"
expected_inbound:
  response_required: true
  raw_pattern: "<manufacturer>,<model>,<serial>,<firmware>"
expected_return:
  type: string
  schema: idn_string
timeout_s: 5
```

The schema may be adapted to the protocol, but it shall preserve the same verification intent.

---

## 8. Argument Coverage

The objective of argument testing under RFDS-019 is to confirm correct call construction and protocol serialization.

For each argument-bearing device keyword, vectors shall cover as applicable:

- one nominal valid value;
- minimum and maximum supported values when these change protocol serialization;
- representative enum or mode values;
- omitted optional argument;
- explicit default argument;
- invalid value that shall be rejected before transmission;
- invalid value that the device is expected to reject;
- repeated invocation when the protocol behavior may differ.

RFDS-019 does not require exhaustive functional or physical boundary characterization.

---

## 9. Protocol Oracles

Each device-facing vector shall use one or more explicit oracles.

### 9.1 Outbound Exact-Match Oracle

Verify exact transmitted bytes or text after documented normalization.

### 9.2 Outbound Structured Oracle

Decode and verify fields such as:

- command header;
- address;
- channel;
- function code;
- data length;
- payload;
- checksum;
- terminator;
- HTTP method, path, headers, and body;
- SDK function and arguments.

### 9.3 Raw Response Oracle

Verify the raw response bytes or text before parsing.

### 9.4 Response-Schema Oracle

Verify the documented response structure, fields, types, units, enum values, and nullability.

### 9.5 Parsed-Value Oracle

Verify exact equality, pattern matching, or documented numeric tolerance for the value returned to Robot Framework.

### 9.6 No-Response Oracle

Verify that the operation is command-only and that the driver does not incorrectly wait for a response.

### 9.7 Protocol Error Oracle

Verify the documented exception type, Robot Framework failure text, device error code, or transport error.

A keyword shall not pass only because it returned without an exception.

---

## 10. Transport Observation

The conformance implementation shall provide a way to observe protocol exchange using one or more of:

- instrumented simulator;
- transport spy or wrapper;
- mock transport at the protocol boundary;
- VISA trace;
- serial trace;
- TCP proxy or packet capture;
- HTTP request log;
- CAN trace;
- vendor SDK spy;
- device diagnostic log.

The selected observation point shall be close enough to the device boundary to prove what the driver attempted to transmit and what it received.

Internal method-call mocking alone is insufficient when it does not verify the serialized device protocol.

Credentials and other secrets shall be redacted from evidence.

---

## 11. Simulator and Real-Device Use

### 11.1 Approved simulator

An approved simulator may be used to verify:

- all outbound commands and queries;
- valid responses;
- malformed responses;
- timeouts;
- protocol error codes;
- framing and parsing;
- deterministic edge cases.

The simulator shall operate at the same protocol boundary used by the real device connection.

### 11.2 Real device

A real device should be used to confirm representative protocol exchanges for each protocol family and command class supported by the driver.

RFDS-019 does not require independent physical measurement of the device output. The real-device result may be verified through:

- device acknowledgement;
- documented query response;
- read-back command;
- status or error query;
- device-side protocol log.

Operations that cannot be safely executed shall use an approved simulator or transport spy and shall be listed in `exclusions.yaml`.

---

## 12. Required Execution Workflow

### Step 1 — Preflight

- capture driver package version;
- capture Python version;
- capture Robot Framework version;
- capture operating system;
- capture transport type and configuration;
- select simulator or real-device profile;
- confirm the protocol trace mechanism.

### Step 2 — Inventory

- enumerate public Robot Framework keywords;
- identify canonical keywords and aliases;
- identify device-facing keywords;
- associate each device-facing keyword with a protocol vector;
- fail on unexplained omissions.

### Step 3 — Establish Communication

- call the driver connection keyword;
- verify the expected open/connect protocol behavior;
- execute the identity or equivalent communication query when supported;
- record the raw and parsed response.

### Step 4 — Execute Callability Tests

- call every supported public keyword through Robot Framework;
- record arguments, result, duration, and status.

### Step 5 — Verify Outbound Protocol

For every device-facing keyword:

- start trace capture;
- call the keyword;
- stop trace capture;
- compare actual and expected outbound protocol data.

### Step 6 — Verify Inbound Protocol

For every response-producing keyword:

- record the raw response;
- verify framing and schema;
- verify parsed return type and value.

### Step 7 — Verify Protocol Failures

Execute applicable timeout, malformed-response, device-error, and disconnect vectors.

### Step 8 — Verify Recovery

After each recoverable protocol fault, execute one known-good communication keyword and verify successful communication.

### Step 9 — Disconnect

- call the driver disconnect or close keyword;
- verify the expected transport close behavior;
- confirm that no protocol operation remains blocked indefinitely.

### Step 10 — Generate Evidence

Generate the mandatory coverage and protocol reports.

---

## 13. Coverage Matrix

The generated coverage matrix shall contain at least:

| Field | Requirement |
|---|---|
| Keyword name | Exported Robot Framework name |
| Canonical keyword | Canonical public name |
| Driver method | Implementation target |
| Device-facing | Yes/No |
| Transport type | SCPI, serial, HTTP, SDK, and so on |
| Protocol vector | Vector identifier |
| Callability tested | Yes/No |
| Outbound verified | PASS/FAIL/N/A |
| Raw response verified | PASS/FAIL/N/A |
| Parsed result verified | PASS/FAIL/N/A |
| Protocol error tested | PASS/FAIL/N/A |
| Recovery tested | PASS/FAIL/N/A |
| Result | PASS/FAIL/SKIP/EXCLUDED |
| Evidence | Trace or report reference |
| Reason | Required for SKIP or EXCLUDED |

Aliases shall be listed individually, even when they map to the same driver method.

---

## 14. Coverage Metrics

The report shall calculate:

```text
Keyword Inventory Coverage
    = inventoried public keywords / exported public keywords

Keyword Callability Coverage
    = called public keywords / executable public keywords

Protocol Vector Coverage
    = device-facing keywords with vectors / device-facing public keywords

Outbound Protocol Coverage
    = outbound-verified keywords / device-facing executable keywords

Inbound Protocol Coverage
    = response-verified keywords / response-producing executable keywords

Protocol Error Coverage
    = executed protocol-error vectors / applicable protocol-error vectors
```

Skipped and excluded keywords shall remain visible in the report.

---

## 15. Acceptance Criteria

A driver passes RFDS-019 only when:

1. 100% of exported public Robot Framework keywords are inventoried;
2. 100% of supported executable public keywords are called through Robot Framework;
3. every device-facing public keyword has a protocol vector or approved exclusion;
4. every executed device-facing keyword transmits the expected protocol operation;
5. every response-producing keyword receives and parses the expected protocol response;
6. every returned value has the documented Robot Framework-compatible type;
7. command-only keywords do not incorrectly wait for a response;
8. documented protocol timeouts and malformed responses produce the expected failure;
9. recoverable protocol failures permit a subsequent known-good call after recovery;
10. aliases produce protocol behavior equivalent to their canonical keyword unless explicitly documented otherwise;
11. every PASS result has traceable evidence;
12. all mandatory vectors pass;
13. every SKIP or EXCLUDED result has a documented and approved reason.

---

## 16. Failure Conditions

RFDS-019 shall fail when:

- an exported public keyword is omitted from inventory;
- a supported public keyword cannot be invoked through Robot Framework;
- the keyword calls the wrong driver operation;
- a device-facing keyword has no protocol vector and no approved exclusion;
- the driver transmits the wrong command, query, request, frame, or SDK call;
- arguments are serialized incorrectly;
- command framing, checksum, terminator, address, or payload is incorrect;
- a query reads the wrong response or parses it incorrectly;
- the returned Robot Framework value has the wrong type or content;
- a command-only operation waits for an undefined response;
- a device protocol error is reported as success;
- a timeout or malformed response produces undocumented behavior;
- a documented recoverable protocol failure leaves communication unusable;
- an alias produces different protocol behavior without documentation;
- required trace evidence is missing.

---

## 17. Result Statuses

Only these statuses are permitted:

- **PASS** — required call and protocol oracles passed;
- **FAIL** — one or more required call or protocol oracles failed;
- **SKIP** — execution could not occur because a declared prerequisite was unavailable;
- **EXCLUDED** — execution is intentionally prohibited or not applicable and has an approved reason;
- **NOT RUN** — no execution occurred; this fails acceptance unless converted to approved SKIP or EXCLUDED.

---

## 18. Evidence and Reporting

Each run shall produce:

- Robot Framework `output.xml`;
- Robot Framework `log.html`;
- Robot Framework `report.html`;
- machine-readable keyword inventory;
- CSV or JSON coverage matrix;
- protocol vector results;
- outbound protocol trace;
- inbound protocol trace where responses apply;
- environment and driver version record;
- connected device identity when available;
- skips and exclusions report;
- Markdown summary.

Recommended layout:

```text
results/call_protocol_conformance/<driver>/<timestamp>/
├── output.xml
├── log.html
├── report.html
├── conformance_summary.md
├── keyword_inventory.json
├── keyword_coverage.csv
├── protocol_vector_results.json
├── outbound_trace.log
├── inbound_trace.log
├── environment.json
├── device_identity.json
└── exclusions.json
```

Every trace entry shall identify the keyword and protocol vector that produced it.

---

## 19. Integration with RFDS-017

RFDS-017 may provide the following source information for RFDS-019:

- canonical keyword name;
- aliases;
- signature;
- argument types;
- return type;
- expected protocol operation;
- response schema;
- timeout behavior;
- protocol errors;
- connection preconditions.

RFDS-019 shall not use RFDS-017 to assess complete device-capability implementation. It uses RFDS-017 only to define and verify the declared public calls and expected protocol exchange.

---

## 20. Integration with RFDS-018

RFDS-018 is required only when the conformance test needs real-device or bench connection information, including:

- device address;
- transport configuration;
- required fixture;
- allowed command profile;
- prohibited operations;
- startup and shutdown sequence.

RFDS-019 does not require independent measurement equipment unless that equipment is necessary to observe the protocol itself.

---

## 21. Change Control

Whenever a public keyword or its protocol behavior is added, removed, renamed, aliased, deprecated, or changed, the same driver revision shall update:

- keyword inventory;
- protocol vector;
- expected outbound operation;
- expected response or no-response declaration;
- expected return type;
- protocol-error vectors when applicable;
- conformance evidence.

A public call or protocol change without a corresponding RFDS-019 update shall fail conformance review.

---

## 22. Review Checklist

1. Are all exported public Robot Framework keywords inventoried?
2. Was every supported public keyword called through Robot Framework?
3. Is every device-facing keyword linked to a protocol vector?
4. Was the actual outbound protocol operation captured?
5. Does the outbound operation match the expected command, frame, request, or SDK call?
6. Was the raw device response captured when applicable?
7. Was the response parsed correctly?
8. Does the Robot Framework return value have the expected type and value?
9. Are command-only operations explicitly marked as no-response operations?
10. Were documented timeouts and malformed responses tested?
11. Were device protocol errors reported correctly?
12. Was communication restored after recoverable protocol failures?
13. Do aliases produce equivalent protocol behavior?
14. Are all skips and exclusions justified?
15. Is every result traceable to protocol evidence?

---

## 23. Minimum Definition of Done

RFDS-019 is complete when:

- the full public keyword inventory is generated;
- every supported public keyword is called through Robot Framework;
- every device-facing public keyword has an approved protocol vector;
- every executed device-facing keyword has outbound protocol evidence;
- every response-producing keyword has inbound and parsed-result evidence;
- applicable protocol error and recovery vectors pass;
- all required reports are generated;
- no mandatory call or protocol verification remains NOT RUN;
- all acceptance criteria in Section 15 pass.

---

## 24. Goal

Provide objective proof that every declared Robot Framework driver call reaches the intended device protocol operation and that every applicable device response is correctly received, interpreted, and returned by the driver.

---

## Appendix A — Changes from Version 1.0

Version 1.1 narrows RFDS-019 to:

- public keyword discovery;
- Robot Framework callability;
- outbound driver-to-device protocol verification;
- inbound device-to-driver response verification;
- protocol parsing;
- protocol errors, timeouts, and recovery;
- traceable conformance evidence.

The following subjects were removed from RFDS-019 scope:

- full driver implementation coverage;
- vendor-manual feature completeness;
- architecture review;
- packaging and release readiness;
- physical output accuracy;
- calibration verification;
- performance and soak testing;
- general documentation completeness.
