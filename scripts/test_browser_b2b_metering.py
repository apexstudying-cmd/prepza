"""End-to-end sponsored-ad viewability and prepaid-ledger regression.

Runs against the disposable PostgreSQL + real Flask + Chromium stack created by
mobile-responsive-browser.yml. No external provider or real payment is used.
"""
from __future__ import annotations

import json
import time
import uuid

from playwright.sync_api import sync_playwright

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
    code = """
import json
from datetime import datetime, timedelta
from app import app, db, User, Organisation, Opportunity
from sqlalchemy import text

with app.app_context():
    user = db.session.get(User, __USER_ID__)
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
    db.session.execute(text("INSERT INTO organisation_member (organisation_id, user_id, role, joined_at) VALUES (:oid, :uid, 'owner', CURRENT_TIMESTAMP) ON CONFLICT (organisation_id, user_id) DO UPDATE SET role='owner'"), {"oid": organisation.id, "uid": user.id})

    opportunity = Opportunity(
        organisation_id=organisation.id,
        created_by=user.id,
        title="Prepza B2B browser ledger proof",
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

    db.session.execute(text("INSERT INTO student_opportunity_discovery (user_id, discoverable, consent_version, updated_at) VALUES (:uid, TRUE, 'g5-browser-test', CURRENT_TIMESTAMP) ON CONFLICT (user_id) DO UPDATE SET discoverable=TRUE, consent_version='g5-browser-test', updated_at=CURRENT_TIMESTAMP"), {"uid": user.id})
    db.session.execute(text("INSERT INTO product_activity_day (user_id, activity_date, sessions, engaged_seconds, core_actions, last_seen_at) VALUES (:uid, CURRENT_DATE, 1, 180, 2, CURRENT_TIMESTAMP) ON CONFLICT (user_id, activity_date) DO UPDATE SET engaged_seconds=GREATEST(product_activity_day.engaged_seconds, 180), core_actions=GREATEST(product_activity_day.core_actions, 2), last_seen_at=CURRENT_TIMESTAMP"), {"uid": user.id})

    snapshot = {
        "home_impression_cpm": {"value": {"amount_kes": 350, "per": 1000}, "version": "browser-qa-v1"},
        "click_cpc": {"value": {"amount_kes": 20}, "version": "browser-qa-v1"},
        "home_frequency_cap": {"value": {"max_impressions": 1000, "window_days": 7}, "version": "browser-qa-v1"},
        "click_frequency_cap": {"value": {"max_clicks": 1, "window_days": 1}, "version": "browser-qa-v1"}
    }
    campaign_id = db.session.execute(text("INSERT INTO discovery_campaign (organisation_id, opportunity_id, name, objective, placement, status, budget_kes, bid_type, bid_kes, target_json, starts_at, ends_at, funding_status, funded_amount_minor, pricing_version, pricing_snapshot) VALUES (:oid, :opid, 'Browser QA sponsored ledger', 'reach', 'home_carousel', 'active', 5000, 'both', 350, CAST(:target AS jsonb), :starts, :ends, 'funded', 1000000, 'browser-qa-v1', CAST(:snapshot AS jsonb)) RETURNING id"), {
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
    code = code.replace("__USER_ID__", str(int(user_id)))
    return json.loads(run_container_python(code).splitlines()[-1])


def read_campaign_state(campaign_id: int) -> dict:
    code = """
import json
from app import app, db
from sqlalchemy import text
with app.app_context():
    params = {"cid": __CAMPAIGN_ID__}
    events = db.session.execute(text("SELECT event_type, COUNT(*) AS count FROM discovery_event WHERE campaign_id=:cid GROUP BY event_type ORDER BY event_type"), params).mappings().all()
    ledger = db.session.execute(text("SELECT entry_type, signed_amount_minor, delivery_event_id, idempotency_key FROM b2b_campaign_ledger WHERE campaign_id=:cid AND entry_type IN ('delivery_impression','delivery_click') ORDER BY id"), params).mappings().all()
    campaign = db.session.execute(text("SELECT delivered_impressions, delivered_clicks, funded_amount_minor FROM discovery_campaign WHERE id=:cid"), params).mappings().one()
    remaining = int(campaign["funded_amount_minor"]) + int(db.session.execute(text("SELECT COALESCE(SUM(signed_amount_minor), 0) FROM b2b_campaign_ledger WHERE campaign_id=:cid"), params).scalar_one())
    campus_ids = db.session.execute(text("SELECT DISTINCT metadata->>'campus_id' FROM discovery_event WHERE campaign_id=:cid AND metadata ? 'campus_id'"), params).scalars().all()
    print(json.dumps({
        "events": [dict(row) for row in events],
        "ledger": [dict(row) for row in ledger],
        "campus_ids": campus_ids,
        "delivered_impressions": int(campaign["delivered_impressions"]),
        "delivered_clicks": int(campaign["delivered_clicks"]),
        "remaining_minor": remaining,
    }))
"""
    code = code.replace("__CAMPAIGN_ID__", str(int(campaign_id)))
    return json.loads(run_container_python(code).splitlines()[-1])


def cleanup_campaign_fixture(ids: dict) -> None:
    code = """
from app import app, db
from sqlalchemy import text
with app.app_context():
    db.session.execute(text("DELETE FROM b2b_campaign_ledger WHERE campaign_id=:cid"), {"cid": __CAMPAIGN_ID__})
    db.session.execute(text("DELETE FROM discovery_event WHERE campaign_id=:cid"), {"cid": __CAMPAIGN_ID__})
    db.session.execute(text("DELETE FROM discovery_campaign WHERE id=:cid"), {"cid": __CAMPAIGN_ID__})
    db.session.execute(text("DELETE FROM organisation_member WHERE organisation_id=:oid OR user_id=:uid"), {"oid": __ORGANISATION_ID__, "uid": __USER_ID__})
    db.session.execute(text("DELETE FROM product_activity_day WHERE user_id=:uid"), {"uid": __USER_ID__})
    db.session.execute(text("DELETE FROM student_opportunity_discovery_audit WHERE user_id=:uid"), {"uid": __USER_ID__})
    db.session.execute(text("DELETE FROM student_opportunity_discovery WHERE user_id=:uid"), {"uid": __USER_ID__})
    db.session.execute(text("DELETE FROM opportunity WHERE id=:oid"), {"oid": __OPPORTUNITY_ID__})
    db.session.execute(text("DELETE FROM organisation WHERE id=:oid"), {"oid": __ORGANISATION_ID__})
    db.session.commit()
"""
    for name in ("campaign_id", "user_id", "opportunity_id", "organisation_id"):
        code = code.replace(f"__{name.upper()}__", str(int(ids[name])))
    run_container_python(code)


def run_browser_regression(fixture: dict, campaign_fixture: dict) -> None:
    campaign_id = campaign_fixture["campaign_id"]
    state = read_campaign_state(campaign_id)
    assert state["events"] == [], f"new campaign unexpectedly has events: {state}"
    assert state["ledger"] == [], f"new campaign unexpectedly has charges: {state}"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        requests: list[dict] = []
        impression_attempts = {"count": 0}
        click_attempts = {"count": 0}

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

        def drop_first_impression_response(route) -> None:
            impression_attempts["count"] += 1
            if impression_attempts["count"] == 1:
                # Let the real backend commit, then simulate a lost response.
                response = route.fetch()
                if response.ok:
                    route.abort("failed")
                else:
                    route.fulfill(response=response)
            else:
                route.continue_()

        page.route(
            f"**/api/discovery/campaigns/{campaign_id}/impression",
            drop_first_impression_response,
        )

        def drop_first_click_response(route) -> None:
            click_attempts["count"] += 1
            if click_attempts["count"] == 1:
                # Commit the click at the real server, then lose the response.
                response = route.fetch()
                if response.ok:
                    route.abort("failed")
                else:
                    route.fulfill(response=response)
            else:
                route.continue_()

        page.route(
            f"**/api/discovery/campaigns/{campaign_id}/click",
            drop_first_click_response,
        )

        # Install CSS before the app mounts the card, so IntersectionObserver
        # sees a real zero-intersection element rather than a mocked observer.
        page.add_init_script(
            """(() => {
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
            })()"""
        )

        try:
            login(page, fixture)
            card = page.get_by_role("button", name=f"View sponsored opportunity: {TITLE}")
            card.wait_for(state="attached", timeout=20000)
            page.wait_for_timeout(1900)

            offscreen_state = read_campaign_state(campaign_id)
            assert offscreen_state["events"] == [], (
                "offscreen sponsored card caused a billable event: " + str(offscreen_state)
            )
            assert offscreen_state["ledger"] == [], (
                "offscreen sponsored card debited the advertiser: " + str(offscreen_state)
            )
            print("PASS: offscreen ad created no event and no ledger debit")

            page.locator(f"style#{STYLE_ID}").evaluate("(style) => style.remove()")
            card.scroll_into_view_if_needed(timeout=5000)
            box = card.bounding_box()
            assert box and box["width"] > 0 and box["height"] > 0, (
                f"qualifying sponsored card has no layout box: {box}"
            )

            # An offline display must not become a billable impression. After
            # reconnect, require a fresh visible interval rather than backdating
            # the offline view.
            context.set_offline(True)
            page.wait_for_timeout(1900)
            offline_state = read_campaign_state(campaign_id)
            assert offline_state["events"] == [] and offline_state["ledger"] == [], (
                "offline sponsored view created a billable event/debit: " + str(offline_state)
            )
            assert impression_attempts["count"] == 0, (
                f"offline page attempted to submit an impression: {impression_attempts}"
            )
            print("PASS: offline sponsored card made no request and created no ledger debit")
            context.set_offline(False)

            # Reconnection starts a fresh qualification timer. Scroll away
            # before its 1.5s window elapses; that partial view must not bill.
            page.wait_for_timeout(400)
            quick_scroll_style = page.add_style_tag(content=
                'button[aria-label="View sponsored opportunity: Prepza B2B browser ledger proof"] '
                '{ position: fixed !important; top: 4000px !important; left: 0 !important; }'
            )
            page.wait_for_timeout(1900)
            quick_scroll_state = read_campaign_state(campaign_id)
            assert quick_scroll_state["events"] == [] and quick_scroll_state["ledger"] == [], (
                "quick scroll did not reset the continuous-visibility timer: " + str(quick_scroll_state)
            )
            assert impression_attempts["count"] == 0, (
                f"quick-scroll view submitted an impression: {impression_attempts}"
            )
            quick_scroll_style.evaluate("(style) => style.remove()")
            card.scroll_into_view_if_needed(timeout=5000)
            print("PASS: quick scroll reset the timer; only a fresh continuous view can qualify")

            deadline = time.monotonic() + 25
            current = read_campaign_state(campaign_id)
            while time.monotonic() < deadline:
                current = read_campaign_state(campaign_id)
                if current["delivered_impressions"] == 1 and impression_attempts["count"] >= 2:
                    break
                page.wait_for_timeout(250)

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

            card.click(timeout=8000)
            deadline = time.monotonic() + 12
            current = read_campaign_state(campaign_id)
            while time.monotonic() < deadline:
                current = read_campaign_state(campaign_id)
                if current["delivered_clicks"] == 1 and click_attempts["count"] >= 2:
                    break
                page.wait_for_timeout(200)

            assert click_attempts["count"] >= 2, (
                "click response was lost after commit but pending click was not retried: "
                f"attempts={click_attempts}, requests={requests}"
            )
            click_events = [event for event in requests if event["url"].endswith("/click")]
            click_ids = [event["event_id"] for event in click_events]
            assert len(click_ids) >= 2 and click_ids[0] and len(set(click_ids[:2])) == 1, (
                f"click retry did not reuse one stable event ID: {click_events}"
            )
            click_id = click_ids[0]
            assert current["delivered_clicks"] == 1, "click did not reach campaign counter: " + str(current)
            click_charges = [row for row in current["ledger"] if row["entry_type"] == "delivery_click"]
            assert len(click_charges) == 1 and int(click_charges[0]["signed_amount_minor"]) == -2000, (
                "qualifying click must debit exactly KES 20 once: " + str(current)
            )

            # Wait out the first click's debounce window, then submit two
            # distinct event IDs back-to-back. The first is raw telemetry
            # (the daily cap prevents billing); the second must be server-debounced.
            page.wait_for_timeout(850)
            rapid_click_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
            rapid_clicks = page.evaluate(
                """async ({campaignId, eventIds}) => {
                  const results = [];
                  for (const eventId of eventIds) {
                    const response = await fetch(
                      "/api/discovery/campaigns/" + campaignId + "/click",
                      { method: 'POST', credentials: 'same-origin',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ event_id: eventId }) }
                    );
                    results.push({ status: response.status, body: await response.json() });
                  }
                  return results;
                }""",
                {"campaignId": campaign_id, "eventIds": rapid_click_ids},
            )
            assert all(item["status"] == 200 for item in rapid_clicks), rapid_clicks
            assert rapid_clicks[0]["body"].get("recorded") is True, rapid_clicks
            assert rapid_clicks[0]["body"].get("billable") is False, rapid_clicks
            assert rapid_clicks[1]["body"].get("debounced") is True, rapid_clicks
            rapid_state = read_campaign_state(campaign_id)
            assert rapid_state["delivered_clicks"] == 1, (
                "rapid distinct clicks changed the billable click counter: " + str(rapid_state)
            )
            assert len([
                row for row in rapid_state["ledger"] if row["entry_type"] == "delivery_click"
            ]) == 1, "rapid distinct clicks created an extra advertiser debit: " + str(rapid_state)
            print("PASS: server-side rapid-click debounce rejects distinct event IDs without extra billing")

            # A later, distinct click attempt by the same authenticated user
            # is still counted as a raw interaction, but the daily billable
            # click cap must protect prepaid advertiser money.
            page.wait_for_timeout(850)
            second_click_id = str(uuid.uuid4())
            second_click = page.evaluate(
                """async ({campaignId, eventId}) => {
                  const response = await fetch(
                    "/api/discovery/campaigns/" + campaignId + "/click",
                    { method: 'POST', credentials: 'same-origin',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ event_id: eventId }) }
                  );
                  return { status: response.status, body: await response.json() };
                }""",
                {"campaignId": campaign_id, "eventId": second_click_id},
            )
            assert second_click["status"] == 200
            assert second_click["body"].get("eligible") is True
            assert second_click["body"].get("billable") is False
            assert second_click["body"].get("billing_reason") == "student_frequency_cap", second_click
            capped_state = read_campaign_state(campaign_id)
            assert capped_state["delivered_clicks"] == 1
            assert len([row for row in capped_state["ledger"] if row["entry_type"] == "delivery_click"]) == 1
            assert capped_state["remaining_minor"] == 1000000 - 35 - 2000
            print("PASS: repeated user click is counted without a second billable click/debit")

            replay = page.evaluate(
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

            report_response = page.request.get(
                BASE_URL + f"/api/organisations/{campaign_fixture['organisation_id']}/discovery/report"
            )
            assert report_response.status == 200, (
                f"advertiser JSON report failed: {report_response.status} {report_response.text()}"
            )
            report = report_response.json()
            campaign_report = next(
                item for item in report["campaigns"]
                if item["campaign_id"] == campaign_id
            )
            assert campaign_report["impressions"] == 1
            assert campaign_report["unique_reach"] == 1
            assert campaign_report["campus_breakdown"] == [], (
                "small campus cohort must be suppressed from advertiser report: " + str(campaign_report)
            )
            assert all(not any(key in item for key in ("user_id", "student_id", "email"))
                       for item in report["campaigns"])
            assert len(final["campus_ids"]) == 1, (
                "billable delivery events did not capture campus attribution: " + str(final)
            )
            # The report counts the billable click plus two distinct
            # raw-only interactions, including the first request in the
            # rapid-click debounce pair. The second rapid request is dropped.
            assert campaign_report["raw_clicks"] == 3
            assert campaign_report["unique_clicks"] == 1
            assert campaign_report["billable_clicks"] == 1
            assert campaign_report["unique_billable_clickers"] == 1
            assert campaign_report["ctr_percent"] == 100.0
            assert campaign_report["billable_ctr_percent"] == 100.0
            assert campaign_report["raw_ctr_percent"] == 300.0
            assert campaign_report["unique_ctr_percent"] == 100.0
            assert campaign_report["unique_billable_ctr_percent"] == 100.0
            assert campaign_report["net_spend_kes"] == 20.35, campaign_report

            # Explicit campus filters must not reveal low-reach groups.
            assert final["campus_ids"] and final["campus_ids"][0] is not None
            campus_filter_response = page.request.get(
                BASE_URL + f"/api/organisations/{campaign_fixture['organisation_id']}/discovery/report"
                + f"?university_id={int(final['campus_ids'][0])}"
            )
            assert campus_filter_response.status == 200
            assert campus_filter_response.json()["campaigns"] == [], (
                "campus-filtered report must suppress a cohort smaller than ten"
            )
            campaign_filter_response = page.request.get(
                BASE_URL + f"/api/organisations/{campaign_fixture['organisation_id']}/discovery/report"
                + f"?campaign_id={campaign_id}"
            )
            assert campaign_filter_response.status == 200
            assert len(campaign_filter_response.json()["campaigns"]) == 1
            assert campaign_filter_response.json()["filters"]["campaign_id"] == campaign_id

            csv_response = page.request.get(
                BASE_URL + f"/api/organisations/{campaign_fixture['organisation_id']}/discovery/report?format=csv"
            )
            assert csv_response.status == 200, (
                f"advertiser CSV report failed: {csv_response.status} {csv_response.text()}"
            )
            assert "text/csv" in csv_response.headers.get("content-type", "")
            csv_body = csv_response.text()
            assert "Scope" in csv_body
            assert "Campus ID" in csv_body
            assert "Unique reach" in csv_body
            assert "Unique clickers" in csv_body
            assert "Billable CTR (%)" in csv_body
            assert "Raw CTR (%)" in csv_body
            assert "Unique CTR (%)" in csv_body
            assert "Browser QA sponsored ledger" in csv_body
            assert "20.35" in csv_body
            print("PASS: advertiser JSON/CSV reports distinguish 2 raw clicks from 1 unique/billable click and reconcile KES 20.35")
            print("PASS: click reached the right campaign, and duplicate click replay did not debit twice")
        finally:
            context.close()
            browser.close()


def main() -> int:
    fixture = create_fixture()
    campaign_fixture = None
    try:
        campaign_fixture = create_campaign_fixture(fixture["user_id"])
        run_browser_regression(fixture, campaign_fixture)
        return 0
    finally:
        if campaign_fixture is not None:
            cleanup_campaign_fixture(campaign_fixture)
        cleanup_fixture(fixture)


if __name__ == "__main__":
    raise SystemExit(main())
