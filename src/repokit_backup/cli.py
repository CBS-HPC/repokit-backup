"""
CLI interface - Argument parsing and command dispatch.
"""

import argparse
import importlib
import json
import math
import os
import pathlib
import sys

from .remote_types import CANONICAL_BACKENDS, normalize_backend

# from ..common import ensure_correct_kernel

SUPPORTED_BACKENDS = CANONICAL_BACKENDS
RUNTIME_GITIGNORE_ENTRIES = (".env", "bin/")


def _parse_transfer_timeout(value: str) -> float | None:
    """Parse a total transfer limit where zero disables the limit."""
    try:
        timeout = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number of seconds") from exc
    if not math.isfinite(timeout) or timeout < 0:
        raise argparse.ArgumentTypeError("must be zero or a positive number of seconds")
    return None if timeout == 0 else timeout


def _repokit_common_module():
    """Import Common only after the CLI has selected its project root."""
    import repokit_common

    return repokit_common


def _activate_repokit_common_root(project_root: pathlib.Path):
    """Align Common's cached root values with this CLI invocation.

    Common 1.0 currently exposes ``PROJECT_ROOT`` from several compatibility
    modules. Prefer its future public setter when available; otherwise keep
    those cached imports aligned for an explicit ``--project-root``.
    """
    repokit_common = _repokit_common_module()
    resolved_root = project_root.resolve()
    set_project_root = getattr(repokit_common, "set_project_root", None)
    if callable(set_project_root):
        set_project_root(resolved_root)
        return repokit_common

    for module_name in (
        "repokit_common",
        "repokit_common.base",
        "repokit_common.env",
        "repokit_common.secretstore",
        "repokit_common.tomlutils",
    ):
        module = importlib.import_module(module_name)
        if hasattr(module, "PROJECT_ROOT"):
            setattr(module, "PROJECT_ROOT", resolved_root)
    return repokit_common


def _resolved_add_backend(explicit_backend: str | None, _remote_alias: str) -> str:
    if not explicit_backend:
        raise ValueError(
            "--backend is required for `repokit-backup add`. "
            f"Supported values: {', '.join(SUPPORTED_BACKENDS)}"
        )
    backend = normalize_backend(explicit_backend)
    if not backend:
        raise ValueError(
            f"Unsupported backend '{explicit_backend}'. Supported values: {', '.join(SUPPORTED_BACKENDS)}"
        )
    return backend


def _resolve_cli_project_root(
    explicit_project_root: str | None,
    command: str | None = None,
) -> pathlib.Path:
    """Resolve the project root for the current CLI invocation."""
    if explicit_project_root:
        resolved_root = pathlib.Path(explicit_project_root).expanduser().resolve()
        if not resolved_root.exists() or not resolved_root.is_dir():
            raise ValueError(
                f"Error: --project-root does not exist or is not a directory: {resolved_root}"
            )
        return resolved_root
    if command == "init":
        return pathlib.Path.cwd().resolve()
    # Auto-detection intentionally imports Common while still in the caller's
    # directory. For --project-root and init, import happens after chdir below.
    from repokit_common.base import project_root as detect_project_root

    return detect_project_root(extra_markers={"bin/rclone_remote.json", "bin/rclone.conf"})


def _ensure_rcloneignore_pyproject_config() -> None:
    """
    Ensure pyproject.toml exists and has [tool.rcloneignore] defaults.
    """
    defaults = {
        "tool-description": "Ignore patterns for backup and remote synchronization.",
        "tool-replaces": ".rcloneignore",
        "patterns": ["bin/", ".venv/", ".conda/"],
    }
    repokit_common = _repokit_common_module()

    current = (
        repokit_common.read_toml(
            folder=str(repokit_common.PROJECT_ROOT),
            json_filename=repokit_common.JSON_FILENAME,
            tool_name="rcloneignore",
            toml_path=repokit_common.TOML_PATH,
        )
        or {}
    )

    patterns = current.get("patterns", [])
    if isinstance(patterns, str):
        pattern_list = [patterns]
    elif isinstance(patterns, list):
        pattern_list = [p for p in patterns if isinstance(p, str) and p.strip()]
    else:
        pattern_list = []

    merged_patterns = list(pattern_list)
    seen = {p.strip() for p in pattern_list}
    for p in defaults["patterns"]:
        if p not in seen:
            merged_patterns.append(p)
            seen.add(p)

    payload = {
        "tool-description": current.get("tool-description") or defaults["tool-description"],
        "tool-replaces": current.get("tool-replaces") or defaults["tool-replaces"],
        "patterns": merged_patterns,
    }

    repokit_common.write_toml(
        data=payload,
        folder=str(repokit_common.PROJECT_ROOT),
        json_filename=repokit_common.JSON_FILENAME,
        tool_name="rcloneignore",
        toml_path=repokit_common.TOML_PATH,
    )


def _ensure_runtime_gitignore() -> None:
    """Exclude project-local credentials and rclone state from version control."""
    repokit_common = _repokit_common_module()
    gitignore_path = pathlib.Path(repokit_common.PROJECT_ROOT) / ".gitignore"
    try:
        current = gitignore_path.read_text(encoding="utf-8") if gitignore_path.exists() else ""
        entries = {line.strip() for line in current.splitlines() if line.strip()}
        missing = [entry for entry in RUNTIME_GITIGNORE_ENTRIES if entry not in entries]
        if not missing:
            return
        separator = "" if not current or current.endswith("\n") else "\n"
        addition = "# Project-local repokit-backup runtime state\n" + "\n".join(missing) + "\n"
        gitignore_path.write_text(current + separator + addition, encoding="utf-8")
    except OSError as exc:
        print(f"Warning: could not update {gitignore_path}: {exc}")


def _bootstrap_project_runtime(install_rclone_fn) -> tuple[pathlib.Path, pathlib.Path]:
    """
    Ensure local project state for repokit-backup exists.

    Returns:
        (bin_dir, pyproject_path)
    """
    _ensure_runtime_gitignore()
    _ensure_rcloneignore_pyproject_config()
    if not install_rclone_fn("./bin"):
        raise RuntimeError("Error: rclone installation/verification failed.")
    repokit_common = _repokit_common_module()
    bin_dir = (repokit_common.PROJECT_ROOT / pathlib.Path("./bin")).resolve()
    pyproject_path = (
        repokit_common.PROJECT_ROOT / pathlib.Path(repokit_common.TOML_PATH)
    ).resolve()
    return bin_dir, pyproject_path


def _read_secret_file(path_value: str | None, label: str) -> str | None:
    """Read a required non-empty secret from a local file without echoing it."""
    if not path_value:
        return None
    path = pathlib.Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"{label} file not found: {path}")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"{label} file is empty: {path}")
    return value


def _load_rclone_options(path_value: str | None) -> dict[str, str] | None:
    """Load flat rclone config options for a generic non-interactive backend."""
    if not path_value:
        return None
    path = pathlib.Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"Rclone options file not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Rclone options file is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict) or not raw:
        raise ValueError("Rclone options file must contain a non-empty JSON object.")

    options: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key.strip() or not key.replace("_", "").isalnum():
            raise ValueError(
                "Rclone option names must contain only letters, digits, and underscores."
            )
        if isinstance(value, bool):
            options[key] = "true" if value else "false"
        elif isinstance(value, (str, int, float)):
            options[key] = str(value)
        else:
            raise ValueError(f"Rclone option '{key}' must have a scalar JSON value.")
    return options


def _validate_non_interactive_add(args, local_path: str | None) -> None:
    """Ensure `add --non-interactive` has every decision that would otherwise prompt."""
    mapping_mode = getattr(args, "mapping_mode", None)
    if mapping_mode is None:
        raise ValueError("--mapping is required with --non-interactive.")
    remote_path = getattr(args, "add_remote_path", None)
    policy = getattr(args, "add_policy", None)
    if getattr(args, "ssh_mode", False):
        raise ValueError(
            "--ssh cannot be used with --non-interactive; use --token or --token-file."
        )
    if mapping_mode == "full":
        if not local_path:
            raise ValueError("--mapping full requires --path or --subdir.")
        if not remote_path:
            raise ValueError("--mapping full requires --remote-path.")
    elif mapping_mode == "remote-only":
        if local_path:
            raise ValueError("--mapping remote-only cannot be combined with --path or --subdir.")
        if not remote_path:
            raise ValueError("--mapping remote-only requires --remote-path.")
    elif mapping_mode == "none":
        if local_path or remote_path:
            raise ValueError(
                "--mapping none cannot be combined with --path, --subdir, or --remote-path."
            )
    if mapping_mode != "none" and not policy:
        raise ValueError("--policy is required with --non-interactive when paths are saved.")
    if getattr(args, "on_existing", "error") == "merge" and mapping_mode != "full":
        raise ValueError("--on-existing merge requires --mapping full.")


# @ensure_correct_kernel
def main():
    """Main CLI entry point."""
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("command", nargs="?")
    pre_parser.add_argument(
        "--project-root",
        dest="project_root",
        help="Explicit project root directory (overrides auto-detection).",
    )
    pre_args, _ = pre_parser.parse_known_args()

    try:
        resolved_root = _resolve_cli_project_root(
            explicit_project_root=pre_args.project_root,
            command=getattr(pre_args, "command", None),
        )
    except ValueError as exc:
        print(str(exc))
        sys.exit(2)

    os.chdir(resolved_root)
    repokit_common = _activate_repokit_common_root(resolved_root)

    # Import after root resolution so modules that read PROJECT_ROOT at import-time
    # capture the resolved root, not the shell subdirectory.
    from .rclone import (
        generate_diff_report,
        install_rclone,
        list_remote_entries,
        pull_rclone,
        push_rclone,
        transfer_between_remotes,
    )
    from .remotes import (
        delete_remote,
        list_remotes,
        list_supported_remote_types,
        setup_rclone,
    )
    from .registry import set_push_policy, set_remote_pin

    parser = argparse.ArgumentParser(description="Backup manager CLI using rclone")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Global arguments
    parser.add_argument(
        "--dry-run", action="store_true", help="Do not modify remote; show actions."
    )
    parser.add_argument(
        "-v", "--verbose", action="count", default=1, help="Increase verbosity (-v, -vv, -vvv)."
    )
    parser.add_argument(
        "--project-root",
        dest="project_root",
        help="Explicit project root directory (overrides auto-detection).",
    )

    # Init command
    subparsers.add_parser(
        "init",
        help="Initialize repokit-backup in the current project root (creates ./bin and pyproject.toml config).",
    )

    # List command
    subparsers.add_parser("list", help="List rclone remotes and mapped folders")

    # Types command
    subparsers.add_parser("types", help="List supported remote types")

    # List remote entries command
    ls = subparsers.add_parser("ls", help="List files/folders at a configured remote path")
    ls.add_argument("--remote", required=True, help="Remote name")
    ls.add_argument(
        "--path",
        dest="list_path",
        default="",
        help="Optional subpath under the mapped remote root (e.g. /data).",
    )
    ls.add_argument(
        "--search",
        dest="search_pattern",
        default=None,
        help=(
            "Optional recursive glob search. "
            "Relative patterns search under --path/current base; leading '/' anchors to remote root."
        ),
    )

    # Policy command
    policy = subparsers.add_parser("policy", help="Update push/pull policy for a configured remote")
    policy.add_argument("--remote", required=True, help="Remote name")
    policy.add_argument(
        "--set",
        dest="policy_value",
        required=True,
        choices=["full", "append-only", "pull-only"],
        help="Policy value to set",
    )

    # Add command
    add = subparsers.add_parser("add", help="Add a remote and folder mapping")
    add.add_argument("--remote", required=True, help="Remote name")
    add.add_argument(
        "--backend",
        required=True,
        help=(
            "Backend type for the remote being created "
            "(examples: dropbox, onedrive, drive, erda, ucloud, lumio/lumi-o, lumip/lumi-p/lumi-f, local, s3, sftp)."
        ),
    )
    add_paths = add.add_mutually_exclusive_group()
    add_paths.add_argument(
        "--subdir",
        dest="project_subdir",
        help="Project-relative source subdirectory to use/create (e.g. data).",
    )
    add_paths.add_argument(
        "--path",
        dest="source_path",
        help="Filesystem source path (absolute or relative to current shell directory).",
    )
    add_paths.add_argument(
        "--local-path",
        "--local_path",
        dest="legacy_local_path",
        help="Deprecated alias for --path (kept for backward compatibility).",
    )
    add.add_argument(
        "--remote-path",
        dest="add_remote_path",
        help="Persistent remote base path. Required for non-interactive saved mappings.",
    )
    add.add_argument(
        "--mapping",
        dest="mapping_mode",
        choices=["full", "remote-only", "none"],
        help="Saved path mode: full local/remote mapping, remote-only pin, or no paths.",
    )
    add.add_argument(
        "--policy",
        dest="add_policy",
        choices=["full", "append-only", "pull-only"],
        help="Persistent transfer policy for the remote.",
    )
    add.add_argument(
        "--on-existing",
        choices=["error", "use", "merge", "overwrite"],
        default="error",
        help="How to handle an existing remote folder (non-interactive default: error).",
    )
    add.add_argument(
        "--non-interactive",
        action="store_true",
        help="Forbid prompts; require flags, persisted values, or supplied secret files.",
    )
    add.add_argument(
        "--token",
        dest="oauth_token",
        help="OAuth token JSON output from `rclone authorize` (dropbox/onedrive/drive)",
    )
    add.add_argument(
        "--token-file",
        dest="oauth_token_file",
        help="Path to file containing OAuth token JSON output from `rclone authorize`",
    )
    add.add_argument(
        "--ssh",
        "--ssh-mode",
        "--shh-mode",
        dest="ssh_mode",
        action="store_true",
        help="Enable SSH tunnel instructions for OAuth remotes (headless setup).",
    )
    add.add_argument("--lumio-project-id", help="LUMI-O project id for non-interactive setup.")
    add.add_argument("--lumio-access-key", help="LUMI-O access key for non-interactive setup.")
    add.add_argument(
        "--lumio-secret-file",
        help="File containing the LUMI-O secret key for non-interactive setup.",
    )
    add.add_argument("--lumip-project-id", help="LUMI-P project id for non-interactive setup.")
    add.add_argument("--lumip-username", help="LUMI-P username for non-interactive setup.")
    add.add_argument("--erda-username", help="ERDA username for non-interactive setup.")
    add.add_argument(
        "--erda-password-file",
        help="File containing the ERDA password for non-interactive setup.",
    )
    add.add_argument(
        "--ssh-key-path",
        help="SSH private key path for LUMI-P or UCloud non-interactive setup.",
    )
    add.add_argument(
        "--use-ssh-agent",
        action="store_true",
        help="Use ssh-agent instead of an SSH key file for supported SFTP backends.",
    )
    add.add_argument("--ucloud-port", help="UCloud SSH port for non-interactive setup.")
    add.add_argument(
        "--rclone-options-file",
        help="JSON file of flat rclone config options for generic sftp or s3 backends.",
    )

    # Push command
    push = subparsers.add_parser("push", help="Push/backup to remote")
    push.add_argument("--remote", required=True, help="Remote name")
    push.add_argument(
        "--mode",
        choices=["sync", "copy", "move"],
        default="sync",
        help="sync: mirror (default), copy: no deletes, move: delete source after",
    )
    push.add_argument("--remote-path", help="remote path to backup")
    push.add_argument(
        "--path",
        dest="local_path",
        help="Override the saved local source path; required for remote-only pins.",
    )
    push.add_argument(
        "--search",
        dest="search_pattern",
        default=None,
        help=(
            "Recursive glob filter for source files. "
            "Examples: /data/**/*.parquet, data/*.csv, /*/file_*.txt"
        ),
    )
    push.add_argument(
        "--select",
        nargs="?",
        const=".",
        default=None,
        help="Interactively select files/folders to transfer. Optional subpath scope (e.g. --select /data).",
    )
    push.add_argument(
        "--transfer-timeout",
        type=_parse_transfer_timeout,
        metavar="SECONDS",
        help="Total transfer limit per remote; 0 or omission allows unlimited duration.",
    )

    # Pull command
    pull = subparsers.add_parser("pull", help="Pull/restore from remote")
    pull.add_argument("--remote", required=True, help="Remote name")
    pull.add_argument(
        "--mode",
        choices=["sync", "copy", "move"],
        default="sync",
        help="sync: mirror (default), copy: no deletes, move: delete source after",
    )
    pull.add_argument(
        "--remote-path",
        dest="remote_path",
        help="Override source path on remote when pulling.",
    )
    pull.add_argument(
        "--path",
        "--local-path",
        "--local_path",
        dest="local_path",
        help="Override destination path (`--local-path` kept as legacy alias).",
    )

    # Pin command
    pin = subparsers.add_parser("pin", help="Pin or clear a default remote base path")
    pin.add_argument("--remote", required=True, help="Registered remote name")
    pin_paths = pin.add_mutually_exclusive_group(required=True)
    pin_paths.add_argument("--remote-path", help="Remote base path to pin")
    pin_paths.add_argument("--clear", action="store_true", help="Clear the saved remote pin")
    pull.add_argument(
        "--search",
        dest="search_pattern",
        default=None,
        help=(
            "Recursive glob filter for source files. "
            "Examples: /data/**/*.parquet, data/*.csv, /*/file_*.txt"
        ),
    )
    pull.add_argument(
        "--select",
        nargs="?",
        const=".",
        default=None,
        help="Interactively select files/folders to transfer. Optional subpath scope (e.g. --select /data).",
    )
    pull.add_argument(
        "--transfer-timeout",
        type=_parse_transfer_timeout,
        metavar="SECONDS",
        help="Total transfer limit; 0 or omission allows unlimited duration.",
    )

    # Delete command
    delete = subparsers.add_parser("delete", help="Delete a remote and its mapping")
    delete.add_argument("--remote", required=True, help="Remote name or 'all'")

    # Diff command
    diff = subparsers.add_parser("diff", help="Generate a diff report for a remote")
    diff.add_argument("--remote", required=True, help="Remote name")

    # Transfer command (remote-to-remote)
    transfer = subparsers.add_parser("transfer", help="Transfer data between two remotes")
    transfer.add_argument("--source", required=True, help="Source remote name")
    transfer.add_argument("--destination", required=True, help="Destination remote name")
    transfer.add_argument(
        "--mode", choices=["copy", "sync"], default="copy", help="Operation: copy or sync"
    )
    transfer.add_argument(
        "--confirm", action="store_true", help="Confirm execution (otherwise dry-run)"
    )
    transfer.add_argument(
        "--transfer-timeout",
        type=_parse_transfer_timeout,
        metavar="SECONDS",
        help="Total transfer limit; 0 or omission allows unlimited duration.",
    )

    args = parser.parse_args()

    try:
        bin_dir, pyproject_path = _bootstrap_project_runtime(install_rclone)
    except RuntimeError as exc:
        print(str(exc))
        sys.exit(1)

    # Normalize add source path options.
    add_local_path = None
    if getattr(args, "command", None) == "add":
        project_subdir = getattr(args, "project_subdir", None)
        source_path = getattr(args, "source_path", None)
        legacy_local_path = getattr(args, "legacy_local_path", None)

        if legacy_local_path and not source_path:
            print("[WARN] --local-path is deprecated for add; use --path instead.")
            source_path = legacy_local_path

        if project_subdir:
            normalized_subdir = (project_subdir or "").strip().replace("\\", "/")
            if normalized_subdir.startswith("/"):
                # Allow convenient /data style input but keep it project-relative.
                normalized_subdir = normalized_subdir.lstrip("/")
            project_subdir_path = pathlib.Path(normalized_subdir).expanduser()
            if project_subdir_path.is_absolute():
                print("Error: --subdir must be project-relative.")
                sys.exit(2)
            resolved_subdir = (pathlib.Path.cwd().resolve() / project_subdir_path).resolve()
            resolved_subdir.mkdir(parents=True, exist_ok=True)
            add_local_path = str(resolved_subdir)
        elif source_path:
            if source_path == ".":
                source_path = str(pathlib.Path.cwd().resolve())
            add_local_path = source_path

    # Handle commands
    if hasattr(args, "remote") and args.remote:
        remote = args.remote.strip().lower()

        add_backend = None
        if args.command == "add":
            try:
                add_backend = _resolved_add_backend(getattr(args, "backend", None), remote)
            except ValueError as exc:
                print(f"Error: {exc}")
                sys.exit(2)

        # Dispatch commands
        if args.command == "add":
            oauth_token = getattr(args, "oauth_token", None)
            oauth_token_file = getattr(args, "oauth_token_file", None)

            if oauth_token and oauth_token_file:
                print("Error: use only one of --token or --token-file.")
                sys.exit(2)

            if oauth_token_file:
                token_path = pathlib.Path(oauth_token_file).expanduser().resolve()
                if not token_path.exists():
                    print(f"Error: token file not found: {token_path}")
                    sys.exit(2)
                try:
                    oauth_token = token_path.read_text(encoding="utf-8").strip()
                    # Validate JSON early for clear CLI feedback.
                    json.loads(oauth_token)
                except Exception as e:
                    print(f"Error: invalid token JSON in {token_path}: {e}")
                    sys.exit(2)

            try:
                backend_config = {
                    "lumio_project_id": getattr(args, "lumio_project_id", None),
                    "lumio_access_key": getattr(args, "lumio_access_key", None),
                    "lumio_secret_key": _read_secret_file(
                        getattr(args, "lumio_secret_file", None), "LUMI-O secret"
                    ),
                    "lumip_project_id": getattr(args, "lumip_project_id", None),
                    "lumip_username": getattr(args, "lumip_username", None),
                    "erda_username": getattr(args, "erda_username", None),
                    "erda_password": _read_secret_file(
                        getattr(args, "erda_password_file", None), "ERDA password"
                    ),
                    "ssh_key_path": getattr(args, "ssh_key_path", None),
                    "use_ssh_agent": bool(getattr(args, "use_ssh_agent", False)),
                    "ucloud_port": getattr(args, "ucloud_port", None),
                }
                rclone_options = _load_rclone_options(getattr(args, "rclone_options_file", None))
                if getattr(args, "non_interactive", False):
                    _validate_non_interactive_add(args, add_local_path)
            except ValueError as exc:
                print(f"Error: {exc}")
                sys.exit(2)

            created = setup_rclone(
                remote,
                backend=add_backend,
                local_backup_path=add_local_path,
                oauth_token=oauth_token,
                ssh_mode=getattr(args, "ssh_mode", False),
                non_interactive=getattr(args, "non_interactive", False),
                mapping_mode=getattr(args, "mapping_mode", None),
                remote_path=getattr(args, "add_remote_path", None),
                push_policy=getattr(args, "add_policy", None),
                on_existing=(
                    getattr(args, "on_existing", "error")
                    if getattr(args, "non_interactive", False)
                    else None
                ),
                backend_config=backend_config,
                rclone_options=rclone_options,
            )
            if not created:
                sys.exit(1)

        elif args.command == "push":
            if getattr(args, "search_pattern", None) and getattr(args, "select", None) is not None:
                print("Error: use either --search or --select for push, not both.")
                sys.exit(2)
            mode = getattr(args, "mode", "sync")
            ok = push_rclone(
                remote_name=remote,
                new_path=args.remote_path,
                local_path=args.local_path,
                operation=mode,
                dry_run=args.dry_run,
                verbose=args.verbose,
                select_path=getattr(args, "select", None),
                search_pattern=getattr(args, "search_pattern", None),
                transfer_timeout=getattr(args, "transfer_timeout", None),
            )
            if not ok:
                sys.exit(1)

        elif args.command == "pull":
            if getattr(args, "search_pattern", None) and getattr(args, "select", None) is not None:
                print("Error: use either --search or --select for pull, not both.")
                sys.exit(2)
            mode = getattr(args, "mode", "sync")
            ok = pull_rclone(
                remote_name=remote,
                remote_path=args.remote_path,
                new_path=args.local_path,
                operation=mode,
                dry_run=args.dry_run,
                verbose=args.verbose,
                select_path=getattr(args, "select", None),
                search_pattern=getattr(args, "search_pattern", None),
                transfer_timeout=getattr(args, "transfer_timeout", None),
            )
            if not ok:
                sys.exit(1)

        elif args.command == "delete":
            ok = delete_remote(remote_name=remote, verbose=args.verbose)
            if not ok:
                sys.exit(1)

        elif args.command == "pin":
            pinned_path = None if getattr(args, "clear", False) else args.remote_path
            if not set_remote_pin(remote_name=remote, remote_path=pinned_path):
                sys.exit(2)

        elif args.command == "diff":
            if not generate_diff_report(remote_name=remote):
                sys.exit(1)
        elif args.command == "ls":
            if not list_remote_entries(
                remote_name=remote,
                sub_path=getattr(args, "list_path", ""),
                search_pattern=getattr(args, "search_pattern", None),
            ):
                sys.exit(1)
        elif args.command == "policy":
            ok = set_push_policy(remote_name=remote, push_policy=getattr(args, "policy_value", ""))
            if not ok:
                sys.exit(2)

    elif args.command == "transfer":
        # Remote-to-remote transfer
        operation = getattr(args, "mode", "copy")
        dry_run = not args.confirm  # If not confirmed, run in dry-run
        if not transfer_between_remotes(
            source_remote=args.source.strip().lower(),
            dest_remote=args.destination.strip().lower(),
            operation=operation,
            dry_run=dry_run,
            verbose=args.verbose,
            transfer_timeout=getattr(args, "transfer_timeout", None),
        ):
            sys.exit(1)

    else:
        # Commands without a remote
        if args.command == "init":
            print(f"Initialized repokit-backup in {repokit_common.PROJECT_ROOT}")
            print(f"rclone bin: {bin_dir}")
            print(f"pyproject: {pyproject_path}")
        elif args.command == "list":
            list_remotes()
        elif args.command == "types":
            list_supported_remote_types()
        else:
            parser.print_help()
            sys.exit(2)


if __name__ == "__main__":
    main()
