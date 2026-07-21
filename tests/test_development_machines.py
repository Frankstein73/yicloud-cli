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


def test_development_machine_help_exposes_workspace_commands():
    result = invoke(["development-machine", "--help"])

    assert result.exit_code == 0
    assert "Workspace" in result.output
    assert "create" in result.output
    assert "list" in result.output
    assert "inspect" in result.output
    for sandbox_command in (
        "stop",
        "delete",
        "batch-delete",
        "update-lifecycle",
    ):
        assert sandbox_command not in result.output


def test_create_quota_mode_constructs_official_workspace_request(monkeypatch):
    captured = {}

    def create_workspace(_ctx, request):
        captured["request"] = request
        return workspace_data(WorkspaceId="workspace-created", Name="new-notebook")

    monkeypatch.setattr(workspace, "create_workspace", create_workspace)
    result = invoke(
        [
            "--output",
            "json",
            "development-machine",
            "create",
            "--name",
            "new-notebook",
            "--project",
            "demo",
            "--description",
            "research environment",
            "--env",
            "MODE=train",
            "--env",
            "EMPTY=",
            "--image",
            "registry.example/notebook:1",
            "--use-private-machine",
            "--runtime-mode",
            "kata",
            "--cpu",
            "4",
            "--memory",
            "16Gi",
            "--gpu",
            "1",
            "--quota-group",
            "research",
            "--mount-gpfs",
            "gpfs://legacy/path:/mnt/legacy",
            "--gpfs-volume",
            "gpfs://gpfs1/team=/mnt/team",
        ]
    )

    assert result.exit_code == 0, result.output
    assert captured["request"] == models.CreateWorkspaceReq(
        Name="new-notebook",
        CPU="4",
        Description="research environment",
        Env={"MODE": "train", "EMPTY": ""},
        GPU="1",
        Image="registry.example/notebook:1",
        Memory="16Gi",
        MountGPFS="gpfs://legacy/path:/mnt/legacy",
        MountGpfsVolumes=[
            models.CreateWorkspaceReqMountGpfsVolume(
                Source="gpfs://gpfs1/team", Target="/mnt/team"
            )
        ],
        Project="demo",
        QuotaGroup="research",
        RuntimeMode="kata",
        UsePrivateMachine=True,
    )
    output = json.loads(result.output)
    assert output["workspace_id"] == "workspace-created"
    assert output["name"] == "new-notebook"


def test_create_sku_mode_loads_json_and_yaml_disks(monkeypatch, tmp_path):
    system_disk = tmp_path / "system.yaml"
    system_disk.write_text(
        """name: system
storage: 100Gi
storage_class_name: fast-rbd
data_source:
  api_group: image.brainpp.cn
  kind: Image
  name: ubuntu-22
""",
        encoding="utf-8",
    )
    data_disk = tmp_path / "data.json"
    data_disk.write_text(
        json.dumps(
            {
                "Name": "dataset-copy",
                "DataSourceType": "clone",
                "Storage": "500Gi",
                "DataSource": {
                    "ApiGroup": "workspace.brainpp.cn",
                    "Kind": "Workspace",
                    "Name": "workspace-source",
                },
            }
        ),
        encoding="utf-8",
    )
    captured = {}

    def create_workspace(_ctx, request):
        captured["request"] = request
        return workspace_data(WorkspaceId="workspace-sku")

    monkeypatch.setattr(workspace, "create_workspace", create_workspace)
    result = invoke(
        [
            "development-machine",
            "create",
            "--name",
            "sku-notebook",
            "--sku-id",
            "sku-a100",
            "--sku-private",
            "--sku-project",
            "--system-disk",
            str(system_disk),
            "--data-disk",
            str(data_disk),
        ]
    )

    assert result.exit_code == 0, result.output
    request = captured["request"]
    assert request == models.CreateWorkspaceReq(
        Name="sku-notebook",
        DataDisk=models.CreateWorkspaceReqDiskInput(
            Name="dataset-copy",
            DataSource=models.CreateWorkspaceReqDataSource(
                ApiGroup="workspace.brainpp.cn",
                Kind="Workspace",
                Name="workspace-source",
            ),
            DataSourceType="clone",
            Storage="500Gi",
        ),
        SkuId="sku-a100",
        SkuPrivate=True,
        SkuProject=True,
        SkuPublic=False,
        SkuTenant=False,
        SystemDisk=models.CreateWorkspaceReqDiskInput(
            Name="system",
            DataSource=models.CreateWorkspaceReqDataSource(
                ApiGroup="image.brainpp.cn", Kind="Image", Name="ubuntu-22"
            ),
            Storage="100Gi",
            StorageClassName="fast-rbd",
        ),
    )


def test_create_existing_volume_disk_allows_optional_storage(monkeypatch, tmp_path):
    disk = tmp_path / "volume.yaml"
    disk.write_text(
        """name: existing
data_source:
  api_group: volume.brainpp.cn
  kind: Volume
  name: volume-123
""",
        encoding="utf-8",
    )
    captured = {}

    def create_workspace(_ctx, request):
        captured["request"] = request
        return workspace_data()

    monkeypatch.setattr(workspace, "create_workspace", create_workspace)
    result = invoke(
        [
            "development-machine",
            "create",
            "--name",
            "existing-volume",
            "--sku-id",
            "sku-public",
            "--sku-public",
            "--data-disk",
            str(disk),
        ]
    )

    assert result.exit_code == 0, result.output
    assert captured["request"].DataDisk == models.CreateWorkspaceReqDiskInput(
        Name="existing",
        DataSource=models.CreateWorkspaceReqDataSource(
            ApiGroup="volume.brainpp.cn", Kind="Volume", Name="volume-123"
        ),
    )


@pytest.mark.parametrize(
    "arguments,message",
    [
        (["--runtime-mode", "kata", "--cpu", "4"], "quota mode requires"),
        (
            [
                "--runtime-mode",
                "kata",
                "--cpu",
                "4",
                "--memory",
                "16Gi",
                "--quota-group",
                "research",
                "--sku-id",
                "sku-a100",
                "--sku-public",
            ],
            "mutually exclusive",
        ),
        (["--sku-public"], "requires --sku-id"),
        (["--sku-id", "sku-a100"], "exactly one of --sku-public"),
        (
            ["--sku-id", "sku-a100", "--sku-public", "--sku-private"],
            "exactly one of --sku-public",
        ),
        (
            ["--sku-id", "sku-a100", "--sku-public", "--sku-tenant"],
            "public SKU mode cannot use",
        ),
        (
            ["--sku-id", "sku-a100", "--sku-private"],
            "exactly one of --sku-tenant",
        ),
        (
            [
                "--sku-id",
                "sku-a100",
                "--sku-private",
                "--sku-tenant",
                "--sku-project",
            ],
            "exactly one of --sku-tenant",
        ),
        (
            [
                "--runtime-mode",
                "kata",
                "--cpu",
                "zero",
                "--memory",
                "16Gi",
                "--quota-group",
                "research",
            ],
            "positive Kubernetes resource quantity",
        ),
        (
            [
                "--runtime-mode",
                "kata",
                "--cpu",
                "4",
                "--memory",
                "0Gi",
                "--quota-group",
                "research",
            ],
            "positive Kubernetes resource quantity",
        ),
    ],
)
def test_invalid_create_modes_fail_before_client_construction(arguments, message):
    calls = []
    application = create_cli(
        environ=ENVIRONMENT,
        client_factory=lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    result = CliRunner().invoke(
        application,
        ["development-machine", "create", "--name", "notebook", *arguments],
    )

    assert result.exit_code == 2
    assert message in result.output
    assert calls == []


@pytest.mark.parametrize(
    "payload,message",
    [
        ({"name": "new"}, "require storage"),
        (
            {
                "name": "image",
                "data_source": {"kind": "Image", "name": "ubuntu"},
            },
            "require storage",
        ),
        ({"name": "clone", "data_source_type": "clone"}, "require data_source"),
        (
            {
                "name": "clone-image",
                "data_source_type": "clone",
                "data_source": {"kind": "Image", "name": "ubuntu"},
            },
            "cannot use an Image",
        ),
        ({"name": "bad", "storage": "0Gi"}, "positive Kubernetes quantity"),
        (
            {
                "name": "bad-kind",
                "storage": "10Gi",
                "data_source": {"kind": "Workspace", "name": "source"},
            },
            "must be Image or Volume",
        ),
    ],
)
def test_invalid_disk_files_fail_before_client_construction(tmp_path, payload, message):
    disk = tmp_path / "disk.yaml"
    disk.write_text(json.dumps(payload), encoding="utf-8")
    calls = []
    application = create_cli(
        environ=ENVIRONMENT,
        client_factory=lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    result = CliRunner().invoke(
        application,
        [
            "development-machine",
            "create",
            "--name",
            "notebook",
            "--sku-id",
            "sku-a100",
            "--sku-public",
            "--data-disk",
            str(disk),
        ],
    )

    assert result.exit_code == 2
    assert message in result.output
    assert calls == []


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


def test_mocked_transport_posts_create_workspace_payload(tmp_path):
    disk = tmp_path / "data-disk.yaml"
    disk.write_text(
        """name: dataset
storage: 250Gi
storage_class_name: csi-rbd-storageclass
data_source:
  api_group: image.brainpp.cn
  kind: Image
  name: dataset-image
""",
        encoding="utf-8",
    )
    response = {
        "Code": 0,
        "Msg": "ok",
        "Data": {
            "WorkspaceId": "workspace-created",
            "Name": "notebook",
            "Project": "demo",
            "Phase": "Pending",
        },
    }

    with requests_mock.Mocker() as mock:
        mock.post(
            "https://gate.yicloud.com/workspace/v1alpha1/CreateWorkspace",
            json=response,
        )
        result = invoke(
            [
                "--output",
                "json",
                "development-machine",
                "create",
                "--name",
                "notebook",
                "--project",
                "demo",
                "--sku-id",
                "sku-a100",
                "--sku-private",
                "--sku-tenant",
                "--data-disk",
                str(disk),
            ]
        )

        assert result.exit_code == 0, result.output
        request = mock.last_request
        assert request is not None
        assert request.method == "POST"
        assert request.url == (
            "https://gate.yicloud.com/workspace/v1alpha1/CreateWorkspace"
        )
        assert request.json() == {
            "Name": "notebook",
            "Project": "demo",
            "SkuId": "sku-a100",
            "SkuPrivate": True,
            "SkuProject": False,
            "SkuPublic": False,
            "SkuTenant": True,
            "DataDisk": {
                "Name": "dataset",
                "Storage": "250Gi",
                "StorageClassName": "csi-rbd-storageclass",
                "DataSource": {
                    "ApiGroup": "image.brainpp.cn",
                    "Kind": "Image",
                    "Name": "dataset-image",
                },
                "DataSourceType": None,
            },
        }
        assert json.loads(result.output)["workspace_id"] == "workspace-created"
