# Phase 15 — representative driver migrations

Migration evidence for the architecture, per sections 42 and 43 of
`task/SCPI_DRIVER_CORE_IMPLEMENTATION_TASK.md`.

Source: `ami3go/RobotFrameworks_hw_drivers`, branch `dev`, commit
`a5388c5bc08da24bd981fdc5571dde43b2589890` — the exact baseline the task
document names.

Each driver is vendored here as a verbatim snapshot at that commit, with only
its infrastructure replaced. The snapshot includes the source project's own
governance files — `RELEASE_INFO.json`, `SHA256SUMS.txt`, `history/`, and its
`.github/` workflows. Those describe that project's release, not this
repository's; they are kept only so the driver's own packaging tests run
unmodified, and GitHub reads workflows only from the repository root.

Per section 43 a migration is an architecture extraction, not a feature
rewrite: public behavior, SCPI command mappings, safety policy, and error
semantics are preserved, and the driver's own test suite is the acceptance
test.

Two of the driver's packaging tests resolve paths relative to the working
directory, so its suite must be run from inside its own directory, as the
command at the end of this file does.

## Status

| Driver | Validates | Baseline tests | After migration |
| --- | --- | --- | --- |
| `rf_keysight_n6700` | VISA, raw TCP, multi-channel, strict error checking, protocol audit | 33 pass | 33 pass + 11 new |
| `rf_agilent34411a` | VISA, large SCPI surface, measurement parsing, guards | 109 pass | 109 pass + 15 new |
| `rf_tbs1000c` | USBTMC, binary blocks, waveform and setup transfer | not started | |
| `rf_ngi_n83624` | TCP, UDP, RS232, emulator, multiple aliases | not started | |
| `rf_ea_ps9000t` | VISA, tolerant unit-suffixed parsing, device error queue | not started | |

## rf_keysight_n6700

### What changed

`keysight_n6700/transport.py` and the generic half of `keysight_n6700/scpi.py`.
Nothing else. `driver.py`, `channel.py`, `modules.py`, `capabilities.py`,
`datalog.py`, `simulator.py`, `types.py` and `cli.py` are byte-for-byte
unchanged, verified by `diff`.

The whole 5,500-line driver reaches its transport through exactly three calls
— `transport.write`, `transport.query`, `transport.close` — which is why the
seam is this clean.

Replaced by the core:

| Was | Now |
| --- | --- |
| hand-rolled `PyVisaTransport` | `VisaTransport` + `ScpiClient` |
| hand-rolled `RawSocketTransport` | `TcpTransport` + `ScpiClient` |
| `parse_idn` | `parse_identity` + this driver's manufacturer policy |
| `parse_error` | `parse_scpi_error` |
| `parse_ieee488_definite_block` | `decode_definite_length_block` |
| `parse_csv_floats` / `parse_csv_strings` | `parse_csv` + `parse_float` |

Kept as device-specific, correctly: the `(@1:4)` channel-list grammar, the
manufacturer whitelist, `split_ieee488_blocks` (the N6700's comma-separated
multi-block framing), and the REAL32/REAL64 datalog unpacking.

### Defects the migration removed

- **VISA terminations were left on.** The old transport set
  `read_termination="\n"` on the PyVISA resource, so PyVISA could trim payload
  bytes out of a binary block. The core disables both terminations and lets the
  codec own framing.
- **The raw-socket read was unbounded.** `read_raw` looped `recv` until a
  newline with no maximum size, so a chatty or malfunctioning instrument could
  grow the buffer without limit. Core reads are bounded by construction.
- **`query()` opened the connection in `__init__`** and had no state model, so
  a failed connection and a closed one were indistinguishable.

### What did not shrink

Code lines are roughly flat: `transport.py` 162 → 159, `scpi.py` 164 → 160,
excluding docstrings. That is worth stating plainly rather than dressing up.

Two reasons. Section 43 requires preserving the driver's `write(str)`/
`query(str)` interface, so an adapter layer has to exist; it is transitional
and a later deliberate API change could delete it. And `SimulatedTransport`,
about 60 lines, stays as-is because it models N6700 behavior — device
semantics, not infrastructure.

The gain is not line count in one driver. It is that every direct use of
`socket`, `recv`, `sendall`, `pyvisa` and `ResourceManager` is gone (7
occurrences → 0), replaced by delegation to a layer that is tested to 96% and
already bounded, byte-faithful, and deterministic about close. That logic was
duplicated across the fleet; it now exists once. The saving multiplies with the
second driver, not the first.

### Evidence

- The driver's 33 pre-existing tests pass unchanged.
- 11 new tests in `tests/unit/test_core_migration.py` drive a real `N6700`
  over the real adapter over the real core transport, against a fake VISA
  backend and a loopback TCP server. The pre-existing tests all used the
  simulator, so they proved nothing about the two transports that were actually
  replaced.
- Mutation-checked: reverting the core's VISA terminations to `"\n"` makes
  `test_visa_terminations_are_left_to_the_codec` fail, and restoring it makes
  the suite pass. The driver's tests genuinely exercise the core rather than
  merely importing it.
- No vendor identifier appears anywhere under `src/scpi_driver_core/`, checked
  by grep. The core learned nothing about Keysight to make this work.

## rf_agilent34411a

`agilent34411a/transport.py` replaced, plus the identity and reading-burst
parsing in `driver.py`. `simulator.py`, `models.py`, `enums.py`, `exceptions.py`
and `__init__.py` are byte-for-byte unchanged.

This driver already separated `open()` from construction, so the seam was
cleaner than the N6700's. Its `PyvisaTransport` no longer imports pyvisa at all:
the core owns the session, and the module-level rule that "protocol code never
touches pyvisa outside this module" now holds one level more strongly.

Identity parsing keeps this driver's historic tolerance for partial `*IDN?`
replies — missing fields become empty strings rather than raising — because its
callers depend on that. The core parses; the fallback is the driver's.

15 new tests in `tests/unit/test_core_migration.py` drive a real
`Agilent34411A` over the real transport over the core, against a fake VISA
backend. Mutation-checked: removing the core's second-to-millisecond timeout
conversion makes one fail.

### Running it

```bash
pip install -e .                      # the core, from the repository root
pip install -e "migrations/rf_keysight_n6700[dev]"
cd migrations/rf_keysight_n6700 && pytest tests/unit
```
