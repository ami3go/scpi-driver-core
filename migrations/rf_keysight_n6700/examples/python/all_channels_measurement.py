from keysight_n6700 import N6700

with N6700.connect_simulated() as inst:
    for ch, meas in inst.measure_all().items():
        print(ch, meas)
