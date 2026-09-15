"""Remote MCP adapter for the protected Prepza control API and browser.

This service is intentionally separate from the main Flask app. ChatGPT talks
to this MCP server; the MCP server talks to Prepza's narrow internal control
API and a restricted Playwright browser. No database credentials, payment
operations, raw SQL, arbitrary external navigation, or unrestricted browser
protocol are exposed.
"""

import hmac
import os
from typing import Any

import httpx
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ImageContent, TextContent
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from browser import (
    back as browser_back,
    click as browser_click,
    close as browser_close,
    console_and_errors,
    fill as browser_fill,
    navigate as browser_navigate,
    press as browser_press,
    reload as browser_reload,
    screenshot as browser_screenshot,
    screenshot_base64,
    scroll as browser_scroll,
    set_viewport as browser_set_viewport,
    snapshot as browser_snapshot,
)


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
        "Read-only developer diagnostics plus a restricted Prepza browser. "
        "Never invent state. Inspect the live application before proposing UI fixes. "
        "The browser is limited to the configured Prepza host and has no credential, "
        "payment, database, filesystem, arbitrary URL, or raw browser-protocol tools."
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


@mcp.tool()
async def prepza_browser_open(url: str) -> dict[str, Any]:
    """Open a Prepza page in the controlled browser. Navigation is restricted to the configured Prepza host."""
    return await browser_navigate(url)


@mcp.tool()
async def prepza_browser_snapshot() -> dict[str, Any]:
    """Inspect the current live Prepza page using visible text and an accessibility-tree snapshot."""
    return await browser_snapshot()


@mcp.tool()
async def prepza_browser_screenshot(full_page: bool = False) -> list[ImageContent | TextContent]:
    """Capture the current live Prepza page so the model can visually inspect the rendered UI."""
    data = await browser_screenshot(full_page=full_page)
    return [
        ImageContent(type="image", data=screenshot_base64(data), mime_type="image/png"),
        TextContent(type="text", text="Screenshot captured from the restricted Prepza browser."),
    ]


@mcp.tool()
async def prepza_browser_click(selector: str) -> dict[str, Any]:
    """Click one CSS selector on the current Prepza page and report the resulting route/title."""
    return await browser_click(selector)


@mcp.tool()
async def prepza_browser_fill(selector: str, value: str) -> dict[str, Any]:
    """Fill a non-sensitive form field on the current Prepza page. Do not use this for passwords or secrets."""
    if any(token in selector.lower() for token in ("password", "token", "secret", "card", "cvv", "authorization")):
        raise ValueError("Sensitive credential/payment fields are blocked by the Prepza browser connector.")
    return await browser_fill(selector, value)


@mcp.tool()
async def prepza_browser_press(selector: str, key: str) -> dict[str, Any]:
    """Press a keyboard key on a selected Prepza element."""
    return await browser_press(selector, key)


@mcp.tool()
async def prepza_browser_scroll(direction: str = "down", amount: int = 650) -> dict[str, Any]:
    """Scroll the current Prepza page by a bounded amount."""
    return await browser_scroll(direction, amount)


@mcp.tool()
async def prepza_browser_set_viewport(width: int, height: int) -> dict[str, Any]:
    """Set the browser viewport for responsive UI verification within a safe size range."""
    return await browser_set_viewport(width, height)


@mcp.tool()
async def prepza_browser_reload() -> dict[str, Any]:
    """Reload the current Prepza page and report the resulting route/title/status."""
    return await browser_reload()


@mcp.tool()
async def prepza_browser_back() -> dict[str, Any]:
    """Go back one browser history entry on Prepza."""
    return await browser_back()


@mcp.tool()
async def prepza_browser_errors() -> dict[str, Any]:
    """Inspect the current Prepza page for browser-side diagnostic state."""
    return await console_and_errors()


@mcp.tool()
async def prepza_browser_close() -> dict[str, str]:
    """Close the controlled browser session and discard its in-memory state."""
    await browser_close()
    return {"status": "closed"}


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
