from keysight_n6700 import N6700

with N6700.connect_simulated() as inst:
    smu = inst.smu(2)
    smu.configure_current_priority(0.01, 2.0, output=False)
    try:
        # ENERGIZES DUT: explicit SMU output enable line.
        smu.output_on()
        print(smu.measure())
    finally:
        smu.output_off()
