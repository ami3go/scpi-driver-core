# Examples

The repository includes fourteen Robot Framework examples under `examples/robot/` and eighteen Python driver examples under `examples/python/`.

## Run one Robot example

```bash
python -m robot --outputdir build/example-results examples/robot/01_simulator_smoke.robot
```

## Run all Robot examples

```bash
python -m robot --outputdir build/example-results examples/robot
```

Hardware examples skip unless explicit hardware variables are provided.

## Example categories

- Simulator smoke and identity
- Power supply configuration
- Measurement assertions
- Multi-channel operation
- Named instrument sessions
- SMU voltage- and current-priority modes
- Electronic-load constant-current mode
- Protection and SCPI errors
- Raw SCPI access
- Reusable Robot resource workflows
- Voltage polling
- Guarded real-hardware discovery and output testing
