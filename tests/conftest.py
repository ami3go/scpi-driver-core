from __future__ import annotations

import os

from hypothesis import settings

# Hypothesis deadlines are disabled because pytest-timeout is the suite-level
# watchdog. This avoids treating a slow CI runner as a property-test failure.
settings.register_profile("dev", max_examples=100, deadline=None)
settings.register_profile(
    "ci",
    max_examples=200,
    deadline=None,
    derandomize=True,
    database=None,
)
settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "dev"))
