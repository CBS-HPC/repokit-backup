# Contributing

## Development Setup

Use Python 3.10 or newer and install a compatible `repokit-common` checkout
or released wheel first:

```bash
python -m pip install -e ../repokit-common
python -m pip install -e ".[dev]"
```

Run the local checks before proposing a change:

```bash
python -m ruff check .
python -m ruff format --check .
python -m mypy src
python -m pytest
python -m build
```

## Change Expectations

- Keep command failures observable through a nonzero exit status.
- Preserve remote paths exactly, including a meaningful leading `/` after the
  rclone remote alias.
- Add tests for CLI behavior, configuration persistence, and error paths when
  changing backup or delete logic.
- Do not add credentials, `.env` files, `bin/` runtime state, or generated
  private rclone configuration to Git.
- Update `README.md`, `docs/api-reference.md`, and `CHANGELOG.md` for
  user-facing behavior changes.

## Cross-Repository Dependency

repokit-backup 1.0.x requires `repokit-common>=0.1.0,<0.2.0`. Coordinate changes
to shared root detection or environment persistence with the Common 0.1.x
release line before releasing a backup wheel.
