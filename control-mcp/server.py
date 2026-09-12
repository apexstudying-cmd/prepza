"""Remote MCP adapter for the protected Prepza control API.

This service is intentionally separate from the main Flask app. ChatGPT talks
to this MCP server; the MCP server talks to Prepza's narrow internal control
API. No database credentials live here and no write tools are exposed.
"""

import hmac
import os
from typing import Any

import httpx
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings


PREPZA_API_BASE_URL = os.environ.get("PREPZA_API_BASE_URL", "https://prepza-sf60.onrender.com").rstrip("/")
PREPZA_CONTROL_TOKEN = os.environ.get("PREPZA_CONTROL_TOKEN", "").strip()
MCP_ACCESS_TOKEN = os.environ.get("PREPZA_MCP_ACCESS_TOKEN", "").strip()
MCP_HOSTNAME = os.environ.get("PREPZA_MCP_HOSTNAME", "").strip()

if not PREPZA_CONTROL_TOKEN:
    raise RuntimeError("PREPZA_CONTROL_TOKEN is required")
if not MCP_ACCESS_TOKEN:
    raise RuntimeError("PREPZA_MCP_ACCESS_TOKEN is required")
if not MCP_HOSTNAME:
    raise RuntimeError("PREPZA_MCP_HOSTNAME is required")


async def _prepza_get(path: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {PREPZA_CONTROL_TOKEN}"}
    async with httpx.AsyncClient(base_url=PREPZA_API_BASE_URL, timeout=15.0, follow_redirects=False) as client:
        response = await client.get(path, headers=headers)
    if response.status_code >= 400:
        try:
            detail = response.json()
        except ValueError:
            detail = {"error": response.text[:300]}
        raise RuntimeError(f"Prepza control API returned {response.status_code}: {detail}")
    return response.json()


mcp = MCPServer(
    "Prepza Control",
    instructions=(
        "Read-only developer diagnostics for Prepza. Never invent state. "
        "Use the narrow diagnostics tools before proposing changes. "
        "This server intentionally exposes no write, delete, payment, credential, "
        "or raw-database tools."
    ),
)


@mcp.tool()
async def prepza_health() -> dict[str, Any]:
    """Check whether the Prepza control connection is currently enabled and healthy."""
    return await _prepza_get("/internal/control/v1/health")


@mcp.tool()
async def prepza_status() -> dict[str, Any]:
    """Return the current read-only control connection capabilities."""
    return await _prepza_get("/internal/control/v1/status")


@mcp.tool()
async def prepza_system_overview() -> dict[str, Any]:
    """Return high-level Prepza counts for users, documents, and generated materials."""
    return await _prepza_get("/internal/control/v1/system/overview")


@mcp.tool()
async def prepza_user_summary(user_id: int) -> dict[str, Any]:
    """Return a privacy-limited summary for one Prepza user; credentials and contact secrets are excluded."""
    return await _prepza_get(f"/internal/control/v1/users/{user_id}/summary")


@mcp.tool()
async def prepza_document_summary(document_id: int) -> dict[str, Any]:
    """Return metadata and processing state for one Prepza document, without exposing its file contents."""
    return await _prepza_get(f"/internal/control/v1/documents/{document_id}/summary")


@mcp.tool()
async def prepza_document_materials(document_id: int) -> dict[str, Any]:
    """Return generated-material status, scope, parameters, and errors for one document, without payload contents."""
    return await _prepza_get(f"/internal/control/v1/documents/{document_id}/materials")


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> Response:
    return JSONResponse({"status": "ok", "service": "prepza-control-mcp"})


class MCPBearerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path == "/health":
            return await call_next(request)
        authorization = request.headers.get("authorization", "")
        scheme, _, supplied = authorization.partition(" ")
        if scheme.lower() != "bearer" or not supplied or not hmac.compare_digest(supplied, MCP_ACCESS_TOKEN):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)


security = TransportSecuritySettings(
    allowed_hosts=[MCP_HOSTNAME, f"{MCP_HOSTNAME}:*"],
    allowed_origins=[f"https://{MCP_HOSTNAME}"],
)

app = mcp.streamable_http_app(
    transport_security=security,
    stateless_http=True,
)
app.add_middleware(MCPBearerMiddleware)
