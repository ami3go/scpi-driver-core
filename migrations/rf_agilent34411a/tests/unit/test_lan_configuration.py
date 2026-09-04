"""LAN configuration round-trips (Gate 3 extension —
SYSTem:COMMunicate:LAN:* subsystem).
"""

from __future__ import annotations

import pytest

from agilent34411a.driver import Agilent34411A
from agilent34411a.exceptions import Agilent34411AValidationError


@pytest.fixture()
def driver():
    d = Agilent34411A.connect_simulated()
    yield d
    d.close()


def test_dhcp_round_trip(driver):
    assert driver.get_lan_dhcp_enabled() is True  # simulator factory default
    driver.set_lan_dhcp_enabled(False)
    assert driver.get_lan_dhcp_enabled() is False
    driver.set_lan_dhcp_enabled(True)
    assert driver.get_lan_dhcp_enabled() is True


def test_ip_address_round_trip(driver):
    driver.set_lan_ip_address("10.0.0.5")
    assert driver.get_lan_ip_address() == "10.0.0.5"


def test_ip_address_accepts_current_and_static_selectors(driver):
    driver.set_lan_ip_address("10.0.0.5")
    assert driver.get_lan_ip_address("current") == "10.0.0.5"
    assert driver.get_lan_ip_address("STATIC") == "10.0.0.5"


def test_ip_address_rejects_unknown_selector(driver):
    with pytest.raises(Agilent34411AValidationError, match="selector"):
        driver.get_lan_ip_address("bogus")


def test_subnet_mask_round_trip(driver):
    driver.set_lan_subnet_mask("255.255.0.0")
    assert driver.get_lan_subnet_mask() == "255.255.0.0"


def test_gateway_round_trip(driver):
    driver.set_lan_gateway("10.0.0.1")
    assert driver.get_lan_gateway() == "10.0.0.1"


def test_dns_round_trip(driver):
    driver.set_lan_dns("8.8.8.8")
    assert driver.get_lan_dns() == "8.8.8.8"


def test_hostname_round_trip(driver):
    driver.set_lan_hostname("bench-3-dmm")
    assert driver.get_lan_hostname() == "bench-3-dmm"


def test_domain_round_trip(driver):
    driver.set_lan_domain("lab.example.com")
    assert driver.get_lan_domain() == "lab.example.com"


def test_auto_ip_round_trip(driver):
    assert driver.get_lan_auto_ip() is True  # simulator factory default
    driver.set_lan_auto_ip(False)
    assert driver.get_lan_auto_ip() is False


def test_ddns_round_trip(driver):
    assert driver.get_lan_ddns_enabled() is True  # simulator factory default
    driver.set_lan_ddns_enabled(False)
    assert driver.get_lan_ddns_enabled() is False


def test_keepalive_round_trip(driver):
    assert driver.get_lan_keepalive() == pytest.approx(3600.0)  # simulator factory default
    driver.set_lan_keepalive(120.0)
    assert driver.get_lan_keepalive() == pytest.approx(120.0)


def test_logical_ip_address_is_read_only(driver):
    driver.set_lan_ip_address("10.0.0.5")
    assert driver.get_lan_logical_ip_address() == "10.0.0.5"
    assert not hasattr(driver, "set_lan_logical_ip_address")


def test_mac_address_is_read_only(driver):
    mac = driver.get_lan_mac_address()
    assert mac
    assert not hasattr(driver, "set_lan_mac_address")


def test_connection_status_queries_are_read_only(driver):
    assert driver.get_lan_connection_status()
    assert driver.get_lan_control_connection_status()
    assert not hasattr(driver, "set_lan_connection_status")


def test_mdns_round_trip(driver):
    assert driver.get_lan_mdns_enabled() is True  # simulator factory default
    driver.set_lan_mdns_enabled(False)
    assert driver.get_lan_mdns_enabled() is False


def test_netbios_round_trip(driver):
    assert driver.get_lan_netbios_enabled() is True  # simulator factory default
    driver.set_lan_netbios_enabled(False)
    assert driver.get_lan_netbios_enabled() is False


def test_telnet_prompt_round_trip(driver):
    driver.set_lan_telnet_prompt("SCPI2>")
    assert driver.get_lan_telnet_prompt() == "SCPI2>"


def test_telnet_welcome_message_round_trip(driver):
    driver.set_lan_telnet_welcome_message("Welcome to bench 3")
    assert driver.get_lan_telnet_welcome_message() == "Welcome to bench 3"


def test_lan_history_round_trip(driver):
    assert driver.get_lan_history() == ""
    driver.clear_lan_history()
    assert driver.get_lan_history() == ""


# ------------------------------------------------------------------
# Robot library wiring
# ------------------------------------------------------------------
def test_library_lan_keywords_go_through_the_session():
    from rf_agilent34411a.library import Agilent34411ALibrary

    lib = Agilent34411ALibrary()
    lib.connect(alias="dmm1", simulated=True)
    lib.set_lan_hostname("bench-3-dmm", alias="dmm1")
    assert lib.get_lan_hostname(alias="dmm1") == "bench-3-dmm"
    lib.set_lan_dhcp_enabled(False, alias="dmm1")
    assert lib.get_lan_dhcp_enabled(alias="dmm1") is False
    assert lib.get_lan_mac_address(alias="dmm1")
    lib.disconnect("dmm1")
