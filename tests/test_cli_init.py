from __future__ import annotations

import pathlib

import repokit_backup.cli as cli


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

    monkeypatch.setattr(cli.repokit_common, "PROJECT_ROOT", tmp_path.resolve())
    monkeypatch.setattr(
        cli,
        "_ensure_rcloneignore_pyproject_config",
        lambda: calls.append("pyproject"),
    )

    def fake_install_rclone(path: str) -> bool:
        calls.append(path)
        return True

    bin_dir, pyproject_path = cli._bootstrap_project_runtime(fake_install_rclone)

    assert calls == ["pyproject", "./bin"]
    assert bin_dir == (tmp_path / "bin").resolve()
    assert pyproject_path == (tmp_path / cli.repokit_common.TOML_PATH).resolve()
