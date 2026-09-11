from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MATERIALS = {
    "summary": "generate_document_summary",
    "quiz": "generate_document_quiz",
    "flashcards": "generate_document_flashcards",
    "podcast": "generate_document_podcast_script",
    "mind_map": "generate_document_mindmap",
}


def _top_level_function(source: str, name: str):
    tree = ast.parse(source)
    return next(
        (node for node in tree.body
         if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name),
        None,
    )


def _install_wrapper(source: str, material_type: str, public_name: str) -> str:
    if f"def {public_name}(" in source:
        return source

    legacy_name = f"_legacy_{public_name}"
    node = _top_level_function(source, legacy_name)
    if node is None:
        raise RuntimeError(f"Could not locate top-level legacy generator {legacy_name}")

    wrapper = f'''def {public_name}(document_content_id, triggering_user_id, plan_tier="free", parameters=None):
    from ai_reusable_generation import generate_document_material
    return generate_document_material(
        material_type="{material_type}",
        document_content_id=document_content_id,
        triggering_user_id=triggering_user_id,
        plan_tier=plan_tier,
        parameters=parameters,
    )

'''
    lines = source.splitlines(keepends=True)
    start = sum(len(line) for line in lines[: node.lineno - 1])
    updated = source[:start] + wrapper + source[start:]
    ast.parse(updated)
    return updated


def patch_legacy_generators() -> None:
    path = ROOT / "ai_service.py"
    source = path.read_text(encoding="utf-8")

    for material_type, public_name in MATERIALS.items():
        if f"def {public_name}(" in source:
            continue
        legacy_name = f"_legacy_{public_name}"
        if f"def {legacy_name}(" not in source:
            node = _top_level_function(source, public_name)
            if node is None:
                raise RuntimeError(f"Could not find {public_name}")
            lines = source.splitlines(keepends=True)
            start = sum(len(line) for line in lines[: node.lineno - 1])
            end = sum(len(line) for line in lines[: node.end_lineno])
            original = source[start:end]
            renamed = original.replace(f"def {public_name}", f"def {legacy_name}", 1)
            source = source[:start] + renamed + source[end:]
            ast.parse(source)
        source = _install_wrapper(source, material_type, public_name)

    path.write_text(source, encoding="utf-8")


def patch_generated_material_model() -> None:
    path = ROOT / "app.py"
    source = path.read_text(encoding="utf-8")
    if "generation_fingerprint = db.Column" not in source:
        anchor = '    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)\n\n    # ---- Content review (Chunk 10) ----'
        addition = '''    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)\n\n    generation_fingerprint = db.Column(db.String(128), nullable=False)\n    generation_parameters = db.Column(db.JSON, nullable=True)\n    generation_version = db.Column(db.String(50), nullable=False, default="v2")\n    scope = db.Column(db.String(20), nullable=False, default="shared")\n    owner_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)\n\n    # ---- Content review (Chunk 10) ----'''
        if anchor not in source:
            raise RuntimeError("GeneratedMaterial model anchor not found")
        source = source.replace(anchor, addition, 1)

    source = source.replace(
        '        db.UniqueConstraint("document_content_id", "material_type", name="uq_material_content_type"),',
        '        db.Index("uq_generated_material_fingerprint", "generation_fingerprint", unique=True),',
        1,
    )
    path.write_text(source, encoding="utf-8")


def patch_ai_routes() -> None:
    path = ROOT / "app.py"
    source = path.read_text(encoding="utf-8")
    routes = {
        "summary": "def summarize_document(document_id):",
        "quiz": "def quiz_document(document_id):",
        "flashcards": "def flashcards_document(document_id):",
        "podcast": "def podcast_script_document(document_id):",
        "mind_map": "def mindmap_document(document_id):",
    }
    for material_type, marker in routes.items():
        start = source.find(marker)
        if start < 0:
            raise RuntimeError(f"Route marker missing for {material_type}")
        next_route = source.find("\n@app.route(", start + 1)
        end = next_route if next_route >= 0 else len(source)
        block = source[start:end]
        old_call = (
            "            document_content_id=content.id,\n"
            "            triggering_user_id=user_id,\n"
            "            plan_tier=get_ai_plan_tier(user_id),\n"
        )
        if "parameters=request.get_json(silent=True) or {}" not in block:
            if old_call not in block:
                raise RuntimeError(f"AI call block missing for {material_type}")
            block = block.replace(old_call, old_call + "            parameters=request.get_json(silent=True) or {},\n", 1)
        block = block.replace('        "reused": result["reused"],\n', '        "reused": False,\n', 1)
        source = source[:start] + block + source[end:]
    path.write_text(source, encoding="utf-8")


def patch_user_material_lookup() -> None:
    path = ROOT / "app.py"
    source = path.read_text(encoding="utf-8")
    if "def get_generated_material_for_user(" not in source:
        anchor = "\n\nclass AiJob(db.Model):"
        helper = '''\n\ndef get_generated_material_for_user(document_content_id, material_type, user_id):\n    """Return ready material without crossing the public/private boundary."""\n    owned = (\n        db.session.query(Document.id)\n        .filter(\n            Document.user_id == user_id,\n            Document.document_content_id == document_content_id,\n            Document.is_removed.is_(False),\n        )\n        .first()\n    )\n    query = GeneratedMaterial.query.filter_by(\n        document_content_id=document_content_id, material_type=material_type, status="ready"\n    )\n    if owned:\n        approved = (\n            db.session.query(LibraryPublication.id)\n            .filter(\n                LibraryPublication.document_id == owned.id,\n                LibraryPublication.status == "approved",\n            )\n            .first()\n        )\n        if approved:\n            return query.filter(GeneratedMaterial.scope == "shared").first()\n        return query.filter(\n            GeneratedMaterial.scope == "private", GeneratedMaterial.owner_user_id == user_id\n        ).first()\n\n    public = (\n        db.session.query(LibraryPublication.id)\n        .join(Document, LibraryPublication.document_id == Document.id)\n        .filter(Document.document_content_id == document_content_id, LibraryPublication.status == "approved")\n        .first()\n    )\n    if public:\n        return query.filter(GeneratedMaterial.scope == "shared").first()\n    return None\n'''
        if anchor not in source:
            raise RuntimeError("AiJob model anchor not found")
        source = source.replace(anchor, helper + anchor, 1)

    # Podcast playback/audio routes must use the same scope gate as generation.
    old_lookup = '''    material = GeneratedMaterial.query.filter_by(
        document_content_id=document.document_content_id, material_type="podcast"
    ).first()'''
    new_lookup = '''    material = get_generated_material_for_user(
        document.document_content_id, "podcast", session.get("user_id")
    )'''
    source = source.replace(old_lookup, new_lookup)
    path.write_text(source, encoding="utf-8")


def main() -> None:
    patch_generated_material_model()
    patch_user_material_lookup()
    patch_ai_routes()
    patch_legacy_generators()
    print("AI generation architecture patch applied")


if __name__ == "__main__":
    main()
