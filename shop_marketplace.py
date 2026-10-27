"""Prepza Shop classifieds API.

Shop never processes a buyer's purchase or holds buyer funds. Paystack is used
only for the seller's KES 100 listing-posting fee on every listing, including
the first. There is no free-post allowance. Listing ownership, moderation,
legacy-fee normalization and payment fulfillment are enforced on the server.
"""
from __future__ import annotations

import hmac
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta
from urllib.parse import quote

from flask import jsonify, redirect, request, session
from sqlalchemy import or_


LISTING_POST_FEE_KES = 100
LISTING_BILLING_PERIOD_DAYS = 30


def listing_period_expiry(started_at: datetime) -> datetime:
    """Return the end of the paid 30-day listing period (manual renewal)."""
    return started_at + timedelta(days=LISTING_BILLING_PERIOD_DAYS)
MAX_LISTING_IMAGES = 6
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_CATEGORIES = {
    "Books & study", "Electronics", "Hostel & home", "Fashion", "Accessories",
    "Sports & fitness", "Other",
}
ALLOWED_CONDITIONS = {"new", "good", "fair", "for_parts"}
ALLOWED_LISTING_STATES = {"draft", "pending_payment", "payment_review", "pending_review", "active", "paused", "sold", "rejected", "removed"}


def listing_fee_for_post_number(post_number: int) -> int:
    """Every listing, including the first, costs KES 100 to post."""
    try:
        number = int(post_number)
    except (TypeError, ValueError):
        raise ValueError("Post number must be a positive integer")
    if number < 1:
        raise ValueError("Post number must be a positive integer")
    return LISTING_POST_FEE_KES


def normalize_whatsapp_number(value: str | None) -> str | None:
    """Normalize Kenyan mobile numbers to WhatsApp's country-code digit format."""
    raw = str(value or "").strip()
    if not raw:
        return None
    digits = re.sub(r"[\s().-]", "", raw)
    if digits.startswith("+"):
        digits = digits[1:]
    if digits.startswith("0") and len(digits) == 10 and digits[1] in "17":
        digits = "254" + digits[1:]
    if not re.fullmatch(r"254[17]\d{8}", digits):
        raise ValueError("Enter a valid Kenyan mobile number, e.g. 0712345678")
    return digits


def validate_listing_payload(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Listing details must be an object")
    title = str(data.get("title") or "").strip()
    description = str(data.get("description") or "").strip()
    category = str(data.get("category") or "").strip()
    condition = str(data.get("condition") or "").strip().lower()
    location_area = str(data.get("location_area") or "").strip()
    if not 5 <= len(title) <= 100:
        raise ValueError("Title must be between 5 and 100 characters")
    if not 10 <= len(description) <= 2000:
        raise ValueError("Description must be between 10 and 2,000 characters")
    if category not in ALLOWED_CATEGORIES:
        raise ValueError("Choose a valid product category")
    if condition not in ALLOWED_CONDITIONS:
        raise ValueError("Choose a valid item condition")
    if not 2 <= len(location_area) <= 100:
        raise ValueError("Campus/area must be between 2 and 100 characters")
    raw_price = data.get("price_kes")
    if isinstance(raw_price, bool) or not isinstance(raw_price, int):
        raise ValueError("Price must be a whole number of Kenyan shillings")
    if raw_price < 0 or raw_price > 10_000_000:
        raise ValueError("Price must be between KES 0 and KES 10,000,000")
    whatsapp = normalize_whatsapp_number(data.get("whatsapp_number"))
    return {
        "title": title,
        "description": description,
        "category": category,
        "condition": condition,
        "location_area": location_area,
        "price_kes": raw_price,
        "whatsapp_number": whatsapp,
    }


_ShopListing = None
_ShopSavedListing = None
_ShopReport = None


def fulfill_shop_posting_payment(db, payment):
    """Idempotently records a verified posting fee without handling a product sale."""
    global _ShopListing
    if _ShopListing is None or payment.payment_type != "shop_posting" or payment.status != "success":
        return False
    try:
        listing_id = int(payment.plan or "")
    except (TypeError, ValueError):
        return False
    listing = _ShopListing.query.filter_by(id=listing_id, seller_id=payment.user_id).with_for_update().first()
    if not listing or int(payment.amount) != LISTING_POST_FEE_KES:
        return False
    now = datetime.utcnow()
    if listing.posting_period_payment_reference == payment.reference and listing.posting_fee_expires_at:
        return True
    listing.posting_fee_paid = True
    listing.posting_fee_expires_at = listing_period_expiry(now)
    listing.posting_period_payment_reference = payment.reference
    listing.posting_payment_reference = payment.reference
    if listing.status == "pending_payment":
        listing.status = "draft"
        listing.checkout_url = None
    listing.updated_at = datetime.utcnow()
    db.session.commit()
    return True


def fail_shop_posting_payment(db, payment):
    """Release an abandoned/failed checkout so the seller can retry safely."""
    global _ShopListing
    if _ShopListing is None or payment.payment_type != "shop_posting":
        return False
    try:
        listing_id = int(payment.plan or "")
    except (TypeError, ValueError):
        return False
    listing = _ShopListing.query.filter_by(id=listing_id, seller_id=payment.user_id).with_for_update().first()
    if not listing or listing.status != "pending_payment":
        return False
    listing.status = "draft"
    listing.checkout_url = None
    listing.updated_at = datetime.utcnow()
    db.session.commit()
    return True


def mark_shop_posting_payment_mismatch(db, payment, reason=None):
    """Quarantine a provider-successful charge whose amount/currency is wrong."""
    global _ShopListing
    if _ShopListing is None or payment.payment_type != "shop_posting":
        return False
    try:
        listing_id = int(payment.plan or "")
    except (TypeError, ValueError):
        return False
    listing = _ShopListing.query.filter_by(id=listing_id, seller_id=payment.user_id).with_for_update().first()
    if not listing or listing.posting_fee_paid:
        return False
    listing.status = "payment_review"
    listing.checkout_url = None
    message = (str(reason or "").strip()[:500] or "Posting payment requires manual verification. Do not retry this charge yet.")
    listing.moderation_note = message
    listing.posting_payment_review_note = message
    listing.posting_payment_reviewed_by = None
    listing.posting_payment_reviewed_at = None
    listing.updated_at = datetime.utcnow()
    db.session.commit()
    return True


def register_shop_routes(app, db, User, Payment, Conversation, ConversationParticipant, limiter, create_paystack_transaction, sync_paystack_payment_status):
    """Register Shop tables and endpoints after Prepza's core models are defined."""
    global _ShopListing, _ShopSavedListing, _ShopReport
    if getattr(app, "_prepza_shop_registered", False):
        return {"Listing": _ShopListing, "SavedListing": _ShopSavedListing, "Report": _ShopReport}

    class ShopListing(db.Model):
        __tablename__ = "shop_listing"
        id = db.Column(db.Integer, primary_key=True)
        seller_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
        title = db.Column(db.String(100), nullable=False)
        description = db.Column(db.Text, nullable=False)
        category = db.Column(db.String(40), nullable=False, index=True)
        condition = db.Column(db.String(20), nullable=False)
        price_kes = db.Column(db.Integer, nullable=False)
        location_area = db.Column(db.String(100), nullable=False, index=True)
        whatsapp_number = db.Column(db.String(12), nullable=True)
        image_keys = db.Column(db.JSON, nullable=False, default=list)
        status = db.Column(db.String(24), nullable=False, default="draft", index=True)
        is_free_post = db.Column(db.Boolean, nullable=False, default=False)
        posting_fee_kes = db.Column(db.Integer, nullable=False, default=0)
        posting_fee_paid = db.Column(db.Boolean, nullable=False, default=False)
        posting_fee_expires_at = db.Column(db.DateTime, nullable=True, index=True)
        posting_period_payment_reference = db.Column(db.String(50), nullable=True, unique=True)
        posting_payment_reference = db.Column(db.String(50), nullable=True, unique=True)
        checkout_url = db.Column(db.String(500), nullable=True)
        moderation_note = db.Column(db.String(500), nullable=True)
        moderated_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
        moderated_at = db.Column(db.DateTime, nullable=True)
        posting_payment_reviewed_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
        posting_payment_reviewed_at = db.Column(db.DateTime, nullable=True)
        posting_payment_review_note = db.Column(db.String(500), nullable=True)
        created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
        updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
        sold_at = db.Column(db.DateTime, nullable=True)
        __table_args__ = (
            db.CheckConstraint("price_kes >= 0", name="ck_shop_listing_price_nonnegative"),
            db.CheckConstraint("posting_fee_kes IN (0, 100)", name="ck_shop_listing_posting_fee"),
            db.Index("ix_shop_listing_active_created", "status", "created_at"),
        )

    class ShopSavedListing(db.Model):
        __tablename__ = "shop_saved_listing"
        id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
        listing_id = db.Column(db.Integer, db.ForeignKey("shop_listing.id", ondelete="CASCADE"), nullable=False)
        created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        __table_args__ = (db.UniqueConstraint("user_id", "listing_id", name="uq_shop_saved_user_listing"),)

    class ShopReport(db.Model):
        __tablename__ = "shop_report"
        id = db.Column(db.Integer, primary_key=True)
        listing_id = db.Column(db.Integer, db.ForeignKey("shop_listing.id", ondelete="CASCADE"), nullable=False, index=True)
        reporter_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
        reason = db.Column(db.String(40), nullable=False)
        details = db.Column(db.String(1000), nullable=True)
        status = db.Column(db.String(20), nullable=False, default="open", index=True)
        reviewed_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
        reviewed_at = db.Column(db.DateTime, nullable=True)
        created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
        __table_args__ = (db.UniqueConstraint("listing_id", "reporter_id", name="uq_shop_report_listing_reporter"),)

    _ShopListing, _ShopSavedListing, _ShopReport = ShopListing, ShopSavedListing, ShopReport

    def current_user():
        user_id = session.get("user_id")
        if not user_id:
            return None
        user = db.session.get(User, user_id)
        if not user or getattr(user, "is_suspended", False):
            return None
        return user

    def csrf_valid():
        supplied = request.headers.get("X-CSRF-Token", "")
        expected = session.get("csrf_token", "")
        return bool(supplied and expected and hmac.compare_digest(supplied, expected))

    def require_user():
        user = current_user()
        if not user:
            return None, (jsonify({"error": "Authentication required"}), 401)
        return user, None

    def listing_json(listing, viewer_id=None, detail=False, seller=None, saved_ids=None):
        if seller is None:
            seller = db.session.get(User, listing.seller_id)
        images = []
        for key in (listing.image_keys or []):
            try:
                from object_storage import r2_presigned_get
                images.append({"key": key, "url": r2_presigned_get("shop-listings", key, expires_in=900)})
            except Exception:
                images.append({"key": key, "url": None})
        if saved_ids is not None:
            saved = listing.id in saved_ids
        else:
            saved = bool(viewer_id and _ShopSavedListing.query.filter_by(user_id=viewer_id, listing_id=listing.id).first())
        seller_public = bool(seller and getattr(seller, "profile_visibility", "public") == "public")
        result = {
            "id": listing.id,
            "title": listing.title,
            "description": listing.description if detail else None,
            "category": listing.category,
            "condition": listing.condition,
            "price_kes": listing.price_kes,
            "location_area": listing.location_area,
            "images": images,
            "status": listing.status,
            "seller_id": listing.seller_id,
            "seller_name": (seller.display_name or "Prepza seller") if seller_public else "Prepza seller",
            "seller_university_id": getattr(seller, "university_id", None) if seller_public else None,
            "whatsapp_number": listing.whatsapp_number if detail and viewer_id == listing.seller_id else None,
            "whatsapp_url": ("https://wa.me/" + listing.whatsapp_number) if detail and listing.whatsapp_number and viewer_id != listing.seller_id else None,
            "saved": saved,
            "is_mine": viewer_id == listing.seller_id,
            "is_free_post": listing.is_free_post,
            "posting_fee_kes": listing.posting_fee_kes,
            "posting_fee_paid": listing.posting_fee_paid,
            "posting_fee_expires_at": listing.posting_fee_expires_at.isoformat() if listing.posting_fee_expires_at else None,
            "posting_payment_reference": listing.posting_payment_reference if detail and (viewer_id == listing.seller_id or bool(getattr(db.session.get(User, viewer_id), "is_admin", False))) else None,
            "posting_payment_review_note": listing.posting_payment_review_note if detail and (viewer_id == listing.seller_id or bool(getattr(db.session.get(User, viewer_id), "is_admin", False))) else None,
            "moderation_note": listing.moderation_note if viewer_id == listing.seller_id else None,
            "created_at": listing.created_at.isoformat() if listing.created_at else None,
            "updated_at": listing.updated_at.isoformat() if listing.updated_at else None,
        }
        return result

    def listing_json_batch(rows, viewer_id=None, detail=False):
        rows = list(rows)
        if not rows:
            return []
        seller_ids = {row.seller_id for row in rows}
        sellers = {
            seller.id: seller
            for seller in User.query.filter(User.id.in_(seller_ids)).all()
        }
        listing_ids = {row.id for row in rows}
        saved_ids = set()
        if viewer_id:
            saved_ids = {
                row[0]
                for row in db.session.query(_ShopSavedListing.listing_id)
                .filter(_ShopSavedListing.user_id == viewer_id, _ShopSavedListing.listing_id.in_(listing_ids))
                .all()
            }
        return [
            listing_json(row, viewer_id, detail=detail, seller=sellers.get(row.seller_id), saved_ids=saved_ids)
            for row in rows
        ]

    def listing_for_owner(listing_id, user_id):
        listing = db.session.get(ShopListing, listing_id)
        if not listing or listing.seller_id != user_id:
            return None
        return listing

    @app.get("/api/shop/listings")
    def shop_browse_listings():
        user, denied = require_user()
        if denied:
            return denied
        now = datetime.utcnow()
        query = ShopListing.query.filter_by(status="active").filter(ShopListing.posting_fee_expires_at > now)
        term = (request.args.get("q") or "").strip()[:100]
        category = (request.args.get("category") or "").strip()
        condition = (request.args.get("condition") or "").strip().lower()
        location = (request.args.get("location") or "").strip()[:100]
        if term:
            pattern = f"%{term}%"
            query = query.filter(or_(ShopListing.title.ilike(pattern), ShopListing.description.ilike(pattern)))
        if category in ALLOWED_CATEGORIES:
            query = query.filter_by(category=category)
        if condition in ALLOWED_CONDITIONS:
            query = query.filter_by(condition=condition)
        if location:
            query = query.filter(ShopListing.location_area.ilike(f"%{location}%"))
        sort = request.args.get("sort", "newest")
        if sort == "price_low":
            query = query.order_by(ShopListing.price_kes.asc(), ShopListing.id.desc())
        elif sort == "price_high":
            query = query.order_by(ShopListing.price_kes.desc(), ShopListing.id.desc())
        else:
            query = query.order_by(ShopListing.created_at.desc(), ShopListing.id.desc())
        page = max(1, min(request.args.get("page", 1, type=int) or 1, 10000))
        page_size = 24
        total = query.count()
        rows = query.offset((page - 1) * page_size).limit(page_size).all()
        return jsonify({"listings": listing_json_batch(rows, user.id), "page": page, "page_size": page_size, "total": total, "categories": sorted(ALLOWED_CATEGORIES)})

    @app.get("/api/shop/listings/<int:listing_id>")
    def shop_listing_detail(listing_id):
        user, denied = require_user()
        if denied:
            return denied
        listing = db.session.get(ShopListing, listing_id)
        if not listing or (listing.status != "active" and listing.seller_id != user.id) or (listing.status == "active" and (not listing.posting_fee_expires_at or listing.posting_fee_expires_at <= datetime.utcnow()) and listing.seller_id != user.id):
            return jsonify({"error": "Listing not found"}), 404
        return jsonify({"listing": listing_json(listing, user.id, detail=True)})

    @app.get("/api/shop/my-listings")
    def shop_my_listings():
        user, denied = require_user()
        if denied:
            return denied
        rows = ShopListing.query.filter_by(seller_id=user.id).order_by(ShopListing.updated_at.desc(), ShopListing.id.desc()).limit(100).all()
        return jsonify({"listings": listing_json_batch(rows, user.id, detail=True)})

    @app.post("/api/shop/listings")
    @limiter.limit("10 per hour")
    def shop_create_listing():
        user, denied = require_user()
        if denied:
            return denied
        if not csrf_valid():
            return jsonify({"error": "Invalid CSRF token"}), 403
        try:
            payload = validate_listing_payload(request.get_json(silent=True) or {})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        # Lock the seller row to serialize listing creation and fee accounting.
        locked_user = User.query.filter_by(id=user.id).with_for_update().first()
        existing_count = ShopListing.query.filter_by(seller_id=user.id).count()
        free_post = False
        listing = ShopListing(
            seller_id=locked_user.id,
            **payload,
            status="draft",
            is_free_post=free_post,
            posting_fee_kes=listing_fee_for_post_number(existing_count + 1),
            posting_fee_paid=False,
        )
        db.session.add(listing)
        db.session.commit()
        return jsonify({"listing": listing_json(listing, user.id, detail=True), "message": "Draft saved. Add photos and publish when ready."}), 201

    @app.patch("/api/shop/listings/<int:listing_id>")
    def shop_update_listing(listing_id):
        user, denied = require_user()
        if denied:
            return denied
        if not csrf_valid():
            return jsonify({"error": "Invalid CSRF token"}), 403
        listing = listing_for_owner(listing_id, user.id)
        if not listing:
            return jsonify({"error": "Listing not found"}), 404
        if listing.status in {"sold", "removed", "payment_review"}:
            return jsonify({"error": "This listing cannot be edited until its posting payment is reconciled"}), 409
        try:
            payload = validate_listing_payload(request.get_json(silent=True) or {})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        for key, value in payload.items():
            setattr(listing, key, value)
        if listing.status == "rejected":
            listing.status = "draft"
            listing.moderation_note = None
        elif listing.status == "active":
            listing.status = "pending_review"
            listing.moderation_note = None
        listing.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"listing": listing_json(listing, user.id, detail=True)})

    @app.post("/api/shop/listings/<int:listing_id>/images")
    @limiter.limit("30 per hour")
    def shop_upload_listing_image(listing_id):
        user, denied = require_user()
        if denied:
            return denied
        if not csrf_valid():
            return jsonify({"error": "Invalid CSRF token"}), 403
        listing = listing_for_owner(listing_id, user.id)
        if not listing or listing.status not in {"draft", "pending_payment", "pending_review"}:
            return jsonify({"error": "Listing is not accepting photos"}), 409
        if len(listing.image_keys or []) >= MAX_LISTING_IMAGES:
            return jsonify({"error": f"A listing can have at most {MAX_LISTING_IMAGES} photos"}), 400
        file = request.files.get("image")
        if not file:
            return jsonify({"error": "Choose an image to upload"}), 400
        raw = file.stream.read(MAX_IMAGE_BYTES + 1)
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            return jsonify({"error": "Images must be smaller than 5 MB"}), 413
        try:
            from PIL import Image, UnidentifiedImageError
            import io
            source = Image.open(io.BytesIO(raw))
            source_format = source.format
            source.verify()
            image = Image.open(io.BytesIO(raw))
            if image.width <= 0 or image.height <= 0 or image.width * image.height > 20_000_000:
                raise ValueError("Images must be smaller than 20 megapixels")
            mime_by_format = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
            mime = mime_by_format.get(source_format)
            extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(mime)
            if not extension:
                raise ValueError("Use a JPEG, PNG or WebP image")
            # Re-encode to cap dimensions and strip EXIF/GPS metadata before storage.
            image.thumbnail((1600, 1600))
            cleaned = io.BytesIO()
            if source_format == "JPEG":
                if image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                image.save(cleaned, format="JPEG", quality=84, optimize=True, progressive=True)
            elif source_format == "PNG":
                image.save(cleaned, format="PNG", optimize=True)
            else:
                image.save(cleaned, format="WEBP", quality=82, method=5)
            raw = cleaned.getvalue()
            if not raw or len(raw) > MAX_IMAGE_BYTES:
                raise ValueError("Optimized photo must be smaller than 5 MB")
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception:
            return jsonify({"error": "That file is not a valid supported image"}), 400
        try:
            from object_storage import r2_put_bytes
            key = f"{user.id}/{listing.id}/{uuid.uuid4().hex}.{extension}"
            r2_put_bytes("shop-listings", key, raw, mime)
        except Exception:
            app.logger.exception("Shop image storage unavailable")
            return jsonify({"error": "Photo storage is not configured or temporarily unavailable. Please try again later."}), 503
        listing.image_keys = list(listing.image_keys or []) + [key]
        listing.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"images": listing_json(listing, user.id, detail=True)["images"]}), 201

    @app.delete("/api/shop/listings/<int:listing_id>/images/<int:image_index>")
    def shop_delete_listing_image(listing_id, image_index):
        user, denied = require_user()
        if denied:
            return denied
        if not csrf_valid():
            return jsonify({"error": "Invalid CSRF token"}), 403
        listing = listing_for_owner(listing_id, user.id)
        if not listing:
            return jsonify({"error": "Listing not found"}), 404
        keys = list(listing.image_keys or [])
        if image_index < 0 or image_index >= len(keys):
            return jsonify({"error": "Photo not found"}), 404
        key = keys.pop(image_index)
        try:
            from object_storage import r2_delete
            r2_delete("shop-listings", key)
        except Exception:
            app.logger.exception("Could not delete Shop image")
            return jsonify({"error": "Photo could not be deleted; please retry"}), 503
        listing.image_keys = keys
        listing.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"images": listing_json(listing, user.id, detail=True)["images"]})

    @app.post("/api/shop/listings/<int:listing_id>/checkout")
    @limiter.limit("5 per hour")
    def shop_checkout_posting_fee(listing_id):
        user, denied = require_user()
        if denied:
            return denied
        if not csrf_valid():
            return jsonify({"error": "Invalid CSRF token"}), 403
        listing = listing_for_owner(listing_id, user.id)
        if not listing:
            return jsonify({"error": "Listing not found"}), 404
        # Upgrade stale drafts to the current per-listing fee before checkout.
        if listing.posting_fee_kes != LISTING_POST_FEE_KES:
            listing.posting_fee_kes = LISTING_POST_FEE_KES
            listing.is_free_post = False
            listing.posting_fee_paid = False
            listing.checkout_url = None
            if listing.status == "pending_payment":
                listing.status = "draft"
            listing.updated_at = datetime.utcnow()
            db.session.commit()
        period_current = bool(listing.posting_fee_paid and listing.posting_fee_expires_at and listing.posting_fee_expires_at > datetime.utcnow())
        if period_current:
            return jsonify({"error": "This listing's 30-day posting period is already covered"}), 409
        if listing.status not in {"draft", "pending_payment", "active", "paused"}:
            return jsonify({"error": "This listing cannot start a posting-fee checkout"}), 409
        if listing.checkout_url and listing.status == "pending_payment":
            existing_payment = Payment.query.filter_by(
                reference=listing.posting_payment_reference,
                user_id=user.id,
                payment_type="shop_posting",
            ).first()
            if existing_payment and existing_payment.status == "pending":
                return jsonify({"redirect_url": listing.checkout_url, "reference": listing.posting_payment_reference, "recovered": True})
            if existing_payment and existing_payment.status == "success":
                from shop_marketplace import fulfill_shop_posting_payment
                fulfill_shop_posting_payment(db, existing_payment)
                listing = listing_for_owner(listing_id, user.id)
                if listing and listing.posting_fee_paid:
                    return jsonify({"error": "This listing's posting fee is already covered"}), 409
            if listing:
                listing.status = "draft"
                listing.checkout_url = None
                db.session.commit()
        reference = f"PZA-shop-post-{listing.id}-{secrets.token_hex(6)}"
        payment = Payment(
            user_id=user.id,
            content_item_id=None,
            amount=LISTING_POST_FEE_KES,
            provider="paystack",
            reference=reference,
            payment_type="shop_posting",
            plan=str(listing.id),
            status="pending",
        )
        db.session.add(payment)
        listing.status = "pending_payment"
        listing.posting_payment_reference = reference
        listing.checkout_url = None
        db.session.commit()
        try:
            callback_url = f"{os.environ.get('BASE_URL', '').rstrip('/')}/shop/payment/callback"
            if not callback_url.startswith("https://"):
                callback_url = None
            _, checkout_url = create_paystack_transaction(
                reference, LISTING_POST_FEE_KES, f"Prepza Shop listing #{listing.id} posting fee", user,
                callback_url=callback_url,
            )
            listing.checkout_url = checkout_url
            db.session.commit()
        except Exception:
            db.session.rollback()
            listing = listing_for_owner(listing_id, user.id)
            if listing:
                listing.status = "draft"
                listing.checkout_url = None
            payment_row = Payment.query.filter_by(reference=reference, user_id=user.id).first()
            if payment_row and payment_row.status == "pending":
                payment_row.status = "failed"
            db.session.commit()
            app.logger.exception("Shop posting fee checkout initialization failed")
            return jsonify({"error": "Paystack checkout could not be started. Your listing is saved; please retry."}), 502
        return jsonify({"redirect_url": checkout_url, "reference": reference})

    @app.get("/shop/payment/callback")
    def shop_payment_callback():
        reference = (request.args.get("reference") or request.args.get("trxref") or "").strip()
        if reference:
            payment = Payment.query.filter_by(reference=reference, payment_type="shop_posting").first()
            if payment:
                try:
                    sync_paystack_payment_status(reference)
                except Exception:
                    app.logger.exception("Shop posting fee callback verification failed")
        return redirect("/?shop_payment=" + quote(reference, safe=""))

    @app.get("/api/shop/payments/<string:reference>")
    def shop_payment_status(reference):
        user, denied = require_user()
        if denied:
            return denied
        payment = Payment.query.filter_by(reference=reference, user_id=user.id, payment_type="shop_posting").first()
        if not payment:
            return jsonify({"error": "Payment not found"}), 404
        listing_id = int(payment.plan) if (payment.plan or "").isdigit() else None
        listing = listing_for_owner(listing_id, user.id) if listing_id else None
        status = payment.status
        if payment.status == "success" and listing and not listing.posting_fee_paid:
            status = "mismatched"
        return jsonify({"status": status, "listing": listing_json(listing, user.id, detail=True) if listing else None})

    @app.post("/api/shop/listings/<int:listing_id>/publish")
    def shop_publish_listing(listing_id):
        user, denied = require_user()
        if denied:
            return denied
        if not csrf_valid():
            return jsonify({"error": "Invalid CSRF token"}), 403
        listing = listing_for_owner(listing_id, user.id)
        if not listing:
            return jsonify({"error": "Listing not found"}), 404
        if listing.status not in {"draft", "pending_payment", "pending_review", "paused", "active"}:
            return jsonify({"error": "This listing cannot be published from its current state"}), 409
        # Older drafts may have been created under the retired free-first-post
        # rule. Normalize them before any publish decision; browser-supplied
        # flags and legacy database values must never grant a free post.
        if listing.posting_fee_kes != LISTING_POST_FEE_KES:
            listing.posting_fee_kes = LISTING_POST_FEE_KES
            listing.is_free_post = False
            listing.posting_fee_paid = False
            listing.checkout_url = None
            if listing.status == "pending_payment":
                listing.status = "draft"
            listing.updated_at = datetime.utcnow()
            db.session.commit()
        period_current = bool(listing.posting_fee_paid and listing.posting_fee_expires_at and listing.posting_fee_expires_at > datetime.utcnow())
        if listing.status == "pending_payment" or not period_current:
            return jsonify({"error": "A KES 100 fee must be paid for the current 30-day listing period before publishing", "code": "SHOP_POSTING_FEE_REQUIRED", "fee_kes": LISTING_POST_FEE_KES}), 402
        if not listing.image_keys:
            return jsonify({"error": "Add at least one product photo before publishing"}), 400
        if listing.status == "paused":
            listing.status = "pending_review"
        else:
            listing.status = "pending_review"
        listing.moderation_note = None
        listing.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"listing": listing_json(listing, user.id, detail=True), "message": "Submitted for review. It will appear in Shop after approval."}), 200

    @app.post("/api/shop/listings/<int:listing_id>/pause")
    def shop_pause_listing(listing_id):
        user, denied = require_user()
        if denied:
            return denied
        if not csrf_valid():
            return jsonify({"error": "Invalid CSRF token"}), 403
        listing = listing_for_owner(listing_id, user.id)
        if not listing or listing.status != "active":
            return jsonify({"error": "Active listing not found"}), 404
        listing.status = "paused"
        listing.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"listing": listing_json(listing, user.id, detail=True)})

    @app.post("/api/shop/listings/<int:listing_id>/mark-sold")
    def shop_mark_listing_sold(listing_id):
        user, denied = require_user()
        if denied:
            return denied
        if not csrf_valid():
            return jsonify({"error": "Invalid CSRF token"}), 403
        listing = listing_for_owner(listing_id, user.id)
        if not listing or listing.status not in {"active", "paused"}:
            return jsonify({"error": "Listing cannot be marked sold"}), 409
        listing.status = "sold"
        listing.sold_at = datetime.utcnow()
        listing.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"listing": listing_json(listing, user.id, detail=True)})

    @app.delete("/api/shop/listings/<int:listing_id>")
    def shop_remove_listing(listing_id):
        user, denied = require_user()
        if denied:
            return denied
        if not csrf_valid():
            return jsonify({"error": "Invalid CSRF token"}), 403
        listing = listing_for_owner(listing_id, user.id)
        if not listing:
            return jsonify({"error": "Listing not found"}), 404
        if listing.status in {"pending_payment", "payment_review"}:
            return jsonify({"error": "Finish or reconcile the posting-fee checkout before removing this listing"}), 409
        # Delete product images on explicit removal to stop charging storage for
        # objects the seller no longer wants published. S3 DeleteObject is
        # idempotent, so a retry safely handles partial provider failures.
        if listing.image_keys:
            try:
                from object_storage import r2_delete
                for key in list(listing.image_keys):
                    r2_delete("shop-listings", key)
            except Exception:
                app.logger.exception("Shop listing image cleanup failed")
                return jsonify({"error": "The listing could not be fully removed because photo cleanup failed. Please retry."}), 503
            listing.image_keys = []
        listing.status = "removed"
        listing.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"ok": True})

    @app.post("/api/shop/listings/<int:listing_id>/save")
    def shop_save_listing(listing_id):
        user, denied = require_user()
        if denied:
            return denied
        if not csrf_valid():
            return jsonify({"error": "Invalid CSRF token"}), 403
        listing = ShopListing.query.filter_by(id=listing_id, status="active").filter(ShopListing.posting_fee_expires_at > datetime.utcnow()).first()
        if not listing:
            return jsonify({"error": "Listing not found"}), 404
        saved = ShopSavedListing.query.filter_by(user_id=user.id, listing_id=listing_id).first()
        if not saved:
            db.session.add(ShopSavedListing(user_id=user.id, listing_id=listing_id))
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
        return jsonify({"saved": True})

    @app.delete("/api/shop/listings/<int:listing_id>/save")
    def shop_unsave_listing(listing_id):
        user, denied = require_user()
        if denied:
            return denied
        if not csrf_valid():
            return jsonify({"error": "Invalid CSRF token"}), 403
        ShopSavedListing.query.filter_by(user_id=user.id, listing_id=listing_id).delete(synchronize_session=False)
        db.session.commit()
        return jsonify({"saved": False})

    @app.get("/api/shop/saved")
    def shop_saved_listings():
        user, denied = require_user()
        if denied:
            return denied
        rows = (ShopListing.query.join(ShopSavedListing, ShopSavedListing.listing_id == ShopListing.id)
                .filter(ShopSavedListing.user_id == user.id, ShopListing.status == "active", ShopListing.posting_fee_expires_at > datetime.utcnow())
                .order_by(ShopSavedListing.created_at.desc()).limit(100).all())
        return jsonify({"listings": [listing_json(row, user.id, detail=True) for row in rows]})

    @app.post("/api/shop/listings/<int:listing_id>/report")
    @limiter.limit("10 per day")
    def shop_report_listing(listing_id):
        user, denied = require_user()
        if denied:
            return denied
        if not csrf_valid():
            return jsonify({"error": "Invalid CSRF token"}), 403
        listing = ShopListing.query.filter_by(id=listing_id, status="active").filter(ShopListing.posting_fee_expires_at > datetime.utcnow()).first()
        if not listing or listing.seller_id == user.id:
            return jsonify({"error": "Listing not found"}), 404
        data = request.get_json(silent=True) or {}
        reason = str(data.get("reason") or "").strip()
        details = str(data.get("details") or "").strip()
        if reason not in {"scam", "prohibited_item", "misleading", "harassment", "spam", "other"}:
            return jsonify({"error": "Choose a valid report reason"}), 400
        if len(details) > 1000:
            return jsonify({"error": "Report details must be 1,000 characters or fewer"}), 400
        report = ShopReport(listing_id=listing.id, reporter_id=user.id, reason=reason, details=details or None)
        db.session.add(report)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return jsonify({"error": "You have already reported this listing"}), 409
        return jsonify({"ok": True, "message": "Report received for review"}), 201

    @app.get("/api/shop/admin/queue")
    def shop_admin_queue():
        user, denied = require_user()
        if denied:
            return denied
        if not getattr(user, "is_admin", False):
            return jsonify({"error": "Admin access required"}), 403
        pending = ShopListing.query.filter_by(status="pending_review").order_by(ShopListing.created_at.asc()).limit(100).all()
        payment_reviews = ShopListing.query.filter_by(status="payment_review").order_by(ShopListing.updated_at.asc()).limit(100).all()
        reports = ShopReport.query.filter_by(status="open").order_by(ShopReport.created_at.asc()).limit(100).all()
        return jsonify({
            "listings": listing_json_batch(pending, user.id, detail=True),
            "payment_reviews": listing_json_batch(payment_reviews, user.id, detail=True),
            "reports": [{"id": r.id, "listing_id": r.listing_id, "reason": r.reason, "details": r.details, "reporter_id": r.reporter_id, "created_at": r.created_at.isoformat()} for r in reports],
        })

    @app.post("/api/shop/admin/listings/<int:listing_id>/moderate")
    def shop_admin_moderate_listing(listing_id):
        user, denied = require_user()
        if denied:
            return denied
        if not csrf_valid():
            return jsonify({"error": "Invalid CSRF token"}), 403
        if not getattr(user, "is_admin", False):
            return jsonify({"error": "Admin access required"}), 403
        listing = db.session.get(ShopListing, listing_id)
        if not listing:
            return jsonify({"error": "Listing not found"}), 404
        data = request.get_json(silent=True) or {}
        action = data.get("action")
        note = str(data.get("note") or "").strip()[:500]
        if action not in {"approve", "reject", "remove"}:
            return jsonify({"error": "Choose approve, reject or remove"}), 400
        if action == "approve":
            if not listing.image_keys:
                return jsonify({"error": "Listing must have at least one photo before approval"}), 409
            if listing.posting_fee_kes != LISTING_POST_FEE_KES:
                listing.posting_fee_kes = LISTING_POST_FEE_KES
                listing.is_free_post = False
                listing.posting_fee_paid = False
                listing.status = "draft"
                listing.checkout_url = None
                listing.updated_at = datetime.utcnow()
                db.session.commit()
                return jsonify({"error": "Legacy listing requires the KES 100 posting fee before approval"}), 409
            if not listing.posting_fee_paid or not listing.posting_fee_expires_at or listing.posting_fee_expires_at <= datetime.utcnow():
                return jsonify({"error": "The current 30-day posting fee is not verified"}), 409
            listing.status = "active"
        elif action == "reject":
            listing.status = "rejected"
        else:
            if listing.image_keys:
                try:
                    from object_storage import r2_delete
                    for key in list(listing.image_keys):
                        r2_delete("shop-listings", key)
                except Exception:
                    app.logger.exception("Shop moderation image cleanup failed")
                    return jsonify({"error": "Could not remove the listing photos; retry the moderation action."}), 503
                listing.image_keys = []
            listing.status = "removed"
        listing.moderation_note = note or None
        listing.moderated_by = user.id
        listing.moderated_at = datetime.utcnow()
        listing.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"listing": listing_json(listing, user.id, detail=True)})

    @app.post("/api/shop/admin/listings/<int:listing_id>/resolve-payment")
    def shop_admin_resolve_payment_issue(listing_id):
        user, denied = require_user()
        if denied:
            return denied
        if not csrf_valid():
            return jsonify({"error": "Invalid CSRF token"}), 403
        if not getattr(user, "is_admin", False):
            return jsonify({"error": "Admin access required"}), 403
        listing = db.session.get(ShopListing, listing_id)
        if not listing or listing.status != "payment_review":
            return jsonify({"error": "Shop payment review item not found"}), 404
        data = request.get_json(silent=True) or {}
        action = data.get("action")
        note = str(data.get("note") or "").strip()[:500]
        if action not in {"confirm_paid", "allow_retry"}:
            return jsonify({"error": "Choose confirm_paid or allow_retry"}), 400
        if len(note) < 10:
            return jsonify({"error": "Record at least 10 characters of provider verification evidence"}), 400
        payment = Payment.query.filter_by(
            reference=listing.posting_payment_reference,
            user_id=listing.seller_id,
            payment_type="shop_posting",
            status="success",
        ).first()
        if action == "confirm_paid":
            if not payment or int(payment.amount) != LISTING_POST_FEE_KES:
                return jsonify({"error": "No successful KES 100 Shop posting payment is recorded. Verify provider evidence before confirming."}), 409
            # This is a privileged manual reconciliation after checking the
            # provider dashboard for the exact reference, KES amount and currency.
            listing.posting_fee_paid = True
        else:
            # Only choose this after confirming no fee was captured, or the
            # incorrect charge has been handled outside Prepza.
            listing.posting_fee_paid = False
        listing.status = "draft"
        listing.checkout_url = None
        listing.posting_payment_reviewed_by = user.id
        listing.posting_payment_reviewed_at = datetime.utcnow()
        listing.posting_payment_review_note = note
        listing.moderation_note = None
        listing.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"listing": listing_json(listing, user.id, detail=True)})

    @app.post("/api/shop/admin/reports/<int:report_id>/resolve")
    def shop_admin_resolve_report(report_id):
        user, denied = require_user()
        if denied:
            return denied
        if not csrf_valid():
            return jsonify({"error": "Invalid CSRF token"}), 403
        if not getattr(user, "is_admin", False):
            return jsonify({"error": "Admin access required"}), 403
        report = db.session.get(ShopReport, report_id)
        if not report:
            return jsonify({"error": "Report not found"}), 404
        report.status = "resolved"
        report.reviewed_by = user.id
        report.reviewed_at = datetime.utcnow()
        db.session.commit()
        return jsonify({"ok": True})

    app._prepza_shop_registered = True
    return {"Listing": ShopListing, "SavedListing": ShopSavedListing, "Report": ShopReport}
