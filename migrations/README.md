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

## Naming

Upstream prefixes everything `rf_`, because that project is Robot Framework
first. Here the prefix says what a package *is*:

| Prefix | Example | What it is |
| --- | --- | --- |
| `py_` | `py_ngi_n83624/py_ngi_n83624/` | The pure-Python driver. Imports nothing from Robot Framework and is usable from plain Python, pytest, or any other runner. |
| `rf_` | `py_ngi_n83624/rf_ngi_n83624/` | The Robot Framework adapter: keyword library, listeners, evidence hooks. It `import robot` and is loaded by `.robot` files under exactly this name. |

Project directories take `py_` too, since what is vendored here is the Python
driver built on this core. `KeysightN6700Library` keeps its name for the same
reason `rf_*` does — it is a Robot Framework library, whatever its spelling.

This is the one place these snapshots deliberately diverge from upstream. It
touches the N6700's release governance, which derives its archive name from
the folder name, so `RELEASE_INFO.json` and the AI-contract lock were
regenerated to match. Upstream's own distribution names on PyPI
(`robotframework-agilent33220a`, `rf-ngi-n83624`) are left alone: they are
published identifiers, not paths.

## Status

| Driver | Validates | Baseline tests | After migration |
| --- | --- | --- | --- |
| `py_keysight_n6700` | VISA, raw TCP, multi-channel, strict error checking, protocol audit | 33 pass | 33 pass + 11 new |
| `py_agilent34411a` | VISA, large SCPI surface, measurement parsing, guards | 109 pass | 109 pass + 15 new |
| `py_tbs1000c` | USBTMC, binary blocks, waveform and setup transfer | 61 pass | 61 pass + 19 new |
| `py_ngi_n83624` | TCP, UDP, RS232, emulator, multiple aliases | 30 pass | 30 pass + 33 new |
| `py_ea_ps9000t` | VISA, tolerant unit-suffixed parsing, device error queue | 105 pass | 105 pass + 21 new |
| `py_agilent33220a` | VISA, function generator (secondary validation) | 101 pass | 101 pass + 15 new |
| `py_hp34401a` | VISA GPIB (secondary validation) | 169 pass, 2 skip | 190 pass, 2 skip |
| `py_eresistor` | SCPI/TCP path only (secondary validation) | 37 pass | 51 pass |
| `rf_bk8500b` | not migrated — see below | — | — |

## py_keysight_n6700

### What changed

`py_keysight_n6700/transport.py` and the generic half of `py_keysight_n6700/scpi.py`.
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

## py_agilent34411a

`py_agilent34411a/transport.py` replaced, plus the identity and reading-burst
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

## py_tbs1000c

`py_tbs1000c/transport.py` and the block/identity halves of `py_tbs1000c/codec.py`.
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

## py_ea_ps9000t

`py_ea_ps9000t/transport.py`, plus the numeric and identity parsing in
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

## py_agilent33220a

Secondary validation. `py_agilent33220a/transport.py` and the identity parsing in
`driver.py`; `simulator.py`, `models.py`, `enums.py` and `exceptions.py` are
byte-for-byte unchanged.

The same shape as the 34411A, which is the point: by this driver the migration
was mechanical, because the seam and the core API were already settled. That is
the compounding the first migration could not demonstrate.

## py_hp34401a

`py_hp34401a_dmm/visa_transport.py` only. This driver already had a
template-method `BaseTransport`, so the migration replaced the `_do_open`,
`_do_close`, `_send`, `_recv`, `_clear` and `_set_timeout` hooks and touched
nothing else.

`_send` no longer strips the write terminator back off and hope PyVISA
re-appends the same one: the core disables PyVISA's terminations, so the bytes
`BaseTransport` produced go out unaltered.

The GPIB address rules stay in the driver. Talk-only mode and primary-address
ranges are GPIB semantics, and the core has no business knowing them.

Note: this package depends on `rfds-core`, which is not published, so it cannot
be `pip install`-ed here. Its suite runs against the source tree with
`PYTHONPATH=.`, which is how the baseline was taken and how the result below
was measured.

21 migration-proof tests cover the VISA path and the GPIB address rules.
Mutation-checked against the core's VISA terminations.

A procedural note from doing that check: after restoring the mutated core file,
the test kept failing until `src/**/__pycache__` was cleared. Python was reusing
the mutated bytecode. A mutation check that does not clear it can report either
a false pass or a false failure.

## py_ngi_n83624

The only non-VISA migration, and section 42D's case. `py_ngi_n83624/transports.py`
is the sole changed file: three hand-rolled backends — TCP, UDP and RS232 —
replaced by the core's. Every direct use of `socket` and `serial` is gone.

The device-specific parts stayed, and there are more of them here than
elsewhere: the UDP port scheme where 7001..7024 map to channels 1..24, the TCP
port range check, and the RS232 baudrate whitelist. None of that belongs in a
generic core.

### What the migration found in the core

The core faults a TCP transport when a read times out, on the grounds that an
unterminated stream leaves session validity uncertain. That is defensible, but
it means data buffered before the timeout becomes unreachable: a driver cannot
catch the timeout and then read what already arrived.

This driver relied on exactly that. Its original `query` returned whatever had
been received if the terminator never came, and only raised when nothing at
all had arrived. Preserving that behaviour meant restructuring the read to
accumulate incrementally rather than asking for a terminated message in one
call — which is what the original socket loop did anyway.

Worth recording as a real consequence of the fault-on-timeout rule, found by a
driver rather than by the core's own tests.

22 new tests cover all three transports against a loopback TCP server, a real
UDP socket, and a faked pyserial backend. Mutation-checked against the core's
UDP datagram read.

### The same rule bites the completion wait

The fault-on-timeout rule has a second consequence here, found later. This
instrument can spend minutes on a command, and `wait_operation_complete`
polled `*OPC?` in a tight loop. The first poll a busy instrument declined to
answer timed out, faulted the transport, and every later poll then failed
against a dead link — the loop spun until its deadline and left the session
unusable.

Waiting with one long read instead is not the fix; it is the same bug with a
bigger constant. The wait now treats an unanswered poll as "not finished yet"
and reopens the transport before the next one, which is what makes the stale
reply harmless: a new stream or a new UDP local port drops it rather than
returning it as the answer to the next query. The interval backs off, and the
method still reports a timeout by returning `False`.

The core got the general version of this: `Ieee4882.wait_for_completion` arms
`*OPC` and polls `*ESR?`, which a busy instrument answers immediately, so no
read is ever left open long enough to fault. That is the better pattern, and
the one to use on any instrument that documents `*ESR?`. This one does not —
`*CLS` and `*ESR?` are absent from its programming guide and stay gated behind
`experimental_ok` — so it polls `*OPC?` and handles the fallout.

11 further tests cover the wait on an injected clock.

## py_eresistor

`py_eresistor_driver/scpi.py` only, and only the SCPI/TCP path. Section 3 of the
task document is explicit that the HTTP fallback stays device-specific, so
`http_api.py` is untouched.

The byte-at-a-time `recv(1)` loop is gone, replaced by one bounded read that
also enforces `max_response_bytes` rather than checking it per byte. The
driver keeps everything above that: its connection-state machine, its reconnect
backoff, its multi-line framing, and its `ERR,<code>,"<message>"` error format,
which is this instrument's own and not the conventional SCPI shape.

The greeting read needed care. An instrument that sends no banner is the normal
case, so a timeout there must not break the connection — but the core faults a
TCP transport on read timeout. The greeting is therefore read with a short bound
and a faulted transport is reopened, which keeps a silent instrument connecting
cleanly.

## rf_bk8500b — deliberately not migrated

Section 42 lists this driver's SCPI-facing path as secondary validation, and
section 3 admits it as a "secondary/hybrid reference" with one condition: any
legacy or binary protocol path must remain outside the core, and the SCPI
abstraction must not be distorted to accommodate non-SCPI protocols.

Two findings make migration the wrong call here.

**Its VISA transport does not exist.** `bk8500b/transport/visa.py` is a
fifteen-line stub whose constructor raises `ConfigurationError`. It is exported
but never constructed. There is no VISA path to migrate, so this driver is not
one of the VISA drivers in any case.

**Its SCPI and legacy protocols share one transport.** `CommandExecutor` holds a
single `transport`, and both `protocol/scpi.py` and `protocol/legacy.py` read
from it directly — the former with `read_until`, the latter byte-by-byte for the
binary codec. Migrating that transport would put the legacy binary path on the
core, which is precisely what section 3 rules out.

Separating the two would mean giving each protocol its own transport, which is a
feature rewrite rather than an architecture extraction, and section 43 forbids
exactly that during a migration.

So this is recorded as a reasoned exclusion rather than an omission. Migrating
it would require first splitting the transports in the source project, as a
deliberate change with its own review.

## Phase 16 — what the migrations revealed about the core

Section 16 asks for a review of duplication remaining across migrated drivers,
extracting only what several implementations prove reusable. With eight drivers
there is finally evidence to review.

### A missing primitive, found by four drivers

`ScpiClient` had no way to change its timeout, so four drivers independently
rebuilt the whole client in their timeout setter. That is not merely verbose:
rebuilding silently discarded the error-queue policy, the retry observer, and
the operation-id sequence, so a driver that had enabled strict error checking
lost it, and traces stopped correlating at `op-1` again. Demonstrated by
measurement, not assumption:

```
before rebuild: error checking on = True  | observer wired = True  | next op id = op-3
after  rebuild: error checking on = False | observer wired = False | next op id = op-1
```

`ScpiClient.set_timeout()` was added to the core and all four drivers now use
it. Section 32 already named `set_communication_timeout` as an expected
service, so this closed a real gap rather than inventing one.

### What was deliberately not extracted

The text adapter presenting `write(str)`/`query(str)` over `ScpiClient` recurs
in every driver, but each translates into its own exception hierarchy and its
own tolerance for padding. A shared base class would have to be parameterised
by all of that, which is the deep-inheritance shape section 31 warns against.
Left alone.

The fake VISA backend is duplicated across six migration test files, about 280
lines. That is real duplication, but it is test scaffolding for drivers rather
than core behaviour, and publishing it would make it API the core has to keep
stable. Recorded here as a candidate, not acted on.

## Automatic API conformance

`driver_api_conformance.py` walks each driver's whole public surface instead of
enumerating it by hand, because these drivers are large — the 34411A has 147
public members — and a migration that quietly broke one method would not be
caught by tests written per feature.

Per driver it checks four things:

| Check | Behaviour |
| --- | --- |
| Surface snapshot | a rename or removal fails; additions prompt a deliberate refresh |
| Annotations | recorded as a ratchet: existing gaps tolerated, new ones fail |
| Docstrings | same ratchet, marked `[undocumented]` in the snapshot |
| Invocation sweep | every no-argument method is called against the simulator |

| Driver | Public members | Methods swept |
| --- | --- | --- |
| `py_agilent34411a` | 147 | 72 |
| `py_agilent33220a` | 116 | 62 |
| `py_ea_ps9000t` | 87 | 47 |
| `py_tbs1000c` | 58 | 18 |
| `py_keysight_n6700` | 48 | 17 |
| `py_hp34401a` | 50 | 26 |

The sweep is the check that earns its keep, and it is deliberately bounded.
Only the driver's own simulator or fake transport is ever driven, and lifecycle
methods that would tear the session down or reach for hardware are excluded by
name. **This must never be pointed at an instrument**: a harness that blindly
invokes every method on live hardware would happily enable an output.

Mutation-checked rather than assumed. Renaming a public method fails the
snapshot test; making one raise a non-driver error fails both the sweep and the
per-method test that names it.

The ratchets were built because these drivers carried real debt: 445
undocumented public members across the six with snapshots. That debt has since
been paid — see below — so every snapshot now records zero. The ratchets stay,
because their job now is to keep it that way.

Not covered: `py_ngi_n83624` and `py_eresistor`. Neither has a simulated
constructor the harness can call without bespoke setup — the N83624 driver
builds around an emulator transport and the E-Resistor client opens a socket in
its constructor. Both are reachable with more work; neither is done.

## Docstrings

All eight drivers are now fully documented: 1385 docstrings added,
`[undocumented]` count zero in every API snapshot.

They were generated by `scripts/add_docstrings.py`, which derives each one from
the method's own body rather than inventing prose. The SCPI command a method
sends is the most useful fact about it and cannot be wrong, because it is read
from the source:

```python
def get_frequency(self) -> float:
    """Return the frequency.

    Sends ``FREQuency?``.
    """
    return float(self._query("FREQuency?"))
```

Methods that already had a docstring were never touched, and the rewrite is
applied by line insertion, so no other formatting, comment, or line of code
changed. Where the rules could not phrase something better than restating its
own name, the generator adds nothing: 170 members were deliberately skipped on
that basis before the remaining names were given explicit phrasing, because a
docstring reading `"""Timeout s."""` is worse than none.

Two bugs the pilot caught before the rollout, which is why it was a pilot:
inserting into a `Protocol` stub whose body shares the signature's line
produced invalid syntax, and an all-caps test for SCPI headers wrongly rejected
short/long forms like `OUTPut` and `FREQuency`, silently dropping the command
from most setter docstrings.

Each driver also gained `docs/scpi-driver-core.md`, recording what moved to the
core, what stayed, and the instrument-specific reason. The existing driver
documentation was left alone rather than rewritten: 88 files whose contents
have not been verified here.

### Running it

```bash
pip install -e .                      # the core, from the repository root
pip install -e "migrations/py_keysight_n6700[dev]"
cd migrations/py_keysight_n6700 && pytest tests/unit
```
