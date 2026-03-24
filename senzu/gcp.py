from __future__ import annotations

from .exceptions import SecretFetchError, SecretPushError


def _get_secret_client():
    from google.cloud import secretmanager  # type: ignore

    return secretmanager.SecretManagerServiceClient()


def fetch_secret_latest(project: str, secret_name: str) -> bytes:
    """Return the latest version payload bytes for *secret_name* in *project*."""
    try:
        client = _get_secret_client()
        name = f"projects/{project}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data
    except Exception as exc:
        raise SecretFetchError(
            f"Failed to fetch secret '{secret_name}' from project '{project}': {exc}"
        ) from exc


def push_secret_version(project: str, secret_name: str, payload: bytes) -> None:
    """Add a new version to *secret_name* in *project*."""
    try:
        client = _get_secret_client()
        parent = f"projects/{project}/secrets/{secret_name}"
        client.add_secret_version(
            request={"parent": parent, "payload": {"data": payload}}
        )
    except Exception as exc:
        raise SecretPushError(
            f"Failed to push secret '{secret_name}' to project '{project}': {exc}"
        ) from exc


def ensure_secret_exists(project: str, secret_name: str) -> None:
    """Create the secret resource if it doesn't already exist."""
    try:
        client = _get_secret_client()
        client.create_secret(
            request={
                "parent": f"projects/{project}",
                "secret_id": secret_name,
                "secret": {"replication": {"automatic": {}}},
            }
        )
    except Exception as exc:
        from google.api_core.exceptions import AlreadyExists  # type: ignore

        if isinstance(exc, AlreadyExists):
            return
        raise SecretPushError(
            f"Failed to create secret '{secret_name}' in project '{project}': {exc}"
        ) from exc
