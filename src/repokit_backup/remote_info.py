"""Remote information collection helpers for rclone setup."""

from __future__ import annotations

import getpass
import os
import pathlib

from repokit_common import check_path_format, load_from_env, save_to_env

from .remote_types import _detect_remote_type


def ensure_repo_suffix(folder: str, repo: str, project_root: pathlib.Path) -> str:
    folder = folder.strip().replace("\\", "/").rstrip("/")
    if not folder.endswith(repo):
        folder = os.path.join(folder, repo).replace("\\", "/")
    project_root_normalized = os.path.normpath(str(project_root))
    folder_normalized = os.path.normpath(folder)
    if folder_normalized.startswith(project_root_normalized):
        folder = project_root_normalized + "_backup"
    return folder


def handle_lumi_o_remote(remote_name: str, repo_name: str, project_root: pathlib.Path) -> tuple[str, str, str, str]:
    remote_type = "public" if "public" in remote_name.lower() else "private"
    project_id = load_from_env("LUMI_PROJECT_ID")
    access_key = load_from_env("LUMI_ACCESS_KEY")
    secret_key = load_from_env("LUMI_SECRET_KEY")
    base_folder = load_from_env(f"LUMI_BASE_{remote_type.upper()}")

    if project_id and access_key and secret_key and base_folder:
        base_folder = ensure_repo_suffix(base_folder, repo_name, project_root)
        return lumi_o_remote_name(remote_name), base_folder, access_key, secret_key

    default_base = f"rclone-backup/{repo_name}"
    base_folder = input(f"Enter base folder for LUMI-O ({remote_type}) [{default_base}]: ").strip() or default_base
    base_folder = ensure_repo_suffix(base_folder, repo_name, project_root)
    print("\nGet your LUMI-O credentials from: https://auth.lumidata.eu")

    project_id = access_key = secret_key = None
    while not project_id or not access_key or not secret_key:
        project_id = input("Please enter LUMI project ID (e.g., 465000001): ").strip()
        access_key = input("Please enter LUMI access key: ").strip()
        secret_key = getpass.getpass("Please enter LUMI secret key: ").strip()
        if not project_id or not access_key or not secret_key:
            print("All three fields (project ID, access key, secret key) are required.\n")

    save_to_env(project_id, "LUMI_PROJECT_ID")
    save_to_env(access_key, "LUMI_ACCESS_KEY")
    save_to_env(secret_key, "LUMI_SECRET_KEY")
    save_to_env(base_folder, f"LUMI_BASE_{remote_type.upper()}")
    return lumi_o_remote_name(remote_name), base_folder, access_key, secret_key


def lumi_o_remote_name(remote_name: str) -> str:
    project_id = load_from_env("LUMI_PROJECT_ID")
    remote_type = "public" if "public" in remote_name.lower() else "private"
    return f"lumi-{project_id}-{remote_type}"


def check_lumi_o_credentials(remote_name: str, command: str = "add", repo_name: str = ".cookiecutter", project_root: pathlib.Path | None = None) -> str | None:
    project_id = load_from_env("LUMI_PROJECT_ID")
    if project_root is None:
        project_root = pathlib.Path.cwd().resolve()
    if not project_id and command == "add":
        remote_name, _, _, _ = handle_lumi_o_remote(remote_name, repo_name, project_root)
        return remote_name
    if not project_id and command != "add":
        print(f"{remote_name} remote not found. Please set up the remote first by running 'backup add --remote {remote_name}'.")
        return None
    if project_id:
        return lumi_o_remote_name(remote_name)
    return None


def remote_user_info(remote_name: str, local_backup_path: str, project_root: pathlib.Path):
    repo_name = pathlib.Path(local_backup_path).name
    remote_type = _detect_remote_type(remote_name)
    if "lumi" in remote_type:
        return _lumi_remote_info(remote_name, repo_name)
    handlers = {
        "ucloud": _ucloud_remote_info,
        "local": _local_remote_info,
        "dropbox": _oauth_remote_info,
        "onedrive": _oauth_remote_info,
        "drive": _oauth_remote_info,
    }
    handler = handlers.get(remote_type, _generic_remote_info)
    return handler(remote_name, repo_name, project_root)


def _ucloud_remote_info(remote_name: str, repo_name: str, project_root: pathlib.Path):
    default_base = f"/work/rclone-backup/{repo_name}"
    base_folder = input(f"Enter base folder for {remote_name} [{default_base}]: ").strip() or default_base
    base_folder = ensure_repo_suffix(base_folder, repo_name, project_root)
    return remote_name, "ucloud", None, base_folder


def _local_remote_info(remote_name: str, repo_name: str, project_root: pathlib.Path):
    base_folder = input("Please enter the local path for rclone: ").strip().replace("'", "").replace('"', "")
    base_folder = check_path_format(base_folder)
    if not os.path.isdir(base_folder):
        print(f"Error: The specified local path does not exist: {base_folder}")
        return remote_name, None, None, None
    base_folder = ensure_repo_suffix(base_folder, repo_name, project_root)
    return remote_name, None, None, base_folder


def _oauth_remote_info(remote_name: str, repo_name: str, project_root: pathlib.Path):
    default_base = f"rclone-backup/{repo_name}"
    base_folder = input(f"Enter base folder for {remote_name} [{default_base}]: ").strip() or default_base
    base_folder = ensure_repo_suffix(base_folder, repo_name, project_root)
    return remote_name, None, None, base_folder


def _lumi_remote_info(remote_name: str, repo_name: str):
    remote_name = check_lumi_o_credentials(remote_name, command="add", repo_name=repo_name) or remote_name
    access_key = load_from_env("LUMI_ACCESS_KEY")
    secret_key = load_from_env("LUMI_SECRET_KEY")
    remote_type = "public" if "public" in remote_name.lower() else "private"
    base_folder = load_from_env(f"LUMI_BASE_{remote_type.upper()}") or f"rclone-backup/{repo_name}"
    return remote_name, access_key, secret_key, base_folder


def _generic_remote_info(remote_name: str, repo_name: str, project_root: pathlib.Path):
    default_base = f"rclone-backup/{repo_name}"
    base_folder = input(f"Enter base folder for {remote_name} [{default_base}]: ").strip() or default_base
    base_folder = ensure_repo_suffix(base_folder, repo_name, project_root)
    return remote_name, None, None, base_folder

