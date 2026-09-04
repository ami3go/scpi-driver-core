from keysight_n6700.cli import main


def test_cli_idn_sim(capsys):
    assert main(["--sim", "idn"]) == 0
    assert "N6700B" in capsys.readouterr().out
