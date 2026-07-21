from __future__ import annotations

import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SYSTEM_PATH = "/usr/local/bin:/usr/bin:/bin"


@pytest.fixture
def installation_checkout(tmp_path: Path) -> Path:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    shutil.copy2(PROJECT_ROOT / "install.sh", checkout / "install.sh")
    shutil.copy2(PROJECT_ROOT / "README.md", checkout / "README.md")
    (checkout / "pyproject.toml").write_text(
        '[project]\nname = "yicloud-cli"\nrequires-python = ">=3.11"\n',
        encoding="utf-8",
    )
    (checkout / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    package = checkout / "src/yicloud_cli"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    return checkout


@pytest.fixture
def source_archive(installation_checkout: Path, tmp_path: Path) -> Path:
    archive_root = tmp_path / "archive-root"
    snapshot = archive_root / "yicloud-cli-test"
    shutil.copytree(installation_checkout, snapshot)
    archive = tmp_path / "source.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(snapshot, arcname=snapshot.name)
    return archive


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def fake_tools(
    tmp_path: Path,
    *,
    include_uv: bool = True,
    include_curl: bool = False,
) -> Path:
    executable_directory = tmp_path / "fake-bin"
    executable_directory.mkdir(exist_ok=True)

    if include_uv:
        write_executable(
            executable_directory / "uv",
            """#!/bin/bash
set -eu
printf '%s|%s\n' "$PWD" "$*" >> "$FAKE_UV_LOG"
if [[ ${1-} == python && ${2-} == find ]]; then
    [[ -z ${Access_Key_ID-} ]]
    [[ -z ${Secret_Access_Key-} ]]
    if [[ ${FAKE_UV_PYTHON_FAILURE-0} == 1 ]]; then
        exit 2
    fi
    printf '%s\n' /fake/python3.11
    exit 0
fi
if [[ ${1-} == sync ]]; then
    [[ -z ${Access_Key_ID-} ]]
    [[ -z ${Secret_Access_Key-} ]]
    if [[ -n ${FAKE_UV_SYNC_EXIT-} ]]; then
        exit "$FAKE_UV_SYNC_EXIT"
    fi
    /bin/mkdir -p "$UV_PROJECT_ENVIRONMENT/bin"
    /usr/bin/printf '%s\n' \
        '#!/bin/bash' \
        'case "${1-}" in' \
        '  --version) printf "yicloud, version 0.1.0\\n" ;;' \
        '  --help) printf "Usage: yicloud [OPTIONS] COMMAND [ARGS]...\\n" ;;' \
        '  *) printf "fake yicloud\\n" ;;' \
        'esac' > "$UV_PROJECT_ENVIRONMENT/bin/yicloud"
    /bin/chmod +x "$UV_PROJECT_ENVIRONMENT/bin/yicloud"
    exit 0
fi
if [[ ${1-} == tool && ${2-} == update-shell ]]; then
    bin_directory=${UV_TOOL_BIN_DIR:-$HOME/.local/bin}
    case ${SHELL##*/} in
        bash)
            for profile in "$HOME/.bash_profile" "$HOME/.bashrc"; do
                line=$(/usr/bin/printf 'export PATH="%s:$PATH"' "$bin_directory")
                if [[ ! -f $profile ]] || ! /usr/bin/grep -Fqx "$line" "$profile"; then
                    /usr/bin/printf '# uv\n%s\n' "$line" >> "$profile"
                fi
            done
            ;;
        zsh)
            profile=${ZDOTDIR:-$HOME}/.zshenv
            line=$(/usr/bin/printf 'export PATH="%s:$PATH"' "$bin_directory")
            if [[ ! -f $profile ]] || ! /usr/bin/grep -Fqx "$line" "$profile"; then
                /usr/bin/printf '# uv\n%s\n' "$line" >> "$profile"
            fi
            ;;
        fish)
            profile=${XDG_CONFIG_HOME:-$HOME/.config}/fish/config.fish
            /bin/mkdir -p "${profile%/*}"
            line=$(/usr/bin/printf 'fish_add_path "%s"' "$bin_directory")
            if [[ ! -f $profile ]] || ! /usr/bin/grep -Fqx "$line" "$profile"; then
                /usr/bin/printf '# uv\n%s\n' "$line" >> "$profile"
            fi
            ;;
        *) exit 2 ;;
    esac
    exit 0
fi
exit 64
""",
        )

    if include_curl:
        write_executable(
            executable_directory / "curl",
            """#!/bin/bash
set -eu
[[ -z ${Access_Key_ID-} ]]
[[ -z ${Secret_Access_Key-} ]]
printf '%s\n' "$*" >> "$FAKE_CURL_LOG"
output=
while [[ $# -gt 0 ]]; do
    if [[ $1 == -o ]]; then
        output=$2
        shift 2
    else
        shift
    fi
done
[[ -n $output ]]
/bin/cp "$FAKE_SOURCE_ARCHIVE" "$output"
""",
        )

    return executable_directory


def installer_environment(
    tmp_path: Path,
    executable_directory: Path,
    **overrides: str,
) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return {
        "HOME": str(home),
        "ZDOTDIR": str(home),
        "SHELL": "/bin/bash",
        "PATH": f"{executable_directory}:{SYSTEM_PATH}",
        "FAKE_UV_LOG": str(tmp_path / "uv.log"),
        "FAKE_CURL_LOG": str(tmp_path / "curl.log"),
        **overrides,
    }


def run_checkout_installer(
    checkout: Path,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(checkout / "install.sh")],
        cwd=checkout.parent,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def run_stdin_installer(
    script: Path,
    cwd: Path,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash"],
        cwd=cwd,
        env=environment,
        input=script.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        check=False,
    )


def assert_fresh_shell_can_invoke(home: Path, cwd: Path, shell_path: str) -> None:
    result = subprocess.run(
        [
            shell_path,
            "-lic",
            "command -v yicloud && yicloud --help && yicloud --version",
        ],
        cwd=cwd,
        env={
            "HOME": str(home),
            "ZDOTDIR": str(home),
            "SHELL": shell_path,
            "PATH": SYSTEM_PATH,
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert str(home / ".local/bin/yicloud") in result.stdout
    assert "Usage: yicloud" in result.stdout
    assert "yicloud, version 0.1.0" in result.stdout


@pytest.mark.parametrize(
    "shell_path",
    [
        "/bin/bash",
        pytest.param(
            shutil.which("zsh") or "zsh",
            marks=pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh unavailable"),
        ),
    ],
)
def test_successful_checkout_install_is_global_in_detected_shell(
    installation_checkout: Path, tmp_path: Path, shell_path: str
) -> None:
    environment = installer_environment(
        tmp_path,
        fake_tools(tmp_path),
        SHELL=shell_path,
        Access_Key_ID="installer-access-key-sentinel",
        Secret_Access_Key="installer-secret-key-sentinel",
    )

    result = run_checkout_installer(installation_checkout, environment)

    assert result.returncode == 0, result.stderr
    assert "Installation complete" in result.stdout
    assert "installer-access-key-sentinel" not in result.stdout + result.stderr
    assert "installer-secret-key-sentinel" not in result.stdout + result.stderr
    home = Path(environment["HOME"])
    install_root = home / ".local/share/yicloud-cli"
    assert (install_root / "pyproject.toml").is_file()
    assert (install_root / "uv.lock").is_file()
    assert (install_root / ".venv/bin/yicloud").is_file()
    assert (home / ".local/bin/yicloud").resolve() == (
        install_root / ".venv/bin/yicloud"
    )
    assert_fresh_shell_can_invoke(home, tmp_path, shell_path)

    uv_log = Path(environment["FAKE_UV_LOG"]).read_text(encoding="utf-8")
    assert "python find >=3.11 --no-python-downloads" in uv_log
    assert "sync --locked --no-dev --python /fake/python3.11" in uv_log
    assert "tool update-shell" in uv_log
    assert str(install_root) in uv_log


def test_stdin_install_downloads_snapshot_and_is_global_in_fresh_bash(
    installation_checkout: Path,
    source_archive: Path,
    tmp_path: Path,
) -> None:
    environment = installer_environment(
        tmp_path,
        fake_tools(tmp_path, include_curl=True),
        FAKE_SOURCE_ARCHIVE=str(source_archive),
    )
    outside_checkout = tmp_path / "outside-checkout"
    outside_checkout.mkdir()

    result = run_stdin_installer(
        installation_checkout / "install.sh", outside_checkout, environment
    )

    assert result.returncode == 0, result.stderr
    assert "Downloading yicloud-cli" in result.stdout
    assert "Installation complete" in result.stdout
    assert Path(environment["FAKE_CURL_LOG"]).read_text(encoding="utf-8")
    assert_fresh_shell_can_invoke(
        Path(environment["HOME"]), outside_checkout, environment["SHELL"]
    )


def test_missing_uv_has_an_actionable_error(
    installation_checkout: Path, tmp_path: Path
) -> None:
    environment = installer_environment(
        tmp_path,
        fake_tools(tmp_path, include_uv=False),
    )

    result = run_checkout_installer(installation_checkout, environment)

    assert result.returncode == 1
    assert "uv was not found on PATH" in result.stderr
    assert "docs.astral.sh/uv" in result.stderr


def test_repeat_install_refreshes_managed_files_and_keeps_path_idempotent(
    installation_checkout: Path, tmp_path: Path
) -> None:
    environment = installer_environment(tmp_path, fake_tools(tmp_path))
    first = run_checkout_installer(installation_checkout, environment)
    installed_readme = Path(environment["HOME"]) / ".local/share/yicloud-cli/README.md"
    installed_readme.write_text("stale installation", encoding="utf-8")

    second = run_checkout_installer(installation_checkout, environment)

    assert first.returncode == second.returncode == 0
    assert installed_readme.read_text(encoding="utf-8") == (
        installation_checkout / "README.md"
    ).read_text(encoding="utf-8")
    bashrc = (Path(environment["HOME"]) / ".bashrc").read_text(encoding="utf-8")
    assert bashrc.count("# uv") == 1
    assert bashrc.count("export PATH=") == 1
    uv_log = Path(environment["FAKE_UV_LOG"]).read_text(encoding="utf-8")
    assert uv_log.count("sync --locked --no-dev") == 2
    assert uv_log.count("tool update-shell") == 2
    assert_fresh_shell_can_invoke(
        Path(environment["HOME"]), tmp_path, environment["SHELL"]
    )


def test_sync_failure_propagates_and_preserves_previous_install(
    installation_checkout: Path, tmp_path: Path
) -> None:
    tools = fake_tools(tmp_path)
    environment = installer_environment(tmp_path, tools)
    first = run_checkout_installer(installation_checkout, environment)
    assert first.returncode == 0

    failed_environment = {
        **environment,
        "FAKE_UV_SYNC_EXIT": "23",
    }
    failed = run_checkout_installer(installation_checkout, failed_environment)

    assert failed.returncode == 23
    assert "Installation complete" not in failed.stdout
    assert "locked dependency synchronization failed" in failed.stderr
    assert_fresh_shell_can_invoke(
        Path(environment["HOME"]), tmp_path, environment["SHELL"]
    )


def test_missing_supported_python_has_an_actionable_error(
    installation_checkout: Path, tmp_path: Path
) -> None:
    environment = installer_environment(
        tmp_path,
        fake_tools(tmp_path),
        FAKE_UV_PYTHON_FAILURE="1",
    )

    result = run_checkout_installer(installation_checkout, environment)

    assert result.returncode == 1
    assert "Python 3.11 or newer is unavailable" in result.stderr
    assert "uv python install 3.11" in result.stderr


def test_uninstall_removes_managed_files_and_legacy_path_block_only(
    installation_checkout: Path, tmp_path: Path
) -> None:
    environment = installer_environment(tmp_path, fake_tools(tmp_path))
    home = Path(environment["HOME"])
    zshrc = home / ".zshrc"
    zshrc.write_text(
        "export KEEP_ME=yes\n"
        "# >>> yicloud-cli >>>\n"
        'export PATH="/legacy/.local/bin:$PATH"\n'
        "# <<< yicloud-cli <<<\n",
        encoding="utf-8",
    )
    installed = run_checkout_installer(installation_checkout, environment)
    assert installed.returncode == 0

    unrelated = home / ".local/bin/unrelated"
    unrelated.write_text("keep", encoding="utf-8")
    result = subprocess.run(
        ["/bin/bash", str(installation_checkout / "install.sh"), "--uninstall"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not (home / ".local/share/yicloud-cli").exists()
    assert not (home / ".local/bin/yicloud").exists()
    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert zshrc.read_text(encoding="utf-8").strip() == "export KEEP_ME=yes"
    assert "# uv" in (home / ".bashrc").read_text(encoding="utf-8")


def test_unknown_shell_keeps_install_and_prints_manual_path_guidance(
    installation_checkout: Path, tmp_path: Path
) -> None:
    environment = installer_environment(
        tmp_path,
        fake_tools(tmp_path),
        SHELL="/bin/unknown-shell",
    )

    result = run_checkout_installer(installation_checkout, environment)

    assert result.returncode == 0, result.stderr
    assert "shell PATH could not be updated automatically" in result.stdout
    assert "Add " in result.stdout and " to PATH" in result.stdout
    cli = Path(environment["HOME"]) / ".local/bin/yicloud"
    direct = subprocess.run(
        [str(cli), "--help"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert direct.returncode == 0
    assert "Usage: yicloud" in direct.stdout


def test_fish_path_configuration_uses_fish_add_path(
    installation_checkout: Path, tmp_path: Path
) -> None:
    environment = installer_environment(
        tmp_path,
        fake_tools(tmp_path),
        SHELL="/usr/bin/fish",
        XDG_CONFIG_HOME=str(tmp_path / "home/.config"),
    )

    result = run_checkout_installer(installation_checkout, environment)

    assert result.returncode == 0, result.stderr
    fish_config = Path(environment["XDG_CONFIG_HOME"]) / "fish/config.fish"
    assert (
        f'fish_add_path "{environment["HOME"]}/.local/bin"'
        in fish_config.read_text(encoding="utf-8")
    )


def test_reinstall_migrates_legacy_zsh_block_to_detected_shell(
    installation_checkout: Path, tmp_path: Path
) -> None:
    environment = installer_environment(tmp_path, fake_tools(tmp_path))
    home = Path(environment["HOME"])
    zshrc = home / ".zshrc"
    zshrc.write_text(
        "export KEEP_ME=yes\n"
        "# >>> yicloud-cli >>>\n"
        'export PATH="/legacy/.local/bin:$PATH"\n'
        "# <<< yicloud-cli <<<\n",
        encoding="utf-8",
    )

    result = run_checkout_installer(installation_checkout, environment)

    assert result.returncode == 0, result.stderr
    assert "Migrated the legacy yicloud-cli Zsh PATH block" in result.stdout
    assert zshrc.read_text(encoding="utf-8").strip() == "export KEEP_ME=yes"
    assert "# uv" in (home / ".bashrc").read_text(encoding="utf-8")
