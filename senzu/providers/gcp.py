from __future__ import annotations

from ..exceptions import ProviderNotInstalledError, SecretFetchError, SecretPushError, SenzuError


class GcpProvider:
    def __init__(self, project: str) -> None:
        self._project = project
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from google.cloud import secretmanager  # type: ignore
            except ImportError:
                raise ProviderNotInstalledError(
                    "GCP support requires 'google-cloud-secret-manager'. "
                    "Install it with:  pip install senzu[gcp]"
                )
            self._client = secretmanager.SecretManagerServiceClient()
        return self._client

    def fetch_latest(self, secret_name: str) -> bytes:
        try:
            client = self._get_client()
            name = f"projects/{self._project}/secrets/{secret_name}/versions/latest"
            response = client.access_secret_version(request={"name": name})
            return response.payload.data
        except SenzuError:
            raise
        except Exception as exc:
            raise SecretFetchError(
                f"Failed to fetch secret '{secret_name}' from project '{self._project}': {exc}"
            ) from exc

    def push_version(self, secret_name: str, payload: bytes) -> None:
        try:
            client = self._get_client()
            parent = f"projects/{self._project}/secrets/{secret_name}"
            client.add_secret_version(
                request={"parent": parent, "payload": {"data": payload}}
            )
        except SenzuError:
            raise
        except Exception as exc:
            raise SecretPushError(
                f"Failed to push secret '{secret_name}' to project '{self._project}': {exc}"
            ) from exc

    def ensure_exists(self, secret_name: str) -> None:
        try:
            client = self._get_client()
            client.create_secret(
                request={
                    "parent": f"projects/{self._project}",
                    "secret_id": secret_name,
                    "secret": {"replication": {"automatic": {}}},
                }
            )
        except SenzuError:
            raise
        except Exception as exc:
            from google.api_core.exceptions import AlreadyExists  # type: ignore

            if isinstance(exc, AlreadyExists):
                return
            raise SecretPushError(
                f"Failed to create secret '{secret_name}' in project '{self._project}': {exc}"
            ) from exc
