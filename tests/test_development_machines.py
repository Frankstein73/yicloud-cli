import json

import pytest
import requests_mock
from click.testing import CliRunner
from yicloud.services import workspace
from yicloud.services.workspace import models

from yicloud_cli.auth import ACCESS_KEY_ENV, SECRET_KEY_ENV
from yicloud_cli.cli import create_cli


ENVIRONMENT = {
    ACCESS_KEY_ENV: "development-machine-access-key",
    SECRET_KEY_ENV: "development-machine-secret-key",
}


def invoke(arguments):
    return CliRunner().invoke(create_cli(environ=ENVIRONMENT), arguments)


def workspace_data(**overrides):
    values = {
        "WorkspaceId": "workspace-1",
        "Uid": "uid-1",
        "Project": "demo",
        "Name": "notebook",
        "Phase": "Running",
        "CPU": "4",
        "Memory": "16Gi",
        "GPU": "1",
        "WorkerCount": 2,
        "Creator": "alice",
        "CreatorId": "user-1",
        "RealCreator": "alice",
        "RealCreatorId": "user-1",
        "QuotaGroup": "research",
        "SkuId": "sku-a100",
        "SkuPoolName": "gpu-pool",
        "SkuPoolType": "gpu",
        "SkuResourceScope": "SkuPublic",
        "SkuPublic": True,
        "CreationTime": "2026-07-21T10:00:00Z",
        "UpdateTime": "2026-07-21T10:10:00Z",
        "StartTimestamp": "2026-07-21T10:01:00Z",
        "StopTimestamp": "",
    }
    values.update(overrides)
    return models.GetWorkspaceData(**values)


def test_development_machine_help_exposes_workspace_reads_only():
    result = invoke(["development-machine", "--help"])

    assert result.exit_code == 0
    assert "Workspace" in result.output
    assert "list" in result.output
    assert "inspect" in result.output
    for sandbox_command in (
        "create",
        "stop",
        "delete",
        "batch-delete",
        "update-lifecycle",
    ):
        assert sandbox_command not in result.output


@pytest.mark.parametrize(
    "arguments,message",
    [
        (["list", "--cpu-min", "8", "--cpu-max", "4"], "--cpu-min"),
        (
            ["list", "--memory-min", "32", "--memory-max", "16"],
            "--memory-min",
        ),
        (
            [
                "list",
                "--creation-timestamp-min",
                "200",
                "--creation-timestamp-max",
                "100",
            ],
            "--creation-timestamp-min",
        ),
        (
            [
                "list",
                "--close-timestamp-min",
                "200",
                "--close-timestamp-max",
                "100",
            ],
            "--close-timestamp-min",
        ),
        (["list", "--workspace-id", "   "], "must not be empty"),
        (["list", "--quota-group", "   "], "must not be empty"),
        (["list", "--limit", "0"], "0 is not in the range"),
        (["inspect", "--project", "   ", "workspace-1"], "must not be empty"),
    ],
)
def test_invalid_workspace_filters_are_rejected_before_client_construction(
    arguments, message
):
    calls = []
    application = create_cli(
        environ=ENVIRONMENT,
        client_factory=lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    result = CliRunner().invoke(application, ["development-machine", *arguments])

    assert result.exit_code == 2
    assert message in result.output
    assert calls == []


def test_list_constructs_all_official_workspace_filters_and_human_output(monkeypatch):
    captured = {}

    def list_workspaces(_ctx, request):
        captured["request"] = request
        return models.ListWorkspacesData(Items=[workspace_data()], Total=1)

    monkeypatch.setattr(workspace, "list_workspaces", list_workspaces)
    result = invoke(
        [
            "development-machine",
            "list",
            "--project",
            "demo",
            "--workspace-id",
            "workspace-1",
            "--workspace-id",
            "workspace-2",
            "--name",
            "note",
            "--creator",
            "alice",
            "--share",
            "shared-with-me",
            "--quota-group",
            "research",
            "--quota-group",
            "shared",
            "--cpu-min",
            "2",
            "--cpu-max",
            "8",
            "--memory-min",
            "4",
            "--memory-max",
            "32",
            "--creation-timestamp-min",
            "100",
            "--creation-timestamp-max",
            "200",
            "--close-timestamp-min",
            "300",
            "--close-timestamp-max",
            "400",
            "--sort-by",
            "CreationTime desc",
            "--limit",
            "25",
            "--offset",
            "5",
        ]
    )

    assert result.exit_code == 0, result.output
    assert captured["request"] == models.ListWorkspacesReq(
        CPUMax=8,
        CPUMin=2,
        CloseTimestampMax=400,
        CloseTimestampMin=300,
        CreationTimestampMax=200,
        CreationTimestampMin=100,
        Creator="alice",
        Limit=25,
        MemoryMax=32,
        MemoryMin=4,
        Name="note",
        Offset=5,
        Project="demo",
        QuotaGroup=["research", "shared"],
        Share="shared-with-me",
        SortBy="CreationTime desc",
        WorkspaceId=["workspace-1", "workspace-2"],
    )
    for value in (
        "workspace-1",
        "Running",
        "alice",
        "research",
        "sku-a100",
        "gpu-pool",
        "2026-07-21T10:00:00Z",
        "2026-07-21T10:10:00Z",
        "2026-07-21T10:01:00Z",
    ):
        assert value in result.output


def test_inspect_constructs_workspace_request_and_renders_stable_json(monkeypatch):
    captured = {}

    def get_workspace(_ctx, request):
        captured["request"] = request
        return workspace_data(DaemonJupyterToken="must-not-render")

    monkeypatch.setattr(workspace, "get_workspace", get_workspace)
    result = invoke(
        [
            "--output",
            "json",
            "development-machine",
            "inspect",
            "--project",
            "demo",
            "workspace-1",
        ]
    )

    assert result.exit_code == 0, result.output
    assert captured["request"] == models.GetWorkspaceReq(
        Project="demo", WorkspaceId="workspace-1"
    )
    output = json.loads(result.output)
    assert output["workspace_id"] == "workspace-1"
    assert output["phase"] == "Running"
    assert output["resources"] == {
        "cpu": "4",
        "gpu": "1",
        "memory": "16Gi",
        "worker_count": 2,
    }
    assert output["creator"]["name"] == "alice"
    assert output["quota_group"] == "research"
    assert output["sku"]["id"] == "sku-a100"
    assert output["timestamps"]["created"] == "2026-07-21T10:00:00Z"
    assert "must-not-render" not in result.output
    assert "daemon_jupyter_token" not in result.output


@pytest.mark.parametrize(
    "command,path,response",
    [
        (
            [
                "list",
                "--project",
                "demo",
                "--workspace-id",
                "workspace-1",
                "--workspace-id",
                "workspace-2",
                "--quota-group",
                "research",
                "--quota-group",
                "shared",
                "--cpu-min",
                "2",
                "--memory-max",
                "32",
            ],
            "/workspace/v1alpha1/ListWorkspaces",
            {
                "Code": 0,
                "Msg": "ok",
                "Data": {
                    "Items": [{"WorkspaceId": "workspace-1", "Phase": "Running"}],
                    "Total": 1,
                },
            },
        ),
        (
            ["inspect", "--project", "demo", "workspace-1"],
            "/workspace/v1alpha1/GetWorkspace",
            {
                "Code": 0,
                "Msg": "ok",
                "Data": {"WorkspaceId": "workspace-1", "Phase": "Running"},
            },
        ),
    ],
)
def test_mocked_workspace_transport_uses_workspace_endpoints(command, path, response):
    with requests_mock.Mocker() as mock:
        mock.get(f"https://gate.yicloud.com{path}", json=response)
        result = invoke(["--output", "json", "development-machine", *command])

        assert result.exit_code == 0, result.output
        request = mock.last_request
        assert request is not None
        assert request.url.split("?", 1)[0] == f"https://gate.yicloud.com{path}"
        assert request.qs["project"] == ["demo"]
        if command[0] == "list":
            assert request.qs["workspaceid"] == ["workspace-1,workspace-2"]
            assert request.qs["quotagroup"] == ["research,shared"]
            assert request.qs["cpumin"] == ["2"]
            assert request.qs["memorymax"] == ["32"]
        else:
            assert request.qs["workspaceid"] == ["workspace-1"]
