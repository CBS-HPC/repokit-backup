"""Remote information collection helpers for rclone setup."""

from __future__ import annotations

import getpass
import os
import pathlib

from repokit_common import check_path_format, load_from_env, save_to_env


def ensure_repo_suffix(folder: str, repo: str, project_root: pathlib.Path) -> str:
    folder = folder.strip().replace("\\", "/").rstrip("/")
    if not folder.endswith(repo):
        add_suffix = True
        try:
            reply = input(
                f"Add project name suffix '{repo}' to remote folder path? [Y/n]: "
            ).strip().lower()
            if reply in {"n", "no"}:
                add_suffix = False
        except EOFError:
            add_suffix = True

        if add_suffix:
            folder = os.path.join(folder, repo).replace("\\", "/")
    project_root_normalized = os.path.normpath(str(project_root))
    folder_normalized = os.path.normpath(folder)
    if folder_normalized.startswith(project_root_normalized):
        folder = project_root_normalized + "_backup"
    return folder


def _prompt_non_empty(prompt: str, secret: bool = False, default: str = "") -> str:
    while True:
        if secret:
            value = getpass.getpass(prompt).strip()
        else:
            raw = input(prompt).strip()
            value = raw or default
        if value:
            return value
        print("Value is required.")


def _validate_lumip_base_path(path: str, expected_prefix: str | None = None) -> str:
    normalized = (path or "").strip().replace("\\", "/")
    if not normalized:
        raise ValueError("LUMI-P base path is required.")
    if not normalized.startswith("/"):
        raise ValueError("LUMI-P base path must be absolute (start with '/').")
    if "/../" in f"{normalized}/" or normalized.endswith("/.."):
        raise ValueError("LUMI-P base path cannot contain '..'.")
    if expected_prefix and not normalized.startswith(expected_prefix):
        raise ValueError(
            f"LUMI-P base path must start with '{expected_prefix}' for selected storage class."
        )
    return normalized.rstrip("/") or "/"


def _prompt_lumip_storage_root(project_id: str, username: str, default_base: str) -> str:
    options = [
        ("1", f"/users/{username}", "home"),
        ("2", f"/project/{project_id}", "project"),
        ("3", f"/scratch/{project_id}", "scratch"),
        ("4", f"/flash/{project_id}", "flash"),
        ("5", default_base, "custom"),
    ]
    print("\nSelect LUMI-P/LUMI-F storage class:")
    for code, path, label in options:
        if label == "custom":
            print(f"{code}) custom absolute path [{path}]")
        else:
            print(f"{code}) {label}: {path}")

    while True:
        choice = input("Choose [1-5] (default 3): ").strip() or "3"
        if choice not in {code for code, _, _ in options}:
            print("Invalid choice. Use 1-5.")
            continue

        if choice == "1":
            return _validate_lumip_base_path(f"/users/{username}", f"/users/{username}")
        if choice == "2":
            return _validate_lumip_base_path(f"/project/{project_id}", f"/project/{project_id}")
        if choice == "3":
            return _validate_lumip_base_path(f"/scratch/{project_id}", f"/scratch/{project_id}")
        if choice == "4":
            return _validate_lumip_base_path(f"/flash/{project_id}", f"/flash/{project_id}")

        entered = input(f"Enter custom absolute path [{default_base}]: ").strip() or default_base
        try:
            return _validate_lumip_base_path(entered)
        except ValueError as exc:
            print(f"Invalid path: {exc}")


def _lumio_remote_info(remote_name: str, repo_name: str, project_root: pathlib.Path):
    project_id_default = (load_from_env("LUMIO_PROJECT_ID") or "").strip()
    access_key_default = (load_from_env("LUMIO_ACCESS_KEY") or "").strip()
    secret_key_default = (load_from_env("LUMIO_SECRET_KEY") or "").strip()
    default_base = (load_from_env("LUMIO_DEFAULT_BASE") or f"rclone-backup/{repo_name}").strip()

    if project_id_default:
        project_id = input(f"LUMI-O project id [{project_id_default}]: ").strip() or project_id_default
    else:
        project_id = _prompt_non_empty("LUMI-O project id: ")

    if access_key_default:
        access_key = input(f"LUMI-O access key [{access_key_default}]: ").strip() or access_key_default
    else:
        access_key = _prompt_non_empty("LUMI-O access key: ")

    if secret_key_default:
        secret_prompt = "LUMI-O secret key [stored]: "
        secret_key = getpass.getpass(secret_prompt).strip() or secret_key_default
    else:
        secret_key = _prompt_non_empty("LUMI-O secret key: ", secret=True)

    base_folder = input(f"Enter base folder for {remote_name} [{default_base}]: ").strip() or default_base
    base_folder = ensure_repo_suffix(base_folder, repo_name, project_root)

    save_to_env(project_id, "LUMIO_PROJECT_ID")
    save_to_env(access_key, "LUMIO_ACCESS_KEY")
    save_to_env(secret_key, "LUMIO_SECRET_KEY")
    save_to_env(base_folder, "LUMIO_DEFAULT_BASE")

    return remote_name, access_key, secret_key, base_folder


def _lumip_remote_info(remote_name: str, repo_name: str, project_root: pathlib.Path):
    project_default = (load_from_env("LUMIP_PROJECT_ID") or "").strip()
    user_default = (load_from_env("LUMIP_USERNAME") or getpass.getuser()).strip()
    base_default = (load_from_env("LUMIP_BASE_PATH") or f"/scratch/{project_default or 'PROJECT_ID'}").strip()

    if project_default:
        project_id = input(f"LUMI project id [{project_default}]: ").strip() or project_default
    else:
        project_id = _prompt_non_empty("LUMI project id: ")

    username = input(f"LUMI username [{user_default}]: ").strip() or user_default

    base_root = _prompt_lumip_storage_root(project_id, username, base_default)
    base_folder = ensure_repo_suffix(base_root, repo_name, project_root)

    save_to_env(project_id, "LUMIP_PROJECT_ID")
    save_to_env(username, "LUMIP_USERNAME")
    save_to_env(base_root, "LUMIP_BASE_PATH")

    return remote_name, username, None, base_folder


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


def _generic_remote_info(remote_name: str, repo_name: str, project_root: pathlib.Path):
    default_base = f"rclone-backup/{repo_name}"
    base_folder = input(f"Enter base folder for {remote_name} [{default_base}]: ").strip() or default_base
    base_folder = ensure_repo_suffix(base_folder, repo_name, project_root)
    return remote_name, None, None, base_folder


def remote_user_info(
    remote_name: str,
    local_backup_path: str,
    project_root: pathlib.Path,
    backend: str,
):
    repo_name = pathlib.Path(local_backup_path).name
    handlers = {
        "ucloud": _ucloud_remote_info,
        "local": _local_remote_info,
        "dropbox": _oauth_remote_info,
        "onedrive": _oauth_remote_info,
        "drive": _oauth_remote_info,
        "lumio": _lumio_remote_info,
        "lumip": _lumip_remote_info,
    }
    handler = handlers.get(backend, _generic_remote_info)
    return handler(remote_name, repo_name, project_root)

