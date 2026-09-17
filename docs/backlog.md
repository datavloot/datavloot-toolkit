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

### Automate the moving-branch fast-forward

Step 5 of the dbt package release in [`releasing.md`](releasing.md) — fast-forwarding `X.Y.x` to
the new tag — is manual, and skipping it fails silently: the tag exists, the release looks
shipped, and every consumer tracking `X.Y.x` stays on the previous version indefinitely. No
warning is emitted on either side, since dbt only warns about unpinned revisions for the literal
strings `HEAD`, `main`, and `master`.

Replace it with a GitLab CI job triggered on pushing a tag matching `X.Y.Z`, which fast-forwards
the corresponding `X.Y.x` branch to that tag. Needs a token with write access to protected
branches (a project access token or CI/CD variable), and `rules:` gated on
`$CI_COMMIT_TAG =~ /^\d+\.\d+\.\d+$/` so it never fires on the `datavloot-v*` PyPI tag series.

Documentation is the current mitigation, which is why this is worth doing properly — the failure
mode is invisible rather than noisy.

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

### Authentication — two modes exist, the frontend knows about neither

Token mode (`CROWSNEST_AUTH_TOKEN`) shipped for the Optimist-on-a-VM case. OIDC mode
(`CROWSNEST_OIDC_ISSUER`, branch `feature/evka_valk_vessel`) validates Zitadel tokens for the Valk and
exposes the caller's role at `/api/me`. What is still missing is on the frontend side:

- Show who is signed in and with which role (from `/api/me`), and hide or disable write actions
  (the v1.1 "Run" button, notebook launch/stop) for `reader`s instead of letting them hit a 403.
- On a 401 in OIDC mode the browser should be sent to `/oauth2/sign_in` (the oauth2-proxy login),
  not shown a JSON error; in token mode the native Basic prompt stays.

---

### Multi-user readiness — Notebooks panel has no per-user isolation

Found during fase 0 of the Optimist multi-reader VM test (`draaiboek-optimist-vm-test.md`, 2026-09-11): the
Notebooks panel's backend state is entirely global, which breaks as soon as a second person uses the
same Crows Nest instance.

- `_marimo_process` in [`routes/notebooks.py`](../datavloot_platform/crowsnest/routes/notebooks.py) is a single
  module-level variable. Launching a notebook while another is running silently kills the first one
  (`launch_notebook` calls `.kill()` on the existing process before starting a new one).
- `stop_notebook()` also calls `_kill_port(2718)`, which kills *whatever* process is listening on that
  port — not just the one this session started. One user's "Close notebook" click stops the notebook
  everyone else is looking at.
- No concept of a session or user in the notebook launch/stop flow at all.

Fix needs a per-session (or per-user) registry of Marimo processes and ports instead of one global
variable, plus scoping "close" to the caller's own session. Until then, multi-user deployments should
run Marimo as an independent service outside the Crows Nest's own launch/stop machinery (which is what
the VM test's draaiboek does as a workaround).

---

### Multi-user readiness — Marimo iframe URL is resolved client-side

Also found in fase 0 of the same VM test. The Notebooks panel embeds Marimo via
`<iframe src={marimoUrl}>` ([`NotebooksPanel.js`](../datavloot_platform/crowsnest/frontend/components/NotebooksPanel.js)),
where `marimoUrl` comes from `CROWSNEST_MARIMO_URL` (default `http://127.0.0.1:2718`, see
[`config.py`](../datavloot_platform/crowsnest/config.py)). This address is loaded and resolved by the
*browser*, not the server. On a shared VM/server deployment, the default silently points every
visitor's browser at their own laptop instead of the server, unless an operator manually reverse-proxies
Marimo through its own subdomain/port and sets `CROWSNEST_MARIMO_URL` accordingly.

Consider either documenting this prominently for server deployments, or making the Crows Nest backend
proxy the iframe traffic itself (so the browser only ever talks to the Crows Nest's own origin) rather
than relying on the client resolving a second address directly.

On the Valk both findings are sidestepped rather than fixed: Marimo runs as SRDP's own service and the
panel embeds `https://marimo.<domain>` (set through `CROWSNEST_MARIMO_URL` by the Compose overlay). The
fix above is still needed for the Optimist-on-a-VM case.

---

## Valk

Branch `feature/evka_valk_vessel` (2026-09-17) implements `vessel: valk`: the same project deployed as a
client project on an SRDP Compose stack (github.com/srdp-hub/srdp, pinned to commit `896ceea8`). Design
and the honest list of gaps: [`docs/valk.md`](valk.md). Background analysis (outside the repo):
`Documents/datavloot docs/scaling-with-srdp.md`.

Everything below is ordered: the pilot first, because nothing under it is worth doing if the pilot fails.

### Pilot — bring the stack up for the first time

The branch is unit-tested (render, config discovery, ATTACH statements, dlt destination, token
validation, a real local DuckLake through the query route) but `docker compose up` against SRDP's real
stack has never run: the machine the branch was written on has no Docker. Do this on a Linux box or VM
(Hetzner, Ubuntu 24.04, 16 GB — the 11 September draaiboek machine is fine), with the NOAA demo:

1. `pip install "datavloot[valk] @ git+https://gitlab.com/datavloot/datavloot-toolkit.git@feature/evka_valk_vessel"`,
   `datavloot demo`, set `vessel: valk` with `domain: noaa.valk.localhost` in `datavloot.yml`.
2. `datavloot valk render --datavloot-source git+https://gitlab.com/datavloot/datavloot-toolkit.git@feature/evka_valk_vessel`
   (the image must install the branch, not PyPI 0.1.2). Check `deploy/valk/` reads sensibly.
3. `datavloot valk fetch && datavloot valk certs && datavloot valk up`. Expect the first image build to
   take several minutes (`dbt deps` runs inside it). Record every step that is missing from
   `deploy/valk/README.md` and `docs/valk.md` **immediately** (see `feedback_readme_testing.md`).
4. Zitadel first boot: create the OIDC app, roles `reader`/`writer`/`admin`, paste client id/secret
   into `deploy/valk/.env`, `datavloot valk up` again. Log in once; confirm the cookie covers
   `crowsnest.`, `dagster.`, `marimo.` and `quarto.` without a second login.
5. Copy `data/guam_2025.csv` into the project before building, materialize everything from
   `dagster.<domain>`. Confirm in the Crows Nest catalog: `noaa.business.dim_vessel`,
   `noaa.business.fct_port_event`, `noaa.business_elementary.*`, `noaa.source.guam_atmo_hourly` (dlt).
6. Run the Query panel as a `reader`, try to POST to `/api/pipelines/...` as a `reader` (expect 403),
   as a `writer` (expect past auth). Check `/api/me`.
7. Two browsers, two users, at the same time: SQL editor plus a materialization. This is Thijs's #8
   (DuckDB concurrency) answered for real; no serving-copy workaround should be needed.
8. `sudo reboot`; everything comes back (`restart: unless-stopped` on ours, SRDP's policies on theirs)
   and Dagster history survives (it is in Postgres, not in a container).

Expected breakages, each a small fix on the branch once observed:

- The overlay overrides `command`, `labels` and `environment` on SRDP's services. If Compose merges
  any of them differently than assumed (labels are expected to merge by key, `command` to replace),
  the first symptom is a 404 from Traefik or oauth2-proxy refusing the redirect.
- `dbt parse` in the entrypoint runs before Postgres has the `ducklake` database; the entrypoint
  creates it first, but the retry loop has only been reasoned about.
- `CREATE OR REPLACE TABLE` on a DuckLake catalog (the demo's CSV asset). If DuckLake refuses it,
  switch the asset to `DROP TABLE IF EXISTS` + `CREATE TABLE`.
- Elementary's `on-run-end` hooks writing to the target database (`memory`) instead of the attached
  catalog despite `+database` on its models. If so, Elementary needs its own database config or
  is disabled on the Valk.
- `is_ducklake: true` on the dbt attach makes dbt-duckdb emit DuckLake-safe DDL; confirm incremental
  models (the demo's `ais` layer) and `unique_key` merges work on DuckLake. dlt's docs say dbt on
  DuckLake is "not implemented" on *their* side; dbt-duckdb attaches on its own, so this should be
  unaffected, but it has not been run.

### Verify — assumptions written into the branch

- **Zitadel roles scope.** The overlay requests `urn:zitadel:iam:org:projects:roles` and the runbook
  tells the operator to tick "assert roles on authentication" and set the token type to JWT. Confirm
  against the Zitadel version SRDP pins (v4.2.2 in Compose) that the roles claim then appears in the
  *access* token. If it only appears in the id token, the Crows Nest falls back to userinfo on every
  request (works, slower, one-minute cache). The fix would then be to have oauth2-proxy forward the
  id token instead; reading the forwarded `X-Auth-Request-*` headers is never the answer (ADR-0008).
- **oauth2-proxy `--pass-access-token` + Traefik `authResponseHeaders`.** The token must arrive as
  `X-Auth-Request-Access-Token`; the overlay adds it to the header list. Confirm the header reaches the
  Crows Nest container (Traefik must forward it, not strip it).
- **Postgres credentials.** At the pinned SRDP commit the Postgres password and the Dagster DB password
  are literals in *their* compose file. The overlay reads `POSTGRES_PASSWORD` and `DAGSTER_PG_PASSWORD`
  from `.env` for *our* containers; both must stay equal to SRDP's literals until the pin moves. Verify
  the code server can reach Postgres with them.
- **Compose `x-` anchors and `<<:` merge keys** in the overlay: Compose v2 supports both; Compose v1
  does not. Document the minimum Compose version.
- **S3 storage path** (`storage.kind: s3`): not exercised at all. Test against Scaleway Object Storage
  or Hetzner Object Storage: DuckDB `CREATE SECRET` with `ENDPOINT` + `URL_STYLE 'path'`, dbt-duckdb
  `secrets:`, and dlt's `FilesystemConfiguration` with `AwsCredentials(endpoint_url=...)`. Then re-check
  the weaker Crows Nest hardening on remote data (`enable_external_access` stays on; see `db.py`).
- **Dagster version alignment.** The webserver/daemon image is built on the toolkit's Dagster pin
  (1.13.x); SRDP's lockfile has 1.12.17. The overlay avoids the skew by building both sides ourselves.
  Confirm the gRPC handshake and that `dagster api grpc-health-check` exists in that version.
- **`datavloot launch` inside a container with `DAGSTER_HOME` set but no `dagster.yaml` copied for the
  Crows Nest image role**: it does not need one; confirm it does not warn.

### Follow-ups — after the pilot passes

- **Move the SRDP pin to PR #51** once it merges (adds dbt extra, `srdp.api`, hub page, DuckDB UI,
  Marquez; changes the dev domain to `srdp.localhost` and parametrizes Postgres passwords). Diff their
  `deploy/docker/` between the two commits, adjust `datavloot_platform/valk/templates/`, re-run
  `tests/test_valk_render.py`. Re-evaluate the overlay: several overrides (domain, passwords) may
  become unnecessary.
- **Trigger runs via `srdp.api`** instead of Dagster GraphQL once their API merges (their exposed
  Dagster UI is `--read-only` in prod, ADR-0005). Until then the Crows Nest backend is the writer-gated
  path; the v1.1 "Run" button above must go through it.
- **Mount the project's `notebooks/` into SRDP's Marimo service** so `marimo.<domain>` shows this
  project's notebooks, not SRDP's example app. Small overlay change (volume + command).
- **`datavloot upgrade`**: copy a local `.duckdb` (schemas `source`, `business`, `seeds`,
  `*_elementary`) into the DuckLake catalog. Today it is a manual `ATTACH` + `CREATE TABLE AS`.
- **Hetzner (or Scaleway Instances) provisioning** for the VM: SRDP only ships OpenTofu for GCP
  Compute Engine, which fails the CLOUD Act test on `waarom.html`. Port their `deploy/opentofu/gcp/`
  (cloud-init that installs Docker, clones, runs compose) and offer it upstream.
- **Backups on Compose.** SRDP's Helm chart has a nightly `pg_dump` CronJob; their Compose stack has
  none. Add a `datavloot valk backup` (or a documented cron) covering the Postgres volume and the
  DuckLake data path.
- **Existing-project migration helper.** `datavloot valk render` warns when `dbt_project.yml` or a
  `_sources.yml` lacks the `DATAVLOOT_DBT_DATABASE` env var. Offer to apply the edit instead of only
  warning; it is a mechanical YAML change.
- **`data-instructions.md`** (scaffold and demo) still tells the AI assistant to use `duckdb.connect`
  and dlt's duckdb destination directly. Point it at `vessel.connect()` / `vessel.dlt_destination()`
  so generated code stays vessel-agnostic.
- **Multiple projects on one stack.** SRDP's compose names one code server (`srdp-dagster-code`) and
  their workspace points at it. Several projects = several code servers + a workspace with several
  entries. Catamaran scope; note it in `docs/valk.md` (done) and leave it.
- **Python 3.12 only inside the images** because SRDP pins `<3.13`. Ask them why; lift when they do.
- **Release.** `datavloot 0.2.0` on PyPI with the `valk` extra, so `deploy/valk/Dockerfile` can install
  from PyPI instead of the git branch. Follow `docs/releasing.md`.

### CI

- `.github/workflows/ci.yml` (branch `feature/evka_github_actions_ci`) and `.gitlab-ci.yml` do not know
  the new tests. The `crowsnest` job needs `--with "pyjwt[crypto]"` and should run
  `tests/test_crowsnest_oidc.py` and `tests/test_crowsnest_ducklake.py`; the `lint` job picks up
  `tests/test_vessel.py` and `tests/test_valk_render.py` automatically but `test_vessel.py`'s dlt test
  needs `--with "dlt[ducklake]"` or it skips.
- The slow DuckLake test (`test_query_route_reads_a_local_ducklake`, marker `slow`) downloads the
  extension; add it to the smoke job, which already has network.
- A render smoke in CI: `datavloot new`, set `vessel: valk`, `datavloot valk render`, then
  `docker compose config` on SRDP's compose plus the overlay (needs the SRDP checkout and Docker on the
  runner; `ubuntu-latest` has both). This is the cheapest check that the overlay still matches the pin.

### Upstream to SRDP — offers, in order

Each removes a reason for them to build a competing piece, and each is small.

1. Tests for `src/srdp/io/ducklake.py` (`create_connection` against a Postgres container); they have
   `pytest` configured and no `tests/` directory.
2. An S3 `StorageBackend` (their ADR-0003 says "optional via extras"; no class exists).
3. A Hetzner/Scaleway-Instances OpenTofu target next to GCP.
4. Zitadel OIDC application provisioning (their #35 / PR #36 stalled since July); the Valk needs it
   more than they do.
5. Amend ADR-0003's "IO manager is the single write path" to "every write lands in the DuckLake
   catalog", which dbt and dlt satisfy; their own PR #51 already lets dbt write directly.
6. Co-design `srdp.toml` (#42) so `datavloot.yml` can generate it.

### Website and docs

- `scaling-to-valk.md` (outside the repo) still says Valk Q1 2027 and lists a Kennisplatform; the live
  vaarroute says Valk Q4 2026, Catamaran Q2 2027. Sync it, and decide whether it stays as the
  build-own fallback or is retired once the pilot passes.
- `datavloot.nl/vaarroute`: once the pilot passes, the Valk card can say "op SRDP" and link the
  runbook; until then nothing on the site should claim the Valk runs.
