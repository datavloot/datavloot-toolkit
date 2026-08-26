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
from datavloot_platform.crowsnest.routes import pipelines, quality, query, catalog, notebooks

STATIC_DIR = pathlib.Path(__file__).parent / "static"
FRONTEND_DIR = pathlib.Path(__file__).parent / "frontend"

# Build inputs that affect static/.  Only these directories are walked — never
# node_modules, .next, or out.
_SOURCE_DIRS = ("app", "components", "lib")
_SOURCE_FILES = (
    "next.config.js",
    "package.json",
    "postcss.config.js",
    "tailwind.config.js",
)

_STALE_WARNING = """
  !!  Crows Nest is serving a STALE frontend build.

      Newest source:  {source} ({age})
      Newest static/: {static}

      static/ is what this server actually serves, so the browser will show the
      PREVIOUS UI -- edits to the frontend source will look like they did nothing.

      Rebuild and deploy:
        cd datavloot_platform/crowsnest/frontend
        npm run build
        rm -rf ../static/* && cp -r out/* ../static/
"""


def _newest_mtime(paths):
    """Return (mtime, path) for the most recently modified file in paths."""
    newest, newest_path = 0.0, None
    for path in paths:
        try:
            if not path.is_file():
                continue
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime > newest:
            newest, newest_path = mtime, path
    return newest, newest_path


def _source_files():
    for dirname in _SOURCE_DIRS:
        directory = FRONTEND_DIR / dirname
        if directory.is_dir():
            yield from directory.rglob("*")
    for filename in _SOURCE_FILES:
        yield FRONTEND_DIR / filename


def check_static_freshness():
    """
    Return a warning message if static/ is older than the frontend source, else None.

    static/ is a committed build artifact -- the thing this app serves -- while
    frontend/ next to it is only the build input.  `npm run build` writes to
    frontend/out/, so editing the source and rebuilding without copying out/ into
    static/ leaves the server quietly serving an older UI.  That failure is silent
    and indistinguishable from a change not working, so it is worth catching here.

    Returns None when frontend/ is absent, which is the normal case for an
    installed package, and never raises -- a broken check must not stop the server.
    """
    try:
        if not FRONTEND_DIR.is_dir() or not STATIC_DIR.is_dir():
            return None

        source_mtime, source_path = _newest_mtime(_source_files())
        static_mtime, static_path = _newest_mtime(STATIC_DIR.rglob("*"))

        if not source_path or not static_path or source_mtime <= static_mtime:
            return None

        hours = (source_mtime - static_mtime) / 3600
        age = f"{hours:.0f}h newer" if hours < 48 else f"{hours / 24:.0f} days newer"
        return _STALE_WARNING.format(
            source=source_path.relative_to(FRONTEND_DIR).as_posix(),
            static=static_path.relative_to(STATIC_DIR).as_posix(),
            age=age,
        )
    except Exception:
        return None


class _CacheControlledStatic(StaticFiles):
    """
    StaticFiles sends no Cache-Control at all, which lets browsers apply heuristic
    caching to index.html -- quietly reusing a stale shell that points at chunk
    hashes from an older build.  The page then renders entirely from cache and looks
    like a deploy that did not take effect.

    Chunk filenames under _next/static are content-hashed, so they are immutable and
    safe to cache forever; the HTML shell that references them must always revalidate.
    """

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("text/html"):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        elif "_next/static" in str(path).replace("\\", "/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


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
    app.include_router(notebooks.router, prefix="/api/notebooks", tags=["Notebooks"])

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

    warning = check_static_freshness()
    if warning:
        print(warning)

    # Mount pre-built frontend last so API routes take precedence.
    # If static/ hasn't been built yet, skip the mount and the API still works.
    if STATIC_DIR.exists() and any(STATIC_DIR.iterdir()):
        app.mount("/", _CacheControlledStatic(directory=str(STATIC_DIR), html=True), name="static")

    return app
