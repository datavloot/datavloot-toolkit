# Releasing

This repo releases the **`datavloot` Python package**, installed via PyPI (`pip install`).

The **`optimist` dbt package** that the templates install is released from its own repo,
[datavloot/dbt-datavloot-optimist](https://github.com/datavloot/dbt-datavloot-optimist), with bare `X.Y.Z` tags there.

---

## The optimist dbt package

### Versioning

SemVer, independent of the `datavloot` PyPI package version. `version:` in the package repo's
`dbt_project.yml` is the source of truth.

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

### Shipping a release to new projects

The scaffold and demo templates pin an exact tag:

```yaml
  - git: "https://github.com/datavloot/dbt-datavloot-optimist.git"
    revision: 0.1.0
```

After tagging a release in the package repo, update `revision:` in
[`datavloot_platform/templates/scaffold/packages.yml`](../datavloot_platform/templates/scaffold/packages.yml)
and
[`datavloot_platform/templates/demo/packages.yml`](../datavloot_platform/templates/demo/packages.yml)
on a feature branch here, then release `datavloot` so `datavloot new` scaffolds with it. Existing
projects keep their pin until they edit their own `packages.yml`.

Once the package is listed on dbt Package Hub, the templates can switch to
`package: datavloot/optimist` with a version range (e.g. `[">=0.1.0", "<0.2.0"]`), which picks up
patch releases without any moving branch.

### Projects created before the package moved out

Older projects install the package from this repo:

```yaml
  - git: "https://gitlab.com/datavloot/datavloot-toolkit.git"
    subdirectory: "dbt/optimist"
    revision: 0.1.x
```

The `0.1.x` branch and the bare `0.1.0` and `0.1.2` tags in this repo still contain the package,
so those projects keep working. **Do not delete or move them.** To switch an older project to the
new repo, replace that entry with the snippet above. Macro names and the
`dbt_packages/optimist/` paths are unchanged. The package no longer brings in elementary or its
`on-run-end` hook, so add both to the project as the current templates do.

---

## Releasing the datavloot PyPI package

How the `datavloot` Python package (the CLI + Crows Nest + everything under
`datavloot_platform/`) gets versioned, built, and published to PyPI.

### Versioning

SemVer, `version` in [`pyproject.toml`](../pyproject.toml) — the single source of truth (not
dynamic; there's no `[tool.hatch.version]` source, so this field must be bumped by hand before
every release). Independent of the optimist dbt package version.

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
Prefixed with `datavloot-` because the bare `X.Y.Z` tags in this repo belong to the dbt package
releases made before it moved out.

### Cutting a release

1. Decide the bump type (see Versioning above) based on what changed since the last release.
2. On a feature branch off `main`, update `version` in `pyproject.toml` to match, and commit.
3. Push the branch, open a merge request against `main`, and accept it in the GitLab UI —
   `main` is protected and cannot be pushed to directly, and the release must not be merged
   locally: the tag in step 7 has to point at the merge commit GitLab creates.
   ```bash
   git push origin feature/<name>      -o merge_request.create      -o merge_request.target=main      -o merge_request.title="Release datavloot X.Y.Z"
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
   If the push is rejected, the tag pattern needs allowing under *Settings → Repository →
   Protected tags*, or someone with Maintainer rights has to push it.
8. Check whether the install snippet on the marketing site (`html/production/index.html`) needs
   updating to match — see the open item in [`docs/backlog.md`](backlog.md).

### Current state

PyPI already has two releases — **0.1.0** and **0.1.1** (confirmed via the PyPI JSON API,
2026-06-30) — but this checkout's `pyproject.toml` currently says `version = "0.1.0"`, and no
`datavloot-vX.Y.Z` tags exist in git. The next release must bump to at least `0.1.2`, not
`0.1.1` (already taken) or `0.1.0` (already superseded). Worth reconciling before the next
publish: figure out why the checked-out version fell behind what's live, and retroactively tag
the two existing releases (`datavloot-v0.1.0`, `datavloot-v0.1.1`) so the tag history matches
what's actually on PyPI.

There's also a stale local `dist/datavloot-0.1.1-*` build sitting untracked at the repo root
(matches the already-published 0.1.1). `dist/` isn't in `.gitignore` yet — worth adding, so
build output doesn't show up as untracked noise in every `git status`.
