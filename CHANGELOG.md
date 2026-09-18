# Changelog

All notable changes to this project will be documented here.

The project follows Semantic Versioning once the public API reaches 1.0.0.

## [Unreleased]

### Added

- Initial repository skeleton.
- SCPI driver core implementation task.
- Common exception hierarchy in `scpi_driver_core.exceptions`, re-exported from the
  top-level `scpi_driver_core` package.
- `ResponseParseError.raw`, retaining the response that failed to parse.
- Transport value types: `TransportState`, `TransportDescriptor`, `ReadMode`,
  `ReadRequest`, `WriteResult`, `FlushDirection`, `ReplayPolicy`.
- `Transport`, the byte-oriented transport protocol.
- `MockTransport`, a deterministic in-memory transport with failure injection,
  write fragmentation, and an operation log.
- A reusable transport conformance suite in `tests/transport_contract/`.
- `ScpiTextCodec` for SCPI text framing above the byte transport.
- `Identity` and `ScpiError` value types.
- Generic parsers: `parse_float`, `parse_int`, `parse_bool`, `parse_csv`,
  `parse_identity`, `parse_scpi_error`, `parse_optional_unit_float`,
  `quote_scpi_string`.
- `parse_engineering_value` for human-written values such as `500mA` or `2.2k`.
- `ScpiClient` with text and raw-byte operations, typed query helpers, timeout
  resolution, correlated operation IDs, and transaction locking.
- `TcpTransport` with buffered bounded reads, partial-write handling, remote
  disconnect detection, optional TCP_NODELAY, and deterministic cleanup.
- `UdpTransport` with datagram-preserving reads, optional local binding and
  source validation, and no implicit retransmission.
- Loopback TCP/UDP integration tests wired into the reusable transport contract.
- `SerialTransport` as an optional pyserial backend with finite read/write
  timeouts, serial-line configuration, DTR/RTS control, and directional flush.
- `VisaTransport` as an optional PyVISA backend: byte-preserving raw I/O with
  terminations disabled, second-to-millisecond timeout conversion, native
  `BACKEND_DEFINED_MESSAGE` reads, and resource-manager ownership rules.
- `Ieee4882` common-command helpers (`*IDN?`, `*CLS`, `*RST`, `*OPC`/`*OPC?`,
  `*WAI`, `*TRG`, `*TST?`, `*STB?`, `*ESR?`) with per-call timeout bounds.
- `SelfTestResult`, reporting the `*TST?` code without deciding a verdict.
- IEEE-488.2 definite-length binary blocks: `encode_definite_length_block`,
  `decode_definite_length_block`, and `read_definite_length_block`, with
  `ScpiClient.query_binary_block` and `write_binary_block` built on them.
- `ScpiTextCodec.encode_block_command` for framing a text prefix around a
  binary block.
- `ScpiErrorQueue` for `SYST:ERR?` reading and bounded draining, with
  configurable command and no-error codes.
- `ScpiExecutionPolicy` and `ScpiClient.enable_error_checking`, opt-in
  error-queue checks after writes or queries.
- `poll_until`, bounded polling on a monotonic deadline with an injectable
  clock.
- `RetryPolicy` and `run_with_retry`; `ScpiClient.query` accepts a retry policy
  only when the query is classified `ReplayPolicy.SAFE`.
- `RetryPolicy.constant`, a factory for a fixed-delay retry schedule (e.g. an
  instrument whose replies need a flat multi-second wait before a retry is
  worth attempting).
- `RetryPolicy.fast_attempts` and `RetryPolicy.max_delay_s`, extending a
  flat-delay plateau before `backoff` compounding starts, and capping how
  large any single wait can grow.
- `RetryPolicy.max_elapsed_s` and matching `run_with_retry(..., now=...)`
  support: a wall-clock retry budget that stops further attempts once
  crossed, independently of `attempts`.
- `RetryPolicy.progressive`, a factory for the "retry fast a few times, then
  back off, then give up after a deadline" shape.
- `run_with_retry(..., before_retry=...)`, called before each retried attempt.
- `ScpiClient.query(..., before_retry=...)`, forwarding to the above.
- `ScpiSession.recover_if_faulted`, reopening a transport a prior failure
  faulted (releasing its resource, per `Transport`'s contract) so a retried
  operation can actually reach the instrument again; meant to be passed as
  `ScpiClient.query(..., before_retry=session.recover_if_faulted)`. Without
  it, every retry after the first transport-level failure previously failed
  immediately with `NotConnectedError` instead of ever retrying anything.
- `ScpiClient(..., minimum_interval_s=..., sleep=..., now=...)`: an
  unconditional floor on the gap between successive operations, for a device
  documented to need quiet time between commands regardless of success.
- `parse_csv_floats`, splitting and parsing a comma-separated numeric reply,
  and `ScpiClient.query_csv_floats`, the typed query built on it.
- `ConfirmationGuard`, per-instance phrase confirmation with no global state.
- `ScpiSession`: transport ownership, connection generations, identity cache,
  health, an opt-in connection probe, and driver-supplied identity validation.
- `SessionHealth`, tracking responsiveness separately from transport state with
  an explicit unknown state.
- `SessionRegistry` with normalized aliases, a deterministic active session,
  and `disconnect_all` that closes every session even when one fails.
- `ProtocolTraceEvent`, `TraceObserver`, and `Tracer` with sequence numbering,
  dual UTC/monotonic clocks, and session/operation correlation.
- `InstrumentedTransport`, a transparent wrapper that traces every backend.
- `JsonlTraceSink`: append-only JSONL, schema version, base64 payloads, payload
  truncation, and deterministic finalization.
- `Redactor` protocol and `PatternRedactor`; redaction rewrites the recorded
  bytes as well as the text.
- `ScpiSession` keeps a tracer's alias and generation context current.
- `ScriptedScpiTransport`, a command-level instrument simulator with exact,
  regex, and predicate handlers, text/binary/block replies, forced timeouts,
  disconnects and delays, a simulated SCPI error queue, and command history.
- `MockTransport.operation_lock`, so a composed transport can keep a write and
  its matching read indivisible.
- Hypothesis property-based tests for binary-block framing and SCPI text-codec
  round trips, with a deterministic higher-volume CI profile.
- `pytest-timeout` watchdogs with per-test and whole-suite bounds so deadlocks
  and unbounded test hangs fail visibly in CI.
- PyVISA-sim integration coverage that exercises a simulated GPIB instrument
  through `VisaTransport`, `ScpiClient`, and `ScpiSession` without hardware.

### Changed

- Extracted `TransportStateMachine`, the lifecycle and state rules every
  backend had copied verbatim. TCP, UDP, serial, VISA and mock now share one
  implementation, removing about 130 duplicated lines.

### Fixed

- Session/client cross-layer locking now always acquires the client operation
  lock before the session state lock. This removes the AB/BA deadlock possible
  when a retry callback called `ScpiSession.recover_if_faulted()` while another
  thread held the session lock and was entering `ScpiClient`.
- `close()` now reaches `CLOSED` even when releasing the backend resource
  raises, instead of stranding the transport in `CLOSING`, a state nothing
  transitioned out of. The failure still propagates.

- Optional-unit parsing now honors `allow_non_finite=True` for responses such
  as `INF V`, rather than rejecting them before numeric parsing.
