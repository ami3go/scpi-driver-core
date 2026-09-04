"""Robot Framework library package for the Agilent (Keysight) 34411A.

``library.py`` is a thin adapter over the typed core driver in
:mod:`agilent34411a` — argument/result conversion and named-session (alias)
management only, no SCPI construction. Every public keyword is also wrapped
with RFDS-008 structured evidence recording; see ``evidence.py`` and
``docs/logging_and_evidence.md``.
"""

from .library import Agilent34411ALibrary

__version__ = "26.2"

__all__ = ["Agilent34411ALibrary", "__version__"]
