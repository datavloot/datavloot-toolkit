# Releasing

Two independently versioned things ship from this repo:

- the **`dbt/optimist` package**, installed via git (`dbt deps`)
- the **`datavloot` Python package**, installed via PyPI (`pip install`)

They version and release differently — a git-installed dbt package needs a moving ref because
git has no equivalent of `pip`'s version-range operators, while a PyPI package doesn't need
that machinery at all. This doc covers both.

---

## Releasing the optimist dbt package

How `dbt/optimist` is versioned and tagged, so consuming projects can pin to a moving
"current minor version" ref instead of `main` — picking up patch releases without silently
picking up breaking changes.

### Versioning

SemVer, scoped to `dbt/optimist` only — independent of the `datavloot` PyPI package version.
`version:` in [`dbt/optimist/dbt_project.yml`](../dbt/optimist/dbt_project.yml) is the source of
truth.

- **PATCH** (`0.1.0` → `0.1.1`) — bug fixes, no consumer-facing change.
- **MINOR** (`0.1.0` → `0.2.0`) — backwards-compatible additions: new macros, new optional
  config keys, new built-in dims/facts, internal refactors that keep the public call signature
  (e.g. converting `generate_surrogate_key` to `adapter.dispatch` — same signature, still minor).
- **MAJOR** (`0.x` → `1.0.0`) — anything that would break `dbt parse`/`dbt build` for an
  existing consumer without them changing their own project: renaming or removing a macro or
  macro argument, renaming a required `meta` key (e.g. a future `fk`/`dim_fk`/`key` rename),
  changing a built-in model's public columns or grain (e.g. `dim_time` moving to a different
  default granularity), or any other default-behavior change that changes output. Bundle
  breaking changes into one deliberate major bump rather than shipping them piecemeal — a
  consumer should have to read one migration note, not four.

### Git refs

- **Immutable release tags:** bare `X.Y.Z`, one per release. Never moved once pushed.
- **Moving minor branches:** `0.1.x`, `0.2.x`, … — each points at the latest released commit
  within that minor version. Fast-forwarded on every patch release. Frozen permanently the
  moment the next minor version ships.
- Unprefixed: a bare `X.Y.Z` tag in this repo always means the dbt package. The `datavloot`
  PyPI package uses `datavloot-vX.Y.Z` instead, so the two series never collide.

A consuming project's `packages.yml` references either:

```yaml
# floats within the current minor — picks up 0.1.1, 0.1.2, ... automatically
revision: 0.1.x
```

```yaml
# pinned to one exact release for full reproducibility
revision: 0.1.0
```

Moving from `0.1.x` to `0.2.x` is always a manual, deliberate edit in the consumer's
`packages.yml` — never automatic. Floating is deliberately scoped to patches rather than to a
whole major: while the package is pre-1.0, a minor bump is allowed to change behaviour, so
picking those up silently would defeat the point.

Two rules keep this scheme working. Both fail silently if broken:

- **Never create a tag named `X.Y.x`.** dbt resolves a `revision:` by preferring a tag over a
  branch of the same name, so such a tag would shadow the moving branch permanently — every
  consumer would freeze on it, with no error and no warning.
- **Pushing the moving branch is what ships the release.** The tag alone changes nothing for
  consumers; they track the branch. A release where step 5 was skipped looks complete from the
  repo and leaves everyone on the previous version.

### Cutting a release

1. Decide the bump type (see Versioning above) based only on what changed under
   `dbt/optimist/` since the last release.
2. On a feature branch off `main`, update `version:` in `dbt/optimist/dbt_project.yml` to
   match, and commit.
3. Push the branch and open a pull request against `main`, and merge it on GitHub. **The release
   must not be merged locally**: the tag in the next step has to point at the merge commit
   GitHub creates, which does not exist until the pull request is merged.
   ```bash
   git push -u origin feature/<name>
   gh pr create --base main --title "Release X.Y.Z"
   ```
4. Pull the resulting merge commit and tag it:
   ```bash
   git switch main
   git pull origin main
   git tag -a X.Y.Z -m "optimist dbt package X.Y.Z"
   git push origin X.Y.Z
   ```
5. Pushing the bare tag in step 4 starts the `Release` workflow
   ([`.github/workflows/release.yml`](../.github/workflows/release.yml)), which fast-forwards the
   moving minor branch to the tag, or creates it on the first release of a minor version. Check
   in the Actions tab that it ran: the tag alone changes nothing for consumers who track
   `X.Y.x`. If it did not, do it by hand (patch release):
   ```bash
   git branch -f 0.1.x 0.1.1
   git push origin 0.1.x --force-with-lease
   ```
   On a minor/major bump the new branch is created instead, and the old one is never touched
   again:
   ```bash
   git branch 0.2.x 0.2.0
   git push origin 0.2.x
   # 0.1.x is now frozen — do not push to it again
   ```
6. Set `DBT_PACKAGE_VERSION` in [`datavloot_platform/cli.py`](../datavloot_platform/cli.py) to
   the new version, on the **same feature branch as step 2**. `datavloot new` and
   `datavloot demo` write it as `revision:` in a new project's `packages.yml`, so new projects
   get this release with the next datavloot PyPI release. `tests/test_scaffold.py` fails while
   the constant and `version:` in `dbt_project.yml` differ.

> **Ordering hazard.** Between the merge (step 3) and the tag push (step 4), `main` pins new
> projects to a tag that does not exist yet, so `dbt deps` fails in a project created from a
> checkout of `main`. PyPI users only get the new constant with the next datavloot release, so
> push the tag before that release.
>
> **Protected refs.** The workflow pushes with the built-in `GITHUB_TOKEN`, which cannot push to
> an `X.Y.x` branch that has a protection rule. If the push is rejected, allow
> `github-actions[bot]` in the rule's bypass list, or give the workflow a token with
> *Contents: write* (see the comments in `release.yml`). A tag protection rule on `X.Y.Z`
> blocks your own `git push origin X.Y.Z` the same way.

### Release history

- **`0.1.0`** — first release. `dbt/optimist/dbt_project.yml` previously declared
  `version: '1.0.0'`, a stale default from `dbt init` rather than an actual release; corrected
  to `'0.1.0'` to match reality. This release also replaced `revision: main` (and its
  `dbt deps` warning) with `revision: 0.1.x` in the scaffold and demo `packages.yml` templates,
  and established the unprefixed-tag / `X.Y.x` moving-branch scheme described above.

---

## Releasing the datavloot PyPI package

How the `datavloot` Python package (the CLI + Crows Nest + everything under
`datavloot_platform/`) gets versioned, built, and published to PyPI.

### Versioning

SemVer, `version` in [`pyproject.toml`](../pyproject.toml) — the single source of truth (not
dynamic; there's no `[tool.hatch.version]` source, so this field must be bumped by hand before
every release). Independent of the `dbt/optimist` version above.

- **PATCH** — bug fixes, no consumer-facing change.
- **MINOR** — backwards-compatible additions: new CLI commands/flags, new optional
  dependencies/extras, new Crows Nest features.
- **MAJOR** — breaking changes: removing/renaming a CLI command or flag, renaming or removing
  an extra (e.g. `[optimist]`), dropping support for a Python version, changing the scaffolded
  project structure in a way that breaks existing projects on upgrade.

No moving-branch scheme is needed here, unlike the dbt package above — PyPI itself is the
distribution point, and `pip`'s own version specifiers (e.g. `datavloot[optimist]<1.0`) already
give consumers a "stay within a major" option without any extra git machinery on our side.

### Git refs

One immutable tag per release: `datavloot-vX.Y.Z`, matching the version just published to PyPI.
Prefixed with `datavloot-` (as opposed to the dbt package's bare `X.Y.Z` tags) so the two tag
series never collide in the same repo.

### Cutting a release

1. Decide the bump type (see Versioning above) based on what changed outside `dbt/optimist/`
   since the last release.
2. On a feature branch off `main`, update `version` in `pyproject.toml` to match, and commit.
3. Push the branch, open a pull request against `main`, and merge it on GitHub. Same flow as
   [step 3 of the dbt package procedure](#cutting-a-release) above; do not merge locally.
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
   If the push is rejected, see the protected-refs note in the dbt package procedure above.
8. Check whether the install snippets and release notes on the website (the `datavloot-website`
   repository) need updating to match.

### Current state

As of 2026-10-22:

- PyPI has **0.1.0**, **0.1.1** and **0.1.2**; `pyproject.toml` says `0.1.2`. Git has the tags
  `datavloot-v0.1.1` and `datavloot-v0.1.2`; `datavloot-v0.1.0` was never tagged.
- The dbt package is at `0.1.0` (`dbt/optimist/dbt_project.yml` and `DBT_PACKAGE_VERSION` in
  `cli.py`), tagged `0.1.0`.
- **There is also a bare tag `0.1.2`** (2026-09-07, the same day as `datavloot-v0.1.2`), while
  no dbt package `0.1.2` exists. It looks like the PyPI release tagged without its prefix. A bare
  tag counts as a dbt package release and starts the `Release` workflow, so decide whether to
  delete it, or to keep it and skip `0.1.2` for the dbt package (bump straight to `0.1.3`).
