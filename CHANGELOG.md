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
