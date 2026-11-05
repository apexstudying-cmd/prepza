"""Public read-only university and program lookup routes.

The signup and group-creation flows need this catalog before authentication
or during profile setup. Keep this registrar independent of the app module so
route ownership can move without changing the global application lifecycle.
"""

from flask import jsonify


def register_academic_catalog_routes(app, University, Program):
    """Register the existing public academic catalog endpoints."""

    def list_universities():
        """
        Public, unauthenticated - the signup wizard needs this before a
        session exists. Only returns active universities so a
        deactivated one can't be selected by new signups.
        """
        universities = University.query.filter_by(is_active=True).order_by(University.name).all()
        return jsonify([
            {"id": u.id, "name": u.name, "short_code": u.short_code, "country": u.country}
            for u in universities
        ])

    def list_programs(university_id):
        """
        Public, unauthenticated - same reasoning as /universities above.
        404s on an unknown or inactive university instead of silently
        returning an empty list, so the frontend can tell 'no programs
        yet' apart from 'that university id doesn't exist'.
        """
        university = University.query.filter_by(id=university_id, is_active=True).first()
        if not university:
            return jsonify({"error": "University not found"}), 404

        programs = Program.query.filter_by(university_id=university_id, is_active=True).order_by(Program.name).all()
        return jsonify([
            {
                "id": p.id,
                "name": p.name,
                "degree_level": p.degree_level,
                "discipline_category": p.discipline_category,
            }
            for p in programs
        ])

    # Preserve the original endpoint names as well as the URL/method contract.
    # Existing consumers may depend on these names through Flask's url_for.
    app.add_url_rule(
        "/universities",
        endpoint="list_universities",
        view_func=list_universities,
        methods=["GET"],
    )
    app.add_url_rule(
        "/universities/<int:university_id>/programs",
        endpoint="list_programs",
        view_func=list_programs,
        methods=["GET"],
    )
