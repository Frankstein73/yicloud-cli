import json

import click
import pytest
from click.testing import CliRunner

from yicloud_cli.auth import ACCESS_KEY_ENV, SECRET_KEY_ENV
from yicloud_cli.cli import CliContext, create_cli, pass_cli_context
from yicloud_cli.errors import ApiError


@click.command("show")
@pass_cli_context
def show_context(context: CliContext) -> None:
    """Expose shared configuration for tests and future command modules."""
    context.write(
        {
            "endpoint": context.endpoint,
            "profile": context.profile,
            "authenticated": context.client is not None,
        }
    )


def test_help_and_version_do_not_construct_authenticated_client():
    calls = []
    application = create_cli(
        client_factory=lambda *args, **kwargs: calls.append((args, kwargs))
    )
    runner = CliRunner()

    help_result = runner.invoke(application, ["--help"])
    version_result = runner.invoke(application, ["--version"])

    assert help_result.exit_code == 0
    assert "Manage YiCloud custom tasks and development machines." in help_result.output
    assert "custom-task" in help_result.output
    assert "development-machine" in help_result.output
    assert "--endpoint" in help_result.output
    assert version_result.exit_code == 0
    assert version_result.output.startswith("yicloud, version ")
    assert calls == []


@pytest.mark.parametrize(
    "arguments,expected",
    [
        (["not-a-command"], "No such command 'not-a-command'"),
        (["--output", "yaml"], "Invalid value for '--output'"),
        (
            ["--endpoint", "gate.yicloud.com"],
            "must be an absolute http:// or https:// URL",
        ),
    ],
)
def test_invalid_commands_and_options_are_useful_usage_errors(arguments, expected):
    result = CliRunner().invoke(create_cli(), arguments)

    assert result.exit_code == 2
    assert "Usage:" in result.output
    assert expected in result.output


def test_extension_commands_receive_global_configuration_and_lazy_client():
    sentinel_client = object()
    calls = []

    def client_factory(config, *, environ):
        calls.append((config, environ))
        return sentinel_client

    environment = {
        ACCESS_KEY_ENV: "public-for-test",
        SECRET_KEY_ENV: "secret-for-test",
    }
    application = create_cli(
        custom_task_commands=[show_context],
        development_machine_commands=[show_context],
        client_factory=client_factory,
        environ=environment,
    )
    runner = CliRunner()

    custom_result = runner.invoke(
        application,
        [
            "--endpoint",
            "https://api.example.test/",
            "--profile",
            "staging",
            "custom-task",
            "show",
        ],
    )
    development_result = runner.invoke(
        application,
        ["--output", "json", "development-machine", "show"],
    )

    assert custom_result.exit_code == 0
    assert "endpoint: https://api.example.test" in custom_result.output
    assert "profile: staging" in custom_result.output
    assert "authenticated: yes" in custom_result.output
    assert development_result.exit_code == 0
    assert json.loads(development_result.output) == {
        "endpoint": "https://gate.yicloud.com",
        "profile": "default",
        "authenticated": True,
    }
    assert calls[0][0].host == "https://api.example.test"
    assert calls[0][1] is environment
    assert len(calls) == 2


def test_client_is_cached_for_the_duration_of_one_command():
    calls = []

    @click.command("twice")
    @pass_cli_context
    def use_client_twice(context: CliContext) -> None:
        context.write(context.client is context.client)

    application = create_cli(
        custom_task_commands=[use_client_twice],
        client_factory=lambda *args, **kwargs: calls.append((args, kwargs)) or object(),
        environ={},
    )

    result = CliRunner().invoke(application, ["custom-task", "twice"])

    assert result.exit_code == 0
    assert result.output == "True\n"
    assert len(calls) == 1


def test_global_configuration_can_be_loaded_from_environment():
    @click.command("settings")
    @pass_cli_context
    def settings(context: CliContext) -> None:
        context.write(
            {
                "endpoint": context.endpoint,
                "profile": context.profile,
                "output": context.output_format.value,
            }
        )

    application = create_cli(custom_task_commands=[settings])

    result = CliRunner().invoke(
        application,
        ["custom-task", "settings"],
        env={
            "YICLOUD_ENDPOINT": "https://environment.example.test/",
            "YICLOUD_PROFILE": "automation",
            "YICLOUD_OUTPUT": "json",
        },
    )

    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "endpoint": "https://environment.example.test",
        "profile": "automation",
        "output": "json",
    }


def test_human_and_json_output_have_stable_result_formatting():
    @click.command("list")
    @pass_cli_context
    def list_items(context: CliContext) -> None:
        context.write(
            [
                {"name": "build", "ready": True},
                {"name": "deploy", "ready": False},
            ]
        )

    application = create_cli(custom_task_commands=[list_items])
    runner = CliRunner()

    human = runner.invoke(application, ["custom-task", "list"])
    structured = runner.invoke(application, ["--output", "json", "custom-task", "list"])

    assert human.exit_code == 0
    assert "name" in human.output
    assert "build" in human.output
    assert "yes" in human.output
    assert "no" in human.output
    assert json.loads(structured.output) == [
        {"name": "build", "ready": True},
        {"name": "deploy", "ready": False},
    ]


@pytest.mark.parametrize("output_arguments", [[], ["--output", "json"]])
def test_normal_command_output_redacts_credentials(output_arguments):
    access_key = "public-key-that-must-not-leak"
    secret_key = "secret-key-that-must-not-leak"

    @click.command("credentials")
    @pass_cli_context
    def credentials(context: CliContext) -> None:
        context.write(
            {
                "Access_Key_ID": access_key,
                "nested": {
                    "Secret_Access_Key": secret_key,
                    "message": f"access_key={access_key}",
                },
            }
        )

    application = create_cli(
        custom_task_commands=[credentials],
        environ={ACCESS_KEY_ENV: access_key, SECRET_KEY_ENV: secret_key},
    )

    result = CliRunner().invoke(
        application, [*output_arguments, "custom-task", "credentials"]
    )

    assert result.exit_code == 0
    assert "[REDACTED]" in result.output
    assert access_key not in result.output
    assert secret_key not in result.output


def test_expected_api_errors_have_exit_one_and_redact_secrets():
    access_key = "public-key-that-must-not-leak"
    secret_key = "secret-key-that-must-not-leak"

    @click.command("fail")
    def fail() -> None:
        raise ApiError(
            f"request rejected for access_key={access_key} secret={secret_key}",
            code="DENIED",
            status=403,
        )

    application = create_cli(
        custom_task_commands=[fail],
        environ={ACCESS_KEY_ENV: access_key, SECRET_KEY_ENV: secret_key},
    )

    result = CliRunner().invoke(application, ["custom-task", "fail"])

    assert result.exit_code == 1
    assert "API request failed (HTTP 403, code DENIED)" in result.output
    assert "[REDACTED]" in result.output
    assert access_key not in result.output
    assert secret_key not in result.output


def test_missing_credentials_are_usage_errors_without_secret_values():
    application = create_cli(custom_task_commands=[show_context], environ={})

    result = CliRunner().invoke(application, ["custom-task", "show"])

    assert result.exit_code == 2
    assert ACCESS_KEY_ENV in result.output
    assert SECRET_KEY_ENV in result.output
    assert "Usage:" in result.output


def test_unexpected_exceptions_do_not_expose_exception_details():
    secret = "sensitive-value"

    @click.command("explode")
    def explode() -> None:
        raise RuntimeError(f"internal failure containing {secret}")

    application = create_cli(custom_task_commands=[explode])

    result = CliRunner().invoke(application, ["custom-task", "explode"])

    assert result.exit_code == 1
    assert (
        "Command failed unexpectedly; no sensitive details were displayed."
        in result.output
    )
    assert secret not in result.output
