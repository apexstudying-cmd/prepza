"""Public application-shell and process-health HTTP routes.

This module registers the existing root document, root-scoped service worker,
and lightweight health check. Dependencies are passed by the Flask entry
module so route registration never imports a partially initialized app.
"""

from flask import jsonify, send_from_directory


def register_public_shell_routes(app, db, limiter, sweep_expired_opportunities_safe):
    @app.route("/")
    def home():
        return send_from_directory(app.static_folder, "index.html")

    @app.route("/sw.js")
    def service_worker():
        """
        Served at the root URL (not /static/sw.js) so its scope covers the
        whole site, not just the static folder. Deliberately not cached
        long-term, unlike images/CSS/JS, so browsers pick up updates to this
        file quickly.
        """
        response = send_from_directory(app.static_folder, "sw.js")
        response.headers["Content-Type"] = "application/javascript"
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.route("/health")
    @limiter.exempt
    def health():
        """
        Lightweight status check. Pinged automatically every ~10 minutes by a
        GitHub Actions workflow to prevent Render's free tier from spinning down
        and Supabase's free tier from auto-pausing due to inactivity.

        Deliberately excluded from rate limiting (it's an automated, low-value
        target for abuse) and returns no sensitive data.
        """
        from sqlalchemy import text
        try:
            db.session.execute(text("SELECT 1"))
            sweep_expired_opportunities_safe()
            return jsonify({"status": "ok"}), 200
        except Exception:
            return jsonify({"status": "error"}), 503
