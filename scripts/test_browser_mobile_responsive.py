"""Mobile/tablet browser smoke test for responsive layout and navigation.

The test uses an isolated student fixture and real Chromium viewports. Screenshots
are retained as CI artifacts so a failure can be diagnosed visually rather than
only from a numeric assertion.
"""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

from test_browser_study_hub_offline_content import (
    BASE_URL,
    cleanup_fixture,
    create_fixture,
    login,
)

ARTIFACTS = Path("artifacts/mobile-responsive")
VIEWPORTS = (
    ("phone-small", 360, 800, True),
    ("phone-standard", 390, 844, True),
    ("tablet-portrait", 768, 1024, False),
)


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    fixture = create_fixture()
    failures: list[str] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                for name, width, height, mobile in VIEWPORTS:
                    context = browser.new_context(
                        viewport={"width": width, "height": height},
                        is_mobile=mobile,
                        has_touch=True,
                        device_scale_factor=1,
                    )
                    page = context.new_page()
                    page_errors: list[str] = []
                    page.on("pageerror", lambda error: page_errors.append(str(error)))
                    try:
                        login(page, fixture)
                        page.get_by_role(
                            "navigation", name="Primary navigation"
                        ).wait_for(state="visible", timeout=20000)
                        page.wait_for_timeout(300)
                        page.screenshot(
                            path=str(ARTIFACTS / f"{name}.png"),
                            full_page=True,
                            animations="disabled",
                        )

                        dimensions = page.evaluate(
                            """() => ({
                              viewportWidth: window.innerWidth,
                              documentWidth: document.documentElement.scrollWidth,
                              bodyWidth: document.body.scrollWidth,
                              viewportHeight: window.innerHeight
                            })"""
                        )
                        if dimensions["documentWidth"] > dimensions["viewportWidth"] + 1:
                            failures.append(
                                f"{name}: horizontal document overflow: {dimensions}"
                            )
                        if dimensions["bodyWidth"] > dimensions["viewportWidth"] + 1:
                            failures.append(
                                f"{name}: horizontal body overflow: {dimensions}"
                            )

                        nav = page.get_by_role("navigation", name="Primary navigation")
                        if not nav.is_visible():
                            failures.append(f"{name}: primary navigation is not visible")
                        elif nav.bounding_box() is None:
                            failures.append(f"{name}: primary navigation has no layout box")
                        else:
                            nav_buttons = nav.get_by_role("button")
                            if nav_buttons.count() == 0:
                                failures.append(f"{name}: primary navigation has no buttons")
                            for index in range(nav_buttons.count()):
                                button = nav_buttons.nth(index)
                                label = button.get_attribute("aria-label") or ""
                                bounds = button.bounding_box()
                                if not label.strip():
                                    failures.append(f"{name}: navigation button {index} has no accessible name")
                                if bounds and (bounds["width"] < 44 or bounds["height"] < 44):
                                    failures.append(
                                        f"{name}: navigation target {label!r} is smaller than 44x44 CSS px: {bounds}"
                                    )

                        if page_errors:
                            failures.append(
                                f"{name}: uncaught browser errors: {' | '.join(page_errors)}"
                            )

                        print(
                            f"{name}: viewport={width}x{height}, "
                            f"documentWidth={dimensions['documentWidth']}, "
                            f"bodyWidth={dimensions['bodyWidth']}, "
                            f"primaryNavVisible={nav.is_visible()}, "
                            f"pageErrors={len(page_errors)}"
                        )
                    except Exception as exc:
                        failures.append(f"{name}: {type(exc).__name__}: {exc}")
                        try:
                            page.screenshot(
                                path=str(ARTIFACTS / f"{name}-failure.png"),
                                full_page=True,
                                animations="disabled",
                            )
                        except Exception:
                            pass
                    finally:
                        context.close()
            finally:
                browser.close()
    finally:
        cleanup_fixture(fixture)

    if failures:
        print("MOBILE RESPONSIVE FAILURES:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Mobile/tablet responsive browser smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
