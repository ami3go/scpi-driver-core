"""Robot Framework library for Keysight/Agilent N6700 modular power systems.

This package re-exports :class:`KeysightN6700Library` so that Robot Framework
can resolve the canonical ``Library    rf_keysight_n6700.KeysightN6700Library``
import, matching the ``rf_<device>.<Device>Library`` convention used by the
other drivers in this repository. The legacy bare
``Library    KeysightN6700Library`` import keeps working unchanged.
"""

from KeysightN6700Library.library import KeysightN6700Library
from KeysightN6700Library.version import __version__

__all__ = ["KeysightN6700Library", "__version__"]
