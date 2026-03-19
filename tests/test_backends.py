from __future__ import annotations

import pathlib

import pytest

from repokit_backup.cli import _resolved_add_backend
from repokit_backup.remote_info import (
    _lumio_remote_info,
    _lumip_remote_info,
    _oauth_remote_info,
    _validate_lumip_base_path,
)
from repokit_backup.remote_types import normalize_backend, resolve_backend


def test_backend_canonicalization_aliases():
    assert normalize_backend("lumi-o") == "lumio"
    assert normalize_backend("lumio") == "lumio"
    assert normalize_backend("lumi-p") == "lumip"
    assert normalize_backend("lumi-f") == "lumip"
    assert normalize_backend("gdrive") == "drive"


def test_backend_resolution_precedence():
    assert resolve_backend("lumio", "dropbox-main") == "lumio"
    assert resolve_backend(None, "lumi-f-data") == "lumip"
    assert _resolved_add_backend("lumi-o", "dropbox-main") == "lumio"


def test_add_requires_explicit_backend():
    with pytest.raises(ValueError, match="--backend is required"):
        _resolved_add_backend(None, "lumip-data")


def test_lumio_remote_keeps_alias_and_persists_env(monkeypatch: pytest.MonkeyPatch):
    env_store: dict[str, str] = {}

    monkeypatch.setattr("repokit_backup.remote_info.load_from_env", lambda key: env_store.get(key))
    monkeypatch.setattr(
        "repokit_backup.remote_info.save_to_env",
        lambda value, key: env_store.__setitem__(key, value),
    )

    answers = iter(
        [
            "465000001",  # project id
            "ACCESS123",  # access key
            "",  # create mapping default yes
            "rclone-backup/myrepo",  # base folder
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr("getpass.getpass", lambda _: "SECRET456")

    remote_name, access_key, secret_key, base_folder = _lumio_remote_info(
        "teamdata",
        "myrepo",
        pathlib.Path.cwd(),
    )
    assert remote_name == "teamdata"
    assert access_key == "ACCESS123"
    assert secret_key == "SECRET456"
    assert base_folder == "rclone-backup/myrepo"
    assert env_store["LUMIO_PROJECT_ID"] == "465000001"
    assert env_store["LUMIO_ACCESS_KEY"] == "ACCESS123"
    assert env_store["LUMIO_SECRET_KEY"] == "SECRET456"
    assert env_store["LUMIO_DEFAULT_BASE"] == "rclone-backup/myrepo"


def test_lumip_path_validation():
    assert _validate_lumip_base_path("/scratch/123") == "/scratch/123"
    with pytest.raises(ValueError):
        _validate_lumip_base_path("scratch/123")
    with pytest.raises(ValueError):
        _validate_lumip_base_path("/scratch/123/../bad")
    with pytest.raises(ValueError):
        _validate_lumip_base_path("/project/123", expected_prefix="/scratch/123")


def test_lumip_selection_and_env_persistence(monkeypatch: pytest.MonkeyPatch):
    env_store = {
        "LUMIP_PROJECT_ID": "465000002",
        "LUMIP_USERNAME": "alice",
        "LUMIP_BASE_PATH": "/scratch/465000002",
        "LUMIP_SSH_KEY_PATH": "/home/alice/.ssh/id_ed25519",
    }

    monkeypatch.setattr("repokit_backup.remote_info.load_from_env", lambda key: env_store.get(key))
    monkeypatch.setattr(
        "repokit_backup.remote_info.save_to_env",
        lambda value, key: env_store.__setitem__(key, value),
    )
    monkeypatch.setattr(
        "repokit_backup.remote_info.detect_existing_ssh_key",
        lambda *_args, **_kwargs: "/home/alice/.ssh/id_ed25519",
    )
    monkeypatch.setattr(
        pathlib.Path,
        "exists",
        lambda self: str(self).replace("\\", "/") == "/home/alice/.ssh/id_ed25519",
    )

    answers = iter(
        [
            "",  # keep project id default
            "",  # keep username default
            "",  # keep SSH key default
            "",  # create mapping default yes
            "4",  # flash storage class
            "",  # add repo suffix default yes
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    remote_name, username, _, base_folder = _lumip_remote_info(
        "dataset-store",
        "myrepo",
        pathlib.Path.cwd(),
    )

    assert remote_name == "dataset-store"
    assert username == "alice"
    assert base_folder.endswith("/myrepo")
    assert env_store["LUMIP_PROJECT_ID"] == "465000002"
    assert env_store["LUMIP_USERNAME"] == "alice"
    assert env_store["LUMIP_BASE_PATH"] == "/flash/465000002"
    assert env_store["LUMIP_SSH_KEY_PATH"].replace("\\", "/") == "/home/alice/.ssh/id_ed25519"


def test_add_lumip_remote_prefers_key_file(monkeypatch: pytest.MonkeyPatch):
    from repokit_backup import remotes

    captured = {}

    monkeypatch.setattr(
        "repokit_backup.remotes.load_from_env",
        lambda key: {"LUMIP_HOST": "lumi.csc.fi", "LUMIP_PORT": "22"}.get(key),
    )
    monkeypatch.setattr("repokit_backup.remotes.save_to_env", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "repokit_backup.remotes.detect_existing_ssh_key",
        lambda *_args, **_kwargs: "/home/alice/.ssh/id_ed25519",
    )

    def fake_run(cmd, **_kwargs):
        captured["cmd"] = cmd
        return None

    monkeypatch.setattr(remotes.subprocess, "run", fake_run)

    remotes._add_lumip_remote("lumip_test", "alice")

    assert "key_file" in captured["cmd"]
    assert "/home/alice/.ssh/id_ed25519" in captured["cmd"]
    assert "use_agent" not in captured["cmd"]


def test_oauth_remote_info_can_skip_mapping(monkeypatch: pytest.MonkeyPatch):
    answers = iter(["n"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    remote_name, _, _, base_folder = _oauth_remote_info(
        "dropbox-main",
        "myrepo",
        pathlib.Path.cwd(),
    )

    assert remote_name == "dropbox-main"
    assert base_folder is None
