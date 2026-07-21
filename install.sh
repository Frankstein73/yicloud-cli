#!/usr/bin/env bash

set -Eeuo pipefail

readonly MINIMUM_PYTHON="3.11"
readonly DEFAULT_INSTALL_REF="main"
readonly REPOSITORY="Frankstein73/yicloud-cli"
readonly ZSH_BLOCK_BEGIN="# >>> yicloud-cli >>>"
readonly ZSH_BLOCK_END="# <<< yicloud-cli <<<"

fail() {
    printf 'yicloud-cli installer error: %s\n' "$1" >&2
    exit 1
}

note() {
    printf '%s\n' "$1"
}

command_available() {
    command -v "$1" >/dev/null 2>&1
}

require_command() {
    command_available "$1" || fail "$2"
}

path_is_absolute() {
    [[ $1 == /* ]]
}

profile_has_line() {
    local profile=$1
    local expected=$2
    local line

    [[ -f $profile ]] || return 1
    while IFS= read -r line || [[ -n $line ]]; do
        [[ $line == "$expected" ]] && return 0
    done < "$profile"
    return 1
}

escape_for_double_quotes() {
    local value=$1
    value=${value//\\/\\\\}
    value=${value//\"/\\\"}
    value=${value//\$/\\\$}
    value=${value//\`/\\\`}
    printf '%s' "$value"
}

configure_zsh_path() {
    local profile=$1
    local bin_directory=$2
    local escaped_bin
    local profile_directory
    local temporary_profile

    if profile_has_line "$profile" "$ZSH_BLOCK_BEGIN"; then
        profile_has_line "$profile" "$ZSH_BLOCK_END" || fail "the yicloud-cli PATH block in $profile is incomplete. Remove the partial block and rerun the installer."
        return 0
    fi

    profile_directory=${profile%/*}
    [[ -n $profile_directory ]] || profile_directory=/
    mkdir -p -- "$profile_directory"
    escaped_bin=$(escape_for_double_quotes "$bin_directory")

    temporary_profile=$(mktemp "${profile}.yicloud.XXXXXX")
    if [[ -f $profile ]]; then
        cp -p -- "$profile" "$temporary_profile"
    fi
    {
        printf '\n%s\n' "$ZSH_BLOCK_BEGIN"
        printf 'export PATH="%s:$PATH"\n' "$escaped_bin"
        printf '%s\n' "$ZSH_BLOCK_END"
    } >> "$temporary_profile" || {
        rm -f -- "$temporary_profile"
        fail "could not prepare the PATH update for $profile. Add $bin_directory to PATH manually and rerun the installer."
    }
    mv -f -- "$temporary_profile" "$profile" || fail "could not update $profile. Add $bin_directory to PATH manually and rerun the installer."
}

remove_zsh_path_block() {
    local profile=$1
    local temporary_profile
    local line
    local inside_block=0

    [[ -f $profile ]] || return 0
    profile_has_line "$profile" "$ZSH_BLOCK_BEGIN" || return 0

    temporary_profile=$(mktemp "${profile}.yicloud.XXXXXX")
    cp -p -- "$profile" "$temporary_profile"
    : > "$temporary_profile"

    while IFS= read -r line || [[ -n $line ]]; do
        if [[ $line == "$ZSH_BLOCK_BEGIN" ]]; then
            inside_block=1
            continue
        fi
        if [[ $line == "$ZSH_BLOCK_END" ]]; then
            inside_block=0
            continue
        fi
        (( inside_block == 1 )) || printf '%s\n' "$line" >> "$temporary_profile"
    done < "$profile"

    (( inside_block == 0 )) || {
        rm -f -- "$temporary_profile"
        fail "the yicloud-cli PATH block in $profile is incomplete. Remove the partial block manually."
    }
    mv -f -- "$temporary_profile" "$profile"
}

resolve_checkout() {
    local source_path=${BASH_SOURCE[0]-}
    local source_directory

    [[ -n $source_path && -f $source_path ]] || return 1
    if [[ $source_path != /* ]]; then
        source_path=$PWD/$source_path
    fi
    source_directory=$(cd -- "${source_path%/*}" && pwd -P)
    [[ -f $source_directory/pyproject.toml ]] || return 1
    [[ -f $source_directory/uv.lock ]] || return 1
    [[ -d $source_directory/src/yicloud_cli ]] || return 1
    printf '%s\n' "$source_directory"
}

home_directory=${HOME-}
[[ -n $home_directory ]] || fail "HOME is not set. Set HOME to your user home directory and rerun the installer."
path_is_absolute "$home_directory" || fail "HOME must be an absolute path."

data_home=${XDG_DATA_HOME:-$home_directory/.local/share}
install_root=${YICLOUD_INSTALL_ROOT:-$data_home/yicloud-cli}
bin_directory=${YICLOUD_BIN_DIR:-$home_directory/.local/bin}
zsh_config=${YICLOUD_ZSH_CONFIG:-${ZDOTDIR:-$home_directory}/.zshrc}
install_ref=${YICLOUD_INSTALL_REF:-$DEFAULT_INSTALL_REF}
archive_url=${YICLOUD_SOURCE_ARCHIVE_URL:-https://codeload.github.com/$REPOSITORY/tar.gz/refs/heads/$install_ref}
cli_link=$bin_directory/yicloud
managed_marker=$install_root/.yicloud-cli-managed

path_is_absolute "$install_root" || fail "the installation directory must be an absolute path: $install_root"
path_is_absolute "$bin_directory" || fail "the user bin directory must be an absolute path: $bin_directory"
path_is_absolute "$zsh_config" || fail "the zsh configuration path must be an absolute path: $zsh_config"
[[ $install_root != / && $bin_directory != / ]] || fail "refusing to manage a root filesystem path."
[[ $install_root != "$home_directory" && $install_root != "$data_home" && $install_root != "$bin_directory" ]] || fail "the installation directory is too broad to manage safely: $install_root"

if [[ ${1-} == "--uninstall" ]]; then
    [[ $# -eq 1 ]] || fail "usage: install.sh [--uninstall]"
    require_command rm "rm is required to uninstall yicloud-cli."
    require_command readlink "readlink is required to verify the managed CLI link."
    require_command mktemp "mktemp is required to update the zsh configuration safely."
    require_command cp "cp is required to update the zsh configuration safely."
    require_command mv "mv is required to uninstall yicloud-cli safely."

    if [[ -e $install_root ]]; then
        [[ -f $managed_marker ]] || fail "$install_root is not marked as a yicloud-cli managed installation and was not removed."
    fi

    if [[ -L $cli_link ]]; then
        link_target=$(readlink "$cli_link")
        if [[ $link_target == "$install_root/.venv/bin/yicloud" ]]; then
            rm -f -- "$cli_link"
        else
            fail "$cli_link points to an unmanaged target and was not removed."
        fi
    elif [[ -e $cli_link ]]; then
        fail "$cli_link is not a yicloud-cli managed symbolic link and was not removed."
    fi

    [[ ! -e $install_root ]] || rm -rf -- "$install_root"
    remove_zsh_path_block "$zsh_config"
    note "yicloud-cli was removed from $install_root and $cli_link."
    exit 0
fi

[[ $# -eq 0 ]] || fail "usage: install.sh [--uninstall]"

# Installation never needs cloud credentials. Keep them out of dependency
# synchronization, snapshot acquisition, and entry-point verification.
unset Access_Key_ID Secret_Access_Key

require_command uv "uv was not found on PATH. Install uv from https://docs.astral.sh/uv/getting-started/installation/ and rerun the installer."
require_command git "git was not found on PATH. Install Git so uv can fetch the locked YiCloud SDK dependency."
require_command tar "tar was not found on PATH. Install tar so the project snapshot can be prepared."
require_command mktemp "mktemp was not found on PATH. Install standard system utilities and rerun the installer."
require_command readlink "readlink was not found on PATH. Install standard system utilities and rerun the installer."
require_command mkdir "mkdir was not found on PATH. Install standard system utilities and rerun the installer."
require_command cp "cp was not found on PATH. Install standard system utilities and rerun the installer."
require_command mv "mv was not found on PATH. Install standard system utilities and rerun the installer."
require_command rm "rm was not found on PATH. Install standard system utilities and rerun the installer."
require_command ln "ln was not found on PATH. Install standard system utilities and rerun the installer."

if ! python_path=$(uv python find ">=$MINIMUM_PYTHON" --no-python-downloads); then
    fail "Python $MINIMUM_PYTHON or newer is unavailable. Install a supported Python (for example, 'uv python install $MINIMUM_PYTHON') and rerun the installer."
fi

install_parent=${install_root%/*}
[[ -n $install_parent ]] || install_parent=/
mkdir -p -- "$install_parent" "$bin_directory"

if [[ -e $install_root ]]; then
    [[ -f $managed_marker ]] || fail "$install_root already exists and is not marked as a yicloud-cli managed installation. Move it aside or choose YICLOUD_INSTALL_ROOT."
fi

if [[ -e $cli_link || -L $cli_link ]]; then
    [[ -L $cli_link ]] || fail "$cli_link already exists and is not a yicloud-cli managed symbolic link. Move it aside or choose YICLOUD_BIN_DIR."
    existing_target=$(readlink "$cli_link")
    [[ $existing_target == "$install_root/.venv/bin/yicloud" ]] || fail "$cli_link points to an unmanaged target and will not be overwritten."
fi

stage_directory=$(mktemp -d "$install_parent/.yicloud-cli-stage.XXXXXX")
backup_directory=
activated_new_install=0
installation_succeeded=0
link_replaced=0

cleanup() {
    local exit_status=$?
    trap - EXIT

    if (( installation_succeeded == 0 && activated_new_install == 1 )); then
        rm -rf -- "$install_root"
        if [[ -n $backup_directory && -e $backup_directory ]]; then
            mv -- "$backup_directory" "$install_root"
        elif (( link_replaced == 1 )) && [[ -L $cli_link ]] && [[ $(readlink "$cli_link") == "$install_root/.venv/bin/yicloud" ]]; then
            rm -f -- "$cli_link"
        fi
    fi

    [[ ! -e $stage_directory ]] || rm -rf -- "$stage_directory"
    if (( installation_succeeded == 1 )) && [[ -n $backup_directory && -e $backup_directory ]]; then
        rm -rf -- "$backup_directory"
    fi
    exit "$exit_status"
}
trap cleanup EXIT

if checkout_directory=$(resolve_checkout); then
    note "Preparing yicloud-cli from local checkout $checkout_directory..."
    (
        cd -- "$checkout_directory"
        tar -cf - install.sh pyproject.toml uv.lock README.md src
    ) | tar -xf - -C "$stage_directory"
else
    require_command curl "curl was not found on PATH. Install curl to use the remote installer, or run install.sh from a complete checkout."
    source_archive=$stage_directory/yicloud-cli.tar.gz
    note "Downloading yicloud-cli from $archive_url..."
    curl -fsSL "$archive_url" -o "$source_archive" || fail "could not download the yicloud-cli source archive. Check network access and the install URL."
    tar -xzf "$source_archive" --strip-components=1 -C "$stage_directory" || fail "the downloaded yicloud-cli source archive could not be extracted."
    rm -f -- "$source_archive"
fi

[[ -f $stage_directory/pyproject.toml ]] || fail "the project snapshot does not contain pyproject.toml."
[[ -f $stage_directory/uv.lock ]] || fail "the project snapshot does not contain uv.lock."
[[ -d $stage_directory/src/yicloud_cli ]] || fail "the project snapshot does not contain the yicloud_cli package sources."
printf 'yicloud-cli managed installation\n' > "$stage_directory/.yicloud-cli-managed"

if [[ -e $install_root ]]; then
    backup_directory=$install_parent/.yicloud-cli-backup.$$
    [[ ! -e $backup_directory ]] || fail "temporary backup path already exists: $backup_directory"
    mv -- "$install_root" "$backup_directory"
fi
mv -- "$stage_directory" "$install_root"
activated_new_install=1

note "Synchronizing the locked runtime environment with $python_path..."
(
    cd -- "$install_root"
    export UV_PROJECT_ENVIRONMENT=$install_root/.venv
    uv sync --locked --no-dev --python "$python_path"
) || {
    sync_status=$?
    printf '%s\n' "yicloud-cli installer error: locked dependency synchronization failed. Review the uv error above, then check network access and the committed pyproject.toml and uv.lock." >&2
    exit "$sync_status"
}

installed_cli=$install_root/.venv/bin/yicloud
[[ -x $installed_cli ]] || fail "dependency synchronization finished, but the expected CLI entry point was not created at $installed_cli."
"$installed_cli" --version

temporary_link=$bin_directory/.yicloud-link.$$
[[ ! -e $temporary_link && ! -L $temporary_link ]] || fail "temporary CLI link already exists: $temporary_link"
ln -s "$install_root/.venv/bin/yicloud" "$temporary_link"
mv -f -- "$temporary_link" "$cli_link"
link_replaced=1

configure_zsh_path "$zsh_config" "$bin_directory"
installation_succeeded=1

note ""
note "Installation complete."
note "The CLI is installed at $cli_link."
if [[ :$PATH: == *:$bin_directory:* ]]; then
    note "Run: yicloud --help"
else
    note "Open a new zsh session or run: source \"$zsh_config\""
    note "Then run: yicloud --help"
fi
