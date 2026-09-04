"""GPIB/LAN interface configuration commands (Gate 3): plain pass-through
config, including the read-only queries.
"""

from __future__ import annotations

import pytest

from agilent33220a.driver import Agilent33220A
from rf_agilent33220a.library import Agilent33220ALibrary


@pytest.fixture()
def driver():
    d = Agilent33220A.connect_simulated()
    yield d
    d.close()


def test_gpib_address_round_trip(driver):
    driver.set_gpib_address(12)
    assert driver.get_gpib_address() == 12


def test_lan_auto_ip_round_trip(driver):
    assert driver.get_lan_auto_ip() is True  # factory default per the manual: ON
    driver.set_lan_auto_ip(False)
    assert driver.get_lan_auto_ip() is False
    driver.set_lan_auto_ip(True)
    assert driver.get_lan_auto_ip() is True


def test_lan_ip_address_round_trip(driver):
    driver.set_lan_ip_address("192.168.1.50")
    assert driver.get_lan_ip_address() == "192.168.1.50"


def test_lan_logical_ip_address_is_read_only(driver):
    address = driver.get_lan_logical_ip_address()
    assert address
    assert not hasattr(driver, "set_lan_logical_ip_address")


def test_lan_mac_address_is_read_only(driver):
    mac = driver.get_lan_mac_address()
    assert mac
    assert not hasattr(driver, "set_lan_mac_address")


def test_lan_media_sense_round_trip(driver):
    """SYSTem:COMMunicate:LAN:MEDiasense — LAN link-loss detection/auto-restart,
    not mDNS despite the mnemonic; factory default per the manual is ON."""

    assert driver.get_lan_media_sense_enabled() is True
    driver.set_lan_media_sense_enabled(False)
    assert driver.get_lan_media_sense_enabled() is False


def test_lan_netbios_round_trip(driver):
    assert driver.get_lan_netbios_enabled() is True
    driver.set_lan_netbios_enabled(False)
    assert driver.get_lan_netbios_enabled() is False


def test_lan_telnet_prompt_round_trip(driver):
    driver.set_lan_telnet_prompt("MYPROMPT>")
    assert driver.get_lan_telnet_prompt() == "MYPROMPT>"


def test_lan_telnet_welcome_message_round_trip(driver):
    driver.set_lan_telnet_welcome_message("Hello from the bench")
    assert driver.get_lan_telnet_welcome_message() == "Hello from the bench"


# ------------------------------------------------------------------
# Robot library wiring
# ------------------------------------------------------------------
def test_library_gpib_lan_keywords_round_trip():
    lib = Agilent33220ALibrary()
    lib.connect(alias="gen1", simulated=True)

    lib.set_gpib_address(15, alias="gen1")
    assert lib.get_gpib_address(alias="gen1") == 15

    lib.set_lan_auto_ip(False, alias="gen1")
    assert lib.get_lan_auto_ip(alias="gen1") is False

    lib.set_lan_ip_address("10.0.0.5", alias="gen1")
    assert lib.get_lan_ip_address(alias="gen1") == "10.0.0.5"

    assert lib.get_lan_logical_ip_address(alias="gen1")
    assert lib.get_lan_mac_address(alias="gen1")

    lib.set_lan_media_sense_enabled(False, alias="gen1")
    assert lib.get_lan_media_sense_enabled(alias="gen1") is False

    lib.set_lan_netbios_enabled(False, alias="gen1")
    assert lib.get_lan_netbios_enabled(alias="gen1") is False

    lib.set_lan_telnet_prompt("PROMPT>", alias="gen1")
    assert lib.get_lan_telnet_prompt(alias="gen1") == "PROMPT>"

    lib.set_lan_telnet_welcome_message("Hi", alias="gen1")
    assert lib.get_lan_telnet_welcome_message(alias="gen1") == "Hi"

    lib.disconnect("gen1")
