# Contributing

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev,all]"
```

## Quality checks

Run before opening a pull request:

```bash
ruff check .
ruff format --check .
mypy src
pytest
python -m build
```

## Design rules

- Keep runtime code independent of Robot Framework, HardPy, and pytest.
- Keep the canonical transport boundary byte-oriented.
- Keep manufacturer- and model-specific semantics in concrete driver packages.
- Do not add automatic retries for potentially non-idempotent writes.
- Add tests with every behavior change.
- Prefer composition over deep inheritance.

See `task/SCPI_DRIVER_CORE_IMPLEMENTATION_TASK.md` for the full architecture and acceptance criteria.
