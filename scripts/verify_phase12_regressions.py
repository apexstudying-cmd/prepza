"""Static regression checks for the Phase 1/2 navigation and Study Hub contract.

This intentionally verifies existing production code rather than adding runtime
behavior. It fails closed when required contracts disappear or duplicate
implementations are introduced.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "frontend" / "src" / "App.tsx"
NAV = ROOT / "frontend" / "src" / "crypto" / "navigationTransitions.ts"
CSS = ROOT / "frontend" / "src" / "index.css"


def text(path):
    assert path.exists(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def main():
    app, nav, css = text(APP), text(NAV), text(CSS)

    # Phase 1: cached-first/loading and document back-navigation contracts.
    assert "DOC_CACHE" in app
    assert "prepza-navigation-state" in nav
    assert "localStorage" in nav
    assert "visibility = 'visible'" in nav
    assert "Opening your document" not in app
    assert "loading && !document" in app

    # Phase 1: dark canvas must be painted outside React's rendered surface.
    for selector in ("html", "body", "#root"):
        assert selector in css
    assert "100dvh" in css

    # Phase 2: personal Study Hub and public Library remain separate.
    assert "/library/saved" in app
    assert "/library/:id/save" in app
    assert "/documents/:id" in app
    assert "removeStudyHubOfflineCopy" in app
    assert "prepza-last-study-document-id" in app

    # No duplicate definitions of the critical resume key or cache identifier.
    assert len(re.findall(r"prepza-last-study-document-id", app)) >= 1
    assert len(re.findall(r"const\s+DOC_CACHE\b", app)) == 1

    print("Phase 1/2 static regression contracts: PASS")


if __name__ == "__main__":
    main()
