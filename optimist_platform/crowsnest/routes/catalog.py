"""
Catalog route — builds a data catalog from Elementary's warehouse tables.
"""

from fastapi import APIRouter, HTTPException
import duckdb

from optimist_platform.crowsnest.config import get_config
from optimist_platform.crowsnest.db import get_conn

router = APIRouter()


def _schema() -> str:
    return get_config().elementary_schema


@router.get("/models")
async def get_models(search: str | None = None):
    """List all dbt models with metadata from Elementary."""
    conn = get_conn(read_only=True)
    try:
        query = f"""
            SELECT
                unique_id,
                alias,
                schema_name,
                database_name,
                description,
                owner,
                tags,
                package_name,
                path
            FROM {_schema()}.dbt_models
        """
        if search:
            query += f" WHERE alias ILIKE '%{search}%' OR description ILIKE '%{search}%'"
        query += " ORDER BY alias"

        results = conn.execute(query).fetchdf()
        models = [
            {
                "unique_id": row.get("unique_id"),
                "name": row.get("alias"),
                "schema": row.get("schema_name"),
                "database": row.get("database_name"),
                "description": row.get("description"),
                "owner": row.get("owner"),
                "tags": row.get("tags"),
                "package": row.get("package_name"),
                "path": row.get("path"),
            }
            for _, row in results.iterrows()
        ]
        return {"models": models, "total": len(models)}

    except duckdb.CatalogException:
        return await _fallback_models(conn, search)
    finally:
        conn.close()


@router.get("/models/{model_name}")
async def get_model_detail(model_name: str):
    """Detailed view of a model including columns and test coverage."""
    conn = get_conn(read_only=True)
    try:
        model = conn.execute(
            f"SELECT * FROM {_schema()}.dbt_models WHERE alias = ? LIMIT 1",
            [model_name],
        ).fetchdf()

        if model.empty:
            raise HTTPException(404, f"Model '{model_name}' not found")

        model_data = model.to_dict(orient="records")[0]

        try:
            columns = conn.execute(
                f"""
                SELECT column_name, data_type, description
                FROM {_schema()}.dbt_columns
                WHERE model_unique_id = ?
                ORDER BY column_name
                """,
                [model_data.get("unique_id")],
            ).fetchdf()
            column_list = columns.to_dict(orient="records")
        except duckdb.CatalogException:
            column_list = []

        try:
            tests = conn.execute(
                f"""
                SELECT test_name, test_type, status, column_name, test_timestamp
                FROM {_schema()}.elementary_test_results
                WHERE table_name = ?
                ORDER BY test_timestamp DESC
                LIMIT 50
                """,
                [model_name],
            ).fetchdf()
            test_list = tests.to_dict(orient="records")
        except duckdb.CatalogException:
            test_list = []

        return {
            "model": {
                "name": model_data.get("alias"),
                "unique_id": model_data.get("unique_id"),
                "schema": model_data.get("schema_name"),
                "database": model_data.get("database_name"),
                "description": model_data.get("description"),
                "owner": model_data.get("owner"),
                "tags": model_data.get("tags"),
                "path": model_data.get("path"),
            },
            "columns": column_list,
            "recent_tests": test_list,
        }

    except duckdb.CatalogException:
        raise HTTPException(404, "Elementary catalog tables not found")
    finally:
        conn.close()


@router.get("/sources")
async def get_sources():
    """List all dbt sources from Elementary metadata."""
    conn = get_conn(read_only=True)
    try:
        results = conn.execute(
            f"""
            SELECT unique_id, source_name, name, schema_name, database_name, description, owner, tags
            FROM {_schema()}.dbt_sources
            ORDER BY source_name, name
            """
        ).fetchdf()
        return {"sources": results.to_dict(orient="records")}

    except duckdb.CatalogException:
        return {"sources": [], "error": "Elementary source tables not found"}
    finally:
        conn.close()


@router.get("/search")
async def search_catalog(q: str):
    """Search across models and sources."""
    conn = get_conn(read_only=True)
    results = []

    try:
        models = conn.execute(
            f"""
            SELECT 'model' as type, alias as name, description
            FROM {_schema()}.dbt_models
            WHERE alias ILIKE ? OR description ILIKE ?
            LIMIT 20
            """,
            [f"%{q}%", f"%{q}%"],
        ).fetchall()
        results.extend([{"type": t, "name": n, "description": d} for t, n, d in models])
    except duckdb.CatalogException:
        pass

    try:
        sources = conn.execute(
            f"""
            SELECT 'source' as type, name, description
            FROM {_schema()}.dbt_sources
            WHERE name ILIKE ? OR description ILIKE ?
            LIMIT 20
            """,
            [f"%{q}%", f"%{q}%"],
        ).fetchall()
        results.extend([{"type": t, "name": n, "description": d} for t, n, d in sources])
    except duckdb.CatalogException:
        pass

    conn.close()
    return {"query": q, "results": results}


async def _fallback_models(conn, search: str | None = None):
    """List tables from information_schema when Elementary is not available."""
    try:
        query = """
            SELECT table_schema as schema_name, table_name as name, table_type as type
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
        """
        if search:
            query += f" AND table_name ILIKE '%{search}%'"
        query += " ORDER BY table_schema, table_name"

        results = conn.execute(query).fetchall()
        models = [
            {"name": name, "schema": schema, "type": ttype, "description": None, "source": "information_schema"}
            for schema, name, ttype in results
        ]
        return {"models": models, "total": len(models), "source": "information_schema"}
    except Exception:
        return {"models": [], "total": 0}
