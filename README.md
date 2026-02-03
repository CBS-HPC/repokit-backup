# repokit-backup

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/CBS-HPC/repokit-backup/actions/workflows/ci.yml/badge.svg)](https://github.com/CBS-HPC/repokit-backup/actions/workflows/ci.yml)

Backup utilities for research projects, built around **rclone**. This package can be used **independently** or as part of `repokit`.

## Highlights

- Configure and manage rclone remotes
- Push/pull project backups
- Diff and list backup status
- Supports multiple storage targets (e.g., ERDA, Dropbox, OneDrive, local)

## Installation

From source:

```bash
git clone https://github.com/CBS-HPC/repokit-backup.git
cd repokit-backup
pip install -e .
```

## CLI

```bash
backup types
backup add --remote erda
backup push --remote erda
backup pull --remote erda
backup diff --remote erda
backup list
backup delete --remote erda
```

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
