# yicloud-cli

`yicloud-cli` is a command-line interface for managing YiCloud custom tasks and
development machines from a terminal or automation workflow. It uses the
[YiCloud OpenAPI](https://api.yicloud.com.cn/).

## Prerequisites

- Linux or macOS. Windows users can use a Linux environment such as WSL 2.
- Bash 3.2 or newer to run `install.sh`.
- Zsh for the documented automatic PATH setup. The installed command also works
  in Bash and other shells when `~/.local/bin` is on `PATH`.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) available on
  `PATH`.
- Python 3.11 or newer installed locally or through uv. The installer does not
  download Python automatically; `uv python install 3.11` can prepare it first.
- Git and network access to fetch the YiCloud SDK dependency pinned in
  `uv.lock`.
- `curl` and `tar` for the one-line remote installation. A checkout installation
  also needs `tar`.

You do not need YiCloud credentials to install the project or display help and
version output.

## Installation

Install the current release directly from Zsh or another terminal:

```shell
curl -fsSL https://raw.githubusercontent.com/Frankstein73/yicloud-cli/main/install.sh | bash
```

The installer downloads the project snapshot, creates a persistent locked
environment in `~/.local/share/yicloud-cli`, and links the command at
`~/.local/bin/yicloud`. It adds this idempotent block to the active Zsh
configuration file (`${ZDOTDIR:-$HOME}/.zshrc` by default):

```shell
# >>> yicloud-cli >>>
export PATH="/absolute/path/to/.local/bin:$PATH"
# <<< yicloud-cli <<<
```

Open a new Zsh session, or load the change once in the current session:

```shell
source "${ZDOTDIR:-$HOME}/.zshrc"
yicloud --help
yicloud --version
```

The command now works from any directory without `uv run`, changing into a
source checkout, or activating a virtual environment.

### Installation from a checkout

From a fresh checkout, prepare the same persistent user-level installation:

```shell
./install.sh
```

Both installation forms check prerequisites, acquire a complete project
snapshot, synchronize its exact locked runtime dependencies with a
project-level uv command, and verify the `yicloud` entry point. They do not
inspect or store YiCloud credentials.

### Manual development installation

For development or a deliberately checkout-local environment, use:

```shell
uv python find '>=3.11' --no-python-downloads
uv sync --locked --no-dev
uv run --locked --no-dev yicloud --version
```

`--locked` makes synchronization fail instead of silently changing the
committed `uv.lock`. This manual workflow does not create the persistent global
`yicloud` command.

### Upgrade or reinstall

Rerun the one-line installer to download the current `main` snapshot and
atomically refresh the managed installation:

```shell
curl -fsSL https://raw.githubusercontent.com/Frankstein73/yicloud-cli/main/install.sh | bash
```

From an updated checkout, `./install.sh` performs the same refresh. A failed
download or dependency synchronization restores the previous usable
installation. The Zsh PATH block and command link are reused rather than
duplicated.

### Uninstall

Run the managed installer copy with its uninstall flag:

```shell
bash "$HOME/.local/share/yicloud-cli/install.sh" --uninstall
```

This removes only the managed `~/.local/share/yicloud-cli` installation, the
managed `~/.local/bin/yicloud` symbolic link, and the marked yicloud-cli PATH
block in the Zsh configuration file. It does not remove source checkouts,
credentials, unrelated files in `~/.local`, or shared uv caches. Custom
locations set with `YICLOUD_INSTALL_ROOT`, `YICLOUD_BIN_DIR`, or
`YICLOUD_ZSH_CONFIG` must be supplied again when uninstalling.

## Authentication

Commands that call the API read credentials lazily from two environment
variables. Export them in the shell where you run the CLI:

```shell
export Access_Key_ID='your-access-key-id'
export Secret_Access_Key='your-secret-access-key'
```

Use your shell or CI system's secret manager for persistent configuration. Do
not commit credentials to the repository. Help and version commands do not read
these variables, and installation explicitly removes them from child-process
environments.

The endpoint, profile name, and output format can optionally be configured with
`YICLOUD_ENDPOINT`, `YICLOUD_PROFILE`, and `YICLOUD_OUTPUT`. Global options must
come before the resource command:

```shell
yicloud \
  --endpoint https://gate.yicloud.com \
  --profile default \
  --output json \
  custom-task --help
```

## Usage

Start with command discovery, which does not contact YiCloud:

```shell
yicloud --help
yicloud custom-task --help
yicloud development-machine --help
```

The following API examples require valid credentials, a reachable endpoint,
and identifiers from your YiCloud account.

### Custom tasks

Custom tasks use the OpenAPI `job/v1alpha1` service. A task specification is
supplied as `NAME=JSON`; `image`, `command`, and `replicas` are required, while
`env` defaults to an empty object.

```shell
yicloud custom-task create \
  --project demo \
  --name training-run \
  --task-spec 'worker={"image":"registry.example/train:1","command":["python","train.py"],"replicas":1,"env":{"MODE":"train"}}'

yicloud custom-task list --project demo --phase Running --limit 25
yicloud --output json custom-task inspect task-123 --project demo
yicloud custom-task update task-123 --project demo --priority 7
yicloud custom-task update task-123 --project demo --top
yicloud custom-task cancel task-123 task-456 --project demo
yicloud custom-task clone task-123 --project demo --target-name rerun
yicloud custom-task delete task-123 --project demo --yes
```

The API does not expose a retry action; use `clone` to create a new task from an
existing one. Run `yicloud custom-task COMMAND --help` for all supported filters
and options.

### Development machines

Every development-machine API command requires a project namespace.

```shell
# Create from an existing development environment.
yicloud development-machine create \
  --project my-project \
  --environment-id env-123 \
  --name interactive-dev \
  --lifecycle-minutes 120

# Or create directly from an image and explicit resources.
yicloud development-machine create \
  --project my-project \
  --image-ref team/dev-image:latest \
  --cpu 2 \
  --memory 4Gi \
  --env MODE=development \
  --port 8080:http:web

yicloud development-machine list --project my-project --run-state running
yicloud --output json development-machine inspect --project my-project sandbox-123
yicloud development-machine update-lifecycle \
  --project my-project sandbox-123 --mode extend --minutes 60
yicloud development-machine stop --project my-project sandbox-123
yicloud development-machine delete --project my-project sandbox-123
yicloud development-machine batch-delete \
  --project my-project sandbox-123 sandbox-456
```

The pinned SDK exposes create, list, inspect, stop, delete, batch-delete, and
lifecycle-update operations. It does not expose start or restart endpoints, so
the CLI does not advertise them. Run
`yicloud development-machine COMMAND --help` for all inputs and filters.

## Troubleshooting

### A prerequisite is missing

- `uv was not found on PATH`: install uv using its official instructions, open
  a new shell if needed, confirm `uv --version`, and rerun the installer.
- `git was not found on PATH`: install Git and confirm `git --version`.
- `Python 3.11 or newer is unavailable`: install a supported interpreter with
  your platform tools or `uv python install 3.11`, then confirm it with
  `uv python find '>=3.11' --no-python-downloads`.
- `curl` or `tar` is missing: install the named system tool. You can avoid the
  remote download by using a checkout, but checkout installation still needs
  `tar`.
- `Permission denied` for `./install.sh`: restore the executable checkout bit
  with `chmod +x install.sh`, then rerun it.

### `yicloud` is not found after installation

Open a new Zsh session or run `source "${ZDOTDIR:-$HOME}/.zshrc"`. Confirm that
`~/.local/bin` appears in `print -r -- $path` and that
`~/.local/bin/yicloud` is a symbolic link. If a custom `YICLOUD_BIN_DIR` or
`YICLOUD_ZSH_CONFIG` was used, inspect that directory or file instead.

### Credentials are missing

API commands report which of `Access_Key_ID` or `Secret_Access_Key` is absent.
Export both variables in the current shell. Confirm only that they are set,
without printing their values:

```shell
test -n "${Access_Key_ID:-}" && test -n "${Secret_Access_Key:-}" && echo 'credentials are set'
```

### Locked dependency synchronization fails

For a checkout install, confirm that `pyproject.toml` and `uv.lock` are present
and unchanged with `git status --short -- pyproject.toml uv.lock`. For a remote
install, confirm access to GitHub's raw-content and archive hosts. Then check
network access to the package index and the pinned YiCloud SDK Git repository.
Running the manual `uv sync --locked --no-dev -v` workflow in a checkout
provides detailed resolver diagnostics without involving cloud credentials. A
lock mismatch must be resolved in source control; the installer never rewrites
the lockfile.

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
