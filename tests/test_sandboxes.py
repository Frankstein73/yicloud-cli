import json

import pytest
import requests_mock
from click.testing import CliRunner
from yicloud.base.errs import ServerException
from yicloud.services import sandbox
from yicloud.services.sandbox import models

from yicloud_cli.auth import ACCESS_KEY_ENV, SECRET_KEY_ENV
from yicloud_cli.cli import create_cli


ENVIRONMENT = {
    ACCESS_KEY_ENV: "development-machine-access-key",
    SECRET_KEY_ENV: "development-machine-secret-key",
}


def invoke(arguments, **kwargs):
    return CliRunner().invoke(create_cli(environ=ENVIRONMENT), arguments, **kwargs)


def test_sandbox_help_lists_the_complete_sdk_sandbox_lifecycle():
    result = invoke(["sandbox", "--help"])

    assert result.exit_code == 0
    for command in (
        "create",
        "list",
        "inspect",
        "stop",
        "delete",
        "batch-delete",
        "update-lifecycle",
    ):
        assert command in result.output
    assert "restart" not in result.output


@pytest.mark.parametrize(
    "arguments,message",
    [
        (["create", "--project", "demo"], "provide exactly one"),
        (
            [
                "create",
                "--project",
                "demo",
                "--environment-id",
                "env-1",
                "--image-ref",
                "image:tag",
            ],
            "provide exactly one",
        ),
        (
            ["create", "--project", "demo", "--image-ref", "image:tag"],
            "requires --cpu and --memory",
        ),
        (
            ["create", "--project", "demo", "--image-ref", "image:tag", "--cpu", "2"],
            "--cpu and --memory must be provided together",
        ),
        (
            [
                "create",
                "--project",
                "demo",
                "--environment-id",
                "env-1",
                "--port",
                "70000",
            ],
            "between 1 and 65535",
        ),
        (
            [
                "create",
                "--project",
                "demo",
                "--environment-id",
                "env-1",
                "--env",
                "INVALID",
            ],
            "must use KEY=VALUE",
        ),
        (
            [
                "create",
                "--project",
                "demo",
                "--environment-id",
                "env-1",
                "--volume",
                "{}",
            ],
            "non-empty mount_path",
        ),
        (
            ["list", "--project", "demo", "--created-after", "2026-07-21"],
            "RFC3339 timestamp with a timezone",
        ),
        (
            [
                "list",
                "--project",
                "demo",
                "--created-after",
                "2026-07-22T00:00:00Z",
                "--created-before",
                "2026-07-21T00:00:00Z",
            ],
            "--created-after must not be later",
        ),
        (
            ["list", "--project", "demo", "--environment-ids", "env-1,,env-2"],
            "comma-separated list of non-empty values",
        ),
        (
            [
                "update-lifecycle",
                "--project",
                "demo",
                "machine-1",
                "--mode",
                "set",
                "--minutes",
                "0",
            ],
            "0 is not in the range",
        ),
    ],
)
def test_invalid_arguments_are_rejected_before_client_construction(arguments, message):
    calls = []
    application = create_cli(
        environ=ENVIRONMENT,
        client_factory=lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    result = CliRunner().invoke(application, ["sandbox", *arguments])

    assert result.exit_code == 2
    assert message in result.output
    assert calls == []


def test_create_constructs_the_openapi_request(monkeypatch):
    captured = {}

    def create(_ctx, request):
        captured["request"] = request
        return models.CreateSandboxData(Id="machine-1", Type="code")

    monkeypatch.setattr(sandbox, "create_sandbox", create)
    result = invoke(
        [
            "--output",
            "json",
            "sandbox",
            "create",
            "--project",
            "demo",
            "--image-ref",
            "team/image:latest",
            "--image-username",
            "registry-user",
            "--cpu",
            "2",
            "--memory",
            "4Gi",
            "--name",
            "dev",
            "--entrypoint",
            "python",
            "--entrypoint=-m",
            "--entrypoint",
            "http.server",
            "--env",
            "MODE=dev",
            "--port",
            "8080:http:web",
            "--volume",
            '{"mount_path":"/data","read_only":true,"pvc":{"claim_name":"workspace"}}',
            "--lifecycle-minutes",
            "120",
        ]
    )

    assert result.exit_code == 0, result.output
    request = captured["request"]
    assert request.ProjectName == "demo"
    assert request.Name == "dev"
    assert request.Image.Ref == "team/image:latest"
    assert request.Image.Auth.Username == "registry-user"
    assert request.Resources == models.CreateSandboxReqResources(Cpu="2", Memory="4Gi")
    assert request.Entrypoint == ["python", "-m", "http.server"]
    assert request.Env == {"MODE": "dev"}
    assert request.Ports == [
        models.CreateSandboxReqPort(ContainerPort=8080, Name="http", Purpose="web")
    ]
    assert request.Volumes[0].Pvc.ClaimName == "workspace"
    assert request.Volumes[0].ReadOnly is True
    assert json.loads(result.output)["id"] == "machine-1"


def test_list_constructs_filters_and_renders_stable_human_table(monkeypatch):
    captured = {}

    def list_sandboxes(_ctx, request):
        captured["request"] = request
        return models.ListSandboxesData(
            Items=[
                models.GetSandboxData(
                    Id="machine-1",
                    Name="dev",
                    RunState="running",
                    Type="code",
                    CreatedAt="2026-07-21T12:00:00Z",
                    ExpiresAt="2026-07-21T14:00:00Z",
                )
            ],
            Total=1,
        )

    monkeypatch.setattr(sandbox, "list_sandboxes", list_sandboxes)
    result = invoke(
        [
            "sandbox",
            "list",
            "--project",
            "demo",
            "--run-state",
            "running",
            "--allocation-mode",
            "manual",
            "--created-after",
            "2026-07-21T00:00:00Z",
            "--self-only",
            "--limit",
            "20",
        ]
    )

    assert result.exit_code == 0, result.output
    request = captured["request"]
    assert request.RunState == "running"
    assert request.AllocationMode == "manual"
    assert request.CreatedAfter == "2026-07-21T00:00:00Z"
    assert request.Self is True
    assert request.Limit == 20
    assert "machine-1" in result.output
    assert "running" in result.output
    assert "total" not in result.output.lower()


@pytest.mark.parametrize(
    "command,action_name,request_type",
    [
        (
            ["inspect", "--project", "demo", "machine-1"],
            "get_sandbox",
            models.GetSandboxReq,
        ),
        (
            ["stop", "--project", "demo", "machine-1"],
            "stop_sandbox",
            models.StopSandboxReq,
        ),
        (
            ["delete", "--project", "demo", "machine-1"],
            "delete_sandbox",
            models.DeleteSandboxReq,
        ),
        (
            [
                "update-lifecycle",
                "--project",
                "demo",
                "machine-1",
                "--mode",
                "extend",
                "--minutes",
                "60",
            ],
            "update_sandbox_lifecycle",
            models.UpdateSandboxLifecycleReq,
        ),
    ],
)
def test_identifier_lifecycle_commands_construct_requests(
    monkeypatch, command, action_name, request_type
):
    captured = {}

    def action(_ctx, request):
        captured["request"] = request
        if action_name == "get_sandbox":
            return models.GetSandboxData(Id="machine-1", RunState="running")
        if action_name == "update_sandbox_lifecycle":
            return models.UpdateSandboxLifecycleData(
                LifecycleMinutes=60, ExpireAt="later"
            )
        return None

    monkeypatch.setattr(sandbox, action_name, action)
    result = invoke(["--output", "json", "sandbox", *command])

    assert result.exit_code == 0, result.output
    assert isinstance(captured["request"], request_type)
    assert captured["request"].ProjectName == "demo"
    assert captured["request"].SandboxId == "machine-1"


def test_batch_delete_validates_and_constructs_request(monkeypatch):
    captured = {}

    def batch_delete(_ctx, request):
        captured["request"] = request
        return models.BatchDeleteSandboxesData(Succeeded=request.Ids, Failed=[])

    monkeypatch.setattr(sandbox, "batch_delete_sandboxes", batch_delete)
    result = invoke(
        [
            "--output",
            "json",
            "sandbox",
            "batch-delete",
            "--project",
            "demo",
            "one",
            "two",
        ]
    )

    assert result.exit_code == 0, result.output
    assert captured["request"] == models.BatchDeleteSandboxesReq(
        Ids=["one", "two"], ProjectName="demo"
    )
    assert json.loads(result.output) == {"failed": [], "succeeded": ["one", "two"]}


def test_sdk_api_errors_are_mapped_and_credentials_are_redacted(monkeypatch):
    def get_sandbox(_ctx, _request):
        raise ServerException(
            "GetSandbox",
            status_code=403,
            ret_code=1007,
            message=f"denied token={ENVIRONMENT[SECRET_KEY_ENV]}",
        )

    monkeypatch.setattr(sandbox, "get_sandbox", get_sandbox)
    result = invoke(
        ["sandbox", "inspect", "--project", "demo", "machine-1"]
    )

    assert result.exit_code == 1
    assert "API request failed (HTTP 403, code 1007)" in result.output
    assert "token=[REDACTED]" in result.output
    assert ENVIRONMENT[SECRET_KEY_ENV] not in result.output


@pytest.mark.parametrize(
    "command,path,method,response,expected_request",
    [
        (
            [
                "create",
                "--project",
                "demo",
                "--environment-id",
                "env-1",
                "--name",
                "dev",
            ],
            "/sandbox/v1alpha1/CreateSandbox",
            "POST",
            {"Code": 0, "Msg": "ok", "Data": {"Id": "machine-1", "Name": "dev"}},
            {"ProjectName": "demo", "EnvironmentId": "env-1", "Name": "dev"},
        ),
        (
            ["list", "--project", "demo", "--run-state", "running"],
            "/sandbox/v1alpha1/ListSandboxes",
            "GET",
            {
                "Code": 0,
                "Msg": "ok",
                "Data": {
                    "Items": [{"Id": "machine-1", "RunState": "running"}],
                    "Total": 1,
                },
            },
            None,
        ),
        (
            ["inspect", "--project", "demo", "machine-1"],
            "/sandbox/v1alpha1/GetSandbox",
            "GET",
            {
                "Code": 0,
                "Msg": "ok",
                "Data": {"Id": "machine-1", "RunState": "running"},
            },
            None,
        ),
        (
            ["stop", "--project", "demo", "machine-1"],
            "/sandbox/v1alpha1/StopSandbox",
            "POST",
            {"Code": 0, "Msg": "ok"},
            {"ProjectName": "demo", "SandboxId": "machine-1"},
        ),
        (
            ["delete", "--project", "demo", "machine-1"],
            "/sandbox/v1alpha1/DeleteSandbox",
            "POST",
            {"Code": 0, "Msg": "ok"},
            {"ProjectName": "demo", "SandboxId": "machine-1"},
        ),
        (
            ["batch-delete", "--project", "demo", "machine-1", "machine-2"],
            "/sandbox/v1alpha1/BatchDeleteSandboxes",
            "POST",
            {
                "Code": 0,
                "Msg": "ok",
                "Data": {"Succeeded": ["machine-1", "machine-2"], "Failed": []},
            },
            {"ProjectName": "demo", "Ids": ["machine-1", "machine-2"]},
        ),
        (
            [
                "update-lifecycle",
                "--project",
                "demo",
                "machine-1",
                "--mode",
                "extend",
                "--minutes",
                "30",
            ],
            "/sandbox/v1alpha1/UpdateSandboxLifecycle",
            "POST",
            {
                "Code": 0,
                "Msg": "ok",
                "Data": {"LifecycleMinutes": 30, "ExpireAt": "later"},
            },
            {
                "ProjectName": "demo",
                "SandboxId": "machine-1",
                "Mode": "extend",
                "LifecycleMinutes": 30,
            },
        ),
    ],
)
def test_mocked_sdk_transport_for_every_supported_sandbox_operation(
    command, path, method, response, expected_request
):
    url = f"https://gate.yicloud.com{path}"
    with requests_mock.Mocker() as mock:
        mock.register_uri(method, url, json=response)
        result = invoke(["--output", "json", "sandbox", *command])

        assert result.exit_code == 0, result.output
        request = mock.last_request
        assert request is not None
        if expected_request is not None:
            assert request.json() == expected_request
        else:
            assert request.qs["projectname"] == ["demo"]
            if command[0] == "list":
                assert request.qs["runstate"] == ["running"]
            else:
                assert request.qs["sandboxid"] == ["machine-1"]


def test_legacy_mutating_development_machine_alias_is_hidden_and_deprecated(
    monkeypatch,
):
    def stop_sandbox(_ctx, request):
        assert request == models.StopSandboxReq(
            ProjectName="demo", SandboxId="sandbox-1"
        )

    monkeypatch.setattr(sandbox, "stop_sandbox", stop_sandbox)
    help_result = invoke(["development-machine", "--help"])
    result = invoke(
        ["development-machine", "stop", "--project", "demo", "sandbox-1"]
    )

    assert help_result.exit_code == 0
    assert "stop" not in help_result.output
    assert result.exit_code == 0, result.output
    assert "deprecated" in result.output.lower()
    assert "yicloud sandbox stop" in result.output


def test_development_machine_list_is_not_a_sandbox_compatibility_alias(monkeypatch):
    calls = []
    monkeypatch.setattr(
        sandbox,
        "list_sandboxes",
        lambda *_args: calls.append(_args),
    )
    result = invoke(["development-machine", "list", "--project", "demo"])

    assert result.exit_code != 0
    assert calls == []
