# 0001. Optimist as a single-node, single-writer architecture

- **Date:** 2026-10-01
- **Issue:** #9

## Context

The Optimist targets an small organisation with a data team of one, and runs the whole platform on one machine.

That team of one still runs several writing processes at once: a scheduled Dagster run, dbt during development, a dlt load. Projects write to a single DuckDB file, and DuckDB lets only one process open a file for writing; while it does, no other process can open it, not even read-only. Runs collide on the lock, and a Marimo notebook cannot open during a Dagster run.

The rest of the organisation only reads. It needs the platform reachable beyond one laptop, but not per-user data permissions.

## Decision

- **Technically multi-client, organisationally single-writer.** Several local processes may read while one writes; writes are committed one at a time. Production data is written only by Dagster; development writes go to a separate schema.
- **DuckLake with a SQLite catalog and Parquet files on local disk.** Both live in `lake/` in the project directory, with the catalog in WAL mode. The catalog stores file paths relative to the data directory, so the directory can be moved. It is the full state, and the unit of backup.
- **One package, two ways of running.** Laptop mode: `pip install datavloot[optimist]` and `datavloot start`. VM mode: the same package in a Docker image under Docker Compose.
- **Access, not authorisation.** In VM mode every service sits behind Traefik, with optional oauth2-proxy against the customer's identity provider, or basic auth. Whoever is let in sees everything.
- **Out of scope:** per-user data authorisation, writers on more than one machine, streaming, Kubernetes.

## Consequences

- A notebook or the Crows Nest can read while a pipeline writes, and readers never see a half-written state. Without WAL mode on the catalog, readers and a writer lock each other out.
- Parquet files accumulate: compaction and snapshot expiry must run on a schedule, and backups must copy the catalog before the files and not overlap with cleanup.
- Existing projects on a `.duckdb` file need a migration path.
- The project directory must be on a local disk: sync folders and network drives do not honour the file locks SQLite and DuckDB rely on.
- Writers take turns. A second process committing at the same moment fails with `database is locked`, also when it writes another table, instead of waiting. Dagster therefore runs one writer at a time, and a dbt run by hand next to a running job may fail a model that then has to be rerun. No data is lost or left half-written.

Follow-up work is tracked in the issues labelled `optimist`.

## Alternatives considered

- **One DuckDB file, every writer serialised through Dagster.** dbt development and notebooks still hit the lock.
- **DuckLake with a DuckDB catalog.** The catalog file has the same single-writer limit.
- **DuckLake with a PostgreSQL catalog.** No file-lock concerns, but a database server to install, run and back up on a laptop, and the state is no longer one directory.
- **Per-user roles.** Needs an identity provider with a roles claim and authorisation in every component; more than a team of one needs.
