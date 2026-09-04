import csv

from keysight_n6700 import N6700
from keysight_n6700.datalog import log_measurements_csv


def test_csv_logging(tmp_path):
    path = tmp_path / "log.csv"
    with N6700.connect_simulated() as inst:
        log_measurements_csv(inst, path, [1], 0.01, duration_s=0.01, append=False)
    rows = list(csv.DictReader(path.open()))
    assert rows
    assert "power_source" in rows[0]
