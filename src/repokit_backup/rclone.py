import os
import pathlib
import subprocess
import platform
import zipfile
import glob
import requests


from repokit_common import (
    PROJECT_ROOT,
    toml_ignore,
    exe_to_path,
    is_installed,
    toml_dataset_path,
    load_from_env,
    save_to_env,
)

try:
    from repokit.vcs import rclone_commit
except Exception:
    rclone_commit = None

from .registry import update_sync_status, load_registry, load_all_registry

DEFAULT_TIMEOUT = 600  # seconds

DEFAULT_DATASET_PATH, _ = toml_dataset_path()


def _rc_verbose_args(level: int) -> list[str]:
    """Convert verbosity level to rclone args."""
    return ["-" + "v" * min(max(level, 0), 3)] if level > 0 else []


def install_rclone(install_path: str = "./bin") -> bool:
    """Download and extract rclone to the specified bin folder."""

    install_root = (PROJECT_ROOT / pathlib.Path(install_path)).resolve()
    install_root.mkdir(parents=True, exist_ok=True)
    rclone_config = install_root / "rclone.conf"

    def download_rclone(install_path: str = "./bin"):
        os_type = platform.system().lower()

        # Set the URL and executable name based on the OS
        if os_type == "windows":
            url = "https://downloads.rclone.org/rclone-current-windows-amd64.zip"
            rclone_executable = "rclone.exe"
        elif os_type in ["linux", "darwin"]:
            url = (
                "https://downloads.rclone.org/rclone-current-linux-amd64.zip"
                if os_type == "linux"
                else "https://downloads.rclone.org/rclone-current-osx-amd64.zip"
            )
            rclone_executable = "rclone"
        else:
            print(f"Unsupported operating system: {os_type}. Please install rclone manually.")
            return None

        # Create the bin folder if it doesn't exist
        install_path = str(PROJECT_ROOT / pathlib.Path(install_path))
        os.makedirs(install_path, exist_ok=True)

        # Download rclone
        local_zip = os.path.join(install_path, "rclone.zip")
        print(f"Downloading rclone for {os_type} to {local_zip}...")
        response = requests.get(url)
        if response.status_code == 200:
            with open(local_zip, "wb") as file:
                file.write(response.content)
            print("Download complete.")
        else:
            print("Failed to download rclone. Please check the URL.")
            return None

        # Extract the rclone executable
        print("Extracting rclone...")
        with zipfile.ZipFile(local_zip, "r") as zip_ref:
            zip_ref.extractall(install_path)

        rclone_folder = glob.glob(os.path.join(install_path, "rclone-*"))

        if not rclone_folder or len(rclone_folder) > 1:
            print(f"More than one 'rclone-*' folder detected in {install_path}")
            return None

        # Clean up by deleting the zip file
        os.remove(local_zip)

        rclone_path = os.path.join(install_path, rclone_folder[0], rclone_executable)
        print(f"rclone installed successfully at {rclone_path}.")

        rclone_path = os.path.abspath(rclone_path)
        os.chmod(rclone_path, 0o755)
        return rclone_path

    if not is_installed("rclone", "Rclone", local_path="./bin"):
        rclone_path = download_rclone(install_path)
        if not rclone_path:
            return False
        rclone_dir = os.path.dirname(rclone_path)
    else:
        # Even when already installed, ensure process PATH includes the resolved local dir.
        rclone_dir = os.environ.get("RCLONE")
        if not rclone_dir:
            rclone_dir = str((PROJECT_ROOT / pathlib.Path(install_path)).resolve())

    if not exe_to_path("rclone", rclone_dir):
        return False

    # Prefer existing persisted config path; if missing, create and persist a local default.
    resolved_rclone_config = load_from_env("RCLONE_CONFIG")
    if not resolved_rclone_config:
        resolved_rclone_config = str(rclone_config)
        os.environ["RCLONE_CONFIG"] = resolved_rclone_config
        save_to_env(resolved_rclone_config, "RCLONE_CONFIG")
    else:
        os.environ["RCLONE_CONFIG"] = resolved_rclone_config
    print(f"rclone:config set to {resolved_rclone_config}")
    return True


def _rclone_transfer(
    remote_name: str,
    src: str,
    dst: str,
    src_kind: str = "local",
    action: str = "push",
    operation: str = "sync",
    include_patterns: list[str] = None,
    exclude_patterns: list[str] = None,
    dry_run: bool = False,
    verbose: int = 0,
):
    """
    Transfer files using rclone. Automatically uses ucloud config if remote is ucloud.

    Args:
        remote_name: Name of the configured remote
        src: Source path (local FS path or rclone remote URI)
        dst: Destination path (local FS path or rclone remote URI)
        src_kind: 'local' or 'remote' (controls local path checks)
        action: 'push', 'pull', or 'transfer'
        operation: 'sync', 'copy', or 'move'
        exclude_patterns: List of patterns to exclude
        dry_run: If True, show what would be done
        verbose: Verbosity level (0-3)
    """
    exclude_patterns = exclude_patterns or []
    include_patterns = include_patterns or []
    operation = operation.lower().strip()

    if operation not in {"sync", "copy", "move"}:
        print("Error: 'operation' must be either 'sync', 'copy', or 'move'")
        return

    # Build rclone command
    include_args = []
    for pattern in include_patterns:
        include_args.extend(["--include", pattern])

    exclude_args = []
    for pattern in exclude_patterns:
        exclude_args.extend(["--exclude", pattern])

    if src_kind not in {"local", "remote"}:
        print(f"Error: Invalid src_kind '{src_kind}'. Must be 'local' or 'remote'.")
        return

    if src_kind == "local" and not os.path.exists(src):
        print(f"Error: The folder '{src}' does not exist.")
        return

    command = ["rclone", operation, src, dst] + _rc_verbose_args(verbose) + include_args + exclude_args

    # Use ucloud config if applicable
    if remote_name.lower().startswith("ucloud") or str(src).startswith("ucloud:") or str(
        dst
    ).startswith("ucloud:"):
        rclone_conf = pathlib.Path("./bin/rclone_ucloud.conf").resolve()
        if rclone_conf.exists():
            command += ["--config", str(rclone_conf)]
        else:
            print("⚠️ ucloud rclone config not found in ./bin. Please run set_host_port first.")
            return

    if dry_run:
        command.append("--dry-run")

    try:
        subprocess.run(command, check=True, timeout=DEFAULT_TIMEOUT)
        verb = {"sync": "synchronized", "copy": "copied", "move": "moved (deleted at origin)"}.get(
            operation, operation
        )
        print(f"Transfer '{src}' -> '{dst}' successfully {verb}.")
        update_sync_status(remote_name, action=action, operation=operation, success=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to {operation} transfer '{src}' -> '{dst}': {e}")
        update_sync_status(remote_name, action=action, operation=operation, success=False)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        update_sync_status(remote_name, action=action, operation=operation, success=False)


def _normalize_select_subpath(select_path: str | None) -> str:
    path = (select_path or "").strip().replace("\\", "/")
    if path in {"", ".", "/"}:
        return ""
    return path.lstrip("/")


def _join_remote_path(base_remote_path: str, sub_path: str) -> str:
    if not sub_path:
        return base_remote_path
    prefix, sep, tail = base_remote_path.partition(":")
    if sep == "":
        return base_remote_path
    tail = tail.rstrip("/")
    return f"{prefix}:{tail}/{sub_path}" if tail else f"{prefix}:{sub_path}"


def _remote_root(remote_name: str) -> str:
    return f"{(remote_name or '').strip().lower()}:"


def _normalize_search_pattern(search_pattern: str | None) -> tuple[str | None, bool]:
    pattern = (search_pattern or "").strip().replace("\\", "/")
    if not pattern:
        return None, False
    anchored_to_root = pattern.startswith("/")
    normalized = pattern.lstrip("/")
    return normalized or None, anchored_to_root


def _search_include_patterns(search_pattern: str | None) -> list[str]:
    normalized, _ = _normalize_search_pattern(search_pattern)
    if not normalized:
        return []
    if normalized.endswith("/"):
        return [f"{normalized.rstrip('/')}/**"]
    return [normalized]


def _select_source_path(src: str, src_kind: str, select_path: str | None) -> tuple[str, str]:
    sub_path = _normalize_select_subpath(select_path)
    if not sub_path:
        return src, ""
    if src_kind == "remote":
        return _join_remote_path(src, sub_path), sub_path
    return str(pathlib.Path(src) / pathlib.Path(sub_path)), sub_path


def _parse_selection_indices(raw: str, max_index: int) -> list[int]:
    selected = set()
    chunks = [part.strip() for part in (raw or "").split(",") if part.strip()]
    if not chunks:
        return []
    for chunk in chunks:
        if "-" in chunk:
            left, right = chunk.split("-", 1)
            if not left.strip().isdigit() or not right.strip().isdigit():
                return []
            start = int(left.strip())
            end = int(right.strip())
            if start > end:
                start, end = end, start
            if start < 1 or end > max_index:
                return []
            selected.update(range(start, end + 1))
        else:
            if not chunk.isdigit():
                return []
            idx = int(chunk)
            if idx < 1 or idx > max_index:
                return []
            selected.add(idx)
    return sorted(selected)


def _list_top_level_entries(src: str, src_kind: str, remote_name: str) -> list[str]:
    if src_kind == "local":
        base = pathlib.Path(src)
        if not base.exists():
            return []
        entries = []
        for child in sorted(base.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            entries.append(f"{child.name}/" if child.is_dir() else child.name)
        return entries

    cmd = ["rclone", "lsf", src, "--max-depth", "1"]
    if remote_name.lower().startswith("ucloud") or str(src).startswith("ucloud:"):
        rclone_conf = pathlib.Path("./bin/rclone_ucloud.conf").resolve()
        if rclone_conf.exists():
            cmd += ["--config", str(rclone_conf)]
    try:
        result = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=DEFAULT_TIMEOUT,
        )
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return sorted(lines, key=lambda s: (not s.endswith("/"), s.lower()))
    except Exception as e:
        print(f"Failed to list source entries for interactive selection: {e}")
        return []


def _interactive_include_patterns(
    src: str, src_kind: str, remote_name: str, include_prefix: str = ""
) -> list[str] | None:
    entries = _list_top_level_entries(src, src_kind, remote_name)
    if not entries:
        print("No entries available for interactive selection.")
        return []

    print("\nSelect entries to transfer (comma/range format like 1,3,5-7).")
    print("Press Enter for all entries, or 'c' to cancel this transfer.")
    for idx, entry in enumerate(entries, start=1):
        print(f"{idx:>3}) {entry}")

    while True:
        raw = input("Selection: ").strip()
        if raw == "":
            return []
        if raw.lower() in {"c", "cancel", "q", "quit"}:
            print("Transfer cancelled by user.")
            return None
        indices = _parse_selection_indices(raw, len(entries))
        if not indices:
            print("Invalid selection. Use numbers/ranges like 1,3,5-7.")
            continue
        patterns = []
        for i in indices:
            entry = entries[i - 1]
            item_pattern = entry.rstrip("/") + "/**" if entry.endswith("/") else entry
            if include_prefix:
                item_pattern = f"{include_prefix.rstrip('/')}/{item_pattern}"
            patterns.append(item_pattern)
        return patterns


def _direct_include_pattern(select_path: str | None) -> str:
    normalized = _normalize_select_subpath(select_path)
    if not normalized:
        return ""
    if normalized.endswith("/"):
        return f"{normalized.rstrip('/')}/**"
    return normalized


def _select_include_patterns(
    src: str,
    src_kind: str,
    remote_name: str,
    select_path: str | None,
) -> list[str] | None:
    """
    Resolve include patterns from --select.
    - --select            -> interactive from root
    - --select /sub/path  -> interactive from scope if scope is listable
                            otherwise direct include of that path
    """
    if select_path is None:
        return []

    normalized = _normalize_select_subpath(select_path)
    selection_src, include_prefix = _select_source_path(src, src_kind, select_path)

    # Root selection remains interactive.
    if normalized == "":
        return _interactive_include_patterns(selection_src, src_kind, remote_name, include_prefix="")

    entries = _list_top_level_entries(selection_src, src_kind, remote_name)
    if entries:
        return _interactive_include_patterns(
            selection_src,
            src_kind,
            remote_name,
            include_prefix=include_prefix,
        )

    # Fallback: treat the provided selection path as a direct include target.
    pattern = _direct_include_pattern(select_path)
    if pattern:
        print(f"Using direct selection pattern: {pattern}")
        return [pattern]
    return []


def _exclude_patterns(local_path: str) -> list[str]:
    """Get exclude patterns from pyproject.toml if applicable."""
    if pathlib.Path(local_path).resolve() == PROJECT_ROOT.resolve():
        _, exclude_patterns = toml_ignore(
            folder=local_path,
            toml_path="pyproject.toml",
            ignore_filename=".rcloneignore",
            tool_name="rcloneignore",
            toml_key="patterns",
        )
        return exclude_patterns
    return []


def _nested_remote_excludes(remote_name: str, local_path: str, registry: dict) -> list[str]:
    """
    Build exclude patterns for nested child remotes.
    If current remote maps to /project and another remote maps to /project/data,
    then current remote excludes data/** so ownership is delegated to the child.
    """
    current_root = pathlib.Path(local_path).resolve()
    excludes: list[str] = []

    for other_name, meta in (registry or {}).items():
        if other_name == remote_name:
            continue
        if not isinstance(meta, dict):
            continue
        other_local = meta.get("local_path")
        if not other_local:
            continue
        other_root = pathlib.Path(str(other_local)).resolve()
        if other_root == current_root:
            continue

        try:
            rel = other_root.relative_to(current_root)
        except ValueError:
            continue

        rel_str = str(rel).replace("\\", "/").strip("/")
        if not rel_str:
            continue
        excludes.append(f"{rel_str}/")
        excludes.append(f"{rel_str}/**")

    # stable and deduplicated
    return sorted(set(excludes))


def push_rclone(
    remote_name: str,
    new_path: str = None,
    operation: str = "sync",
    dry_run: bool = False,
    verbose: int = 0,
    select_path: str | None = None,
    search_pattern: str | None = None,
):
    """Push local files to remote."""
    os.chdir(PROJECT_ROOT)

    if not install_rclone("./bin"):
        return

    if remote_name.lower() == "all":
        all_remotes = load_all_registry().keys()
    else:
        all_remotes = [remote_name]

    flag = False
    registry = load_all_registry()
    for remote_name in all_remotes:
        remote_key = remote_name.lower()
        remote_meta = registry.get(remote_key, {})
        if isinstance(remote_meta, dict):
            push_policy = str(remote_meta.get("push_policy", "full")).strip().lower()
        else:
            push_policy = "full"

        if push_policy == "pull-only":
            print(f"Skipping '{remote_name}': push policy is pull-only.")
            continue
        if push_policy == "append-only" and operation in {"sync", "move"}:
            print(
                f"Skipping '{remote_name}': push policy is append-only; "
                f"operation '{operation}' is not allowed (use copy)."
            )
            continue

        _remote_path, _local_path = load_registry(remote_key)
        if not _remote_path:
            print(
                f"Remote has not been configured or not found in registry. "
                f"Run 'backup add --remote {remote_name}' first."
            )
            continue

        target_path = new_path if new_path is not None else _remote_path
        if rclone_commit:
            flag = rclone_commit(
                _local_path, flag, msg=f"Rclone Push from {_local_path} to {target_path}"
            )
        exclude_patterns = _exclude_patterns(_local_path)
        exclude_patterns += _nested_remote_excludes(remote_key, _local_path, registry)
        exclude_patterns = sorted(set(exclude_patterns))
        include_patterns = _search_include_patterns(search_pattern)
        if select_path is not None:
            selected = _select_include_patterns(
                _local_path,
                "local",
                remote_name.lower(),
                select_path,
            )
            if selected is None:
                continue
            include_patterns = selected

        _rclone_transfer(
            remote_name=remote_key,
            src=_local_path,
            dst=target_path,
            src_kind="local",
            action="push",
            operation=operation,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            dry_run=dry_run,
            verbose=verbose,
        )


def pull_rclone(
    remote_name: str,
    remote_path: str = None,
    new_path: str = None,
    operation: str = "sync",
    dry_run: bool = False,
    verbose: int = 0,
    select_path: str | None = None,
    search_pattern: str | None = None,
):
    """Pull files from remote to local."""
    if remote_name is None:
        print("Error: No remote specified for pulling backup.")
        return
    if remote_name.lower() == "all":
        print("Error: Pulling from 'all' remotes is not supported.")
        return

    os.chdir(PROJECT_ROOT)

    if not install_rclone("./bin"):
        return

    _remote_path, _local_path = load_registry(remote_name.lower())
    registry = load_all_registry()
    remote_meta = registry.get(remote_name.lower(), {})
    if isinstance(remote_meta, dict):
        push_policy = str(remote_meta.get("push_policy", "full")).strip().lower()
    else:
        push_policy = "full"

    if push_policy in {"append-only", "pull-only"} and operation in {"sync", "move"}:
        print(
            f"Policy '{push_policy}' only allows pull operation 'copy'. "
            f"Auto-switching from '{operation}' to 'copy' for '{remote_name}'."
        )
        operation = "copy"

    has_mapping = bool(_remote_path and _local_path)
    effective_remote_path = remote_path or _remote_path
    effective_local_path = new_path or _local_path

    if not has_mapping:
        if not new_path:
            print(
                f"Remote '{remote_name}' has no saved mapping. "
                "Provide --path for pull destination."
            )
            return
        if not remote_path:
            effective_remote_path = f"{remote_name.lower()}:"
            print(
                f"Remote '{remote_name}' has no saved mapping. "
                f"Defaulting pull source to remote root '{effective_remote_path}'."
            )

    if not effective_remote_path:
        print(f"Error: No remote source path resolved for '{remote_name}'.")
        return
    if not effective_local_path:
        print(f"Error: No local destination path resolved for '{remote_name}'.")
        return

    if not os.path.exists(effective_local_path):
        os.makedirs(effective_local_path)
    if rclone_commit:
        _ = rclone_commit(
            effective_local_path,
            False,
            msg=f"Rclone Pull from {effective_remote_path} to {effective_local_path}",
        )
    exclude_patterns = []
    if _local_path:
        exclude_patterns = _exclude_patterns(_local_path)
        exclude_patterns += _nested_remote_excludes(remote_name.lower(), _local_path, registry)
    exclude_patterns = sorted(set(exclude_patterns))
    include_patterns = _search_include_patterns(search_pattern)
    if select_path is not None:
        selected = _select_include_patterns(
            effective_remote_path,
            "remote",
            remote_name.lower(),
            select_path,
        )
        if selected is None:
            return
        include_patterns = selected
        # Ensure local parent path exists for direct file selections.
        normalized = _normalize_select_subpath(select_path)
        if normalized and not normalized.endswith("/"):
            local_target = pathlib.Path(effective_local_path) / pathlib.Path(normalized)
            local_target.parent.mkdir(parents=True, exist_ok=True)

    _rclone_transfer(
        remote_name=remote_name.lower(),
        src=effective_remote_path,
        dst=effective_local_path,
        src_kind="remote",
        action="pull",
        operation=operation,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        dry_run=dry_run,
        verbose=verbose,
    )


def rclone_diff_report(local_path: str, remote_path: str):
    """Quick diff between local folder and remote path, handles ucloud remote."""
    import tempfile
    import pathlib

    cmd = ["rclone", "diff"]

    # Handle ucloud remote
    if remote_path.startswith("ucloud:"):
        rclone_conf = pathlib.Path("./bin/rclone_ucloud.conf").resolve()
        if not rclone_conf.exists():
            print("⚠️ ucloud rclone config not found in ./bin. Cannot run diff.")
            return
        # Strip "ucloud:" prefix and make path absolute
        remote_path = "/" + remote_path[len("ucloud:") :].lstrip("/")
        cmd += ["--config", str(rclone_conf)]

    cmd += [
        local_path,
        remote_path,
        "--no-traverse",
        "--differ",
        "--missing-on-dst",
        "--missing-on-src",
        "--dry-run",
    ]

    with tempfile.NamedTemporaryFile() as temp:
        cmd += ["--output", temp.name]
        try:
            subprocess.run(cmd, check=True, timeout=DEFAULT_TIMEOUT)
            with open(temp.name) as f:
                diff_output = f.read()
            print(diff_output or "[No differences]")
        except subprocess.CalledProcessError as e:
            print(f"Failed to generate diff report: {e}")


def generate_diff_report(remote_name: str):
    """Generate diff report between local and remote using the reusable diff function."""

    def run_diff(remote: str):
        remote_path, local_path = load_registry(remote)
        if not remote_path or not local_path:
            print(f"No path found for remote '{remote}'.")
            return
        print(f"\n📊 Diff report for '{remote}':")
        rclone_diff_report(local_path, remote_path)

    if remote_name.lower() == "all":
        for remote in load_all_registry().keys():
            run_diff(remote)
    else:
        run_diff(remote_name)


def list_remote_entries(
    remote_name: str,
    sub_path: str = "",
    search_pattern: str | None = None,
):
    """
    List files/folders for a remote.
    Uses configured mapping when present; otherwise defaults to remote root.
    """
    remote_name = (remote_name or "").strip().lower()
    remote_path, _ = load_registry(remote_name)
    base_remote = remote_path if remote_path else _remote_root(remote_name)
    if not remote_path:
        print(f"No mapped path for '{remote_name}'. Listing remote root.")

    target, _ = _select_source_path(base_remote, "remote", sub_path)
    normalized_search, anchored_to_root = _normalize_search_pattern(search_pattern)
    if normalized_search:
        target = _remote_root(remote_name) if anchored_to_root else target
        cmd = ["rclone", "lsf", target, "--recursive", "--include", normalized_search]
    else:
        cmd = ["rclone", "lsf", target, "--max-depth", "1"]

    if remote_name.startswith("ucloud") or str(target).startswith("ucloud:"):
        rclone_conf = pathlib.Path("./bin/rclone_ucloud.conf").resolve()
        if rclone_conf.exists():
            cmd += ["--config", str(rclone_conf)]
        else:
            print("[WARN] ucloud rclone config not found in ./bin. Please run set_host_port first.")
            return

    try:
        result = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=DEFAULT_TIMEOUT,
        )
        entries = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if normalized_search:
            print(f"\nRemote search for '{remote_name}': {target} | pattern={normalized_search}")
        else:
            print(f"\nRemote listing for '{remote_name}': {target}")
        if not entries:
            print("[No matches]" if normalized_search else "[Empty]")
            return
        for entry in sorted(entries, key=lambda s: (not s.endswith("/"), s.lower())):
            print(f"  {entry}")
    except subprocess.CalledProcessError as e:
        action = "search" if normalized_search else "list"
        print(f"Failed to {action} remote entries at '{target}': {e}")


def transfer_between_remotes(
    source_remote: str,
    dest_remote: str,
    operation: str = "copy",
    dry_run: bool = True,
    verbose: int = 0,
):
    """
    Transfer data from one remote to another.

    Safeguard: Only allowed if both remotes share the same local_path.
    """
    all_remotes = load_all_registry()
    src_meta = all_remotes.get(source_remote)
    dst_meta = all_remotes.get(dest_remote)

    if not src_meta or not dst_meta:
        print(
            f"Error: One or both remotes not registered. Source: {source_remote}, Destination: {dest_remote}"
        )
        return

    src_local = src_meta.get("local_path")
    dst_local = dst_meta.get("local_path")

    if not src_local or not dst_local:
        print("Error: One or both remotes do not have local paths configured.")
        return

    if os.path.abspath(src_local) != os.path.abspath(dst_local):
        print("Error: Cannot transfer between remotes with different local paths.")
        print(f"Source local path: {src_local}")
        print(f"Destination local path: {dst_local}")
        return

    src_path = src_meta.get("remote_path")
    dst_path = dst_meta.get("remote_path")

    print(f"\n🔁 Transfer from '{source_remote}' to '{dest_remote}'")
    print(f"Local path (shared): {src_local}")
    print(f"Remote paths: {src_path} → {dst_path}")
    print(f"Operation: {operation} | Dry run: {dry_run}\n")

    if operation not in {"copy", "sync"}:
        print("Error: Only 'copy' or 'sync' operations are allowed for remote-to-remote transfers.")
        return

    exclude_patterns = _exclude_patterns(src_local)

    _rclone_transfer(
        remote_name=f"{source_remote}->{dest_remote}",
        src=src_path,
        dst=dst_path,
        src_kind="remote",
        action="transfer",
        operation=operation,
        exclude_patterns=exclude_patterns,
        dry_run=dry_run,
        verbose=verbose,
    )
