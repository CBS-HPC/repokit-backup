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

## Installation

> Note: `repokit-backup` is not published on PyPI yet. Use local wheel/source installation for now.

Install from PyPI:

```bash
pip install repokit-backup
```

Install from local wheel files (`/dist`):

```bash
# 1) Install dependency wheel first
pip install ../repokit-common/dist/repokit_common-*.whl

# 2) Install repokit-backup wheel
pip install ./dist/repokit_backup-*.whl
```

If you are installing into a fresh virtual environment, install in this order so `repokit-common` is available before `repokit-backup`.

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
| `repokit-backup delete` | Remove a configured remote mapping. |
| `repokit-backup transfer` | Transfer data between two remotes. |
| `repokit-backup types` | List supported remote types. |

## Examples

Setup a remote:

```bash
repokit-backup add --remote erda
```

Push to remote:

```bash
repokit-backup push --remote erda
```

This command performs the following:

- Commits and pushes the root Git project (if version control is enabled)
- Commits and pushes the data/ Git repository
- Syncs the project, excluding any ignored files (e.g., `.rcloneignore` or `pyproject.toml` patterns)

Pull backup from remote:

```bash
repokit-backup pull --remote erda
```

View differences before sync:

```bash
repokit-backup diff --remote erda
```

Remove a remote:

```bash
repokit-backup delete --remote erda
```

List configured remotes and status:

```bash
repokit-backup list
```

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
