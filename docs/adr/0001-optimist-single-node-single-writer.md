# 0001. Optimist as a single-node, single-writer architecture

- **Date:** 2026-10-01
- **Issue:** #9

## Context

The Optimist targets an small organisation with a data team of one, and runs the whole platform on one machine.

That team of one still runs several writing processes at once: a scheduled Dagster run, dbt during development, a dlt load. Projects write to a single DuckDB file, and DuckDB lets only one process open a file for writing; while it does, no other process can open it, not even read-only. Runs collide on the lock, and a Marimo notebook cannot open during a Dagster run.

The rest of the organisation only reads. It needs the platform reachable beyond one laptop, but not per-user data permissions.

## Decision

- **Technically multi-client, organisationally single-writer.** Several local processes may read and write at once. Production data is written only by Dagster; development writes go to a separate schema.
- **DuckLake with a SQLite catalog and Parquet files on local disk.** Both live under the project directory, referenced by relative paths. That directory is the full state, and the unit of backup.
- **One package, two ways of running.** Laptop mode: `pip install datavloot[optimist]` and `datavloot start`. VM mode: the same package in a Docker image under Docker Compose.
- **Access, not authorisation.** In VM mode every service sits behind Traefik, with optional oauth2-proxy against the customer's identity provider, or basic auth. Whoever is let in sees everything.
- **Out of scope:** per-user data authorisation, writers on more than one machine, streaming, Kubernetes.

## Consequences

- dbt development, a scheduled run and a notebook no longer lock each other out, and readers never see a half-written state.
- Parquet files accumulate: compaction and snapshot expiry must run on a schedule, and backups must copy the catalog before the files and not overlap with cleanup.
- Existing projects on a `.duckdb` file need a migration path.
- The project directory must be on a local disk: sync folders and network drives do not honour the file locks SQLite and DuckDB rely on.
- Concurrent writes to the same table can conflict at commit time and must be retried or reported. Whether the SQLite catalog holds up under the expected load is tested, not assumed.

Follow-up work is tracked in the issues labelled `optimist`.

## Alternatives considered

- **One DuckDB file, every writer serialised through Dagster.** dbt development and notebooks still hit the lock.
- **DuckLake with a DuckDB catalog.** The catalog file has the same single-writer limit.
- **DuckLake with a PostgreSQL catalog.** No file-lock concerns, but a database server to install, run and back up on a laptop, and the state is no longer one directory.
- **Per-user roles.** Needs an identity provider with a roles claim and authorisation in every component; more than a team of one needs.
