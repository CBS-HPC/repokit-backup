from __future__ import annotations

import subprocess


def test_ls_defaults_to_remote_root_without_mapping(monkeypatch, capsys):
    from repokit_backup import rclone

    captured = {}

    def fake_run(cmd, **_kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout="data/\nnotes.txt\n",
            stderr="",
        )

    monkeypatch.setattr(rclone, "load_registry", lambda *_args, **_kwargs: (None, None))
    monkeypatch.setattr(rclone.subprocess, "run", fake_run)

    rclone.list_remote_entries("dropbox")
    out = capsys.readouterr().out
    assert "Listing remote root" in out
    assert captured["cmd"][2] == "dropbox:"


def test_ls_defaults_to_remote_root_with_subpath_without_mapping(monkeypatch):
    from repokit_backup import rclone

    captured = {}

    def fake_run(cmd, **_kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(rclone, "load_registry", lambda *_args, **_kwargs: (None, None))
    monkeypatch.setattr(rclone.subprocess, "run", fake_run)

    rclone.list_remote_entries("dropbox", "/data")
    assert captured["cmd"][2] == "dropbox:/data"


def test_ls_preserves_leading_slash_for_unmapped_remote_subpath(monkeypatch):
    from repokit_backup import rclone

    captured = {}

    def fake_run(cmd, **_kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(rclone, "load_registry", lambda *_args, **_kwargs: (None, None))
    monkeypatch.setattr(rclone.subprocess, "run", fake_run)

    rclone.list_remote_entries("test", "/Team Folder - (LIB)")
    assert captured["cmd"][2] == "test:/Team Folder - (LIB)"


def test_ls_search_relative_pattern_uses_scoped_target(monkeypatch):
    from repokit_backup import rclone

    captured = {}

    def fake_run(cmd, **_kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        rclone,
        "load_registry",
        lambda *_args, **_kwargs: ("dropbox:mapped-root", "/tmp/local"),
    )
    monkeypatch.setattr(rclone.subprocess, "run", fake_run)

    rclone.list_remote_entries("dropbox", "/data", "file_*.txt")
    assert captured["cmd"][2] == "dropbox:mapped-root/data"
    assert "--recursive" in captured["cmd"]
    assert captured["cmd"][-1] == "file_*.txt"


def test_ls_search_absolute_pattern_anchors_to_remote_root(monkeypatch):
    from repokit_backup import rclone

    captured = {}

    def fake_run(cmd, **_kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(rclone, "load_registry", lambda *_args, **_kwargs: (None, None))
    monkeypatch.setattr(rclone.subprocess, "run", fake_run)

    rclone.list_remote_entries("dropbox", "/ignored", "/data/file_*.txt")
    assert captured["cmd"][2] == "dropbox:"
    assert captured["cmd"][-1] == "data/file_*.txt"


def test_ls_search_absolute_wildcard_from_remote_root(monkeypatch):
    from repokit_backup import rclone

    captured = {}

    def fake_run(cmd, **_kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(rclone, "load_registry", lambda *_args, **_kwargs: (None, None))
    monkeypatch.setattr(rclone.subprocess, "run", fake_run)

    rclone.list_remote_entries("dropbox", search_pattern="/*/file_*.txt")
    assert captured["cmd"][2] == "dropbox:"
    assert captured["cmd"][-1] == "*/file_*.txt"
