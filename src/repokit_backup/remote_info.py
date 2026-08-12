"""Remote information collection helpers for rclone setup."""

from __future__ import annotations

import getpass
import os
import pathlib

from repokit_common import check_path_format, load_from_env, save_to_env
from .auth import detect_existing_ssh_key


def ensure_repo_suffix(folder: str, repo: str, project_root: pathlib.Path) -> str:
    folder = folder.strip().replace("\\", "/").rstrip("/")
    if not folder.endswith(repo):
        add_suffix = True
        try:
            reply = (
                input(f"Add project name suffix '{repo}' to remote folder path? [Y/n]: ")
                .strip()
                .lower()
            )
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


def _prompt_create_mapping() -> bool:
    while True:
        reply = input("Create a local/remote path mapping now? [Y/n]: ").strip().lower()
        if reply in {"", "y", "yes"}:
            return True
        if reply in {"n", "no"}:
            return False
        print("Invalid choice. Use y or n.")


def _prompt_base_folder(remote_name: str, default_base: str = "") -> str | None:
    if not _prompt_create_mapping():
        print("[INFO] Remote configured without a saved path mapping.")
        return None

    prompt = f"Enter base folder for {remote_name}"
    if default_base:
        prompt += f" [{default_base}]"
    prompt += ": "

    while True:
        entered = input(prompt).strip()
        value = entered or default_base
        if value:
            return value
        print("Folder path cannot be empty. Answer 'n' in the previous prompt to skip mapping.")


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


def _resolve_non_interactive_value(
    explicit: str | None,
    env_key: str,
    label: str,
    *,
    default: str = "",
    required: bool = True,
) -> str:
    """Resolve a non-secret setting without ever prompting for input."""
    value = (explicit or load_from_env(env_key) or default or "").strip()
    if required and not value:
        raise ValueError(f"{label} is required with --non-interactive (use its flag or {env_key}).")
    if explicit and value:
        save_to_env(value, env_key)
    return value


def _resolve_non_interactive_key(
    explicit_key_path: str | None,
    env_key: str,
    label: str,
    *,
    use_ssh_agent: bool,
) -> str:
    """Resolve an SSH key path or require an explicit agent choice."""
    if use_ssh_agent:
        return ""

    key_path = (explicit_key_path or detect_existing_ssh_key(env_key, "SSH_PATH") or "").strip()
    if not key_path:
        raise ValueError(
            f"{label} is required with --non-interactive. Use --ssh-key-path or --use-ssh-agent."
        )
    expanded = str(pathlib.Path(key_path).expanduser())
    if not pathlib.Path(expanded).is_file():
        raise ValueError(f"{label} file not found: {expanded}")
    if explicit_key_path:
        save_to_env(expanded, env_key)
    return expanded


def non_interactive_remote_info(
    backend: str,
    *,
    lumio_project_id: str | None = None,
    lumio_access_key: str | None = None,
    lumio_secret_key: str | None = None,
    lumip_project_id: str | None = None,
    lumip_username: str | None = None,
    erda_username: str | None = None,
    erda_password: str | None = None,
    ssh_key_path: str | None = None,
    use_ssh_agent: bool = False,
    ucloud_port: str | None = None,
) -> tuple[str | None, str | None, dict[str, str | bool]]:
    """Resolve backend credentials for `add --non-interactive` without prompts."""
    backend = (backend or "").strip().lower()
    options: dict[str, str | bool] = {"use_ssh_agent": use_ssh_agent}

    if backend == "lumio":
        project_id = _resolve_non_interactive_value(
            lumio_project_id, "LUMIO_PROJECT_ID", "LUMI-O project id"
        )
        access_key = _resolve_non_interactive_value(
            lumio_access_key, "LUMIO_ACCESS_KEY", "LUMI-O access key"
        )
        secret_key = _resolve_non_interactive_value(
            lumio_secret_key, "LUMIO_SECRET_KEY", "LUMI-O secret key"
        )
        options["lumio_project_id"] = project_id
        return access_key, secret_key, options

    if backend == "lumip":
        project_id = _resolve_non_interactive_value(
            lumip_project_id, "LUMIP_PROJECT_ID", "LUMI project id"
        )
        username = _resolve_non_interactive_value(
            lumip_username,
            "LUMIP_USERNAME",
            "LUMI username",
            default=getpass.getuser(),
        )
        options["lumip_project_id"] = project_id
        options["ssh_key_path"] = _resolve_non_interactive_key(
            ssh_key_path,
            "LUMIP_SSH_KEY_PATH",
            "LUMI SSH private key",
            use_ssh_agent=use_ssh_agent,
        )
        return username, None, options

    if backend == "ucloud":
        port = _resolve_non_interactive_value(
            ucloud_port,
            "UCLOUD_PORT",
            "UCloud SSH port",
            default="22",
        )
        if not port.isdigit() or not (1 <= int(port) <= 65535):
            raise ValueError("UCloud SSH port must be an integer in range 1-65535.")
        options["ucloud_port"] = port
        options["ssh_key_path"] = _resolve_non_interactive_key(
            ssh_key_path,
            "UCLOUD_SSH_KEY_PATH",
            "UCloud SSH private key",
            use_ssh_agent=use_ssh_agent,
        )
        return "ucloud", None, options

    if backend == "erda":
        username = _resolve_non_interactive_value(erda_username, "ERDA_USERNAME", "ERDA username")
        password = _resolve_non_interactive_value(
            erda_password,
            "ERDA_PASSWORD",
            "ERDA password",
            required=False,
        )
        if password:
            options["erda_auth"] = "password"
            return username, password, options
        if use_ssh_agent:
            options["erda_auth"] = "agent"
            return username, None, options
        raise ValueError(
            "ERDA authentication is required with --non-interactive. "
            "Use --erda-password-file or --use-ssh-agent."
        )

    return None, None, options


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
        project_id = (
            input(f"LUMI-O project id [{project_id_default}]: ").strip() or project_id_default
        )
    else:
        project_id = _prompt_non_empty("LUMI-O project id: ")

    if access_key_default:
        access_key = (
            input(f"LUMI-O access key [{access_key_default}]: ").strip() or access_key_default
        )
    else:
        access_key = _prompt_non_empty("LUMI-O access key: ")

    if secret_key_default:
        secret_prompt = "LUMI-O secret key [stored]: "
        secret_key = getpass.getpass(secret_prompt).strip() or secret_key_default
    else:
        secret_key = _prompt_non_empty("LUMI-O secret key: ", secret=True)

    base_folder = _prompt_base_folder(remote_name, default_base)
    if base_folder is not None:
        base_folder = ensure_repo_suffix(base_folder, repo_name, project_root)

    save_to_env(project_id, "LUMIO_PROJECT_ID")
    save_to_env(access_key, "LUMIO_ACCESS_KEY")
    save_to_env(secret_key, "LUMIO_SECRET_KEY")
    if base_folder is not None:
        save_to_env(base_folder, "LUMIO_DEFAULT_BASE")

    return remote_name, access_key, secret_key, base_folder


def _lumip_remote_info(remote_name: str, repo_name: str, project_root: pathlib.Path):
    project_default = (load_from_env("LUMIP_PROJECT_ID") or "").strip()
    user_default = (load_from_env("LUMIP_USERNAME") or getpass.getuser()).strip()
    base_default = (
        load_from_env("LUMIP_BASE_PATH") or f"/scratch/{project_default or 'PROJECT_ID'}"
    ).strip()
    ssh_key_default = detect_existing_ssh_key("LUMIP_SSH_KEY_PATH", "SSH_PATH")

    if project_default:
        project_id = input(f"LUMI project id [{project_default}]: ").strip() or project_default
    else:
        project_id = _prompt_non_empty("LUMI project id: ")

    username = input(f"LUMI username [{user_default}]: ").strip() or user_default

    if ssh_key_default:
        ssh_prompt = f"LUMI SSH private key [{ssh_key_default}] (leave empty to use default): "
        ssh_key_path = input(ssh_prompt).strip() or ssh_key_default
    else:
        ssh_key_path = input("LUMI SSH private key (leave empty to use ssh-agent): ").strip()

    ssh_key_path = str(pathlib.Path(ssh_key_path).expanduser()) if ssh_key_path else ""
    if ssh_key_path:
        if not pathlib.Path(ssh_key_path).exists():
            raise ValueError(f"LUMI SSH key file not found: {ssh_key_path}")
        save_to_env(ssh_key_path, "LUMIP_SSH_KEY_PATH")

    if _prompt_create_mapping():
        base_root = _prompt_lumip_storage_root(project_id, username, base_default)
        base_folder = ensure_repo_suffix(base_root, repo_name, project_root)
        save_to_env(base_root, "LUMIP_BASE_PATH")
    else:
        print("[INFO] Remote configured without a saved path mapping.")
        base_folder = None

    save_to_env(project_id, "LUMIP_PROJECT_ID")
    save_to_env(username, "LUMIP_USERNAME")

    return remote_name, username, None, base_folder


def _ucloud_remote_info(remote_name: str, repo_name: str, project_root: pathlib.Path):
    default_base = f"/work/rclone-backup/{repo_name}"
    base_folder = _prompt_base_folder(remote_name, default_base)
    if base_folder is not None:
        base_folder = ensure_repo_suffix(base_folder, repo_name, project_root)
    return remote_name, "ucloud", None, base_folder


def _local_remote_info(remote_name: str, repo_name: str, project_root: pathlib.Path):
    if not _prompt_create_mapping():
        print("[INFO] Remote configured without a saved path mapping.")
        return remote_name, None, None, None

    base_folder = (
        input("Please enter the local path for rclone: ").strip().replace("'", "").replace('"', "")
    )
    base_folder = check_path_format(base_folder)
    if not os.path.isdir(base_folder):
        print(f"Error: The specified local path does not exist: {base_folder}")
        return remote_name, None, None, None
    base_folder = ensure_repo_suffix(base_folder, repo_name, project_root)
    return remote_name, None, None, base_folder


def _oauth_remote_info(remote_name: str, repo_name: str, project_root: pathlib.Path):
    default_base = f"rclone-backup/{repo_name}"
    base_folder = _prompt_base_folder(remote_name, default_base)
    if base_folder is not None:
        base_folder = ensure_repo_suffix(base_folder, repo_name, project_root)
    return remote_name, None, None, base_folder


def _generic_remote_info(remote_name: str, repo_name: str, project_root: pathlib.Path):
    default_base = f"rclone-backup/{repo_name}"
    base_folder = _prompt_base_folder(remote_name, default_base)
    if base_folder is not None:
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
