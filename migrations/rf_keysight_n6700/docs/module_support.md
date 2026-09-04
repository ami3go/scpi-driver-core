# Module Support Matrix

| Model | Type | Status |
|---|---|---|
| N673x/N674x/N675x/N676x/N677x | Power supply | Implemented for core CV/CC APIs |
| N678xA | SMU | Implemented for voltage/current priority wrapper APIs |
| SIM_LOAD | Simulator-only electronic load | Implemented for no-hardware tests |
| Real electronic load models | Electronic load | Blocked until exact official command docs are added |

> **N6775A power measurement:** the module does not support direct `MEAS:POW?`. The library reads `MEAS:VOLT?` and `MEAS:CURR?`, calculates watts, and reports `power_source=calculated`.
