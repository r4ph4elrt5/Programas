import pytest

from multipost.platforms import Capability, PLATFORM_NAMES, registry


def test_five_destinations_do_not_claim_restricted_apis():
    connectors = registry()
    assert set(connectors) == set(PLATFORM_NAMES)
    assert connectors["youtube"].capability == Capability.AUTH_REQUIRED
    for key in ("instagram", "facebook", "tiktok", "kwai"):
        assert connectors[key].capability == Capability.ASSISTED_PUBLISH
        assert connectors[key].official_url.startswith("https://")
        with pytest.raises(NotImplementedError):
            connectors[key].publish()
    assert registry(True)["youtube"].capability == Capability.AUTO_PUBLISH
