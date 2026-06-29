"""
DuckDB connection helper for the Crows Nest.

Supports two modes:
  Standard:  plain DuckDB file connection (default)
  DuckLake:  in-memory connection with ducklake extension and catalog attached
             (enabled by setting CROWSNEST_DUCKLAKE_CATALOG_PATH)
"""

import time

import duckdb
from fastapi import HTTPException

from datavloot_platform.crowsnest.config import get_config


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
                conn.execute(
                    f"ATTACH '{catalog_path}' AS {config.ducklake_alias} (TYPE ducklake)"
                )
                conn.execute(f"USE {config.ducklake_alias}")
                return conn
            else:
                return duckdb.connect(config.duckdb_path, read_only=read_only)
        except Exception as e:
            last_exc = e
            if attempt < 2 and "another process" in str(e).lower():
                time.sleep(0.15 * (attempt + 1))
                continue
            break
    raise HTTPException(503, f"Cannot connect to database: {last_exc}")
