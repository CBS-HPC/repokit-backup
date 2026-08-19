# repokit-backup API Reference

This document is the full command and behavior reference for `repokit-backup`.
Use [`README.md`](../README.md) for quick-start workflows and this document for exact flag, mapping, backend, and transfer semantics.

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
- ensures `.gitignore` excludes the local `.env` file and `bin/` runtime state

The automatic installer uses the pinned, SHA-256-verified rclone 1.73.2
release archive for the detected Windows, Linux, or macOS architecture. If a
working `rclone` is already available, repokit-backup uses it instead.

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
| `init` | Initialize local `repokit-backup` runtime state in the current project root |
| `add` | Configure a remote and optionally create a mapping entry |
| `push` | Transfer local files to a remote |
| `pull` | Transfer remote files to local storage |
| `ls` | List or search files on a remote |
| `list` | Show configured remotes and registry entries |
| `policy` | Change saved transfer policy for a configured remote |
| `pin` | Save or clear a remote-only default base path |
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
- `LUMIP_SSH_KEY_PATH`
- `LUMIP_HOST`
- `LUMIP_PORT`

`erda`:

- `ERDA_HOST`
- `ERDA_PORT`
- `ERDA_USERNAME`
- `ERDA_PASSWORD`

`ucloud`:

- `UCLOUD_HOST`
- `UCLOUD_PORT`
- `UCLOUD_SSH_KEY_PATH`

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
- `mapping_mode`: `full`, `remote-only`, or `none`
- `remote_path_ownership`: `managed`, `external`, or `none`
- `last_action`
- `last_operation`
- `timestamp`
- `status`

The three mapping modes are:

| Mode | Saved state | Default behavior |
|---|---|---|
| `full` | remote path and local path | `push`, `pull`, `ls`, and `diff` can use the saved paths |
| `remote-only` | remote path only | `ls` and `pull` use the saved remote base; `push`/`pull` still need `--path` |
| `none` | no paths | `ls` and `pull` fall back to remote root; `push`/`pull` need explicit paths |

Remote paths selected with `use`, `merge`, or a remote-only pin are marked `external`. They are never purged by `repokit-backup delete`.

`add` can also configure a remote without creating a mapping if you answer `n` to:

```text
Create a local/remote path mapping now? [Y/n]:
```

If you answer `n`, the remote is still written to `./bin/rclone_remote.json` with:

- `remote_path: null`
- `local_path: null`
- `status: "configured"`

Unmapped remotes are supported only in limited cases:

- `ls` falls back to remote root
- `pull` requires `--path`; if `--remote-path` is omitted it falls back to remote root
- `push` requires both `--path` and `--remote-path`

## Command Reference

### `init`

Initializes `repokit-backup` state in the current working directory, or under `--project-root` if provided.

Behavior:

- ensures `./bin/` exists under the resolved project root
- installs or wires `rclone` for that local `./bin/`
- ensures `pyproject.toml` exists and contains `[tool.rcloneignore]` defaults
- prints the resolved project root, `bin` path, and `pyproject.toml` path

Notes:

- `init` is intended to be run from the project root
- unlike other commands, root resolution for `init` uses the current working directory by default instead of walking upward to older backup markers
- adds `.env` and `bin/` to `.gitignore` without removing existing entries

### `add`

Configures the rclone remote and optionally creates a registry mapping.

Arguments:

- `--remote`: required alias/name
- `--backend`: required backend type for the remote being created
- `--subdir`: project-relative local source path to use or create
- `--path`: filesystem path for local source
- `--local-path`, `--local_path`: deprecated alias for `--path`
- `--remote-path`: persistent remote base path
- `--mapping`: `full`, `remote-only`, or `none`
- `--policy`: `full`, `append-only`, or `pull-only`
- `--on-existing`: `error`, `use`, `merge`, or `overwrite`
- `--non-interactive`: prohibit prompts and require a complete explicit specification
- `--token`: OAuth token JSON
- `--token-file`: file containing OAuth token JSON
- `--ssh`, `--ssh-mode`, `--shh-mode`: show SSH tunnel instructions for OAuth callback flow
- `--lumio-project-id`, `--lumio-access-key`, `--lumio-secret-file`: LUMI-O automation values
- `--lumip-project-id`, `--lumip-username`, `--ssh-key-path`, `--use-ssh-agent`: LUMI-P automation values
- `--erda-username`, `--erda-password-file`: ERDA automation values
- `--ucloud-port`: UCloud SSH port for automation
- `--rclone-options-file`: JSON file containing flat rclone options for generic `sftp` or `s3`

Behavior:

- creates local `bin/` state if missing
- requires `--backend`; alias prefix alone is not enough
- first asks whether to create a local/remote path mapping
- if mapping is enabled, prompts for remote base folder
- if mapping is enabled, prompts for policy
- if mapping is enabled, stores mapping in `./bin/rclone_remote.json`
- if mapping is skipped, the remote is still registered in `./bin/rclone_remote.json` with null paths
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
- `lumip`: prompts for project id, username, SSH private key path (preferred over ssh-agent), and storage class/root
- `local`: prompts for a local target path
- `sftp`, `s3`: falls back to interactive `rclone config create`

#### Dropbox Business paths

For Dropbox, a leading slash is significant to rclone and selects the
Dropbox team root rather than the personal/member namespace:

```text
moody-dropbox:folder     # personal/member namespace
moody-dropbox:/folder    # Dropbox team root
```

Use paths such as `/Team Folder - (LIB)/myproject` for team-folder mappings.
Verify the configured alias can see the team root before saving a mapping:

```bash
rclone lsd "moody-dropbox:/"
```

This is Dropbox-specific behavior. It does not imply that leading slashes
have the same provider semantics for other rclone backends.

Notes:

- `--subdir` is relative to the detected project root
- `/data` is accepted and normalized as project-relative `data`
- `--subdir` creates the folder if missing
- `--path` accepts an absolute path or a path relative to the current shell directory

#### Non-interactive `add`

`--non-interactive` does not call `input()` or run interactive `rclone config` setup. Values resolve in this order:

1. Explicit command-line value
2. Saved value through `load_from_env(...)`
3. A documented safe default where one exists

Explicit LUMI, ERDA, and UCloud values are persisted with `save_to_env(...)` for later runs. Secret values should be supplied through the corresponding `*-file` flag rather than shell history.

`--mapping` is mandatory with `--non-interactive`:

- `full` requires `--path` (or `--subdir`), `--remote-path`, and `--policy`
- `remote-only` requires `--remote-path` and `--policy`, and rejects a local source path
- `none` rejects all path flags and creates only the rclone/registry remote entry
- `--on-existing error` is the default and fails safely if the remote folder already exists
- `--on-existing use` retains existing data and marks the remote path external
- `--on-existing merge` is allowed only for `full` mappings
- `--on-existing overwrite` purges the specified remote folder before saving a managed mapping

OAuth backends require `--token` or `--token-file` in this mode. Generic `sftp` and `s3` require `--rclone-options-file`, for example:

```json
{
  "host": "storage.example.org",
  "user": "researcher",
  "key_file": "/home/researcher/.ssh/id_ed25519"
}
```

### `push`

Transfers local files to the remote destination.

Arguments:

- `--remote`: required
- `--mode`: `sync`, `copy`, `move`
- `--remote-path`: override mapped remote destination
- `--path`: override mapped local source
- `--search`: non-interactive recursive source filter
- `--select`: interactive source selection
- `--transfer-timeout SECONDS`: optional total limit per rclone invocation; `0` is unlimited

Behavior:

- default mode is `sync` unless `--mode` is provided
- uses the mapped local source path unless `--path` is given
- uses the mapped remote path unless `--remote-path` is given
- a remote-only pin supplies the destination, but `--path` is still required
- an unmapped remote requires both `--path` and `--remote-path`
- reads ignore patterns from `[tool.rcloneignore]` if the local source is the project root
- excludes nested child mappings automatically
- commits through `repokit.vcs.rclone_commit` when that integration is available
- has no total wall-clock deadline by default; set `--transfer-timeout` to enforce one

Search/filter rules:

- `--remote-path` accepts either a full rclone URI (`myproject:/archive`) or a remote-scoped path (`/archive`) when `--remote myproject` is already supplied
- `--search` is evaluated on the local source side
- relative patterns search under the current local source base
- patterns starting with `/` are anchored to the local source root
- when a search contains a deterministic path prefix, the local source is narrowed to that prefix and the remote destination is augmented with the same prefix so folder structure is preserved
- example: `--search "/data/**/*.parquet"` narrows the local source to `data/`, augments the remote destination with `data/`, and uses include pattern `**/*.parquet`
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
- `--transfer-timeout SECONDS`: optional total limit per rclone invocation; `0` is unlimited

Mapped remote behavior:

- default mode is `sync` unless `--mode` is provided
- source defaults to mapped `remote_path`
- destination defaults to mapped `local_path`

Unmapped remote behavior:

- `--path` is required
- if `--remote-path` is omitted, source defaults to remote root `<remote>:`

This makes ad hoc restore possible even before a persistent mapping has been created.

For remote-only pins, source defaults to the pinned remote path and `--path` is required.

Pull has no total wall-clock deadline by default; set `--transfer-timeout` to enforce one.

Search/filter rules:

- `--remote-path` accepts either a full rclone URI (`myproject:/archive`) or a remote-scoped path (`/archive`) when `--remote myproject` is already supplied
- `--search` is evaluated on the remote source side
- relative patterns search under the current remote source base
- patterns starting with `/` are anchored to the remote root
- when a search contains a deterministic path prefix, the remote source is narrowed to that prefix and the local destination is augmented with the same prefix so folder structure is preserved
- example: `--remote-path "/archive/project-data" --search "datasets/file_202001*"` narrows the source to `.../datasets`, augments the local destination with `datasets/`, and uses include pattern `file_202001*`
- for direct file pulls with `--select`, local parent directories are created automatically
- `--search` and `--select` are mutually exclusive

Policy rules:

- default `sync`/`move` requests are auto-switched to `copy` when policy is `append-only` or `pull-only`
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
repokit-backup ls --remote myproject
repokit-backup ls --remote myproject --path /data
repokit-backup ls --remote myproject --search "/backup_*"
repokit-backup ls --remote myproject --path /data --search "file_*.txt"
repokit-backup ls --remote myproject --search "/*/file_*.txt"
```

### `list`

Prints configured remotes, saved mappings, last action, last operation, timestamp, status, and policy.

Labels distinguish full mappings (`[mapped]`), remote-only pins (`[remote-pinned]`), registered unmapped remotes (`[registered]`), and rclone-only remotes (`[unmapped]`).

### `pin`

Adds or clears a remote-only default base path for a registered remote.

Arguments:

- `--remote`: registered remote name
- `--remote-path`: base path to persist
- `--clear`: remove an existing remote-only pin

Examples:

```bash
repokit-backup pin --remote myproject --remote-path "/shared/team-research/myproject"
repokit-backup pin --remote myproject --clear
```

`pin` is intentionally limited to registered unmapped or remote-only entries. It refuses to overwrite a full mapping, so a local source path cannot be discarded accidentally.

It combines:

- remotes known by rclone
- remotes known in `./bin/rclone_remote.json`
- warning markers when a registry entry no longer exists in the active rclone config

State labels:

- `[mapped]`: registry entry has both `remote_path` and `local_path`
- `[registered]`: registry entry exists but paths are null
- `[unmapped]`: rclone config entry exists without a registry record

### `policy`

Updates the saved policy for an existing configured remote.

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

- purges a remote folder only when its mapping marks it as `managed`
- never purges an externally owned pinned path
- removes rclone config entry
- removes registry entry
- deletes empty config file when applicable

If rclone cannot purge a managed folder or remove its config entry, deletion
stops and the command exits nonzero. This avoids claiming that a remote was
deleted when its configuration still exists.

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
- `--transfer-timeout SECONDS`: optional total limit per rclone invocation; `0` is unlimited

Restrictions:

- both remotes must exist in the registry
- both remotes must share the same `local_path`
- only `copy` and `sync` are allowed
- transfers have no total wall-clock deadline by default

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
- `push`: local source path override
- `pull`: local destination path
- `ls`: remote subpath under the current listing base

### `--remote-path`

Meaning depends on command:

- `push`: override remote destination
- `pull`: override remote source
- `add`: persistent remote path for `--mapping full` or `--mapping remote-only`
- `pin`: persistent remote-only base path

Accepted forms:

- full rclone URI: `myproject:/archive`
- remote-scoped path when `--remote` is already given: `/archive`

`remote_path` values are opaque rclone paths. Consumers must preserve their
exact form, including a leading slash, rather than stripping or normalizing
them. This is required for Dropbox Business mappings, where
`moody-dropbox:folder` and `moody-dropbox:/folder` address different
namespaces. Use `/Team Folder - (LIB)/...` for Dropbox team-folder mappings.

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
  "myproject": {
    "remote_path": "myproject:rclone-backup/project-name",
    "local_path": "/path/to/project",
    "remote_type": "dropbox",
    "push_policy": "full",
    "mapping_mode": "full",
    "remote_path_ownership": "managed",
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
- remote-only pins require `--path` for `push` and `pull`
- `pin` cannot replace a full mapping
- externally owned remote paths are never purged by `delete`
- nested child mappings are excluded from parent pushes/pulls
- root-level ignore patterns come from `[tool.rcloneignore]`
- LUMI-P custom paths must be absolute and must not contain `..`
- `append-only` blocks destructive push modes
- `pull-only` blocks push entirely
- `--search` and `--select` are currently mutually exclusive for `push` and `pull`

## Exit Status

`repokit-backup` exits with status `0` after a completed operation, including a
cancelled destructive-delete confirmation. It exits nonzero when rclone or a
required local operation fails. Invalid command-line combinations exit with
status `2`. Automation should check the process exit status rather than parse
printed output.

## Credential Storage

Repokit-common persists environment-backed configuration such as OAuth tokens,
LUMI credentials, and `RCLONE_CONFIG` in the project-local runtime state. The
CLI adds `.env` and `bin/` to `.gitignore` during initialization because these
locations can hold sensitive data. Keep them out of Git, logs, and shared
archives. Use the `*-file` options for non-interactive secrets instead of
putting credentials in shell history.

## Examples

### Add and map a Dropbox remote

```bash
repokit-backup add --remote myproject --backend dropbox --subdir /data
```

### Add a remote-only pin without prompts

```bash
repokit-backup add --remote myproject --backend dropbox \
  --token-file ./dropbox-token.json \
  --mapping remote-only --remote-path "/shared/team-research/myproject" \
  --policy full --on-existing use --non-interactive
```

### Push only parquet files under `data/`

```bash
repokit-backup push --remote myproject --search "/data/**/*.parquet"
```

### Pull from an unmapped remote root

```bash
repokit-backup pull --remote myproject --path ./restore
```

### Pull from an explicit remote archive path

```bash
repokit-backup pull --remote myproject --remote-path "/archive" --path ./restore
```

### Pull from an explicit base plus relative search

```bash
repokit-backup pull --remote archive --remote-path "/archive/project-data" --search "datasets/file_202001*" --path .
```

### Pull with a root-anchored search only

```bash
repokit-backup pull --remote archive --search "/archive/project-data/datasets/file_202001*" --path .
```

### Search the remote for dated files

```bash
repokit-backup ls --remote myproject --search "/backup_*"
```
