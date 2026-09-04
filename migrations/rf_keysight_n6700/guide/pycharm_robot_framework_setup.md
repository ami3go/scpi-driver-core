# PyCharm and Robot Framework Setup

## 1. Open the repository

Open the unpacked `rf_keysight_n6700/` folder as a PyCharm project. Do not open the parent download directory.

## 2. Create the project environment

Preferred command from the PyCharm terminal on Windows:

```bat
scripts\setup_venv.bat
```

Or create it manually:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev,docs]"
```

Python 3.10–3.13 is supported.

## 3. Select the interpreter

In PyCharm:

1. Open **File > Settings > Project > Python Interpreter**.
2. Choose **Add Interpreter > Add Local Interpreter**.
3. Select **Existing environment**.
4. Select `.venv\Scripts\python.exe` on Windows or `.venv/bin/python` on Linux/macOS.
5. Apply the change.

Verify that `robotframework`, `pyvisa`, `pytest`, `ruff`, and `mypy` appear in the interpreter package list.

## 4. Install Robot Framework language support

Install a current Robot Framework language-server plugin from PyCharm's **Settings > Plugins > Marketplace**. After installation, restart PyCharm and confirm that `.robot` files have syntax highlighting, keyword completion, and navigation.

Plugin availability and names can change; use an actively maintained plugin compatible with the installed PyCharm version and Robot Framework language server.

## 5. Configure source roots

The project intentionally has no `src/` folder. Keep the repository root on the Python path. PyCharm normally does this automatically when the repository root is opened as the project.

Do not mark only `KeysightN6700Library/` as the project root, because the Robot adapter imports the sibling `keysight_n6700/` package.

## 6. Configure a Robot run target

Create a Python run configuration:

- **Module name:** `robot`
- **Parameters:** `--outputdir build/robot-results examples/robot/01_simulator_smoke.robot`
- **Working directory:** repository root
- **Interpreter:** project `.venv`

For the complete simulator-compatible example set:

```text
--outputdir build/example-results examples/robot
```

The two hardware examples skip automatically when hardware variables are not supplied.

## 7. Configure tests and quality checks

Use the supplied scripts:

```bat
scripts\run_tests.bat
```

Or run commands in the PyCharm terminal:

```powershell
python -m pytest -m "not hardware"
python -m robot --outputdir build/robot-results tests/robot
python -m ruff check .
python -m mypy keysight_n6700 KeysightN6700Library
```

## 8. Configure real hardware variables

Do not hard-code bench addresses in committed Robot files. Pass variables from the command line or a local variable file excluded from Git.

VISA example:

```powershell
python -m robot `
  --variable N6700_RESOURCE:TCPIP0::192.168.1.50::inst0::INSTR `
  examples/robot/10_real_hardware_readonly.robot
```

Before running an output-changing test, define reviewed voltage/current limits and verify the connected load and fixture.

## 9. View keyword documentation

Open `docs/KeysightN6700Library.html` in a browser. Regenerate it after keyword changes:

```powershell
python -m robot.libdoc KeysightN6700Library docs/KeysightN6700Library.html
```

## 10. Common problems

### Library import is red in PyCharm

Confirm the selected interpreter is `.venv`, the repository was installed with `pip install -e .`, and the working directory is the repository root.

### `No keyword with name ... found`

Regenerate Libdoc, restart the Robot language server, and confirm the suite imports `KeysightN6700Library` with the exact capitalization.

### VISA resource is not found

Check the resource with the vendor VISA utility or:

```powershell
python -c "import pyvisa; print(pyvisa.ResourceManager().list_resources())"
```

### PowerShell blocks activation

Run the BAT script from Command Prompt, or allow local scripts according to your organization's PowerShell policy. Do not weaken execution policy globally without approval.
