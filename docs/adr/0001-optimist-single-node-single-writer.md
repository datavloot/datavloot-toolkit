# 0001. Optimist as a single-node, single-writer architecture

- **Status:** Proposed
- **Date:** 2026-10-01
- **Issue:** #9

## Context

The Optimist is the entry-level vessel, aimed at an organisation of 20–200 people with a data team of one, and runs the whole platform on one machine.

Even a team of one runs several writing processes at once: a scheduled Dagster run, dbt during development, a dlt load. Scaffolded and demo projects write to a single DuckDB file (`<project>.duckdb`, configured in `profiles.yml` and the dlt assets). DuckDB allows one process to open a file for writing, and while it does, no other process can open the file at all, not even read-only. The processes collide on the file lock, and a Marimo notebook cannot open during a Dagster run.

The organisation around the data team does not write: it reads dashboards and asks questions. It does not need per-user data permissions, but it does need the platform reachable beyond the laptop of the person who built it.

A larger vessel, the Falcon (earlier called the Valk), is being built separately on SRDP, with a PostgreSQL catalog, Zitadel and per-user roles. An earlier design shared a vessel abstraction between the two (`feature/evka_valk_vessel`), so one project could switch between them with a config flag. That branch will not be merged.

## Decision

**Technically multi-client, organisationally single-writer.** Several local processes may read and write at the same time. Production data is written only by Dagster; development writes go to a separate schema.

**Storage is DuckLake with a SQLite catalog and Parquet files on local disk.** The catalog and the data directory sit under the project directory, referenced by relative paths. That directory is the full state of the platform, and the unit of backup and migration.

**One artifact, two ways of running.** Laptop mode installs `datavloot[optimist]` with pip and runs `datavloot start`. VM mode runs the same package in a Docker image under Docker Compose. Project layout and storage are the same in both; only paths, secrets and process management differ.

**Access, not authorisation.** In VM mode every service sits behind Traefik, with an optional oauth2-proxy against the customer's own identity provider (Entra ID, Google Workspace), or Traefik basic auth without one. Whoever is let in sees everything; there is no per-user data authorisation.

**The Optimist stands on its own.** It shares no code with the Falcon. Moving up to a larger setup is a data migration (catalog into PostgreSQL, Parquet files to a volume or object storage), not a switch in the project config.

**Out of scope:** per-user data authorisation, writers on more than one machine, streaming, Kubernetes.

## Consequences

- dbt development, a scheduled run and a notebook no longer lock each other out. DuckLake's snapshot isolation also means readers never see a half-written state.
- New operational work: Parquet files accumulate, so compaction and snapshot expiry must run on a schedule; backups must copy the catalog before the files, and must not overlap with cleanup.
- Existing projects on a `.duckdb` file need a migration path.
- SQLite and DuckDB rely on OS file locks, which sync folders (OneDrive, Dropbox) and network drives do not provide reliably. The project directory must live on a local disk.
- DuckDB extensions (`ducklake`, `sqlite`) are downloaded on first use today, which fails behind corporate proxies; they need to be installed up front.
- Concurrent writes to the same table can still conflict at commit time; those must be retried or reported clearly. Whether the SQLite catalog holds up under the expected load is verified by a concurrency test rather than assumed.
- The Falcon can evolve on SRDP without the Optimist waiting on it, at the cost that moving up is a migration instead of a config change.

The follow-up work is tracked in the issues labelled `optimist` (#10–#21).

## Alternatives considered

- **Stay on one DuckDB file and serialise every writer through Dagster.** dbt development next to a scheduled run still hits the lock, and so does a notebook.
- **DuckLake with a DuckDB catalog** (what `setup_catalog.py` does now). The catalog file has the same single-writer limit as a plain DuckDB file.
- **DuckLake with a PostgreSQL catalog on the Optimist.** Removes the file-lock concerns, but adds a database server to install, run and back up on a laptop, and the state is no longer one directory.
- **A shared vessel abstraction with the Falcon** (`feature/evka_valk_vessel`). One project could run on both by changing `vessel:` in `datavloot.yml`. Dropped: the Falcon moves to SRDP, and coupling the two would make the simple tier wait on the complex one.
- **Per-user roles in the Optimist.** Requires an identity provider with a roles claim and authorisation in every component; that is the Falcon's territory.
