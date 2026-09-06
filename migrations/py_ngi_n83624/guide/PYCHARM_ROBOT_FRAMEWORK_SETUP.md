# PyCharm and Robot Framework Setup

## 1. Prerequisites

- Python 3.10–3.13.
- PyCharm Community or Professional.
- Git, when using a cloned repository.
- For RS232: a visible Windows COM port or Linux serial device.
- For real hardware: network/serial access to the N83624 and an approved bench safety plan.

## 2. Open the project

1. Extract `rf_ngi_n83624_v26.01.zip`.
2. Confirm the path ends in `rf_ngi_n83624/` and contains `pyproject.toml`.
3. In PyCharm, select **File → Open** and choose that folder.

## 3. Create the virtual environment

### Windows PowerShell

```powershell
.\scripts\setup_venv.ps1
```

### Windows Command Prompt

```bat
scripts\setup_venv.bat
```

### Linux/macOS

```bash
./scripts/setup_venv.sh
```

Manual equivalent:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,docs]"
```

## 4. Configure the PyCharm interpreter

1. Open **Settings → Project → Python Interpreter**.
2. Select **Add Interpreter → Add Local Interpreter**.
3. Choose **Existing environment**.
4. Windows interpreter: `.venv\Scripts\python.exe`.
5. Linux/macOS interpreter: `.venv/bin/python`.
6. Apply and wait for indexing.

## 5. Robot Framework editor support

Install one actively maintained Robot Framework language plugin from the PyCharm Marketplace. Plugin names and availability change; verify compatibility with your PyCharm release. The driver itself does not require a specific IDE plugin.

After installation:

1. Associate `*.robot` with Robot Framework files if not automatic.
2. Ensure the plugin uses the project `.venv` interpreter.
3. Confirm it resolves `rf_ngi_n83624.NGI_N83624Library`.

## 6. Create a Robot run configuration

1. Open **Run → Edit Configurations**.
2. Add a **Python** configuration when no dedicated Robot configuration exists.
3. Module name: `robot`.
4. Parameters:

```text
--outputdir build/pycharm examples/01_emulator_smoke.robot
```

5. Working directory: project root.
6. Interpreter: project `.venv`.

A dedicated Robot plugin may provide a native Robot configuration; use the same arguments and working directory.

## 7. Verify the offline environment

Run:

```powershell
.\scripts\run_tests.ps1
```

Expected gates:

- Python tests pass.
- Robot acceptance suite passes.
- Ruff passes.
- Wheel and source distribution build.

Run one example:

```powershell
.\scripts\run_example.ps1 .\examples\01_emulator_smoke.robot
```

## 8. Start a new suite

```robot
*** Settings ***
Library           rf_ngi_n83624.NGI_N83624Library    auto_close_on_suite_end=${False}
Suite Setup       Open N83624 Emulator    dev
Suite Teardown    Close All N83624 Connections

*** Test Cases ***
Identify
    ${idn}=    Identify N83624
    Log    ${idn}
```

Keep explicit suite teardown even though automatic library cleanup is available. Explicit teardown is easier to review and makes the safety intent visible.

## 9. Real instrument configuration

Replace emulator setup only after offline tests pass:

```robot
Suite Setup    Open N83624 TCP Connection
...    bench
...    host=192.168.0.123
...    port=7000
...    max_voltage_v=5.0
...    max_current_ma=500
...    audit_log_path=${OUTPUT DIR}${/}ngi_audit.jsonl
```

Do not copy example limits blindly. Enter limits verified for the exact instrument, fixture, cable, DUT, and channel.

## 10. Troubleshooting

### Library import fails

```powershell
.\.venv\Scripts\python.exe -c "from rf_ngi_n83624 import NGI_N83624; print('OK')"
```

If this fails, reinstall:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,docs]"
```

### `robot` command is not found

Use the venv executable directly:

```powershell
.\.venv\Scripts\robot.exe --version
```

### PowerShell blocks scripts

Run the BAT script or use a process-local policy only when permitted by your organization:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

### Serial port access denied on Linux

Add the user to the appropriate serial-device group for the distribution, then sign out/in. Confirm permissions with `ls -l /dev/ttyUSB* /dev/ttyACM*`.

### Output cannot be enabled

Confirm:

1. Finite voltage and current limits are configured.
2. The channel was armed with exact text `ENABLE OUTPUT`.
3. Configuration values are inside limits.
4. Connection was not recovered or limits changed after arming.
