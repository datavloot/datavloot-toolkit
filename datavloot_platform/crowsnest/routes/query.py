"""
SQL query route — executes read-only queries against DuckDB.

Two rules replace what used to be here:

  * what may run is decided by parsing, not by inspecting the first word
  * how many rows come back is decided when fetching, not by editing the SQL

The old version matched `sql.split()[0].upper()` against a set of forbidden
keywords, which a leading comment, a leading paren, or anything after a semicolon
walks straight past -- and it never saw `COPY ... TO`, which writes files. It also
appended `LIMIT n` to the query text when the string "LIMIT" did not appear
anywhere in it, so `select 'LIMIT'` returned uncapped and a trailing semicolon
produced `select 1; LIMIT 1000`, a syntax error for anyone who types SQL normally.

The filesystem itself is closed off one level down, in db.py.
"""

import time

import duckdb
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from datavloot_platform.crowsnest.db import get_conn

router = APIRouter()

MAX_ROWS = 10_000

# DuckDB reports `select`, `show`, `describe`, `pragma` and CTE queries all as
# SELECT, which is exactly the read surface a query editor wants. Everything that
# writes, attaches, installs or configures gets its own type and is refused.
# EXPLAIN is allowed as a reading aid; the connection is read-only, so an
# EXPLAIN ANALYZE of a write cannot execute one.
_ALLOWED_STATEMENTS = {
    duckdb.StatementType.SELECT,
    duckdb.StatementType.EXPLAIN,
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


def _validate(sql: str) -> str:
    """
    Return the single read statement to run, or raise.

    Parsing is the check: one statement, and its type must be in the allowlist.
    """
    try:
        statements = duckdb.extract_statements(sql)
    except Exception as e:
        raise HTTPException(400, f"SQL syntax error: {e}")

    if not statements:
        raise HTTPException(400, "Empty query")
    if len(statements) > 1:
        raise HTTPException(
            400,
            f"One statement at a time — got {len(statements)}. "
            "Run them separately.",
        )

    statement = statements[0]
    if statement.type not in _ALLOWED_STATEMENTS:
        raise HTTPException(
            403,
            f"{statement.type.name} statements are not allowed in the query editor, "
            "which is read-only. Use dbt for transformations.",
        )
    return statement.query


@router.post("/execute", response_model=QueryResponse)
async def execute_query(req: QueryRequest):
    """Execute a read-only SQL query and return results as columns + rows."""
    sql = _validate(req.sql.strip())
    effective_limit = max(1, min(req.limit, MAX_ROWS))

    conn = None
    try:
        conn = get_conn(read_only=True)
        start = time.monotonic()

        result = conn.execute(sql)
        # Cap while fetching rather than by appending LIMIT to the query text.
        # One extra row tells us whether there were more, and no rewriting means
        # no statement shape can slip past the cap.
        rows = result.fetchmany(effective_limit + 1)
        truncated = len(rows) > effective_limit
        rows = rows[:effective_limit]

        columns = [desc[0] for desc in result.description]
        duration = round((time.monotonic() - start) * 1000, 1)

        return QueryResponse(
            columns=columns,
            rows=[[_json_safe(v) for v in row] for row in rows],
            row_count=len(rows),
            truncated=truncated,
            duration_ms=duration,
        )

    except duckdb.ParserException as e:
        raise HTTPException(400, f"SQL syntax error: {e}")
    except duckdb.BinderException as e:
        raise HTTPException(400, f"SQL error: {e}")
    except duckdb.CatalogException as e:
        raise HTTPException(404, f"Table or column not found: {e}")
    except duckdb.PermissionException as e:
        # The db.py sandbox refusing a filesystem or extension access.
        raise HTTPException(403, f"Not permitted: {e}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Query failed: {e}")
    finally:
        if conn is not None:
            conn.close()


@router.get("/tables")
async def list_tables():
    """List all tables available for querying."""
    conn = None
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

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Cannot list tables: {e}")
    finally:
        if conn is not None:
            conn.close()


@router.get("/columns/{table_name}")
async def list_columns(table_name: str):
    """
    List columns for a table.

    table_name arrives from the URL and is bound as a parameter, never
    interpolated: it used to be spliced into the WHERE clause, so
    `/api/query/columns/x' OR '1'='1` was an injection on an endpoint the
    statement check never saw.
    """
    conn = None
    try:
        conn = get_conn(read_only=True)
        if "." in table_name:
            schema, table = table_name.split(".", 1)
            where, params = "table_schema = ? AND table_name = ?", [schema, table]
        else:
            where, params = "table_name = ?", [table_name]

        result = conn.execute(
            f"""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE {where}
            ORDER BY ordinal_position
            """,
            params,
        ).fetchall()

        columns = [
            {"name": name, "type": dtype, "nullable": nullable == "YES"}
            for name, dtype, nullable in result
        ]
        return {"table": table_name, "columns": columns}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Cannot list columns: {e}")
    finally:
        if conn is not None:
            conn.close()


def _json_safe(value):
    if value is None:
        return None
    if isinstance(value, (int, float, str, bool)):
        return value
    if isinstance(value, bytes):
        return value.hex()
    return str(value)
