"""Mobile/tablet browser smoke test for responsive layout and navigation.

The test uses an isolated student fixture and real Chromium viewports. Screenshots
are retained as CI artifacts so a failure can be diagnosed visually rather than
only from a numeric assertion.
"""
from __future__ import annotations

import base64
import json
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
                        browse_request_count = 0
                        cached_listing = {
                            "id": 990001,
                            "title": "QA cached listing",
                            "description": "Synthetic public browse fixture for cache regression.",
                            "category": "Electronics",
                            "condition": "good",
                            "price_kes": 1200,
                            "location_area": "Near campus",
                            "images": [],
                            "status": "active",
                            "seller_id": 990002,
                            "seller_name": "QA seller",
                            "whatsapp_url": None,
                            "saved": True,
                            "is_mine": True,
                            "posting_fee_kes": 100,
                            "posting_fee_paid": True,
                            "posting_fee_expires_at": "2099-01-01T00:00:00+00:00",
                            "posting_payment_reference": "must-not-survive-in-cache",
                            "posting_payment_review_note": "private payment review detail",
                            "moderation_note": "private moderation detail",
                        }

                        def shop_browse_route(route):
                            nonlocal browse_request_count
                            request = route.request
                            endpoint = request.url.split("?", 1)[0]
                            if request.method != "GET" or not endpoint.endswith("/api/shop/listings"):
                                route.continue_()
                                return
                            browse_request_count += 1
                            if browse_request_count == 1:
                                route.fulfill(
                                    status=200,
                                    content_type="application/json",
                                    body=json.dumps({"listings": [cached_listing]}),
                                )
                            else:
                                route.abort("failed")

                        page.route("**/api/shop/listings*", shop_browse_route)
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

                        broken_logos = page.locator('img[alt="Prepza"]').evaluate_all(
                            "(images) => images.filter(image => !image.complete || image.naturalWidth === 0).map(image => image.currentSrc || image.src)"
                        )
                        if broken_logos:
                            failures.append(
                                f"{name}: broken Prepza logo image(s): {' | '.join(broken_logos)}"
                            )

                        tool_icons = page.evaluate(
                            """() => {
                              const labels = ['Upload', 'My Study', 'Library', 'Ada', 'Shop'];
                              return labels.map(label => {
                                const button = Array.from(document.querySelectorAll('button')).find(
                                  candidate => Array.from(candidate.querySelectorAll('span')).some(
                                    span => span.textContent.trim() === label
                                  )
                                );
                                const iconBox = button?.querySelector('div');
                                return {
                                  label,
                                  found: Boolean(button),
                                  svgCount: iconBox?.querySelectorAll('svg').length || 0,
                                  iconText: (iconBox?.innerText || '').trim(),
                                };
                              });
                            }"""
                        )
                        for item in tool_icons:
                            if not item["found"] or item["svgCount"] == 0 or item["iconText"]:
                                failures.append(
                                    f"{name}: {item['label']} quick-action must use a non-text SVG icon: {item}"
                                )

                        # Exercise the actual Shop route at each responsive viewport,
                        # not just the Home shortcut's presence.
                        shop_button = page.get_by_role("button", name="Shop").first
                        shop_button.click(timeout=5000)
                        page.get_by_text(
                            "Find useful things near campus. Connect directly with sellers.",
                            exact=True,
                        ).wait_for(timeout=10000)
                        page.get_by_text("QA cached listing", exact=True).wait_for(timeout=5000)
                        shop_dimensions = page.evaluate(
                            """() => ({
                              viewportWidth: window.innerWidth,
                              documentWidth: document.documentElement.scrollWidth,
                              bodyWidth: document.body.scrollWidth
                            })"""
                        )
                        if shop_dimensions["documentWidth"] > shop_dimensions["viewportWidth"] + 1:
                            failures.append(f"{name}: Shop horizontal overflow: {shop_dimensions}")
                        if shop_dimensions["bodyWidth"] > shop_dimensions["viewportWidth"] + 1:
                            failures.append(f"{name}: Shop body overflow: {shop_dimensions}")
                        page.screenshot(
                            path=str(ARTIFACTS / f"shop-{name}.png"),
                            full_page=True,
                            animations="disabled",
                        )

                        # Prove an older same-query snapshot is shown while revalidation
                        # runs, and remains visible with a clear stale notice when offline.
                        page.get_by_role("button", name="‹ Home").click(timeout=5000)
                        page.get_by_role("navigation", name="Primary navigation").wait_for(state="visible", timeout=5000)
                        page.evaluate(
                            """() => {
                              const original = Date.now.bind(Date);
                              window.__prepzaOriginalDateNow = original;
                              Date.now = () => window.__prepzaOriginalDateNow() + 6 * 60 * 1000;
                            }"""
                        )
                        page.get_by_role("button", name="Shop").first.click(timeout=5000)
                        page.get_by_text("QA cached listing", exact=True).wait_for(timeout=5000)
                        page.get_by_role("alert").filter(
                            has_text="Showing recently viewed listings. Reconnect to refresh availability and status."
                        ).wait_for(timeout=5000)
                        page.evaluate(
                            """() => {
                              if (window.__prepzaOriginalDateNow) {
                                Date.now = window.__prepzaOriginalDateNow;
                                delete window.__prepzaOriginalDateNow;
                              }
                            }"""
                        )
                        page.screenshot(
                            path=str(ARTIFACTS / f"shop-stale-cache-{name}.png"),
                            full_page=True,
                            animations="disabled",
                        )

                        # Capture the real listing form and a selected-photo state.
                        page.get_by_role("button", name="Sell an item").click(timeout=5000)
                        page.get_by_role("heading", name="List a product").wait_for(timeout=10000)
                        page.get_by_text(
                            "Posting fee: KES 100 per listing, including your first.",
                            exact=False,
                        ).wait_for(timeout=5000)
                        upload_input = page.locator('input[type="file"]')
                        if upload_input.get_attribute("accept") != "image/jpeg,image/png,image/webp":
                            failures.append(f"{name}: listing photo input does not restrict accepted image formats")
                        upload_input.set_input_files({
                            "name": "calculator.png",
                            "mimeType": "image/png",
                            "buffer": base64.b64decode(
                                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/jP8AAAAASUVORK5CYII="
                            ),
                        })
                        page.get_by_text("1 photo(s) selected: calculator.png", exact=True).wait_for(timeout=5000)
                        page.screenshot(
                            path=str(ARTIFACTS / f"shop-listing-form-{name}.png"),
                            full_page=True,
                            animations="disabled",
                        )
                        page.get_by_role("button", name="‹ Back").click(timeout=5000)
                        page.get_by_role("button", name="‹ Home").click(timeout=5000)
                        page.get_by_role("navigation", name="Primary navigation").wait_for(state="visible", timeout=5000)

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
