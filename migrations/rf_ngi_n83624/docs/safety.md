# Safety Model

The Robot library enforces an additional output gate above the inherited Python driver.

1. Configure finite `max_voltage_v` and `max_current_ma` limits.
2. Configure the required mode and values with output disabled.
3. Arm the channel using exact confirmation text `ENABLE OUTPUT`.
4. Enable output.
5. Disable output and close the session in suite teardown.

Changing per-channel limits clears that channel's armed state. Reconnect also clears all armed states.

Safe shutdown attempts all 24 channels even when one shutdown command fails, then reports an aggregated error. This improves the probability of reaching a safe state but cannot prove the physical output state after communication loss.

Raw SCPI is separately guarded because it bypasses the typed validation and arming model.
