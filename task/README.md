# Implementation task documents

The task directory contains the architectural specification used to build
`scpi-driver-core`.

- `SCPI_DRIVER_CORE_IMPLEMENTATION_TASK.md` — original detailed architecture,
  phases, migration targets, and acceptance criteria.
- `TEST_HARNESS_ADDENDUM.md` — current testing/quality-gate requirements added
  after the hardware-free Hypothesis, PyVISA-sim, and pytest-timeout harness was
  implemented.

When the two documents differ on test execution or test-harness requirements,
`TEST_HARNESS_ADDENDUM.md` is authoritative. It does not change the core
architecture or the representative migration/HIL requirements of the original
task.

Operational testing guidance is maintained in `../docs/testing.md` and
`../tests/README.md`. AI/code agents should also follow `../AGENTS.md`.
