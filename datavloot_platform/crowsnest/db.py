"""
DuckDB connection helper for the Crows Nest.

Three modes, decided by config.py:
  Optimist:  plain DuckDB file connection (default)
  DuckLake:  in-memory connection with the ducklake extension and a catalog attached,
             either a local catalog file or a `ducklake:postgres:...` string
             (CROWSNEST_DUCKLAKE_CATALOG_PATH, or the dbt target's `attach:` entry)
  Valk:      the shared DuckLake catalog described by the DUCKLAKE_* environment,
             attached through vessel.attach_ducklake so the Crows Nest, dbt and dlt
             agree on data path and metadata schema

Every connection is sandboxed before it is handed out -- see _harden().
"""

import time

import duckdb
from fastapi import HTTPException

from datavloot_platform.crowsnest.config import get_config


# Applied to every connection, immediately before it is returned.
#
# `read_only=True` on a DuckDB connection stops writes to the *database*. It does
# not stop writes to the *filesystem*, so `COPY (SELECT ...) TO '/tmp/x.csv'`
# happily exfiltrates a table, and `read_csv('/etc/passwd')` reads back anything
# the server process can. Statement-level filtering in a route cannot fix that
# reliably, and only protects the one route that remembers to do it.
#
# These three settings close it at the connection instead, so every route --
# including ones not written yet -- gets the same guarantee:
#
#   enable_external_access  no attaching databases, installing extensions, or
#                           reaching the network
#   disabled_filesystems    no local file reads or writes through SQL
#   lock_configuration      neither of the above can be turned back on by a query
#
# lock_configuration must come last, since it freezes the others.
_HARDENING = (
    "SET enable_external_access=false",
    "SET disabled_filesystems='LocalFileSystem'",
    "SET lock_configuration=true",
)

# When the DuckLake data lives in a bucket, the *engine itself* needs the network
# to read Parquet through httpfs, so enable_external_access must stay on. What is
# still closed: the local filesystem (no reads, no COPY TO), and the configuration
# is locked so a query cannot widen it. The remaining exposure is that a query can
# `read_parquet('s3://...')` anything the attached S3 secret can reach, which is
# the same bucket the catalog already serves -- accepted for the Valk, documented
# in docs/valk.md.
_HARDENING_REMOTE = (
    "SET disabled_filesystems='LocalFileSystem'",
    "SET lock_configuration=true",
)


def _harden(conn: duckdb.DuckDBPyConnection, *, remote: bool = False) -> duckdb.DuckDBPyConnection:
    """
    Lock a connection down to reading what is already attached.

    Applied after any ATTACH, which must happen while external access is still
    permitted. Verified not to affect a local DuckLake: its parquet data files
    still resolve after the filesystem is disabled.
    """
    for statement in (_HARDENING_REMOTE if remote else _HARDENING):
        conn.execute(statement)
    return conn


def attach_statement(
    catalog: str,
    alias: str,
    *,
    read_only: bool,
    data_path: str | None = None,
    metadata_schema: str | None = None,
) -> str:
    """
    The ATTACH for a DuckLake catalog, whichever way it was named.

    A `ducklake:` string (a Postgres catalog, `ducklake:postgres:host=...`, or an
    explicit `ducklake:/path/file.ducklake`) is passed through untouched: it may
    contain spaces and `=`, and it must never be path-normalised. A bare filename
    is the legacy form and gets `TYPE ducklake` plus Windows-slash normalisation.
    """
    options = []
    if catalog.startswith("ducklake:"):
        target = catalog
    else:
        target = catalog.strip().replace("\\", "/")
        options.append("TYPE ducklake")
    if read_only:
        options.append("READ_ONLY")
    if data_path:
        options.append(f"DATA_PATH '{data_path}'")
        options.append("OVERRIDE_DATA_PATH true")
    if metadata_schema:
        options.append(f"METADATA_SCHEMA '{metadata_schema}'")
    suffix = f" ({', '.join(options)})" if options else ""
    return f"ATTACH IF NOT EXISTS '{target}' AS {alias}{suffix}"


def _open_ducklake(conn: duckdb.DuckDBPyConnection, config, read_only: bool) -> bool:
    """Attach the configured DuckLake catalog. Returns True when its data is remote."""
    from datavloot_platform import vessel

    if config.is_valk:
        vessel.attach_ducklake(conn, config.vessel, read_only=read_only, alias=config.ducklake_alias)
        return vessel.is_remote(vessel.data_path())

    conn.execute("INSTALL ducklake")
    conn.execute("LOAD ducklake")
    remote = bool(config.ducklake_data_path and vessel.is_remote(config.ducklake_data_path))
    if remote:
        conn.execute("INSTALL httpfs")
        conn.execute("LOAD httpfs")
        secret = vessel.s3_secret_sql(config.vessel)
        if secret:
            conn.execute(secret)
    conn.execute(
        attach_statement(
            config.ducklake_catalog_path,
            config.ducklake_alias,
            read_only=read_only,
            data_path=config.ducklake_data_path,
            metadata_schema=config.ducklake_metadata_schema,
        )
    )
    conn.execute(f"USE {config.ducklake_alias}")
    return remote


def get_conn(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    config = get_config()
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            if config.uses_ducklake:
                conn = duckdb.connect()
                remote = _open_ducklake(conn, config, read_only)
                return _harden(conn, remote=remote)
            return _harden(duckdb.connect(config.duckdb_path, read_only=read_only))
        except Exception as e:
            last_exc = e
            if attempt < 2 and "another process" in str(e).lower():
                time.sleep(0.15 * (attempt + 1))
                continue
            break
    raise HTTPException(503, f"Cannot connect to database: {last_exc}")
