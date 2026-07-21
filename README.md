# yicloud-cli

`yicloud-cli` is a command-line interface for managing YiCloud custom tasks and
development machines from a terminal or automation workflow. It uses the
[YiCloud OpenAPI](https://api.yicloud.com.cn/).

## Prerequisites

- Linux or macOS. Windows users can use a Linux environment such as WSL 2.
- Bash 3.2 or newer to execute the installer. Your interactive shell does not
  need to be Bash; the installed CLI works from Bash, Zsh, Fish, and other
  shells when its bin directory is on `PATH`.
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

## Quick install

If uv is not installed yet:

```shell
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install the current yicloud-cli snapshot:

```shell
curl -fsSL https://raw.githubusercontent.com/Frankstein73/yicloud-cli/main/install.sh | bash
```

The installer downloads the project snapshot, creates a persistent locked
environment in `~/.local/share/yicloud-cli`, and links the command at
`~/.local/bin/yicloud`. When that bin directory is not already on `PATH`, it
uses `uv tool update-shell` to update the configuration for the detected shell.
Open a new terminal after installation, then verify the command:

```shell
yicloud --help
yicloud --version
```

The installation command is piped to Bash only because `install.sh` is a Bash
script; it does not make Bash the required interactive shell. Once installed,
`yicloud` works from any directory without `uv run`, changing into a source
checkout, or activating a virtual environment.

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
installation. The command link and shell PATH configuration are reused rather
than duplicated. Reinstalling also migrates the PATH block written to `.zshrc`
by older yicloud-cli installers to the shell-neutral setup.

### Uninstall

Run the managed installer copy with its uninstall flag:

```shell
bash "$HOME/.local/share/yicloud-cli/install.sh" --uninstall
```

This removes only the managed `~/.local/share/yicloud-cli` installation, the
managed `~/.local/bin/yicloud` symbolic link, and any legacy yicloud-cli PATH
block written by an older installer. It does not remove source checkouts,
credentials, unrelated files in `~/.local`, shared uv caches, or PATH entries
managed by uv because other uv-installed tools may use them. Custom locations
set with `YICLOUD_INSTALL_ROOT` or `YICLOUD_BIN_DIR` must be supplied again when
uninstalling. `YICLOUD_ZSH_CONFIG` is accepted only to clean up a legacy PATH
block from an older installation.

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
yicloud sandbox --help
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

Development machines are YiCloud Workspace resources served by the
`workspace/v1alpha1` API. Phase 1 provides the baseline read path: list
Workspaces with official API filters and inspect one Workspace by its Workspace
ID.

```shell
yicloud development-machine list \
  --project my-project \
  --workspace-id workspace-123 \
  --creator alice \
  --quota-group research \
  --cpu-min 2 \
  --memory-max 32 \
  --sort-by 'CreationTime desc' \
  --limit 25

yicloud --output json development-machine inspect \
  --project my-project workspace-123
```

The pinned SDK also exposes Workspace create, edit, start, restart, stop,
transfer, and delete operations. Those Workspace lifecycle operations are
outside this phase; their absence from the CLI is a product-scope decision, not
an SDK limitation. Run `yicloud development-machine COMMAND --help` for all
read filters and inputs.

### Sandboxes

Sandboxes are separate resources served by the `sandbox/v1alpha1` API. The
operations that earlier CLI releases mislabeled as development machines remain
available under the explicit `yicloud sandbox` namespace.

```shell
yicloud sandbox create \
  --project my-project \
  --environment-id env-123 \
  --name interactive-sandbox \
  --lifecycle-minutes 120

yicloud sandbox list --project my-project --run-state running
yicloud --output json sandbox inspect --project my-project sandbox-123
yicloud sandbox update-lifecycle \
  --project my-project sandbox-123 --mode extend --minutes 60
yicloud sandbox stop --project my-project sandbox-123
yicloud sandbox delete --project my-project sandbox-123
yicloud sandbox batch-delete \
  --project my-project sandbox-123 sandbox-456
```

For compatibility, the old mutating spellings under `development-machine`
(`create`, `stop`, `delete`, `batch-delete`, and
`update-lifecycle`) remain temporarily available as hidden deprecated aliases
and print the replacement `yicloud sandbox` command. The old
`development-machine list` and `inspect` meanings are not retained because
those names now implement the official Workspace read API; use `sandbox list`
or `sandbox inspect` for Sandbox IDs.

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

Open a new terminal and confirm that the command link exists and the bin
directory is on `PATH`:

```shell
ls -l "$HOME/.local/bin/yicloud"
command -v yicloud
```

For the current Bash, Zsh, or POSIX-style shell session, add the default bin
directory temporarily with:

```shell
export PATH="$HOME/.local/bin:$PATH"
```

Fish users can run `fish_add_path ~/.local/bin`. To make the change persistent,
rerun `uv tool update-shell`, or add the equivalent command to the startup file
used by your shell. If `YICLOUD_BIN_DIR` was set during installation, use that
directory instead of `~/.local/bin`.

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
