# repokit-backup

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/CBS-HPC/repokit-backup/actions/workflows/ci.yml/badge.svg)](https://github.com/CBS-HPC/repokit-backup/actions/workflows/ci.yml)

Backup and synchronization utilities built on rclone. Works with the Research Template and can be used standalone.

## ?? What it does

Data loss can compromise months or years of research. This package provides automated backup to CBS-approved storage providers using rclone.

Supported backup targets:

- ERDA (SFTP with password + MFA)
- Dropbox
- OneDrive
- Local folder
- Multiple (any combination of the above)

Notes:

- rclone is automatically downloaded and installed if not already available
- Other rclone remotes should work, but are not yet tested with this workflow
- All configured remotes and folder mappings are stored in `./bin/rclone_remote.json`

## ?? Installation

```bash
pip install repokit-backup
```

## ?? Requirements

- `rclone` on `PATH` (auto-installed if missing)

## ?? CLI

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

## ?? Examples

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

### <a id="backup-rclone"></a>
<details>
<summary><strong>â˜ï¸ Backup with Rclone</strong></summary><br>

Data loss can compromise months or years of research. To support **reproducible**, **secure**, and **policy-compliant** workflows, this template offers automated backup to CBS-approved storage providers using [`rclone`](https://rclone.org).

Supported backup targets include:

- [**ERDA**](https://erda.dk/) â€“ configured via **SFTP with password and MFA**  
- [**Dropbox**](https://www.dropbox.com/)  
- [**OneDrive**](https://onedrive.live.com/)  
- **Local** storage â€“ backup to a folder on your own system  
- **Multiple** â€“ select any combination of the above

> â˜ï¸ `rclone` is automatically downloaded and installed if not already available on your system.  
> ðŸ§ª Other [Rclone-supported remotes](https://rclone.org/overview/#supported-storage-systems) **should work**, but have not yet been tested with this template's workflow.
> ðŸ“ All configured remotes and folder mappings are logged in `./bin/rclone_remote.json`.

#### ðŸ§° CLI Backup Commands

Once your environment is activated (see [ðŸš€ Project Activation](#-project-activation)), you can use the `repokit-backup` CLI tool:

**ðŸ“Œ Setup a Remote**
```
repokit-backup add --remote erda  # (other options: erda, dropbox, onedrive, local or all)
```
**ðŸš€ Push to Remote**
```
repokit-backup push --remote erda  # (other options: erda, dropbox, onedrive, local or all)
```
This command performs the following:
- Commits and pushes the root Git project (if version control is enabled)
- Commits and pushes the data/ Git repository
- Syncs the project, excluding any ignored files (e.g., .rcloneignore or pyproject.toml patterns)

**ðŸ“¥ Pull Backup from Remote**
```
repokit-backup pull --remote erda  # (other options: erda, dropbox, onedrive, local or all)
```
**ðŸ“Š View Differences Before Sync**
```
repokit-backup diff --remote erda  # (other options: erda, dropbox, onedrive, local or all)
```
**ðŸ§¹ Remove Remote**
```
repokit-backup delete --remote erda  # (other options: erda, dropbox, onedrive, local or all)
```
**ðŸ“‹ List Configured Remotes and Sync Status**
```
repokit-backup list
```
**ðŸ“¦ View Supported Remote Types**
```
repokit-backup types
```

---
</details>

## ?? License

MIT
