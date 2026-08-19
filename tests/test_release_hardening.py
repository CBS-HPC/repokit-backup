from __future__ import annotations

import argparse
import hashlib
import io
import pathlib
import subprocess
import sys
import zipfile

import pytest

from repokit_backup import cli
from repokit_backup import rclone
from repokit_backup.registry import delete_from_registry, save_registry


class _Response:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int):
        for offset in range(0, len(self.content), chunk_size):
            yield self.content[offset : offset + chunk_size]


def test_pinned_rclone_download_verifies_checksum(monkeypatch, tmp_path: pathlib.Path):
    payload = b"verified archive"
    captured: dict[str, object] = {}

    def fake_get(url: str, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _Response(payload)

    monkeypatch.setattr(rclone.requests, "get", fake_get)

    archive = rclone._download_rclone_archive(
        "rclone-v1.73.2-linux-amd64.zip",
        hashlib.sha256(payload).hexdigest(),
        tmp_path,
    )

    assert archive.read_bytes() == payload
    assert captured["url"] == "https://downloads.rclone.org/v1.73.2/rclone-v1.73.2-linux-amd64.zip"
    assert captured["kwargs"] == {"stream": True, "timeout": (10, 60)}


def test_pinned_rclone_download_removes_bad_archive(monkeypatch, tmp_path: pathlib.Path):
    monkeypatch.setattr(rclone.requests, "get", lambda *_args, **_kwargs: _Response(b"bad archive"))

    with pytest.raises(RuntimeError, match="SHA-256"):
        rclone._download_rclone_archive("rclone.zip", "0" * 64, tmp_path)

    assert not (tmp_path / "rclone.zip").exists()


def test_installer_extracts_only_verified_pinned_archive(monkeypatch, tmp_path: pathlib.Path):
    archive_name = "rclone-v1.73.2-linux-amd64.zip"
    archive_data = io.BytesIO()
    with zipfile.ZipFile(archive_data, "w") as archive:
        archive.writestr("rclone-v1.73.2-linux-amd64/rclone", "binary")
    payload = archive_data.getvalue()
    configured: dict[str, str] = {}

    monkeypatch.setattr(rclone.repokit_common, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(rclone, "is_installed", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        rclone,
        "RCLONE_RELEASES",
        {("linux", "amd64"): (archive_name, "rclone", hashlib.sha256(payload).hexdigest())},
    )
    monkeypatch.setattr(rclone.platform, "system", lambda: "Linux")
    monkeypatch.setattr(rclone.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(rclone.requests, "get", lambda *_args, **_kwargs: _Response(payload))
    monkeypatch.setattr(
        rclone,
        "exe_to_path",
        lambda executable, directory: configured.update(executable=executable, directory=directory)
        or True,
    )
    monkeypatch.setattr(rclone, "load_from_env", lambda _key: None)
    monkeypatch.setattr(rclone, "save_to_env", lambda value, key: configured.update({key: value}))

    assert rclone.install_rclone("./bin")
    assert configured["executable"] == "rclone"
    assert configured["directory"] == str(tmp_path / "bin" / "rclone-v1.73.2-linux-amd64")
    assert configured["RCLONE_CONFIG"] == str(tmp_path / "bin" / "rclone.conf")
    assert not (tmp_path / "bin" / archive_name).exists()


def test_rclone_archive_rejects_path_traversal(tmp_path: pathlib.Path):
    archive_data = io.BytesIO()
    with zipfile.ZipFile(archive_data, "w") as archive:
        archive.writestr("../outside", "not allowed")

    archive_data.seek(0)
    with zipfile.ZipFile(archive_data) as archive, pytest.raises(ValueError, match="Unsafe path"):
        rclone._safe_extract_zip(archive, tmp_path)

    assert not (tmp_path.parent / "outside").exists()


def test_transfer_failure_returns_false(monkeypatch, tmp_path: pathlib.Path):
    monkeypatch.setattr(rclone.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(rclone, "update_sync_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        rclone.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.CalledProcessError(returncode=1, cmd="rclone")
        ),
    )

    assert not rclone._rclone_transfer(
        remote_name="myproject",
        src=str(tmp_path),
        dst="myproject:/backup",
        operation="copy",
    )


def test_transfer_has_no_default_total_timeout(monkeypatch, tmp_path: pathlib.Path):
    captured: dict[str, object] = {}
    monkeypatch.setattr(rclone.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(rclone, "update_sync_status", lambda *_args, **_kwargs: None)

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs

    monkeypatch.setattr(rclone.subprocess, "run", fake_run)

    assert rclone._rclone_transfer(
        remote_name="myproject",
        src=str(tmp_path),
        dst="myproject:/backup",
        operation="copy",
    )
    assert captured["kwargs"] == {"check": True}


def test_transfer_uses_explicit_total_timeout(monkeypatch, tmp_path: pathlib.Path):
    captured: dict[str, object] = {}
    monkeypatch.setattr(rclone.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(rclone, "update_sync_status", lambda *_args, **_kwargs: None)

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs

    monkeypatch.setattr(rclone.subprocess, "run", fake_run)

    assert rclone._rclone_transfer(
        remote_name="myproject",
        src=str(tmp_path),
        dst="myproject:/backup",
        operation="copy",
        transfer_timeout=7200,
    )
    assert captured["kwargs"] == {"check": True, "timeout": 7200}


def test_transfer_timeout_marks_transfer_failed(monkeypatch, tmp_path: pathlib.Path, capsys):
    status: dict[str, object] = {}
    monkeypatch.setattr(rclone.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(
        rclone,
        "update_sync_status",
        lambda *_args, **kwargs: status.update(kwargs),
    )
    monkeypatch.setattr(
        rclone.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired(cmd="rclone", timeout=45)
        ),
    )

    assert not rclone._rclone_transfer(
        remote_name="myproject",
        src=str(tmp_path),
        dst="myproject:/backup",
        operation="copy",
        transfer_timeout=45,
    )
    assert "exceeded the configured total transfer timeout of 45 seconds" in capsys.readouterr().out
    assert status["success"] is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [("0", None), ("7200", 7200.0), ("1.5", 1.5)],
)
def test_parse_transfer_timeout(value: str, expected: float | None):
    assert cli._parse_transfer_timeout(value) == expected


@pytest.mark.parametrize("value", ["-1", "nan", "inf", "not-a-number"])
def test_parse_transfer_timeout_rejects_invalid_values(value: str):
    with pytest.raises(argparse.ArgumentTypeError, match="seconds|number"):
        cli._parse_transfer_timeout(value)


def test_cli_passes_transfer_timeout_to_push(monkeypatch, tmp_path: pathlib.Path):
    captured: dict[str, object] = {}
    monkeypatch.setattr(cli, "_resolve_cli_project_root", lambda **_kwargs: tmp_path)
    monkeypatch.setattr(
        cli,
        "_bootstrap_project_runtime",
        lambda _installer: (tmp_path / "bin", tmp_path / "pyproject.toml"),
    )
    monkeypatch.setattr(rclone, "push_rclone", lambda **kwargs: captured.update(kwargs) or True)
    monkeypatch.setattr(
        sys,
        "argv",
        ["repokit-backup", "push", "--remote", "myproject", "--transfer-timeout", "7200"],
    )

    cli.main()

    assert captured["transfer_timeout"] == 7200.0


def test_registry_delete_is_atomic_and_reports_success(tmp_path: pathlib.Path):
    registry_path = tmp_path / "bin" / "rclone_remote.json"
    save_registry("myproject", None, None, "dropbox", json_path=str(registry_path))

    assert delete_from_registry("myproject", json_path=str(registry_path))
    assert '"myproject"' not in registry_path.read_text(encoding="utf-8")


def test_registry_delete_refuses_to_hide_corruption(tmp_path: pathlib.Path):
    registry_path = tmp_path / "bin" / "rclone_remote.json"
    registry_path.parent.mkdir()
    registry_path.write_text("not json", encoding="utf-8")

    assert not delete_from_registry("myproject", json_path=str(registry_path))
    assert registry_path.read_text(encoding="utf-8") == "not json"


def test_cli_returns_nonzero_when_push_fails(monkeypatch, tmp_path: pathlib.Path):
    import repokit_backup.cli as cli

    monkeypatch.setattr(cli, "_resolve_cli_project_root", lambda **_kwargs: tmp_path)
    monkeypatch.setattr(
        cli,
        "_bootstrap_project_runtime",
        lambda _installer: (tmp_path / "bin", tmp_path / "pyproject.toml"),
    )
    monkeypatch.setattr(rclone, "push_rclone", lambda **_kwargs: False)
    monkeypatch.setattr(sys, "argv", ["repokit-backup", "push", "--remote", "myproject"])

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 1
