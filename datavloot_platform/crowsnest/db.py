"""
DuckDB connection helper for the Crows Nest.

Supports two modes:
  Standard:  plain DuckDB file connection (default)
  DuckLake:  in-memory connection with ducklake extension and catalog attached
             (enabled by setting CROWSNEST_DUCKLAKE_CATALOG_PATH)
"""

import duckdb
from fastapi import HTTPException

from datavloot_platform.crowsnest.config import get_config


def get_conn(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    config = get_config()
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
        raise HTTPException(503, f"Cannot connect to database: {e}")
