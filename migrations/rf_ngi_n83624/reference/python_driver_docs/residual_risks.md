# Residual Risks

Even with the safety features in this package, these risks remain:

1. **Incorrect external limits**: The driver relies on user-provided model and bench limits.
2. **Hardware failure**: Relay weld, output stage fault, cable short, or DUT failure cannot be prevented by software alone.
3. **Communication ambiguity**: After communication loss, the real instrument output state may be unknown.
4. **Manual ambiguity**: Some SCPI commands are interpreted from an inconsistent programming guide and must be hardware-verified.
5. **UDP unreliability**: UDP may lose packets; use TCP for critical control where possible.
6. **Capacitive DUT energy**: Voltage may remain after output is disabled; configure fault simulation thresholds and timeouts carefully.
7. **Concurrent external controllers**: If another program or front-panel operator changes state, software assumptions may be invalid. Use HMI disconnect and bench procedures where appropriate.
