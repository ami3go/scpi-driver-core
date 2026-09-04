from keysight_n6700 import N6700

with N6700.connect_simulated() as inst:
    load = inst.load(3)
    load.configure_cc(0.1, input_on=False)
    try:
        # ENERGIZES LOAD INPUT: explicit input enable line.
        load.input_on()
        print(load.measure())
    finally:
        load.input_off()
