# Connections

The library supports:

- Simulator sessions for CI and development
- VISA resources, including USB and TCP/IP INSTR resources
- Raw Ethernet SCPI sockets, normally on TCP port 5025

Connections are non-invasive by default: the library does not reset the mainframe or enable outputs merely by connecting.

See [Hardware connection and safety](guide/hardware_connection.md).
