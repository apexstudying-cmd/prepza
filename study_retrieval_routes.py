"""Authenticated HTTP boundary for ordinary (non-E2EE) study-note retrieval."""
from flask import jsonify, request, session

from study_retrieval_service import retrieve_authorized_pages


def register_study_retrieval_routes(app, db, login_required, require_csrf):
    if getattr(app, "_prepza_study_retrieval_routes_registered", False):
        return
    app._prepza_study_retrieval_routes_registered = True

    @app.route("/api/study/retrieval", methods=["POST"])
    @login_required
    @require_csrf
    def retrieve_study_context():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "A JSON request body is required"}), 400
        query = payload.get("query")
        if not isinstance(query, str) or not query.strip() or len(query) > 1000:
            return jsonify({"error": "query must contain 1 to 1000 characters"}), 400

        document_id = payload.get("document_id")
        if document_id is not None and (
            not isinstance(document_id, int) or isinstance(document_id, bool) or document_id <= 0
        ):
            return jsonify({"error": "document_id must be a positive integer"}), 400

        try:
            results = retrieve_authorized_pages(
                db.session,
                user_id=session["user_id"],
                query=query.strip(),
                document_id=document_id,
                top_k=5,
            )
        except Exception:
            db.session.rollback()
            app.logger.exception("Study retrieval failed")
            return jsonify({"error": "Study context is temporarily unavailable"}), 503

        # An explicitly requested document that returns no accessible page is
        # indistinguishable from a missing/not-ready document, avoiding ID leaks.
        if document_id is not None and not results:
            return jsonify({"error": "Document not found or not ready"}), 404

        return jsonify({
            "query": query.strip(),
            "results": [{
                "text": result.text[:1200],
                "score": round(result.score, 5),
                "citation": result.citation,
            } for result in results],
        }), 200
