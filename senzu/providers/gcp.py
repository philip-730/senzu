from __future__ import annotations

from ..exceptions import SecretFetchError, SecretPushError


class GcpProvider:
    def __init__(self, project: str) -> None:
        self._project = project

    def _client(self):
        try:
            from google.cloud import secretmanager  # type: ignore
        except ImportError:
            raise RuntimeError(
                "GCP support requires 'google-cloud-secret-manager'. "
                "Install it with:  pip install senzu[gcp]"
            )
        return secretmanager.SecretManagerServiceClient()

    def fetch_latest(self, secret_name: str) -> bytes:
        try:
            client = self._client()
            name = f"projects/{self._project}/secrets/{secret_name}/versions/latest"
            response = client.access_secret_version(request={"name": name})
            return response.payload.data
        except (RuntimeError, ImportError):
            raise
        except Exception as exc:
            raise SecretFetchError(
                f"Failed to fetch secret '{secret_name}' from project '{self._project}': {exc}"
            ) from exc

    def push_version(self, secret_name: str, payload: bytes) -> None:
        try:
            client = self._client()
            parent = f"projects/{self._project}/secrets/{secret_name}"
            client.add_secret_version(
                request={"parent": parent, "payload": {"data": payload}}
            )
        except (RuntimeError, ImportError):
            raise
        except Exception as exc:
            raise SecretPushError(
                f"Failed to push secret '{secret_name}' to project '{self._project}': {exc}"
            ) from exc

    def ensure_exists(self, secret_name: str) -> None:
        try:
            client = self._client()
            client.create_secret(
                request={
                    "parent": f"projects/{self._project}",
                    "secret_id": secret_name,
                    "secret": {"replication": {"automatic": {}}},
                }
            )
        except (RuntimeError, ImportError):
            raise
        except Exception as exc:
            from google.api_core.exceptions import AlreadyExists  # type: ignore

            if isinstance(exc, AlreadyExists):
                return
            raise SecretPushError(
                f"Failed to create secret '{secret_name}' in project '{self._project}': {exc}"
            ) from exc
