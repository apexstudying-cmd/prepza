"""Restricted browser controller for the Prepza MCP server.

The browser is deliberately scoped to the Prepza production/test host. It does
not accept arbitrary external URLs, credentials, raw browser protocol commands,
or filesystem paths. The MCP layer remains the authorization boundary.
"""

from __future__ import annotations

import asyncio
import base64
import os
import subprocess
import sys
from urllib.parse import urlparse

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright


BASE_URL = os.environ.get("PREPZA_BROWSER_BASE_URL", "https://prepza-sf60.onrender.com").rstrip("/")
parsed_base = urlparse(BASE_URL)
ALLOWED_HOSTS = {
    host.strip().lower()
    for host in os.environ.get("PREPZA_BROWSER_ALLOWED_HOSTS", parsed_base.netloc).split(",")
    if host.strip()
}

MAX_SCREENSHOT_BYTES = 6 * 1024 * 1024
MAX_TEXT_CHARS = 40_000

_playwright: Playwright | None = None
_browser: Browser | None = None
_context: BrowserContext | None = None
_page: Page | None = None
_lock = asyncio.Lock()
_console_errors: list[str] = []


def _validate_url(url: str) -> str:
    candidate = urlparse(url if url.startswith(("http://", "https://")) else f"{BASE_URL}/{url.lstrip('/')}")
    if candidate.scheme != "https":
        raise ValueError("Browser navigation only permits HTTPS URLs.")
    if candidate.netloc.lower() not in ALLOWED_HOSTS:
        raise ValueError("Navigation is restricted to the configured Prepza host.")
    return candidate.geturl()


def _install_browser_if_missing() -> None:
    """Install Chromium lazily so the existing Render build remains lightweight."""
    global _browser
    if _browser is not None:
        return
    env = dict(os.environ)
    env.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/tmp/prepza-playwright")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except subprocess.SubprocessError as exc:
        raise RuntimeError("Unable to bootstrap the Prepza browser runtime.") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "browser install failed")[-1200:]
        raise RuntimeError(f"Unable to bootstrap Chromium: {detail}")
    os.environ.update({"PLAYWRIGHT_BROWSERS_PATH": env["PLAYWRIGHT_BROWSERS_PATH"]})


def _record_console(message: object) -> None:
    text = str(message)
    if len(_console_errors) < 100:
        _console_errors.append(text[:1000])


async def _ensure_browser() -> Page:
    global _playwright, _browser, _context, _page
    if _page and not _page.is_closed():
        return _page
    if _playwright is None:
        _playwright = await async_playwright().start()
    if _browser is None or not _browser.is_connected():
        try:
            _browser = await _playwright.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
        except Exception:
            _install_browser_if_missing()
            _browser = await _playwright.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
    if _context is None:
        _context = await _browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1)
        _context.set_default_timeout(10_000)
    _page = await _context.new_page()
    _page.on("console", lambda message: _record_console(message.text) if message.type == "error" else None)
    _page.on("pageerror", lambda error: _record_console(f"pageerror: {error}"))
    return _page


async def navigate(url: str) -> dict:
    async with _lock:
        page = await _ensure_browser()
        target = _validate_url(url)
        response = await page.goto(target, wait_until="domcontentloaded", timeout=30_000)
        return {
            "url": page.url,
            "title": await page.title(),
            "status": response.status if response else None,
        }


async def snapshot() -> dict:
    async with _lock:
        page = await _ensure_browser()
        text = (await page.locator("body").inner_text())[:MAX_TEXT_CHARS]
        aria = await page.aria_snapshot(mode="ai", depth=8)
        return {"url": page.url, "title": await page.title(), "text": text, "aria": aria}


async def screenshot(full_page: bool = False) -> bytes:
    async with _lock:
        page = await _ensure_browser()
        data = await page.screenshot(full_page=full_page, type="png", animations="disabled")
        if len(data) > MAX_SCREENSHOT_BYTES:
            raise ValueError("Screenshot exceeds the MCP safety size limit.")
        return data


async def click(selector: str) -> dict:
    async with _lock:
        page = await _ensure_browser()
        await page.locator(selector).first.click()
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=5_000)
        except Exception:
            pass
        return {"url": page.url, "title": await page.title()}


async def fill(selector: str, value: str) -> dict:
    async with _lock:
        page = await _ensure_browser()
        await page.locator(selector).first.fill(value)
        return {"url": page.url, "selector": selector, "filled": True}


async def press(selector: str, key: str) -> dict:
    async with _lock:
        page = await _ensure_browser()
        await page.locator(selector).first.press(key)
        return {"url": page.url, "key": key}


async def scroll(direction: str = "down", amount: int = 650) -> dict:
    if direction not in {"up", "down"}:
        raise ValueError("direction must be 'up' or 'down'.")
    amount = max(50, min(int(amount), 2000))
    delta = amount if direction == "down" else -amount
    async with _lock:
        page = await _ensure_browser()
        await page.mouse.wheel(0, delta)
        return await page.evaluate("({y: window.scrollY, height: document.documentElement.scrollHeight, viewport: window.innerHeight})")


async def set_viewport(width: int, height: int) -> dict:
    if not (320 <= width <= 2560 and 480 <= height <= 1800):
        raise ValueError("Viewport is outside the supported safety range.")
    async with _lock:
        page = await _ensure_browser()
        await page.set_viewport_size({"width": width, "height": height})
        return {"width": width, "height": height, "url": page.url}


async def reload() -> dict:
    async with _lock:
        page = await _ensure_browser()
        response = await page.reload(wait_until="domcontentloaded", timeout=30_000)
        return {"url": page.url, "title": await page.title(), "status": response.status if response else None}


async def back() -> dict:
    async with _lock:
        page = await _ensure_browser()
        response = await page.go_back(wait_until="domcontentloaded", timeout=15_000)
        return {"url": page.url, "title": await page.title(), "status": response.status if response else None}


async def console_and_errors() -> dict:
    async with _lock:
        page = await _ensure_browser()
        return {
            "url": page.url,
            "consoleErrors": list(_console_errors[-50:]),
            "bodyText": (await page.locator("body").inner_text())[:2000],
        }


async def close() -> None:
    global _playwright, _browser, _context, _page, _console_errors
    async with _lock:
        if _context:
            await _context.close()
        if _browser:
            await _browser.close()
        if _playwright:
            await _playwright.stop()
        _playwright = _browser = _context = _page = None
        _console_errors = []


def screenshot_base64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")
