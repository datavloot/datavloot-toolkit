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
3. Push the branch and open a merge request against `main`. **`main` is protected — it cannot
   be pushed to directly, and the release must not be merged locally.** The tag in the next
   step has to point at the merge commit GitLab itself creates, which does not exist until the
   MR is accepted.
   ```bash
   git push origin feature/<name> \
     -o merge_request.create \
     -o merge_request.target=main \
     -o merge_request.title="Release X.Y.Z"
   ```
   Then accept the MR in the GitLab UI. (`glab mr create` does the same thing if the CLI is
   installed; the push options above need no extra tooling.)
4. Pull the resulting merge commit and tag it:
   ```bash
   git switch main
   git pull origin main
   git tag -a X.Y.Z -m "optimist dbt package X.Y.Z"
   git push origin X.Y.Z
   ```
5. Fast-forward the moving minor branch (patch release). **On a patch release this is
   automatic**: the `fast-forward-minor-branch` job in
   [`.gitlab-ci.yml`](../.gitlab-ci.yml) fires on any bare `X.Y.Z` tag push and advances
   `X.Y.x` for you. It needs `GITLAB_PUSH_TOKEN` set as a masked CI/CD variable with write
   access to protected branches; check the job succeeded, and if the variable is not
   configured yet, do it by hand:
   ```bash
   git branch -f 0.1.x 0.1.1
   git push origin 0.1.x --force-with-lease
   ```
   Or, on a minor/major bump, create the new branch instead and stop touching the old one:
   ```bash
   git branch 0.2.x 0.2.0
   git push origin 0.2.x
   # 0.1.x is now frozen — do not push to it again
   ```
6. On a minor or major bump, `revision:` in
   [`datavloot_platform/templates/scaffold/packages.yml`](../datavloot_platform/templates/scaffold/packages.yml)
   and
   [`datavloot_platform/templates/demo/packages.yml`](../datavloot_platform/templates/demo/packages.yml)
   must point at the new minor branch, so newly scaffolded projects get the new default. Make
   this edit on the **same feature branch as step 2**, not afterwards — it goes through the
   protected-branch MR like any other change, and doing it as a follow-up MR just widens the
   window described in the note below.

> **Ordering hazard.** Between the MR merging (step 3) and the branch push (step 5), the
> templates reference a ref that does not exist yet, so `dbt deps` in a freshly scaffolded
> project fails to resolve. Run steps 4 and 5 promptly after accepting the MR.
>
> **Protected refs.** GitLab protects tags and branches by pattern, separately from protected
> branches. If `git push origin X.Y.Z` or the `0.1.x` push is rejected, the ref pattern needs
> allowing under *Settings → Repository → Protected tags / Protected branches*, or someone with
> Maintainer rights has to push it.

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
3. Push the branch, open a merge request against `main`, and accept it in the GitLab UI —
   `main` is protected and cannot be pushed to directly. Same flow and same push options as
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
