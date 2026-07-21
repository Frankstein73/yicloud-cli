"""Credential loading and authenticated YiCloud SDK client construction."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from yicloud.base.auth.credential import Credential
from yicloud.base.client import Client
from yicloud.base.config import Config


ACCESS_KEY_ENV = "Access_Key_ID"
SECRET_KEY_ENV = "Secret_Access_Key"


class AuthenticationError(ValueError):
    """Raised when required YiCloud credentials are unavailable."""


@dataclass(frozen=True)
class ClientConfig:
    """Non-secret settings used to construct the SDK client."""

    host: str = "https://gate.yicloud.com"
    timeout: float = 30.0


def load_credentials(environ: Mapping[str, str] | None = None) -> Credential:
    """Load and validate credentials from the two supported environment variables."""
    values = os.environ if environ is None else environ
    access_key = values.get(ACCESS_KEY_ENV, "").strip()
    secret_key = values.get(SECRET_KEY_ENV, "").strip()
    missing = [
        name
        for name, value in (
            (ACCESS_KEY_ENV, access_key),
            (SECRET_KEY_ENV, secret_key),
        )
        if not value
    ]
    if missing:
        names = ", ".join(missing)
        raise AuthenticationError(
            f"Missing required YiCloud credential environment variable(s): {names}."
        )
    return Credential(public_key=access_key, private_key=secret_key)


def build_client(
    config: ClientConfig | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    http_client=None,
) -> Client:
    """Build an authenticated SDK client without exposing secret values."""
    settings = config or ClientConfig()
    sdk_config = Config(host=settings.host, timeout=settings.timeout)
    return Client(cfg=sdk_config, crede=load_credentials(environ), http_client=http_client)
