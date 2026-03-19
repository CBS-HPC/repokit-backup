# repokit-backup

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/CBS-HPC/repokit-backup/actions/workflows/ci.yml/badge.svg)](https://github.com/CBS-HPC/repokit-backup/actions/workflows/ci.yml)

Backup and synchronization utilities built on rclone. Works with the Research Template and can be used standalone.

Data loss can compromise months or years of research. To support **reproducible**, **secure**, and **policy-compliant** workflows, this template offers automated backup to storage providers using [`rclone`](https://rclone.org).

Implemented and supported remote families:

- [**ERDA**](https://erda.dk/) via SFTP
- [**UCloud**](https://www.cloud.sdu.dk/) via SFTP and local `rclone_ucloud.conf`
- [**Dropbox**](https://www.dropbox.com/) via OAuth
- [**OneDrive**](https://onedrive.live.com/) via OAuth
- **Google Drive** via OAuth (`drive`, `googledrive`, `gdrive`)
- **LUMI-O** object storage via S3-compatible configuration
- **LUMI-P / LUMI-F** via SFTP-backed storage roots
- **Local** filesystem targets
- **Generic SFTP** targets
- **Generic S3** targets
- **Multiple remotes** for the same project

Notes:

- `rclone`is automatically downloaded and installed if not already available
- Other [Rclone-supported remotes](https://rclone.org/overview/#supported-storage-systems) **should work**, but have not yet been tested with this template's workflow.
- All configured remotes and folder mappings are logged in `./bin/rclone_remote.json`.

## Documentation

- `README.md`: installation, quick start, and common workflows
- [`docs/api-reference.md`](docs/api-reference.md): full CLI, backend, mapping, policy, and transfer behavior reference

## Installation

`repokit-backup` is not published on PyPI yet. Use local wheel/source installation.

Install from local wheel files (`/dist`):

```bash
# 1) Install dependency wheel first
pip install https://github.com/CBS-HPC/repokit-common/raw/main/dist/repokit_common-0.1-py3-none-any.whl

# 2) Install repokit-backup wheel
pip install https://github.com/CBS-HPC/repokit-backup/raw/main/dist/repokit_backup-0.1-py3-none-any.whl
```

If you are installing into a fresh virtual environment, install in this order so `repokit-common` is available before `repokit-backup`.
Wheel filenames include version tags and may change over time.

## Requirements

- `rclone` on `PATH` (auto-installed if missing)

## CLI

| Command | Description |
|---------|-------------|
| `repokit-backup init` | Initialize local `repokit-backup` state in the current project root. |
| `repokit-backup add` | Configure a backup remote and optional mapping. |
| `repokit-backup push` | Push/sync project data to remote storage. |
| `repokit-backup pull` | Restore/sync from remote to local project. |
| `repokit-backup diff` | Show remote/local diff report. |
| `repokit-backup list` | List configured remotes/mappings. |
| `repokit-backup ls` | List files/folders at a configured remote path. |
| `repokit-backup policy` | Update policy (`full`, `append-only`, `pull-only`) for a configured remote. |
| `repokit-backup delete` | Remove a configured remote mapping. |
| `repokit-backup transfer` | Transfer data between two remotes. |
| `repokit-backup types` | List supported remote types. |

Full flag-by-flag behavior is documented in [`docs/api-reference.md`](docs/api-reference.md).

## Quick Start

Initialize the current project root first:

```bash
repokit-backup init
```

This ensures:

- `./bin/` exists under the current project root
- `rclone` is installed or made available from that `./bin/`
- `pyproject.toml` exists with `[tool.rcloneignore]` defaults

Common setup examples:

```bash
repokit-backup add --remote myproject --backend dropbox
repokit-backup add --remote shared-data --backend onedrive
repokit-backup add --remote research-drive --backend drive
repokit-backup add --remote archive --backend erda
repokit-backup add --remote project-copy --backend ucloud
repokit-backup add --remote object-store --backend lumi-o
repokit-backup add --remote project-space --backend lumi-p
repokit-backup add --remote local-copy --backend local
repokit-backup add --remote lab-server --backend sftp
repokit-backup add --remote cold-storage --backend s3
```

Set source scope during add:

```bash
# Project-relative source (created if missing)
repokit-backup add --remote myproject --backend dropbox --subdir /data

# Filesystem source path
repokit-backup add --remote myproject --backend dropbox --path /work/shared/data
```

`--local-path` is still accepted for backward compatibility (alias of `--path` for `add`).

`--remote` is an alias/name only. For `add`, `--backend` is required and is the source of truth for the backend being created.

For non-`add` commands, stored registry metadata is used first, with alias inference still available as a compatibility fallback for older mappings.

During `add`, `repokit-backup` now first asks:

```text
Create a local/remote path mapping now? [Y/n]:
```

If you answer `n`, the remote is configured and registered, but `remote_path` and `local_path` are left unmapped until you add them later.

If you answer `y`, `repokit-backup` then prompts for the remote base folder and saves a persistent push policy per remote:

- `full`: push/pull `sync`, `copy`, and `move` are allowed
- `append-only`: push `copy` only; pull `copy` only
- `pull-only`: push is blocked; pull `copy` only

If the remote folder already exists, the conflict prompt includes:

- overwrite
- merge/sync
- use existing
- change folder
- cancel

LUMI environment keys, backend aliases, and storage selector details are documented in [`docs/api-reference.md`](docs/api-reference.md).

## Common Workflows

Push to remote:

```bash
repokit-backup push --remote myproject
```

This command performs the following:

- Commits and pushes the root Git project (if version control is enabled)
- Commits and pushes the data/ Git repository
- Syncs the project, excluding any ignored files (e.g., `.rcloneignore` or `pyproject.toml` patterns)

Pull backup from remote:

```bash
repokit-backup pull --remote myproject
```

Note: if remote policy is `append-only` or `pull-only`, `pull` auto-switches `sync`/`move` to `copy`.
For unmapped remotes, `pull` requires `--path`; if `--remote-path` is omitted it defaults to the remote root.

Interactive file/folder selection for transfer:

```bash
repokit-backup push --remote myproject --select
repokit-backup pull --remote myproject --select
```

`--select` opens an interactive picker (number/range syntax like `1,3,5-7`) and transfers only selected entries.

Scope selection to a subpath:

```bash
repokit-backup push --remote myproject --select /data
repokit-backup pull --remote myproject --select /data
```

Direct path selection also works (non-interactive include fallback):

```bash
repokit-backup pull --remote myproject --select /data/dataset1/file1.txt
repokit-backup push --remote myproject --select /data/dataset1/file1.txt
```

Non-interactive recursive filtering for transfer:

```bash
repokit-backup push --remote myproject --search "/data/**/*.parquet"
repokit-backup pull --remote myproject --path ./restore --search "/data/**/*.parquet"
repokit-backup pull --remote myproject --remote-path "/archive" --path ./restore --search "backup_*"
repokit-backup pull --remote archive --remote-path "/archive/project-data" --search "datasets/file_202001*" --path .
```

`--search` is evaluated relative to the current source base:

- `push`: relative to the mapped local source path
- `pull`: relative to the mapped remote path or explicit `--remote-path`
- patterns starting with `/` are anchored to the source root

When a search pattern contains a deterministic path prefix, `repokit-backup` narrows the transfer source to that prefix and augments the destination with the same prefix so folder structure is preserved.
For example, `/data/**/*.parquet` keeps the `data/...` tree on the destination.
`--search` and `--select` are mutually exclusive for `push` and `pull`.

Transfer between two configured remotes:

```bash
repokit-backup transfer --source myproject --destination archive --mode copy --confirm
```

List remote entries at mapped root or a subpath:

```bash
repokit-backup ls --remote myproject
repokit-backup ls --remote myproject --path /data
```

If a remote has no saved mapping, `ls` falls back to the remote root:

```bash
repokit-backup ls --remote myproject
repokit-backup ls --remote myproject --path /data
```

Recursive search for remote files/folders:

```bash
repokit-backup ls --remote myproject --search "/data/file_*.txt"
repokit-backup ls --remote myproject --search "/backup_*"
repokit-backup ls --remote myproject --path /data --search "file_*.txt"
repokit-backup ls --remote myproject --search "/*/file_*.txt"
```

For `ls --search`, patterns starting with `/` are anchored at remote root. Relative patterns search under the current `--path` or mapped base.

List configured remotes and status:

```bash
repokit-backup list
```

`list` distinguishes:

- `[mapped]`: remote and local paths are saved
- `[registered]`: remote is configured in the registry, but no paths are mapped yet
- `[unmapped]`: remote exists in rclone config but has no registry entry

Update policy for an existing remote:

```bash
repokit-backup policy --remote myproject --set full
repokit-backup policy --remote myproject --set append-only
repokit-backup policy --remote myproject --set pull-only
```

View differences before sync:

```bash
repokit-backup diff --remote myproject
```

Remove a remote:

```bash
repokit-backup delete --remote myproject
```

View supported remote types:

```bash
repokit-backup types
```

## Backend Notes

Backend-specific setup details are covered in [`docs/api-reference.md`](docs/api-reference.md).
Use the sections below only for the two most common OAuth headless flows.

## SSH tunnel OAuth mode

For remote/headless sessions where you can keep an SSH tunnel open from your local browser machine:

```bash
repokit-backup add --remote dropbox --backend dropbox --ssh
```

`repokit-backup` will print:

- an `APP_PORT` prompt (default from `.env` key `APP_PORT`, fallback `53682`)
- the SSH tunnel command to run on your local machine
- instructions to open the exact OAuth callback URL printed by `rclone` (`/auth?state=...`)

Important:

- open the full `/auth?state=...` URL exactly as printed by `rclone`
- do not open only `http://127.0.0.1:53682/`
- if tunnel-based callback fails, use `--token-file` as the fallback

## Headless OAuth in containers

If your runtime cannot open a browser (for example, Ubuntu container/VM), create the token on another machine and pass it with `--token` or `--token-file`.

On a machine with browser access:

```bash
rclone authorize "dropbox" --auth-no-open-browser
```

Copy the returned JSON token object into a file (for example `token.json`).

Then in your container:

```bash
repokit-backup add --remote dropbox --backend dropbox --token '<PASTE_TOKEN_JSON>'
```

Or preferably:

```bash
repokit-backup add --remote dropbox --backend dropbox --token-file ./token.json
```

The same flow applies to `onedrive` and `drive` by replacing `"dropbox"` in `rclone authorize`.

## License

MIT
