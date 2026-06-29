# Datavloot — Backlog

Improvements deferred from implementation. Pick these up in future sessions.

---

## README

### Update dbt packages.yml git URL when repo is renamed

`README.md` line 332 contains a git reference used by `dbt deps`:
```yaml
- git: "https://gitlab.com/datavloot/optimist-toolkit.git"
```
When the GitLab repo is renamed (e.g. to `datavloot`), update this URL. Also update the same reference in any project templates that include a `packages.yml`.

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

### v1.1 — `optimist start` command

A single command that starts both Dagster and the Crows Nest together, so users don't need two terminals.

```
optimist start
```

Implementation: `cmd_start` in `cli.py` that spawns `dagster dev` as a subprocess, then starts the crowsnest server in the foreground. Forward Ctrl+C to both processes.

---

### v1.1 — Scaffold integration

`optimist new <path>` should include any Crows Nest config stub that new projects need (if any configuration beyond `profiles.yml` becomes necessary). Currently no config is needed — revisit when `optimist start` is added.

---

### v1.2 — Real-time run log streaming

Clicking a run ID in the Pipelines panel should open a log view for that run. Dagster exposes logs via the `logsForRun` GraphQL subscription. Either poll or stream via the backend.

---

### v1.2 — Trigger individual asset materializations

Beyond job-level runs, allow selecting and materializing individual Dagster assets from the Catalog panel (analogous to clicking "Materialize" in the Dagster UI).

---

### v1.1 — Align visual style with Datavloot brand

The current frontend uses a provisional green palette and DM Sans / JetBrains Mono fonts. The proper brand styles are at `C:\Users\aevan\git\datavloot-website\html\production\index.html`.

Key values to apply:
- Background: `#F6F0E2` (warm cream/parchment)
- Accent: `#2C80A5` (teal/blue)
- Warm/amber: `#D8A021`
- Wood brown: `#A96F4A`
- Navy: `#1a3a4a`
- Body font: **Geist** (not DM Sans)
- Mono font: **Geist Mono** (not JetBrains Mono)

The website's feature list already refers to the dashboard as "Crow's Nest cockpit" — this is the canonical name.

Implementation: update `tailwind.config.js` color tokens and `app/layout.js` font imports to match.

---

### Later — Authentication

Currently all endpoints are public — fine for localhost, but needed before exposing on a shared server or VM. Consider HTTP Basic Auth or a simple token header, configurable via `CROWSNEST_AUTH_TOKEN`.
