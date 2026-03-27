from __future__ import annotations

import pytest

from senzu.config import SecretRef
from senzu.exceptions import ConfigParseError
from senzu.lock import LockEntry
from senzu.providers.aws import AwsProvider
from senzu.providers.factory import get_provider_for_lock_entry, get_provider_for_ref
from senzu.providers.gcp import GcpProvider


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
    assert isinstance(get_provider_for_ref(_ref("gcp", project="my-proj")), GcpProvider)


def test_returns_aws_provider_for_aws_ref():
    assert isinstance(get_provider_for_ref(_ref("aws", project=None, region="us-east-1")), AwsProvider)


def test_raises_for_unknown_provider():
    with pytest.raises(ConfigParseError, match="azure"):
        get_provider_for_ref(_ref("azure"))


# ---------------------------------------------------------------------------
# get_provider_for_lock_entry
# ---------------------------------------------------------------------------


def test_returns_gcp_provider_for_gcp_lock_entry():
    assert isinstance(get_provider_for_lock_entry(_entry("gcp", project="my-proj")), GcpProvider)


def test_returns_aws_provider_for_aws_lock_entry():
    assert isinstance(get_provider_for_lock_entry(_entry("aws", project=None, region="us-east-1")), AwsProvider)


def test_raises_for_unknown_provider_in_lock_entry():
    with pytest.raises(ConfigParseError):
        get_provider_for_lock_entry(_entry("vault"))
