from __future__ import annotations


def test_search_include_patterns_normalizes_root_prefix():
    from repokit_backup import rclone

    assert rclone._search_include_patterns("/data/**/*.parquet") == ["data/**/*.parquet"]
    assert rclone._search_include_patterns("/*/file_*.txt") == ["*/file_*.txt"]
    assert rclone._search_include_patterns("data/") == ["data/**"]
    assert rclone._search_include_patterns(None) == []


def test_push_search_passes_include_pattern_without_changing_source(monkeypatch):
    from repokit_backup import rclone

    captured = {}

    monkeypatch.setattr(rclone, "install_rclone", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        rclone,
        "load_registry",
        lambda *_args, **_kwargs: ("dropbox-main:rclone-backup/myproject", "/work/myproject"),
    )
    monkeypatch.setattr(
        rclone,
        "load_all_registry",
        lambda *_args, **_kwargs: {
            "dropbox-main": {
                "remote_path": "dropbox-main:rclone-backup/myproject",
                "local_path": "/work/myproject",
                "push_policy": "full",
            }
        },
    )
    monkeypatch.setattr(rclone, "_exclude_patterns", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(rclone, "_nested_remote_excludes", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(rclone, "_rclone_transfer", lambda **kwargs: captured.update(kwargs))

    rclone.push_rclone(
        remote_name="dropbox-main",
        operation="copy",
        search_pattern="/data/**/*.parquet",
    )

    assert captured["src"] == "/work/myproject"
    assert captured["dst"] == "dropbox-main:rclone-backup/myproject"
    assert captured["include_patterns"] == ["data/**/*.parquet"]


def test_pull_search_passes_include_pattern_with_remote_root_fallback(monkeypatch, capsys):
    from repokit_backup import rclone

    captured = {}

    monkeypatch.setattr(rclone, "install_rclone", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(rclone, "load_registry", lambda *_args, **_kwargs: (None, None))
    monkeypatch.setattr(rclone, "load_all_registry", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(rclone.os.path, "exists", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(rclone.os, "makedirs", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(rclone, "_rclone_transfer", lambda **kwargs: captured.update(kwargs))

    rclone.pull_rclone(
        remote_name="dropbox-main",
        new_path="/tmp/restore",
        operation="copy",
        search_pattern="/data/**/*.parquet",
    )

    out = capsys.readouterr().out
    assert "Defaulting pull source to remote root" in out
    assert captured["src"] == "dropbox-main:"
    assert captured["dst"] == "/tmp/restore"
    assert captured["include_patterns"] == ["data/**/*.parquet"]
