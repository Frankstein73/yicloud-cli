import json

import pytest
import requests_mock

from yicloud.base.client import Client
from yicloud.base.msgs import Rsp
from yicloud_cli.auth import (
    ACCESS_KEY_ENV,
    SECRET_KEY_ENV,
    AuthenticationError,
    build_client,
    load_credentials,
)


ACCESS_KEY = "access-key-for-tests"
SECRET_KEY = "secret-key-for-tests"


def test_load_credentials_uses_only_supported_names():
    credentials = load_credentials(
        {
            ACCESS_KEY_ENV: ACCESS_KEY,
            SECRET_KEY_ENV: SECRET_KEY,
            "YICLOUD_PUBLIC_KEY": "wrong-name",
            "YICLOUD_SECRET_KEY": "wrong-name",
        }
    )

    assert credentials.public_key == ACCESS_KEY
    assert credentials.private_key == SECRET_KEY


@pytest.mark.parametrize(
    "environment,missing",
    [
        ({SECRET_KEY_ENV: SECRET_KEY}, ACCESS_KEY_ENV),
        ({ACCESS_KEY_ENV: ACCESS_KEY}, SECRET_KEY_ENV),
        ({}, f"{ACCESS_KEY_ENV}, {SECRET_KEY_ENV}"),
    ],
)
def test_missing_credentials_are_actionable_and_redacted(environment, missing):
    with pytest.raises(AuthenticationError) as raised:
        load_credentials(environment)

    message = str(raised.value)
    assert missing in message
    assert ACCESS_KEY not in message
    assert SECRET_KEY not in message


def test_build_client_constructs_sdk_client_without_secret_repr():
    client = build_client(environ={ACCESS_KEY_ENV: ACCESS_KEY, SECRET_KEY_ENV: SECRET_KEY})

    assert isinstance(client, Client)
    assert client.crede.public_key == ACCESS_KEY
    assert client.crede.private_key == SECRET_KEY
    assert SECRET_KEY not in repr(client)


def test_authenticated_request_uses_sdk_transport_and_redacts_secret():
    with requests_mock.Mocker() as mock:
        mock.get(
            "https://gate.yicloud.com/health",
            json={"Code": 0, "Msg": "ok", "Data": {"status": "ready"}},
        )
        client = build_client(
            environ={ACCESS_KEY_ENV: ACCESS_KEY, SECRET_KEY_ENV: SECRET_KEY},
        )
        response = Rsp()

        client.get(None, "/health", {}, response)

        request = mock.last_request
        assert request is not None
        assert request.headers["X-OGW-PUBLIC-KEY"] == ACCESS_KEY
        assert SECRET_KEY not in (request.text or "")
        assert SECRET_KEY not in json.dumps(dict(request.headers))
