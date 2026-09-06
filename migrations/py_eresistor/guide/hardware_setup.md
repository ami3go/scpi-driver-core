# Hardware setup

1. Power the E-Resistor and connect its W5500 Ethernet interface to the test network.
2. Confirm the configured address. Examples default to `192.168.0.55`; override `${ERESISTOR_HOST}` from the command line when needed.
3. Run `01_identity.robot` before connecting a DUT.
4. Run `03_mask_control.robot` while electrically verifying CH1 and the expected Q16/Q1 mapping.
5. Open all channels, connect the DUT, then use resistance or temperature examples.

Example override:

```bash
robot --variable ERESISTOR_HOST:192.168.7.50 examples/01_identity.robot
```

The board listens on SCPI port 5025 and normally uses HTTP port 80 for ping, identify, and calibration fallback. Avoid placing a DMM on all eight channels in parallel; leakage can disturb high-resistance measurements. Use a relay multiplexer so only one channel is connected to the DMM at a time.

