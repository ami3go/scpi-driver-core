# Scripted binary uploads

`ScriptedScpiTransport` supports outbound IEEE-488.2 *definite-length*
binary blocks without decoding or splitting payload bytes.

```python
sim = ScriptedScpiTransport()
sim.on_binary_write("DATA:ARB", lambda command, payload: verify(payload))
sim.open()
ScpiClient(sim).write_binary_block("DATA:ARB ", bytes(range(256)))
assert sim.binary_history[0][1] == bytes(range(256))
```

`history` contains text commands only; `binary_history` returns copies of
(header, byte-preserved payload) tuples, bounded by `max_binary_history_bytes` (8 MiB by default, with a
256-entry cap). Oversized individual payloads go to the handler but are not
retained in history. Set the retention limit to zero to disable capture.
`clear_history()` clears both.

Handlers are looked up by the exact text preceding the block (for example
`"DATA:ARB 1,"`) and then by its header alone (`"DATA:ARB"`), so one
header registration covers every argument combination; the handler receives
the full preceding text. IEEE 488.2 non-decimal numerics such as `#H20`,
`#B1010` and `#Q17` are ordinary text, not blocks.

A binary handler may return any existing scripted reply type. The declared
payload length must fit `DEFAULT_MAXIMUM_BLOCK_SIZE`; malformed, truncated
and `#0` indefinite-length blocks are rejected. An interrupted binary write
invalidates the simulated connection; recovery must be explicit.

Simulation does not prove that any particular physical instrument supports
a given binary upload command or payload format.
