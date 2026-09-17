# The Valk

The Valk is the second vessel: the same project, moved from one laptop to a small
team's server. It is built as a **client project on SRDP** (github.com/srdp-hub/srdp),
which supplies the reverse proxy, single sign-on, the Postgres that holds the
DuckLake catalog, and the Dagster process split. Datavloot supplies the project:
the dbt models and macros, dlt ingestion, Elementary, the Crows Nest, and the CLI
that ties the two together.

This document covers how it works and how to run it. The analysis behind the
choice to build on SRDP rather than beside it lives outside the repo
(`scaling-with-srdp.md`, 2026-09-17).

## The promise, and what makes it true

`datavloot.yml` has one key that matters:

```yaml
vessel: valk
```

Nothing in `models/`, `seeds/` or the Dagster assets changes between vessels.
Four things make that literally true, and they are the whole design:

| Concern | Optimist | Valk | Where the switch lives |
|---|---|---|---|
| dbt target | `dev`: `<project>.duckdb` | `valk`: `:memory:` with the DuckLake catalog attached | `profiles.yml`, written by `datavloot valk render`; selected with `DBT_TARGET=valk` |
| dbt database | the file's catalog name | the attached catalog alias `ducklake` | `+database: "{{ env_var('DATAVLOOT_DBT_DATABASE', '<project>') }}"` on models, seeds, Elementary and sources |
| dlt destination | `duckdb(<file>)` | `ducklake(postgres catalog, data path)` | `datavloot_platform.vessel.dlt_destination()` |
| plain DuckDB writes | `duckdb.connect(<file>)` | in-memory DuckDB with the catalog attached and selected | `datavloot_platform.vessel.connect()` |

All three writers (dbt, dlt, plain assets) and the one reader (Crows Nest) pass the
same three facts to DuckLake: the Postgres connection, the data path, and the
metadata schema. Those come from environment variables with **SRDP's own names**
(`DUCKLAKE_PG_HOST`, `DUCKLAKE_DATA_PATH`, ...), so a datavloot project also runs
unchanged inside SRDP's own reference container.

## What runs

```
                 https://crowsnest.<domain>   dagster.<domain>   marimo.<domain>   auth.<domain>
                            │                      │                 │                │
                     ┌──────▼──────────────────────▼─────────────────▼────────────────▼──────┐
                     │  Traefik  ── forwardauth ──▶  oauth2-proxy  ── OIDC ──▶  Zitadel       │  SRDP
                     └──────┬──────────────────────┬─────────────────┬──────────────────────┘
                            │                      │                 │
                     ┌──────▼──────┐      ┌────────▼────────┐  ┌─────▼─────┐
                     │ Crows Nest  │      │ Dagster webserver│  │  Marimo   │        SRDP compose,
                     │ (this image)│      │ + daemon (ours)  │  │ (SRDP)    │        our overlay
                     └──────┬──────┘      └────────┬────────┘  └───────────┘
                            │             gRPC     │
                            │           ┌──────────▼──────────┐
                            │           │ dagster-code         │  this project's image:
                            │           │ (this image)         │  dbt, dlt, datavloot, assets
                            │           └──────────┬──────────┘
                            │                      │
                     ┌──────▼──────────────────────▼──────┐   ┌──────────────────────────┐
                     │ Postgres: DuckLake catalog,        │   │ DuckLake data (Parquet)   │
                     │ Dagster state, Zitadel users       │   │ volume, or S3 bucket      │
                     └────────────────────────────────────┘   └──────────────────────────┘
```

Two compose files, layered: SRDP's `deploy/docker/docker-compose.yml` (checked out
at a pinned commit into `.srdp/`) and this project's rendered
`deploy/valk/docker-compose.valk.yml`. The overlay does three things and nothing
else: re-points every hostname at your domain (SRDP's file hardcodes a dev
domain), swaps in this project's images, and adds the Crows Nest behind the same
SSO gate as Marimo and Dagster.

## Running it

Prerequisites on the machine that runs the stack: Docker with Compose v2, git,
mkcert. On your laptop for a real domain: DNS A records for the five hostnames.

```bash
pip install "datavloot[valk]"
cd my-project
# edit datavloot.yml: vessel: valk, fill in the valk: block (domain at minimum)
datavloot valk render          # writes deploy/valk/, adds the dbt target, creates .env once
datavloot valk fetch           # SRDP at the pinned commit -> .srdp/
datavloot valk certs           # mkcert certificates for *.<domain>
datavloot valk up              # docker compose up -d --build
```

Then the one-time Zitadel step in `deploy/valk/README.md`: create the OIDC
application, paste its client id and secret into `deploy/valk/.env`, run
`datavloot valk up` again. `datavloot valk up --prod` adds SRDP's Let's Encrypt
override and needs `ACME_EMAIL` in `.env`.

Day to day: `datavloot valk compose logs -f crowsnest`, `datavloot valk compose ps`,
`datavloot valk down`. Materialize from the Dagster UI or with
`datavloot valk compose exec dagster-code dagster asset materialize -m <module> --select "*"`.

### Existing projects

Projects scaffolded before this release need two edits, or dbt builds into the
in-memory database on the Valk and the Crows Nest sees nothing:

1. `dbt_project.yml`: add `+database: "{{ env_var('DATAVLOOT_DBT_DATABASE', '<project>') }}"`
   under `models: <project>:`, `models: elementary:` and `seeds: <project>:`.
2. Every `_sources.yml`: add `database: "{{ env_var('DATAVLOOT_DBT_DATABASE', '<project>') }}"`.

Plain assets that call `duckdb.connect(DB_PATH)` should call
`datavloot_platform.vessel.connect(PROJECT_DIR, DB_PATH)` instead, and dlt
pipelines should take their destination from `vessel.dlt_destination()`.
`datavloot valk render` warns about the first two; it cannot see the third.

## Access

Authentication is SRDP's: Traefik asks oauth2-proxy, oauth2-proxy sends the
browser to Zitadel, one cookie covers every hostname. The Crows Nest does **not**
trust the `X-Auth-Request-*` headers that come out of that flow. Any container on
the internal network could send them. It validates the access token itself on
every request (SRDP's ADR-0008 rule), then reads roles from it.

| Role (SRDP ADR-0005 names) | Can |
|---|---|
| `reader` | browse the catalog, quality results and run history; run read-only SQL |
| `writer` | reader, plus anything that changes state: trigger runs, start or stop notebooks |
| `admin` | writer; reserved for a settings surface that does not exist yet |

Roles are Zitadel project roles with exactly those names. A signed-in user without
one gets `valk.access.default_role` (`reader` by default; `none` to deny). The
Zitadel switches that make this fast are in `deploy/valk/README.md` step 3:
without them the access token is opaque and the Crows Nest asks Zitadel's userinfo
endpoint who it belongs to (cached one minute per token).

For the Optimist on a VM, `CROWSNEST_AUTH_TOKEN` still works as before. When an
issuer is configured it is ignored, so one deployment never has two password
prompts.

## What is pinned, and how to move it

`valk.srdp.ref` in `datavloot.yml` (default in `datavloot_platform/vessel.py`) is
the SRDP commit the overlay is rendered against. The overlay depends on that
commit's service names, network names, container names and Traefik label keys.
Moving the pin is deliberate work: diff SRDP's `deploy/docker/` between the two
commits, adjust the templates under `datavloot_platform/valk/templates/`, run
`tests/test_valk_render.py`. Their PR #51 (open) changes the dev domain, the
Postgres password handling and adds services; it will be the first bump.

The Dagster webserver and daemon are rebuilt from `deploy/valk/Dockerfile.dagster`
on the Dagster version this toolkit pins, rather than taken from SRDP's lockfile,
because the code server and webserver talk gRPC and Dagster only promises that
between matching versions.

## Known gaps

Honest list, as of the first render. None of these has been exercised end to end;
the pilot in `scaling-with-srdp.md` step 1 is where they get closed.

- **Not run against a live stack yet.** Rendering, config discovery, the ATTACH
  statements, dlt destination construction and token validation are unit-tested.
  `docker compose up` with SRDP's stack has not been executed from this branch.
- **Postgres password is SRDP's hardcoded default.** At the pinned commit their
  compose sets `POSTGRES_PASSWORD: postgres` and `dagster_pw` literally. The overlay
  reads `.env` for both so a later pin that parametrizes them (PR #51 does) works,
  but today changing them in `.env` alone does nothing.
- **First-boot Zitadel client is manual.** SRDP issue #35 and PR #36 track
  automating it. Until then it is five clicks and a paste, documented in the
  rendered README.
- **S3 hardening is weaker than local.** With data on a bucket the Crows Nest's
  DuckDB connection must keep network access for httpfs, so `enable_external_access`
  stays on (the local filesystem stays closed and the configuration stays locked).
  A query can read any object the attached S3 secret can, which is the same bucket
  the catalog serves. Documented in `crowsnest/db.py`.
- **Role scope name.** The overlay asks Zitadel for `urn:zitadel:iam:org:projects:roles`.
  Verify against the Zitadel version SRDP pins that this scope, plus "assert roles
  on authentication", puts the roles claim in the token. If not, everything still
  works through the userinfo fallback, only slower.
- **SRDP is Python 3.12 only** (their pyproject pins `<3.13`). The project image is
  built on 3.12 regardless of the Python on the laptop.
- **One code location per stack.** SRDP's compose names the code server
  `srdp-dagster-code` and their workspace points at it; the Valk runs one project.
  Several projects on one stack is a Catamaran question.
- **Marimo notebooks are SRDP's.** The Notebooks panel embeds `marimo.<domain>`,
  which serves SRDP's `services/marimo/notebooks/app.py`, not this project's
  `notebooks/`. Mounting the project's notebooks into that service is a small
  overlay change once the pilot shows the rest works.
- **No `datavloot upgrade` yet.** Copying an existing `.duckdb` into the catalog is
  still a manual `ATTACH` + `CREATE TABLE AS`.

## Files

| Path | What |
|---|---|
| `datavloot_platform/vessel.py` | `datavloot.yml` loader; `connect()`, `dlt_destination()`, `attach_ducklake()`; the SRDP pin |
| `datavloot_platform/valk/render.py` | writes `deploy/valk/`, the dbt target, `.gitignore` entries |
| `datavloot_platform/valk/commands.py` | `fetch`, `certs`, `up`, `down`, `compose` |
| `datavloot_platform/valk/templates/` | the overlay, Dockerfiles, entrypoint, Traefik config, env, runbook |
| `datavloot_platform/crowsnest/auth.py` | token mode and OIDC mode |
| `datavloot_platform/crowsnest/config.py` | vessel and `attach:` discovery |
| `datavloot_platform/crowsnest/db.py` | DuckLake connections, remote-aware hardening |
| `tests/test_vessel.py`, `test_valk_render.py`, `test_crowsnest_oidc.py`, `test_crowsnest_ducklake.py` | the unit tests |
