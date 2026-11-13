"""Real-browser buyer, seller and moderator journeys for Prepza Shop.

Uses isolated student/admin accounts and disposable PostgreSQL rows. Payment
provider redirects are not invoked; the fee/checkout boundary is covered by
the mocked-provider database QA test.
"""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from test_browser_study_hub_offline_content import (
    BASE_URL,
    cleanup_fixture,
    create_fixture,
    login,
    run_container_python,
)

ARTIFACTS = Path("artifacts/mobile-responsive/shop-journeys")
ACTIVE_TITLE = "QA Shop active textbook"
PENDING_APPROVE_TITLE = "QA Shop awaiting approval"
PENDING_REJECT_TITLE = "QA Shop needs changes"
PAYMENT_REVIEW_TITLE = "QA Shop payment review"


def seed_shop_rows(seller_id: int, admin_id: int) -> dict:
    code = f"""
import json
from datetime import datetime, timedelta
from app import app, db, User
import shop_marketplace

with app.app_context():
    seller = db.session.get(User, {seller_id})
    admin = db.session.get(User, {admin_id})
    if seller is None or admin is None:
        raise RuntimeError("Shop browser fixtures are missing")
    admin.is_admin = True
    Listing = shop_marketplace._ShopListing
    if Listing is None:
        raise RuntimeError("Shop routes/models were not registered")
    expiry = datetime.utcnow() + timedelta(days=30)
    common = dict(
        seller_id=seller.id,
        category="Books & study",
        condition="good",
        price_kes=850,
        location_area="Kahawa, near KU",
        posting_fee_kes=100,
        posting_fee_paid=True,
        posting_fee_expires_at=expiry,
        is_free_post=False,
    )
    active = Listing(
        **common,
        title={ACTIVE_TITLE!r},
        description="A used textbook in good condition for browser QA.",
        whatsapp_number="254712345678",
        status="active",
    )
    approve = Listing(
        **common,
        title={PENDING_APPROVE_TITLE!r},
        description="A paid listing awaiting moderator approval.",
        image_keys=["qa-shop-fixtures/approved-listing.png"],
        status="pending_review",
    )
    reject = Listing(
        **common,
        title={PENDING_REJECT_TITLE!r},
        description="A paid listing that needs changes.",
        status="pending_review",
    )
    payment_review = Listing(
        seller_id=seller.id,
        title={PAYMENT_REVIEW_TITLE!r},
        description="Ambiguous provider response fixture.",
        category="Books & study",
        condition="good",
        price_kes=500,
        location_area="Kahawa, near KU",
        posting_fee_kes=100,
        posting_fee_paid=False,
        is_free_post=False,
        status="payment_review",
        posting_payment_reference="QA-SHOP-PAYMENT-REVIEW",
        posting_payment_review_note="Provider response requires manual verification.",
    )
    db.session.add_all([active, approve, reject, payment_review])
    db.session.commit()
    print(json.dumps({{
        "active_id": active.id,
        "approve_id": approve.id,
        "reject_id": reject.id,
        "payment_review_id": payment_review.id,
    }}))
"""
    return json.loads(run_container_python(code).splitlines()[-1])


def cleanup_shop_conversations(user_ids: list[int]) -> None:
    # The buyer journey creates a direct chat. Remove that disposable thread
    # before the shared fixture helper deletes its users; conversation
    # participants have a restrictive user FK in the current schema.
    code = f"""
from app import app, db, Conversation, ConversationParticipant

with app.app_context():
    conversation_ids = [
        row[0] for row in db.session.query(ConversationParticipant.conversation_id)
        .filter(ConversationParticipant.user_id.in_({user_ids!r}))
        .distinct().all()
    ]
    if conversation_ids:
        Conversation.query.filter(Conversation.id.in_(conversation_ids)).delete(
            synchronize_session=False
        )
    db.session.commit()
"""
    run_container_python(code)


def open_shop(page) -> None:
    page.get_by_role("navigation", name="Primary navigation").wait_for(
        state="visible", timeout=20000
    )
    page.get_by_role("button", name="Shop").first.click(timeout=10000)
    page.get_by_role("navigation", name="Shop sections").wait_for(
        state="visible", timeout=10000
    )


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    seller = create_fixture()
    buyer = create_fixture()
    admin = create_fixture()
    try:
        rows = seed_shop_rows(seller["user_id"], admin["user_id"])
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                # Buyer: browse, inspect, save, report and contact the seller.
                buyer_context = browser.new_context(viewport={"width": 390, "height": 844})
                buyer_page = buyer_context.new_page()
                login(buyer_page, buyer)
                open_shop(buyer_page)
                buyer_page.get_by_text(ACTIVE_TITLE, exact=True).wait_for(timeout=10000)
                buyer_page.get_by_role(
                    "button", name=f"Open listing: {ACTIVE_TITLE}"
                ).click(timeout=10000)
                buyer_page.get_by_text("A used textbook in good condition", exact=False).wait_for(timeout=5000)
                buyer_page.get_by_role("button", name="WhatsApp seller").wait_for(
                    state="visible", timeout=5000
                )
                buyer_page.get_by_role("button", name="Save item").click(timeout=10000)
                buyer_page.get_by_role("button", name="Saved ✓").wait_for(timeout=5000)
                buyer_page.get_by_role("button", name="Saved", exact=True).click(timeout=5000)
                buyer_page.get_by_text(ACTIVE_TITLE, exact=True).wait_for(timeout=10000)
                buyer_page.screenshot(
                    path=str(ARTIFACTS / "buyer-saved-listing.png"),
                    full_page=True,
                    animations="disabled",
                )
                buyer_page.get_by_role("button", name="Browse", exact=True).click(timeout=5000)
                buyer_page.get_by_role(
                    "button", name=f"Open listing: {ACTIVE_TITLE}"
                ).click(timeout=10000)
                buyer_page.get_by_role("button", name="Report").click(timeout=5000)
                buyer_page.get_by_label("Reason").select_option("misleading")
                buyer_page.get_by_label("Details (optional)").fill(
                    "QA buyer report details: item condition needs moderator review."
                )
                buyer_page.get_by_role("button", name="Submit report").click(timeout=10000)
                buyer_page.get_by_role("status").filter(
                    has_text="Your report has been sent"
                ).wait_for(timeout=10000)
                buyer_page.screenshot(
                    path=str(ARTIFACTS / "buyer-listing-reported.png"),
                    full_page=True,
                    animations="disabled",
                )
                with buyer_page.expect_response(
                    lambda response: response.request.method == "POST"
                    and response.url.rstrip("/").endswith("/chats"),
                    timeout=15000,
                ) as create_chat_response:
                    buyer_page.get_by_role("button", name="Message in Prepza").click(timeout=10000)
                created_chat = create_chat_response.value
                if not created_chat.ok:
                    raise AssertionError(
                        f"Shop in-app contact failed to create a chat: "
                        f"{created_chat.status} {created_chat.text()}"
                    )
                chat_payload = created_chat.json()
                if chat_payload.get("status") != "accepted":
                    raise AssertionError(
                        "Shop contact did not open an accepted conversation; "
                        f"received status={chat_payload.get('status')!r}"
                    )
                conversation_id = int(chat_payload["id"])
                buyer_page.wait_for_function(
                    """expected => {
                      const state = JSON.parse(sessionStorage.getItem('prepza-navigation-state') || '{}')
                      return Number(state.activeConversationId) === Number(expected)
                    }""",
                    arg=conversation_id,
                    timeout=10000,
                )
                navigation_state = buyer_page.evaluate(
                    "JSON.parse(sessionStorage.getItem('prepza-navigation-state') || '{}')"
                )
                print(f"ChatDetail navigation state after contact: {navigation_state!r}")
                buyer_page.get_by_role("button", name="Chat options").wait_for(
                    state="visible", timeout=15000
                )
                composer = buyer_page.get_by_placeholder("Message", exact=True)
                composer.wait_for(state="visible", timeout=10000)
                composer.fill("QA in-app seller message")
                send_button = buyer_page.get_by_role("button", name="Send", exact=True)
                send_button.wait_for(state="visible", timeout=5000)
                with buyer_page.expect_response(
                    lambda response: response.request.method == "POST"
                    and response.url.rstrip("/").endswith(
                        f"/chats/{conversation_id}/messages"
                    ),
                    timeout=15000,
                ) as send_message_response:
                    send_button.click(timeout=10000)
                sent_message = send_message_response.value
                if sent_message.status not in (200, 201):
                    raise AssertionError(
                        f"Shop in-app message failed: {sent_message.status} "
                        f"{sent_message.text()}"
                    )
                buyer_page.get_by_text(
                    "QA in-app seller message", exact=False
                ).wait_for(timeout=10000)
                if composer.input_value():
                    raise AssertionError("Chat composer did not clear after sending the message")
                buyer_page.screenshot(
                    path=str(ARTIFACTS / "buyer-chat-message-sent.png"),
                    full_page=True,
                    animations="disabled",
                )
                print("PASS: buyer browsed details, saved, reported, opened ChatDetail and sent an in-app message")
                buyer_context.close()

                # Seller: inspect owned listings and exercise pause/sold controls.
                seller_context = browser.new_context(viewport={"width": 390, "height": 844})
                seller_page = seller_context.new_page()
                login(seller_page, seller)
                open_shop(seller_page)
                seller_page.get_by_role("button", name="My listings").click(timeout=5000)
                seller_page.get_by_text(ACTIVE_TITLE, exact=True).wait_for(timeout=10000)
                seller_page.get_by_role(
                    "button", name=f"Open listing: {ACTIVE_TITLE}"
                ).click(timeout=10000)
                seller_page.get_by_text("Status: Live", exact=False).wait_for(timeout=5000)
                seller_page.screenshot(
                    path=str(ARTIFACTS / "seller-listing-live.png"),
                    full_page=True,
                    animations="disabled",
                )
                seller_page.get_by_role("button", name="Pause").click(timeout=10000)
                seller_page.get_by_text("Status: Paused", exact=False).wait_for(timeout=10000)
                seller_page.get_by_role("button", name="Mark sold").click(timeout=10000)
                seller_page.get_by_text("Status: Sold", exact=False).wait_for(timeout=10000)
                seller_page.get_by_role("button", name="Sell an item").click(timeout=5000)
                seller_page.get_by_role("heading", name="List a product").wait_for(timeout=5000)
                seller_page.get_by_text(
                    "Posting fee: KES 100 per item for each 30-day period, including your first.",
                    exact=False,
                ).wait_for(timeout=5000)
                print("PASS: seller viewed own listing, paused it, marked it sold and reached the paid listing form")
                seller_context.close()

                # Admin: approve/reject listings, resolve a buyer report, and
                # safely clear an ambiguous payment review with a recorded note.
                admin_context = browser.new_context(viewport={"width": 390, "height": 844})
                admin_page = admin_context.new_page()
                login(admin_page, admin)
                open_shop(admin_page)
                admin_page.get_by_role("button", name="Moderation").click(timeout=5000)
                admin_page.get_by_text(PENDING_APPROVE_TITLE, exact=True).wait_for(timeout=10000)
                admin_page.screenshot(
                    path=str(ARTIFACTS / "admin-moderation-queue.png"),
                    full_page=True,
                    animations="disabled",
                )
                approve_card = admin_page.locator("div").filter(
                    has_text=PENDING_APPROVE_TITLE
                ).filter(has=admin_page.get_by_role("button", name="Approve")).last
                approve_card.get_by_role("button", name="Approve").click(timeout=10000)
                admin_page.get_by_role("status").filter(
                    has_text="Listing approved and published"
                ).wait_for(timeout=10000)

                reject_card = admin_page.locator("div").filter(
                    has_text=PENDING_REJECT_TITLE
                ).filter(has=admin_page.get_by_role("button", name="Reject")).last
                reject_card.get_by_role("button", name="Reject").click(timeout=10000)
                admin_page.get_by_role("status").filter(
                    has_text="Moderation decision saved"
                ).wait_for(timeout=10000)

                admin_page.get_by_text(
                    "QA buyer report details: item condition needs moderator review.",
                    exact=True,
                ).wait_for(timeout=10000)
                report_card = admin_page.locator("div").filter(
                    has_text="QA buyer report details: item condition needs moderator review."
                ).filter(has=admin_page.get_by_role("button", name="Resolve report")).last
                report_card.get_by_role("button", name="Resolve report").click(timeout=10000)
                admin_page.get_by_text(
                    "QA buyer report details: item condition needs moderator review.",
                    exact=True,
                ).wait_for(state="detached", timeout=10000)

                admin_page.get_by_label("Provider verification note").fill(
                    "Verified provider reference and confirmed no captured fee; retry is safe."
                )
                admin_page.get_by_role(
                    "button", name="Allow retry after verification"
                ).click(timeout=10000)
                admin_page.get_by_role("status").filter(
                    has_text="Payment review closed"
                ).wait_for(timeout=10000)
                print("PASS: admin approved/rejected listings, resolved a buyer report and documented payment review")
                admin_context.close()
            finally:
                browser.close()
        print(f"Shop browser journeys passed; seeded listing IDs: {rows}")
        return 0
    finally:
        # Remove the buyer-created conversation before deleting the users.
        cleanup_shop_conversations([
            seller["user_id"], buyer["user_id"], admin["user_id"]
        ])
        # Shop rows are owned by the fixture seller; FK cascades clean reports,
        # saved rows and listings when the disposable users are removed.
        for fixture in (seller, buyer, admin):
            cleanup_fixture(fixture)


if __name__ == "__main__":
    raise SystemExit(main())
