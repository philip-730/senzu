from __future__ import annotations

import pytest

from senzu.exceptions import SecretFetchError, SecretPushError
from senzu.providers.gcp import GcpProvider


def _provider(mocker, project: str = "my-project") -> tuple[GcpProvider, object]:
    """Return a GcpProvider with a mocked Secret Manager client."""
    provider = GcpProvider(project)
    mock_client = mocker.MagicMock()
    mocker.patch.object(provider, "_client", return_value=mock_client)
    return provider, mock_client


# ---------------------------------------------------------------------------
# fetch_latest
# ---------------------------------------------------------------------------


def test_fetch_latest_calls_correct_resource_name(mocker):
    provider, client = _provider(mocker)
    client.access_secret_version.return_value.payload.data = b'{"KEY": "val"}'

    result = provider.fetch_latest("my-secret")

    assert result == b'{"KEY": "val"}'
    client.access_secret_version.assert_called_once_with(
        request={"name": "projects/my-project/secrets/my-secret/versions/latest"}
    )


def test_fetch_latest_wraps_exception_as_secret_fetch_error(mocker):
    provider, client = _provider(mocker)
    client.access_secret_version.side_effect = Exception("permission denied")

    with pytest.raises(SecretFetchError, match="my-secret"):
        provider.fetch_latest("my-secret")


def test_fetch_latest_error_includes_project(mocker):
    provider, client = _provider(mocker, project="my-project")
    client.access_secret_version.side_effect = Exception("boom")

    with pytest.raises(SecretFetchError, match="my-project"):
        provider.fetch_latest("my-secret")


# ---------------------------------------------------------------------------
# push_version
# ---------------------------------------------------------------------------


def test_push_version_calls_add_secret_version(mocker):
    provider, client = _provider(mocker)

    provider.push_version("my-secret", b'{"KEY": "new"}')

    client.add_secret_version.assert_called_once_with(
        request={
            "parent": "projects/my-project/secrets/my-secret",
            "payload": {"data": b'{"KEY": "new"}'},
        }
    )


def test_push_version_wraps_exception_as_secret_push_error(mocker):
    provider, client = _provider(mocker)
    client.add_secret_version.side_effect = Exception("quota exceeded")

    with pytest.raises(SecretPushError, match="my-secret"):
        provider.push_version("my-secret", b"payload")


# ---------------------------------------------------------------------------
# ensure_exists
# ---------------------------------------------------------------------------


def test_ensure_exists_creates_secret_with_automatic_replication(mocker):
    provider, client = _provider(mocker)

    provider.ensure_exists("my-secret")

    client.create_secret.assert_called_once_with(
        request={
            "parent": "projects/my-project",
            "secret_id": "my-secret",
            "secret": {"replication": {"automatic": {}}},
        }
    )


def test_ensure_exists_is_idempotent_on_already_exists(mocker):
    from google.api_core.exceptions import AlreadyExists  # type: ignore

    provider, client = _provider(mocker)
    client.create_secret.side_effect = AlreadyExists("already exists")

    # Should not raise
    provider.ensure_exists("my-secret")


def test_ensure_exists_wraps_other_errors_as_secret_push_error(mocker):
    provider, client = _provider(mocker)
    client.create_secret.side_effect = Exception("network error")

    with pytest.raises(SecretPushError, match="my-secret"):
        provider.ensure_exists("my-secret")
