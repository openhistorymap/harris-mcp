"""Starlette entrypoint for the Harris Matrix MCP server.

Mirrors the layout used by sibling OHM MCP services (`mcp/gaia/app.py`,
`mcp/agent/app.py`): MCP is exposed at `/mcp` via SSE, `/` is a health
route.
"""

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from harris_mcp import __version__
from harris_mcp.server import mcp


async def health(request):
    return JSONResponse({
        "status": "Harris Matrix MCP server is running",
        "version": __version__,
    })


mcp_app = mcp.http_app(transport="sse", path="/sse")

app = Starlette(
    routes=[
        Route("/", health),
        Mount("/mcp", mcp_app),  # SSE stream at /mcp/sse
    ],
    lifespan=mcp_app.lifespan,
)

# Run via:
#   uvicorn app:app --reload --port 8000
