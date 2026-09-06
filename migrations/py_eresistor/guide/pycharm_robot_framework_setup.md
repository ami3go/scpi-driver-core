# PyCharm and Robot Framework setup

1. Open the unpacked `rf_eresistor` folder as the PyCharm project.
2. Create a virtual environment using Python 3.10 or newer.
3. In PyCharm's terminal, activate that environment and run `python -m pip install -e ".[test,yaml]"`.
4. Install the **Robot Framework Language Server** or **Robot Framework Support** PyCharm plugin.
5. Configure the plugin/interpreter to use the same virtual environment.
6. Open an example and run it from the terminal with `python -m robot --outputdir results examples/01_identity.robot`.

For an existing `uv` environment:

```powershell
uv pip install -e ".[test,yaml]"
uv run robot --outputdir results examples\01_identity.robot
```

If Robot reports that a test file does not exist, verify the current directory with `Get-Location`, then use a path relative to it or the full file path. Import errors almost always mean PyCharm, Robot, and the terminal are using different Python interpreters; compare `python -c "import sys; print(sys.executable)"` and `robot --version`.

