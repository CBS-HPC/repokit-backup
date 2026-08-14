# Release Procedure

Use this procedure for a repokit-backup release after the required
`repokit-common` 0.1.x is published.

## Prerequisites

- `repokit-common` 0.1.x is tagged and its wheel is available from its GitHub
  release.
- The backup branch is reviewed, clean, and synchronized with its target.
- `CHANGELOG.md` has a dated release entry and `pyproject.toml` has the final
  semantic version.

## Validation

Run the complete local release gate:

```bash
python -m ruff check .
python -m ruff format --check .
python -m mypy src
python -m pytest
python -m build --outdir tmp/release-build
python -m pip install --force-reinstall --no-deps (Get-ChildItem tmp\release-build\*.whl | Select-Object -First 1).FullName
repokit-backup --help
python -m repokit_backup --help
```

Also confirm the GitHub Actions matrix passes on Windows and Linux for Python
3.10 and 3.12. Perform a manual smoke test with a disposable local remote and,
when credentials are available, each supported remote family.

## Publish

1. Commit source, documentation, and the rebuilt wheel artifacts according to
   the repository artifact policy.
2. Push the release commit and create an annotated `vX.Y.Z` tag.
3. Create a GitHub release from that tag and attach the wheel and source
   distribution from the verified build output.
4. Update the README installation URLs to the released version if necessary.
5. Confirm a clean virtual environment can install the matching Common wheel
   followed by the backup wheel and run `repokit-backup --help`.
