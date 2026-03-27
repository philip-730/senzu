from __future__ import annotations

import sys

import pytest

from senzu.exceptions import ProviderNotInstalledError, SecretFetchError, SecretPushError, SenzuError
from senzu.providers.aws import AwsProvider


def _provider_with_mock_client(mocker, client_mock=None):
    """Return an AwsProvider whose boto3 client is replaced with a MagicMock."""
    provider = AwsProvider("us-east-1")
    if client_mock is None:
        client_mock = mocker.MagicMock()
    mocker.patch.object(provider, "_get_client", return_value=client_mock)
    return provider, client_mock


# ---------------------------------------------------------------------------
# fetch_latest
# ---------------------------------------------------------------------------


def test_fetch_latest_returns_string_as_bytes(mocker):
    provider, client = _provider_with_mock_client(mocker)
    client.get_secret_value.return_value = {"SecretString": '{"DB": "pg://..."}'}

    result = provider.fetch_latest("myapp/env")

    assert result == b'{"DB": "pg://..."}'
    client.get_secret_value.assert_called_once_with(SecretId="myapp/env")


def test_fetch_latest_returns_binary(mocker):
    provider, client = _provider_with_mock_client(mocker)
    client.get_secret_value.return_value = {"SecretBinary": b"\x00\x01\x02"}

    result = provider.fetch_latest("myapp/bin")

    assert result == b"\x00\x01\x02"


def test_fetch_latest_prefers_binary_over_string(mocker):
    provider, client = _provider_with_mock_client(mocker)
    client.get_secret_value.return_value = {
        "SecretBinary": b"binary-wins",
        "SecretString": "string-loses",
    }

    result = provider.fetch_latest("myapp/secret")

    assert result == b"binary-wins"


def test_fetch_latest_wraps_exception_as_secret_fetch_error(mocker):
    provider, client = _provider_with_mock_client(mocker)
    client.get_secret_value.side_effect = Exception("connection refused")

    with pytest.raises(SecretFetchError, match="myapp/env"):
        provider.fetch_latest("myapp/env")


def test_fetch_latest_error_includes_region(mocker):
    provider, client = _provider_with_mock_client(mocker)
    client.get_secret_value.side_effect = Exception("boom")

    with pytest.raises(SecretFetchError, match="us-east-1"):
        provider.fetch_latest("myapp/env")


# ---------------------------------------------------------------------------
# push_version
# ---------------------------------------------------------------------------


def test_push_version_calls_put_secret_value(mocker):
    provider, client = _provider_with_mock_client(mocker)

    provider.push_version("myapp/env", b'{"DB": "pg://new"}')

    client.put_secret_value.assert_called_once_with(
        SecretId="myapp/env",
        SecretString='{"DB": "pg://new"}',
    )


def test_push_version_wraps_exception_as_secret_push_error(mocker):
    provider, client = _provider_with_mock_client(mocker)
    client.put_secret_value.side_effect = Exception("access denied")

    with pytest.raises(SecretPushError, match="myapp/env"):
        provider.push_version("myapp/env", b"payload")


# ---------------------------------------------------------------------------
# ensure_exists
# ---------------------------------------------------------------------------


def test_ensure_exists_creates_secret(mocker):
    provider, client = _provider_with_mock_client(mocker)

    provider.ensure_exists("myapp/env")

    client.create_secret.assert_called_once_with(Name="myapp/env", SecretString="")


def test_ensure_exists_is_idempotent_on_resource_exists(mocker):
    import botocore.exceptions

    provider, client = _provider_with_mock_client(mocker)
    error_response = {"Error": {"Code": "ResourceExistsException", "Message": "already exists"}}
    client.create_secret.side_effect = botocore.exceptions.ClientError(error_response, "CreateSecret")

    # Should not raise
    provider.ensure_exists("myapp/env")


def test_ensure_exists_wraps_other_errors_as_secret_push_error(mocker):
    import botocore.exceptions

    provider, client = _provider_with_mock_client(mocker)
    error_response = {"Error": {"Code": "AccessDeniedException", "Message": "not allowed"}}
    client.create_secret.side_effect = botocore.exceptions.ClientError(error_response, "CreateSecret")

    with pytest.raises(SecretPushError, match="myapp/env"):
        provider.ensure_exists("myapp/env")


# ---------------------------------------------------------------------------
# ProviderNotInstalledError
# ---------------------------------------------------------------------------


def test_raises_provider_not_installed_when_boto3_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "boto3", None)

    provider = AwsProvider("us-east-1")
    provider._client = None  # ensure no cached client

    with pytest.raises(ProviderNotInstalledError, match="pip install senzu\\[aws\\]"):
        provider._get_client()


def test_provider_not_installed_error_is_senzu_error():
    assert issubclass(ProviderNotInstalledError, SenzuError)
