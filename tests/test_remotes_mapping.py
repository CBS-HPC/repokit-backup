from __future__ import annotations

import pathlib

import repokit_backup.remotes as remotes


def test_setup_rclone_skips_add_folder_when_mapping_is_skipped(
    monkeypatch,
    tmp_path: pathlib.Path,
):
    monkeypatch.setattr(remotes, "PROJECT_ROOT", tmp_path.resolve())
    monkeypatch.setattr(
        remotes,
        "_remote_user_info",
        lambda remote_name, local_backup_path, project_root, backend: (
            remote_name,
            None,
            None,
            None,
        ),
    )
    monkeypatch.setattr(remotes, "_add_remote", lambda *args, **kwargs: True)

    add_folder_calls: list[tuple] = []
    monkeypatch.setattr(
        remotes,
        "_add_folder",
        lambda *args, **kwargs: add_folder_calls.append((args, kwargs)),
    )

    remotes.setup_rclone("dropbox-main", backend="dropbox")

    assert add_folder_calls == []
