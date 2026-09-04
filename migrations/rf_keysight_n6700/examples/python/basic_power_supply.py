from keysight_n6700 import N6700

with N6700.connect_simulated() as inst:
    ch1 = inst.power_supply(1)
    ch1.set_voltage_setpoint(5.0)
    ch1.set_current_limit(1.0)
    try:
        # ENERGIZES DUT: explicit output enable line.
        ch1.output_on()
        print(ch1.measure())
    finally:
        ch1.output_off()
