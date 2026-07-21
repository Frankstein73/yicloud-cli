"""Development-machine reads backed by the YiCloud Workspace OpenAPI."""

from __future__ import annotations

import re
from dataclasses import asdict, is_dataclass
from typing import Any

import click
from yicloud.services import workspace
from yicloud.services.workspace import models

from .output import OutputFormat


class _CommaSeparatedQueryValues(list[str]):
    """Keep SDK list semantics while producing its expected query representation."""

    def __str__(self) -> str:
        return ",".join(self)


def _non_empty(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        raise click.BadParameter("must not be empty", param_hint=label)
    return value


def _optional_text(value: str | None, label: str) -> str | None:
    return _non_empty(value, label) if value is not None else None


def _repeated_text(
    _ctx: click.Context, param: click.Parameter, values: tuple[str, ...]
) -> list[str] | None:
    if not values:
        return None
    return _CommaSeparatedQueryValues(
        _non_empty(value, f"--{param.name.replace('_', '-')}") for value in values
    )


def _snake_case(name: str) -> str:
    name = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()


def _normalized(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    if isinstance(value, dict):
        return {_snake_case(str(key)): _normalized(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalized(item) for item in value]
    return value


def _workspace_view(value: Any) -> dict[str, Any]:
    item = _normalized(value) or {}
    return {
        "workspace_id": item.get("workspace_id", ""),
        "uid": item.get("uid", ""),
        "project": item.get("project", ""),
        "name": item.get("name", ""),
        "phase": item.get("phase", ""),
        "resources": {
            "cpu": item.get("cpu", ""),
            "memory": item.get("memory", ""),
            "gpu": item.get("gpu", ""),
            "worker_count": item.get("worker_count", 0),
        },
        "creator": {
            "name": item.get("creator", ""),
            "id": item.get("creator_id", ""),
            "real_name": item.get("real_creator", ""),
            "real_id": item.get("real_creator_id", ""),
        },
        "quota_group": item.get("quota_group", ""),
        "sku": {
            "id": item.get("sku_id", ""),
            "pool_name": item.get("sku_pool_name", ""),
            "pool_type": item.get("sku_pool_type", ""),
            "resource_scope": item.get("sku_resource_scope", ""),
            "public": item.get("sku_public", False),
            "private": item.get("sku_private", False),
            "project": item.get("sku_project", False),
            "tenant": item.get("sku_tenant", False),
        },
        "timestamps": {
            "created": item.get("creation_time", ""),
            "updated": item.get("update_time", ""),
            "started": item.get("start_timestamp", ""),
            "stopped": item.get("stop_timestamp", ""),
        },
        "runtime_mode": item.get("runtime_mode", ""),
        "image": item.get("image", ""),
        "description": item.get("description", ""),
        "use_private_machine": item.get("use_private_machine", False),
    }


def _invoke(context: Any, action: Any, request: Any) -> Any:
    workspace.use_client(context.client)
    return action(None, request)


def _validate_range(
    minimum: int | None,
    maximum: int | None,
    minimum_option: str,
    maximum_option: str,
) -> None:
    if minimum is not None and maximum is not None and minimum > maximum:
        raise click.UsageError(
            f"{minimum_option} must not be greater than {maximum_option}"
        )


@click.command("list")
@click.option("--project", help="Filter by project namespace.")
@click.option(
    "--workspace-id",
    "workspace_ids",
    multiple=True,
    callback=_repeated_text,
    help="Workspace ID; repeat to match multiple workspaces.",
)
@click.option("--name", help="Workspace name filter (fuzzy match).")
@click.option("--creator", help="Creator username.")
@click.option("--share", help="Workspace share mode.")
@click.option(
    "--quota-group",
    "quota_groups",
    multiple=True,
    callback=_repeated_text,
    help="Quota group; repeat to match multiple groups.",
)
@click.option("--cpu-min", type=click.IntRange(min=0), help="Minimum CPU cores.")
@click.option("--cpu-max", type=click.IntRange(min=0), help="Maximum CPU cores.")
@click.option(
    "--memory-min", type=click.IntRange(min=0), help="Minimum memory in GiB."
)
@click.option(
    "--memory-max", type=click.IntRange(min=0), help="Maximum memory in GiB."
)
@click.option(
    "--creation-timestamp-min",
    type=click.IntRange(min=0),
    help="Minimum creation Unix timestamp in seconds.",
)
@click.option(
    "--creation-timestamp-max",
    type=click.IntRange(min=0),
    help="Maximum creation Unix timestamp in seconds.",
)
@click.option(
    "--close-timestamp-min",
    type=click.IntRange(min=0),
    help="Minimum close Unix timestamp in seconds.",
)
@click.option(
    "--close-timestamp-max",
    type=click.IntRange(min=0),
    help="Maximum close Unix timestamp in seconds.",
)
@click.option("--sort-by", help="Workspace API sort expression.")
@click.option("--limit", type=click.IntRange(min=1), help="Maximum results.")
@click.option("--offset", type=click.IntRange(min=0), help="Result offset.")
@click.pass_obj
def list_machines(
    context: Any,
    project: str | None,
    workspace_ids: list[str] | None,
    name: str | None,
    creator: str | None,
    share: str | None,
    quota_groups: list[str] | None,
    cpu_min: int | None,
    cpu_max: int | None,
    memory_min: int | None,
    memory_max: int | None,
    creation_timestamp_min: int | None,
    creation_timestamp_max: int | None,
    close_timestamp_min: int | None,
    close_timestamp_max: int | None,
    sort_by: str | None,
    limit: int | None,
    offset: int | None,
) -> None:
    """List YiCloud Workspace development machines."""
    _validate_range(cpu_min, cpu_max, "--cpu-min", "--cpu-max")
    _validate_range(memory_min, memory_max, "--memory-min", "--memory-max")
    _validate_range(
        creation_timestamp_min,
        creation_timestamp_max,
        "--creation-timestamp-min",
        "--creation-timestamp-max",
    )
    _validate_range(
        close_timestamp_min,
        close_timestamp_max,
        "--close-timestamp-min",
        "--close-timestamp-max",
    )
    request = models.ListWorkspacesReq(
        CPUMax=cpu_max,
        CPUMin=cpu_min,
        CloseTimestampMax=close_timestamp_max,
        CloseTimestampMin=close_timestamp_min,
        CreationTimestampMax=creation_timestamp_max,
        CreationTimestampMin=creation_timestamp_min,
        Creator=_optional_text(creator, "--creator"),
        Limit=limit,
        MemoryMax=memory_max,
        MemoryMin=memory_min,
        Name=_optional_text(name, "--name"),
        Offset=offset,
        Project=_optional_text(project, "--project"),
        QuotaGroup=quota_groups,
        Share=_optional_text(share, "--share"),
        SortBy=_optional_text(sort_by, "--sort-by"),
        WorkspaceId=workspace_ids,
    )
    response = _invoke(context, workspace.list_workspaces, request)
    items = [_workspace_view(item) for item in response.Items or []]
    if context.output_format is OutputFormat.JSON:
        context.write({"items": items, "total": response.Total or 0})
        return
    context.write(
        [
            {
                "workspace_id": item["workspace_id"],
                "name": item["name"],
                "phase": item["phase"],
                "cpu": item["resources"]["cpu"],
                "memory": item["resources"]["memory"],
                "gpu": item["resources"]["gpu"],
                "creator": item["creator"]["name"],
                "quota_group": item["quota_group"],
                "sku_id": item["sku"]["id"],
                "sku_pool": item["sku"]["pool_name"],
                "created_at": item["timestamps"]["created"],
                "updated_at": item["timestamps"]["updated"],
                "started_at": item["timestamps"]["started"],
                "stopped_at": item["timestamps"]["stopped"],
            }
            for item in items
        ]
    )


@click.command("inspect")
@click.option("--project", required=True, help="Project namespace.")
@click.argument("workspace_id")
@click.pass_obj
def inspect_machine(context: Any, project: str, workspace_id: str) -> None:
    """Inspect one YiCloud Workspace by Workspace ID."""
    request = models.GetWorkspaceReq(
        Project=_non_empty(project, "--project"),
        WorkspaceId=_non_empty(workspace_id, "WORKSPACE_ID"),
    )
    context.write(_workspace_view(_invoke(context, workspace.get_workspace, request)))


COMMANDS = (list_machines, inspect_machine)
