# Valk implementation plan

Status: 2026-10-12. Branch `feature/evka_valk_vessel`, after merging `main` (up to
`ff691ce`, #37). Target: the Valk running on SRDP `main` once
[srdp-hub/srdp#115](https://github.com/srdp-hub/srdp/pull/115) (configurable domain)
is merged.

Ground rules, from the brief:

- Moving a project from the Optimist to the Valk is a configuration change:
  `vessel: valk` plus `valk.domain` in `datavloot.yml`, then the `datavloot valk`
  commands. No edits to models, seeds, assets or notebooks.
- Minimal changes. Nothing is built that the Valk does not need today.
- Zitadel holds the three SRDP access roles (`reader`, `writer`, `admin`, ADR-0005).
- Where datavloot has no standard of its own, SRDP's applies: its environment
  variable names, its compose files unmodified, its ADRs.

## Where things stand after the merge

Main gained two things that overlap with this branch:

- **#33, DuckLake for the Optimist.** Every project now keeps its data in `lake/`
  (SQLite catalog plus Parquet), attached **under the project name**.
  `datavloot_platform/storage.py` is the one module that knows how to attach it;
  templates call `storage.connect()` and `storage.dlt_destination()`.
- **#34, dev and prod writes.** `dbt` by hand builds the `dev` target into `dev_*`
  schemas; Dagster builds `prod`, set in the templates as
  `DbtProject(target="prod")`. Writers to the lake share a Dagster pool limited to
  one at a time.

That makes most of this branch's own switching mechanism redundant: the
`DATAVLOOT_DBT_DATABASE` override, the extra `valk` dbt target,
`vessel.connect()` and `vessel.dlt_destination()`. The merge resolved every
conflict in favour of main's design and kept the parts of the Valk that do not
depend on it (the `datavloot valk` commands, the overlay, OIDC in the Crows Nest).

**What does not work right after the merge.** These come from main's design
winning, not from a regression in main:

1. On the Valk, Dagster builds the `prod` target, which in the project's own
   `profiles.yml` is the SQLite lake inside the container. dbt writes there, not to
   the shared Postgres catalog. The `valk` target that `datavloot valk render`
   adds is no longer used by anything.
2. dlt and plain assets call `storage.*`, which only knows the SQLite lake.
3. The Valk attaches its catalog as `ducklake`; main's sources and models expect
   the project name. `tests/test_valk_render.py::test_render_writes_the_whole_deploy_dir`
   is marked `xfail(strict=True)` for this until step 1 lands.

The Crows Nest is fine: its Valk mode attaches the Postgres catalog itself, and now
uses main's `allowed_directories` hardening for a local data volume. The old
hardening disabled the local file system outright, which #33 found stops a
DuckLake from reading its Parquet at all.

## Step 1: one storage module, two catalogs

The Valk becomes "the same lake, with its catalog in Postgres instead of SQLite".
Everything else, including the alias, schema names and targets, stays identical.

| | Optimist | Valk |
|---|---|---|
| Catalog | `ducklake:sqlite:lake/catalog.sqlite` | `ducklake:postgres:` from `DUCKLAKE_PG_*` |
| Data path | `lake/data/` | `DUCKLAKE_DATA_PATH` (`/data/ducklake` or `s3://...`) |
| Alias | project name | project name |
| Attach options | `META_JOURNAL_MODE 'WAL'` | `METADATA_SCHEMA 'ducklake_<project>'` |
| dbt targets | `dev`, `prod` in the project's `profiles.yml` | the same names, in `deploy/valk/profiles.yml`, copied over `/app/profiles.yml` in the image |

Changes:

1. **`storage.py`** decides the catalog from the environment: with
   `DATAVLOOT_VESSEL=valk` (set by the overlay), `connect()`, `create()` and
   `dlt_destination()` attach the Postgres catalog with SRDP's variable names.
   Move the needed parts of `vessel.py` here (`catalog_attach_string`,
   `metadata_schema`, the S3 secret) and delete `vessel.connect`,
   `vessel.dlt_destination` and `vessel.attach_ducklake`. `vessel.py` keeps only
   the `datavloot.yml` loader and the SRDP pin. Coordinate with Stan: `storage.py`
   is his module from #33.
2. **dbt profiles.** `datavloot valk render` stops editing the project's
   `profiles.yml` (`_update_profiles` goes) and writes `deploy/valk/profiles.yml`
   with `dev` and `prod` outputs on the Postgres catalog, both with `alias` =
   project name. `deploy/valk/Dockerfile` copies it to `/app/profiles.yml`.
   Reason: `DbtProject` passes `--profiles-dir <project dir>` explicitly
   (checked in `dagster_dbt/dbt_project.py`), so `DBT_PROFILES_DIR` cannot point
   dbt elsewhere. Drop `DBT_TARGET=valk` from the Dockerfile, the entrypoint and
   the overlay.
3. **Alias.** Delete `valk.catalog.alias` and `DEFAULT_CATALOG_ALIAS`; the alias is
   the project name everywhere.
4. **Templates.** Remove the `+database: "{{ env_var('DATAVLOOT_DBT_DATABASE', ...) }}"`
   lines from both `dbt_project.yml` templates and the demo's `_sources.yml` files,
   and the matching check from `render._check_project_wiring`. Main's templates
   already name the database by the project name.
5. **Dagster pools.** `deploy/valk/dagster/dagster.yaml` gets main's
   `concurrency.pools` block (`default_limit: 1`, `granularity: op`), so the
   `lake` pool means the same thing on both vessels. Keep
   `max_concurrent_runs: 1`.
6. **Crows Nest.** Its Valk branch in `crowsnest/db.py` calls `storage.connect()`
   like the lake branch does, then hardens with `allowed_directories` (local) or
   `_HARDENING_REMOTE` (S3).

Tests: `test_vessel.py` loses the connect and destination tests, which move to
`test_storage.py` as Valk cases (attach string, alias, metadata schema, S3
secret). `test_valk_render.py` checks `deploy/valk/profiles.yml` and loses the
`xfail`.

Done when: the full test tier passes, and in a scaffolded project the only diff
between the two vessels is `datavloot.yml` plus the generated `deploy/valk/`.

## Step 2: SRDP pin to main after #115

Set `SRDP_REF` in `vessel.py` to the merge commit of #115. That brings in 125
commits since our current pin (`896ceea`, 2026-09-04). These are the ones that touch
the overlay:

| SRDP change | Effect on us |
|---|---|
| Routing moved from Docker labels to `config/traefik/dynamic/srdp.yml`; Traefik has no Docker provider | Every `labels:` block in our overlay is dead |
| `quarto` service removed | Our `quarto:` block breaks `docker compose` |
| Hostnames come from `SRDP_DOMAIN` (#115) | Our domain rewriting is unnecessary |
| `X-Auth-Request-Access-Token` forwarded upstream | Our `zitadel-auth` middleware override is unnecessary |
| Passwords required, no defaults; `srdp-setup` creates the databases from `srdp.toml` | `.env` must generate them |
| Prod is `docker-compose.yml` + `docker-compose.prod.yml`, without the override | `--prod` must stop loading the override |
| `dagster-webserver` has an `image:` on ghcr | Our build would be tagged as SRDP's image |

Changes:

1. **`docker-compose.valk.yml.tmpl`.** Delete the `traefik`, `zitadel-init`,
   `zitadel`, `zitadel-login` and `oauth2-proxy` blocks; the label blocks on
   `dagster-webserver`, `marimo` and `quarto`; and the `ducklake-data` volume
   definition (SRDP defines it at the same `/data/ducklake`). Add
   `image: valk-dagster-webserver` to `dagster-webserver` and `dagster-daemon`.
   Make `POSTGRES_PASSWORD` and `DAGSTER_PG_PASSWORD` required (no `:-default`).
   Replace the Crows Nest's labels with one Traefik volume:
   `@@valk_dir/traefik-crowsnest.yml:/etc/traefik/dynamic/crowsnest.yml:ro`.
2. **`traefik-crowsnest.yml.tmpl`** (new) replaces `traefik.yml.tmpl`: a
   `crowsnest` router on `Host(crowsnest.{{ env "SRDP_DOMAIN" }})` with SRDP's
   `zitadel-errors` and `zitadel-auth` middlewares, a `crowsnest-oauth2` router for
   `/oauth2/` on the same host to SRDP's `oauth2-proxy` service, and the
   `crowsnest` service on port 8080. This is the client-route pattern #115 tested.
3. **`env.tmpl`.** Generate `POSTGRES_PASSWORD`,
   `ZITADEL_DATABASE_POSTGRES_USER_PASSWORD`, `DAGSTER_PG_PASSWORD` and
   `MARQUEZ_DB_PASSWORD`. Rename `ZITADEL_ADMIN_PASSWORD` to SRDP's
   `ZITADEL_FIRSTINSTANCE_ORG_HUMAN_PASSWORD`. `.env` is written once and never
   overwritten, so a stack already rendered from the old template needs its `.env`
   deleted and regenerated. Nobody runs one yet.
4. **`commands.py`.** `compose_command` passes `SRDP_DOMAIN=<valk.domain>` in the
   subprocess environment, as SRDP's Justfile does from `srdp.toml`. The domain then
   lives only in `datavloot.yml`; `.env` is not re-rendered, so it cannot hold it.
   `compose_files(prod=True)` returns base, prod and ours, without the override.
   `cmd_certs` issues `<domain>`, `*.<domain>` and `auth.<domain>`.
5. **`render.py`.** `HOSTS` loses `quarto`; `hosts_rule`, `ducklake_volume_mount`
   and `ducklake_volume_def` go; `traefik.yml` is replaced by
   `traefik-crowsnest.yml` in the render list.
6. **Runbook (`README.md.tmpl`).** Redirect URIs: drop quarto, add the hub
   (`https://<domain>/oauth2/callback`) and SRDP's other gated hosts, so one
   oauth2-proxy application serves the whole stack.

Unchanged on purpose:

- **Our Dagster webserver image.** SRDP locks Dagster 1.13.20, the toolkit 1.13.7,
  and webserver and code server must match.
- **`ensure_catalog_database()`.** It is redundant now that `srdp-setup` creates
  `ducklake`, but harmless.
- **SRDP's example services.** streamlit, api, duckdb-ui, marquez and the hub run as
  SRDP ships them.
- **The manual Zitadel step.** SRDP's `provision-oidc.sh` still hardcodes its
  domain and does not create the application.

Tests: rewrite `test_valk_render.py`'s label, oauth2-proxy and `traefik.yml`
assertions; add one for the routing file and one for `compose_files(prod=True)`.

Done when: `datavloot valk render && fetch && certs && up` on a clean machine
serves `https://crowsnest.<domain>` behind the Zitadel login, with no file under
`.srdp/` modified.

## Step 3: access, the SRDP way

The Crows Nest already validates the token itself and reads the roles from it
(ADR-0008). Three small changes close the gaps:

1. **Audience.** The overlay sets `CROWSNEST_OIDC_AUDIENCE: ${OIDC_CLIENT_ID}`.
   ADR-0008 requires an audience check; the code supports it and it is off today.
   This assumes Zitadel puts the client ID in the access token's `aud`, which SRDP's
   own `--extra-jwt-issuers=<issuer>=<client id>` relies on too. Confirm in the pilot.
2. **Roles scope.** Removing our oauth2-proxy block (step 2) also drops the
   `urn:zitadel:iam:org:projects:roles` scope we added. The runbook's Zitadel
   settings (JWT access token, *Add user roles to the access token*, *Assert roles
   on authentication*) put the roles in the token without it. If the pilot shows
   otherwise, the Crows Nest still gets them through userinfo, only slower.
3. **Default role: decision needed.** Today a signed-in user without a role gets
   `reader`. On SRDP that means everyone in the Zitadel instance. Recommendation:
   default `none`, so access is granted, never assumed. It is a one-line default
   in `vessel.py` plus the docs.

Out of scope, recorded so it is not mistaken for done: SRDP gates its own services
(Dagster UI, marimo, duckdb-ui, api) on "signed in", not on a role. ADR-0005 plans
role checks at the edge, and SRDP has not built them. In production SRDP makes the
Dagster UI read-only (`--read-only`), which the Crows Nest is compatible with: it
never starts runs.

## Step 4: docs and the pilot

- `docs/valk.md`: update the "promise" table, "What runs" and "Known gaps" after
  steps 1 and 2. The access, `datavloot.yml` and CLI sections added with this plan
  stay valid.
- `datavloot.yml` templates: update the `srdp.ref` comment; remove `catalog.alias`.
- Pilot (the NOAA demo, from `scaling-with-srdp.md`), checking specifically:
  - a Dagster run lands in Postgres and is visible in the Crows Nest;
  - a user with each role gets the right answer, and a user without a role gets the
    default;
  - the token's `aud` contains the client ID;
  - the Crows Nest still queries a Postgres catalog after `enable_external_access=false`.
    Already-attached databases should keep working, but this has not been run.
  - `--prod` gets Let's Encrypt certificates.

## Order and size

| Step | Depends on | Size |
|---|---|---|
| 1. One storage module | merge (done) | medium; mostly moving code, net deletion |
| 2. SRDP pin | #115 merged | small; net deletion in templates |
| 3. Access | 2 | three lines plus docs |
| 4. Docs and pilot | 1–3, a machine with Docker | one session |

Step 1 can start now. Step 2 can be written against the PR head (`55a3b1d`) and
re-pinned to the merge commit once #115 lands.
