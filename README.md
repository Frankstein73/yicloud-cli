# yicloud-cli

`yicloud-cli` is a command-line interface for managing YiCloud custom tasks and
development machines from a terminal or automation workflow. It uses the
[YiCloud OpenAPI](https://api.yicloud.com.cn/).

## Prerequisites

- Linux or macOS. Windows users can use a Linux environment such as WSL 2.
- Bash 3.2 or newer for `install.sh`. The installed CLI can be run from Bash,
  Zsh, or another shell that can execute a program from the project directory.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) available on
  `PATH`.
- Python 3.11 or newer installed locally or through uv. The installer does not
  download Python automatically; `uv python install 3.11` can prepare it first.
- Git and network access to fetch the YiCloud SDK dependency pinned in
  `uv.lock`.

You do not need YiCloud credentials to install the project or display help and
version output.

## Installation

From a fresh checkout, run the repository installer:

```shell
./install.sh
```

The script checks its prerequisites, creates or updates the project-local
`.venv`, synchronizes the exact locked runtime dependencies, and verifies the
installed `yicloud` entry point. It can be run repeatedly. It does not inspect
or store YiCloud credentials.

Run the installed command directly:

```shell
.venv/bin/yicloud --help
.venv/bin/yicloud --version
```

Or let uv run the same project entry point:

```shell
uv run --locked --no-dev yicloud --help
uv run --locked --no-dev yicloud --version
```

### Manual installation

The equivalent project-level workflow is:

```shell
uv python find '>=3.11' --no-python-downloads
uv sync --locked --no-dev
uv run --locked --no-dev yicloud --version
```

`--locked` makes synchronization fail instead of silently changing the
committed `uv.lock`.

### Upgrade or reinstall

To upgrade to a newer checkout while retaining locked, reproducible
dependencies:

```shell
git pull --ff-only
./install.sh
```

Running `./install.sh` again is also the normal repair/reinstall operation. To
force uv to reinstall every locked runtime package in the existing project
environment, run:

```shell
UV_PROJECT_ENVIRONMENT="$PWD/.venv" uv sync --locked --no-dev --reinstall
```

### Uninstall or clean up

Installation creates only the `.venv` directory inside this checkout. Remove
that project-owned environment to uninstall the prepared CLI:

```shell
rm -rf -- .venv
```

This does not remove the source checkout, credentials, or shared uv caches.

## Authentication

Commands that call the API read credentials lazily from two environment
variables. Export them in the shell where you run the CLI:

```shell
export Access_Key_ID='your-access-key-id'
export Secret_Access_Key='your-secret-access-key'
```

Use your shell or CI system's secret manager for persistent configuration. Do
not commit credentials to the repository. Help and version commands do not
read these variables.

The endpoint, profile name, and output format can optionally be configured with
`YICLOUD_ENDPOINT`, `YICLOUD_PROFILE`, and `YICLOUD_OUTPUT`. Global options must
come before the resource command:

```shell
.venv/bin/yicloud \
  --endpoint https://gate.yicloud.com \
  --profile default \
  --output json \
  custom-task --help
```

## Usage

Start with command discovery, which does not contact YiCloud:

```shell
.venv/bin/yicloud --help
.venv/bin/yicloud custom-task --help
.venv/bin/yicloud development-machine --help
```

The following API examples require valid credentials, a reachable endpoint,
and identifiers from your YiCloud account.

### Custom tasks

Custom tasks use the OpenAPI `job/v1alpha1` service. A task specification is
supplied as `NAME=JSON`; `image`, `command`, and `replicas` are required, while
`env` defaults to an empty object.

```shell
.venv/bin/yicloud custom-task create \
  --project demo \
  --name training-run \
  --task-spec 'worker={"image":"registry.example/train:1","command":["python","train.py"],"replicas":1,"env":{"MODE":"train"}}'

.venv/bin/yicloud custom-task list --project demo --phase Running --limit 25
.venv/bin/yicloud --output json custom-task inspect task-123 --project demo
.venv/bin/yicloud custom-task update task-123 --project demo --priority 7
.venv/bin/yicloud custom-task update task-123 --project demo --top
.venv/bin/yicloud custom-task cancel task-123 task-456 --project demo
.venv/bin/yicloud custom-task clone task-123 --project demo --target-name rerun
.venv/bin/yicloud custom-task delete task-123 --project demo --yes
```

The API does not expose a retry action; use `clone` to create a new task from
an existing one. Run `.venv/bin/yicloud custom-task COMMAND --help` for all
supported filters and options.

### Development machines

Every development-machine API command requires a project namespace.

```shell
# Create from an existing development environment.
.venv/bin/yicloud development-machine create \
  --project my-project \
  --environment-id env-123 \
  --name interactive-dev \
  --lifecycle-minutes 120

# Or create directly from an image and explicit resources.
.venv/bin/yicloud development-machine create \
  --project my-project \
  --image-ref team/dev-image:latest \
  --cpu 2 \
  --memory 4Gi \
  --env MODE=development \
  --port 8080:http:web

.venv/bin/yicloud development-machine list --project my-project --run-state running
.venv/bin/yicloud --output json development-machine inspect --project my-project sandbox-123
.venv/bin/yicloud development-machine update-lifecycle \
  --project my-project sandbox-123 --mode extend --minutes 60
.venv/bin/yicloud development-machine stop --project my-project sandbox-123
.venv/bin/yicloud development-machine delete --project my-project sandbox-123
.venv/bin/yicloud development-machine batch-delete \
  --project my-project sandbox-123 sandbox-456
```

The pinned SDK exposes create, list, inspect, stop, delete, batch-delete, and
lifecycle-update operations. It does not expose start or restart endpoints, so
the CLI does not advertise them. Run
`.venv/bin/yicloud development-machine COMMAND --help` for all inputs and
filters.

## Troubleshooting

### A prerequisite is missing

- `uv was not found on PATH`: install uv using its official instructions,
  start a new shell if needed, confirm `uv --version`, and rerun the installer.
- `git was not found on PATH`: install Git and confirm `git --version`.
- `Python 3.11 or newer is unavailable`: install a supported interpreter with
  your platform tools or `uv python install 3.11`, then confirm it with
  `uv python find '>=3.11' --no-python-downloads`.
- `Permission denied` for `./install.sh`: restore the executable checkout bit
  with `chmod +x install.sh`, then rerun it.

### Credentials are missing

API commands report which of `Access_Key_ID` or `Secret_Access_Key` is absent.
Export both variables in the current shell. Confirm only that they are set,
without printing their values:

```shell
test -n "${Access_Key_ID:-}" && test -n "${Secret_Access_Key:-}" && echo 'credentials are set'
```

### Locked dependency synchronization fails

Confirm that `pyproject.toml` and `uv.lock` are present and unchanged with
`git status --short -- pyproject.toml uv.lock`. Then check network access to the
package index and the pinned YiCloud SDK Git repository. `uv sync --locked
--no-dev -v` provides detailed resolver diagnostics without involving cloud
credentials. A lock mismatch must be resolved in source control; the installer
will not rewrite the lockfile.

### The API rejects a command

Read the sanitized error, confirm the endpoint and project/resource identifiers,
and verify that the access key has permission for the requested operation.
Authentication failures generally indicate missing, expired, or unauthorized
credentials. Network errors can indicate DNS, proxy, TLS, or endpoint
availability problems. Use `--output json` when structured output is useful for
automation; credential values are redacted from normal output and expected
errors.

## Development and tests

Synchronize the locked development environment and run the full suite:

```shell
uv sync --locked
uv run --locked pytest
```

Run only the installer harness with:

```shell
uv run --locked pytest tests/test_install.py
```

The package also supports module invocation during development:

```shell
uv run --locked python -m yicloud_cli --help
```

## Contributing

Issues and pull requests are welcome. Include the relevant OpenAPI endpoint or
behavior and explain how the change was tested.

## License

No license has been selected yet.
