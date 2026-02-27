"""
Remote management - Detection, configuration, and listing.
"""

import os
import pathlib
import subprocess
import getpass
import json
import socket
import time

from repokit_common import PROJECT_ROOT, load_from_env, save_to_env, check_path_format
from .auth import set_host_port, setup_ssh_agent_and_add_key
from .remote_types import _detect_remote_type, _get_base_remote_type
from .remote_info import (
    check_lumi_o_credentials,
    ensure_repo_suffix as _ensure_repo_suffix,
    remote_user_info as _remote_user_info,
)
from .registry import save_registry, load_all_registry, delete_from_registry, load_registry
from .rclone import (
    _rc_verbose_args,
    rclone_diff_report,
    _rclone_transfer,
    DEFAULT_TIMEOUT,
    install_rclone,
)




































def _rclone_cmd(*args: str) -> list[str]:
    return ["rclone", *args]


def check_rclone_remote(remote_name: str) -> bool:
    """Check if rclone remote is configured."""
    try:
        result = subprocess.run(
            _rclone_cmd("listremotes"),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=DEFAULT_TIMEOUT,
        )
        remotes = result.stdout.decode("utf-8").splitlines()
        return f"{remote_name}:" in remotes
    except subprocess.CalledProcessError as e:
        print(f"Failed to check rclone remotes: {e}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return False


def _list_rclone_remotes(config_path: pathlib.Path | None = None) -> set[str]:
    """Return configured remote names, optionally from a specific rclone config file."""
    cmd = _rclone_cmd("listremotes")
    if config_path is not None:
        cmd += ["--config", str(config_path)]
    try:
        result = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=DEFAULT_TIMEOUT,
        )
        return {line.rstrip(":").strip() for line in result.stdout.splitlines() if line.strip()}
    except Exception:
        return set()


def _default_rclone_config_path() -> pathlib.Path | None:
    """Resolve the default rclone config path via `rclone config file`."""
    try:
        result = subprocess.run(
            _rclone_cmd("config", "file"),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=DEFAULT_TIMEOUT,
        )
    except Exception:
        return None

    for line in result.stdout.splitlines():
        if ":" in line:
            maybe_path = line.split(":", 1)[1].strip()
            if maybe_path:
                return pathlib.Path(maybe_path).expanduser().resolve()
    return None


def _delete_config_if_no_remotes(config_path: pathlib.Path | None = None):
    """Delete a config file when it has no remotes configured."""
    target = config_path or _default_rclone_config_path()
    if target is None or not target.exists():
        return

    remotes = _list_rclone_remotes(config_path if config_path is not None else None)
    if remotes:
        return

    try:
        target.unlink()
        print(f"No remotes left. Deleted config file: {target}")
    except Exception as e:
        print(f"Could not delete config file '{target}': {e}")


def _delete_single_remote(remote_name: str, verbose: int = 0):
    """Delete one remote mapping and cleanup config files when empty."""
    remote_name = remote_name.strip().lower()
    remote_path, _ = load_registry(remote_name)

    rclone_conf = None
    if remote_name.startswith("ucloud"):
        ucloud_conf = pathlib.Path("./bin/rclone_ucloud.conf").resolve()
        if ucloud_conf.exists():
            rclone_conf = ucloud_conf

    if remote_path:
        purge_cmd = _rclone_cmd("purge", remote_path) + _rc_verbose_args(verbose)
        if rclone_conf is not None:
            purge_cmd += ["--config", str(rclone_conf)]

        try:
            print(f"Attempting to purge remote folder at: {remote_path}")
            subprocess.run(purge_cmd, check=True, timeout=DEFAULT_TIMEOUT)
            print(f"Successfully purged remote folder: {remote_path}")
        except subprocess.CalledProcessError as e:
            print(f"Warning: Could not purge remote folder '{remote_path}': {e}")
        except Exception as e:
            print(f"Unexpected error during purge: {e}")
    else:
        print(f"No registry mapping found for '{remote_name}'. Skipping purge.")

    delete_cmd = _rclone_cmd("config", "delete", remote_name) + _rc_verbose_args(verbose)
    if rclone_conf is not None:
        delete_cmd += ["--config", str(rclone_conf)]

    try:
        subprocess.run(delete_cmd, check=True, timeout=DEFAULT_TIMEOUT)
        print(f"Rclone remote '{remote_name}' deleted from rclone configuration.")
    except subprocess.CalledProcessError as e:
        print(f"Error deleting remote from rclone: {e}")

    delete_from_registry(remote_name)

    # Always cleanup empty config files after single-remote deletion.
    _delete_config_if_no_remotes()
    ucloud_conf = pathlib.Path("./bin/rclone_ucloud.conf").resolve()
    if ucloud_conf.exists():
        _delete_config_if_no_remotes(ucloud_conf)


def _add_erda_remote(remote_name: str, login: str, pass_key: str | None):
    command = _rclone_cmd(
        "config",
        "create",
        remote_name,
        "sftp",
        "host",
        load_from_env("HOST"),
        "port",
        load_from_env("PORT"),
        "user",
        login,
    )

    if pass_key:
        command += ["pass", pass_key, "--obscure"]
    else:
        command += ["use_agent", "true"]

    subprocess.run(command, check=True, timeout=DEFAULT_TIMEOUT)
    print(f"Rclone remote '{remote_name}' (erda) created.")


def _add_lumi_remote(remote_name: str, login: str, pass_key: str):
    acl = "public-read" if "public" in remote_name.lower() else "private"

    command = _rclone_cmd(
        "config",
        "create",
        remote_name,
        "s3",
        "provider",
        "Other",
        "endpoint",
        "https://lumidata.eu",
        "access_key_id",
        login,
        "secret_access_key",
        pass_key,
        "region",
        "other-v2-signature",
        "acl",
        acl,
    )

    subprocess.run(command, check=True, timeout=DEFAULT_TIMEOUT)
    print(f"Rclone remote '{remote_name}' (lumi) created.")


def _is_port_listening(host: str, port: int, retries: int = 5, delay_s: float = 0.4) -> bool:
    for _ in range(max(retries, 1)):
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(delay_s)
    return False


def _add_simple_remote(
    remote_name: str,
    base_type: str,
    ssh_mode: bool = False,
    callback_port: int = 53682,
):
    print(f"You will need to authorize rclone with {base_type}")
    command = _rclone_cmd("config", "create", remote_name, base_type)
    if not ssh_mode:
        subprocess.run(command, check=True, timeout=DEFAULT_TIMEOUT)
    else:
        # In ssh-mode, stream output and fail early if callback listener never opens.
        saw_waiting_for_code = False
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                print(line.rstrip())
                if (not saw_waiting_for_code) and ("Waiting for code" in line):
                    saw_waiting_for_code = True
                    if not _is_port_listening("127.0.0.1", callback_port):
                        proc.terminate()
                        raise RuntimeError(
                            f"OAuth callback port {callback_port} is not listening on remote host. "
                            "Check SSH tunnel target, runtime context, or use --token-file."
                        )
            rc = proc.wait(timeout=DEFAULT_TIMEOUT)
        finally:
            if proc.poll() is None:
                proc.terminate()

        if rc != 0:
            raise subprocess.CalledProcessError(rc, command)
    print(f"Rclone remote '{remote_name}' created.")


def _prompt_ssh_tunnel_for_oauth(app_port: int = 53682) -> None:
    """Prompt SSH endpoint and print local tunnel command for OAuth callback flow."""
    default_host = (load_from_env("SSH_HOST") or "").strip()
    default_port = (load_from_env("SSH_PORT") or "22").strip()

    host_prompt = f"SSH host/user (user@host){f' [{default_host}]' if default_host else ''}: "
    entered_host = input(host_prompt).strip()
    ssh_host = entered_host or default_host
    if not ssh_host:
        print("SSH host is required for --ssh-mode.")
        raise ValueError("Missing SSH host")

    port_prompt = f"SSH port [{default_port}]: "
    entered_port = input(port_prompt).strip()
    ssh_port = entered_port or default_port

    save_to_env(ssh_host, "SSH_HOST")
    save_to_env(ssh_port, "SSH_PORT")

    cmd = f"ssh -N -L {app_port}:127.0.0.1:{app_port} {ssh_host} -p {ssh_port}"
    print("\n=== SSH tunnel for OAuth callback ===")
    print("Run this on your LOCAL machine before continuing authorization:")
    print(f"  {cmd}")
    print(
        "Then open the exact '/auth?state=...' URL printed by rclone in your LOCAL browser "
        f"(through http://127.0.0.1:{app_port})."
    )
    print()


def _validate_oauth_token_json(oauth_token: str) -> str:
    token_str = (oauth_token or "").strip()
    if not token_str:
        raise ValueError("OAuth token is empty.")
    try:
        parsed = json.loads(token_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"OAuth token is not valid JSON: {e}") from e
    if not isinstance(parsed, dict):
        raise ValueError("OAuth token JSON must be an object.")
    return json.dumps(parsed, separators=(",", ":"))


def _add_oauth_remote_with_token(remote_name: str, base_type: str, oauth_token: str):
    token_json = _validate_oauth_token_json(oauth_token)
    command = _rclone_cmd("config", "create", remote_name, base_type, "token", token_json)
    subprocess.run(command, check=True, timeout=DEFAULT_TIMEOUT)
    print(f"Rclone remote '{remote_name}' created using provided OAuth token.")


def _add_interactive_remote(remote_name: str, base_type: str):
    output = list_supported_remote_types()
    backend_types = [
        line.split()[0]
        for line in output.splitlines()
        if line and not line.startswith(" ") and ":" in line
    ]

    if base_type not in backend_types:
        raise RuntimeError(f"Unsupported remote type: {base_type}")

    print(f"Running interactive config for backend '{base_type}'...")
    command = _rclone_cmd("config", "create", remote_name, base_type)
    subprocess.run(command, check=True, timeout=DEFAULT_TIMEOUT)
    print(f"Rclone remote '{remote_name}' created.")


def _add_remote(
    remote_name: str,
    login: str = None,
    pass_key: str = None,
    oauth_token: str | None = None,
    ssh_mode: bool = False,
):
    """Add a new rclone remote or prepare runtime config."""
    remote_type = _detect_remote_type(remote_name)
    base_type = _get_base_remote_type(remote_name)
    oauth_remotes = {"dropbox", "onedrive", "drive"}

    try:
        if remote_type == "erda":
            _add_erda_remote(remote_name, login, pass_key)
            return True

        elif remote_type == "ucloud":
            return True

        elif "lumi" in remote_type:
            _add_lumi_remote(remote_name, login, pass_key)
            return True

        elif remote_type in oauth_remotes:
            if oauth_token:
                _add_oauth_remote_with_token(remote_name, base_type, oauth_token)
            else:
                if ssh_mode:
                    _prompt_ssh_tunnel_for_oauth()
                _add_simple_remote(remote_name, base_type, ssh_mode=ssh_mode)
            return True

        elif remote_type == "local":
            if oauth_token:
                print(
                    "[WARN] --token was provided for a non-OAuth backend ('local'). Ignoring token."
                )
            _add_simple_remote(remote_name, base_type)
            return True

        else:
            if oauth_token:
                print(
                    f"[WARN] --token was provided for backend '{remote_type}' which is not OAuth-based. Ignoring token."
                )
            _add_interactive_remote(remote_name, base_type)
            return True

    except Exception as e:
        print(f"Failed to add remote '{remote_name}': {e}")
        return False


def _add_folder(remote_name: str, base_folder: str, local_backup_path: str):
    """Add folder mapping for remote with overwrite/merge safeguard, using ucloud config if applicable."""
    remote_type = _detect_remote_type(remote_name)

    # Build list/mkdir commands
    if remote_type in ["dropbox", "onedrive", "drive"]:
        base_folder = base_folder.lstrip("/")
        list_cmd = _rclone_cmd("lsd", f"{remote_name}:{base_folder}")
        mkdir_cmd = _rclone_cmd("mkdir", f"{remote_name}:{base_folder}")
    elif "lumi" in remote_type:
        list_cmd = _rclone_cmd("lsd", f"{remote_name}:/{base_folder}")
        mkdir_cmd = _rclone_cmd("mkdir", f"{remote_name}:/{base_folder}")
    else:  # SFTP (ucloud, erda) or local
        base_folder = f"/{base_folder.lstrip('/')}"
        list_cmd = _rclone_cmd("lsf", f"{remote_name}:{base_folder}")
        mkdir_cmd = _rclone_cmd("mkdir", f"{remote_name}:{base_folder}")

        # Use ucloud config if remote is ucloud
        if remote_name.lower().startswith("ucloud"):
            rclone_conf = pathlib.Path("./bin/rclone_ucloud.conf").resolve()
            if rclone_conf.exists():
                list_cmd += ["--config", str(rclone_conf)]
                mkdir_cmd += ["--config", str(rclone_conf)]
            else:
                print("[WARN] ucloud rclone config not found in ./bin. Please run set_host_port first.")
                return

    # Check if remote folder exists
    result = subprocess.run(list_cmd, capture_output=True, text=True, timeout=DEFAULT_TIMEOUT)
    merge_only = False
    if result.returncode == 0 and result.stdout.strip():
        valid_choices = {"o": "overwrite", "s": "merge/sync", "n": "rename", "c": "cancel"}
        while True:
            choice = (
                input(
                    f"'{base_folder}' exists on '{remote_name}'. Overwrite (o), Merge/Sync (s), Rename (n), Cancel (c)? [o/s/n/c]: "
                )
                .strip()
                .lower()
            )
            if choice not in valid_choices:
                print(
                    f"Invalid choice: {choice}. Please choose one of {', '.join(valid_choices.keys())}."
                )
                continue

            if choice == "o":
                print("[WARN] You chose to overwrite the remote folder.")
                subprocess.run(
                    _rclone_cmd("purge", f"{remote_name}:{base_folder}")
                    + (["--config", str(rclone_conf)] if remote_name.lower() == "ucloud" else []),
                    check=True,
                    timeout=DEFAULT_TIMEOUT,
                )
                break

            elif choice == "s":
                print("[INFO] Will merge/sync differences only.")
                merge_only = True
                break

            elif choice == "n":
                base_folder = input("New folder name: ").strip()
                if remote_type in ["dropbox", "onedrive", "drive"]:
                    base_folder = base_folder.lstrip("/")
                result = subprocess.run(
                    list_cmd, capture_output=True, text=True, timeout=DEFAULT_TIMEOUT
                )
                continue

            elif choice == "c":
                print("Cancelled.")
                return

    # Ensure remote folder exists
    try:
        subprocess.run(mkdir_cmd, check=True, timeout=DEFAULT_TIMEOUT)
    except Exception as e:
        print(f"Error creating folder: {e}")
        return

    # Save mapping
    save_registry(remote_name, base_folder, local_backup_path, remote_type)

    # Run merge if requested
    if merge_only:
        remote_full_path = f"{remote_name}:{base_folder}"
        print("\nRunning diff report before syncing...")
        rclone_diff_report(local_backup_path, remote_full_path)
        print("\nSyncing differences to merge local and remote...")
        _rclone_transfer(
            remote_name=remote_name,
            local_path=local_backup_path,
            remote_path=remote_full_path,
            action="push",
            operation="copy",
        )  # copy to avoid deleting


def list_remotes():
    """List all configured remotes and their status."""
    print("\n[REMOTES] Rclone Remotes:")
    try:
        result = subprocess.run(
            _rclone_cmd("listremotes"), check=True, stdout=subprocess.PIPE, timeout=DEFAULT_TIMEOUT
        )
        rclone_configured = set(r.rstrip(":") for r in result.stdout.decode().splitlines())
    except Exception as e:
        print(f"Failed to list remotes: {e}")
        rclone_configured = set()

    print("\n[FOLDERS] Mapped Backup Folders:")
    all_remotes = load_all_registry()
    if not all_remotes:
        print("  No folders registered.")
    else:
        for remote, meta in all_remotes.items():
            remote_path = meta.get("remote_path") if isinstance(meta, dict) else meta
            local_path = (
                meta.get("local_path", "Not specified")
                if isinstance(meta, dict)
                else "Not specified"
            )
            remote_type = (
                meta.get("remote_type", "unknown") if isinstance(meta, dict) else "unknown"
            )
            action = meta.get("last_action") if isinstance(meta, dict) else "-"
            operation = meta.get("last_operation") if isinstance(meta, dict) else "-"
            timestamp = meta.get("timestamp") if isinstance(meta, dict) else "-"
            status = meta.get("status") if isinstance(meta, dict) else "-"
            status_note = "[OK]" if remote in rclone_configured else "[WARN] missing in rclone config"
            print(f"  - {remote} ({remote_type}):")
            print(f"      Remote: {remote_path}")
            print(f"      Local:  {local_path}")
            print(
                f"      Action: {action} | Operation: {operation} | Timestamp: {timestamp} | Status: {status} {status_note}"
            )


def setup_rclone(
    remote_name: str = None,
    local_backup_path: str = None,
    oauth_token: str | None = None,
    ssh_mode: bool = False,
):
    """Setup rclone remote and folder mapping."""
    if local_backup_path is None:
        local_backup_path = str(PROJECT_ROOT)

    if remote_name:
        remote_name, login_key, pass_key, base_folder = _remote_user_info(
            remote_name.lower(), local_backup_path, pathlib.Path(PROJECT_ROOT)
        )
        created = _add_remote(
            remote_name.lower(),
            login_key,
            pass_key,
            oauth_token=oauth_token,
            ssh_mode=ssh_mode,
        )
        if not created:
            print(f"Aborting setup for '{remote_name}' because remote creation failed.")
            return
        _add_folder(remote_name.lower(), base_folder, local_backup_path)
    else:
        install_rclone("./bin")


def delete_remote(remote_name: str, verbose: int = 0):
    """Delete one remote or all remotes (`remote_name='all'`)."""
    remote_name = remote_name.strip().lower()

    if remote_name == "all":
        registry_remotes = set(load_all_registry().keys())
        default_cfg_remotes = _list_rclone_remotes()
        ucloud_conf = pathlib.Path("./bin/rclone_ucloud.conf").resolve()
        ucloud_cfg_remotes = _list_rclone_remotes(ucloud_conf) if ucloud_conf.exists() else set()

        all_remotes = sorted(registry_remotes | default_cfg_remotes | ucloud_cfg_remotes)
        if not all_remotes:
            print("No remotes found.")
            _delete_config_if_no_remotes()
            if ucloud_conf.exists():
                _delete_config_if_no_remotes(ucloud_conf)
            return

        confirm = input(
            f"Really delete ALL data and config entries for all remotes ({', '.join(all_remotes)})? [y/N]: "
        )
        if confirm.lower() != "y":
            return

        for name in all_remotes:
            _delete_single_remote(name, verbose=verbose)
        return

    confirm = input(f"Really delete ALL data for '{remote_name}'? [y/N]: ")
    if confirm.lower() != "y":
        return

    _delete_single_remote(remote_name, verbose=verbose)

def list_supported_remote_types() -> str:
    """List all supported rclone backend types."""
    try:
        result = subprocess.run(
            _rclone_cmd("help", "backends"),
            check=True,
            stdout=subprocess.PIPE,
            text=True,
            timeout=DEFAULT_TIMEOUT,
        )
        print("\n[TYPES] Supported Rclone Remote Types:")
        print("\nRecommended: ['ERDA' ,'Ucloud', 'Lumi','Dropbox', 'Onedrive', 'Local']\n")
        print("\nSupported by Rclone:\n")
        print(result.stdout)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error fetching remote types: {e}")
        return ""
