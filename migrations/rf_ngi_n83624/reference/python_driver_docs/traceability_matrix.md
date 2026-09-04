# Requirements Traceability Matrix

| Requirement | Implementation | Tests | Docs |
|---|---|---|---|
| TCP/UDP/serial transport | `transports.py` | `test_transports.py` | API reference |
| Raw SCPI access | `N83624CellSimulator.write/query` | `test_driver_common.py` | API reference |
| 24-channel validation | `safety.validate_channel` | `test_validation.py` | API reference |
| Output off before mode/config | `N83624Channel.configure_*`, `set_mode` | `test_command_sequences.py` | Production safety |
| Mandatory output limits | `set_output` | `test_safety.py` | Production safety |
| UDP per-channel restriction | `UdpTransport.single_channel`, `channel()` | `test_transports.py` | Protocol verification |
| Compound-operation locking | `locked_operation()` usage | `test_command_sequences.py` | API reference |
| Fault simulation settle-to-zero | `set_fault_simulation` | `test_safety.py` | Production safety |
| SOC `file_number=None` behavior | `configure_soc` | `test_command_sequences.py` | API reference |
| `ONDWell` validation | `set_on_dwell_us` | `test_validation.py` | API reference |
| Dangerous setting confirmation | system setters, `factory_reset` | `test_safety.py` | Production safety |
| Protocol parsing | `parsing.py` | `test_parsing.py` | API reference |
