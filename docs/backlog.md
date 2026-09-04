# Datavloot — Backlog

Improvements deferred from implementation. Pick these up in future sessions.

---

## Website

### Update install commands to `pip install datavloot[optimist]`

The PyPI package has been renamed from `datavloot-optimist` to `datavloot` with vessel-based extras.
Every occurrence of `pip install datavloot-optimist` in `html/production/index.html` needs to become `pip install datavloot[optimist]`.

Locations in `index.html`:
- Line 432 — hero install command snippet (inside `.hero-code`)
- Line 502 — terminal block step 1 comment
- Line 503 — terminal block `pip install` command line

---

## Release process

### Finish wiring the moving-branch fast-forward

The CI job exists — `fast-forward-minor-branch` in [`.gitlab-ci.yml`](../.gitlab-ci.yml), gated on
`$CI_COMMIT_TAG =~ /^\d+\.\d+\.\d+$/` so the `datavloot-v*` PyPI series never triggers it.

What is left is operational: create a project access token with write access to protected branches,
expose it as the masked CI/CD variable `GITLAB_PUSH_TOKEN`, and prove the job works by pushing a
throwaway tag before relying on it for a real release. Until that variable exists the job will fail
on every tag push, and `releasing.md` step 5 still has the manual commands as a fallback.

---

## Crow's Nest

### v1.1 — Trigger pipeline runs from UI

The current Dagster integration is read-only (runs and jobs are fetched, not launched). Add a "Materialize" or "Run" button on the Pipelines panel that fires a Dagster GraphQL mutation.

Relevant mutation: `launchRun` / `launchPipelineExecution` in the Dagster GraphQL schema.
Backend: new POST endpoint in `routes/pipelines.py`.
Frontend: "Run" button per job row in `PipelinesPanel.js`, confirmation dialog before firing.

---

### v1.1 — Scaffold integration

`datavloot new <path>` should include any Crows Nest config stub that new projects need (if any configuration beyond `profiles.yml` becomes necessary). Currently no config is needed — revisit when `datavloot start` is added.

---

### v1.2 — Real-time run log streaming

Clicking a run ID in the Pipelines panel should open a log view for that run. Dagster exposes logs via the `logsForRun` GraphQL subscription. Either poll or stream via the backend.

---

### v1.2 — Trigger individual asset materializations

Beyond job-level runs, allow selecting and materializing individual Dagster assets from the Catalog panel (analogous to clicking "Materialize" in the Dagster UI).


---

### Notebook lifecycle — orphaned marimo process and a hard-coded port

Launching a notebook starts marimo with `subprocess.Popen`, and stopping it calls
`_marimo_process.kill()` ([`routes/notebooks.py:85`](../datavloot_platform/crowsnest/routes/notebooks.py),
again at `:123`), which signals only the launcher. Any children it spawned are orphaned and keep
holding the port, so the fallback is `_kill_port(2718)` — scanning for whatever is listening and
killing it, which is a blunt instrument that will happily kill an unrelated process.

This is the same problem `datavloot start` already solved for Dagster.
[`cli.py:217 _terminate_tree()`](../datavloot_platform/cli.py) walks the whole tree
(`taskkill /F /T` on Windows, `killpg` on POSIX) and is the pattern to reuse here.

Port 2718 is hard-coded in four places (`:89`, `:111`, `:114`, `:127`) even though the Crows Nest
already has a configured marimo URL — `config.marimo_url`, overridable via `CROWSNEST_MARIMO_URL`
and documented in the README. `notebooks.py` does not import the config at all. Two notebooks on
one machine, or anything else already on 2718, currently has no way out.

---

## Demo

### Demo uses the deprecated `dagster-dlt` translator API

`OpenMeteoDltTranslator` in
[`templates/demo/noaa_platform/assets.py`](../datavloot_platform/templates/demo/noaa_platform/assets.py)
overrides `get_asset_key(resource)`. The scaffold's commented example has already moved to the
current API; the demo has not, so the reference project teaches the older form. Worth doing before
the deprecation becomes a removal, since the demo is what people copy.

---

### Demo requires a manual browser download before it runs

`datavloot demo` prints step 4 as: download the Guam 2025 AIS zone file from a NOAA Marine Cadastre
index page and save it as `data/guam_2025.csv` ([`cli.py:89`](../datavloot_platform/cli.py)). The
link is an HTML index, not a file, so it cannot be scripted as-is — the user has to find the right
zone file by hand before anything works.

Options: resolve the file URL and fetch it in the dlt ingestion asset, or ship a small sample
extract in the template so the demo runs end to end out of the box and the full download becomes
optional. The second keeps the repository small and makes the first run reliable.

---

### AIS vessel and status codes are exposed raw

`dim_vessel.vessel_type` carries the numeric AIS category code, documented as
"e.g. 52 = Tug, 70 = Cargo, 80 = Tanker"
([`_dim_configs.yml:146`](../datavloot_platform/templates/demo/models/business/dimensions/_dim_configs.yml)),
and `status` carries the raw navigational status code. Anyone querying the demo has to keep the
mapping in their head or go back to the docs.

The demo already demonstrates the fix for exactly this shape of problem: `sea_state_categories.csv`
is a seed that turns a raw measurement into a label via a range join. A `vessel_types.csv` seed and
a `dim_vessel_type` would make the star schema self-describing and show the pattern twice.

---

## Installation

### Dependencies still need a C compiler

[`README.md:37`](../README.md) lists a C compiler as a prerequisite, with per-OS instructions for
MSVC, Xcode command line tools and GCC. That is honest documentation of a real requirement, but it
is a substantial ask for a toolkit whose pitch is that it runs on a laptop — on Windows especially,
"install Visual C++ Build Tools" is where a first-time user stops.

Worth identifying which dependency actually forces a source build on a supported Python, and whether
a version bound or a swap removes the need. If it can be dropped, the prerequisites section gets
much shorter.
