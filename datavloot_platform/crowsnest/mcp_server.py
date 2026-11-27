"""
The Crows Nest's MCP server on /mcp (#67), for an agent such as Claude Code, or a
chat front end later. It calls no model itself.

Read-only: the tools call what the API routes call, so an agent gets what the
dashboard shows and is refused what the read-only SQL editor refuses, whatever
CROWSNEST_SQL_WRITE says. Text in the lake can instruct the model; read-only
limits that to what the user could already see.

Needs the `mcp` extra. CROWSNEST_MCP_TOOLS lists the tools that are on, all of
them when unset; empty turns the server off.
"""

import asyncio
import os

from fastapi import HTTPException

from datavloot_platform.crowsnest.config import is_loopback
from datavloot_platform.crowsnest.routes import catalog, pipelines, query

def installed() -> bool:
    try:
        import mcp.server.mcpserver  # noqa: F401
    except ImportError:
        return False
    return True


def enabled_tools() -> tuple[str, ...]:
    setting = os.environ.get("CROWSNEST_MCP_TOOLS")
    if setting is None:
        return TOOLS
    names = tuple(name.strip() for name in setting.split(",") if name.strip())
    unknown = [name for name in names if name not in TOOLS]
    if unknown:
        raise ValueError(
            f"CROWSNEST_MCP_TOOLS names {', '.join(unknown)}, which is no tool here: "
            f"use any of {', '.join(TOOLS)}, or leave it empty to turn the MCP server off."
        )
    return names


def _refused(e: HTTPException):
    from mcp.server.mcpserver.exceptions import ToolError

    # The route's own message, which tells the model what to change.
    return ToolError(str(e.detail))


async def query_tool(sql: str, limit: int = 1000) -> dict:
    """
    Run one read-only SQL statement (DuckDB) against the lake and return its rows.

    One statement at a time; writes, COPY, ATTACH, INSTALL and EXPLAIN ANALYZE are
    refused. Rows are capped as in the SQL editor; `truncated` says whether there
    were more.
    """
    try:
        statement = query._validate(sql.strip(), read_only="the MCP server only reads.")
        result = await asyncio.to_thread(query.run_read, statement.query, limit)
    except HTTPException as e:
        raise _refused(e) from None
    return result.model_dump(include={"columns", "rows", "row_count", "truncated"})


async def catalog_tool(table: str | None = None, search: str | None = None) -> dict:
    """
    The tables dbt knows of, with their descriptions. With `table`, that table's
    columns with their types and descriptions. `search` filters the list on name
    and description.
    """
    try:
        if table:
            return await asyncio.to_thread(catalog.get_model_detail, table)
        return await asyncio.to_thread(catalog.get_models, search)
    except HTTPException as e:
        raise _refused(e) from None


async def runs_tool(limit: int = 20) -> dict:
    """Recent pipeline runs with their status, and for a failed run what went wrong."""
    try:
        return await pipelines.get_recent_runs(limit=limit, errors=True)
    except HTTPException as e:
        raise _refused(e) from None


_FUNCTIONS = {"query": query_tool, "catalog": catalog_tool, "runs": runs_tool}
TOOLS = tuple(_FUNCTIONS)


def build(host: str | None):
    """
    The MCP server and the ASGI app to route /mcp to, or None when it is off or
    the `mcp` extra is not installed.
    """
    tools = enabled_tools()
    if not tools or not installed():
        return None
    from mcp.server.mcpserver import MCPServer
    from mcp.server.streamable_http_manager import StreamableHTTPASGIApp
    from mcp.server.transport_security import TransportSecuritySettings

    # The SDK sets up logging for the whole process (logging.basicConfig); at its
    # default, INFO, every request the Crows Nest makes to Dagster would be logged.
    server = MCPServer("Crows Nest", log_level="WARNING")
    for name in tools:
        server.add_tool(_FUNCTIONS[name], name=name)

    if is_loopback(host):
        # No sign-in on a laptop, so a web page in the user's browser must not
        # reach /mcp: refuse any Origin (agents send none, and the dashboard does
        # not use /mcp), and any Host but a loopback one, which a name rebound to
        # 127.0.0.1 would send.
        security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[
                "127.0.0.1", "localhost", "[::1]",  # port 80
                "127.0.0.1:*", "localhost:*", "[::1]:*",
            ],
            allowed_origins=[],
        )
    else:
        # Elsewhere the sign-in in front of the Crows Nest is the boundary, and
        # the app does not know the name it is reached under. Explicit, because
        # left unset the SDK assumes 127.0.0.1.
        security = TransportSecuritySettings(enable_dns_rebinding_protection=False)

    # Stateless with plain JSON answers: every tool call stands alone. Called for
    # the session manager it sets up; its own app is not used, because /mcp is a
    # route of the Crows Nest itself, which answers there without a redirect to /mcp/.
    server.streamable_http_app(stateless_http=True, json_response=True, transport_security=security)
    return server, StreamableHTTPASGIApp(server.session_manager)
