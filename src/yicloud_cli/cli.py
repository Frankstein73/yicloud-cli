"""Reusable command-line application and command extension points."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from importlib.metadata import version
from typing import Any
from urllib.parse import urlparse

import click
import requests
from yicloud.base.client import Client

from .auth import AuthenticationError, ClientConfig, build_client
from .errors import ApiError, api_error_from_sdk, format_api_error, redact_sensitive
from .output import OutputFormat, OutputWriter


ClientFactory = Callable[..., Client]
CustomTaskServiceFactory = Callable[[Client], Any]


def _package_version() -> str:
    return version("yicloud-cli")


def _validate_endpoint(_ctx: click.Context, _param: click.Parameter, value: str) -> str:
    endpoint = value.rstrip("/")
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise click.BadParameter("must be an absolute http:// or https:// URL")
    return endpoint


@dataclass
class CliContext:
    """Global configuration and lazily initialized dependencies for commands."""

    endpoint: str
    profile: str
    output_format: OutputFormat
    environ: Mapping[str, str] = field(repr=False)
    client_factory: ClientFactory = field(default=build_client, repr=False)
    custom_task_service_factory: CustomTaskServiceFactory | None = field(
        default=None, repr=False
    )
    _client: Client | None = field(default=None, init=False, repr=False)
    _custom_tasks: Any = field(default=None, init=False, repr=False)

    @property
    def client(self) -> Client:
        """Return one authenticated SDK client, creating it only when needed."""
        if self._client is None:
            self._client = self.client_factory(
                ClientConfig(host=self.endpoint),
                environ=self.environ,
            )
        return self._client

    def write(self, value: Any) -> None:
        """Render a command result using the selected global output format."""
        OutputWriter(self.output_format, environ=self.environ).write(value)

    @property
    def custom_tasks(self) -> Any:
        """Return the custom-task service bound to this command's client."""
        if self._custom_tasks is None:
            if self.custom_task_service_factory is None:
                from .custom_tasks import CustomTaskService

                self.custom_task_service_factory = CustomTaskService
            self._custom_tasks = self.custom_task_service_factory(self.client)
        return self._custom_tasks


pass_cli_context = click.make_pass_decorator(CliContext)


class YiCloudGroup(click.Group):
    """Root group that converts command failures to safe, stable CLI errors."""

    def invoke(self, ctx: click.Context) -> Any:
        try:
            return super().invoke(ctx)
        except click.exceptions.Exit:
            raise
        except click.ClickException:
            raise
        except AuthenticationError as error:
            raise click.UsageError(str(error), ctx) from None
        except ApiError as error:
            environ = ctx.find_root().obj.environ if ctx.find_root().obj else os.environ
            raise click.ClickException(format_api_error(error, environ)) from None
        except requests.RequestException as error:
            environ = ctx.find_root().obj.environ if ctx.find_root().obj else os.environ
            message = redact_sensitive(error, environ)
            raise click.ClickException(f"API request failed: {message}") from None
        except Exception as error:
            # The generated SDK's exception hierarchy is intentionally imported
            # lazily so help/version remain lightweight and credential-free.
            from yicloud.base.errs import YiCloudException

            if isinstance(error, YiCloudException):
                environ = (
                    ctx.find_root().obj.environ if ctx.find_root().obj else os.environ
                )
                raise click.ClickException(
                    format_api_error(api_error_from_sdk(error), environ)
                ) from None
            raise click.ClickException(
                "Command failed unexpectedly; no sensitive details were displayed."
            ) from None


def _namespace_group(name: str, help_text: str) -> click.Group:
    return click.Group(name=name, help=help_text, no_args_is_help=True)


def create_cli(
    *,
    custom_task_commands: Sequence[click.Command] | None = None,
    development_machine_commands: Sequence[click.Command] = (),
    client_factory: ClientFactory = build_client,
    custom_task_service_factory: CustomTaskServiceFactory | None = None,
    environ: Mapping[str, str] | None = None,
) -> click.Group:
    """Build the CLI, optionally registering resource commands into namespaces."""
    cli_environ = os.environ if environ is None else environ
    if custom_task_commands is None:
        from .custom_tasks import custom_task_commands as default_custom_task_commands

        custom_task_commands = default_custom_task_commands

    @click.group(
        cls=YiCloudGroup, context_settings={"help_option_names": ["-h", "--help"]}
    )
    @click.version_option(version=_package_version(), prog_name="yicloud")
    @click.option(
        "--endpoint",
        envvar="YICLOUD_ENDPOINT",
        default=ClientConfig.host,
        show_default=True,
        callback=_validate_endpoint,
        help="YiCloud OpenAPI base URL.",
    )
    @click.option(
        "--profile",
        envvar="YICLOUD_PROFILE",
        default="default",
        show_default=True,
        help="Configuration profile name passed to commands.",
    )
    @click.option(
        "--output",
        "output_format",
        type=click.Choice([item.value for item in OutputFormat], case_sensitive=False),
        envvar="YICLOUD_OUTPUT",
        default=OutputFormat.HUMAN.value,
        show_default=True,
        help="Result output format.",
    )
    @click.pass_context
    def application(
        ctx: click.Context,
        endpoint: str,
        profile: str,
        output_format: str,
    ) -> None:
        """Manage YiCloud custom tasks and development machines."""
        ctx.obj = CliContext(
            endpoint=endpoint,
            profile=profile,
            output_format=OutputFormat(output_format.lower()),
            environ=cli_environ,
            client_factory=client_factory,
            custom_task_service_factory=custom_task_service_factory,
        )

    custom_tasks = _namespace_group(
        "custom-task",
        "Manage YiCloud custom tasks.",
    )
    for command in custom_task_commands:
        custom_tasks.add_command(command)
    application.add_command(custom_tasks)

    development_machines = _namespace_group(
        "development-machine",
        "Manage YiCloud development machines.",
    )
    for command in development_machine_commands:
        development_machines.add_command(command)
    application.add_command(development_machines)
    return application


cli = create_cli()


def main() -> None:
    """Run the installed console command."""
    cli(prog_name="yicloud")
