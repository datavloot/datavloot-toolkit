# Valk handover

For Stan, from EVKA, 2026-10-16. I'm out sick; this is everything you need to
carry on with the Valk without me. The detailed design is in
[valk-plan.md](valk-plan.md); this page says where things stand, what changed since
that plan was written, and in which order to work.

## Where it stands

- Branch: `feature/evka_valk_vessel`, pushed. `main` is merged in up to #37
  (`8fc727b`), and nothing is newer on `main` as of today.
- Tests: `uv run --extra valk --extra optimist pytest -m "not slow"` passes with
  one expected failure (see below); `-m slow` passes.
- Nothing has run against a live SRDP stack yet. My machine has no Docker.

**What is broken, on purpose.** The merge resolved every conflict in favour of
your `storage.py` design (#33, #34), which made the Valk's own switch obsolete
(`DATAVLOOT_DBT_DATABASE`, the `valk` dbt target, `vessel.connect()`). Until step 1
below is done, dbt and dlt on the Valk write to a SQLite lake inside the container
instead of the shared Postgres catalog.
`tests/test_valk_render.py::test_render_writes_the_whole_deploy_dir` is marked
`xfail(strict=True)` for exactly this. When your fix makes it pass, pytest reports
it as an unexpected pass and fails the run: that is the signal to remove the marker.

## What changed since the plan

1. **srdp-hub/srdp#115 is merged**, as `d6cd685` (2026-10-15), from the head the
   plan was written against. Step 2 can go ahead as written.
2. **SRDP `main` is already one merge further**: #76 (`b03344e`) adds DuckLake on
   S3 with an optional bundled Garage server. It is additive. Without
   `COMPOSE_PROFILES=s3` nothing changes, and local storage stays the default.
   **Pin `b03344e`** (or whatever `main` is when you start, after checking the
   diff of `deploy/docker/` and `config/traefik/`), not `d6cd685`.
3. **#76 sets SRDP's standard for DuckLake on S3**, and per the brief, SRDP's
   standard wins where we have none of our own. Our names are our own invention,
   so they go:

   | Ours today | SRDP |
   |---|---|
   | `valk.storage.kind: s3` | `DUCKLAKE_STORAGE_BACKEND=s3` |
   | `bucket`, `prefix`, `endpoint`, `region`, `url_style` in `datavloot.yml` | `DUCKLAKE_S3_BUCKET`, `_PREFIX`, `_ENDPOINT` (bare host, no scheme), `_REGION`, `_URL_STYLE`, plus `_USE_SSL` |
   | `DATAVLOOT_S3_KEY_ID` / `_SECRET` for every container | `DUCKLAKE_S3_WRITER_KEY_ID` / `_SECRET` for `dagster-code` only; `DUCKLAKE_S3_READER_*` for every reader |
   | `DATAVLOOT_S3_ENDPOINT` / `_REGION` | `DUCKLAKE_S3_*`, as above |

   In the overlay this means `dagster-code` merges SRDP's `x-ducklake-writer`
   values, and the Crows Nest gets the reader key. The Crows Nest is a SQL console,
   which is exactly SRDP's reason for the split. SRDP's data path is
   `s3://<bucket>/<prefix>/`, with a secret scoped to that path; mirror that in
   `storage.py` (see `src/srdp/io/ducklake.py` in SRDP). The `datavloot.yml` keys
   can stay as the user-facing names, with `render` writing them into `.env` under
   SRDP's names. Keep it to that rename; we don't need Garage.

## Order of work

Each step is a separate PR into the branch, or a commit each if you prefer; the
detail is in [valk-plan.md](valk-plan.md).

1. **Fold the Valk into `storage.py`** (plan step 1). Your module, so your call on
   the shape. The plan's suggestion: `DATAVLOOT_VESSEL=valk` switches the catalog to
   `ducklake:postgres:` from `DUCKLAKE_PG_*`, under the same project-name alias.
   `datavloot valk render` writes `deploy/valk/profiles.yml` with the same `dev` and
   `prod` targets, and the Valk image copies it over `/app/profiles.yml`. That copy
   is needed because `DbtProject` passes `--profiles-dir` explicitly, so
   `DBT_PROFILES_DIR` is ignored. Fold in the S3 naming from the table above here,
   since you are writing that code anyway.
2. **Re-pin SRDP** (plan step 2) to `b03344e` or newer. Mostly deleting overlay
   parts: SRDP no longer reads Docker labels, `quarto` is gone, and the domain comes
   from `SRDP_DOMAIN`. Add one Traefik routing file for the Crows Nest. `commands.py`
   passes `SRDP_DOMAIN` from `datavloot.yml`.
3. **Access** (plan step 3): the audience check, plus the default role.
4. **Docs and the pilot** (plan step 4) on a machine with Docker, against the NOAA
   demo. The checklist is in the plan.

## Open decision

**Default role for a signed-in user without one.** It is `reader` now, which on
SRDP means anyone with an account in that Zitadel instance can read the catalog in
the Crows Nest. I recommended `none` and had not decided yet. Decide it with the
team; it is one default in `vessel.py` plus the docs (`docs/valk.md`, "What the
roles do not cover").

## Things that will bite

- **`deploy/valk/.env` is generated once and never overwritten.** After changing
  `env.tmpl`, delete the `.env` in your test project, or you test the old one.
- **Zitadel records its domain at first boot.** Changing `valk.domain` on a stack
  that has run needs `datavloot valk down` plus deleting the `srdp-pgdata` volume.
- **The overlay must not modify anything under `.srdp/`.** That is SRDP's checkout
  at the pin; every change goes in `datavloot_platform/valk/templates/`.
- **Dagster versions.** The toolkit locks 1.13.7 and SRDP 1.13.20, which is why we
  build our own webserver image (`Dockerfile.dagster`). Keep it, and give it its own
  `image:` name in the overlay, or it gets tagged as SRDP's.
- **Line endings.** Generated container files must stay LF;
  `test_container_files_have_unix_line_endings` checks it. Git on Windows warns
  about CRLF on commit; that is only the working copy.
- **`uv run` needs both extras** (`--extra valk --extra optimist`), or the Valk
  and Crows Nest tests are skipped rather than run.

## Where to read

| What | Where |
|---|---|
| The plan, step by step | [valk-plan.md](valk-plan.md) |
| How the Valk works, access, configuration, commands | [valk.md](valk.md) |
| Why SRDP at all | `scaling-with-srdp.md`, outside the repo; ask me for it |
| SRDP's own rules | `docs/adr/` in srdp-hub/srdp, mainly 0005 (roles), 0006 (project = catalog), 0008 (token validation) |
| SRDP's DuckLake code, the reference for step 1 | `src/srdp/io/ducklake.py` in srdp-hub/srdp |
