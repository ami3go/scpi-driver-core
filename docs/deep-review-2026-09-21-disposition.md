# Deep review disposition — 2026-09-21

This document records the disposition of the 38 findings in the external deep review of `main@241d4b6` (`0.1.0.dev5`). The implementation release is `0.1.0.dev6`.

The review's runtime-integrity concerns are accepted. A few proposed remedies were adjusted where the suggested default could itself be destructive or where a stricter implementation was possible. Hardware-dependent claims are intentionally marked **HIL pending** rather than inferred from simulation.

## Disposition

| ID | Status | Implemented behavior / decision |
| --- | --- | --- |
| SDC-01 | Implemented | `VisaTransport` never closes a PyVISA `ResourceManager`; it closes only its own resource. Multi-session regression coverage proves one transport cannot invalidate a sibling through manager teardown. |
| SDC-02 | Implemented | UDP read timeout faults and closes the socket; a recovered transport uses a fresh socket and bounded stale-datagram draining. Fixed-port `local_bind` races remain documented because generic UDP has no response correlation. |
| SDC-03 | Implemented | Shared `_faulting_io()` faults on any escaping `BaseException`, including `KeyboardInterrupt`, and `_fault()` reaches `FAULTED` even if resource release raises. |
| SDC-04 | Implemented | `Transport.invalidate()` is part of the contract; multi-step binary block queries invalidate the stream after any partially consumed framing failure. Block timeouts remain transport timeouts. |
| SDC-05 | Implemented | Retryable `before_retry` failures consume an attempt instead of aborting the retry budget. `RetryAttempt.phase` distinguishes recovery and operation failures. |
| SDC-06 | Implemented | Read-mode completion semantics and post-timeout behavior are normative. Mock/scripted default to the faulting hardware profile; non-faulting polling behavior is explicit opt-in. |
| SDC-07 | Implemented; HIL pending | VISA `flush()` uses local `viFlush` discard operations and never calls Device Clear. `device_clear()` is an explicit capability. Real USBTMC/GPIB verification remains HIL. |
| SDC-08 | Implemented with stronger isolation | Guard locks protect state only and are never held across user code. Scoped enablement is thread-local; `disable()` revokes open scoped windows via an epoch without waiting. |
| SDC-09 | Implemented | Redaction fails closed through a lossless Latin-1 byte view when primary decoding fails. Responses can be redacted using the originating command through `sensitive_queries`. Observer failures are counted and logged. |
| SDC-10 | Implemented | Text command framing rejects embedded CR/LF/terminators, and `quote_scpi_string()` rejects line breaks. Binary block paths remain intentionally exempt. |
| SDC-11 | Implemented with modified policy | The safe default is now uniform: an uncertain I/O timeout faults the transport. Cheaper/destructive recovery is explicit (for example VISA Device Clear) rather than automatically invoked on timeout. |
| SDC-12 | Implemented | Binary block operations use transport-level `operation_lock()`, invalidate on partial-read failure, and participate in configured SCPI error-queue checking. |
| SDC-13 | Implemented | Transport state uses a small state lock/reference read separate from the long-lived I/O serialization lock, so `state`/`is_open`/`is_connected` do not wait for instrument I/O. |
| SDC-14 | Implemented with conservative audit semantics | Successful TX is emitted only after a successful transaction. On an uncertain failed transaction the outbound attempt is recorded as TX `success=False`, followed by the receive-side failure; no audit record falsely states that the command was transmitted successfully. |
| SDC-15 | Implemented | Trace context can be bound per `InstrumentedTransport`, so multiple sessions may safely share one tracer/sink. Legacy tracer context remains the fallback for a single unbound transport. |
| SDC-16 | Implemented | `ScpiClient` outcome listeners feed normal traffic into session health. `health.connected` reflects live transport state and failed opens preserve their diagnostic error. |
| SDC-17 | Implemented | Auto-recovery is allowed only from `FAULTED`. `CREATED`/deliberately `CLOSED` sessions raise `SessionClosedError`. Recovery repeats the original probe/identity validator before retry traffic continues. |
| SDC-18 | Implemented with modified failure policy | `ScpiErrorQueueError` carries structured `.errors` and `.complete`; overflow and parse failures preserve every popped entry. Automatic draining after an already-failed transport operation is not forced because the stream may be invalid; drivers can drain explicitly after safe recovery. |
| SDC-19 | Implemented; HIL pending | Message-based VISA resources use `BACKEND_DEFINED_MESSAGE` by default; normal codec decoding removes a trailing configured terminator, making LF-terminated and END-only behavior consistent. Vendor-specific ASRL/SOCKET behavior remains HIL. |
| SDC-20 | Implemented | VISA message reads use bounded low-level reads and enforce `maximum_size` during acquisition rather than after unbounded `read_raw()` accumulation. |
| SDC-21 | Implemented | Serial timeout attributes are changed only when the requested value differs, avoiding per-operation port reconfiguration. |
| SDC-22 | Implemented | Serial `EXACT_LENGTH` uses one call-level timeout budget; `UP_TO_LENGTH` waits for the first byte then consumes currently available bytes without deliberately waiting for the full requested length. |
| SDC-23 | Implemented; platform/HIL verification pending | Serial supports `rtscts`, `dsrdtr`, `xonxoff`, `exclusive`, URL handlers through `serial_for_url`, and pre-open DTR/RTS configuration when the backend supports it. Physical adapter line-glitch behavior is HIL/platform dependent. |
| SDC-24 | Implemented | Standard SCPI `9.9E37`, `-9.9E37`, and `9.91E37` special values map to ±Inf/NaN by default and are rejected unless non-finite values are allowed. An opt-out preserves raw finite interpretation when required. |
| SDC-25 | Implemented | Scripted simulation supports compound program messages, scheduled/delayed replies, thread-safe command/reply ordering, late replies, and correct quoting of error text. |
| SDC-26 | Implemented; HIL pending | Optional capability protocols cover Device Clear, serial poll, bus trigger, and local control. VISA implements them; `Ieee4882.read_status_byte()` prefers serial poll where available. Physical bus behavior remains HIL. |
| SDC-27 | Implemented | `ScpiSession.operation_lock()` and transport locking are typed as `AbstractContextManager[None]`, so strict downstream `with` usage type-checks. |
| SDC-28 | Implemented with documented resolver limitation | Socket endpoint/configuration exceptions are translated, `select()` dependency was removed from high-fd paths, receive/flush work is byte/deadline bounded. OS DNS resolution itself cannot be pre-empted portably by Python's blocking resolver and remains a documented platform limitation. |
| SDC-29 | Implemented | Numeric parsing is restricted to ASCII SCPI decimal syntax; underscores, non-ASCII digits and non-decimal forms are rejected. `Decimal` preserves integral values above `2**53`. |
| SDC-30 | Implemented with optional human-input strictness | Engineering prefixes scale through `Decimal` before the single float conversion. Ambiguous case checking is available as strict human-input behavior rather than invalidating standards-valid forms globally. |
| SDC-31 | Implemented | `ScpiTimeoutError` is the common timeout base. Binary-block read timeouts remain `TransportTimeoutError` instead of being relabelled as protocol errors. |
| SDC-32 | Implemented | `FrozenMetadata` replaces `MappingProxyType`, retaining immutability while supporting pickle, deepcopy and dataclass serialization. |
| SDC-33 | Implemented with per-attempt locking | Exponential backoff is overflow-safe. Client serialization is held per retry attempt, not through backoff sleep; the successful attempt and its error-queue check remain atomic. A session recovery callback also makes deliberate close non-recoverable via `SessionClosedError`. |
| SDC-34 | Implemented | Trace observer failures increment `dropped_events` and log warnings; payload limits are validated; optional `fsync_each_event` provides OS-level durability. |
| SDC-35 | Implemented | Transports, sessions, instrumented transports and the session registry support deterministic context-manager cleanup. |
| SDC-36 | Implemented as part of this release | Documentation is updated to match timeout, VISA flush, message-boundary, state-introspection and simulator guarantees. Hardware-only claims are explicitly marked rather than asserted from simulation. |
| SDC-37 | Implemented | TCP terminator scanning remembers progress, receive allocation is chunk-bounded, transfer copies are reduced, and trace recording uses a bounded `deque`. |
| SDC-38 | Implemented | Registry aliases must match `session.alias` after normalization and the same session object cannot be registered under multiple aliases. |

## Verification model

The software changes are verified through the normal hardware-free matrix on Python 3.10–3.13: strict Ruff/format/mypy, unit and transport-contract tests, Hypothesis properties, local TCP/UDP integration, PyVISA-sim, pytest-timeout watchdogs, and the branch-coverage gate.

The following claims still require physical equipment before they should be called hardware-qualified:

- VISA local flush versus Device Clear behavior on representative NI-VISA/Keysight IO Libraries and USBTMC/GPIB hardware (SDC-07).
- END/EOI and vendor-specific `ASRL` / `TCPIP::SOCKET` behavior (SDC-19).
- Serial DTR/RTS glitch behavior, exclusivity and hardware handshake on representative adapters/instruments (SDC-23).
- Device Clear, serial poll, bus trigger and local-control semantics on a real IEEE-488-capable instrument (SDC-26).

No simulator result is treated as proof of those physical-bus behaviors.
