from __future__ import annotations

import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SYSTEM_PATH = "/usr/local/bin:/usr/bin:/bin"
ZSH_PATH = shutil.which("zsh")


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


def assert_fresh_zsh_can_invoke(home: Path, cwd: Path) -> None:
    assert ZSH_PATH is not None, "zsh is required for the installer end-to-end test"
    result = subprocess.run(
        [
            ZSH_PATH,
            "-ic",
            "command -v yicloud && yicloud --help && yicloud --version",
        ],
        cwd=cwd,
        env={
            "HOME": str(home),
            "ZDOTDIR": str(home),
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


def test_successful_checkout_install_is_global_in_fresh_zsh(
    installation_checkout: Path, tmp_path: Path
) -> None:
    environment = installer_environment(
        tmp_path,
        fake_tools(tmp_path),
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
    assert_fresh_zsh_can_invoke(home, tmp_path)

    uv_log = Path(environment["FAKE_UV_LOG"]).read_text(encoding="utf-8")
    assert "python find >=3.11 --no-python-downloads" in uv_log
    assert "sync --locked --no-dev --python /fake/python3.11" in uv_log
    assert str(install_root) in uv_log


def test_stdin_install_downloads_snapshot_and_is_global_in_fresh_zsh(
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
    assert_fresh_zsh_can_invoke(Path(environment["HOME"]), outside_checkout)


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
    zshrc = (Path(environment["HOME"]) / ".zshrc").read_text(encoding="utf-8")
    assert zshrc.count("# >>> yicloud-cli >>>") == 1
    assert zshrc.count("export PATH=") == 1
    uv_log = Path(environment["FAKE_UV_LOG"]).read_text(encoding="utf-8")
    assert uv_log.count("sync --locked --no-dev") == 2
    assert_fresh_zsh_can_invoke(Path(environment["HOME"]), tmp_path)


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
    assert_fresh_zsh_can_invoke(Path(environment["HOME"]), tmp_path)


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


def test_uninstall_removes_only_managed_files_and_path_block(
    installation_checkout: Path, tmp_path: Path
) -> None:
    environment = installer_environment(tmp_path, fake_tools(tmp_path))
    home = Path(environment["HOME"])
    zshrc = home / ".zshrc"
    zshrc.write_text("export KEEP_ME=yes\n", encoding="utf-8")
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
