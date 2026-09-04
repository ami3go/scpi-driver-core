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
| `rf_tbs1000c` | USBTMC, binary blocks, waveform and setup transfer | 61 pass | 61 pass + 19 new |
| `rf_ngi_n83624` | TCP, UDP, RS232, emulator, multiple aliases | not started | |
| `rf_ea_ps9000t` | VISA, tolerant unit-suffixed parsing, device error queue | 105 pass | 105 pass + 21 new |

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

## rf_tbs1000c

`tbs1000c/transport.py` and the block/identity halves of `tbs1000c/codec.py`.
`driver.py`, `simulator.py`, `models.py` and `exceptions.py` are byte-for-byte
unchanged.

This is the byte-fidelity case. `CURVe?` returns sample bytes in which 0x0A and
0x20 are ordinary data, so the payload is read as one whole VISA message with
terminations disabled, and `encode_block_command` appends the command
terminator unconditionally — a block ending in 0x0A must not be mistaken for
one already terminated.

`build_ieee_block` and the binary branch of `parse_curve_response` now call the
core. The ASCII branch stays: handling both the binary and comma-separated
integer forms is this instrument's quirk.

19 new tests, several using a payload of all 256 byte values and one of nothing
but newlines. Mutation-checked, and this is the sharpest of the three: adding a
single `.strip()` to the core's block decoder makes the all-newlines waveform
test fail, which is exactly the silent corruption the design is meant to
prevent.

## rf_ea_ps9000t

`ea_ps9000t/transport.py`, plus the numeric and identity parsing in
`driver.py`. `simulator.py`, `models.py`, `enums.py` and `exceptions.py` are
byte-for-byte unchanged.

This is the driver that motivated `parse_optional_unit_float`. Its firmware
answers `SYSTem:NOMinal:VOLTage?` with `"500.0 V"` on real hardware while its
own programming guide and simulator show a bare number. Eighteen float getters
now route through the core.

`_parse_number` still returns the verbatim numeric token, because integer
getters call `int()` on it; reformatting through a float broke five tests when
first attempted, which is precisely the behaviour-preservation section 43
demands. The core-backed `_parse_float` is separate and additive.

Identity keeps this vendor's fifth user-text field. The core parses the
conventional four and its CSV-aware split means a quoted comma inside that
field is no longer mistaken for a separator.

### A negative result worth recording

The first mutation check here **passed when it should have failed**: breaking
the core's unit regex changed nothing, because `_parse_float` falls back to the
driver's historic token search and both yield 500.0 for `"500.0 V"`. The
fallback was masking whether the core did the work.

The fix was a test that disables the fallback and asserts the core alone parses
the documented replies. With it, the same mutation fails as it should. Worth
stating because a migration can look proven while proving nothing.

### Running it

```bash
pip install -e .                      # the core, from the repository root
pip install -e "migrations/rf_keysight_n6700[dev]"
cd migrations/rf_keysight_n6700 && pytest tests/unit
```
