from __future__ import annotations


def test_pull_safeguard_when_mapping_missing_and_paths_not_provided(
    monkeypatch, capsys
):
    from repokit_backup import rclone

    monkeypatch.setattr(rclone, "install_rclone", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(rclone, "load_registry", lambda *_args, **_kwargs: (None, None))
    monkeypatch.setattr(rclone, "load_all_registry", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        rclone,
        "_rclone_transfer",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("should not transfer")),
    )

    rclone.pull_rclone(remote_name="test")
    out = capsys.readouterr().out
    assert "has no saved mapping" in out
    assert "Provide --path" in out


def test_pull_uses_explicit_paths_when_mapping_missing(monkeypatch):
    from repokit_backup import rclone

    captured = {}

    monkeypatch.setattr(rclone, "install_rclone", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(rclone, "load_registry", lambda *_args, **_kwargs: (None, None))
    monkeypatch.setattr(rclone, "load_all_registry", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(rclone.os.path, "exists", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(rclone.os, "makedirs", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        rclone,
        "_rclone_transfer",
        lambda **kwargs: captured.update(kwargs),
    )

    rclone.pull_rclone(
        remote_name="test",
        remote_path="test:/my/remote/path",
        new_path="/tmp/local",
        operation="copy",
    )
    assert captured["src"] == "test:/my/remote/path"
    assert captured["dst"] == "/tmp/local"
    assert captured["action"] == "pull"


def test_pull_accepts_remote_path_without_remote_prefix(monkeypatch):
    from repokit_backup import rclone

    captured = {}

    monkeypatch.setattr(rclone, "install_rclone", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(rclone, "load_registry", lambda *_args, **_kwargs: (None, None))
    monkeypatch.setattr(rclone, "load_all_registry", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(rclone.os.path, "exists", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(rclone.os, "makedirs", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        rclone,
        "_rclone_transfer",
        lambda **kwargs: captured.update(kwargs),
    )

    rclone.pull_rclone(
        remote_name="test",
        remote_path="/Team Folder - (LIB)",
        new_path="/tmp/local",
        operation="copy",
    )
    assert captured["src"] == "test:/Team Folder - (LIB)"
    assert captured["dst"] == "/tmp/local"
    assert captured["action"] == "pull"


def test_pull_search_is_relative_to_explicit_remote_path(monkeypatch):
    from repokit_backup import rclone

    captured = {}

    monkeypatch.setattr(rclone, "install_rclone", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(rclone, "load_registry", lambda *_args, **_kwargs: (None, None))
    monkeypatch.setattr(rclone, "load_all_registry", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(rclone.os.path, "exists", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(rclone.os, "makedirs", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        rclone,
        "_rclone_transfer",
        lambda **kwargs: captured.update(kwargs),
    )

    rclone.pull_rclone(
        remote_name="test",
        remote_path="/Team Folder - (LIB)",
        new_path="/tmp/local",
        operation="copy",
        search_pattern="taqtrade_dummy/taqtrade_202001*",
    )
    assert captured["src"] == "test:/Team Folder - (LIB)/taqtrade_dummy"
    assert captured["dst"].replace("\\", "/") == "/tmp/local/taqtrade_dummy"
    assert captured["include_patterns"] == ["taqtrade_202001*"]


def test_pull_search_absolute_pattern_from_root_preserves_structure(monkeypatch):
    from repokit_backup import rclone

    captured = {}

    monkeypatch.setattr(rclone, "install_rclone", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(rclone, "load_registry", lambda *_args, **_kwargs: (None, None))
    monkeypatch.setattr(rclone, "load_all_registry", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(rclone.os.path, "exists", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(rclone.os, "makedirs", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        rclone,
        "_rclone_transfer",
        lambda **kwargs: captured.update(kwargs),
    )

    rclone.pull_rclone(
        remote_name="test",
        new_path="/tmp/local",
        operation="copy",
        search_pattern="/Team Folder - (LIB)/taqtrade_dummy/taqtrade_202001*",
    )
    assert captured["src"] == "test:/Team Folder - (LIB)/taqtrade_dummy"
    assert captured["dst"].replace("\\", "/") == "/tmp/local/Team Folder - (LIB)/taqtrade_dummy"
    assert captured["include_patterns"] == ["taqtrade_202001*"]


def test_pull_defaults_to_remote_root_when_mapping_missing_and_only_path_given(
    monkeypatch, capsys
):
    from repokit_backup import rclone

    captured = {}

    monkeypatch.setattr(rclone, "install_rclone", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(rclone, "load_registry", lambda *_args, **_kwargs: (None, None))
    monkeypatch.setattr(rclone, "load_all_registry", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(rclone.os.path, "exists", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(rclone.os, "makedirs", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        rclone,
        "_rclone_transfer",
        lambda **kwargs: captured.update(kwargs),
    )

    rclone.pull_rclone(
        remote_name="test",
        new_path="/tmp/local",
        operation="copy",
    )
    out = capsys.readouterr().out
    assert "Defaulting pull source to remote root" in out
    assert captured["src"] == "test:"
    assert captured["dst"] == "/tmp/local"
