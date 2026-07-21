# yicloud-cli

`yicloud-cli` is a command-line interface for interacting with the YiCloud platform.
It is developed against the [YiCloud OpenAPI](https://api.yicloud.com.cn/) and is intended
to make common YiCloud operations accessible from a terminal or automation workflow.

## Status

This project is at an early stage. The command structure and API coverage will evolve as
YiCloud OpenAPI integrations are added.

## Goals

- Provide a simple, script-friendly interface to YiCloud services.
- Support secure configuration of YiCloud credentials.
- Expose useful API operations as discoverable CLI commands.
- Return predictable output suitable for both humans and automation.

## API reference

The implementation is based on the official [YiCloud OpenAPI](https://api.yicloud.com.cn/).
Please consult the API documentation for authentication requirements, available endpoints,
request parameters, and response formats.

## Development

Install the locked development environment and display the command help with:

```shell
uv sync
uv run yicloud --help
uv run yicloud --version
```

The package also supports module invocation during development:

```shell
uv run python -m yicloud_cli --help
```

After installing the package, the equivalent console command is:

```shell
yicloud --help
yicloud --version
```

Global options must precede the resource command. The default output is intended for humans;
use JSON for automation:

```shell
uv run yicloud \
  --endpoint https://gate.yicloud.com \
  --profile default \
  --output json \
  custom-task --help
```

The endpoint, profile, and output format can also be set with `YICLOUD_ENDPOINT`,
`YICLOUD_PROFILE`, and `YICLOUD_OUTPUT`. Commands that access the API load credentials lazily
from `Access_Key_ID` and `Secret_Access_Key`; help and version commands do not require them.
Credential values are never included in normal CLI output or presented exception messages.

### Custom tasks

Custom tasks use the OpenAPI `job/v1alpha1` service. A task specification is supplied as
`NAME=JSON`; its required fields are `image`, `command`, and `replicas`, while `env`
defaults to an empty object. For example:

```shell
uv run yicloud custom-task create \
  --project demo \
  --name training-run \
  --task-spec 'worker={"image":"registry.example/train:1","command":["python","train.py"],"replicas":1,"env":{"MODE":"train"}}'

uv run yicloud custom-task list --project demo --phase Running --limit 25
uv run yicloud --output json custom-task inspect task-123 --project demo
```

The remaining lifecycle operations exposed by the OpenAPI are available with consistent
task identifiers and project options:

```shell
uv run yicloud custom-task update task-123 --project demo --priority 7
uv run yicloud custom-task update task-123 --project demo --top
uv run yicloud custom-task cancel task-123 task-456 --project demo
uv run yicloud custom-task clone task-123 --project demo --target-name rerun
uv run yicloud custom-task delete task-123 --project demo --yes
```

The API does not expose a retry action. Use `clone` to create a new task from an existing
one. Job replica, process, and log endpoints are observability/subresource APIs rather than
custom-task lifecycle operations and are outside this command group's lifecycle scope.

Run `uv run yicloud custom-task COMMAND --help` for all supported filters and options.
The `development-machine` group remains a stable extension point for its resource commands.

## Contributing

Issues and pull requests are welcome. When proposing a change, please include the relevant
OpenAPI endpoint or behavior and explain how the change was tested.

## License

No license has been selected yet.
