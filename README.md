# repokit-backup

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/CBS-HPC/repokit-backup/actions/workflows/ci.yml/badge.svg)](https://github.com/CBS-HPC/repokit-backup/actions/workflows/ci.yml)

`repokit-backup` is a standalone CLI for **rclone-based backups** of research projects. It can also be used as a dependency of `repokit`.

## What it does

- Configure and manage rclone remotes (SFTP/ERDA, Dropbox, OneDrive, local, etc.)
- Push, pull, and diff backups
- Transfer between remotes
- Dry-run support for safe previews

## Requirements

- Python 3.12+
- Internet access for the initial rclone download (if not installed)

## Install

From PyPI:

```bash
pip install repokit-backup
```

From wheel (`.whl`):

```bash
# from local dist/
pip install dist/repokit_backup-0.1-py3-none-any.whl
# or
uv pip install dist/repokit_backup-0.1-py3-none-any.whl
```

From source:

```bash
git clone https://github.com/CBS-HPC/repokit-backup.git
cd repokit-backup
pip install -e .
```

Using uv:

```bash
uv pip install repokit-backup
```

## Quick start

Run the commands from your **project root** (the tool treats the current working directory as `PROJECT_ROOT`).

```bash
backup types
backup add --remote erda
backup push --remote erda
backup pull --remote erda
backup diff --remote erda
backup list
backup delete --remote erda
```

Remote-to-remote transfer:

```bash
backup transfer --source erda --destination onedrive --mode copy --confirm
```

## Configuration

- Remote mappings are stored at: `./bin/rclone_remote.json`
- The `bin/` folder is created in the current project root.
- If you use `.env`, it is read via `repokit-common` helpers, but it is optional.

## Notes

- `rclone` is downloaded/managed automatically if missing.
- Use `--dry-run` to preview actions without modifying remotes.

## Development

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pytest
ruff check .
```

## License

MIT

### <a id="cli-tools"></a>
<details>
<summary><strong>🔧 CLI Tools</strong></summary><br>

The Repokit toolchain provides command-line tools for core automation (`repokit`) plus standalone backup (`repokit-backup`) and DMP workflows (`repokit-dmp`).

GitHub repositories: [`repokit`](https://github.com/CBS-HPC/repokit), [`repokit-common`](https://github.com/CBS-HPC/repokit-common), [`repokit-backup`](https://github.com/CBS-HPC/repokit-backup), [`repokit-dmp`](https://github.com/CBS-HPC/repokit-dmp).

> ℹ️ **Note**: The CLI tools are automatically installed as part of the project environment.  
> You can also manually install or reinstall them using:  
> `uv pip install repokit` or `pip install repokit`

Once installed, the following commands are available from the terminal:

| Command                  | Description                                                                 |
|--------------------------|-----------------------------------------------------------------------------|
| `repokit`                | Core project automation: deps, readme, templates, examples, git config, CI, lint. |
| `repokit-backup`         | Manages remote backup via `rclone` (add, push, pull, list, diff, delete).   |
| `repokit-dmp`            | DMP tools: dataset registry, DMP update, editor UI, publish to Zenodo/Dataverse. |

#### 🛠️ Usage

After activating your environment (see [🚀 Project Activation](#-project-activation)), run any command directly:

```bash
repokit deps
repokit readme
repokit-backup push --remote erda
repokit-dmp editor
```

Below is a detailed description of each CLI command available in the project, including usage, behavior, and example output.

### <a id="repokit-backup"></a>
<details>
<summary><strong>🧰 <code>repokit-backup</code></strong></summary>

The backup CLI is exposed as the [`repokit-backup`](https://github.com/CBS-HPC/repokit-backup) command via the Python package defined in `pyproject.toml`:

```toml
[project.scripts]
repokit-backup = "repokit_backup.cli:main"
```

Once your environment is activated (see [🚀 Project Activation](#-project-activation)), you can run the following commands from the terminal:

**📌 Setup a Remote**
```
repokit-backup add --remote erda  # (other options: erda, dropbox, onedrive, local or all)
```
**🚀 Push to Remote**
```
repokit-backup push --remote erda  # (other options: erda, dropbox, onedrive, local or all)
```
This command performs the following:
- Commits and pushes the root Git project (if version control is enabled)
- Commits and pushes the data/ Git repository
- Syncs the project, excluding any ignored files (e.g., .rcloneignore or pyproject.toml patterns)

**📥 Pull Backup from Remote**
```
repokit-backup pull --remote erda  # (other options: erda, dropbox, onedrive, local or all)
```
**📊 View Differences Before Sync**
```
repokit-backup diff --remote erda  # (other options: erda, dropbox, onedrive, local or all)
```
**🧹 Remove Remote**
```
repokit-backup delete --remote erda  # (other options: erda, dropbox, onedrive, local or all)
```
**📋 List Configured Remotes and Sync Status**
```
repokit-backup list
```
**📦 View Supported Remote Types**
```
repokit-backup types
```

📁 All configured remotes and folder mappings are logged in `./bin/rclone_remote.json`.

---
</details>

### <a id="backup-rclone"></a>
<details>
<summary><strong>☁️ Backup with Rclone</strong></summary><br>

Data loss can compromise months or years of research. To support **reproducible**, **secure**, and **policy-compliant** workflows, this template offers automated backup to CBS-approved storage providers using [`rclone`](https://rclone.org).

Supported backup targets include:

- [**ERDA**](https://erda.dk/) – configured via **SFTP with password and MFA**  
- [**Dropbox**](https://www.dropbox.com/)  
- [**OneDrive**](https://onedrive.live.com/)  
- **Local** storage – backup to a folder on your own system  
- **Multiple** – select any combination of the above

> ☁️ `rclone` is automatically downloaded and installed if not already available on your system.  
> 🧪 Other [Rclone-supported remotes](https://rclone.org/overview/#supported-storage-systems) **should work**, but have not yet been tested with this template's workflow.
> 📁 All configured remotes and folder mappings are logged in `./bin/rclone_remote.json`.

#### 🧰 CLI Backup Commands

Once your environment is activated (see [🚀 Project Activation](#-project-activation)), you can use the `repokit-backup` CLI tool:

**📌 Setup a Remote**
```
repokit-backup add --remote erda  # (other options: erda, dropbox, onedrive, local or all)
```
**🚀 Push to Remote**
```
repokit-backup push --remote erda  # (other options: erda, dropbox, onedrive, local or all)
```
This command performs the following:
- Commits and pushes the root Git project (if version control is enabled)
- Commits and pushes the data/ Git repository
- Syncs the project, excluding any ignored files (e.g., .rcloneignore or pyproject.toml patterns)

**📥 Pull Backup from Remote**
```
repokit-backup pull --remote erda  # (other options: erda, dropbox, onedrive, local or all)
```
**📊 View Differences Before Sync**
```
repokit-backup diff --remote erda  # (other options: erda, dropbox, onedrive, local or all)
```
**🧹 Remove Remote**
```
repokit-backup delete --remote erda  # (other options: erda, dropbox, onedrive, local or all)
```
**📋 List Configured Remotes and Sync Status**
```
repokit-backup list
```
**📦 View Supported Remote Types**
```
repokit-backup types
```

---
</details>
