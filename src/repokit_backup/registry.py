"""
Registry management - JSON persistence for remote configurations.
"""

import json
import os
import pathlib
from datetime import datetime


MAPPING_MODES = {"full", "remote-only", "none"}
PATH_OWNERSHIPS = {"managed", "external", "none"}


def _atomic_write_json(path: str | os.PathLike[str], data: dict) -> None:
    """Atomically write JSON to avoid corruption."""
    path_obj = pathlib.Path(path)
    tmp = path_obj.with_suffix(path_obj.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path_obj)


def _read_registry_data(json_path: str) -> dict:
    """Read the registry file, returning an empty mapping when it is unavailable."""
    if not os.path.exists(json_path):
        return {}
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _remote_uri(remote_name: str, folder_path: str | None) -> str | None:
    """Return a remote URI while preserving a meaningful leading slash."""
    if folder_path is None:
        return None

    value = str(folder_path).strip().replace("\\", "/")
    if not value:
        return None

    remote_key = remote_name.strip().lower()
    if ":" in value:
        uri_remote, _, _ = value.partition(":")
        if uri_remote.strip().lower() != remote_key:
            raise ValueError(
                f"Remote path '{folder_path}' belongs to '{uri_remote}', not '{remote_name}'."
            )
        return value
    return f"{remote_key}:{value}"


def _mapping_mode(remote_path: str | None, local_path: str | None, requested: str | None) -> str:
    if requested is not None:
        if requested not in MAPPING_MODES:
            raise ValueError(f"Unknown mapping mode '{requested}'.")
        if requested == "full" and (not remote_path or not local_path):
            raise ValueError("A full mapping requires both remote and local paths.")
        if requested == "remote-only" and not remote_path:
            raise ValueError("A remote-only mapping requires a remote path.")
        if requested == "none" and (remote_path or local_path):
            raise ValueError("A mapping mode of 'none' cannot include paths.")
        return requested
    if remote_path and local_path:
        return "full"
    if remote_path:
        return "remote-only"
    return "none"


def load_registry(
    remote_name: str, json_path: str = "./bin/rclone_remote.json"
) -> tuple[str | None, str | None]:
    """
    Load rclone remote mapping.

    Returns:
        (remote_path, local_path) or (None, None) if not found
    """
    if not os.path.exists(json_path):
        print(f"No rclone registry found at {json_path}")
        return None, None

    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        print("Could not parse rclone registry file — it may be corrupted.")
        return None, None
    except OSError as e:
        print(f"Failed to read rclone registry: {e}")
        return None, None

    entry = data.get(remote_name)
    if not isinstance(entry, dict):
        return None, None

    return entry.get("remote_path"), entry.get("local_path")


def save_registry(
    remote_name: str,
    folder_path: str | None,
    local_backup_path: str | None,
    remote_type: str,
    push_policy: str = "full",
    mapping_mode: str | None = None,
    path_ownership: str | None = None,
    json_path: str = "./bin/rclone_remote.json",
) -> None:
    """Save remote configuration to registry."""
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    data = _read_registry_data(json_path)
    if os.path.exists(json_path) and not data:
        print("Warning: JSON file was corrupted or empty, reinitializing.")

    remote_key = remote_name.strip().lower()
    remote_path = _remote_uri(remote_key, folder_path)
    resolved_mode = _mapping_mode(remote_path, local_backup_path, mapping_mode)
    if path_ownership is None:
        path_ownership = "external" if resolved_mode == "remote-only" else "managed"
    if path_ownership not in PATH_OWNERSHIPS:
        raise ValueError(f"Unknown remote path ownership '{path_ownership}'.")
    if not remote_path:
        path_ownership = "none"

    previous = data.get(remote_key, {})
    if not isinstance(previous, dict):
        previous = {}
    data[remote_key] = {
        "remote_path": remote_path,
        "local_path": local_backup_path,
        "remote_type": remote_type,
        "push_policy": push_policy,
        "mapping_mode": resolved_mode,
        "remote_path_ownership": path_ownership,
        "last_action": previous.get("last_action"),
        "last_operation": previous.get("last_operation"),
        "timestamp": previous.get("timestamp"),
        "status": "initialized"
        if resolved_mode == "full"
        else "pinned"
        if remote_path
        else "configured",
    }
    _atomic_write_json(json_path, data)
    if resolved_mode == "full":
        print(f"Saved rclone path ({folder_path}) for '{remote_key}' to {json_path}")
        print(f"Local backup source: {local_backup_path}")
    elif resolved_mode == "remote-only":
        print(f"Pinned remote path ({remote_path}) for '{remote_key}' to {json_path}")
    else:
        print(f"Saved remote '{remote_key}' without a path mapping to {json_path}")
    print(f"Remote type: {remote_type}")
    print(f"Push policy: {push_policy}")


def load_all_registry(json_path: str = "./bin/rclone_remote.json") -> dict:
    """Load entire registry."""
    return _read_registry_data(json_path)


def set_remote_pin(
    remote_name: str,
    remote_path: str | None,
    json_path: str = "./bin/rclone_remote.json",
) -> bool:
    """Pin or clear a remote base without retaining a local path mapping."""
    data = _read_registry_data(json_path)
    remote_key = (remote_name or "").strip().lower()
    entry = data.get(remote_key)
    if not isinstance(entry, dict):
        print(f"Remote '{remote_name}' is not registered. Run `repokit-backup add` first.")
        return False

    current_mode = _mapping_mode(
        entry.get("remote_path"), entry.get("local_path"), entry.get("mapping_mode")
    )
    if current_mode == "full":
        print(
            f"Remote '{remote_name}' has a full local/remote mapping. "
            "`pin` only manages remote-only mappings and will not discard it."
        )
        return False

    normalized_path = _remote_uri(remote_key, remote_path)
    entry["remote_path"] = normalized_path
    entry["local_path"] = None
    entry["mapping_mode"] = "remote-only" if normalized_path else "none"
    entry["remote_path_ownership"] = "external" if normalized_path else "none"
    entry["status"] = "pinned" if normalized_path else "configured"
    _atomic_write_json(json_path, data)

    if normalized_path:
        print(f"Pinned remote path for '{remote_key}': {normalized_path}")
    else:
        print(f"Cleared saved paths for '{remote_key}'.")
    return True


def update_sync_status(
    remote_name: str,
    action: str,
    operation: str,
    success: bool = True,
    json_path: str = "./bin/rclone_remote.json",
):
    """Update last sync status for a remote."""
    if not os.path.exists(json_path):
        return
    try:
        with open(json_path, "r") as f:
            data = json.load(f)
        if remote_name in data and isinstance(data[remote_name], dict):
            data[remote_name]["last_action"] = action
            data[remote_name]["last_operation"] = operation
            data[remote_name]["timestamp"] = datetime.now().isoformat()
            data[remote_name]["status"] = "ok" if success else "potentially corrupt"
        _atomic_write_json(json_path, data)
    except Exception as e:
        print(f"Failed to update sync status: {e}")


def delete_from_registry(remote_name: str, json_path: str = "./bin/rclone_remote.json") -> bool:
    """Remove one remote from the registry atomically."""
    if not os.path.exists(json_path):
        return True
    try:
        with open(json_path, encoding="utf-8") as file_handle:
            data = json.load(file_handle)
        if not isinstance(data, dict):
            print(f"Error updating JSON config: registry is not a JSON object: {json_path}")
            return False
        remote_key = (remote_name or "").strip().lower()
        if remote_key not in data:
            return True
        del data[remote_key]
        _atomic_write_json(json_path, data)
        print(f"Removed '{remote_key}' entry from {json_path}.")
        return True
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error updating JSON config: {exc}")
        return False


def set_push_policy(
    remote_name: str,
    push_policy: str,
    json_path: str = "./bin/rclone_remote.json",
) -> bool:
    """Update push/pull policy for a registered remote."""
    valid = {"full", "append-only", "pull-only"}
    policy = (push_policy or "").strip().lower()
    if policy not in valid:
        print(f"Invalid policy '{push_policy}'. Valid values: {', '.join(sorted(valid))}")
        return False

    if not os.path.exists(json_path):
        print(f"No rclone registry found at {json_path}")
        return False

    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Failed to read rclone registry: {e}")
        return False

    key = (remote_name or "").strip().lower()
    if key not in data or not isinstance(data[key], dict):
        print(f"Remote '{remote_name}' not found in registry.")
        return False

    data[key]["push_policy"] = policy
    _atomic_write_json(json_path, data)
    print(f"Updated policy for '{key}' to '{policy}'.")
    return True
