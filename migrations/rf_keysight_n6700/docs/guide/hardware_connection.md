# Hardware Connection and Safety Guide

## Connection methods

### VISA TCP/IP

```robotframework
Connect To N6700 Via VISA    TCPIP0::192.168.1.50::inst0::INSTR    main
```

### Raw SCPI socket

```robotframework
Connect To N6700 Via Ethernet    192.168.1.50    5025    main
```

### USB VISA

Use the exact USB resource returned by the installed VISA implementation.

## Before enabling an output

1. Confirm mainframe and module identity.
2. Confirm channel number and module rating.
3. Disconnect or verify the DUT and load state.
4. Set a conservative current limit before enabling voltage.
5. Confirm polarity, wiring, grounding, and remote-sense configuration.
6. Keep a hardware-accessible emergency stop or output-disable path.
7. Start with a read-only discovery test.

Run the guarded read-only example first:

```bash
python -m robot --variable N6700_RESOURCE:<VISA_RESOURCE> examples/robot/10_real_hardware_readonly.robot
```

## Output-changing example

`11_real_hardware_output_test.robot` requires explicit variables and should only be used after the limits and fixture are reviewed.

## Software limitations

Automatic shutdown is best effort. It cannot guarantee a safe state when the process crashes, the network fails, the VISA stack blocks, the mainframe faults, or an external switching system is in an unsafe state. Use hardware limits and interlocks appropriate to the DUT energy level.
