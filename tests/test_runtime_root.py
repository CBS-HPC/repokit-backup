from __future__ import annotations

import pathlib

import repokit_common
import repokit_backup.rclone as rclone


def test_install_rclone_uses_runtime_project_root(
    monkeypatch,
    tmp_path: pathlib.Path,
):
    saved: dict[str, str] = {}

    monkeypatch.setattr(rclone.repokit_common, "PROJECT_ROOT", tmp_path.resolve())
    monkeypatch.setattr(rclone, "is_installed", lambda *args, **kwargs: True)
    monkeypatch.setattr(rclone, "exe_to_path", lambda *args, **kwargs: True)
    monkeypatch.setattr(rclone, "load_from_env", lambda key: None)
    monkeypatch.setattr(rclone, "save_to_env", lambda value, key: saved.__setitem__(key, value))
    monkeypatch.delenv("RCLONE", raising=False)
    monkeypatch.delenv("RCLONE_CONFIG", raising=False)

    ok = rclone.install_rclone("./bin")

    assert ok is True
    assert saved["RCLONE_CONFIG"] == str((tmp_path / "bin" / "rclone.conf").resolve())


def test_install_rclone_replaces_external_config_path(monkeypatch, tmp_path: pathlib.Path):
    saved: dict[str, str] = {}
    external_config = tmp_path.parent / "other-project" / "rclone.conf"

    monkeypatch.setattr(rclone.repokit_common, "PROJECT_ROOT", tmp_path.resolve())
    monkeypatch.setattr(rclone, "is_installed", lambda *args, **kwargs: True)
    monkeypatch.setattr(rclone, "exe_to_path", lambda *args, **kwargs: True)
    monkeypatch.setattr(rclone, "load_from_env", lambda _key: str(external_config))
    monkeypatch.setattr(rclone, "save_to_env", lambda value, key: saved.__setitem__(key, value))
    monkeypatch.delenv("RCLONE", raising=False)
    monkeypatch.delenv("RCLONE_CONFIG", raising=False)

    assert rclone.install_rclone("./bin") is True
    assert saved["RCLONE_CONFIG"] == str((tmp_path / "bin" / "rclone.conf").resolve())


def test_bootstrap_adds_runtime_state_to_gitignore(monkeypatch, tmp_path: pathlib.Path):
    import repokit_backup.cli as cli

    monkeypatch.setattr(repokit_common, "PROJECT_ROOT", tmp_path.resolve())
    monkeypatch.setattr(cli, "_ensure_rcloneignore_pyproject_config", lambda: None)

    cli._bootstrap_project_runtime(lambda _path: True)

    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == (
        "# Project-local repokit-backup runtime state\n.env\nbin/\n"
    )
