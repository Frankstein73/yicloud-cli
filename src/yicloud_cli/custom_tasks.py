"""Custom-task commands backed by the generated YiCloud job API."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, fields, is_dataclass
from typing import Any

import click
from yicloud.base.client import Client
from yicloud.services import job
from yicloud.services.job import actions, models

from .cli import CliContext, pass_cli_context


_CAMEL_WORD = re.compile(r"(.)([A-Z][a-z]+)")
_CAMEL_ACRONYM = re.compile(r"([a-z0-9])([A-Z])")
_TASK_SPEC_FIELDS = {field.name for field in fields(models.CreateJobReqTaskSpec)}


def _clean(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        raise click.BadParameter("must not be empty", param_hint=label)
    return value


def _optional_csv(values: tuple[str, ...]) -> str | None:
    cleaned = [_clean(value, "filter") for value in values]
    return ",".join(cleaned) if cleaned else None


def _snake_case(name: str) -> str:
    return _CAMEL_ACRONYM.sub(r"\1_\2", _CAMEL_WORD.sub(r"\1_\2", name)).lower()


_TASK_SPEC_KEYS = {_snake_case(name): name for name in _TASK_SPEC_FIELDS}


def _serializable(value: Any) -> Any:
    """Convert generated SDK models to stable CLI field names."""
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    if isinstance(value, dict):
        return {
            _snake_case(str(key)): _serializable(item) for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_serializable(item) for item in value]
    return value


def _parse_task_spec(value: str) -> tuple[str, models.CreateJobReqTaskSpec]:
    try:
        task_name, raw = value.split("=", 1)
    except ValueError:
        raise click.BadParameter(
            "must use NAME=JSON syntax", param_hint="--task-spec"
        ) from None
    task_name = _clean(task_name, "--task-spec")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise click.BadParameter(
            f"contains invalid JSON: {error.msg}", param_hint="--task-spec"
        ) from None
    if not isinstance(payload, dict):
        raise click.BadParameter(
            "JSON value must be an object", param_hint="--task-spec"
        )

    unknown = sorted(set(payload) - set(_TASK_SPEC_KEYS))
    if unknown:
        raise click.BadParameter(
            f"unknown field(s): {', '.join(unknown)}", param_hint="--task-spec"
        )
    converted = {_TASK_SPEC_KEYS[key]: item for key, item in payload.items()}
    image = converted.get("Image")
    command = converted.get("Command")
    replicas = converted.get("Replicas")
    environment = converted.setdefault("Env", {})
    if not isinstance(image, str) or not image.strip():
        raise click.BadParameter(
            "field 'image' must be a non-empty string", param_hint="--task-spec"
        )
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(item, str) and item for item in command)
    ):
        raise click.BadParameter(
            "field 'command' must be a non-empty string array",
            param_hint="--task-spec",
        )
    if not isinstance(replicas, int) or isinstance(replicas, bool) or replicas < 1:
        raise click.BadParameter(
            "field 'replicas' must be a positive integer", param_hint="--task-spec"
        )
    if not isinstance(environment, dict) or not all(
        isinstance(key, str) and isinstance(item, str)
        for key, item in environment.items()
    ):
        raise click.BadParameter(
            "field 'env' must be a string-to-string object",
            param_hint="--task-spec",
        )
    try:
        return task_name, models.CreateJobReqTaskSpec(**converted)
    except TypeError as error:
        raise click.BadParameter(str(error), param_hint="--task-spec") from None


def _task_specs(values: tuple[str, ...]) -> dict[str, models.CreateJobReqTaskSpec]:
    parsed: dict[str, models.CreateJobReqTaskSpec] = {}
    for value in values:
        name, spec = _parse_task_spec(value)
        if name in parsed:
            raise click.BadParameter(
                f"duplicate task name '{name}'", param_hint="--task-spec"
            )
        parsed[name] = spec
    return parsed


class CustomTaskService:
    """Small adapter around generated module actions and their bound client."""

    def __init__(self, client: Client):
        self.client = client

    def _bind(self) -> None:
        job.use_client(self.client)

    def create(self, request: models.CreateJobReq) -> Any:
        self._bind()
        return actions.create_job(None, request)

    def list(self, request: models.ListJobsReq) -> Any:
        self._bind()
        return actions.list_jobs(None, request)

    def inspect(self, request: models.GetJobReq) -> Any:
        self._bind()
        return actions.get_job(None, request)

    def update(self, request: models.EditJobReq) -> None:
        self._bind()
        actions.edit_job(None, request)

    def cancel(self, request: models.BatchStopJobsReq) -> Any:
        self._bind()
        return actions.batch_stop_jobs(None, request)

    def delete(self, request: models.BatchDeleteJobsReq) -> None:
        self._bind()
        actions.batch_delete_jobs(None, request)

    def clone(self, request: models.CloneJobReq) -> Any:
        self._bind()
        return actions.clone_job(None, request)


@click.command("create")
@click.option("--name", required=True, help="Task display name.")
@click.option("--project", required=True, help="YiCloud project name.")
@click.option(
    "--task-spec",
    "task_spec_values",
    multiple=True,
    required=True,
    metavar="NAME=JSON",
    help="Task specification; repeat for multiple named task roles.",
)
@click.option("--job-type", type=click.Choice(["normal", "idle"]))
@click.option("--priority", type=click.IntRange(1, 9))
@click.option("--auto-delete-duration")
@click.option("--backoff-limit", type=click.IntRange(min=0))
@click.option("--quota-group")
@click.option("--qos")
@pass_cli_context
def create_task(
    context: CliContext,
    name: str,
    project: str,
    task_spec_values: tuple[str, ...],
    job_type: str | None,
    priority: int | None,
    auto_delete_duration: str | None,
    backoff_limit: int | None,
    quota_group: str | None,
    qos: str | None,
) -> None:
    """Create a custom task."""
    request = models.CreateJobReq(
        Name=_clean(name, "--name"),
        Project=_clean(project, "--project"),
        TaskSpecs=_task_specs(task_spec_values),
        JobType=job_type,
        Priority=str(priority) if priority is not None else None,
        AutoDeleteDuration=auto_delete_duration,
        BackoffLimit=backoff_limit,
        QuotaGroup=quota_group,
        Qos=qos,
    )
    context.write(_serializable(context.custom_tasks.create(request)))


@click.command("list")
@click.option("--project", required=True, help="YiCloud project name.")
@click.option("--creator", "creators", multiple=True)
@click.option("--task-id", "task_ids", multiple=True)
@click.option("--name", "names", multiple=True)
@click.option("--phase", "phases", multiple=True)
@click.option("--quota-group", "quota_groups", multiple=True)
@click.option("--job-type", type=click.Choice(["normal", "idle"]))
@click.option("--mine/--all", "mine", default=None)
@click.option("--sort-by")
@click.option("--limit", type=click.IntRange(1, 100))
@click.option("--offset", type=click.IntRange(min=0))
@pass_cli_context
def list_tasks(
    context: CliContext,
    project: str,
    creators: tuple[str, ...],
    task_ids: tuple[str, ...],
    names: tuple[str, ...],
    phases: tuple[str, ...],
    quota_groups: tuple[str, ...],
    job_type: str | None,
    mine: bool | None,
    sort_by: str | None,
    limit: int | None,
    offset: int | None,
) -> None:
    """List custom tasks in a project."""
    request = models.ListJobsReq(
        Project=_clean(project, "--project"),
        Creators=_optional_csv(creators),
        JobIds=_optional_csv(task_ids),
        JobNames=_optional_csv(names),
        Phases=_optional_csv(phases),
        QuotaGroup=_optional_csv(quota_groups),
        JobType=job_type,
        Self=mine,
        SortBy=sort_by,
        Limit=limit,
        Offset=offset,
    )
    response = context.custom_tasks.list(request)
    items = getattr(response, "Items", None) if response is not None else None
    context.write(_serializable(items or []))


@click.command("inspect")
@click.argument("task_id")
@click.option("--project", required=True, help="YiCloud project name.")
@pass_cli_context
def inspect_task(context: CliContext, task_id: str, project: str) -> None:
    """Inspect one custom task by identifier."""
    request = models.GetJobReq(
        JobId=_clean(task_id, "TASK_ID"), Project=_clean(project, "--project")
    )
    context.write(_serializable(context.custom_tasks.inspect(request)))


@click.command("update")
@click.argument("task_id")
@click.option("--project", required=True, help="YiCloud project name.")
@click.option("--priority", type=click.IntRange(1, 9))
@click.option("--top/--no-top", default=None, help="Set or remove queue pinning.")
@pass_cli_context
def update_task(
    context: CliContext,
    task_id: str,
    project: str,
    priority: int | None,
    top: bool | None,
) -> None:
    """Update task priority or queue pinning."""
    if (priority is None) == (top is None):
        raise click.UsageError("provide exactly one of --priority or --top/--no-top")
    request = models.EditJobReq(
        Operation="priority" if priority is not None else "top",
        Project=_clean(project, "--project"),
        JobId=_clean(task_id, "TASK_ID"),
        Priority=str(priority) if priority is not None else None,
        TopAction=("set" if top else "unset") if top is not None else None,
    )
    context.custom_tasks.update(request)
    context.write({"status": "updated", "task_id": task_id})


def _resources(
    task_ids: tuple[str, ...], project: str, resource_type: type[Any]
) -> list[Any]:
    clean_project = _clean(project, "--project")
    return [
        resource_type(JobId=_clean(task_id, "TASK_ID"), Project=clean_project)
        for task_id in task_ids
    ]


@click.command("cancel")
@click.argument("task_ids", nargs=-1, required=True)
@click.option("--project", required=True, help="YiCloud project name.")
@pass_cli_context
def cancel_tasks(context: CliContext, task_ids: tuple[str, ...], project: str) -> None:
    """Cancel one or more custom tasks."""
    request = models.BatchStopJobsReq(
        Resources=_resources(
            task_ids, project, models.BatchStopJobsReqResourceIdentifier
        )
    )
    response = _serializable(context.custom_tasks.cancel(request))
    result = {"status": "cancelled", "task_ids": list(task_ids)}
    if response:
        result["result"] = response
    context.write(result)


@click.command("delete")
@click.argument("task_ids", nargs=-1, required=True)
@click.option("--project", required=True, help="YiCloud project name.")
@click.confirmation_option(prompt="Delete the selected custom tasks?")
@pass_cli_context
def delete_tasks(context: CliContext, task_ids: tuple[str, ...], project: str) -> None:
    """Delete one or more custom tasks."""
    request = models.BatchDeleteJobsReq(
        Resources=_resources(
            task_ids, project, models.BatchDeleteJobsReqResourceIdentifier
        )
    )
    context.custom_tasks.delete(request)
    context.write({"status": "deleted", "task_ids": list(task_ids)})


@click.command("clone")
@click.argument("task_id")
@click.option("--project", required=True, help="YiCloud project name.")
@click.option("--target-name", required=True, help="Display name for the cloned task.")
@pass_cli_context
def clone_task(
    context: CliContext, task_id: str, project: str, target_name: str
) -> None:
    """Clone an existing custom task."""
    request = models.CloneJobReq(
        JobId=_clean(task_id, "TASK_ID"),
        Project=_clean(project, "--project"),
        TargetName=_clean(target_name, "--target-name"),
    )
    context.write(_serializable(context.custom_tasks.clone(request)))


custom_task_commands = (
    create_task,
    list_tasks,
    inspect_task,
    update_task,
    cancel_tasks,
    delete_tasks,
    clone_task,
)
