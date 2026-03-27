from __future__ import annotations

import pytest

from senzu.exceptions import SecretFetchError, SecretPushError
from senzu.gcp import (
    _get_secret_client,
    ensure_secret_exists,
    fetch_secret_latest,
    push_secret_version,
)


def test_get_secret_client(mocker):
    mock_client = mocker.MagicMock()
    mock_sm = mocker.MagicMock()
    mock_sm.SecretManagerServiceClient.return_value = mock_client
    # Patch sys.modules to avoid importing the native secretmanager lib
    mocker.patch.dict("sys.modules", {"google.cloud.secretmanager": mock_sm})
    result = _get_secret_client()
    assert result is mock_client


def test_fetch_secret_latest_returns_payload(mocker):
    client = mocker.MagicMock()
    client.access_secret_version.return_value.payload.data = b'{"KEY": "val"}'
    mocker.patch("senzu.gcp._get_secret_client", return_value=client)

    result = fetch_secret_latest("my-proj", "my-secret")

    assert result == b'{"KEY": "val"}'
    client.access_secret_version.assert_called_once_with(
        request={"name": "projects/my-proj/secrets/my-secret/versions/latest"}
    )


def test_fetch_secret_latest_wraps_errors(mocker):
    client = mocker.MagicMock()
    client.access_secret_version.side_effect = Exception("connection refused")
    mocker.patch("senzu.gcp._get_secret_client", return_value=client)

    with pytest.raises(SecretFetchError, match="my-secret"):
        fetch_secret_latest("my-proj", "my-secret")


def test_push_secret_version_calls_add(mocker):
    client = mocker.MagicMock()
    mocker.patch("senzu.gcp._get_secret_client", return_value=client)

    push_secret_version("my-proj", "my-secret", b"payload")

    client.add_secret_version.assert_called_once_with(
        request={
            "parent": "projects/my-proj/secrets/my-secret",
            "payload": {"data": b"payload"},
        }
    )


def test_push_secret_version_wraps_errors(mocker):
    client = mocker.MagicMock()
    client.add_secret_version.side_effect = Exception("boom")
    mocker.patch("senzu.gcp._get_secret_client", return_value=client)

    with pytest.raises(SecretPushError, match="my-secret"):
        push_secret_version("my-proj", "my-secret", b"payload")


def test_ensure_secret_exists_creates(mocker):
    client = mocker.MagicMock()
    mocker.patch("senzu.gcp._get_secret_client", return_value=client)

    ensure_secret_exists("my-proj", "my-secret")

    client.create_secret.assert_called_once_with(
        request={
            "parent": "projects/my-proj",
            "secret_id": "my-secret",
            "secret": {"replication": {"automatic": {}}},
        }
    )


def test_ensure_secret_exists_already_exists_is_ok(mocker):
    from google.api_core.exceptions import AlreadyExists

    client = mocker.MagicMock()
    client.create_secret.side_effect = AlreadyExists("already exists")
    mocker.patch("senzu.gcp._get_secret_client", return_value=client)

    ensure_secret_exists("my-proj", "my-secret")  # must not raise


def test_ensure_secret_exists_other_error_raises(mocker):
    client = mocker.MagicMock()
    client.create_secret.side_effect = Exception("iam permission denied")
    mocker.patch("senzu.gcp._get_secret_client", return_value=client)

    with pytest.raises(SecretPushError, match="my-secret"):
        ensure_secret_exists("my-proj", "my-secret")
