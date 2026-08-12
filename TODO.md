# Repokit Backup TODO

## Deferred: Python 3.10 compatibility for LUMI

LUMI environments require Python 3.10 compatibility. This work is deferred;
`repokit-backup/main` remains Python 3.12+ until the full release path is ready.

- [ ] Lower `repokit-backup` metadata, Ruff, mypy, and CI targets to Python 3.10.
- [ ] Fix formatting, mypy, and nested-checkout pytest collection before enabling
      the Python 3.10 CI matrix.
- [ ] Keep `repokit-common` compatible with Python 3.10 and publish a matching
      artifact; a fresh backup installation must not resolve an older Common
      package that requires Python 3.12.
- [ ] Verify editable and wheel-based installs of both packages in a clean
      Python 3.10 environment.
- [ ] Run LUMI-O and LUMI-P smoke tests using the supported Python 3.10 runtime.

## Active: non-interactive remote configuration

- [ ] Add non-interactive remote setup, persistent remote-path pins, and
      explicit conflict/policy handling as described in the audit.
