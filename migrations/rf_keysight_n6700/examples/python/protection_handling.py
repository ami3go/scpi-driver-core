from keysight_n6700 import N6700

with N6700.connect_simulated() as inst:
    print(inst.clear_protection(1))
