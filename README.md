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
