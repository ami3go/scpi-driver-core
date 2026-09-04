"""Numeric SCPI response parsing.

Regression coverage for a real-hardware finding (RFDS-019 hardware conformance run):
this instrument's firmware appends a trailing unit suffix to some numeric query
responses (e.g. ``SYSTem:NOMinal:VOLTage?`` replying ``"500.0 V"``) even though the
bundled simulator and the programming guide's examples both show a bare number.
``_parse_number`` is what makes every numeric getter tolerate both forms.
"""

from __future__ import annotations

import pytest

from ea_ps9000t.driver import EaPs9000T, _parse_number
from ea_ps9000t.exceptions import EaPs9000TProtocolError


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ("500.0 V", "500.0"),
        ("500.0", "500.0"),
        ("3.500 A", "3.500"),
        ("1500.0 W", "1500.0"),
        ("  12  W  ", "12"),
        ("-0.5 V", "-0.5"),
        ("+2.5e1 V", "+2.5e1"),
        ("42", "42"),
    ],
)
def test_parse_number_tolerates_a_trailing_unit_suffix(response, expected):
    assert _parse_number(response) == expected


def test_parse_number_raises_a_typed_protocol_error_when_no_number_is_found():
    with pytest.raises(EaPs9000TProtocolError, match="could not parse a number"):
        _parse_number("no digits here")


def test_get_nominal_ratings_tolerates_unit_suffixed_responses():
    """Reproduces the exact real-hardware failure: SYSTem:NOMinal:VOLTage? replying
    "500.0 V" used to raise ValueError: could not convert string to float."""

    class FakeTransport:
        resource = "FAKE::INSTR"
        timeout_s = 5.0

        def __init__(self):
            self._open = True

        def is_open(self):
            return self._open

        def write(self, _command):
            pass

        def query(self, command):
            responses = {
                "SYSTem:LOCK:OWNer?": "REMOTE",
                "SYSTem:NOMinal:VOLTage?": "500.0 V",
                "SYSTem:NOMinal:CURRent?": "40.0 A",
                "SYSTem:NOMinal:POWer?": "5000.0 W",
            }
            return responses[command]

        def close(self):
            self._open = False

    driver = EaPs9000T(FakeTransport())
    ratings = driver.get_nominal_ratings()
    assert ratings.voltage == 500.0
    assert ratings.current == 40.0
    assert ratings.power == 5000.0
    driver.close()
