# Task: SCPI core readiness for N6700 arbitrary waveform generation

**Task ID:** CORE-ARB-001 · **Prepared:** 2026-10-15 · **Status:** CORE IMPLEMENTATION COMPLETE; HARDWARE QUALIFICATION OUTSTANDING
**Repository:** https://github.com/ami3go/scpi-driver-core
**Audited baseline:** `main@d850f88a78ddfbfa08b667c0be6cbb0bb4a01541`, package `0.1.0.dev6`
**Companion task:** [keysight-n6700-driver Arb task](https://github.com/ami3go/keysight-n6700-driver/blob/main/docs/ARB_DRIVER_IMPLEMENTATION_TASK.md)
**Boundary:** only reusable SCPI byte transport, framing, timing, test-harness, diagnostics and documentation. No Keysight shape definitions, module/Option 054 checks, output-enable control or waveform-specific protection in this repository.

> **Documentation task, not a completion claim.** The publication of this plan increments the package's documentation revision; all software changes below need separate reviewed PRs, compatibility testing and new version increments. No hardware is operated by this plan.

## 1. Objective and design decision

Enable dependable large waveforms, finite command sequences and physical-test diagnostics across VISA/TCP/serial without changing the existing `Transport` contract unnecessarily. The existing core already provides:
- `ScpiClient.write/query`, `write_bytes/read_bytes/transact_bytes`, `operation_lock`, error queues and typed CSV queries;
- `write_binary_block/query_binary_block` and IEEE-488.2 **definite-length** binary-block codec;
- serialized, byte-preserving VISA/TCP/serial transports; fail-on-uncertain-timeout semantics;
- `poll_until`, safe-replay policy, named sessions, scripted simulation and trace observers.

**Conclusion:** no core refactor is a prerequisite for initial finite voltage STEP/RAMP/SIN/PULSE implementation. The tasks below harden **cross-instrument** time budgets and simulated binary uploads in advance of larger CDW arrays and acquisition workloads. Do not add `ArbShape`, `Option054`, `PulseArb`, `N6700`, or instrument trigger semantics to core.

### Source references (inspected)

| Component / current code | Concrete behavior | Implication |
| --- | --- | --- |
| [`scpi/binary_block.py`](../src/scpi_driver_core/scpi/binary_block.py): `read_definite_length_block` | Reads header, numeric length, payload, terminator with separate `transport.read(... timeout_s=timeout_s)` calls | Each stage can consume a full timeout; composite wall time is not guaranteed by the single timeout |
| [`scpi/client.py`](../src/scpi_driver_core/scpi/client.py): `query_binary_block` | Performs a write then multi-stage read, with independent timeout values; does invalidate stream on framing failure | Preserve invalidation, but share one monotonic deadline across write and reads |
| [`transport/visa.py`](../src/scpi_driver_core/transport/visa.py): `VisaTransport.write/read` | Repeated `resource.write_raw` and `resource.read_bytes` calls under one configured VISA timeout value | Per-stage/per-progress operations may extend elapsed time beyond nominal total; vendor/backend behavior needs contract tests |
| [`transport/tcp.py`](../src/scpi_driver_core/transport/tcp.py) | Uses `deadline=time.monotonic()+timeout` for read/write loops | Good reference for the invariant; still inspect composite transact |
| [`simulation/scripted.py`](../src/scpi_driver_core/simulation/scripted.py) | `write()` passes outbound bytes to `_split_program_message`; parser decodes as text and splits newline/semicolon | Cannot model **outbound** binary payload containing arbitrary `0x0A`, `0x3B`, quotes, non-text bytes |
| [`scpi/codec.py`](../src/scpi_driver_core/scpi/codec.py) | Text commands default `maximum_command_size=65536`; `encode_block_command` frames prefix + raw block | Large ASCII CDW needs explicit size policy; binary uploads already have a generic path |
| [`execution/polling.py`](../src/scpi_driver_core/execution/polling.py) | Monotonic loop bounds sleeps but not time spent inside a blocking predicate | Document use of a remaining-budget timeout in device status queries |
| [`docs/acceptance.md`](../docs/acceptance.md) | Hardware-free transport contracts green; representative physical migration proof not complete | New core claims remain software-verified until named HIL gate completes |

## 2. Priorities and implementation PRs

| PR | Priority | Work | Independent? | Required before |
| --- | --- | --- | --- | --- |
| **CORE-ARB-A** | P0 | Shared monotonic deadline for multi-stage block read/write/query and per-progress VISA I/O | Yes; can start alongside B | Strict composite timeout claims |
| **CORE-ARB-B** | P0 | Binary-block-aware outbound scripted simulation with length validation and error injection | Yes; can start alongside A | Reliable CDW/binary-upload unit tests |
| **CORE-ARB-C** | P1 | Clarify large numeric-array transfer policies, optionally add generic ASCII vector helper **only if useful to ≥2 concrete drivers** | After A/B APIs stabilize | Large CDW integration |
| **CORE-ARB-D** | P1 | Integration test against `keysight-n6700-driver` and release/migration evidence | After A and B merge | Consumer dependency upgrade |

**Do not merge failed CI or release-breaking behavior.** Every merged code PR increments the core version as required by repository policy; rebase on latest `main` and select the next available version, not a hardcoded future suffix.

## 3. CORE-ARB-A — strict shared monotonic I/O deadlines

### Problem statement

The binary-block helper's four-stage read loop passes the **same** timeout to each read. `ScpiClient.query_binary_block()` also sends a write before starting those reads. `VisaTransport.write()` loops on partial writes with the timeout freshly configured for each backend call. A nominal 5 s command can therefore last materially longer than 5 s under adversarial slow progress.

**Severity:** P0 for users who depend on true end-to-end deadlines; **not** a finding that current core loses bytes or that normal short Arbs are broken.

### Proposed implementation (illustrative Python 3.10-compatible code)

~~~python
# Possible private helper: src/scpi_driver_core/execution/deadline.py
from dataclasses import dataclass, field
import math
import time
from typing import Callable
from scpi_driver_core.exceptions import TransportTimeoutError

@dataclass
class _Deadline:
    ends_at: float
    clock: Callable[[], float] = field(default=time.monotonic, repr=False)

    @classmethod
    def begin(cls, timeout_s: float, clock=time.monotonic) -> "_Deadline":
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("timeout_s must be finite and positive")
        return cls(clock() + timeout_s, clock)

    def remaining_s(self) -> float:
        left = self.ends_at - self.clock()
        if left <= 0:
            raise TransportTimeoutError("SCPI transfer deadline exceeded")
        return left
~~~

Use **one** `_Deadline` for the entire `ScpiClient.query_binary_block` operation. After the write, pass `remaining_s()` to each header/length/payload/terminator read. For `VisaTransport.write/read`, use one deadline across all partial chunks; for composite `transact()`, do not reset the budget between write and read. `TcpTransport` already has per-direction deadlines; confirm composite behavior. Reuse a private helper or straightforward local deadline, not a breaking public API change.

**Pseudocode patch pattern** (not meant to be pasted directly into production):

~~~python
# Inside query_binary_block: one deadline for the complete operation.
def action(operation_id, effective):
    if effective is None:
        # Preserve current per-transport default timeout, but materialize
        # one configured finite deadline before multi-stage I/O.
        effective = resolve_transport_timeout()
    budget = _Deadline.begin(effective)
    with transport.operation_lock():
        transport.write(outbound,
                        timeout_s=budget.remaining_s(),
                        operation_id=operation_id)
        try:
            return read_definite_length_block(
                transport,
                timeout_s=budget.remaining_s(),
                remaining_timeout=budget.remaining_s,  # proposed private API
                maximum_size=limit,
                terminator=terminator,
                operation_id=operation_id,
            )
        except BaseException:
            transport.invalidate()
            raise
~~~

**Important implementation detail:** decide precisely how to resolve a client's `timeout_s=None` into the configured transport default without exposing backend internals. Prefer passing a deadline abstraction through the layer or adding a well-tested internal default-resolution contract. Never introduce an unbounded `None` path; honor existing faulting-on-uncertainty and caller exception types. A multi-call deadline must not be restarted after partial progress or when an instrument returns a short response.

**Acceptance tests to add:**
1. Fake monotonic clock + mocked header/length/payload/terminator: each consumes time; total elapsed cannot exceed the requested operation deadline beyond measurable scheduling overhead.
2. Fragmented VISA writes and exact-length reads, forced slow progress, no-progress, 1-byte fragments, status END and timeout.
3. Composite `transact()` write consumes 80% budget, read gets ≤20%; timeout faults stream.
4. Backend interruption or malformed block retains `TransportTimeoutError`/`ProtocolError`, invalidates stream and does not auto-retry.
5. Existing VISA, TCP, serial, mock and scripted transport contracts remain green, including operation lock ordering and tracing. Do not claim OS DNS resolution is preemptible.

### Required code/test touchpoints

`src/scpi_driver_core/scpi/binary_block.py`, `scpi/client.py`, `transport/visa.py`; test files `tests/unit/test_binary_block.py`, `tests/unit/test_scpi_client.py`, `tests/unit/test_visa_transport.py`, `tests/integration/test_timeout_watchdog.py`. Expand TCP/serial contracts if composite timeout semantics change.

## 4. CORE-ARB-B — simulate outbound IEEE-488.2 binary uploads faithfully

### Problem statement

`ScriptedScpiTransport` supports binary **replies**, but its `write` parser treats outbound bytes as SCPI text. A payload containing `b"\\n;"`, quotes, NUL or non-ASCII bytes may be split into fictitious commands. Real waveforms are raw bytes, not `str`; this leads to false confidence and can corrupt fixture expectations.

### Proposed generic API

~~~python
# DESIGN SKETCH; names may be changed in a reviewed public API.
transport.on_binary_write(
    "DATA:ARB",
    lambda prefix, payload: verify_payload_and_update_state(payload),
)
client.write_binary_block("DATA:ARB ", bytes(range(256)))
~~~

The parser must recognize an IEEE-488.2 definite-length header `#<digit-count><byte-count>` and consume exactly that number of **payload bytes** before examining the terminator. It must never inspect CR, LF, quotes or semicolons *inside* the payload. Preserve text-only `on()`, `on_regex()`, `history` and compound program-message behavior.

**Suggested public simulation record:**

~~~python
@dataclass(frozen=True)
class BinaryWriteRecord:
    prefix: str               # normalized SCPI header, no payload
    payload: bytes             # exact original binary bytes
    operation_id: str | None
~~~

Decide whether oversized payloads are rejected by the configured simulator maximum; expose a finite bound. Consider an independent `binary_history` to avoid decoding arbitrary bytes into text command history. **For a malformed outbound block, reject before invoking any handler.** In a transport-faithful simulation the instrument may have consumed partial bytes; mark the session `FAULTED` when framing cannot be reconciled.

**Minimum tests:**
- Exact round-trip of `bytes(range(256))` and `b";\\n\\r\\x00#\\xff"`; the handler receives one block, no spurious command.
- Empty payload `#10`, shortest and longest legal definite-length headers, mismatched/truncated declarations and excess/trailing bytes.
- Payload split across transport writes **if** simulator explicitly supports multi-write framing; otherwise document that the client sends a single framed message and test failure of fragmented writes (not silent acceptance).
- Outbound `write_binary_block` under VISA/TCP mock and tracing, verify no unintentional decoding/normalizing; scripted text handlers still pass.
- Fault injection halfway through a payload leaves transport faulted; next command must not consume residue.
- Tests explicitly reject `#0` indefinite blocks until/unless bounded handling is designed.

**Likely files:** `src/scpi_driver_core/simulation/scripted.py`, `tests/unit/test_scripted_simulation.py`, `tests/unit/test_scpi_client.py`, `tests/transport_contract/*` if required.

## 5. CORE-ARB-C — numeric vector support (conditional)

For the target Keysight driver, **511-point UDEF** and ordinary finite sequences already fit the text API in most cases. **65,535-point CDW** can exceed `ScpiTextCodec.maximum_command_size=65_536`; increasing that limit at construction time is possible **without core code changes**. Its current `encode_block_command` only checks the command prefix length and supports a large binary payload.

Options, in ascending scope:

1. **Preferred baseline:** let concrete drivers validate/serialize voltage/current vectors, construct `ScpiTextCodec(maximum_command_size=...)` explicitly for instrument-approved ASCII limits, and call the existing text write. Add no generic API.
2. **Optional reuse:** if multiple instrument drivers need the same helper, add a generic, **pure** `format_scpi_numeric_vector(values, maximum_values, maximum_bytes)` in `scpi/codec.py` or a separate module. Validate numeric finiteness and exact byte budget; no module-specific scale/units.
3. **Binary:** use existing `client.write_binary_block(prefix, payload)` **only when the specific instrument command documents a definite-length binary format**. Never automatically convert a Keysight CDW text list into an IEEE block.

**Illustrative helper only (not current core API):**

~~~python
import math

def format_scpi_numeric_vector(values, *, maximum_values: int,
                               maximum_bytes: int) -> str:
    if not 1 <= len(values) <= maximum_values:
        raise ValueError("invalid number of SCPI array points")
    clean = [float(value) for value in values]
    if not all(math.isfinite(v) for v in clean):
        raise ValueError("SCPI arrays require finite numbers")
    rendered = ",".join(format(v, ".12g") for v in clean)
    if len(rendered.encode("ascii")) > maximum_bytes:
        raise ValueError("array would exceed configured SCPI command budget")
    return rendered
~~~

That helper must not infer hardware sample rates, segment arrays across separate SCPI commands, select binary endian, or silently clip an out-of-range instrument setpoint. Add boundary/precision, max-bytes and injection tests if it is approved. **Do not block Arb shapes on CORE-ARB-C.**

## 6. CORE-ARB-D — downstream compatibility and integration

Current [N6700 driver `pyproject.toml`](https://github.com/ami3go/keysight-n6700-driver/blob/main/pyproject.toml) pins core to commit `ec19ab88906d8e6ac270b30d7615ce7e75dc6a08` (including the `[visa]` extra); this is **not** current core `main@d850f88`. A compatibility bump must be **explicit**, not a silent dev dependency rewrite.

1. Build the new core wheel/sdist; install with the existing N6700 driver in an isolated venv and run its simulator/SCPI integration, LIST/UDEF, electronic-load scope and acquisition regression suites. Compare pinned old vs proposed new.
2. Validate `ScpiClient.write_binary_block/query_binary_block`, transport locks, `ReplayPolicy.NEVER`, error translation, trace data size/redaction, and that failed binary transfers leave a faulted transport.
3. If compatible, open a separate **N6700 driver** dependency-update PR, change both `scpi-driver-core` dependency references to **one exact reviewed core commit**, increment driver version and record test evidence.
4. Core migration proof remains hardware-dependent: guarded VISA/TCP setup, small first binary block, larger CDW only when vendor documents format, recovery from unplug/network loss. No equipment use without site approval.

## 7. Explicit non-goals

- No Keysight waveform shape or module/Option 054 logic, `ARB:FUNC:SHAP` construction or model-specific trigger classification in core.
- No `OUTP ON`, `*RST`, `ABOR:TRAN`, E-stop, current/voltage limit or DUT safety policy.
- No automatic write retries, implicit clear/reset, background hardware monitor or privileged raw SCPI.
- No new public async API, indefinite-length SCPI block (`#0`) support, streaming API or transport abstraction rewrite merely for Arb.
- No claim that model-specific CDW supports binary data until the vendor guide and HIL confirm it.

## 8. Review and merge quality gates

Before each PR: re-fetch latest `main`, inspect existing relevant tests, document scope and contract, implement smallest backwards-compatible change, run an **independent code review** focusing on serialization, timeout arithmetic, byte fidelity, transport invalidation and exception safety. Fix all blockers **in the same PR** and rerun CI.

Required automation: Python 3.10–3.13 CI, Ruff/format, strict mypy, pytest unit, property tests, transport contracts, PyVISA-sim, socket integrations, bounded watchdog, wheel and sdist. Keep or improve ≥90% branch coverage. Add Hypothesis vectors for all byte values and malformed framing, and deterministic fake-clock tests for deadlines. CI stays entirely **hardware-free**. Separate physical HIL evidence before production claims.

Merge order: **A and B may run in parallel**; merge A then B (or reverse after rebasing), C only if justified by another concrete driver, then D. Synchronize release notes, `CHANGELOG.md`, documentation and version on **every** implementation PR. Do not merge red CI or revert existing safety invariants.

### Definition of done (core scope) — updated 2026-10-15

- [x] A: One monotonic I/O deadline and preserved compatibility: [PR #9](https://github.com/ami3go/scpi-driver-core/pull/9), merged `3d2c25c5e4e141749478f84631e8215d2984792d`, v0.1.0.dev9.
- [x] B: Byte-accurate outbound scripted binary blocks: [PR #8](https://github.com/ami3go/scpi-driver-core/pull/8), merged `52c879a8be201781bc52e5b077e042c581b10b6c`, v0.1.0.dev8.
- [x] C: Unnecessary generic numeric-vector API rejected after review; rationale in [compatibility report](../docs/n6700-core-compatibility.md).
- [x] D: N6700 simulator/SCPI protocol suite verified against hardened core and original pin, [8-job matrix](https://github.com/ami3go/scpi-driver-core/actions/runs/38715855209).
- [x] No Keysight-specific safety or Arb commands added in the core.
- [x] Version increments, changelog and CI evidence for runtime PRs and compatibility PR #10; [core quality run](https://github.com/ami3go/scpi-driver-core/actions/runs/38715855316).
- [x] No physical HIL qualification asserted or hardware operated.
- [ ] Physical instrument qualification, separately authorized downstream work.

See [CORE-ARB-D detailed software evidence](../docs/n6700-core-compatibility.md) and downstream [N6700 metadata repair PR #19](https://github.com/ami3go/keysight-n6700-driver/pull/19).

