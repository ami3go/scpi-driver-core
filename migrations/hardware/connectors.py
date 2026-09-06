"""How to open a connection to each instrument, where that is a single call.

Kept separate from :mod:`sweep` because it is the part that varies per driver
and the part I could only partly verify. Each entry here was checked by
importing the module in that driver's own virtualenv and confirming the
attribute exists and is callable — but never by calling it, because calling it
opens a connection.

Three drivers have no entry. They are not built from a resource string: the
N83624 and the E-Resistor take a transport object, and the HP34401A is
constructed from a GPIB board and address. Guessing a constructor for those and
being wrong means connecting to something unintended, so they are left blank
and the operator supplies the instance. ``run_sweep`` takes an already-open
driver precisely so that stays possible.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

__all__ = ["CONNECTORS", "ConnectRecipe", "connect"]


@dataclass(frozen=True)
class ConnectRecipe:
    """One verified way to open a driver from a resource string."""

    module: str
    cls: str
    factory: str
    #: What the resource string looks like, for the error message and the docs.
    resource_example: str

    def open(self, resource: str) -> Any:
        """Import, resolve, and call the factory. Opens a real connection."""
        module = importlib.import_module(self.module)
        driver_class = getattr(module, self.cls)
        return getattr(driver_class, self.factory)(resource)


#: Verified to exist by import in each driver's virtualenv. Never called here.
CONNECTORS: dict[str, ConnectRecipe | None] = {
    "py_agilent33220a": ConnectRecipe(
        "py_agilent33220a.driver", "Agilent33220A", "connect_visa",
        "TCPIP0::192.168.0.10::inst0::INSTR",
    ),
    "py_agilent34411a": ConnectRecipe(
        "py_agilent34411a", "Agilent34411A", "connect_visa",
        "TCPIP0::192.168.0.11::inst0::INSTR",
    ),
    "py_ea_ps9000t": ConnectRecipe(
        "py_ea_ps9000t", "EaPs9000T", "connect_visa",
        "TCPIP0::192.168.0.12::inst0::INSTR",
    ),
    "py_keysight_n6700": ConnectRecipe(
        "py_keysight_n6700", "N6700", "connect_visa",
        "TCPIP0::192.168.0.13::inst0::INSTR",
    ),
    "py_tbs1000c": ConnectRecipe(
        "py_tbs1000c", "Tbs1000c", "connect_usbtmc",
        "USB0::0x0699::0x03C7::C000000::INSTR",
    ),
    # No single-call constructor. See the module docstring.
    "py_hp34401a": None,
    "py_ngi_n83624": None,
    "py_eresistor": None,
}


def connect(driver: str, resource: str) -> Any:
    """Open ``driver`` at ``resource``. Opens a real connection.

    Raises:
        LookupError: if this driver has no verified single-call constructor.
            That is not an oversight; supply the instance yourself.
    """
    recipe = CONNECTORS.get(driver)
    if recipe is None:
        raise LookupError(
            f"{driver} has no single-call constructor here; build the driver "
            f"yourself and pass the instance to run_sweep()"
        )
    return recipe.open(resource)
