# Crows Nest — backlog

Improvements deferred from the initial implementation. Pick these up in future sessions.

---

## v1.1 — Trigger pipeline runs from UI

The current Dagster integration is read-only (runs and jobs are fetched, not launched). Add a "Materialize" or "Run" button on the Pipelines panel that fires a Dagster GraphQL mutation.

Relevant mutation: `launchRun` / `launchPipelineExecution` in the Dagster GraphQL schema.
Backend: new POST endpoint in `routes/pipelines.py`.
Frontend: "Run" button per job row in `PipelinesPanel.js`, confirmation dialog before firing.

---

## v1.1 — `optimist start` command

A single command that starts both Dagster and the Crows Nest together, so users don't need two terminals.

```
optimist start
```

Implementation: `cmd_start` in `cli.py` that spawns `dagster dev` as a subprocess, then starts the crowsnest server in the foreground. Forward Ctrl+C to both processes.

---

## v1.1 — Scaffold integration

`optimist new <path>` should include any Crows Nest config stub that new projects need (if any configuration beyond `profiles.yml` becomes necessary). Currently no config is needed — revisit when `optimist start` is added.

---

## v1.2 — Real-time run log streaming

Clicking a run ID in the Pipelines panel should open a log view for that run. Dagster exposes logs via the `logsForRun` GraphQL subscription. Either poll or stream via the backend.

---

## v1.2 — Trigger individual asset materializations

Beyond job-level runs, allow selecting and materializing individual Dagster assets from the Catalog panel (analogous to clicking "Materialize" in the Dagster UI).

---

## v1.1 — Align visual style with Datavloot brand

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

## Later — Authentication

Currently all endpoints are public — fine for localhost, but needed before exposing on a shared server or VM. Consider HTTP Basic Auth or a simple token header, configurable via `CROWSNEST_AUTH_TOKEN`.
