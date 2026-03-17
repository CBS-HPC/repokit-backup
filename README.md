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
- [docs/api-reference.md](C:/work/repokit-packages/repokit-backup/docs/api-reference.md): full CLI, backend, mapping, policy, and transfer behavior reference

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
| `repokit-backup add` | Configure a backup remote and mapping. |
| `repokit-backup push` | Push/sync project data to remote storage. |
| `repokit-backup pull` | Restore/sync from remote to local project. |
| `repokit-backup diff` | Show remote/local diff report. |
| `repokit-backup list` | List configured remotes/mappings. |
| `repokit-backup ls` | List files/folders at a configured remote path. |
| `repokit-backup policy` | Update policy (`full`, `append-only`, `pull-only`) for a configured remote. |
| `repokit-backup delete` | Remove a configured remote mapping. |
| `repokit-backup transfer` | Transfer data between two remotes. |
| `repokit-backup types` | List supported remote types. |

Full flag-by-flag behavior is documented in [docs/api-reference.md](C:/work/repokit-packages/repokit-backup/docs/api-reference.md).

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
repokit-backup add --remote dropbox-main --backend dropbox
repokit-backup add --remote onedrive-main --backend onedrive
repokit-backup add --remote drive-main --backend drive
repokit-backup add --remote erda-main --backend erda
repokit-backup add --remote ucloud-main --backend ucloud
repokit-backup add --remote lumi-object --backend lumi-o
repokit-backup add --remote lumi-scratch --backend lumi-p
repokit-backup add --remote local-archive --backend local
repokit-backup add --remote sftp-lab --backend sftp
repokit-backup add --remote s3-archive --backend s3
```

Set source scope during add:

```bash
# Project-relative source (created if missing)
repokit-backup add --remote dropbox-main --backend dropbox --subdir /data

# Filesystem source path
repokit-backup add --remote dropbox-main --backend dropbox --path /work/shared/data
```

`--local-path` is still accepted for backward compatibility (alias of `--path` for `add`).

`--remote` is an alias/name only. For `add`, `--backend` is required and is the source of truth for the backend being created.

For non-`add` commands, stored registry metadata is used first, with alias inference still available as a compatibility fallback for older mappings.

During `add`, `repokit-backup` now first asks:

```text
Create a local/remote path mapping now? [Y/n]:
```

If you answer `n`, the remote is configured but no registry mapping is created yet.

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

LUMI environment keys, backend aliases, and storage selector details are documented in [docs/api-reference.md](C:/work/repokit-packages/repokit-backup/docs/api-reference.md).

## Common Workflows

Push to remote:

```bash
repokit-backup push --remote dropbox-main
```

This command performs the following:

- Commits and pushes the root Git project (if version control is enabled)
- Commits and pushes the data/ Git repository
- Syncs the project, excluding any ignored files (e.g., `.rcloneignore` or `pyproject.toml` patterns)

Pull backup from remote:

```bash
repokit-backup pull --remote dropbox-main
```

Note: if remote policy is `append-only` or `pull-only`, `pull` auto-switches `sync`/`move` to `copy`.
For unmapped remotes, `pull` requires `--path`; if `--remote-path` is omitted it defaults to the remote root.

Interactive file/folder selection for transfer:

```bash
repokit-backup push --remote dropbox-main --select
repokit-backup pull --remote dropbox-main --select
```

`--select` opens an interactive picker (number/range syntax like `1,3,5-7`) and transfers only selected entries.

Scope selection to a subpath:

```bash
repokit-backup push --remote dropbox-main --select /data
repokit-backup pull --remote dropbox-main --select /data
```

Direct path selection also works (non-interactive include fallback):

```bash
repokit-backup pull --remote dropbox-main --select /data/dataset1/file1.txt
repokit-backup push --remote dropbox-main --select /data/dataset1/file1.txt
```

Non-interactive recursive filtering for transfer:

```bash
repokit-backup push --remote dropbox-main --search "/data/**/*.parquet"
repokit-backup pull --remote dropbox-main --path ./restore --search "/data/**/*.parquet"
repokit-backup pull --remote dropbox-main --remote-path dropbox-main:/archive --path ./restore --search "20250313_*"
```

`--search` preserves relative folder structure under the transfer root. For example, `/data/**/*.parquet` keeps the `data/...` tree on the destination.
`--search` and `--select` are mutually exclusive for `push` and `pull`.

Transfer between two configured remotes:

```bash
repokit-backup transfer --source dropbox-main --destination erda-main --mode copy --confirm
```

List remote entries at mapped root or a subpath:

```bash
repokit-backup ls --remote dropbox-main
repokit-backup ls --remote dropbox-main --path /data
```

If a remote has no saved mapping, `ls` falls back to the remote root:

```bash
repokit-backup ls --remote dropbox-main
repokit-backup ls --remote dropbox-main --path /data
```

Recursive search for remote files/folders:

```bash
repokit-backup ls --remote dropbox-main --search "/data/file_*.txt"
repokit-backup ls --remote dropbox-main --search "/20250313_*"
repokit-backup ls --remote dropbox-main --path /data --search "file_*.txt"
repokit-backup ls --remote dropbox-main --search "/*/file_*.txt"
```

For `ls --search`, patterns starting with `/` are anchored at remote root. Relative patterns search under the current `--path` or mapped base.

List configured remotes and status:

```bash
repokit-backup list
```

Update policy for an existing remote:

```bash
repokit-backup policy --remote dropbox-main --set full
repokit-backup policy --remote dropbox-main --set append-only
repokit-backup policy --remote dropbox-main --set pull-only
```

View differences before sync:

```bash
repokit-backup diff --remote dropbox-main
```

Remove a remote:

```bash
repokit-backup delete --remote dropbox-main
```

View supported remote types:

```bash
repokit-backup types
```

## Backend Notes

Backend-specific setup details are covered in [docs/api-reference.md](C:/work/repokit-packages/repokit-backup/docs/api-reference.md).
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
