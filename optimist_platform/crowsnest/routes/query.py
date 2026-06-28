"""
SQL query route — executes read-only queries against DuckDB.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import duckdb
import time

from optimist_platform.crowsnest.db import get_conn

router = APIRouter()

MAX_ROWS = 10_000

_BLOCKED_STATEMENTS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
    "CREATE", "TRUNCATE", "GRANT", "REVOKE",
}


class QueryRequest(BaseModel):
    sql: str
    limit: int = 1000


class QueryResponse(BaseModel):
    columns: list[str]
    rows: list[list]
    row_count: int
    truncated: bool
    duration_ms: float


@router.post("/execute", response_model=QueryResponse)
async def execute_query(req: QueryRequest):
    """Execute a SQL query and return results as columns + rows."""
    sql = req.sql.strip()
    if not sql:
        raise HTTPException(400, "Empty query")

    first_word = sql.split()[0].upper() if sql.split() else ""
    if first_word in _BLOCKED_STATEMENTS:
        raise HTTPException(
            403,
            f"Write operations ({first_word}) are not allowed in the query editor. "
            "Use dbt for transformations.",
        )

    effective_limit = min(req.limit, MAX_ROWS)

    try:
        conn = get_conn(read_only=True)
        start = time.monotonic()
        limited_sql = (
            f"{sql} LIMIT {effective_limit}"
            if first_word == "SELECT" and "LIMIT" not in sql.upper()
            else sql
        )
        result = conn.execute(limited_sql)
        columns = [desc[0] for desc in result.description]
        rows = result.fetchall()
        duration = round((time.monotonic() - start) * 1000, 1)
        conn.close()

        safe_rows = [[_json_safe(v) for v in row] for row in rows]

        return QueryResponse(
            columns=columns,
            rows=safe_rows,
            row_count=len(safe_rows),
            truncated=len(safe_rows) >= effective_limit,
            duration_ms=duration,
        )

    except duckdb.ParserException as e:
        raise HTTPException(400, f"SQL syntax error: {e}")
    except duckdb.BinderException as e:
        raise HTTPException(400, f"SQL error: {e}")
    except duckdb.CatalogException as e:
        raise HTTPException(404, f"Table or column not found: {e}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Query failed: {e}")


@router.get("/tables")
async def list_tables():
    """List all tables available for querying."""
    try:
        conn = get_conn(read_only=True)
        result = conn.execute(
            """
            SELECT table_schema, table_name, table_type
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
            ORDER BY table_schema, table_name
            """
        ).fetchall()
        conn.close()

        tables = [
            {
                "schema": schema,
                "name": name,
                "full_name": f"{schema}.{name}" if schema != "main" else name,
                "type": ttype.lower(),
            }
            for schema, name, ttype in result
        ]
        return {"tables": tables}

    except Exception as e:
        raise HTTPException(500, f"Cannot list tables: {e}")


@router.get("/columns/{table_name}")
async def list_columns(table_name: str):
    """List columns for a table."""
    try:
        conn = get_conn(read_only=True)
        if "." in table_name:
            schema, table = table_name.split(".", 1)
            where = f"table_schema = '{schema}' AND table_name = '{table}'"
        else:
            where = f"table_name = '{table_name}'"

        result = conn.execute(
            f"""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE {where}
            ORDER BY ordinal_position
            """
        ).fetchall()
        conn.close()

        columns = [
            {"name": name, "type": dtype, "nullable": nullable == "YES"}
            for name, dtype, nullable in result
        ]
        return {"table": table_name, "columns": columns}

    except Exception as e:
        raise HTTPException(500, f"Cannot list columns: {e}")


def _json_safe(value):
    if value is None:
        return None
    if isinstance(value, (int, float, str, bool)):
        return value
    if isinstance(value, bytes):
        return value.hex()
    return str(value)
