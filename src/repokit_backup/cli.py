"""
CLI interface - Argument parsing and command dispatch.
"""

import argparse
import json
import os
import pathlib
import sys

import repokit_common
from repokit_common.base import project_root as detect_project_root
from .remote_types import CANONICAL_BACKENDS, normalize_backend, resolve_backend

# from ..common import ensure_correct_kernel

SUPPORTED_BACKENDS = CANONICAL_BACKENDS


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


def _ensure_rcloneignore_pyproject_config() -> None:
    """
    Ensure pyproject.toml exists and has [tool.rcloneignore] defaults.
    """
    defaults = {
        "tool-description": "Ignore patterns for backup and remote synchronization.",
        "tool-replaces": ".rcloneignore",
        "patterns": ["bin/", ".venv/", ".conda/"],
    }

    current = repokit_common.read_toml(
        folder=str(repokit_common.PROJECT_ROOT),
        json_filename=repokit_common.JSON_FILENAME,
        tool_name="rcloneignore",
        toml_path=repokit_common.TOML_PATH,
    ) or {}

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


# @ensure_correct_kernel
def main():
    """Main CLI entry point."""
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument(
        "--project-root",
        dest="project_root",
        help="Explicit project root directory (overrides auto-detection).",
    )
    pre_args, _ = pre_parser.parse_known_args()

    if pre_args.project_root:
        resolved_root = pathlib.Path(pre_args.project_root).expanduser().resolve()
        if not resolved_root.exists() or not resolved_root.is_dir():
            print(f"Error: --project-root does not exist or is not a directory: {resolved_root}")
            sys.exit(2)
    else:
        resolved_root = detect_project_root(
            extra_markers={"bin/rclone_remote.json", "bin/rclone.conf"}
        )

    os.chdir(resolved_root)
    repokit_common.PROJECT_ROOT = resolved_root

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
        set_host_port,
        setup_rclone,
    )
    from .registry import load_all_registry, set_push_policy

    _ensure_rcloneignore_pyproject_config()

    if not install_rclone("./bin"):
        print("Error: rclone installation/verification failed.")
        sys.exit(1)

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

    args = parser.parse_args()

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
        registry = load_all_registry()

        add_backend = None
        if args.command == "add":
            try:
                add_backend = _resolved_add_backend(getattr(args, "backend", None), remote)
            except ValueError as exc:
                print(f"Error: {exc}")
                sys.exit(2)

        runtime_backend = None
        if args.command in {"push", "pull"} and remote != "all":
            meta = registry.get(remote, {})
            if isinstance(meta, dict):
                runtime_backend = normalize_backend(meta.get("remote_type"))
            runtime_backend = runtime_backend or resolve_backend(None, remote)

        # Set host/port for applicable SFTP remotes.
        if args.command == "add" and add_backend in {"erda", "ucloud"}:
            set_host_port(remote)
        if args.command in {"push", "pull"} and runtime_backend in {"erda", "ucloud"}:
            set_host_port(remote)

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

            setup_rclone(
                remote,
                backend=add_backend,
                local_backup_path=add_local_path,
                oauth_token=oauth_token,
                ssh_mode=getattr(args, "ssh_mode", False),
            )

        elif args.command == "push":
            if getattr(args, "search_pattern", None) and getattr(args, "select", None) is not None:
                print("Error: use either --search or --select for push, not both.")
                sys.exit(2)
            mode = getattr(args, "mode", "sync")
            push_rclone(
                remote_name=remote,
                new_path=args.remote_path,
                operation=mode,
                dry_run=args.dry_run,
                verbose=args.verbose,
                select_path=getattr(args, "select", None),
                search_pattern=getattr(args, "search_pattern", None),
            )

        elif args.command == "pull":
            if getattr(args, "search_pattern", None) and getattr(args, "select", None) is not None:
                print("Error: use either --search or --select for pull, not both.")
                sys.exit(2)
            mode = getattr(args, "mode", "sync")
            pull_rclone(
                remote_name=remote,
                remote_path=args.remote_path,
                new_path=args.local_path,
                operation=mode,
                dry_run=args.dry_run,
                verbose=args.verbose,
                select_path=getattr(args, "select", None),
                search_pattern=getattr(args, "search_pattern", None),
            )

        elif args.command == "delete":
            delete_remote(remote_name=remote, verbose=args.verbose)

        elif args.command == "diff":
            generate_diff_report(remote_name=remote)
        elif args.command == "ls":
            list_remote_entries(
                remote_name=remote,
                sub_path=getattr(args, "list_path", ""),
                search_pattern=getattr(args, "search_pattern", None),
            )
        elif args.command == "policy":
            ok = set_push_policy(remote_name=remote, push_policy=getattr(args, "policy_value", ""))
            if not ok:
                sys.exit(2)

    elif args.command == "transfer":
        # Remote-to-remote transfer
        operation = getattr(args, "mode", "copy")
        dry_run = not args.confirm  # If not confirmed, run in dry-run
        transfer_between_remotes(
            source_remote=args.source.strip().lower(),
            dest_remote=args.destination.strip().lower(),
            operation=operation,
            dry_run=dry_run,
            verbose=args.verbose,
        )

    else:
        # Commands without a remote
        if args.command == "list":
            list_remotes()
        elif args.command == "types":
            list_supported_remote_types()
        else:
            parser.print_help()
            sys.exit(2)


if __name__ == "__main__":
    main()
