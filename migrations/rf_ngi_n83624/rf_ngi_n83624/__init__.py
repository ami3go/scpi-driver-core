"""Robot Framework library package for NGI N83624."""

from .library import NGI_N83624, RELEASE_VERSION

#: Alias matching the ``rf_<device>.<Device>Library`` naming convention used
#: by the other drivers in this repository. ``NGI_N83624`` is kept as the
#: primary name for backward compatibility.
NGI_N83624Library = NGI_N83624

__version__ = RELEASE_VERSION

__all__ = ["NGI_N83624", "NGI_N83624Library", "RELEASE_VERSION"]
