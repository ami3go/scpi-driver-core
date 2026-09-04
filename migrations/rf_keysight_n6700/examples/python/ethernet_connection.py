from keysight_n6700 import N6700

HOST = "192.168.0.100"
with N6700.connect_ethernet(HOST) as inst:
    print(inst.idn())
    print(inst.discover_modules())
