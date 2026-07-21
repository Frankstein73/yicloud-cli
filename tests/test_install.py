from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def installation_checkout(tmp_path: Path) -> Path:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    shutil.copy2(PROJECT_ROOT / "install.sh", checkout / "install.sh")
    (checkout / "pyproject.toml").write_text(
        '[project]\nname = "yicloud-cli"\nrequires-python = ">=3.11"\n',
        encoding="utf-8",
    )
    (checkout / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    return checkout


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def fake_path(tmp_path: Path, *, include_uv: bool = True) -> Path:
    executable_directory = tmp_path / "bin"
    executable_directory.mkdir()
    write_executable(executable_directory / "git", "#!/bin/bash\nexit 0\n")
    if include_uv:
        write_executable(
            executable_directory / "uv",
            """#!/bin/bash
set -eu
printf '%s\\n' "$*" >> "$FAKE_UV_LOG"
if [[ ${1-} == python && ${2-} == find ]]; then
    [[ -z ${Access_Key_ID-} ]]
    [[ -z ${Secret_Access_Key-} ]]
    if [[ ${FAKE_UV_PYTHON_FAILURE-0} == 1 ]]; then
        exit 2
    fi
    printf '%s\\n' /fake/python3.11
    exit 0
fi
if [[ ${1-} == sync ]]; then
    [[ -z ${Access_Key_ID-} ]]
    [[ -z ${Secret_Access_Key-} ]]
    if [[ -n ${FAKE_UV_SYNC_EXIT-} ]]; then
        exit "$FAKE_UV_SYNC_EXIT"
    fi
    /bin/mkdir -p "$UV_PROJECT_ENVIRONMENT/bin"
    printf '#!/bin/bash\\nprintf "yicloud, version 0.1.0\\n"\\n' > "$UV_PROJECT_ENVIRONMENT/bin/yicloud"
    /bin/chmod +x "$UV_PROJECT_ENVIRONMENT/bin/yicloud"
    exit 0
fi
exit 64
""",
        )
    return executable_directory


def run_installer(
    checkout: Path,
    executable_directory: Path,
    log_path: Path,
    **environment_overrides: str,
) -> subprocess.CompletedProcess[str]:
    environment = {
        "PATH": str(executable_directory),
        "FAKE_UV_LOG": str(log_path),
        **environment_overrides,
    }
    return subprocess.run(
        ["/bin/bash", str(checkout / "install.sh")],
        cwd=checkout.parent,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_successful_installation_uses_locked_project_sync(
    installation_checkout: Path, tmp_path: Path
) -> None:
    log_path = tmp_path / "uv.log"

    result = run_installer(
        installation_checkout,
        fake_path(tmp_path),
        log_path,
        Access_Key_ID="installer-access-key-sentinel",
        Secret_Access_Key="installer-secret-key-sentinel",
    )

    assert result.returncode == 0
    assert "yicloud, version 0.1.0" in result.stdout
    assert "Installation complete" in result.stdout
    assert "installer-access-key-sentinel" not in result.stdout + result.stderr
    assert "installer-secret-key-sentinel" not in result.stdout + result.stderr
    assert (installation_checkout / ".venv/bin/yicloud").is_file()
    assert log_path.read_text(encoding="utf-8").splitlines() == [
        "python find >=3.11 --no-python-downloads",
        "sync --locked --no-dev --python /fake/python3.11",
    ]


def test_missing_uv_has_an_actionable_error(
    installation_checkout: Path, tmp_path: Path
) -> None:
    result = run_installer(
        installation_checkout,
        fake_path(tmp_path, include_uv=False),
        tmp_path / "unused.log",
    )

    assert result.returncode == 1
    assert "uv was not found on PATH" in result.stderr
    assert "docs.astral.sh/uv" in result.stderr


def test_repeat_installation_preserves_unmanaged_environment_files(
    installation_checkout: Path, tmp_path: Path
) -> None:
    log_path = tmp_path / "uv.log"
    executable_directory = fake_path(tmp_path)
    first = run_installer(installation_checkout, executable_directory, log_path)
    marker = installation_checkout / ".venv/preserve-me"
    marker.write_text("unchanged", encoding="utf-8")

    second = run_installer(installation_checkout, executable_directory, log_path)

    assert first.returncode == second.returncode == 0
    assert marker.read_text(encoding="utf-8") == "unchanged"
    assert log_path.read_text(encoding="utf-8").count("sync --locked --no-dev") == 2


def test_sync_failure_status_is_propagated(
    installation_checkout: Path, tmp_path: Path
) -> None:
    result = run_installer(
        installation_checkout,
        fake_path(tmp_path),
        tmp_path / "uv.log",
        FAKE_UV_SYNC_EXIT="23",
    )

    assert result.returncode == 23
    assert "Installation complete" not in result.stdout
    assert "locked dependency synchronization failed" in result.stderr
    assert not (installation_checkout / ".venv/bin/yicloud").exists()


def test_missing_supported_python_has_an_actionable_error(
    installation_checkout: Path, tmp_path: Path
) -> None:
    result = run_installer(
        installation_checkout,
        fake_path(tmp_path),
        tmp_path / "uv.log",
        FAKE_UV_PYTHON_FAILURE="1",
    )

    assert result.returncode == 1
    assert "Python 3.11 or newer is unavailable" in result.stderr
    assert "uv python install 3.11" in result.stderr
