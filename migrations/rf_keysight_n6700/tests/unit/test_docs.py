from pathlib import Path


def test_scpi_command_map_exists():
    assert Path("docs/scpi_command_map.md").exists()
    text = Path("docs/scpi_command_map.md").read_text(encoding="utf-8")
    assert "ElectronicLoadChannel" in text
    assert "SIM_LOAD" in text
