"""Robot Framework library for the OpenBench E-Resistor."""

from .library import EResistorLibrary

class rf_eresistor(EResistorLibrary):
    """Compatibility entry point allowing ``Library    rf_eresistor``."""


__all__ = ["EResistorLibrary", "rf_eresistor"]
__version__ = "26.03"
