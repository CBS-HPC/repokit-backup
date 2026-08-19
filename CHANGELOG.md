# Changelog

All notable user-visible changes are recorded here. This project follows
[Semantic Versioning](https://semver.org/).

## [1.0.1] - 2026-08-19

### Fixed

- `push`, `pull`, and remote-to-remote `transfer` no longer terminate healthy
  rclone processes after ten minutes. Transfers have no total time limit by
  default, allowing large files to complete.

### Added

- `--transfer-timeout SECONDS` for `push`, `pull`, and `transfer`. Use a
  positive value to set a total limit per rclone invocation; `0` and omission
  leave the transfer unlimited.

## [1.0.0] - 2026-08-14

### Added

- Explicit backend selection for `add`, including LUMI-O and unified
  LUMI-P/LUMI-F support.
- Persistent mapping modes, remote-only pins, non-interactive remote setup,
  remote search, and selective push/pull workflows.
- `init` for project-local rclone and configuration setup.
- Module invocation with `python -m repokit_backup`.
- GitHub Actions coverage for Python 3.10 and 3.12 on Linux and Windows.

### Changed

- `repokit-backup add` requires `--backend`; a remote alias no longer selects a
  backend during creation.
- Automatic rclone installation uses a pinned, SHA-256-verified 1.73.2 archive.
- Operational failures now produce a nonzero CLI exit status.
- Project-local `.env` and `bin/` runtime state are added to `.gitignore` by
  initialization.
- `backup` remains a compatibility alias; new documentation and automation
  should use `repokit-backup`.
- Supports `repokit-common>=0.1.0,<=1.0.0`.

### Security

- Remote registry writes and removal are atomic.
- ZIP extraction rejects archive members that would escape the project runtime
  directory.

## [0.1] - Historical

Initial tracked package release line.
