"""SSH and host/port setup helpers for SFTP-based remotes."""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

from repokit_common import load_from_env, save_to_env

from .remote_types import _detect_remote_type


def _prompt_with_default(prompt_text: str, default_val: str) -> str:
    val = input(f"{prompt_text} [{default_val}]: ").strip()
    return val if val else default_val


def _validate_port(port_str: str, default_val: str) -> str:
    try:
        p = int(port_str)
        if 1 <= p <= 65535:
            return str(p)
    except Exception:
        pass
    print(f"Invalid port '{port_str}'. Using default '{default_val}'.")
    return default_val


def detect_existing_ssh_key(*env_keys: str) -> str | None:
    for key in env_keys:
        existing = (load_from_env(key) or "").strip()
        if existing:
            expanded = str(pathlib.Path(existing).expanduser())
            if pathlib.Path(expanded).exists():
                return expanded

    home = pathlib.Path.home() / ".ssh"
    for name in ("id_ed25519", "id_rsa", "id_ecdsa"):
        p = home / name
        if p.exists():
            return str(p)

    return None


def _detect_default_ssh_key() -> str:
    detected = detect_existing_ssh_key("SSH_PATH")
    if detected:
        return detected
    return str((pathlib.Path.home() / ".ssh" / "id_ed25519"))


def set_host_port(
    remote_name: str,
    backend: str | None = None,
    *,
    ucloud_port: str | None = None,
    ssh_key_path: str | None = None,
    use_ssh_agent: bool = False,
    non_interactive: bool = False,
) -> None:
    """Create backend-specific SFTP runtime configuration without alias coupling."""
    remote_type = backend or _detect_remote_type(remote_name)
    if remote_type not in ["erda", "ucloud"]:
        return

    if remote_type == "erda":
        save_to_env("io.erda.dk", "ERDA_HOST")
        save_to_env("22", "ERDA_PORT")
        return

    host = (load_from_env("UCLOUD_HOST") or "ssh.cloud.sdu.dk").strip()
    existing_port = (load_from_env("UCLOUD_PORT") or "22").strip()
    if non_interactive:
        port_input = (ucloud_port or existing_port).strip()
    else:
        port_input = _prompt_with_default("Port for ucloud", existing_port)
    port_final = _validate_port(port_input, existing_port)
    save_to_env(host, "UCLOUD_HOST")
    save_to_env(port_final, "UCLOUD_PORT")

    if use_ssh_agent:
        key_path = ""
    elif non_interactive:
        key_path = (
            ssh_key_path or detect_existing_ssh_key("UCLOUD_SSH_KEY_PATH", "SSH_PATH") or ""
        ).strip()
    else:
        default_key = _detect_default_ssh_key()
        key_path = _prompt_with_default("Path to SSH private key for ucloud", default_key).strip()

    key_path = str(pathlib.Path(key_path).expanduser()) if key_path else ""

    if key_path and not os.path.isfile(key_path):
        print(f"SSH key file not found: {key_path}")
        return
    if not key_path and not use_ssh_agent:
        print("SSH key file is required for ucloud. Use --use-ssh-agent to opt in to agent auth.")
        return
    if key_path:
        save_to_env(key_path, "UCLOUD_SSH_KEY_PATH")

    bin_folder = pathlib.Path("./bin").resolve()
    bin_folder.mkdir(parents=True, exist_ok=True)
    rclone_conf = bin_folder / "rclone_ucloud.conf"
    config_content = f"""[{remote_name.strip().lower()}]
type = sftp
host = {host}
port = {port_final}
user = ucloud
"""
    if key_path:
        config_content += f"key_file = {key_path}\n"
    else:
        config_content += "use_agent = true\n"
    with open(rclone_conf, "w", encoding="utf-8") as f:
        f.write(config_content)

    print(f"ucloud rclone config saved/updated at: {rclone_conf}")
    auth_mode = f"SSH key: {key_path}" if key_path else "ssh-agent"
    print(f"Host: {host}, Port: {port_final}, Authentication: {auth_mode}")


def setup_ssh_agent_and_add_key(ssh_path: str) -> None:
    def _parse_ssh_agent_exports(output: str) -> dict:
        env = {}
        for line in output.splitlines():
            if "SSH_AUTH_SOCK=" in line:
                env["SSH_AUTH_SOCK"] = line.split("SSH_AUTH_SOCK=", 1)[1].split(";", 1)[0].strip()
            elif "SSH_AGENT_PID=" in line:
                env["SSH_AGENT_PID"] = line.split("SSH_AGENT_PID=", 1)[1].split(";", 1)[0].strip()
        return env

    def _ensure_ssh_agent_running():
        if sys.platform.startswith("win"):
            sc = shutil.which("sc")
            if sc is None:
                raise RuntimeError(
                    "Windows 'sc' utility not found; cannot control ssh-agent service."
                )
            subprocess.run(
                [sc, "config", "ssh-agent", "start=", "auto"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                [sc, "start", "ssh-agent"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif not os.environ.get("SSH_AUTH_SOCK"):
            ssh_agent = shutil.which("ssh-agent")
            if not ssh_agent:
                raise RuntimeError("ssh-agent not found in PATH.")
            proc = subprocess.run(
                [ssh_agent, "-s"],
                check=True,
                capture_output=True,
                text=True,
            )
            env_updates = _parse_ssh_agent_exports(proc.stdout)
            if "SSH_AUTH_SOCK" in env_updates:
                os.environ["SSH_AUTH_SOCK"] = env_updates["SSH_AUTH_SOCK"]
            if "SSH_AGENT_PID" in env_updates:
                os.environ["SSH_AGENT_PID"] = env_updates["SSH_AGENT_PID"]

    _ensure_ssh_agent_running()
    ssh_add = shutil.which("ssh-add")
    if not ssh_add:
        raise RuntimeError("ssh-add not found in PATH.")

    ssh_path_expanded = os.path.expanduser(ssh_path)
    if not os.path.exists(ssh_path_expanded):
        raise FileNotFoundError(f"SSH key not found: {ssh_path_expanded}")

    subprocess.run([ssh_add, ssh_path_expanded], check=True)
