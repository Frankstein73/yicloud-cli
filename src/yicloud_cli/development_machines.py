"""Development-machine commands backed by the YiCloud Workspace OpenAPI."""

from __future__ import annotations

import re
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import click
import yaml
from yicloud.services import workspace
from yicloud.services.workspace import models

from .output import OutputFormat


class _CommaSeparatedQueryValues(list[str]):
    """Keep SDK list semantics while producing its expected query representation."""

    def __str__(self) -> str:
        return ",".join(self)


_STORAGE_QUANTITY = re.compile(
    r"^(?:0*[1-9]\d*)(?:\.\d+)?(?:[EPTGMK]i?|[eE][+-]?\d+)?$"
)
_CPU_QUANTITY = re.compile(r"^(?:0*[1-9]\d*)(?:\.\d+)?(?:m|[eE][+-]?\d+)?$")
_GPU_QUANTITY = re.compile(r"^(?:0|0*[1-9]\d*)(?:\.\d+)?$")
_RUNTIME_MODES = ("kata", "kubebrain")


def _non_empty(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        raise click.BadParameter("must not be empty", param_hint=label)
    return value


def _optional_text(value: str | None, label: str) -> str | None:
    return _non_empty(value, label) if value is not None else None


def _quantity(value: str | None, label: str, pattern: re.Pattern[str]) -> str | None:
    value = _optional_text(value, label)
    if value is not None and not pattern.fullmatch(value):
        raise click.BadParameter(
            "must be a positive Kubernetes resource quantity", param_hint=label
        )
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


def _gpfs_volume(
    _ctx: click.Context, param: click.Parameter, values: tuple[str, ...]
) -> list[models.CreateWorkspaceReqMountGpfsVolume] | None:
    if not values:
        return None
    result = []
    targets = set()
    for value in values:
        source, separator, target = value.partition("=")
        source = source.strip()
        target = target.strip()
        if not separator or not source or not target:
            raise click.BadParameter("must use SOURCE=TARGET", param=param)
        if not source.startswith("gpfs://"):
            raise click.BadParameter("SOURCE must start with gpfs://", param=param)
        if not target.startswith("/"):
            raise click.BadParameter("TARGET must be an absolute path", param=param)
        if target in targets:
            raise click.BadParameter(
                f"contains duplicate target {target!r}", param=param
            )
        targets.add(target)
        result.append(
            models.CreateWorkspaceReqMountGpfsVolume(
                Source=source,
                Target=target,
            )
        )
    return result


def _disk_file(
    _ctx: click.Context, param: click.Parameter, value: str | None
) -> models.CreateWorkspaceReqDiskInput | None:
    if value is None:
        return None
    path = Path(value)
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise click.BadParameter(f"could not read file: {error}", param=param) from None
    except yaml.YAMLError as error:
        raise click.BadParameter(
            f"must contain valid JSON or YAML: {error}", param=param
        ) from None
    if not isinstance(payload, dict):
        raise click.BadParameter("must contain one disk object", param=param)

    item = {_snake_case(str(key)): value for key, value in payload.items()}
    allowed = {
        "name",
        "data_source",
        "data_source_type",
        "storage",
        "storage_class_name",
    }
    unknown = sorted(set(item) - allowed)
    if unknown:
        raise click.BadParameter(
            f"contains unsupported field(s): {', '.join(unknown)}", param=param
        )

    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        raise click.BadParameter("name must be a non-empty string", param=param)
    name = name.strip()

    storage = item.get("storage")
    if storage is not None:
        if not isinstance(storage, str) or not _STORAGE_QUANTITY.fullmatch(
            storage.strip()
        ):
            raise click.BadParameter(
                "storage must be a positive Kubernetes quantity such as 50Gi",
                param=param,
            )
        storage = storage.strip()

    storage_class = item.get("storage_class_name")
    if storage_class is not None:
        if not isinstance(storage_class, str) or not storage_class.strip():
            raise click.BadParameter(
                "storage_class_name must be a non-empty string", param=param
            )
        storage_class = storage_class.strip()

    data_source_type = item.get("data_source_type")
    if data_source_type is not None:
        if not isinstance(data_source_type, str):
            raise click.BadParameter(
                "data_source_type must be default or clone", param=param
            )
        data_source_type = data_source_type.strip().lower()
        if data_source_type not in {"default", "clone"}:
            raise click.BadParameter(
                "data_source_type must be default or clone", param=param
            )

    source_payload = item.get("data_source")
    source = None
    source_kind = None
    if source_payload is not None:
        if not isinstance(source_payload, dict):
            raise click.BadParameter("data_source must be an object", param=param)
        source_item = {
            _snake_case(str(key)): source_value
            for key, source_value in source_payload.items()
        }
        source_unknown = sorted(set(source_item) - {"api_group", "kind", "name"})
        if source_unknown:
            raise click.BadParameter(
                "data_source contains unsupported field(s): "
                + ", ".join(source_unknown),
                param=param,
            )
        for field in ("kind", "name"):
            field_value = source_item.get(field)
            if not isinstance(field_value, str) or not field_value.strip():
                raise click.BadParameter(
                    f"data_source.{field} must be a non-empty string", param=param
                )
            source_item[field] = field_value.strip()
        api_group = source_item.get("api_group")
        if api_group is not None:
            if not isinstance(api_group, str) or not api_group.strip():
                raise click.BadParameter(
                    "data_source.api_group must be a non-empty string", param=param
                )
            api_group = api_group.strip()
        source_kind = source_item["kind"].lower()
        source = models.CreateWorkspaceReqDataSource(
            ApiGroup=api_group,
            Kind=source_item["kind"],
            Name=source_item["name"],
        )

    if data_source_type == "clone":
        if source is None:
            raise click.BadParameter(
                "clone disks require data_source", param=param
            )
        if source_kind == "image":
            raise click.BadParameter(
                "clone disks cannot use an Image data source", param=param
            )
    elif source_kind not in {None, "image", "volume"}:
        raise click.BadParameter(
            "non-clone data_source.kind must be Image or Volume", param=param
        )

    is_new_disk = source is None or source_kind == "image"
    if is_new_disk and storage is None:
        raise click.BadParameter(
            "new and Image-backed disks require storage", param=param
        )
    return models.CreateWorkspaceReqDiskInput(
        Name=name,
        DataSource=source,
        DataSourceType=data_source_type,
        Storage=storage,
        StorageClassName=storage_class,
    )


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


@click.command("create")
@click.option("--name", required=True, help="Workspace name.")
@click.option("--project", help="Project namespace.")
@click.option("--description", help="Workspace description.")
@click.option(
    "--env",
    "environment",
    multiple=True,
    callback=_key_value,
    metavar="KEY=VALUE",
    help="Environment variable; repeatable.",
)
@click.option("--image", help="Workspace container image.")
@click.option(
    "--use-private-machine/--no-use-private-machine",
    default=None,
    help="Select dedicated private-machine capacity.",
)
@click.option(
    "--runtime-mode",
    type=click.Choice(_RUNTIME_MODES, case_sensitive=False),
    help="Quota-mode runtime.",
)
@click.option("--cpu", help="Quota-mode CPU quantity, for example 4 or 500m.")
@click.option("--memory", help="Quota-mode memory quantity, for example 16Gi.")
@click.option("--gpu", help="Quota-mode GPU quantity, for example 1.")
@click.option("--quota-group", help="Quota-mode quota group.")
@click.option("--sku-id", help="SKU-mode specification ID.")
@click.option("--sku-public", is_flag=True, help="Use a public SKU pool.")
@click.option("--sku-private", is_flag=True, help="Use a private SKU pool.")
@click.option("--sku-tenant", is_flag=True, help="Use a tenant-level private SKU.")
@click.option("--sku-project", is_flag=True, help="Use a project-level private SKU.")
@click.option(
    "--system-disk",
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    callback=_disk_file,
    metavar="JSON_OR_YAML_FILE",
    help="System-disk object loaded from a reusable JSON or YAML file.",
)
@click.option(
    "--data-disk",
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    callback=_disk_file,
    metavar="JSON_OR_YAML_FILE",
    help="Data-disk object loaded from a reusable JSON or YAML file.",
)
@click.option("--mount-gpfs", help="Raw YiCloud GPFS mount string.")
@click.option(
    "--gpfs-volume",
    "gpfs_volumes",
    multiple=True,
    callback=_gpfs_volume,
    metavar="SOURCE=TARGET",
    help="Structured GPFS mount; repeatable.",
)
@click.pass_obj
def create_machine(
    context: Any,
    name: str,
    project: str | None,
    description: str | None,
    environment: dict[str, str] | None,
    image: str | None,
    use_private_machine: bool | None,
    runtime_mode: str | None,
    cpu: str | None,
    memory: str | None,
    gpu: str | None,
    quota_group: str | None,
    sku_id: str | None,
    sku_public: bool,
    sku_private: bool,
    sku_tenant: bool,
    sku_project: bool,
    system_disk: models.CreateWorkspaceReqDiskInput | None,
    data_disk: models.CreateWorkspaceReqDiskInput | None,
    mount_gpfs: str | None,
    gpfs_volumes: list[models.CreateWorkspaceReqMountGpfsVolume] | None,
) -> None:
    """Create a YiCloud Workspace development machine."""
    name = _non_empty(name, "--name")
    project = _optional_text(project, "--project")
    description = _optional_text(description, "--description")
    image = _optional_text(image, "--image")
    runtime_mode = _optional_text(runtime_mode, "--runtime-mode")
    cpu = _quantity(cpu, "--cpu", _CPU_QUANTITY)
    memory = _quantity(memory, "--memory", _STORAGE_QUANTITY)
    gpu = _quantity(gpu, "--gpu", _GPU_QUANTITY)
    quota_group = _optional_text(quota_group, "--quota-group")
    sku_id = _optional_text(sku_id, "--sku-id")
    mount_gpfs = _optional_text(mount_gpfs, "--mount-gpfs")

    quota_values = {
        "--runtime-mode": runtime_mode,
        "--cpu": cpu,
        "--memory": memory,
        "--gpu": gpu,
        "--quota-group": quota_group,
    }
    sku_selected = bool(
        sku_id or sku_public or sku_private or sku_tenant or sku_project
    )
    quota_selected = any(value is not None for value in quota_values.values())
    if sku_selected and quota_selected:
        raise click.UsageError("quota-mode and SKU-mode options are mutually exclusive")
    if not sku_selected:
        required = [
            option
            for option in ("--runtime-mode", "--cpu", "--memory", "--quota-group")
            if quota_values[option] is None
        ]
        if required:
            raise click.UsageError("quota mode requires " + ", ".join(required))
    else:
        if sku_id is None:
            raise click.UsageError("SKU mode requires --sku-id")
        if sku_public == sku_private:
            raise click.UsageError(
                "SKU mode requires exactly one of --sku-public or --sku-private"
            )
        if sku_public and (sku_tenant or sku_project):
            raise click.UsageError(
                "public SKU mode cannot use --sku-tenant or --sku-project"
            )
        if sku_private and sku_tenant == sku_project:
            raise click.UsageError(
                "private SKU mode requires exactly one of --sku-tenant or --sku-project"
            )

    request = models.CreateWorkspaceReq(
        Name=name,
        CPU=cpu,
        DataDisk=data_disk,
        Description=description,
        Env=environment,
        GPU=gpu,
        Image=image,
        Memory=memory,
        MountGPFS=mount_gpfs,
        MountGpfsVolumes=gpfs_volumes,
        Project=project,
        QuotaGroup=quota_group,
        RuntimeMode=runtime_mode.lower() if runtime_mode else None,
        SkuId=sku_id,
        SkuPrivate=sku_private if sku_selected else None,
        SkuProject=sku_project if sku_selected else None,
        SkuPublic=sku_public if sku_selected else None,
        SkuTenant=sku_tenant if sku_selected else None,
        SystemDisk=system_disk,
        UsePrivateMachine=use_private_machine,
    )
    context.write(_workspace_view(_invoke(context, workspace.create_workspace, request)))


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


COMMANDS = (create_machine, list_machines, inspect_machine)
