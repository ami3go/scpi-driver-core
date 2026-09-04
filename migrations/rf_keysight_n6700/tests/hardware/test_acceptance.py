import os

import pytest

from keysight_n6700 import N6700

pytestmark = pytest.mark.hardware


def test_hardware_readonly_acceptance():
    resource = os.getenv("N6700_RESOURCE")
    if not resource:
        pytest.skip("N6700_RESOURCE not set")
    with N6700.connect_visa(resource, discover=True) as inst:
        assert inst.idn().model
        assert inst.channel_count() >= 1
        inst.discover_modules()
