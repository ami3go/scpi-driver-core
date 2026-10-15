# Shared I/O deadlines (CORE-ARB-A)

A single monotonic duration now covers the full sequence of blocking steps
in `read_definite_length_block` and `ScpiClient.query_binary_block`.

Core VISA, TCP, UDP, serial, mock and scripted composite write/read transactions
pass the *remaining* duration into each transport stage. VISA and serial
partial-write loops also progressively reduce the backend timeout.

The configured `timeout_s` is measured **after acquiring** the operation lock:
it bounds one in-flight operation, not time spent waiting for other threads.
A timeout or uncertain partial transfer faults the stream. No command is
automatically retried. Backend blocking calls must honor their requested
timeouts; Python cannot preempt faulty vendor APIs or synchronous DNS lookups.

When the caller supplies no timeout, core transports expose their finite
`default_timeout_s`; tracing wrappers forward this resolution through their
`inner` transport. Unrecognized third-party transports without this optional
attribute retain the legacy behavior. Their callers should provide an explicit
timeout for strict composite guarantees.

Hardware-free tests cover fake clocks and fragmented software transfers;
vendor-specific VISA/serial backend guarantees still require HIL evaluation.
