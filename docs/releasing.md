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
"current major version" ref instead of `main` (see [feedback_thijs.md #1](feedback_thijs.md))
without silently picking up breaking changes.

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
  macro argument, renaming a required `meta` key (e.g. the `fk`/`dim_fk`/`key` rename from
  feedback #12), changing a built-in model's public columns or grain (e.g. `dim_time` moving to
  a different default granularity, feedback #10), or any other default-behavior change that
  changes output. Bundle breaking changes into one deliberate major bump rather than shipping
  them piecemeal — several open items from `feedback_thijs.md` (#10, #11, #12, #13) belong in
  the same future major release for this reason.

### Git refs

- **Immutable release tags:** `optimist-vX.Y.Z`, one per release. Never moved once pushed.
- **Moving major branches:** `optimist-0.x`, `optimist-1.x`, … — each points at the latest
  released commit within that major version. Fast-forwarded on every patch/minor release.
  Frozen permanently the moment the next major version ships.
- Prefixed with `optimist-` (rather than a bare `vX.Y.Z`) to leave room for the `datavloot`
  PyPI package to get its own `datavloot-vX.Y.Z` tags later without collision.

A consuming project's `packages.yml` references either:

```yaml
# floats within the current major — picks up 0.1, 0.2, 0.3, ... automatically
revision: optimist-0.x
```

```yaml
# pinned to one exact release for full reproducibility
revision: optimist-v0.2.0
```

Moving from `optimist-0.x` to `optimist-1.x` is always a manual, deliberate edit in the
consumer's `packages.yml` — never automatic. This is the same model as GitHub Actions'
`uses: action@v4`-style moving major tags.

### Cutting a release

1. On `main`, decide the bump type (see Versioning above) based only on what changed under
   `dbt/optimist/`.
2. Update `version:` in `dbt/optimist/dbt_project.yml` to match.
3. Merge to `main`.
4. Tag the merge commit:
   ```bash
   git tag optimist-vX.Y.Z
   git push origin optimist-vX.Y.Z
   ```
5. Fast-forward the moving major branch (patch/minor release):
   ```bash
   git branch -f optimist-0.x optimist-vX.Y.Z
   git push origin optimist-0.x --force-with-lease
   ```
   Or, on a major bump, create the new branch instead and stop touching the old one:
   ```bash
   git branch optimist-1.x optimist-v1.0.0
   git push origin optimist-1.x
   # optimist-0.x is now frozen — do not push to it again
   ```
6. On a major bump, update `revision:` in
   [`datavloot_platform/templates/scaffold/packages.yml`](../datavloot_platform/templates/scaffold/packages.yml)
   and
   [`datavloot_platform/templates/demo/packages.yml`](../datavloot_platform/templates/demo/packages.yml)
   to the new major branch, so newly scaffolded projects get the new default.

### First release

No tags exist yet. `dbt/optimist/dbt_project.yml` previously declared `version: '1.0.0'` — that
was a stale default from `dbt init`, not an actual release; corrected to `'0.1.0'` to match
reality. The first release should be `optimist-v0.1.0`, cut from `main`, which replaces
`revision: main` (and its `dbt deps` warning) with `revision: optimist-0.x` in the scaffold and
demo `packages.yml` templates.

Cutting this tag/branch and pushing it were intentionally **not** done as part of this write-up
— that's shared remote state and belongs on `main`, not a feature branch mid-review. Run the
steps above (or ask for it to be done) once this is merged.

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
Prefixed with `datavloot-` (as opposed to the dbt package's `optimist-` prefix) so the two tag
series never collide in the same repo.

### Cutting a release

1. On `main`, decide the bump type (see Versioning above) based on what changed outside
   `dbt/optimist/`.
2. Update `version` in `pyproject.toml` to match.
3. Merge to `main`.
4. Build:
   ```bash
   rm -rf dist/
   uv build
   ```
5. Sanity-check the built artifacts before uploading anything:
   ```bash
   uvx twine check dist/*
   ```
6. Publish:
   ```bash
   uv publish
   ```
   Needs a PyPI API token — either `UV_PUBLISH_TOKEN` in the environment or `--token` on the
   command line. (`twine upload dist/*` is the equivalent if not using uv, reading credentials
   from `~/.pypirc` or `TWINE_PASSWORD`.)
7. Tag the release commit and push:
   ```bash
   git tag datavloot-vX.Y.Z
   git push origin datavloot-vX.Y.Z
   ```
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
