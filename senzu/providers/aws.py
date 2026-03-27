from __future__ import annotations

from ..exceptions import ProviderNotInstalledError, SecretFetchError, SecretPushError, SenzuError


class AwsProvider:
    def __init__(self, region: str) -> None:
        self._region = region

    def _get_client(self):
        try:
            import boto3  # type: ignore
        except ImportError:
            raise ProviderNotInstalledError(
                "AWS support requires 'boto3'. "
                "Install it with:  pip install senzu[aws]"
            )
        return boto3.client("secretsmanager", region_name=self._region)

    def fetch_latest(self, secret_name: str) -> bytes:
        try:
            resp = self._get_client().get_secret_value(SecretId=secret_name)
            if "SecretBinary" in resp:
                return resp["SecretBinary"]
            return resp["SecretString"].encode()
        except SenzuError:
            raise
        except Exception as exc:
            raise SecretFetchError(
                f"Failed to fetch secret '{secret_name}' from AWS region '{self._region}': {exc}"
            ) from exc

    def push_version(self, secret_name: str, payload: bytes) -> None:
        try:
            self._get_client().put_secret_value(
                SecretId=secret_name,
                SecretString=payload.decode(),
            )
        except SenzuError:
            raise
        except Exception as exc:
            raise SecretPushError(
                f"Failed to push secret '{secret_name}' to AWS region '{self._region}': {exc}"
            ) from exc

    def ensure_exists(self, secret_name: str) -> None:
        try:
            self._get_client().create_secret(
                Name=secret_name,
                SecretString="",
            )
        except SenzuError:
            raise
        except Exception as exc:
            try:
                import botocore.exceptions  # type: ignore

                if (
                    isinstance(exc, botocore.exceptions.ClientError)
                    and exc.response["Error"]["Code"] == "ResourceExistsException"
                ):
                    return
            except ImportError:
                pass
            raise SecretPushError(
                f"Failed to create secret '{secret_name}' in AWS region '{self._region}': {exc}"
            ) from exc
