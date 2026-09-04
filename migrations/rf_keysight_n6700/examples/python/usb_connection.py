from keysight_n6700 import N6700

RESOURCE = "USB0::0x0957::...::INSTR"
with N6700.connect_usb(RESOURCE) as inst:
    print(inst.idn())
    print(inst.measure_all())
