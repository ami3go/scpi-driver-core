from keysight_n6700 import N6700
from keysight_n6700.datalog import log_measurements_csv

with N6700.connect_simulated() as inst:
    log_measurements_csv(inst, "n6700_measurements.csv", [1, 2, 3, 4], interval_s=1.0, duration_s=1.0, append=False)
