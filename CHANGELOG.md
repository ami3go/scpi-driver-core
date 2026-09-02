# Changelog

All notable changes to this project will be documented here.

The project follows Semantic Versioning once the public API reaches 1.0.0.

## [Unreleased]

### Added

- Initial repository skeleton.
- SCPI driver core implementation task.
- Common exception hierarchy in `scpi_driver_core.exceptions`.
- Transport value types: `TransportState`, `TransportDescriptor`, `ReadMode`,
  `ReadRequest`, `WriteResult`, `FlushDirection`, `ReplayPolicy`.
