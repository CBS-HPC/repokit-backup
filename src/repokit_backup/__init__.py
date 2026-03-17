"""
Backup module - Unified interface for rclone-based backups.

Exports are kept lazy so CLI startup can resolve the runtime project root
before root-sensitive modules are imported.
"""

from .cli import main


def push_rclone(*args, **kwargs):
    from .rclone import push_rclone as _push_rclone

    return _push_rclone(*args, **kwargs)


def pull_rclone(*args, **kwargs):
    from .rclone import pull_rclone as _pull_rclone

    return _pull_rclone(*args, **kwargs)


def install_rclone(*args, **kwargs):
    from .rclone import install_rclone as _install_rclone

    return _install_rclone(*args, **kwargs)


def setup_rclone(*args, **kwargs):
    from .remotes import setup_rclone as _setup_rclone

    return _setup_rclone(*args, **kwargs)


def list_remotes(*args, **kwargs):
    from .remotes import list_remotes as _list_remotes

    return _list_remotes(*args, **kwargs)


def delete_remote(*args, **kwargs):
    from .remotes import delete_remote as _delete_remote

    return _delete_remote(*args, **kwargs)


def list_supported_remote_types(*args, **kwargs):
    from .remotes import list_supported_remote_types as _list_supported_remote_types

    return _list_supported_remote_types(*args, **kwargs)


def set_host_port(*args, **kwargs):
    from .remotes import set_host_port as _set_host_port

    return _set_host_port(*args, **kwargs)


def _ensure_repo_suffix(*args, **kwargs):
    from .remotes import _ensure_repo_suffix as _ensure_repo_suffix_impl

    return _ensure_repo_suffix_impl(*args, **kwargs)


__all__ = [
    "main",
    "push_rclone",
    "pull_rclone",
    "setup_rclone",
    "list_remotes",
    "delete_remote",
    "list_supported_remote_types",
    "set_host_port",
    "_ensure_repo_suffix",
    "install_rclone",
]
