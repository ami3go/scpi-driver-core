"""Robot Framework library package for the Agilent (Keysight) 33220A.

``library.py`` is the Robot Framework adapter (keeps SCPI construction in the
core ``agilent33220a`` package, only converts arguments/results and manages
named sessions). ``evidence.py`` is the RFDS-008 structured logging/
diagnostics layer described in ``docs/logging_and_evidence.md`` — every
keyword call and every SCPI command/response is recorded there.
"""

from .library import Agilent33220ALibrary

__version__ = "26.2"

__all__ = ["Agilent33220ALibrary", "__version__"]
