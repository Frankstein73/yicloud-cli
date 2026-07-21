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

Development machines are managed through the `development-machine` group. Every API command
requires a project namespace; global options such as `--output json` must come before the
resource group:

```shell
# Create from an existing development environment.
uv run yicloud development-machine create \
  --project my-project \
  --environment-id env-123 \
  --name interactive-dev \
  --lifecycle-minutes 120

# Or create directly from an image and explicit resources.
uv run yicloud development-machine create \
  --project my-project \
  --image-ref team/dev-image:latest \
  --cpu 2 \
  --memory 4Gi \
  --env MODE=development \
  --port 8080:http:web

uv run yicloud development-machine list --project my-project --run-state running
uv run yicloud --output json development-machine inspect --project my-project sandbox-123
uv run yicloud development-machine update-lifecycle \
  --project my-project sandbox-123 --mode extend --minutes 60
uv run yicloud development-machine stop --project my-project sandbox-123
uv run yicloud development-machine delete --project my-project sandbox-123
uv run yicloud development-machine batch-delete \
  --project my-project sandbox-123 sandbox-456
```

Run `uv run yicloud development-machine COMMAND --help` for all create inputs and list
filters. The pinned OpenAPI SDK exposes create, list, inspect, stop, delete, batch-delete,
and lifecycle-update operations for individual machines. It does not expose start or restart
endpoints, so the CLI does not advertise commands that it cannot implement safely. Sandbox
environment, prewarm-pool, and environment-statistics endpoints manage reusable templates and
pools rather than individual development machines and are not mapped into this command group.

## Contributing

Issues and pull requests are welcome. When proposing a change, please include the relevant
OpenAPI endpoint or behavior and explain how the change was tested.

## License

No license has been selected yet.
