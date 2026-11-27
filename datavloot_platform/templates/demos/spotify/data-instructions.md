# spotify

A dbt project built on the [datavloot toolkit](https://github.com/datavloot/datavloot-toolkit),
showing your own Spotify listening history (or a made-up sample until an account is connected).

See `dbt_packages/optimist/data-instructions.md` for the full workflow, naming conventions, modelling
conventions, and captain/crew guide. Run `dbt deps` if the file is not yet present. Where data is
written is covered below, under "Development and production".

---

## Project context

- **Sources**: the Spotify Web API (`spotify_platform/spotify.py`), loaded by one dlt pipeline:
  `account`, `recently_played`, `top_tracks`, `top_artists`, `saved_tracks`, `playlists`,
  `playlist_items`, `followed_artists` in the `source` schema. Without a connected account the same
  tables hold the sample from `spotify_platform/sample.py`; the `origin` column says which, and
  `macros/stage_spotify.sql` keeps only the rows matching `source.account`.
- **History**: Spotify returns only the last 50 plays. `recently_played`, `top_tracks` and
  `top_artists` are merged run by run (the `spotify_sync_every_30_minutes` schedule), so history
  starts on the day the account is connected. The other tables are replaced on every run.
- **API limits** (Development Mode, February 2026): no popularity, follower counts or batch lookups;
  playlist tracks only for playlists the user owns or collaborates on. Do not model on fields
  Spotify no longer sends.
- **Warehouse**: DuckLake in `lake/` (SQLite catalog, Parquet files), attached as `spotify`
- **Orchestration**: Dagster via `spotify_platform/`. Dagster is the only production writer (`prod`
  target, `spotify_*` schemas); dbt by hand builds `dev_*` (see "Development and production" below)
- **Time zone**: Spotify gives UTC; `fct_play` converts to `var('spotify_timezone')` in
  `dbt_project.yml`. Hours, days and listening moments are local.
- **Personal data**: this is someone's own listening history. Keep it in the lake; never put it in
  seeds, tests or anything committed to git. `.env` holds the refresh token and is ignored by git.

---

## Development and production

Production has one writer: Dagster. Everything else develops alongside it without touching
production data.

| | Who | dbt target | Lands in |
|---|---|---|---|
| Production | Dagster, from the UI, a schedule or a sensor | `prod` | `spotify_source`, `spotify_business`, … |
| Development | You or the crew, running `dbt run`, `dbt build`, `dbt seed` by hand | `dev` (the default) | `dev_source`, `dev_business`, … |

Both targets attach the same lake (see `profiles.yml`). Sources are read from the same raw
schemas in both, so a dev build works on production input but writes only to `dev_*`.

Rules:

- **Never pass `--target prod` by hand.** To get a change into production, materialise the
  assets in Dagster. A manual prod run bypasses the concurrency limit below and can collide with
  a running pipeline.
- **Every Dagster asset or op that writes to the lake sets `pool=LAKE_POOL`** (`assets.py`):
  dbt assets, dlt assets, lake maintenance and any asset that writes through `storage.connect`.
  `dagster.yaml` limits the pool to one at a time, because the lake accepts one commit at a time;
  without the pool, two writers committing together fail with `database is locked`. Dagster reads
  that file from its home: `datavloot start` uses `.dagster/` in the project and copies
  `dagster.yaml` there on every start, so edit the one in the project. If you set `DAGSTER_HOME`
  yourself, copy `dagster.yaml` into that directory.
- Readers (notebooks, the Crows Nest) open the lake read-only and can run at any time.

A dev build can still collide with a Dagster commit at the same moment. dbt retries the statement
(`retries` in `profiles.yml`). If a model still fails on a lock, rerun it.

### Lake maintenance

Every write adds Parquet files, and old snapshots keep old files alive. The `lake_maintenance`
job (`lake_maintenance.py`) runs daily at 03:00 while Dagster runs: it merges small files, expires
snapshots older than seven days (`keep_snapshots_days` in the job's config) and deletes files
nothing refers to any more. Files are deleted only after a margin of days, so a reader on an old
snapshot can finish; the reasons are in `datavloot_platform/maintenance.py`.

Deleting files waits for the lake's file lock (`lake/files.lock`), which a backup also holds. If
the lock is taken, the job skips deleting and the next run catches up.

To switch the schedule off, set `DATAVLOOT_LAKE_MAINTENANCE=off` in a `.env` file in the project
directory (or in the environment) and restart Dagster. The job then runs only when you start it in
Dagster; `on`, the default, switches it back. Dagster remembers a schedule you switched on or off
in its UI (in `.dagster/`, kept between starts), and that wins over the variable.
