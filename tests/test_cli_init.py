from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import repokit_backup.cli as cli
import repokit_common


def test_resolve_cli_project_root_uses_cwd_for_init(
    monkeypatch,
    tmp_path: pathlib.Path,
):
    monkeypatch.chdir(tmp_path)

    resolved = cli._resolve_cli_project_root(None, command="init")

    assert resolved == tmp_path.resolve()


def test_resolve_cli_project_root_respects_explicit_root(tmp_path: pathlib.Path):
    resolved = cli._resolve_cli_project_root(str(tmp_path), command="init")

    assert resolved == tmp_path.resolve()


def test_bootstrap_project_runtime_creates_expected_paths(
    monkeypatch,
    tmp_path: pathlib.Path,
):
    calls: list[str] = []

    monkeypatch.setattr(repokit_common, "PROJECT_ROOT", tmp_path.resolve())
    monkeypatch.setattr(
        cli,
        "_ensure_rcloneignore_pyproject_config",
        lambda: calls.append("pyproject"),
    )
    monkeypatch.setattr(cli, "_ensure_runtime_gitignore", lambda: calls.append("gitignore"))

    def fake_install_rclone(path: str) -> bool:
        calls.append(path)
        return True

    bin_dir, pyproject_path = cli._bootstrap_project_runtime(fake_install_rclone)

    assert calls == ["gitignore", "pyproject", "./bin"]
    assert bin_dir == (tmp_path / "bin").resolve()
    assert pyproject_path == (tmp_path / repokit_common.TOML_PATH).resolve()


def test_explicit_project_root_is_active_before_common_is_imported(tmp_path: pathlib.Path):
    source_root = pathlib.Path(__file__).resolve().parents[1]
    common_source = source_root.parent / "repokit-common" / "src"
    explicit_root = tmp_path / "explicit-project"
    explicit_root.mkdir()
    code = """
import sys
from pathlib import Path

import repokit_backup.cli as cli

assert 'repokit_common' not in sys.modules
root = Path(sys.argv[1]).resolve()
cli._bootstrap_project_runtime = lambda _installer: (root / 'bin', root / 'pyproject.toml')
sys.argv = ['repokit-backup', '--project-root', str(root), 'init']
cli.main()

import repokit_common
import repokit_common.base
import repokit_common.secretstore
import repokit_common.tomlutils

assert repokit_common.PROJECT_ROOT == root
assert repokit_common.base.PROJECT_ROOT == root
assert repokit_common.secretstore.PROJECT_ROOT == root
assert repokit_common.tomlutils.PROJECT_ROOT == root
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join((str(source_root / "src"), str(common_source)))

    result = subprocess.run(
        [sys.executable, "-c", code, str(explicit_root)],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert result.returncode == 0, result.stderr
