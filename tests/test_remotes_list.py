from __future__ import annotations

import repokit_backup.remotes as remotes


def test_list_remotes_shows_unmapped_configured_remote(monkeypatch, capsys):
    monkeypatch.setattr(remotes, "_list_rclone_remotes", lambda config_path=None: {"test"})
    monkeypatch.setattr(remotes.pathlib.Path, "exists", lambda self: False)
    monkeypatch.setattr(
        remotes,
        "load_all_registry",
        lambda: {
            "test": {
                "remote_path": None,
                "local_path": None,
                "remote_type": "dropbox",
                "push_policy": "full",
                "last_action": None,
                "last_operation": None,
                "timestamp": None,
                "status": "configured",
            }
        },
    )

    remotes.list_remotes()
    out = capsys.readouterr().out

    assert "[REMOTES] Rclone Remotes:" in out
    assert "  - test [registered]" in out
    assert "[FOLDERS] Mapped Backup Folders:" in out
    assert "  - test (dropbox):" in out
    assert "Remote: Not mapped" in out
    assert "Local:  Not mapped" in out
