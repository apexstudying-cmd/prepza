"""Native document-reader routes, registered with explicit app-owned dependencies."""
from __future__ import annotations

from typing import Any, Callable

from flask import Response, jsonify, request, session


def register_document_reader_routes(
    app: Any,
    db: Any,
    *,
    DocumentReadingProgress: Any,
    require_csrf: Callable[[Callable[..., Any]], Callable[..., Any]],
    get_studyable_document: Callable[[Any, int], tuple[Any, Any] | None],
    document_reader_watermark: Callable[[Any, Any], str],
    fetch_private_file_bytes: Callable[..., bytes | None],
    render_watermarked_page: Callable[..., tuple[bytes, Any]],
) -> None:
    """Register the existing reader progress and private rendered-page routes."""

    @app.route("/documents/<int:document_id>/reading", methods=["GET"])
    def get_document_reading(document_id):
        user_id = session.get("user_id")
        if not user_id: return jsonify({"error": "Not logged in"}), 401
        pair = get_studyable_document(user_id, document_id)
        if not pair: return jsonify({"error": "Document not found"}), 404
        document, content = pair
        progress = DocumentReadingProgress.query.filter_by(user_id=user_id, document_id=document.id).first()
        page_num = progress.page_num if progress else 0
        max_page = max(0, (content.page_count or 1) - 1)
        return jsonify({"document_id": document.id, "page_num": min(max(0, page_num), max_page), "page_count": content.page_count})


    @app.route("/documents/<int:document_id>/reading", methods=["POST"])
    @require_csrf
    def save_document_reading(document_id):
        user_id = session.get("user_id")
        if not user_id: return jsonify({"error": "Not logged in"}), 401
        pair = get_studyable_document(user_id, document_id)
        if not pair: return jsonify({"error": "Document not found"}), 404
        document, content = pair
        data = request.get_json(silent=True) or {}
        page_num = data.get("page_num")
        if not isinstance(page_num, int) or isinstance(page_num, bool) or page_num < 0: return jsonify({"error": "page_num must be a non-negative integer"}), 400
        max_page = max(0, (content.page_count or 1) - 1)
        if page_num > max_page: return jsonify({"error": "page_num is outside the document"}), 400
        progress = DocumentReadingProgress.query.filter_by(user_id=user_id, document_id=document.id).first()
        if not progress: db.session.add(DocumentReadingProgress(user_id=user_id, document_id=document.id, page_num=page_num))
        else: progress.page_num = page_num
        db.session.commit()
        return jsonify({"ok": True, "page_num": page_num})


    @app.route("/documents/<int:document_id>/reading/page/<int:page_num>")
    def render_document_reading_page(document_id, page_num):
        user_id = session.get("user_id")
        if not user_id: return jsonify({"error": "Not logged in"}), 401
        pair = get_studyable_document(user_id, document_id)
        if not pair: return jsonify({"error": "Document not found"}), 404
        document, content = pair
        if content.file_type != "pdf": return jsonify({"error": "Native reading currently supports PDF documents only"}), 415
        if page_num < 0 or content.page_count is None or page_num >= content.page_count: return jsonify({"error": "Page not found"}), 404
        file_bytes = fetch_private_file_bytes(content.storage_path, bucket="documents")
        if not file_bytes: return jsonify({"error": "Document file could not be loaded"}), 502
        watermark = document_reader_watermark(user_id, document)
        try:
            image_bytes, _ = render_watermarked_page(file_bytes, page_num, watermark, zoom=1.6)
        except Exception:
            return jsonify({"error": "Document page could not be rendered"}), 500
        response = Response(image_bytes, mimetype="image/png")
        response.headers["Cache-Control"] = "private, no-store, max-age=0"
        response.headers["Content-Disposition"] = "inline"
        return response
