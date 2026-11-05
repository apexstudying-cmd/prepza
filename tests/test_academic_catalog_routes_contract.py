"""Guard the public academic lookup routes while moving them out of app.py."""

from dataclasses import dataclass

from flask import Flask

from academic_catalog_routes import register_academic_catalog_routes


class FakeQuery:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter_by(self, **filters):
        return FakeQuery(
            row
            for row in self.rows
            if all(getattr(row, key) == value for key, value in filters.items())
        )

    def order_by(self, field):
        return FakeQuery(sorted(self.rows, key=lambda row: getattr(row, field)))

    def all(self):
        return list(self.rows)

    def first(self):
        return self.rows[0] if self.rows else None


@dataclass
class UniversityRow:
    id: int
    name: str
    short_code: str
    country: str | None
    is_active: bool


@dataclass
class ProgramRow:
    id: int
    university_id: int
    name: str
    degree_level: str | None
    discipline_category: str | None
    is_active: bool


class FakeUniversity:
    name = "name"
    query = FakeQuery([])


class FakeProgram:
    name = "name"
    query = FakeQuery([])


def _client(universities, programs):
    FakeUniversity.query = FakeQuery(universities)
    FakeProgram.query = FakeQuery(programs)
    app = Flask(__name__)
    register_academic_catalog_routes(app, FakeUniversity, FakeProgram)
    return app.test_client(), app


def test_registrar_keeps_original_public_route_paths_and_endpoint_names():
    _, app = _client([], [])

    routes = {
        (rule.rule, rule.endpoint, frozenset(rule.methods))
        for rule in app.url_map.iter_rules()
    }
    assert (
        "/universities",
        "list_universities",
        frozenset({"GET", "HEAD", "OPTIONS"}),
    ) in routes
    assert (
        "/universities/<int:university_id>/programs",
        "list_programs",
        frozenset({"GET", "HEAD", "OPTIONS"}),
    ) in routes


def test_universities_returns_only_active_rows_sorted_by_name_with_existing_shape():
    client, _ = _client(
        [
            UniversityRow(2, "Zeta University", "ZETA", "Kenya", True),
            UniversityRow(3, "Inactive University", "OFF", "Kenya", False),
            UniversityRow(1, "Alpha University", "ALPHA", None, True),
        ],
        [],
    )

    response = client.get("/universities")

    assert response.status_code == 200
    assert response.get_json() == [
        {"id": 1, "name": "Alpha University", "short_code": "ALPHA", "country": None},
        {"id": 2, "name": "Zeta University", "short_code": "ZETA", "country": "Kenya"},
    ]


def test_program_lookup_returns_404_for_missing_or_inactive_university():
    client, _ = _client(
        [UniversityRow(4, "Inactive University", "OFF", "Kenya", False)],
        [],
    )

    missing = client.get("/universities/999/programs")
    inactive = client.get("/universities/4/programs")

    assert missing.status_code == 404
    assert missing.get_json() == {"error": "University not found"}
    assert inactive.status_code == 404
    assert inactive.get_json() == {"error": "University not found"}


def test_program_lookup_returns_only_active_programs_sorted_by_name_with_existing_shape():
    client, _ = _client(
        [UniversityRow(4, "Kenyatta University", "KU", "Kenya", True)],
        [
            ProgramRow(8, 4, "Zoology", "Bachelor", "Science", True),
            ProgramRow(9, 4, "Inactive Course", "Bachelor", "Arts", False),
            ProgramRow(7, 4, "Actuarial Science", "Bachelor", "Mathematics", True),
            ProgramRow(10, 5, "Other University's Course", "Diploma", "Business", True),
        ],
    )

    response = client.get("/universities/4/programs")

    assert response.status_code == 200
    assert response.get_json() == [
        {
            "id": 7,
            "name": "Actuarial Science",
            "degree_level": "Bachelor",
            "discipline_category": "Mathematics",
        },
        {
            "id": 8,
            "name": "Zoology",
            "degree_level": "Bachelor",
            "discipline_category": "Science",
        },
    ]


def test_app_registers_the_extracted_routes_after_models_and_before_signup():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    app_source = (root / "app.py").read_text(encoding="utf-8")
    registrar = "register_academic_catalog_routes(app, University, Program)"
    register_at = app_source.index(registrar)

    assert register_at > app_source.index("class University(db.Model):")
    assert register_at > app_source.index("class Program(db.Model):")
    assert register_at < app_source.index('@app.route("/signup", methods=["POST"])')
    assert '@app.route("/universities")' not in app_source
    assert '@app.route("/universities/<int:university_id>/programs")' not in app_source
    assert "def list_universities(" not in app_source
    assert "def list_programs(" not in app_source
