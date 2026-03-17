# repokit-backup API Reference

This document is the full command and behavior reference for `repokit-backup`.
Use [README.md](C:/work/repokit-packages/repokit-backup/README.md) for quick-start workflows and this document for exact flag, mapping, backend, and transfer semantics.

## Overview

`repokit-backup` is a CLI wrapper around `rclone` with four main layers:

- remote configuration
- local/remote path mapping
- policy-aware push/pull operations
- registry tracking in `./bin/rclone_remote.json`

At startup, the CLI:

- resolves the project root from `--project-root` or project markers
- changes working directory to that root
- ensures `rclone` is installed and configured locally
- ensures `pyproject.toml` contains `[tool.rcloneignore]` defaults

Implemented backend families in the current codebase:

- ERDA
- UCloud
- Dropbox
- OneDrive
- Google Drive
- LUMI-O
- LUMI-P / LUMI-F
- Local filesystem
- generic SFTP
- generic S3

## Command Summary

| Command | Purpose |
|---|---|
| `add` | Configure a remote and create a mapping entry |
| `push` | Transfer local files to a remote |
| `pull` | Transfer remote files to local storage |
| `ls` | List or search files on a remote |
| `list` | Show configured remotes and registry entries |
| `policy` | Change saved transfer policy for a mapped remote |
| `diff` | Compare mapped local and remote content |
| `delete` | Delete remote config and registry mapping |
| `transfer` | Copy or sync between two remotes |
| `types` | Show rclone-supported backend types |

## Global Options

### `--project-root`

Overrides project-root detection.

- expected value: existing directory
- effect: all relative paths, registry files, and local `bin/` state resolve under that root

### `--dry-run`

Available as a global CLI flag.

- for transfer commands, passes dry-run behavior through to `rclone`

### `-v`, `-vv`, `-vvv`

Controls rclone verbosity.

## Backend Model

### Alias vs backend

`--remote` is the remote alias or name.
For `add`, it is not the source of truth for backend type.

Backend resolution for `add`:

1. `--backend`

For non-`add` commands, runtime backend resolution still uses:

1. stored registry metadata
2. infer from alias prefix for legacy compatibility
3. fallback to `sftp`

### Canonical backends

| Canonical backend | Accepted names |
|---|---|
| `dropbox` | `dropbox` |
| `onedrive` | `onedrive` |
| `drive` | `drive`, `googledrive`, `gdrive` |
| `erda` | `erda` |
| `ucloud` | `ucloud` |
| `lumio` | `lumio`, `lumi-o` |
| `lumip` | `lumip`, `lumi-p`, `lumi-f` |
| `local` | `local` |
| `s3` | `s3` |
| `sftp` | `sftp` |

### Backend categories

OAuth-backed:

- `dropbox`
- `onedrive`
- `drive`

SFTP-backed:

- `erda`
- `ucloud`
- `lumip`
- `sftp`

Object-storage-backed:

- `lumio`
- `s3`

Filesystem-backed:

- `local`

### Backend-specific environment keys

Stored through `load_from_env(...)` and `save_to_env(...)`.

`lumio`:

- `LUMIO_PROJECT_ID`
- `LUMIO_ACCESS_KEY`
- `LUMIO_SECRET_KEY`
- `LUMIO_DEFAULT_BASE`

`lumip`:

- `LUMIP_PROJECT_ID`
- `LUMIP_USERNAME`
- `LUMIP_BASE_PATH`
- `LUMIP_HOST`
- `LUMIP_PORT`

OAuth tunnel support:

- `APP_PORT`
- `SSH_HOST`
- `SSH_PORT`

Local rclone setup:

- `RCLONE_CONFIG`

### LUMI semantics

`lumio` is configured as an S3-compatible remote against `https://lumidata.eu`.

`lumip` is configured as an SFTP remote.
The `lumi-f` alias resolves to `lumip`; the difference is only the chosen default storage root.

LUMI-P/LUMI-F storage choices:

- `/users/<username>`
- `/project/<project_id>`
- `/scratch/<project_id>`
- `/flash/<project_id>`
- custom absolute path

Validation rules for LUMI-P base paths:

- must be absolute
- must not contain `..`
- preset choices enforce the expected prefix

## Mapping Model

Mappings are stored in `./bin/rclone_remote.json`.

Each registry entry contains:

- `remote_path`
- `local_path`
- `remote_type`
- `push_policy`
- `last_action`
- `last_operation`
- `timestamp`
- `status`

Mapped remotes allow `push`, `pull`, `ls`, and `diff` to run without explicit source/destination paths.

Unmapped remotes are supported only in limited cases:

- `ls` falls back to remote root
- `pull` requires `--path`; if `--remote-path` is omitted it falls back to remote root
- `push` still expects a saved mapping

## Command Reference

### `add`

Configures the rclone remote and creates a registry mapping.

Arguments:

- `--remote`: required alias/name
- `--backend`: required backend type for the remote being created
- `--subdir`: project-relative local source path to use or create
- `--path`: filesystem path for local source
- `--local-path`, `--local_path`: deprecated alias for `--path`
- `--token`: OAuth token JSON
- `--token-file`: file containing OAuth token JSON
- `--ssh`, `--ssh-mode`, `--shh-mode`: show SSH tunnel instructions for OAuth callback flow

Behavior:

- creates local `bin/` state if missing
- requires `--backend`; alias prefix alone is not enough
- prompts for remote base folder
- prompts for policy
- stores mapping in `./bin/rclone_remote.json`
- if remote folder already exists, prompts:
  - overwrite
  - merge/sync
  - use existing
  - change folder
  - cancel

Backend-specific setup behavior:

- `dropbox`, `onedrive`, `drive`: OAuth flow, token flow, or SSH-tunneled OAuth
- `erda`: SFTP configuration with prompted credentials or agent use
- `ucloud`: SFTP-like mapping plus separate local `rclone_ucloud.conf`
- `lumio`: prompts for project id, access key, secret key, and default base folder
- `lumip`: prompts for project id, username, and storage class/root
- `local`: prompts for a local target path
- `sftp`, `s3`: falls back to interactive `rclone config create`

Notes:

- `--subdir` is relative to the detected project root
- `/data` is accepted and normalized as project-relative `data`
- `--subdir` creates the folder if missing
- `--path` accepts an absolute path or a path relative to the current shell directory

### `push`

Transfers local files to the remote destination.

Arguments:

- `--remote`: required
- `--mode`: `sync`, `copy`, `move`
- `--remote-path`: override mapped remote destination
- `--search`: non-interactive recursive source filter
- `--select`: interactive source selection

Behavior:

- uses the mapped local source path
- uses the mapped remote path unless `--remote-path` is given
- reads ignore patterns from `[tool.rcloneignore]` if the local source is the project root
- excludes nested child mappings automatically
- commits through `repokit.vcs.rclone_commit` when that integration is available

Search/filter rules:

- `--search` is a source-side include filter
- `--search "/data/**/*.parquet"` becomes include pattern `data/**/*.parquet`
- transfer root is unchanged, so relative folder structure is preserved
- `--search` and `--select` are mutually exclusive

Policy rules:

- `full`: `sync`, `copy`, `move` allowed
- `append-only`: `copy` only
- `pull-only`: push blocked

### `pull`

Transfers remote files to local storage.

Arguments:

- `--remote`: required
- `--mode`: `sync`, `copy`, `move`
- `--remote-path`: override remote source
- `--path`, `--local-path`, `--local_path`: override local destination
- `--search`: non-interactive recursive source filter
- `--select`: interactive source selection

Mapped remote behavior:

- source defaults to mapped `remote_path`
- destination defaults to mapped `local_path`

Unmapped remote behavior:

- `--path` is required
- if `--remote-path` is omitted, source defaults to remote root `<remote>:`

This makes ad hoc restore possible even before a persistent mapping has been created.

Search/filter rules:

- `--search` filters the remote source side
- folder structure is preserved under the local destination
- for direct file pulls with `--select`, local parent directories are created automatically
- `--search` and `--select` are mutually exclusive

Policy rules:

- `append-only` and `pull-only` force pull mode to `copy`

### `ls`

Lists remote files or searches for remote paths.

Arguments:

- `--remote`: required
- `--path`: optional subpath under current base
- `--search`: optional recursive glob search

Base resolution:

- if mapping exists: use mapped remote path
- if mapping does not exist: use remote root `<remote>:`

Search rules:

- without `--search`: non-recursive `lsf --max-depth 1`
- with `--search`: recursive `lsf --recursive --include <pattern>`
- if `--search` starts with `/`, pattern is anchored to remote root
- otherwise, pattern is scoped under current base

Examples:

```bash
repokit-backup ls --remote dropbox-main
repokit-backup ls --remote dropbox-main --path /data
repokit-backup ls --remote dropbox-main --search "/20250313_*"
repokit-backup ls --remote dropbox-main --path /data --search "file_*.txt"
repokit-backup ls --remote dropbox-main --search "/*/file_*.txt"
```

### `list`

Prints configured remotes, saved mappings, last action, last operation, timestamp, status, and policy.

It combines:

- remotes known by rclone
- remotes known in `./bin/rclone_remote.json`
- warning markers when a registry entry no longer exists in the active rclone config

### `policy`

Updates the saved policy for an existing mapped remote.

Arguments:

- `--remote`
- `--set full|append-only|pull-only`

### `diff`

Generates a diff report between the mapped local path and mapped remote path.

Restriction:

- requires a saved mapping

### `delete`

Deletes one remote or all remotes.

Arguments:

- `--remote <name>`
- `--remote all`

Behavior:

- attempts remote purge
- removes rclone config entry
- removes registry entry
- deletes empty config file when applicable

Special handling:

- supports `--remote all`
- also checks the dedicated UCloud config file when cleaning up

### `transfer`

Transfers directly between two remotes.

Arguments:

- `--source`
- `--destination`
- `--mode copy|sync`
- `--confirm`

Restrictions:

- both remotes must exist in the registry
- both remotes must share the same `local_path`
- only `copy` and `sync` are allowed

### `types`

Prints the backend types reported by `rclone help backends`.

## Search vs Select

Use `--search` when:

- you want a scripted, repeatable filter
- you know the file pattern already

Use `--select` when:

- you want an interactive picker
- you want to inspect top-level entries before choosing

Current rule:

- `--search` and `--select` cannot be combined in `push` or `pull`

## Path Semantics

### `--subdir`

- only for `add`
- project-relative
- creates the directory if missing
- `/data` is normalized to `data`

### `--path`

Meaning depends on command:

- `add`: local source path
- `pull`: local destination path
- `ls`: remote subpath under the current listing base

### `--remote-path`

Meaning depends on command:

- `push`: override remote destination
- `pull`: override remote source

## OAuth and SSH Mode

OAuth backends:

- `dropbox`
- `onedrive`
- `drive`

Two supported flows:

- browser-based OAuth through `--ssh`
- token-based headless setup with `--token` or `--token-file`

In `--ssh` mode, the CLI prompts for:

- callback `APP_PORT`
- `SSH_HOST`
- `SSH_PORT`

Then it prints a local SSH tunnel command and expects the exact `/auth?state=...` callback URL to be opened in a local browser.

This applies to:

- Dropbox
- OneDrive
- Google Drive

## Registry File

Path:

```text
./bin/rclone_remote.json
```

Schema example:

```json
{
  "dropbox-main": {
    "remote_path": "dropbox-main:rclone-backup/myproject",
    "local_path": "/work/myproject",
    "remote_type": "dropbox",
    "push_policy": "full",
    "last_action": "push",
    "last_operation": "copy",
    "timestamp": "2026-03-13T12:00:00",
    "status": "ok"
  }
}
```

## Safeguards and Defaults

- `pull all` is not supported
- unmapped `pull` requires `--path`
- unmapped `ls` falls back to remote root
- nested child mappings are excluded from parent pushes/pulls
- root-level ignore patterns come from `[tool.rcloneignore]`
- LUMI-P custom paths must be absolute and must not contain `..`
- `append-only` blocks destructive push modes
- `pull-only` blocks push entirely
- `--search` and `--select` are currently mutually exclusive for `push` and `pull`

## Examples

### Add and map a Dropbox remote

```bash
repokit-backup add --remote dropbox-main --backend dropbox --subdir /data
```

### Push only parquet files under `data/`

```bash
repokit-backup push --remote dropbox-main --search "/data/**/*.parquet"
```

### Pull from an unmapped remote root

```bash
repokit-backup pull --remote dropbox-main --path ./restore
```

### Pull from an explicit remote archive path

```bash
repokit-backup pull --remote dropbox-main --remote-path dropbox-main:/archive --path ./restore
```

### Search the remote for dated files

```bash
repokit-backup ls --remote dropbox-main --search "/20250313_*"
```
