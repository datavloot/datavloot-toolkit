"""
Crows Nest FastAPI application.

Serves the REST API at /api/* and the pre-built frontend static files at /*.
Both run on the same port so no CORS configuration is needed.
"""

import pathlib

import duckdb
import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from datavloot_platform.crowsnest.config import get_config
from datavloot_platform.crowsnest.routes import pipelines, quality, query, catalog

STATIC_DIR = pathlib.Path(__file__).parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Crows Nest",
        description="Unified dashboard for the Optimist data platform",
        version="0.1.0",
    )

    app.include_router(pipelines.router, prefix="/api/pipelines", tags=["Pipelines"])
    app.include_router(quality.router, prefix="/api/quality", tags=["Data Quality"])
    app.include_router(query.router, prefix="/api/query", tags=["SQL Query"])
    app.include_router(catalog.router, prefix="/api/catalog", tags=["Catalog"])

    @app.get("/api/health")
    async def health_check():
        """Live connectivity check for all platform services."""
        config = get_config()
        results: dict = {}

        # Dagster: probe the GraphQL endpoint
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.post(
                    config.dagster_graphql_url,
                    json={"query": "{ __typename }"},
                )
                results["dagster"] = "ok" if resp.status_code == 200 else "offline"
        except Exception:
            results["dagster"] = "offline"

        # DuckDB: try opening the file
        try:
            if config.duckdb_path == ":memory:":
                results["duckdb"] = "ok"
            else:
                conn = duckdb.connect(config.duckdb_path, read_only=True)
                conn.close()
                results["duckdb"] = "ok"
        except Exception:
            results["duckdb"] = "offline"

        # Marimo: probe its root URL
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(config.marimo_url)
                results["marimo"] = "ok" if resp.status_code < 500 else "offline"
        except Exception:
            results["marimo"] = "offline"

        return {"services": results}

    @app.get("/api/services")
    async def get_services():
        """Return live service URLs for the frontend to use."""
        config = get_config()
        return {
            "dagster_url": "http://localhost:3000",
            "marimo_url": config.marimo_url,
            "duckdb_path": config.duckdb_path,
        }

    # Mount pre-built frontend last so API routes take precedence.
    # If static/ hasn't been built yet, skip the mount and the API still works.
    if STATIC_DIR.exists() and any(STATIC_DIR.iterdir()):
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app
