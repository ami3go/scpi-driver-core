# Installation Guide

## Requirements

- Python 3.10 through 3.13
- Windows 11, Linux, or macOS
- Robot Framework 7.x or 8.x
- PyVISA for real hardware
- A vendor VISA implementation or optional `pyvisa-py`

## Recommended repository installation

### Windows

```bat
scripts\setup_venv.bat
```

The script creates `.venv`, upgrades packaging tools, and installs the repository in editable mode with development and documentation dependencies.

Activate manually later with:

```bat
.venv\Scripts\activate.bat
```

PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

### Linux/macOS

```bash
./scripts/setup_venv.sh
source .venv/bin/activate
```

## Runtime-only installation

```bash
python -m pip install .
```

Install the optional pure-Python VISA backend when no vendor VISA runtime is available:

```bash
python -m pip install ".[visa-py]"
```

## Install the included wheel

```bash
python -m pip install dist/robotframework_keysight_n6700-26.9.0-py3-none-any.whl
```

## Verify installation

```bash
python -c "from KeysightN6700Library import KeysightN6700Library; print('Library import OK')"
python -m robot --version
```

Run the simulator example:

```bash
python -m robot examples/robot/01_simulator_smoke.robot
```
