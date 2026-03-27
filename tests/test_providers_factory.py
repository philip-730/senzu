from __future__ import annotations

import pytest

from senzu.config import EnvConfig, SecretRef
from senzu.exceptions import ConfigParseError
from senzu.lock import LockEntry
from senzu.providers.aws import AwsProvider
from senzu.providers.factory import _cache, get_provider_for_lock_entry, get_provider_for_ref
from senzu.providers.gcp import GcpProvider


@pytest.fixture(autouse=True)
def clear_cache():
    _cache.clear()
    yield
    _cache.clear()


def _ref(provider="gcp", project="my-proj", region=None):
    return SecretRef(
        secret="app-env",
        project=project or "",
        provider=provider,
        region=region,
    )


def _entry(provider="gcp", project="my-proj", region=None):
    return LockEntry(
        secret="app-env",
        project=project or "",
        provider=provider,
        region=region,
    )


# ---------------------------------------------------------------------------
# get_provider_for_ref
# ---------------------------------------------------------------------------


def test_returns_gcp_provider_for_gcp_ref():
    provider = get_provider_for_ref(_ref("gcp", project="my-proj"))
    assert isinstance(provider, GcpProvider)


def test_returns_aws_provider_for_aws_ref():
    provider = get_provider_for_ref(_ref("aws", project=None, region="us-east-1"))
    assert isinstance(provider, AwsProvider)


def test_raises_for_unknown_provider():
    with pytest.raises(ConfigParseError, match="azure"):
        get_provider_for_ref(_ref("azure"))


# ---------------------------------------------------------------------------
# get_provider_for_lock_entry
# ---------------------------------------------------------------------------


def test_returns_gcp_provider_for_gcp_lock_entry():
    provider = get_provider_for_lock_entry(_entry("gcp", project="my-proj"))
    assert isinstance(provider, GcpProvider)


def test_returns_aws_provider_for_aws_lock_entry():
    provider = get_provider_for_lock_entry(_entry("aws", project=None, region="us-east-1"))
    assert isinstance(provider, AwsProvider)


def test_raises_for_unknown_provider_in_lock_entry():
    with pytest.raises(ConfigParseError):
        get_provider_for_lock_entry(_entry("vault"))


# ---------------------------------------------------------------------------
# caching
# ---------------------------------------------------------------------------


def test_same_gcp_project_returns_same_instance():
    p1 = get_provider_for_ref(_ref("gcp", project="proj-a"))
    p2 = get_provider_for_ref(_ref("gcp", project="proj-a"))
    assert p1 is p2


def test_different_gcp_projects_return_different_instances():
    p1 = get_provider_for_ref(_ref("gcp", project="proj-a"))
    p2 = get_provider_for_ref(_ref("gcp", project="proj-b"))
    assert p1 is not p2


def test_same_aws_region_returns_same_instance():
    p1 = get_provider_for_ref(_ref("aws", project=None, region="us-east-1"))
    p2 = get_provider_for_ref(_ref("aws", project=None, region="us-east-1"))
    assert p1 is p2


def test_different_aws_regions_return_different_instances():
    p1 = get_provider_for_ref(_ref("aws", project=None, region="us-east-1"))
    p2 = get_provider_for_ref(_ref("aws", project=None, region="eu-west-1"))
    assert p1 is not p2
