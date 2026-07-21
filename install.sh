#!/usr/bin/env bash

set -Eeuo pipefail

readonly MINIMUM_PYTHON="3.11"

fail() {
    printf 'yicloud-cli installer error: %s\n' "$1" >&2
    exit 1
}

script_path=${BASH_SOURCE[0]}
if [[ $script_path != /* ]]; then
    script_path=$PWD/$script_path
fi
readonly PROJECT_DIR=$(cd -- "${script_path%/*}" && pwd -P)
readonly PROJECT_ENVIRONMENT=$PROJECT_DIR/.venv

cd -- "$PROJECT_DIR"

# Installation never needs cloud credentials. Keep them out of every child
# process, including dependency synchronization and entry-point verification.
unset Access_Key_ID Secret_Access_Key

[[ -f pyproject.toml ]] || fail "pyproject.toml is missing from $PROJECT_DIR. Run this script from a complete repository checkout."
[[ -f uv.lock ]] || fail "uv.lock is missing from $PROJECT_DIR. Restore the committed lockfile before installing."

command -v uv >/dev/null 2>&1 || fail "uv was not found on PATH. Install uv from https://docs.astral.sh/uv/getting-started/installation/ and run ./install.sh again."
command -v git >/dev/null 2>&1 || fail "git was not found on PATH. Install Git so uv can fetch the locked YiCloud SDK dependency."

if ! python_path=$(uv python find ">=$MINIMUM_PYTHON" --no-python-downloads); then
    fail "Python $MINIMUM_PYTHON or newer is unavailable. Install a supported Python (for example, 'uv python install $MINIMUM_PYTHON') and run ./install.sh again."
fi

export UV_PROJECT_ENVIRONMENT=$PROJECT_ENVIRONMENT

printf 'Synchronizing yicloud-cli in %s with %s...\n' "$PROJECT_ENVIRONMENT" "$python_path"
uv sync --locked --no-dev --python "$python_path" || {
    status=$?
    printf '%s\n' "yicloud-cli installer error: locked dependency synchronization failed. Review the uv error above, then check network access and the committed pyproject.toml and uv.lock." >&2
    exit "$status"
}

readonly CLI_PATH=$PROJECT_ENVIRONMENT/bin/yicloud
[[ -x $CLI_PATH ]] || fail "dependency synchronization finished, but the expected CLI entry point was not created at $CLI_PATH."

"$CLI_PATH" --version
printf '\nInstallation complete. Run:\n  %s --help\n' "$CLI_PATH"
