"""Sandbox commands backed by the YiCloud sandbox OpenAPI."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

import click
from yicloud.services import sandbox
from yicloud.services.sandbox import models

from .output import OutputFormat


_RFC3339_SUFFIX = re.compile(r"(?:Z|[+-]\d{2}:\d{2})$")


def _non_empty(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        raise click.BadParameter("must not be empty", param_hint=label)
    return value


def _rfc3339(
    _ctx: click.Context, param: click.Parameter, value: str | None
) -> str | None:
    if value is None:
        return None
    if not _RFC3339_SUFFIX.search(value):
        raise click.BadParameter(
            "must be an RFC3339 timestamp with a timezone", param=param
        )
    try:
        datetime.fromisoformat(
            value.removesuffix("Z") + ("+00:00" if value.endswith("Z") else "")
        )
    except ValueError:
        raise click.BadParameter(
            "must be a valid RFC3339 timestamp", param=param
        ) from None
    return value


def _key_value(
    _ctx: click.Context, param: click.Parameter, values: tuple[str, ...]
) -> dict[str, str] | None:
    if not values:
        return None
    result: dict[str, str] = {}
    for value in values:
        key, separator, item = value.partition("=")
        if not separator or not key.strip():
            raise click.BadParameter("must use KEY=VALUE", param=param)
        key = key.strip()
        if key in result:
            raise click.BadParameter(f"contains duplicate key {key!r}", param=param)
        result[key] = item
    return result


def _port(
    _ctx: click.Context, param: click.Parameter, values: tuple[str, ...]
) -> list[models.CreateSandboxReqPort] | None:
    if not values:
        return None
    ports = []
    seen = set()
    for value in values:
        parts = value.split(":", 2)
        try:
            number = int(parts[0])
        except ValueError:
            raise click.BadParameter(
                "must start with a numeric container port", param=param
            ) from None
        if not 1 <= number <= 65535:
            raise click.BadParameter(
                "container port must be between 1 and 65535", param=param
            )
        if number in seen:
            raise click.BadParameter(
                f"contains duplicate container port {number}", param=param
            )
        seen.add(number)
        ports.append(
            models.CreateSandboxReqPort(
                ContainerPort=number,
                Name=parts[1] or None if len(parts) > 1 else None,
                Purpose=parts[2] or None if len(parts) > 2 else None,
            )
        )
    return ports


def _volume(
    _ctx: click.Context, param: click.Parameter, values: tuple[str, ...]
) -> list[models.CreateSandboxReqVolume] | None:
    if not values:
        return None
    volumes = []
    for value in values:
        try:
            item = json.loads(value)
        except json.JSONDecodeError as error:
            raise click.BadParameter(
                f"must be valid JSON: {error.msg}", param=param
            ) from None
        if not isinstance(item, dict) or not str(item.get("mount_path", "")).strip():
            raise click.BadParameter(
                "must be an object with a non-empty mount_path", param=param
            )
        source_names = [
            name for name in ("host", "ossfs", "pvc") if item.get(name) is not None
        ]
        if len(source_names) != 1:
            raise click.BadParameter(
                "must define exactly one of host, ossfs, or pvc", param=param
            )
        allowed = {"mount_path", "name", "read_only", "sub_path", *source_names}
        unknown = sorted(set(item) - allowed)
        if unknown:
            raise click.BadParameter(
                f"contains unsupported field(s): {', '.join(unknown)}", param=param
            )

        host = ossfs = pvc = None
        source = item[source_names[0]]
        if not isinstance(source, dict):
            raise click.BadParameter(
                f"{source_names[0]} must be an object", param=param
            )
        if source_names[0] == "host":
            if set(source) != {"path"} or not str(source.get("path", "")).strip():
                raise click.BadParameter(
                    "host must contain only a non-empty path", param=param
                )
            host = models.CreateSandboxReqVolumeHost(Path=source["path"])
        elif source_names[0] == "ossfs":
            if set(source) != {"bucket", "endpoint"} or not all(
                str(source.get(key, "")).strip() for key in ("bucket", "endpoint")
            ):
                raise click.BadParameter(
                    "ossfs must contain non-empty bucket and endpoint", param=param
                )
            ossfs = models.CreateSandboxReqVolumeOSSFS(
                Bucket=source["bucket"], Endpoint=source["endpoint"]
            )
        else:
            if (
                set(source) != {"claim_name"}
                or not str(source.get("claim_name", "")).strip()
            ):
                raise click.BadParameter(
                    "pvc must contain only a non-empty claim_name", param=param
                )
            pvc = models.CreateSandboxReqVolumePVC(ClaimName=source["claim_name"])
        if "read_only" in item and not isinstance(item["read_only"], bool):
            raise click.BadParameter("read_only must be a JSON boolean", param=param)
        volumes.append(
            models.CreateSandboxReqVolume(
                MountPath=item["mount_path"],
                Host=host,
                Ossfs=ossfs,
                Pvc=pvc,
                Name=item.get("name"),
                ReadOnly=item.get("read_only"),
                SubPath=item.get("sub_path"),
            )
        )
    return volumes


def _snake_case(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _normalized(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    if isinstance(value, dict):
        return {_snake_case(str(key)): _normalized(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalized(item) for item in value]
    return value


def _strip(value: str | None, label: str) -> str | None:
    return _non_empty(value, label) if value is not None else None


def _comma_separated(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    items = [item.strip() for item in value.split(",")]
    if not items or any(not item for item in items):
        raise click.BadParameter(
            "must be a comma-separated list of non-empty values", param_hint=label
        )
    return ",".join(items)


def _invoke(context: Any, action: Any, request: Any) -> Any:
    sandbox.use_client(context.client)
    return action(None, request)


def _write_machine(context: Any, value: Any) -> None:
    context.write(_normalized(value))


def _write_machine_list(context: Any, value: Any) -> None:
    result = _normalized(value) or {}
    if context.output_format is OutputFormat.JSON:
        context.write(result)
        return
    rows = [
        {
            "id": item.get("id", ""),
            "name": item.get("name", ""),
            "state": item.get("run_state")
            or (item.get("status") or {}).get("state", ""),
            "type": item.get("type", ""),
            "created_at": item.get("created_at", ""),
            "expires_at": item.get("expires_at", ""),
        }
        for item in result.get("items") or []
    ]
    context.write(rows)


_project_option = click.option(
    "--project", "project_name", required=True, help="Project namespace."
)


@click.command("create")
@_project_option
@click.option("--name", help="Machine name.")
@click.option("--environment-id", help="Existing development environment identifier.")
@click.option("--image-ref", help="Image reference for a direct machine creation.")
@click.option(
    "--image-uri", help="Legacy full image URI for a direct machine creation."
)
@click.option("--image-username", help="Registry username associated with the image.")
@click.option("--cpu", help="CPU request for a direct machine creation, for example 2.")
@click.option(
    "--memory", help="Memory request for a direct machine creation, for example 4Gi."
)
@click.option(
    "--entrypoint",
    multiple=True,
    help="Entrypoint argument; repeat to preserve argument boundaries.",
)
@click.option(
    "--env",
    "environment",
    multiple=True,
    callback=_key_value,
    metavar="KEY=VALUE",
    help="Environment variable; repeatable.",
)
@click.option(
    "--port",
    "ports",
    multiple=True,
    callback=_port,
    metavar="PORT[:NAME[:PURPOSE]]",
    help="Exposed container port; repeatable.",
)
@click.option(
    "--volume",
    "volumes",
    multiple=True,
    callback=_volume,
    metavar="JSON",
    help="Volume JSON with mount_path and exactly one of host, ossfs, or pvc; repeatable.",
)
@click.option(
    "--lifecycle-minutes",
    type=click.IntRange(min=1),
    help="Machine lifetime in minutes.",
)
@click.option(
    "--request-timeout-seconds",
    type=click.IntRange(min=1),
    help="Per-request timeout in seconds.",
)
@click.pass_obj
def create_machine(
    context: Any,
    project_name: str,
    name: str | None,
    environment_id: str | None,
    image_ref: str | None,
    image_uri: str | None,
    image_username: str | None,
    cpu: str | None,
    memory: str | None,
    entrypoint: tuple[str, ...],
    environment: dict[str, str] | None,
    ports: list[models.CreateSandboxReqPort] | None,
    volumes: list[models.CreateSandboxReqVolume] | None,
    lifecycle_minutes: int | None,
    request_timeout_seconds: int | None,
) -> None:
    """Create a Sandbox resource."""
    project_name = _non_empty(project_name, "--project")
    name = _strip(name, "--name")
    environment_id = _strip(environment_id, "--environment-id")
    image_ref = _strip(image_ref, "--image-ref")
    image_uri = _strip(image_uri, "--image-uri")
    image_username = _strip(image_username, "--image-username")
    cpu = _strip(cpu, "--cpu")
    memory = _strip(memory, "--memory")
    if bool(environment_id) == bool(image_ref or image_uri):
        raise click.UsageError(
            "provide exactly one of --environment-id or --image-ref/--image-uri"
        )
    if image_ref and image_uri:
        raise click.UsageError("provide only one of --image-ref and --image-uri")
    if image_username and not (image_ref or image_uri):
        raise click.UsageError("--image-username requires --image-ref or --image-uri")
    if bool(cpu) != bool(memory):
        raise click.UsageError("--cpu and --memory must be provided together")
    if (image_ref or image_uri) and not (cpu and memory):
        raise click.UsageError("direct image creation requires --cpu and --memory")

    image = None
    if image_ref or image_uri:
        auth = (
            models.CreateSandboxReqImageAuth(Username=image_username)
            if image_username
            else None
        )
        image = models.CreateSandboxReqImageInput(
            Auth=auth, Ref=image_ref, Uri=image_uri
        )
    resources = (
        models.CreateSandboxReqResources(Cpu=cpu, Memory=memory)
        if cpu and memory
        else None
    )
    request = models.CreateSandboxReq(
        ProjectName=project_name,
        Entrypoint=list(entrypoint) or None,
        Env=environment,
        EnvironmentId=environment_id,
        Image=image,
        LifecycleMinutes=lifecycle_minutes,
        Name=name,
        Ports=ports,
        RequestTimeoutSeconds=request_timeout_seconds,
        Resources=resources,
        Volumes=volumes,
    )
    _write_machine(context, _invoke(context, sandbox.create_sandbox, request))


@click.command("list")
@_project_option
@click.option("--keyword")
@click.option("--environment-id")
@click.option("--environment-ids", help="Comma-separated environment identifiers.")
@click.option(
    "--allocation-mode", multiple=True, type=click.Choice(["prewarm", "manual"])
)
@click.option(
    "--run-state",
    multiple=True,
    type=click.Choice(
        [
            "pending",
            "running",
            "terminating",
            "paused",
            "failed",
            "terminated",
            "expired",
        ]
    ),
)
@click.option(
    "--state",
    multiple=True,
    type=click.Choice(
        [
            "pending",
            "running",
            "terminating",
            "paused",
            "failed",
            "terminated",
            "expired",
        ]
    ),
)
@click.option(
    "--type",
    "machine_type",
    type=click.Choice(["code", "browser", "desktop", "custom"]),
)
@click.option("--creator", "creators")
@click.option("--batch-name")
@click.option("--metadata")
@click.option("--quota-groups")
@click.option("--created-after", callback=_rfc3339)
@click.option("--created-before", callback=_rfc3339)
@click.option("--expire-before", callback=_rfc3339)
@click.option(
    "--self-only",
    "self_only",
    is_flag=True,
    default=None,
    help="Only machines created by the current user.",
)
@click.option("--sort-by")
@click.option("--sort-order", type=click.Choice(["asc", "desc"]))
@click.option("--limit", type=click.IntRange(min=1))
@click.option("--offset", type=click.IntRange(min=0))
@click.pass_obj
def list_machines(
    context: Any,
    project_name: str,
    keyword: str | None,
    environment_id: str | None,
    environment_ids: str | None,
    allocation_mode: tuple[str, ...],
    run_state: tuple[str, ...],
    state: tuple[str, ...],
    machine_type: str | None,
    creators: str | None,
    batch_name: str | None,
    metadata: str | None,
    quota_groups: str | None,
    created_after: str | None,
    created_before: str | None,
    expire_before: str | None,
    self_only: bool | None,
    sort_by: str | None,
    sort_order: str | None,
    limit: int | None,
    offset: int | None,
) -> None:
    """List Sandbox resources in a project."""
    created_after_value = (
        datetime.fromisoformat(created_after.replace("Z", "+00:00"))
        if created_after
        else None
    )
    created_before_value = (
        datetime.fromisoformat(created_before.replace("Z", "+00:00"))
        if created_before
        else None
    )
    if (
        created_after_value
        and created_before_value
        and created_after_value > created_before_value
    ):
        raise click.UsageError(
            "--created-after must not be later than --created-before"
        )
    request = models.ListSandboxesReq(
        ProjectName=_non_empty(project_name, "--project"),
        AllocationMode=",".join(allocation_mode) or None,  # type: ignore[arg-type]
        BatchName=_strip(batch_name, "--batch-name"),
        CreatedAfter=created_after,
        CreatedBefore=created_before,
        Creators=_strip(creators, "--creator"),
        EnvironmentId=_strip(environment_id, "--environment-id"),
        EnvironmentIds=_comma_separated(environment_ids, "--environment-ids"),
        ExpireBefore=expire_before,
        Keyword=_strip(keyword, "--keyword"),
        Limit=limit,
        Metadata=_strip(metadata, "--metadata"),
        Offset=offset,
        QuotaGroups=_comma_separated(quota_groups, "--quota-groups"),
        RunState=",".join(run_state) or None,
        Self=self_only,
        SortBy=_strip(sort_by, "--sort-by"),
        SortOrder=sort_order,  # type: ignore[arg-type]
        State=",".join(state) or None,
        Type=machine_type,  # type: ignore[arg-type]
    )
    _write_machine_list(context, _invoke(context, sandbox.list_sandboxes, request))


def _machine_id_argument(function: Any) -> Any:
    return click.argument("machine_id")(function)


@click.command("inspect")
@_project_option
@_machine_id_argument
@click.pass_obj
def inspect_machine(context: Any, project_name: str, machine_id: str) -> None:
    """Inspect one Sandbox resource by identifier."""
    request = models.GetSandboxReq(
        ProjectName=_non_empty(project_name, "--project"),
        SandboxId=_non_empty(machine_id, "MACHINE_ID"),
    )
    _write_machine(context, _invoke(context, sandbox.get_sandbox, request))


def _result(action: str, machine_id: str) -> dict[str, str]:
    return {"id": machine_id, "action": action, "status": "accepted"}


@click.command("stop")
@_project_option
@_machine_id_argument
@click.pass_obj
def stop_machine(context: Any, project_name: str, machine_id: str) -> None:
    """Stop one Sandbox resource."""
    machine_id = _non_empty(machine_id, "MACHINE_ID")
    request = models.StopSandboxReq(
        ProjectName=_non_empty(project_name, "--project"), SandboxId=machine_id
    )
    _invoke(context, sandbox.stop_sandbox, request)
    context.write(_result("stop", machine_id))


@click.command("delete")
@_project_option
@_machine_id_argument
@click.pass_obj
def delete_machine(context: Any, project_name: str, machine_id: str) -> None:
    """Delete one Sandbox resource."""
    machine_id = _non_empty(machine_id, "MACHINE_ID")
    request = models.DeleteSandboxReq(
        ProjectName=_non_empty(project_name, "--project"), SandboxId=machine_id
    )
    _invoke(context, sandbox.delete_sandbox, request)
    context.write(_result("delete", machine_id))


@click.command("batch-delete")
@_project_option
@click.argument("machine_ids", nargs=-1, required=True)
@click.pass_obj
def batch_delete_machines(
    context: Any, project_name: str, machine_ids: tuple[str, ...]
) -> None:
    """Delete up to 100 Sandbox resources."""
    if len(machine_ids) > 100:
        raise click.UsageError("at most 100 machine identifiers can be deleted at once")
    if len(set(machine_ids)) != len(machine_ids):
        raise click.UsageError("machine identifiers must be unique")
    request = models.BatchDeleteSandboxesReq(
        Ids=[_non_empty(item, "MACHINE_IDS") for item in machine_ids],
        ProjectName=_non_empty(project_name, "--project"),
    )
    _write_machine(context, _invoke(context, sandbox.batch_delete_sandboxes, request))


@click.command("update-lifecycle")
@_project_option
@_machine_id_argument
@click.option(
    "--minutes",
    required=True,
    type=click.IntRange(min=1),
    help="New lifetime or extension in minutes.",
)
@click.option("--mode", required=True, type=click.Choice(["set", "extend"]))
@click.pass_obj
def update_lifecycle(
    context: Any, project_name: str, machine_id: str, minutes: int, mode: str
) -> None:
    """Set or extend a Sandbox resource lifecycle."""
    request = models.UpdateSandboxLifecycleReq(
        LifecycleMinutes=minutes,
        Mode=mode,
        ProjectName=_non_empty(project_name, "--project"),
        SandboxId=_non_empty(machine_id, "MACHINE_ID"),
    )
    _write_machine(context, _invoke(context, sandbox.update_sandbox_lifecycle, request))


COMMANDS = (
    create_machine,
    list_machines,
    inspect_machine,
    stop_machine,
    delete_machine,
    batch_delete_machines,
    update_lifecycle,
)


def _deprecated_development_machine_alias(command: click.Command) -> click.Command:
    alias = copy.copy(command)
    alias.hidden = True
    alias.deprecated = f"Use 'yicloud sandbox {command.name}' instead."
    return alias


LEGACY_DEVELOPMENT_MACHINE_COMMANDS = tuple(
    _deprecated_development_machine_alias(command)
    for command in COMMANDS
    if command.name not in {"list", "inspect"}
)
