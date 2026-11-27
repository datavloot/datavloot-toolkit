# CLAUDE.md

Notes for coding agents working on this repository. The human docs are the source:
`CONTRIBUTING.md` (setup, test tiers, pull requests), `developer-instructions.md` (layout) and
`toolkit-developer-standards.md` (structure rules). This file is the short version; read the
section there when a task touches it.

## Where things live

- `datavloot_platform/cli.py`: `datavloot new | demo | update | start | launch | autostart | shortcut | open`, and `DBT_PACKAGE_VERSION`
- `remote.py`: installing a project from a tag (`new --from`) and `update`
- `storage.py`: how dbt, dlt, assets and notebooks attach the lake; `maintenance.py`, `extensions.py`
- `crowsnest/`: the dashboard. FastAPI server, plus a Next.js source in `crowsnest/frontend/` and
  its committed static export in `crowsnest/static/`, which is what is served and shipped
- `templates/scaffold/` (`datavloot new`) and `templates/demos/<name>/` (`datavloot demo --<name>`). A
  demo is an overlay: the scaffold, minus what its `demo.yml` removes, plus the demo's own files. Keep
  the `remove` lists and overlay files in step with scaffold changes
- `installers/`: the PowerShell and shell install scripts; `deploy/`: the Falcon (Compose, OpenTofu)
- The `optimist` dbt package (macros, modelling conventions, `data-instructions.md`) is another
  repository, dbt-datavloot-optimist. This repo only pins it (`DBT_PACKAGE_VERSION`).

## Tests

Use uv, not pip. Run the tier that matches what you changed; CI runs all of them on the pull
request, so do not run the slow tiers locally unless the task asks.

| You changed | Run |
|---|---|
| anything | `uv run --with pytest --with pyyaml python -m pytest tests/ -m "not slow and not package" -q` |
| `crowsnest/`, `remote.py`, `storage.py`, `extensions.py`, `maintenance.py`, installers | the file's tests with the web stack: `uv run --with pytest --with pyyaml --with "duckdb>=1.5,<2" --with fastapi --with httpx --with pytz --with uvicorn python -m pytest tests/<file> -q`. These tests `importorskip`: check they say passed, not skipped |
| `templates/`, `DBT_PACKAGE_VERSION` | `pytest -m slow` (network, minutes); usually CI's job |
| `pyproject.toml`, new files under `datavloot_platform/` | `uv run --with pytest --with pyyaml python -m pytest tests/test_packaging.py -q` |
| dependencies in `pyproject.toml` | `uv lock`, and commit `uv.lock` with it |

On Windows the fast tier takes minutes: run the test files you touched first, the tier once at the
end. Tests that shell out to bash can fail locally without a WSL distribution; CI decides.

## What gets a pull request sent back

- a version bump in `pyproject.toml`; `uv.lock` changes unrelated to a dependency you changed; a
  widened bound without the reason in the pull request (bounds policy: comments in `pyproject.toml`)
- frontend source changed without the rebuilt `crowsnest/static/` in the same commit
  (`npm run build` in `crowsnest/frontend/`, then copy `out/` over `static/`), or the reverse
- a scaffold change without the same change in the demo
- conventions copied into a template's `data-instructions.md`: they live in the dbt package
- example-specific code at the root of `datavloot_platform/` instead of inside its template
- committed `.duckdb`, `dist/`, `target/`, `dbt_packages/`, `.env`, or anything `.gitignore` lists
- a new tag or branch named `X.Y.x` or a bare `X.Y.Z`
- a new CLI command or dependency without an issue that agreed to it

## Style

- Commit subjects are short and imperative and say what the change does; no `feat:`-style prefixes.
  The body is for the why. `git log --oneline` shows the register.
- Code comments record why a bound, exclusion or workaround exists. Keep that habit; do not
  narrate what the code does.
- DRY: do not copy code to keep in sync elsewhere. When it is unclear where code should live, ask.
- One change per branch, off `main`. Rebase on `main`; do not merge `main` in.
- A pull request says what changed, why, which test tiers ran, and `Closes #<n>`.

## Working as an agent here

- Do not commit, push, open pull requests or touch issues unless your task says so: the
  maintainer approves those.
- Stay inside the issue. When the change grows past the files you expected, stop and report
  instead of building on.
- Windows paths: worktrees plus `node_modules` can pass the 260-character limit. Keep new paths short.
