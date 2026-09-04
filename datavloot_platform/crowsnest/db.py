"""
DuckDB connection helper for the Crows Nest.

Supports two modes:
  Standard:  plain DuckDB file connection (default)
  DuckLake:  in-memory connection with ducklake extension and catalog attached
             (enabled by setting CROWSNEST_DUCKLAKE_CATALOG_PATH)

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


def _harden(conn: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyConnection:
    """
    Lock a connection down to reading what is already attached.

    Applied after any ATTACH, which must happen while external access is still
    permitted. Verified not to affect DuckLake: its parquet data files still
    resolve after the filesystem is disabled.
    """
    for statement in _HARDENING:
        conn.execute(statement)
    return conn


def get_conn(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    config = get_config()
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            if config.ducklake_catalog_path:
                conn = duckdb.connect()
                conn.execute("INSTALL ducklake")
                conn.execute("LOAD ducklake")
                catalog_path = config.ducklake_catalog_path.strip().replace("\\", "/")
                # read_only was previously accepted and then ignored on this path,
                # so a DuckLake deployment had no read-only mode at all.
                options = "TYPE ducklake, READ_ONLY" if read_only else "TYPE ducklake"
                conn.execute(
                    f"ATTACH '{catalog_path}' AS {config.ducklake_alias} ({options})"
                )
                conn.execute(f"USE {config.ducklake_alias}")
                return _harden(conn)
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
