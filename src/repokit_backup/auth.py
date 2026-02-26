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


def _detect_default_ssh_key() -> str:
    existing = (load_from_env("SSH_PATH", "") or "").strip()
    if existing:
        return existing

    home = pathlib.Path.home() / ".ssh"
    for name in ("id_ed25519", "id_rsa", "id_ecdsa"):
        p = home / name
        if p.exists():
            return str(p)

    return str(home / "id_ed25519")


def set_host_port(remote_name: str) -> None:
    remote_type = _detect_remote_type(remote_name)
    if remote_type not in ["erda", "ucloud"]:
        return

    if remote_type == "erda":
        save_to_env("io.erda.dk", "HOST")
        save_to_env("22", "PORT")
        return

    host = "ssh.cloud.sdu.dk"
    existing_port = load_from_env("PORT")
    port_input = _prompt_with_default("Port for ucloud", existing_port)
    port_final = _validate_port(port_input, existing_port)
    save_to_env(host, "HOST")
    save_to_env(port_final, "PORT")

    default_key = _detect_default_ssh_key()
    ssh_key_path = _prompt_with_default(
        "Path to SSH private key for ucloud", default_key
    ).strip()
    ssh_key_path = str(pathlib.Path(ssh_key_path).expanduser())

    if not os.path.isfile(ssh_key_path):
        print(f"SSH key file not found: {ssh_key_path}")
        return

    bin_folder = pathlib.Path("./bin").resolve()
    bin_folder.mkdir(parents=True, exist_ok=True)
    rclone_conf = bin_folder / "rclone_ucloud.conf"
    config_content = f"""[ucloud]
type = sftp
host = {host}
port = {port_final}
user = ucloud
key_file = {ssh_key_path}
"""
    with open(rclone_conf, "w", encoding="utf-8") as f:
        f.write(config_content)

    print(f"ucloud rclone config saved/updated at: {rclone_conf}")
    print(f"Host: {host}, Port: {port_final}, SSH key: {ssh_key_path}")


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

