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

### Fixed

- Optional-unit parsing now honors `allow_non_finite=True` for responses such
  as `INF V`, rather than rejecting them before numeric parsing.
