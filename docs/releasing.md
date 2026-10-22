# Releasing

One thing ships from this repo: the **`datavloot` Python package**, installed via PyPI
(`pip install`).

The **`optimist` dbt package** has its own repository,
[dbt-datavloot-optimist](https://github.com/datavloot/dbt-datavloot-optimist), with its own versions and releases. This repo only
decides which of its releases new projects get:

- `DBT_PACKAGE_VERSION` in [`datavloot_platform/cli.py`](../datavloot_platform/cli.py) is the
  tag that `datavloot new` and `datavloot demo` write as `revision:` in a new project's
  `packages.yml`.
- To move new projects to a new dbt package release, bump the constant in a pull request. The
  smoke test (`tests/test_scaffold_smoke.py`) installs the package at that tag from GitHub, so CI
  checks the toolkit against exactly what new projects will get. New projects pick it up with the
  next datavloot release.

Until 2026-10 the dbt package lived in this repository under `dbt/optimist/`, released with bare
`X.Y.Z` tags and a moving `X.Y.x` branch. Those tags and the `0.1.x` branch stay, because
projects created before then install the package from them (`subdirectory: "dbt/optimist"`); do
not move or delete them.

---

## Releasing the datavloot PyPI package

How the `datavloot` Python package (the CLI + Crows Nest + everything under
`datavloot_platform/`) gets versioned, built, and published to PyPI.

### Versioning

SemVer, `version` in [`pyproject.toml`](../pyproject.toml) — the single source of truth (not
dynamic; there's no `[tool.hatch.version]` source, so this field must be bumped by hand before
every release). Independent of the dbt package's versions.

- **PATCH** — bug fixes, no consumer-facing change.
- **MINOR** — backwards-compatible additions: new CLI commands/flags, new optional
  dependencies/extras, new Crows Nest features.
- **MAJOR** — breaking changes: removing/renaming a CLI command or flag, renaming or removing
  an extra (e.g. `[optimist]`), dropping support for a Python version, changing the scaffolded
  project structure in a way that breaks existing projects on upgrade.

No moving-branch scheme is needed — PyPI itself is the
distribution point, and `pip`'s own version specifiers (e.g. `datavloot[optimist]<1.0`) already
give consumers a "stay within a major" option without any extra git machinery on our side.

### Git refs

One immutable tag per release: `datavloot-vX.Y.Z`, matching the version just published to PyPI.
Prefixed with `datavloot-`, so the tags never collide with the bare `X.Y.Z` tags the dbt package
used while it lived here.

### Cutting a release

1. Decide the bump type (see Versioning above) based on what changed since the last release.
2. On a feature branch off `main`, update `version` in `pyproject.toml` to match, and commit.
3. Push the branch, open a pull request against `main`, and merge it on GitHub. **Do not merge
   locally**: the tag in step 7 has to point at the merge commit GitHub creates.
   ```bash
   git push -u origin <branch>
   gh pr create --base main --title "Release X.Y.Z"
   ```
4. Pull the merge commit and build from it, so the uploaded artifact matches the commit that
   gets tagged in step 7:
   ```bash
   git switch main
   git pull origin main
   rm -rf dist/
   uv build
   ```
5. Sanity-check the built artifacts before uploading anything:
   ```bash
   uvx twine check dist/*
   ls -lh dist/
   ```
   `twine check` validates metadata and README rendering only — it will pass a 300 MB wheel
   without comment, which is exactly how 0.1.1 shipped 66.9 MB of frontend build inputs. So
   check the size too: **the wheel should be well under 5 MB**. If it is not, something that
   only a nested `.gitignore` was hiding has entered the build; see the `exclude` list in
   [`pyproject.toml`](../pyproject.toml).

   `tests/test_packaging.py` asserts this in CI on every commit, so a surprise here means the
   pipeline was skipped or the build is being run from a dirty tree.
6. Publish:
   ```bash
   uv publish
   ```
   Needs a PyPI API token — either `UV_PUBLISH_TOKEN` in the environment or `--token` on the
   command line. (`twine upload dist/*` is the equivalent if not using uv, reading credentials
   from `~/.pypirc` or `TWINE_PASSWORD`.)
7. Tag the merge commit you built from in step 4, and push:
   ```bash
   git tag -a datavloot-vX.Y.Z -m "datavloot X.Y.Z"
   git push origin datavloot-vX.Y.Z
   ```
   If the push is rejected, a tag protection rule on `datavloot-v*` needs your account in its
   bypass list.
8. Check whether the install snippets and release notes on the website (the `datavloot-website`
   repository) need updating to match.

### Current state

As of 2026-10-22:

- PyPI has **0.1.0**, **0.1.1** and **0.1.2**; `pyproject.toml` says `0.1.2`. Git has the tags
  `datavloot-v0.1.1` and `datavloot-v0.1.2`; `datavloot-v0.1.0` was never tagged.
- New projects get the dbt package at **0.1.1** from dbt-datavloot-optimist
  (`DBT_PACKAGE_VERSION`).
- The bare tag `0.1.2` (2026-09-07) in this repo has no dbt package release behind it; it looks
  like the PyPI release tagged without its prefix. With the `Release` workflow gone it triggers
  nothing any more. Leave it, so a project that happens to pin it keeps working.
