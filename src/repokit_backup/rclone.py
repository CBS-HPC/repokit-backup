import hashlib
import os
import pathlib
import platform
import shutil
import subprocess
import zipfile

import requests

import repokit_common
from repokit_common import (
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
RCLONE_VERSION = "1.73.2"

# Pin the archives used by automatic installation. This prevents an upstream
# ``rclone-current`` change from silently changing the executable we run.
RCLONE_RELEASES = {
    ("windows", "amd64"): (
        "rclone-v1.73.2-windows-amd64.zip",
        "rclone.exe",
        "b77a72eab9692f9032dac89d7e13e07ce4747acd9ae402168cc8fe306de1138e",
    ),
    ("windows", "arm64"): (
        "rclone-v1.73.2-windows-arm64.zip",
        "rclone.exe",
        "bc100700af528d00647aba08acdcfb81862f624f755c11c5324cf34c14982f2c",
    ),
    ("linux", "amd64"): (
        "rclone-v1.73.2-linux-amd64.zip",
        "rclone",
        "00a1d8cb85552b7b07bb0416559b2e78fcf9c6926662a52682d81b5f20c90535",
    ),
    ("linux", "arm64"): (
        "rclone-v1.73.2-linux-arm64.zip",
        "rclone",
        "2f7d8b807e6ea638855129052c834ca23aa538d3ad7786e30b8ad1e97c5db47b",
    ),
    ("darwin", "amd64"): (
        "rclone-v1.73.2-osx-amd64.zip",
        "rclone",
        "ff3215b93e4588e0ccfef11e4c49755a91d42f4bc89c98bf89f6d30b0ae16f",
    ),
    ("darwin", "arm64"): (
        "rclone-v1.73.2-osx-arm64.zip",
        "rclone",
        "879fd46e0338bf6244f55af6bde9f151a1711dd62abdc46117a4c11cfb0a601e",
    ),
}

ARCHITECTURE_ALIASES = {
    "amd64": "amd64",
    "x86_64": "amd64",
    "arm64": "arm64",
    "aarch64": "arm64",
}

DEFAULT_DATASET_PATH, _ = toml_dataset_path()


def _project_root() -> pathlib.Path:
    return pathlib.Path(repokit_common.PROJECT_ROOT).resolve()


def _remote_name_from_uri(path: str) -> str:
    """Return the rclone alias portion of a remote URI, if present."""
    return str(path or "").partition(":")[0].strip().lower()


def _is_ucloud_remote(remote_name: str, registry: dict | None = None) -> bool:
    """Determine UCloud membership from registry metadata, with legacy alias fallback."""
    key = (remote_name or "").strip().lower()
    registry = registry if registry is not None else load_all_registry()
    meta = registry.get(key, {}) if isinstance(registry, dict) else {}
    return key.startswith("ucloud") or (
        isinstance(meta, dict) and meta.get("remote_type") == "ucloud"
    )


def _rc_verbose_args(level: int) -> list[str]:
    """Convert verbosity level to rclone args."""
    return ["-" + "v" * min(max(level, 0), 3)] if level > 0 else []


def _rclone_release() -> tuple[str, str, str] | None:
    """Return the pinned archive definition for this platform."""
    system = platform.system().lower()
    architecture = ARCHITECTURE_ALIASES.get(platform.machine().lower())
    release = RCLONE_RELEASES.get((system, architecture or ""))
    if not release:
        print(
            "Unsupported rclone platform "
            f"'{system}/{platform.machine().lower()}'. Please install rclone manually."
        )
    return release


def _safe_extract_zip(archive: zipfile.ZipFile, destination: pathlib.Path) -> None:
    """Extract a ZIP archive only when every member remains below destination."""
    destination = destination.resolve()
    for member in archive.infolist():
        target = (destination / member.filename).resolve()
        if not target.is_relative_to(destination):
            raise ValueError(f"Unsafe path in rclone archive: {member.filename}")
    archive.extractall(destination)


def _download_rclone_archive(
    archive_name: str,
    expected_sha256: str,
    install_root: pathlib.Path,
) -> pathlib.Path:
    """Download one pinned rclone archive and verify its SHA-256 checksum."""
    archive_path = install_root / archive_name
    url = f"https://downloads.rclone.org/v{RCLONE_VERSION}/{archive_name}"
    print(f"Downloading rclone {RCLONE_VERSION} to {archive_path}...")
    digest = hashlib.sha256()
    try:
        response = requests.get(url, stream=True, timeout=(10, 60))
        response.raise_for_status()
        with archive_path.open("wb") as file_handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file_handle.write(chunk)
                    digest.update(chunk)
    except requests.RequestException as exc:
        archive_path.unlink(missing_ok=True)
        raise RuntimeError(f"Could not download rclone: {exc}") from exc
    except OSError as exc:
        archive_path.unlink(missing_ok=True)
        raise RuntimeError(f"Could not save rclone archive: {exc}") from exc

    if digest.hexdigest().lower() != expected_sha256.lower():
        archive_path.unlink(missing_ok=True)
        raise RuntimeError("Downloaded rclone archive failed SHA-256 verification.")
    return archive_path


def install_rclone(install_path: str = "./bin") -> bool:
    """Ensure a project-local rclone executable and config path are available."""

    project_root = _project_root()
    install_root = (project_root / pathlib.Path(install_path)).resolve()
    install_root.mkdir(parents=True, exist_ok=True)
    rclone_config = install_root / "rclone.conf"
    rclone_dir: str

    if not is_installed("rclone", "Rclone", local_path="./bin"):
        release = _rclone_release()
        if not release:
            return False
        archive_name, executable_name, expected_sha256 = release
        archive_path: pathlib.Path | None = None
        try:
            archive_path = _download_rclone_archive(archive_name, expected_sha256, install_root)
            print("Extracting rclone...")
            with zipfile.ZipFile(archive_path, "r") as archive:
                _safe_extract_zip(archive, install_root)
            extracted_dir = install_root / archive_name.removesuffix(".zip")
            rclone_path = extracted_dir / executable_name
            if not rclone_path.is_file():
                print(f"Extracted rclone executable was not found: {rclone_path}")
                return False
            rclone_path.chmod(0o755)
            print(f"rclone installed successfully at {rclone_path}.")
        except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
            print(f"Rclone installation failed: {exc}")
            return False
        finally:
            if archive_path:
                archive_path.unlink(missing_ok=True)
        rclone_dir = str(extracted_dir)
    else:
        # Even when already installed, ensure process PATH includes the resolved local dir.
        rclone_dir = os.environ.get("RCLONE")
        if not rclone_dir:
            resolved = shutil.which("rclone")
            rclone_dir = str(pathlib.Path(resolved).parent) if resolved else str(install_root)

    if not exe_to_path("rclone", rclone_dir):
        return False

    # Keep rclone configuration project-local. An inherited process setting
    # from another project must not redirect a new project's remote registry.
    saved_rclone_config = load_from_env("RCLONE_CONFIG")
    resolved_rclone_config = str(rclone_config)
    if saved_rclone_config:
        saved_path = pathlib.Path(saved_rclone_config).expanduser().resolve()
        if saved_path == rclone_config:
            resolved_rclone_config = str(saved_path)
    if resolved_rclone_config != saved_rclone_config:
        save_to_env(resolved_rclone_config, "RCLONE_CONFIG")
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
) -> bool:
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
        return False

    # Build rclone command
    include_args = []
    for pattern in include_patterns:
        include_args.extend(["--include", pattern])

    exclude_args = []
    for pattern in exclude_patterns:
        exclude_args.extend(["--exclude", pattern])

    if src_kind not in {"local", "remote"}:
        print(f"Error: Invalid src_kind '{src_kind}'. Must be 'local' or 'remote'.")
        return False

    if src_kind == "local" and not os.path.exists(src):
        print(f"Error: The folder '{src}' does not exist.")
        return False

    command = (
        ["rclone", operation, src, dst] + _rc_verbose_args(verbose) + include_args + exclude_args
    )

    # Use ucloud config if applicable
    if (
        _is_ucloud_remote(remote_name)
        or _is_ucloud_remote(_remote_name_from_uri(str(src)))
        or _is_ucloud_remote(_remote_name_from_uri(str(dst)))
    ):
        rclone_conf = pathlib.Path("./bin/rclone_ucloud.conf").resolve()
        if rclone_conf.exists():
            command += ["--config", str(rclone_conf)]
        else:
            print("[WARN] UCloud rclone config not found in ./bin. Please run set_host_port first.")
            return False

    if dry_run:
        command.append("--dry-run")

    try:
        subprocess.run(command, check=True, timeout=DEFAULT_TIMEOUT)
        verb = {"sync": "synchronized", "copy": "copied", "move": "moved (deleted at origin)"}.get(
            operation, operation
        )
        print(f"Transfer '{src}' -> '{dst}' successfully {verb}.")
        update_sync_status(remote_name, action=action, operation=operation, success=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to {operation} transfer '{src}' -> '{dst}': {e}")
        update_sync_status(remote_name, action=action, operation=operation, success=False)
        return False
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        update_sync_status(remote_name, action=action, operation=operation, success=False)
        return False


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


def _join_remote_search_path(base_remote_path: str, sub_path: str, remote_name: str) -> str:
    if not sub_path:
        return base_remote_path
    if base_remote_path == _remote_root(remote_name):
        return f"{base_remote_path}/{sub_path.lstrip('/')}"
    return _join_remote_path(base_remote_path, sub_path)


def _remote_root(remote_name: str) -> str:
    return f"{(remote_name or '').strip().lower()}:"


def _list_target_path(remote_name: str, remote_path: str | None, sub_path: str = "") -> str:
    normalized = (sub_path or "").strip().replace("\\", "/")
    base_remote = remote_path if remote_path else _remote_root(remote_name)
    if normalized in {"", ".", "/"}:
        return base_remote
    if remote_path:
        return _join_remote_path(base_remote, normalized.lstrip("/"))
    return f"{_remote_root(remote_name)}{normalized}"


def _normalize_explicit_remote_path(remote_name: str, remote_path: str | None) -> str | None:
    """
    Normalize a user-provided remote path.

    Accept either:
    - a full rclone remote URI, e.g. ``test:/folder``
    - a remote-scoped path when ``--remote test`` is already supplied,
      e.g. ``/folder`` or ``folder``
    """
    if remote_path is None:
        return None

    normalized = remote_path.strip().replace("\\", "/")
    if normalized in {"", "."}:
        return _remote_root(remote_name)
    if ":" in normalized:
        return normalized
    return f"{_remote_root(remote_name)}{normalized}"


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


def _has_glob_chars(segment: str) -> bool:
    return any(ch in segment for ch in ["*", "?", "["])


def _search_prefix_and_remainder(search_pattern: str | None) -> tuple[str, str, bool]:
    normalized, anchored_to_root = _normalize_search_pattern(search_pattern)
    if not normalized:
        return "", "", anchored_to_root

    stripped = normalized.rstrip("/")
    if not stripped:
        return "", "", anchored_to_root

    parts = [part for part in stripped.split("/") if part]
    if not parts:
        return "", "", anchored_to_root

    first_wildcard_idx = next((i for i, part in enumerate(parts) if _has_glob_chars(part)), None)

    if normalized.endswith("/"):
        if first_wildcard_idx is None:
            return stripped, "", anchored_to_root
        prefix = "/".join(parts[:first_wildcard_idx])
        remainder = "/".join(parts[first_wildcard_idx:]) + "/"
        return prefix, remainder, anchored_to_root

    if first_wildcard_idx is None:
        if len(parts) == 1:
            return "", parts[0], anchored_to_root
        return "/".join(parts[:-1]), parts[-1], anchored_to_root

    if first_wildcard_idx == 0:
        return "", stripped, anchored_to_root

    return (
        "/".join(parts[:first_wildcard_idx]),
        "/".join(parts[first_wildcard_idx:]),
        anchored_to_root,
    )


def _join_local_path(base_path: str, sub_path: str) -> str:
    if not sub_path:
        return base_path
    return str(
        pathlib.Path(base_path) / pathlib.Path(*[part for part in sub_path.split("/") if part])
    )


def _resolve_transfer_search(
    remote_name: str,
    src: str,
    dst: str,
    src_kind: str,
    search_pattern: str | None,
) -> tuple[str, str, list[str]]:
    """
    Resolve a search pattern for transfer commands.

    The search remains relative to the source base by default. If the pattern has a
    deterministic path prefix, narrow the transfer source to that prefix and augment
    the destination with the same prefix so folder structure is preserved.
    """
    prefix_dir, remainder, anchored_to_root = _search_prefix_and_remainder(search_pattern)
    if not search_pattern:
        return src, dst, []

    effective_src = src
    effective_dst = dst
    if src_kind == "remote" and anchored_to_root:
        effective_src = _remote_root(remote_name)

    if prefix_dir:
        if src_kind == "remote":
            effective_src = _join_remote_search_path(effective_src, prefix_dir, remote_name)
        else:
            effective_src = _join_local_path(effective_src, prefix_dir)

        if ":" in str(dst):
            effective_dst = _join_remote_path(str(dst), prefix_dir)
        else:
            effective_dst = _join_local_path(str(dst), prefix_dir)

    include_patterns = _search_include_patterns(remainder) if remainder else []
    return effective_src, effective_dst, include_patterns


def _select_source_path(src: str, src_kind: str, select_path: str | None) -> tuple[str, str]:
    sub_path = _normalize_select_subpath(select_path)
    if not sub_path:
        return src, ""
    if src_kind == "remote":
        return _join_remote_path(src, sub_path), sub_path
    return str(pathlib.Path(src) / pathlib.Path(sub_path)), sub_path


def _parse_selection_indices(raw: str, max_index: int) -> list[int]:
    selected: set[int] = set()
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
    if _is_ucloud_remote(remote_name) or _is_ucloud_remote(_remote_name_from_uri(str(src))):
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
        return _interactive_include_patterns(
            selection_src, src_kind, remote_name, include_prefix=""
        )

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


def _resolve_local_source_path(path: str | None) -> str | None:
    """Resolve an explicit push source relative to the project root."""
    if path is None:
        return None
    candidate = pathlib.Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = _project_root() / candidate
    return str(candidate.resolve())


def _exclude_patterns(local_path: str) -> list[str]:
    """Get exclude patterns from pyproject.toml if applicable."""
    if pathlib.Path(local_path).resolve() == _project_root():
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
    local_path: str | None = None,
    operation: str = "sync",
    dry_run: bool = False,
    verbose: int = 0,
    select_path: str | None = None,
    search_pattern: str | None = None,
) -> bool:
    """Push local files to remote."""
    os.chdir(_project_root())

    if not install_rclone("./bin"):
        return False

    if remote_name.lower() == "all":
        if new_path is not None or local_path is not None:
            print("Error: --path and --remote-path cannot be used with --remote all.")
            return False
        all_remotes = list(load_all_registry().keys())
    else:
        all_remotes = [remote_name]

    flag = False
    attempted = False
    all_succeeded = True
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
            all_succeeded = False
            continue
        if push_policy == "append-only" and operation in {"sync", "move"}:
            print(
                f"Skipping '{remote_name}': push policy is append-only; "
                f"operation '{operation}' is not allowed (use copy)."
            )
            all_succeeded = False
            continue

        _remote_path, _local_path = load_registry(remote_key)
        effective_local_path = _resolve_local_source_path(local_path) or _local_path
        target_path = (
            _normalize_explicit_remote_path(remote_key, new_path)
            if new_path is not None
            else _remote_path
        )
        if not target_path:
            print(
                f"Remote '{remote_name}' has no saved remote path. "
                "Provide --remote-path or pin a remote base first."
            )
            all_succeeded = False
            continue
        if not effective_local_path:
            print(
                f"Remote '{remote_name}' has no saved local source. "
                "Provide --path or create a full mapping."
            )
            all_succeeded = False
            continue
        if rclone_commit:
            flag = rclone_commit(
                effective_local_path,
                flag,
                msg=f"Rclone Push from {effective_local_path} to {target_path}",
            )
        exclude_patterns = _exclude_patterns(effective_local_path)
        exclude_patterns += _nested_remote_excludes(remote_key, effective_local_path, registry)
        exclude_patterns = sorted(set(exclude_patterns))
        transfer_src = effective_local_path
        transfer_dst = target_path
        include_patterns: list[str] = []
        if search_pattern:
            transfer_src, transfer_dst, include_patterns = _resolve_transfer_search(
                remote_name=remote_key,
                src=effective_local_path,
                dst=target_path,
                src_kind="local",
                search_pattern=search_pattern,
            )
        if select_path is not None:
            selected = _select_include_patterns(
                effective_local_path,
                "local",
                remote_name.lower(),
                select_path,
            )
            if selected is None:
                all_succeeded = False
                continue
            include_patterns = selected

        attempted = True
        succeeded = _rclone_transfer(
            remote_name=remote_key,
            src=transfer_src,
            dst=transfer_dst,
            src_kind="local",
            action="push",
            operation=operation,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            dry_run=dry_run,
            verbose=verbose,
        )
        all_succeeded = all_succeeded and succeeded
    return attempted and all_succeeded


def pull_rclone(
    remote_name: str,
    remote_path: str = None,
    new_path: str = None,
    operation: str = "sync",
    dry_run: bool = False,
    verbose: int = 0,
    select_path: str | None = None,
    search_pattern: str | None = None,
) -> bool:
    """Pull files from remote to local."""
    if remote_name is None:
        print("Error: No remote specified for pulling backup.")
        return False
    if remote_name.lower() == "all":
        print("Error: Pulling from 'all' remotes is not supported.")
        return False

    os.chdir(_project_root())

    if not install_rclone("./bin"):
        return False

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

    explicit_remote_path = _normalize_explicit_remote_path(remote_name.lower(), remote_path)
    has_full_mapping = bool(_remote_path and _local_path)
    effective_remote_path = explicit_remote_path or _remote_path
    effective_local_path = new_path or _local_path

    if not has_full_mapping:
        if not new_path:
            print(
                f"Remote '{remote_name}' has no saved mapping with a local path. "
                "Provide --path for pull destination."
            )
            return False
        if not effective_remote_path:
            effective_remote_path = f"{remote_name.lower()}:"
            print(
                f"Remote '{remote_name}' has no saved remote path. "
                f"Defaulting pull source to remote root '{effective_remote_path}'."
            )

    if not effective_remote_path:
        print(f"Error: No remote source path resolved for '{remote_name}'.")
        return False
    if not effective_local_path:
        print(f"Error: No local destination path resolved for '{remote_name}'.")
        return False

    try:
        os.makedirs(effective_local_path, exist_ok=True)
    except OSError as exc:
        print(f"Error: Could not create pull destination '{effective_local_path}': {exc}")
        return False
    if rclone_commit:
        _ = rclone_commit(
            effective_local_path,
            False,
            msg=f"Rclone Pull from {effective_remote_path} to {effective_local_path}",
        )
    exclude_patterns = []
    if effective_local_path:
        exclude_patterns = _exclude_patterns(effective_local_path)
        exclude_patterns += _nested_remote_excludes(
            remote_name.lower(), effective_local_path, registry
        )
    exclude_patterns = sorted(set(exclude_patterns))
    transfer_remote_path = effective_remote_path
    transfer_local_path = effective_local_path
    include_patterns: list[str] = []
    if search_pattern:
        transfer_remote_path, transfer_local_path, include_patterns = _resolve_transfer_search(
            remote_name=remote_name.lower(),
            src=effective_remote_path,
            dst=effective_local_path,
            src_kind="remote",
            search_pattern=search_pattern,
        )
    if select_path is not None:
        selected = _select_include_patterns(
            transfer_remote_path,
            "remote",
            remote_name.lower(),
            select_path,
        )
        if selected is None:
            return False
        include_patterns = selected
        # Ensure local parent path exists for direct file selections.
        normalized = _normalize_select_subpath(select_path)
        if normalized and not normalized.endswith("/"):
            local_target = pathlib.Path(transfer_local_path) / pathlib.Path(normalized)
            local_target.parent.mkdir(parents=True, exist_ok=True)

    try:
        os.makedirs(transfer_local_path, exist_ok=True)
    except OSError as exc:
        print(f"Error: Could not create pull destination '{transfer_local_path}': {exc}")
        return False

    return _rclone_transfer(
        remote_name=remote_name.lower(),
        src=transfer_remote_path,
        dst=transfer_local_path,
        src_kind="remote",
        action="pull",
        operation=operation,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        dry_run=dry_run,
        verbose=verbose,
    )


def rclone_diff_report(local_path: str, remote_path: str) -> bool:
    """Generate a dry-run rclone diff report and return whether it completed."""
    import tempfile

    command = ["rclone", "diff"]
    if _is_ucloud_remote(_remote_name_from_uri(remote_path)):
        rclone_conf = pathlib.Path("./bin/rclone_ucloud.conf").resolve()
        if not rclone_conf.exists():
            print("[WARN] UCloud rclone config not found in ./bin. Cannot run diff.")
            return False
        command += ["--config", str(rclone_conf)]

    command += [
        local_path,
        remote_path,
        "--no-traverse",
        "--differ",
        "--missing-on-dst",
        "--missing-on-src",
        "--dry-run",
    ]

    fd, output_name = tempfile.mkstemp(prefix="repokit-rclone-diff-", suffix=".txt")
    os.close(fd)
    try:
        subprocess.run(command + ["--output", output_name], check=True, timeout=DEFAULT_TIMEOUT)
        diff_output = pathlib.Path(output_name).read_text(encoding="utf-8")
        print(diff_output or "[No differences]")
        return True
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Failed to generate diff report: {exc}")
        return False
    finally:
        pathlib.Path(output_name).unlink(missing_ok=True)


def generate_diff_report(remote_name: str) -> bool:
    """Generate a diff report for one remote or every registered remote."""

    def run_diff(remote: str) -> bool:
        remote_path, local_path = load_registry(remote)
        if not remote_path or not local_path:
            print(f"No path found for remote '{remote}'.")
            return False
        print(f"\nDiff report for '{remote}':")
        return rclone_diff_report(local_path, remote_path)

    if remote_name.lower() == "all":
        remotes = list(load_all_registry().keys())
        if not remotes:
            print("No remotes found.")
            return False
        return all(run_diff(remote) for remote in remotes)
    return run_diff(remote_name)


def list_remote_entries(
    remote_name: str,
    sub_path: str = "",
    search_pattern: str | None = None,
) -> bool:
    """List or search a remote path and return whether rclone completed."""
    remote_name = (remote_name or "").strip().lower()
    remote_path, _ = load_registry(remote_name)
    if not remote_path:
        print(f"No mapped path for '{remote_name}'. Listing remote root.")

    target = _list_target_path(remote_name, remote_path, sub_path)
    normalized_search, anchored_to_root = _normalize_search_pattern(search_pattern)
    if normalized_search:
        target = _remote_root(remote_name) if anchored_to_root else target
        command = ["rclone", "lsf", target, "--recursive", "--include", normalized_search]
    else:
        command = ["rclone", "lsf", target, "--max-depth", "1"]

    if _is_ucloud_remote(remote_name) or _is_ucloud_remote(_remote_name_from_uri(str(target))):
        rclone_conf = pathlib.Path("./bin/rclone_ucloud.conf").resolve()
        if rclone_conf.exists():
            command += ["--config", str(rclone_conf)]
        else:
            print("[WARN] UCloud rclone config not found in ./bin. Please run set_host_port first.")
            return False

    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=DEFAULT_TIMEOUT,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        action = "search" if normalized_search else "list"
        print(f"Failed to {action} remote entries at '{target}': {exc}")
        return False

    entries = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if normalized_search:
        print(f"\nRemote search for '{remote_name}': {target} | pattern={normalized_search}")
    else:
        print(f"\nRemote listing for '{remote_name}': {target}")
    if not entries:
        print("[No matches]" if normalized_search else "[Empty]")
        return True
    for entry in sorted(entries, key=lambda item: (not item.endswith("/"), item.lower())):
        print(f"  {entry}")
    return True


def transfer_between_remotes(
    source_remote: str,
    dest_remote: str,
    operation: str = "copy",
    dry_run: bool = True,
    verbose: int = 0,
) -> bool:
    """Transfer between compatible mapped remotes and return the rclone result."""
    all_remotes = load_all_registry()
    src_meta = all_remotes.get(source_remote)
    dst_meta = all_remotes.get(dest_remote)

    if not src_meta or not dst_meta:
        print(
            f"Error: One or both remotes not registered. Source: {source_remote}, Destination: {dest_remote}"
        )
        return False

    src_local = src_meta.get("local_path")
    dst_local = dst_meta.get("local_path")
    if not src_local or not dst_local:
        print("Error: One or both remotes do not have local paths configured.")
        return False
    if os.path.abspath(src_local) != os.path.abspath(dst_local):
        print("Error: Cannot transfer between remotes with different local paths.")
        print(f"Source local path: {src_local}")
        print(f"Destination local path: {dst_local}")
        return False

    src_path = src_meta.get("remote_path")
    dst_path = dst_meta.get("remote_path")
    if not src_path or not dst_path:
        print("Error: One or both remotes do not have remote paths configured.")
        return False
    if operation not in {"copy", "sync"}:
        print("Error: Only 'copy' or 'sync' operations are allowed for remote-to-remote transfers.")
        return False

    print(f"\nTransfer from '{source_remote}' to '{dest_remote}'")
    print(f"Local path (shared): {src_local}")
    print(f"Remote paths: {src_path} -> {dst_path}")
    print(f"Operation: {operation} | Dry run: {dry_run}\n")
    return _rclone_transfer(
        remote_name=f"{source_remote}->{dest_remote}",
        src=src_path,
        dst=dst_path,
        src_kind="remote",
        action="transfer",
        operation=operation,
        exclude_patterns=_exclude_patterns(src_local),
        dry_run=dry_run,
        verbose=verbose,
    )
