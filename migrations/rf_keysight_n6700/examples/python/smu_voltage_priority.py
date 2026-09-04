from keysight_n6700 import N6700

with N6700.connect_simulated() as inst:
    smu = inst.smu(2)
    smu.configure_voltage_priority(1.8, 0.1, output=False)
    try:
        # ENERGIZES DUT: explicit SMU output enable line.
        smu.output_on()
        print(smu.measure())
    finally:
        smu.output_off()
