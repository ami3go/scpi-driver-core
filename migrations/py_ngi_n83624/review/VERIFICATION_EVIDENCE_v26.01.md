# Verification Evidence — v26.01

**Execution date:** 2026-07-18  
**Environment:** Linux container, Python 3.13, Robot Framework 7.4.2

| Verification | Command class | Result |
|---|---|---|
| Python unit tests | `python -m pytest -q` | 8 passed |
| Robot acceptance | `robot tests/robot/acceptance.robot` | 5 passed |
| Offline executable examples | selected emulator suites | 11 passed |
| All examples syntax/keyword dry run | `robot --dryrun examples` | 14 passed |
| Ruff | `python -m ruff check .` | passed |
| Wheel | `python -m build` | built |
| Source distribution | `python -m build` | built |
| Libdoc | `python -m robot.libdoc ...` | generated |
| Fresh wheel install | new virtual environment | passed |
| Wheel-based Robot smoke | separate working directory | 1 passed |

## Built artifacts

- `dist/rf_ngi_n83624-26.1-py3-none-any.whl`
- `dist/rf_ngi_n83624-26.1.tar.gz`
- `docs/keyword-reference.html`

## Not executed

- Real N83624 communication.
- Physical output verification.
- Fault-injection against real network/serial links.
- Hardware soak/endurance.

These remain controlled by `guide/HARDWARE_QUALIFICATION.md`.
