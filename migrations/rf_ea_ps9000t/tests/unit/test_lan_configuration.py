"""LAN configuration round-trips (Gate 3 extension — SYSTem:COMMunicate:LAN:*).

Confirmed against the EA/Intepro "Programming Guide ModBus & SCPI" (Doc ID
PGMBEN, Rev. 17), pages 57-60. See ``ea_ps9000t.driver.EaPs9000T`` for why
SYSTem:COMMunicate:LAN:1SPEed/:2SPEed/:INDex are not implemented (Anybus/IF-AB
and 10000-series-dual-port-only, not applicable to the PST series this driver
targets).
"""

from __future__ import annotations

import pytest

from ea_ps9000t.driver import EaPs9000T
from ea_ps9000t.exceptions import EaPs9000TDeviceError, EaPs9000TValidationError


@pytest.fixture()
def driver():
    d = EaPs9000T.connect_simulated()
    yield d
    d.close()


def test_dhcp_round_trip(driver):
    assert driver.get_lan_dhcp_enabled() is False  # factory default OFF
    driver.set_lan_dhcp_enabled(True)
    assert driver.get_lan_dhcp_enabled() is True
    driver.set_lan_dhcp_enabled(False)
    assert driver.get_lan_dhcp_enabled() is False


def test_ip_address_round_trip(driver):
    driver.set_lan_ip_address("192.168.1.50")
    assert driver.get_lan_ip_address() == "192.168.1.50"


def test_subnet_mask_round_trip(driver):
    driver.set_lan_subnet_mask("255.255.255.0")
    assert driver.get_lan_subnet_mask() == "255.255.255.0"


def test_gateway_round_trip(driver):
    driver.set_lan_gateway("192.168.1.1")
    assert driver.get_lan_gateway() == "192.168.1.1"


def test_hostname_round_trip(driver):
    driver.set_lan_hostname("bench-3")
    assert driver.get_lan_hostname() == "bench-3"


def test_hostname_rejects_too_long_string(driver):
    with pytest.raises(EaPs9000TValidationError):
        driver.set_lan_hostname("x" * 55)


def test_domain_round_trip(driver):
    driver.set_lan_domain("lab.example.com")
    assert driver.get_lan_domain() == "lab.example.com"


def test_domain_rejects_too_long_string(driver):
    with pytest.raises(EaPs9000TValidationError):
        driver.set_lan_domain("x" * 55)


def test_dns_round_trip(driver):
    driver.set_lan_dns1("8.8.8.8")
    assert driver.get_lan_dns1() == "8.8.8.8"
    driver.set_lan_dns2("8.8.4.4")
    assert driver.get_lan_dns2() == "8.8.4.4"


def test_control_port_round_trip(driver):
    assert driver.get_lan_control_port() == 5025  # factory default
    driver.set_lan_control_port(6000)
    assert driver.get_lan_control_port() == 6000


def test_control_port_rejects_502_reserved_for_modbus(driver):
    with pytest.raises(EaPs9000TValidationError, match="502"):
        driver.set_lan_control_port(502)


def test_control_port_rejects_out_of_range(driver):
    with pytest.raises(EaPs9000TValidationError):
        driver.set_lan_control_port(-1)
    with pytest.raises(EaPs9000TValidationError):
        driver.set_lan_control_port(65536)


def test_keepalive_round_trip(driver):
    assert driver.get_lan_keepalive_enabled() is False  # factory default OFF
    driver.set_lan_keepalive_enabled(True)
    assert driver.get_lan_keepalive_enabled() is True


def test_timeout_round_trip(driver):
    assert driver.get_lan_timeout() == 5  # factory default
    driver.set_lan_timeout(0)
    assert driver.get_lan_timeout() == 0
    driver.set_lan_timeout(30)
    assert driver.get_lan_timeout() == 30


def test_timeout_validates_range(driver):
    """0 disables it; otherwise must be between 5 and 65535, per the documented range
    (same style as ``set_communication_timeout``)."""

    for bad in (1, 4, 65536, -1):
        with pytest.raises(EaPs9000TValidationError):
            driver.set_lan_timeout(bad)


def test_mac_address_is_read_only(driver):
    mac = driver.get_lan_mac_address()
    assert mac
    assert not hasattr(driver, "set_lan_mac_address")


def test_lan_write_while_not_remote_raises_typed_error(driver):
    """Every mutating LAN command is rejected the same way as any other mutating
    command on this instrument family when remote control is not held."""

    driver.release_remote_control()
    with pytest.raises(EaPs9000TDeviceError, match="Invalid while in local"):
        driver.set_lan_ip_address("10.0.0.5")
    with pytest.raises(EaPs9000TDeviceError, match="Invalid while in local"):
        driver.set_lan_control_port(6000)
    driver.acquire_remote_control()  # restore for fixture teardown


def test_lan_1speed_2speed_index_not_implemented(driver):
    """Deliberately not implemented: Anybus/IF-AB Ethernet-module speed selection
    and the 10000-series dual-port selector describe hardware the PST series this
    driver targets doesn't have."""

    assert not hasattr(driver, "set_lan_1speed")
    assert not hasattr(driver, "set_lan_2speed")
    assert not hasattr(driver, "set_lan_index")
