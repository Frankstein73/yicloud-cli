import json
from dataclasses import asdict

import pytest
import requests_mock
from click.testing import CliRunner
from yicloud.base.errs import ServerException
from yicloud.services.job import models

from yicloud_cli.auth import ACCESS_KEY_ENV, SECRET_KEY_ENV
from yicloud_cli.cli import create_cli


ENVIRONMENT = {
    ACCESS_KEY_ENV: "access-key-for-custom-task-tests",
    SECRET_KEY_ENV: "secret-key-for-custom-task-tests",
}


class RecordingService:
    def __init__(self):
        self.calls = []

    def create(self, request):
        self.calls.append(("create", request))
        return models.CreateJobData(
            JobId="job-created", Name=request.Name, Project=request.Project
        )

    def list(self, request):
        self.calls.append(("list", request))
        return models.ListJobsData(
            Items=[
                models.GetJobData(
                    JobId="job-one",
                    Name="training",
                    Project=request.Project,
                    Phase="Running",
                )
            ],
            Total=1,
        )

    def inspect(self, request):
        self.calls.append(("inspect", request))
        return models.GetJobData(
            JobId=request.JobId, Name="training", Project=request.Project
        )

    def update(self, request):
        self.calls.append(("update", request))

    def cancel(self, request):
        self.calls.append(("cancel", request))
        return models.BatchStopJobsData(Message="stopped")

    def delete(self, request):
        self.calls.append(("delete", request))

    def clone(self, request):
        self.calls.append(("clone", request))
        return models.CloneJobData(
            JobId="job-cloned", Name=request.TargetName, Project=request.Project
        )


@pytest.fixture
def recording_cli():
    service = RecordingService()
    application = create_cli(
        client_factory=lambda *args, **kwargs: object(),
        custom_task_service_factory=lambda client: service,
        environ=ENVIRONMENT,
    )
    return application, service


def test_custom_task_help_lists_every_openapi_lifecycle_operation():
    result = CliRunner().invoke(create_cli(environ={}), ["custom-task", "--help"])

    assert result.exit_code == 0
    for command in ("create", "list", "inspect", "update", "cancel", "delete", "clone"):
        assert command in result.output


def test_create_parses_task_spec_and_constructs_sdk_request(recording_cli):
    application, service = recording_cli

    result = CliRunner().invoke(
        application,
        [
            "--output",
            "json",
            "custom-task",
            "create",
            "--project",
            "demo",
            "--name",
            "training",
            "--job-type",
            "normal",
            "--priority",
            "7",
            "--backoff-limit",
            "2",
            "--task-spec",
            'worker={"image":"train:1","command":["python","train.py"],"replicas":2,"cpu":"4"}',
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "creation_time": "",
        "job_id": "job-created",
        "name": "training",
        "project": "demo",
        "uid": "",
    }
    operation, request = service.calls[0]
    assert operation == "create"
    assert asdict(request) == {
        "Name": "training",
        "Project": "demo",
        "TaskSpecs": {
            "worker": {
                "Command": ["python", "train.py"],
                "Env": {},
                "Image": "train:1",
                "Replicas": 2,
                "CPU": "4",
                "EnableSSHD": None,
                "EphemeralStorage": None,
                "GPU": None,
                "HostNetwork": None,
                "MaxRunningDuration": None,
                "MaxWaitDuration": None,
                "Memory": None,
                "MountGPFS": None,
                "MountGpfsVolumes": None,
                "NegativeTags": None,
                "OtherResources": None,
                "PositiveTags": None,
                "RestartPolicy": None,
                "SKUId": None,
                "UpdatePolicy": None,
            }
        },
        "AutoDeleteDuration": None,
        "BackoffLimit": 2,
        "Creator": None,
        "CreatorId": None,
        "JobId": None,
        "JobType": "normal",
        "Mount": None,
        "Priority": "7",
        "Qos": None,
        "QuotaGroup": None,
        "RealCreator": None,
        "RealCreatorId": None,
        "SKUPrivate": None,
        "SKUPrivateProject": None,
        "SKUPrivateTenant": None,
        "SKUPublic": None,
        "SelfHealConfig": None,
        "TaskType": None,
        "UsePrivateMachine": None,
    }


@pytest.mark.parametrize(
    "arguments,message",
    [
        (
            [
                "--name",
                " ",
                "--project",
                "demo",
                "--task-spec",
                't={"image":"x","command":["run"],"replicas":1}',
            ],
            "must not be empty",
        ),
        (
            ["--name", "n", "--project", "demo", "--task-spec", "missing-separator"],
            "NAME=JSON",
        ),
        (
            ["--name", "n", "--project", "demo", "--task-spec", "t={not-json}"],
            "invalid JSON",
        ),
        (
            [
                "--name",
                "n",
                "--project",
                "demo",
                "--task-spec",
                't={"command":["run"],"replicas":1}',
            ],
            "field 'image'",
        ),
        (
            [
                "--name",
                "n",
                "--project",
                "demo",
                "--task-spec",
                't={"image":"x","command":[],"replicas":1}',
            ],
            "field 'command'",
        ),
        (
            [
                "--name",
                "n",
                "--project",
                "demo",
                "--task-spec",
                't={"image":"x","command":["run"],"replicas":0}',
            ],
            "field 'replicas'",
        ),
        (
            [
                "--name",
                "n",
                "--project",
                "demo",
                "--task-spec",
                't={"image":"x","command":["run"],"replicas":1,"unknown":true}',
            ],
            "unknown field",
        ),
    ],
)
def test_create_rejects_invalid_fields_before_constructing_client(arguments, message):
    calls = []
    application = create_cli(
        client_factory=lambda *args, **kwargs: calls.append(True),
        environ=ENVIRONMENT,
    )

    result = CliRunner().invoke(application, ["custom-task", "create", *arguments])

    assert result.exit_code == 2
    assert message in result.output
    assert calls == []


def test_list_constructs_filters_and_renders_stable_human_table(recording_cli):
    application, service = recording_cli

    result = CliRunner().invoke(
        application,
        [
            "custom-task",
            "list",
            "--project",
            "demo",
            "--creator",
            "alice",
            "--creator",
            "bob",
            "--task-id",
            "job-one",
            "--name",
            "train",
            "--phase",
            "Running",
            "--quota-group",
            "research",
            "--job-type",
            "normal",
            "--mine",
            "--sort-by",
            "CreationTime",
            "--limit",
            "25",
            "--offset",
            "5",
        ],
    )

    assert result.exit_code == 0
    assert "job_id" in result.output
    assert "job-one" in result.output
    assert "Running" in result.output
    _, request = service.calls[0]
    assert request == models.ListJobsReq(
        Project="demo",
        Creators="alice,bob",
        JobIds="job-one",
        JobNames="train",
        Phases="Running",
        QuotaGroup="research",
        JobType="normal",
        Self=True,
        SortBy="CreationTime",
        Limit=25,
        Offset=5,
    )


def test_inspect_constructs_request_and_renders_json(recording_cli):
    application, service = recording_cli

    result = CliRunner().invoke(
        application,
        ["--output", "json", "custom-task", "inspect", "job-one", "--project", "demo"],
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["job_id"] == "job-one"
    assert service.calls == [
        ("inspect", models.GetJobReq(JobId="job-one", Project="demo"))
    ]


@pytest.mark.parametrize(
    "arguments,expected",
    [
        (
            ["update", "job-one", "--project", "demo", "--priority", "8"],
            models.EditJobReq(
                Operation="priority", Project="demo", JobId="job-one", Priority="8"
            ),
        ),
        (
            ["update", "job-one", "--project", "demo", "--no-top"],
            models.EditJobReq(
                Operation="top", Project="demo", JobId="job-one", TopAction="unset"
            ),
        ),
    ],
)
def test_update_constructs_supported_edit_requests(recording_cli, arguments, expected):
    application, service = recording_cli

    result = CliRunner().invoke(application, ["custom-task", *arguments])

    assert result.exit_code == 0
    assert service.calls == [("update", expected)]


def test_update_requires_exactly_one_change(recording_cli):
    application, service = recording_cli

    missing = CliRunner().invoke(
        application, ["custom-task", "update", "job-one", "--project", "demo"]
    )
    conflicting = CliRunner().invoke(
        application,
        [
            "custom-task",
            "update",
            "job-one",
            "--project",
            "demo",
            "--priority",
            "3",
            "--top",
        ],
    )

    assert missing.exit_code == 2
    assert conflicting.exit_code == 2
    assert "exactly one" in missing.output
    assert "exactly one" in conflicting.output
    assert service.calls == []


def test_cancel_delete_and_clone_construct_lifecycle_requests(recording_cli):
    application, service = recording_cli
    runner = CliRunner()

    cancel = runner.invoke(
        application,
        ["custom-task", "cancel", "job-one", "job-two", "--project", "demo"],
    )
    delete = runner.invoke(
        application,
        ["custom-task", "delete", "job-one", "job-two", "--project", "demo", "--yes"],
    )
    clone = runner.invoke(
        application,
        [
            "custom-task",
            "clone",
            "job-one",
            "--project",
            "demo",
            "--target-name",
            "copy",
        ],
    )

    assert cancel.exit_code == delete.exit_code == clone.exit_code == 0
    assert service.calls[0] == (
        "cancel",
        models.BatchStopJobsReq(
            Resources=[
                models.BatchStopJobsReqResourceIdentifier(
                    JobId="job-one", Project="demo"
                ),
                models.BatchStopJobsReqResourceIdentifier(
                    JobId="job-two", Project="demo"
                ),
            ]
        ),
    )
    assert service.calls[1] == (
        "delete",
        models.BatchDeleteJobsReq(
            Resources=[
                models.BatchDeleteJobsReqResourceIdentifier(
                    JobId="job-one", Project="demo"
                ),
                models.BatchDeleteJobsReqResourceIdentifier(
                    JobId="job-two", Project="demo"
                ),
            ]
        ),
    )
    assert service.calls[2] == (
        "clone",
        models.CloneJobReq(JobId="job-one", Project="demo", TargetName="copy"),
    )


def test_sdk_api_error_is_mapped_and_credentials_are_redacted():
    secret = ENVIRONMENT[SECRET_KEY_ENV]

    class FailingService(RecordingService):
        def inspect(self, request):
            raise ServerException(
                "GetJob",
                status_code=403,
                ret_code=1201,
                message=f"denied secret={secret}",
            )

    service = FailingService()
    application = create_cli(
        client_factory=lambda *args, **kwargs: object(),
        custom_task_service_factory=lambda client: service,
        environ=ENVIRONMENT,
    )

    result = CliRunner().invoke(
        application, ["custom-task", "inspect", "job-one", "--project", "demo"]
    )

    assert result.exit_code == 1
    assert "API request failed (HTTP 403, code 1201)" in result.output
    assert "[REDACTED]" in result.output
    assert secret not in result.output


def _mock_response(data=None):
    return {"Code": 0, "Msg": "ok", "Data": data}


def test_mocked_http_create_list_and_inspect_flows_use_generated_sdk():
    application = create_cli(environ=ENVIRONMENT)
    runner = CliRunner()

    with requests_mock.Mocker() as mock:
        mock.post(
            "https://gate.yicloud.com/job/v1alpha1/CreateJob",
            json=_mock_response(
                {"JobId": "job-created", "Name": "training", "Project": "demo"}
            ),
        )
        mock.get(
            "https://gate.yicloud.com/job/v1alpha1/ListJobs",
            json=_mock_response(
                {
                    "Items": [
                        {
                            "JobId": "job-created",
                            "Name": "training",
                            "Project": "demo",
                            "Phase": "Running",
                        }
                    ],
                    "Total": 1,
                }
            ),
        )
        mock.get(
            "https://gate.yicloud.com/job/v1alpha1/GetJob",
            json=_mock_response(
                {"JobId": "job-created", "Name": "training", "Project": "demo"}
            ),
        )

        create = runner.invoke(
            application,
            [
                "--output",
                "json",
                "custom-task",
                "create",
                "--project",
                "demo",
                "--name",
                "training",
                "--task-spec",
                'worker={"image":"train:1","command":["run"],"replicas":1}',
            ],
        )
        list_result = runner.invoke(
            application,
            ["--output", "json", "custom-task", "list", "--project", "demo"],
        )
        inspect = runner.invoke(
            application,
            [
                "--output",
                "json",
                "custom-task",
                "inspect",
                "job-created",
                "--project",
                "demo",
            ],
        )

    assert create.exit_code == list_result.exit_code == inspect.exit_code == 0
    assert json.loads(create.output)["job_id"] == "job-created"
    assert json.loads(list_result.output)[0]["phase"] == "Running"
    assert json.loads(inspect.output)["name"] == "training"


def test_mocked_http_update_cancel_delete_and_clone_flows_use_generated_sdk():
    application = create_cli(environ=ENVIRONMENT)
    runner = CliRunner()

    with requests_mock.Mocker() as mock:
        update = mock.post(
            "https://gate.yicloud.com/job/v1alpha1/EditJob", json=_mock_response()
        )
        cancel = mock.post(
            "https://gate.yicloud.com/job/v1alpha1/BatchStopJobs",
            json=_mock_response({"Message": "stopped", "Failed": [], "Reasons": {}}),
        )
        delete = mock.post(
            "https://gate.yicloud.com/job/v1alpha1/BatchDeleteJobs",
            json=_mock_response(),
        )
        clone = mock.post(
            "https://gate.yicloud.com/job/v1alpha1/CloneJob",
            json=_mock_response(
                {"JobId": "job-copy", "Name": "copy", "Project": "demo"}
            ),
        )

        results = [
            runner.invoke(
                application,
                [
                    "custom-task",
                    "update",
                    "job-one",
                    "--project",
                    "demo",
                    "--priority",
                    "6",
                ],
            ),
            runner.invoke(
                application, ["custom-task", "cancel", "job-one", "--project", "demo"]
            ),
            runner.invoke(
                application,
                ["custom-task", "delete", "job-one", "--project", "demo", "--yes"],
            ),
            runner.invoke(
                application,
                [
                    "custom-task",
                    "clone",
                    "job-one",
                    "--project",
                    "demo",
                    "--target-name",
                    "copy",
                ],
            ),
        ]

    assert all(result.exit_code == 0 for result in results)
    assert update.last_request.json()["Operation"] == "priority"
    assert cancel.last_request.json()["Resources"][0]["JobId"] == "job-one"
    assert delete.last_request.json()["Resources"][0]["Project"] == "demo"
    assert clone.last_request.json()["TargetName"] == "copy"
