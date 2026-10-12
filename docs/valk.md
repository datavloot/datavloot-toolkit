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

> **Status, 2026-10-12.** Main now keeps every project's data in a DuckLake in
> `lake/` (#33) and splits dev from prod writes (#34). That overlaps with the
> switching mechanism described in the table below, which is being replaced by "the
> same lake, with its catalog in Postgres". Until step 1 of
> [valk-plan.md](valk-plan.md) lands, dbt and dlt on the Valk write to the SQLite
> lake inside the container, not to the shared catalog. The access, configuration
> and command sections below are current.

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
`datavloot valk up` again. `datavloot valk --prod up` adds SRDP's Let's Encrypt
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

| Role (SRDP ADR-0005 names) | In the Crows Nest |
|---|---|
| `reader` | browse the catalog, quality results and run history; run read-only SQL |
| `writer` | reader, plus start and stop notebooks (`POST /api/notebooks/...`) |
| `admin` | the same as writer; reserved for a settings surface that does not exist yet |

Roles are Zitadel project roles with exactly those names. A user with several gets
the highest. A signed-in user without one gets `valk.access.default_role`
(`reader` by default; `none` to deny). The Zitadel switches that make this fast
are in `deploy/valk/README.md` step 3: without them the access token is opaque
and the Crows Nest asks Zitadel's userinfo endpoint who it belongs to (cached one
minute per token).

For the Optimist on a VM, `CROWSNEST_AUTH_TOKEN` still works as before. When an
issuer is configured it is ignored, so one deployment never has two password
prompts.

### Who does what

| Piece | Job |
|---|---|
| Zitadel (`auth.<domain>`) | Stores users, the project, its three roles and who holds which. **This is where people are added and roles granted.** |
| oauth2-proxy + Traefik | Send anyone without a session to the Zitadel login; pass the access token on. They check "signed in", not roles. |
| Crows Nest | Validates the token (signature, issuer, expiry, and audience when `CROWSNEST_OIDC_AUDIENCE` is set), reads the roles from it, allows or refuses each request. It does not log anyone in and has no screen for managing users or roles. |

### Adding a person

Done in the Zitadel console at `https://auth.<domain>`, as an organization owner
(the first-boot admin, or someone they made owner):

1. **Users → New**: name, e-mail, and an initial password or an invitation e-mail.
   Zitadel needs SMTP set up (Default settings → SMTP) to send invitations;
   without it, set a password and hand it over yourself.
2. **Projects → `<project>` → Authorizations → New**: pick the user, tick one
   role (`reader`, `writer` or `admin`).
3. The person signs in at `https://crowsnest.<domain>`. A role change applies at
   their next token: sign out and in, or wait for the access token to expire
   (Zitadel's default is 12 hours). Removing an authorization works the same
   way, so a token issued earlier keeps working until it expires.

To take someone out completely, deactivate or delete the user in Zitadel. No new
token is issued to them after that. The Crows Nest validates tokens offline (the
ADR-0008 pattern), so a token they already hold keeps working there until it
expires; the token lifetime is the revocation delay. Shorten it in Zitadel
(Default settings → OIDC token lifetimes) if that is too long.

### What the roles do not cover

- **SRDP's own services.** The Dagster UI, Marimo, the DuckDB UI, the API and the
  hub are gated on "signed in", not on a role. ADR-0005 plans role checks at the
  edge; SRDP has not built them yet. In production SRDP runs the Dagster UI
  read-only, so a signed-in user can look but not launch.
- **Anyone in the Zitadel instance is "signed in".** With
  `default_role: reader`, that is also enough to read the catalog in the Crows
  Nest. Set `default_role: none` to require an explicit grant, and check that
  self-registration is off in Zitadel (Default settings → Login behavior and
  security) unless you want it.

## Configuration: the `valk:` block

Everything the Valk reads from `datavloot.yml`. Only `domain` is required.
Secrets never go here; they live in `deploy/valk/.env`, which `datavloot valk
render` generates once and git ignores.

| Key | Default | Meaning |
|---|---|---|
| `vessel` | `optimist` | `valk` switches the project to the Valk |
| `valk.domain` | (required) | Bare host name. Services are published as `crowsnest.<domain>`, `dagster.<domain>`, `auth.<domain>`, ... Zitadel records it at first boot, so changing it later means a fresh Zitadel. |
| `valk.acme_email` | empty | Let's Encrypt contact for `datavloot valk --prod up`. Empty means local mkcert certificates, and the Crows Nest then accepts Zitadel's mkcert certificate. |
| `valk.catalog.metadata_schema` | `ducklake_<project>` | Schema in the shared Postgres that holds this project's DuckLake metadata |
| `valk.catalog.alias` | `ducklake` | Name the catalog is attached as. Goes away in [valk-plan.md](valk-plan.md) step 1, where the alias becomes the project name as on the Optimist. |
| `valk.storage.kind` | `local` | `local`: Parquet on a Docker volume. `s3`: any S3-compatible bucket. |
| `valk.storage.data_path` | `/data/ducklake` | `local` only: where the volume is mounted |
| `valk.storage.bucket`, `endpoint` | | `s3`: required |
| `valk.storage.prefix` | project name | `s3`: key prefix inside the bucket |
| `valk.storage.region`, `url_style` | none, `path` | `s3`: as the provider needs |
| `valk.access.default_role` | `reader` | Role for a signed-in user without a Zitadel role: `reader` or `none` |
| `valk.srdp.repo`, `ref` | SRDP on GitHub, the toolkit's pin | The SRDP checkout the overlay is rendered against; see below |

The S3 key pair goes in `.env` as `DATAVLOOT_S3_KEY_ID` and `DATAVLOOT_S3_SECRET`.

## Commands

All of them read `datavloot.yml` from the current directory, or from
`datavloot valk --project <dir> ...`, and print every `git` and `docker compose` command before
running it, so each step can be repeated by hand.

| Command | Does |
|---|---|
| `datavloot valk render [--datavloot-source <spec>]` | Writes `deploy/valk/` (compose overlay, Dockerfiles, Dagster config, runbook), creates `.env` with random secrets if it does not exist, adds `.srdp/` and `deploy/valk/.env` to `.gitignore`. Safe to rerun; `.env` is never overwritten. `--datavloot-source` sets what the image installs: a PyPI version, or `git+https://...@ref` for an unreleased toolkit. |
| `datavloot valk fetch` | Checks SRDP out at the pinned commit into `.srdp/` (shallow, exact SHA) |
| `datavloot valk certs` | mkcert certificates for the domain, into `.srdp/deploy/docker/certs/`. Zitadel serves TLS itself and needs them in production too. |
| `datavloot valk [--prod] up [--no-build]` | `docker compose up -d --build`, SRDP's files first and our overlay last. `--prod` adds SRDP's production override (Let's Encrypt, read-only Dagster UI). |
| `datavloot valk [--prod] down` | `docker compose down`; volumes, and with them the data, stay |
| `datavloot valk compose <args>` | Any other `docker compose` command against the same files, for example `logs -f crowsnest` or `ps` |

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
