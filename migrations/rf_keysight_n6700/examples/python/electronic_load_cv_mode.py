from keysight_n6700 import N6700

with N6700.connect_simulated() as inst:
    load = inst.load(3)
    load.set_load_mode("cv")
    load.set_load_voltage(1.0)
    print(load.measure())
