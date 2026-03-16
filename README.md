# repokit-backup

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/CBS-HPC/repokit-backup/actions/workflows/ci.yml/badge.svg)](https://github.com/CBS-HPC/repokit-backup/actions/workflows/ci.yml)

Backup and synchronization utilities built on rclone. Works with the Research Template and can be used standalone.

Data loss can compromise months or years of research. To support **reproducible**, **secure**, and **policy-compliant** workflows, this template offers automated backup to storage providers using [`rclone`](https://rclone.org).

Supported backup targets:

- [**ERDA**](https://erda.dk/)  (SFTP with password + MFA) 
- [**Dropbox**](https://www.dropbox.com/)  
- [**OneDrive**](https://onedrive.live.com/)  
- **Local** storage - backup to a folder on your own system  
- **Multiple** - select any combination of the above

Notes:

- `rclone`is automatically downloaded and installed if not already available
- Other [Rclone-supported remotes](https://rclone.org/overview/#supported-storage-systems) **should work**, but have not yet been tested with this template's workflow.
- All configured remotes and folder mappings are logged in `./bin/rclone_remote.json`.
- Full command and behavior reference: [docs/api-reference.md](C:/work/repokit-packages/repokit-backup/docs/api-reference.md)

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

## Examples

Setup a remote:

```bash
repokit-backup add --remote dropbox-main
```

Explicit backend (recommended when alias does not include a backend-like prefix):

```bash
repokit-backup add --remote teamdata --backend dropbox
repokit-backup add --remote lumi-object-prod --backend lumi-o
repokit-backup add --remote lumi-scratch --backend lumi-p
```

Set source scope during add:

```bash
# Project-relative source (created if missing)
repokit-backup add --remote dropbox-main --subdir /data

# Filesystem source path
repokit-backup add --remote dropbox-main --path /work/shared/data
```

`--local-path` is still accepted for backward compatibility (alias of `--path` for `add`).

`--remote` is an alias/name only. Backend resolution order for `add`:
1. `--backend` (explicit, preferred)
2. infer from alias prefix for backward compatibility
3. fallback to `sftp`

Canonical backend names:

- `lumio` (aliases: `lumio`, `lumi-o`)
- `lumip` (aliases: `lumip`, `lumi-p`, `lumi-f`)

During `add`, a persistent push policy is saved per remote:

- `full`: push/pull `sync`, `copy`, and `move` are allowed
- `append-only`: push `copy` only; pull `copy` only
- `pull-only`: push is blocked; pull `copy` only

If the remote folder already exists, the conflict prompt includes:

- overwrite
- merge/sync
- use existing
- change folder
- cancel

LUMI backend environment keys:

- `lumio`:
  - `LUMIO_PROJECT_ID`
  - `LUMIO_ACCESS_KEY`
  - `LUMIO_SECRET_KEY`
  - `LUMIO_DEFAULT_BASE`
- `lumip`:
  - `LUMIP_PROJECT_ID`
  - `LUMIP_USERNAME`
  - `LUMIP_BASE_PATH`
  - `LUMIP_HOST` (default `lumi.csc.fi`)
  - `LUMIP_PORT` (default `22`)

`lumip` storage selector presets:

- `/users/<username>`
- `/project/<project_id>`
- `/scratch/<project_id>`
- `/flash/<project_id>`
- custom absolute path

`lumi-f` is treated as `lumip` with the `/flash/<project_id>` storage option.

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

List configured remotes and status:

```bash
repokit-backup list
```

`list` output includes each remote's configured push policy.

View supported remote types:

```bash
repokit-backup types
```

For OAuth remotes (`dropbox`, `onedrive`, `drive`), see:

- `SSH tunnel OAuth mode` (interactive via local browser + SSH tunnel)
- `Headless OAuth in containers` (token-based, non-interactive)

## SSH tunnel OAuth mode

For remote/headless sessions where you can keep an SSH tunnel open from your local browser machine:

```bash
repokit-backup add --remote dropbox --ssh
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
repokit-backup add --remote dropbox --token '<PASTE_TOKEN_JSON>'
```

Or preferably:

```bash
repokit-backup add --remote dropbox --token-file ./token.json
```

The same flow applies to `onedrive` and `drive` by replacing `"dropbox"` in `rclone authorize`.

## License

MIT
