from __future__ import annotations

import json
from argparse import Namespace
from types import SimpleNamespace

import pytest

from repokit_backup.cli import _validate_non_interactive_add
from repokit_backup.registry import save_registry, set_remote_pin


def _fail_prompt(*_args, **_kwargs):
    raise AssertionError("non-interactive code must not prompt")


def test_non_interactive_add_validation_requires_complete_mapping():
    args = Namespace(
        mapping_mode="full",
        add_remote_path="/Team Folder - (LIB)/myproject",
        add_policy="full",
        ssh_mode=False,
        on_existing="use",
    )
    _validate_non_interactive_add(args, "C:/project")

    args.mapping_mode = "remote-only"
    with pytest.raises(ValueError, match="cannot be combined"):
        _validate_non_interactive_add(args, "C:/project")

    args.mapping_mode = "none"
    args.add_remote_path = None
    args.add_policy = None
    _validate_non_interactive_add(args, None)


def test_remote_pin_registry_state_and_clear(tmp_path):
    registry_path = tmp_path / "bin" / "rclone_remote.json"
    save_registry(
        "myproject",
        None,
        None,
        "dropbox",
        mapping_mode="none",
        json_path=str(registry_path),
    )

    assert set_remote_pin(
        "myproject", "/Team Folder - (LIB)/myproject", json_path=str(registry_path)
    )
    saved = json.loads(registry_path.read_text(encoding="utf-8"))["myproject"]
    assert saved["remote_path"] == "myproject:/Team Folder - (LIB)/myproject"
    assert saved["local_path"] is None
    assert saved["mapping_mode"] == "remote-only"
    assert saved["remote_path_ownership"] == "external"

    assert set_remote_pin("myproject", None, json_path=str(registry_path))
    cleared = json.loads(registry_path.read_text(encoding="utf-8"))["myproject"]
    assert cleared["remote_path"] is None
    assert cleared["mapping_mode"] == "none"


def test_remote_pin_refuses_to_replace_full_mapping(tmp_path, capsys):
    registry_path = tmp_path / "bin" / "rclone_remote.json"
    save_registry(
        "myproject",
        "/archive/myproject",
        str(tmp_path),
        "dropbox",
        mapping_mode="full",
        json_path=str(registry_path),
    )

    assert not set_remote_pin("myproject", "/other", json_path=str(registry_path))
    assert "will not discard it" in capsys.readouterr().out
    saved = json.loads(registry_path.read_text(encoding="utf-8"))["myproject"]
    assert saved["mapping_mode"] == "full"
    assert saved["remote_path"] == "myproject:/archive/myproject"


def test_non_interactive_folder_use_never_prompts_and_preserves_slash(monkeypatch, tmp_path):
    from repokit_backup import remotes

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("builtins.input", _fail_prompt)

    def fake_run(_cmd, **kwargs):
        if kwargs.get("capture_output"):
            return SimpleNamespace(returncode=0)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(remotes.subprocess, "run", fake_run)

    assert remotes._add_folder(
        "myproject",
        "dropbox",
        "/Team Folder - (LIB)/myproject",
        None,
        mapping_mode="remote-only",
        push_policy="full",
        on_existing="use",
    )

    saved = json.loads((tmp_path / "bin" / "rclone_remote.json").read_text(encoding="utf-8"))[
        "myproject"
    ]
    assert saved["remote_path"] == "myproject:/Team Folder - (LIB)/myproject"
    assert saved["remote_path_ownership"] == "external"


def test_setup_non_interactive_does_not_call_prompt_adapter(monkeypatch, tmp_path):
    from repokit_backup import remotes

    monkeypatch.setattr(remotes.repokit_common, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("builtins.input", _fail_prompt)
    monkeypatch.setattr(
        remotes,
        "_remote_user_info",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("interactive adapter used")),
    )
    monkeypatch.setattr(
        remotes,
        "_non_interactive_remote_info",
        lambda *_args, **_kwargs: (None, None, {"use_ssh_agent": False}),
    )
    monkeypatch.setattr(remotes, "_add_remote", lambda *_args, **_kwargs: True)

    captured = {}
    monkeypatch.setattr(
        remotes,
        "_add_folder",
        lambda *args, **kwargs: captured.update(args=args, kwargs=kwargs) or True,
    )

    assert remotes.setup_rclone(
        "myproject",
        backend="dropbox",
        non_interactive=True,
        mapping_mode="remote-only",
        remote_path="/Team Folder - (LIB)/myproject",
        push_policy="full",
        on_existing="use",
    )
    assert captured["args"][2] == "/Team Folder - (LIB)/myproject"
    assert captured["kwargs"]["mapping_mode"] == "remote-only"


def test_non_interactive_lumio_reads_and_persists_without_prompt(monkeypatch):
    from repokit_backup.remote_info import non_interactive_remote_info

    stored: dict[str, str] = {}
    monkeypatch.setattr("repokit_backup.remote_info.load_from_env", lambda key: stored.get(key))
    monkeypatch.setattr(
        "repokit_backup.remote_info.save_to_env", lambda value, key: stored.__setitem__(key, value)
    )
    monkeypatch.setattr("builtins.input", _fail_prompt)

    login, secret, options = non_interactive_remote_info(
        "lumio",
        lumio_project_id="465000001",
        lumio_access_key="ACCESS",
        lumio_secret_key="SECRET",
    )

    assert (login, secret) == ("ACCESS", "SECRET")
    assert options["lumio_project_id"] == "465000001"
    assert stored == {
        "LUMIO_PROJECT_ID": "465000001",
        "LUMIO_ACCESS_KEY": "ACCESS",
        "LUMIO_SECRET_KEY": "SECRET",
    }


def test_non_interactive_erda_reads_and_persists_password(monkeypatch):
    from repokit_backup.remote_info import non_interactive_remote_info

    stored = {"ERDA_USERNAME": "saved-user", "ERDA_PASSWORD": "saved-password"}
    monkeypatch.setattr("repokit_backup.remote_info.load_from_env", lambda key: stored.get(key))
    monkeypatch.setattr(
        "repokit_backup.remote_info.save_to_env", lambda value, key: stored.__setitem__(key, value)
    )

    login, password, options = non_interactive_remote_info("erda")

    assert (login, password) == ("saved-user", "saved-password")
    assert options["erda_auth"] == "password"


def test_push_uses_remote_pin_with_explicit_local_path(monkeypatch, tmp_path):
    from repokit_backup import rclone

    captured = {}
    monkeypatch.setattr(rclone, "install_rclone", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(rclone, "rclone_commit", None)
    monkeypatch.setattr(rclone, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(
        rclone, "load_registry", lambda *_args, **_kwargs: ("myproject:/Team Folder", None)
    )
    monkeypatch.setattr(
        rclone,
        "load_all_registry",
        lambda *_args, **_kwargs: {"myproject": {"push_policy": "full"}},
    )
    monkeypatch.setattr(rclone, "_exclude_patterns", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(rclone, "_nested_remote_excludes", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(rclone, "_rclone_transfer", lambda **kwargs: captured.update(kwargs))

    rclone.push_rclone("myproject", local_path=str(tmp_path), operation="copy")

    assert captured["src"] == str(tmp_path.resolve())
    assert captured["dst"] == "myproject:/Team Folder"


def test_pull_uses_remote_pin_with_explicit_local_path(monkeypatch, tmp_path, capsys):
    from repokit_backup import rclone

    captured = {}
    destination = tmp_path / "restore"
    monkeypatch.setattr(rclone, "install_rclone", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(rclone, "rclone_commit", None)
    monkeypatch.setattr(rclone, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(
        rclone, "load_registry", lambda *_args, **_kwargs: ("myproject:/Team Folder", None)
    )
    monkeypatch.setattr(
        rclone,
        "load_all_registry",
        lambda *_args, **_kwargs: {"myproject": {"push_policy": "full"}},
    )
    monkeypatch.setattr(rclone, "_exclude_patterns", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(rclone, "_nested_remote_excludes", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(rclone, "_rclone_transfer", lambda **kwargs: captured.update(kwargs))

    rclone.pull_rclone("myproject", new_path=str(destination), operation="copy")

    assert "Defaulting pull source" not in capsys.readouterr().out
    assert captured["src"] == "myproject:/Team Folder"
    assert captured["dst"] == str(destination)


def test_delete_never_purges_externally_owned_pin(monkeypatch):
    from repokit_backup import remotes

    commands: list[list[str]] = []
    monkeypatch.setattr(
        remotes, "load_registry", lambda *_args, **_kwargs: ("myproject:/Team", None)
    )
    monkeypatch.setattr(
        remotes,
        "load_all_registry",
        lambda *_args, **_kwargs: {
            "myproject": {"remote_type": "dropbox", "remote_path_ownership": "external"}
        },
    )
    monkeypatch.setattr(remotes, "_delete_config_if_no_remotes", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(remotes, "delete_from_registry", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        remotes.subprocess,
        "run",
        lambda command, **_kwargs: commands.append(command) or SimpleNamespace(returncode=0),
    )

    remotes._delete_single_remote("myproject")

    assert not any(command[1] == "purge" for command in commands)
    assert any(command[:3] == ["rclone", "config", "delete"] for command in commands)
