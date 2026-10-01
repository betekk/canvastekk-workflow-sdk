"""Single source of truth for the SDK version and release date (DA-3359).

Lives in a leaf module so non-package modules (the support-horizon gate, the
manifest stamp factory) can read the version without importing the package
root — ``__init__.py`` imports middleware at module top, so anything that
imported the version from the root risked a cycle.
"""

__version__ = "0.37.0"

#: Release date of this version (UTC) — the support-horizon sunset is
#: computed from this date (+ SUPPORT_HORIZON_DAYS).
RELEASE_DATE = "2026-10-01"
