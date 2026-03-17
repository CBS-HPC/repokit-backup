from __future__ import annotations

import pathlib

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
