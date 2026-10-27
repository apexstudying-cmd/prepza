"""End-to-end sponsored-ad viewability and prepaid-ledger regression.

Runs against the disposable PostgreSQL + real Flask + Chromium stack created by
mobile-responsive-browser.yml. No external provider or real payment is used.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from playwright.async_api import async_playwright

from test_browser_study_hub_offline_content import (
    BASE_URL,
    cleanup_fixture,
    create_fixture,
    login,
    run_container_python,
)

TITLE = "Prepza B2B browser ledger proof"
STYLE_ID = "prepza-b2b-offscreen-test-style"


def create_campaign_fixture(user_id: int) -> dict:
    code = f"""
import json
from datetime import datetime, timedelta
from app import app, db, User, Organisation, Opportunity
from sqlalchemy import text

with app.app_context():
    user = db.session.get(User, {int(user_id)})
    assert user is not None
    now = datetime.utcnow()

    organisation = Organisation(
        name="Browser QA Advertiser",
        description="Disposable B2B browser regression fixture",
        contact_email="b2b-browser@test.invalid",
        verification_status="verified",
        is_active=True,
        created_by=user.id,
        created_at=now,
        updated_at=now,
    )
    db.session.add(organisation)
    db.session.flush()

    opportunity = Opportunity(
        organisation_id=organisation.id,
        created_by=user.id,
        title={TITLE!r},
        description="Disposable sponsored-card browser regression.",
        opportunity_type="internship",
        location="Nairobi",
        is_remote=False,
        application_url="https://example.invalid/b2b-browser-qa",
        application_instructions="QA fixture only",
        application_deadline=now + timedelta(days=5),
        expiry_date=now + timedelta(days=20),
        status="published",
        published_at=now,
        view_count=0,
    )
    db.session.add(opportunity)
    db.session.flush()

    db.session.execute(text("""
        INSERT INTO student_opportunity_discovery
            (user_id, discoverable, consent_version, updated_at)
        VALUES (:uid, TRUE, 'g5-browser-test', CURRENT_TIMESTAMP)
        ON CONFLICT (user_id) DO UPDATE
        SET discoverable=TRUE, consent_version='g5-browser-test',
            updated_at=CURRENT_TIMESTAMP
    """), {"uid": user.id})
    db.session.execute(text("""
        INSERT INTO product_activity_day
            (user_id, activity_date, sessions, engaged_seconds, core_actions, last_seen_at)
        VALUES (:uid, CURRENT_DATE, 1, 180, 2, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id, activity_date) DO UPDATE
        SET engaged_seconds=GREATEST(product_activity_day.engaged_seconds, 180),
            core_actions=GREATEST(product_activity_day.core_actions, 2),
            last_seen_at=CURRENT_TIMESTAMP
    """), {"uid": user.id})

    snapshot = {
        "home_impression_cpm": {"value": {"amount_kes": 350, "per": 1000}, "version": "browser-qa-v1"},
        "click_cpc": {"value": {"amount_kes": 20}, "version": "browser-qa-v1"},
        "home_frequency_cap": {"value": {"max_impressions": 1000, "window_days": 7}, "version": "browser-qa-v1"},
        "click_frequency_cap": {"value": {"max_clicks": 1, "window_days": 1}, "version": "browser-qa-v1"}
    }
    campaign_id = db.session.execute(text("""
        INSERT INTO discovery_campaign
            (organisation_id, opportunity_id, name, objective, placement, status,
             budget_kes, bid_type, bid_kes, target_json, starts_at, ends_at,
             funding_status, funded_amount_minor, pricing_version, pricing_snapshot)
        VALUES
            (:oid, :opid, 'Browser QA sponsored ledger', 'reach', 'home_carousel', 'active',
             5000, 'both', 350, CAST(:target AS jsonb), :starts, :ends,
             'funded', 1000000, 'browser-qa-v1', CAST(:snapshot AS jsonb))
        RETURNING id
    """), {
        "oid": organisation.id,
        "opid": opportunity.id,
        "target": json.dumps({"billing_modes": ["cpm", "cpc"]}),
        "starts": now - timedelta(minutes=1),
        "ends": now + timedelta(days=1),
        "snapshot": json.dumps(snapshot),
    }).scalar_one()
    db.session.commit()
    print(json.dumps({
        "organisation_id": organisation.id,
        "opportunity_id": opportunity.id,
        "campaign_id": int(campaign_id),
        "user_id": int(user.id),
    }))
"""
    return json.loads(run_container_python(code).splitlines()[-1])


def read_campaign_state(campaign_id: int) -> dict:
    code = f"""
import json
from app import app, db
from sqlalchemy import text
with app.app_context():
    events = db.session.execute(text("""
        SELECT event_type, COUNT(*) AS count
        FROM discovery_event WHERE campaign_id=:cid
        GROUP BY event_type ORDER BY event_type
    """), {"cid": {int(campaign_id)}}).mappings().all()
    ledger = db.session.execute(text("""
        SELECT entry_type, signed_amount_minor, delivery_event_id, idempotency_key
        FROM b2b_campaign_ledger
        WHERE campaign_id=:cid AND entry_type IN ('delivery_impression','delivery_click')
        ORDER BY id
    """), {"cid": {int(campaign_id)}}).mappings().all()
    campaign = db.session.execute(text("""
        SELECT delivered_impressions, delivered_clicks, funded_amount_minor
        FROM discovery_campaign WHERE id=:cid
    """), {"cid": {int(campaign_id)}}).mappings().one()
    remaining = int(campaign["funded_amount_minor"]) + int(db.session.execute(text("""
        SELECT COALESCE(SUM(signed_amount_minor), 0)
        FROM b2b_campaign_ledger WHERE campaign_id=:cid
    """), {"cid": {int(campaign_id)}}).scalar_one())
    print(json.dumps({
        "events": [dict(row) for row in events],
        "ledger": [dict(row) for row in ledger],
        "delivered_impressions": int(campaign["delivered_impressions"]),
        "delivered_clicks": int(campaign["delivered_clicks"]),
        "remaining_minor": remaining,
    }))
"""
    return json.loads(run_container_python(code).splitlines()[-1])


def cleanup_campaign_fixture(ids: dict) -> None:
    code = f"""
from app import app, db
from sqlalchemy import text
with app.app_context():
    db.session.execute(text("DELETE FROM b2b_campaign_ledger WHERE campaign_id=:cid"), {"cid": {int(ids["campaign_id"])}})
    db.session.execute(text("DELETE FROM discovery_event WHERE campaign_id=:cid"), {"cid": {int(ids["campaign_id"])}})
    db.session.execute(text("DELETE FROM discovery_campaign WHERE id=:cid"), {"cid": {int(ids["campaign_id"])}})
    db.session.execute(text("DELETE FROM product_activity_day WHERE user_id=:uid"), {"uid": {int(ids["user_id"])}})
    db.session.execute(text("DELETE FROM student_opportunity_discovery_audit WHERE user_id=:uid"), {"uid": {int(ids["user_id"])}})
    db.session.execute(text("DELETE FROM student_opportunity_discovery WHERE user_id=:uid"), {"uid": {int(ids["user_id"])}})
    db.session.execute(text("DELETE FROM opportunity WHERE id=:oid"), {"oid": {int(ids["opportunity_id"])}})
    db.session.execute(text("DELETE FROM organisation WHERE id=:oid"), {"oid": {int(ids["organisation_id"])}})
    db.session.commit()
"""
    run_container_python(code)


async def run_browser_regression(fixture: dict, campaign_fixture: dict) -> None:
    campaign_id = campaign_fixture["campaign_id"]
    state = read_campaign_state(campaign_id)
    assert state["events"] == [], f"new campaign unexpectedly has events: {state}"
    assert state["ledger"] == [], f"new campaign unexpectedly has charges: {state}"

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()
        requests: list[dict] = []
        impression_attempts = {"count": 0}

        def remember_request(request) -> None:
            if f"/api/discovery/campaigns/{campaign_id}/" not in request.url:
                return
            if request.method != "POST":
                return
            try:
                payload = json.loads(request.post_data or "{}")
            except json.JSONDecodeError:
                payload = {}
            requests.append({"url": request.url, "event_id": payload.get("event_id")})

        page.on("request", remember_request)

        async def drop_first_impression_response(route) -> None:
            impression_attempts["count"] += 1
            if impression_attempts["count"] == 1:
                # Let the real backend commit, then simulate the response being
                # lost on the network. The client must retry with the same key.
                response = await route.fetch()
                if not response.ok:
                    await route.fulfill(response=response)
                    return
                await route.abort("failed")
            else:
                await route.continue_()

        await page.route(
            f"**/api/discovery/campaigns/{campaign_id}/impression",
            drop_first_impression_response,
        )

        # Install a CSS rule before the app code mounts the campaign card.
        # The actual IntersectionObserver must see a zero-intersection button.
        await page.add_init_script(
            """() => {
              const install = () => {
                const style = document.createElement('style');
                style.id = 'prepza-b2b-offscreen-test-style';
                style.textContent =
                  'button[aria-label="View sponsored opportunity: Prepza B2B browser ledger proof"] {' +
                  'position: fixed !important; top: 4000px !important; left: 0 !important;}';
                (document.head || document.documentElement).appendChild(style);
              };
              if (document.documentElement) install();
              else document.addEventListener('DOMContentLoaded', install, { once: true });
            }"""
        )

        try:
            login(page, fixture)
            card = page.get_by_role("button", name=f"View sponsored opportunity: {TITLE}")
            await card.wait_for(state="attached", timeout=20000)
            await page.wait_for_timeout(1900)

            offscreen_state = read_campaign_state(campaign_id)
            assert offscreen_state["events"] == [], (
                "offscreen sponsored card caused a billable event: " + str(offscreen_state)
            )
            assert offscreen_state["ledger"] == [], (
                "offscreen sponsored card debited the advertiser: " + str(offscreen_state)
            )
            print("PASS: offscreen ad created no event and no ledger debit")

            await page.locator(f"style#{STYLE_ID}").evaluate("(style) => style.remove()")
            await card.scroll_into_view_if_needed(timeout=5000)
            box = await card.bounding_box()
            assert box and box["width"] > 0 and box["height"] > 0, (
                f"qualifying sponsored card has no layout box: {box}"
            )

            deadline = time.monotonic() + 15
            current = read_campaign_state(campaign_id)
            while time.monotonic() < deadline:
                current = read_campaign_state(campaign_id)
                if current["delivered_impressions"] == 1 and impression_attempts["count"] >= 2:
                    break
                await page.wait_for_timeout(250)

            assert impression_attempts["count"] >= 2, (
                "expected the simulated lost impression response to be retried; "
                f"attempts={impression_attempts}, requests={requests}"
            )
            assert current["delivered_impressions"] == 1, (
                "qualifying view did not produce exactly one impression: " + str(current)
            )
            impression_events = [event for event in requests if event["url"].endswith("/impression")]
            impression_ids = [event["event_id"] for event in impression_events]
            assert len(impression_ids) >= 2 and impression_ids[0] and len(set(impression_ids)) == 1, (
                f"impression retries did not reuse one stable event ID: {impression_events}"
            )
            impression_charges = [
                row for row in current["ledger"] if row["entry_type"] == "delivery_impression"
            ]
            assert len(impression_charges) == 1 and int(impression_charges[0]["signed_amount_minor"]) == -35, (
                "one qualifying view must debit exactly KES 0.35 once: " + str(current)
            )
            print("PASS: visible ad charged one CPM unit after a lost response; retry reused the same UUID")

            await card.click(timeout=8000)
            deadline = time.monotonic() + 8
            current = read_campaign_state(campaign_id)
            while time.monotonic() < deadline and current["delivered_clicks"] != 1:
                await page.wait_for_timeout(200)
                current = read_campaign_state(campaign_id)

            click_events = [event for event in requests if event["url"].endswith("/click")]
            assert len(click_events) == 1 and click_events[0]["event_id"], (
                f"click was not attributed with a stable event ID: {click_events}"
            )
            click_id = click_events[0]["event_id"]
            assert current["delivered_clicks"] == 1, "click did not reach campaign counter: " + str(current)
            click_charges = [row for row in current["ledger"] if row["entry_type"] == "delivery_click"]
            assert len(click_charges) == 1 and int(click_charges[0]["signed_amount_minor"]) == -2000, (
                "qualifying click must debit exactly KES 20 once: " + str(current)
            )

            replay = await page.evaluate(
                """async ({campaignId, eventId}) => {
                  const response = await fetch(
                    "/api/discovery/campaigns/" + campaignId + "/click",
                    { method: 'POST', credentials: 'same-origin',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ event_id: eventId }) }
                  );
                  return { status: response.status, body: await response.json() };
                }""",
                {"campaignId": campaign_id, "eventId": click_id},
            )
            assert replay["status"] == 200 and replay["body"].get("eligible") is True, (
                f"click replay did not return an accepted idempotent result: {replay}"
            )
            final = read_campaign_state(campaign_id)
            assert final["delivered_impressions"] == 1 and final["delivered_clicks"] == 1, (
                "duplicate requests altered delivery counters: " + str(final)
            )
            assert len([row for row in final["ledger"] if row["entry_type"] == "delivery_impression"]) == 1
            assert len([row for row in final["ledger"] if row["entry_type"] == "delivery_click"]) == 1
            assert final["remaining_minor"] == 1000000 - 35 - 2000, (
                "advertiser balance did not reconcile after one impression and one click: " + str(final)
            )
            print("PASS: click reached the right campaign, and duplicate click replay did not debit twice")
        finally:
            await context.close()
            await browser.close()


def main() -> int:
    fixture = create_fixture()
    campaign_fixture = None
    try:
        campaign_fixture = create_campaign_fixture(fixture["user_id"])
        asyncio.run(run_browser_regression(fixture, campaign_fixture))
        return 0
    finally:
        if campaign_fixture is not None:
            cleanup_campaign_fixture(campaign_fixture)
        cleanup_fixture(fixture)


if __name__ == "__main__":
    raise SystemExit(main())
