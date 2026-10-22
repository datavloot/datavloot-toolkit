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

### Later — Authentication

Currently all endpoints are public — fine for localhost, but needed before exposing on a shared server or VM. Consider HTTP Basic Auth or a simple token header, configurable via `CROWSNEST_AUTH_TOKEN`.
