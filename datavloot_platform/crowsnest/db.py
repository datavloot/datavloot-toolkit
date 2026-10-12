"""
DuckDB connection helper for the Crows Nest.

Supports three modes:
  Valk:      the shared DuckLake catalog on Postgres described by the DUCKLAKE_*
             environment, attached through vessel.attach_ducklake so the Crows Nest,
             dbt and dlt agree on data path and metadata schema
  DuckLake:  in-memory connection with the project's lake attached, the default
             once the project has one (see config.py and storage.py)
  Standard:  plain DuckDB file connection, for projects still on a .duckdb file

Every connection is sandboxed before it is handed out -- see _harden().
"""

import pathlib
import time

import duckdb
from fastapi import HTTPException

from datavloot_platform import extensions, storage
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
#
# A DuckLake reads its Parquet files through the local file system, so there the
# file system cannot be disabled: every query would fail. Instead,
# allowed_directories opens exactly the lake's data directory, and
# enable_external_access keeps everything else shut (checked: reading or writing
# outside it, re-enabling access and installing extensions all stay blocked).
# What this gives up: a COPY ... TO into the data directory itself would be
# allowed. No route lets one through -- the query route accepts only SELECT and
# EXPLAIN -- so only this second line of defence is narrower.
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


def _harden(
    conn: duckdb.DuckDBPyConnection, lake_data: str | None = None, *, remote: bool = False
) -> duckdb.DuckDBPyConnection:
    """
    Lock a connection down to reading what is already attached.

    Applied after any ATTACH, which must happen while external access is still
    permitted. With `lake_data`, the file system stays open for that directory
    only, as a DuckLake needs. With `remote`, the data is in a bucket and the
    network stays open instead (see _HARDENING_REMOTE).
    """
    statements = _HARDENING
    if remote:
        statements = _HARDENING_REMOTE
    elif lake_data:
        allowed = pathlib.Path(lake_data).as_posix().rstrip("/") + "/"
        statements = (
            f"SET allowed_directories=['{allowed}']",
            "SET enable_external_access=false",
            "SET lock_configuration=true",
        )
    for statement in statements:
        conn.execute(statement)
    return conn


def get_conn(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    config = get_config()
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            if config.is_valk:
                from datavloot_platform import vessel

                conn = duckdb.connect()
                vessel.attach_ducklake(
                    conn, config.vessel, read_only=read_only, alias=config.ducklake_alias
                )
                data = vessel.data_path()
                if vessel.is_remote(data):
                    return _harden(conn, remote=True)
                return _harden(conn, lake_data=data)
            elif config.ducklake_catalog_path:
                conn = duckdb.connect()
                # Not a bare INSTALL: offline, that fails with only a download
                # error. This says how to install it by hand.
                for name in extensions.REQUIRED:
                    extensions.ensure_loaded(conn, name)
                conn.execute(
                    storage.attach_statement(
                        pathlib.Path(config.ducklake_catalog_path),
                        pathlib.Path(config.ducklake_data_path),
                        config.ducklake_alias,
                        read_only=read_only,
                    )
                )
                conn.execute(f"USE {config.ducklake_alias}")
                return _harden(conn, lake_data=config.ducklake_data_path)
            else:
                return _harden(
                    duckdb.connect(config.duckdb_path, read_only=read_only)
                )
        except Exception as e:
            last_exc = e
            if attempt < 2 and "another process" in str(e).lower():
                time.sleep(0.15 * (attempt + 1))
                continue
            break
    raise HTTPException(503, f"Cannot connect to database: {last_exc}")
