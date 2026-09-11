from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

AI_SERVICE_WRAPPERS = {
    "generate_document_summary": '''def generate_document_summary(document_content_id, triggering_user_id, plan_tier="free", parameters=None):\n    from ai_reusable_generation import generate_document_material\n    return generate_document_material(material_type="summary", document_content_id=document_content_id, triggering_user_id=triggering_user_id, plan_tier=plan_tier, parameters=parameters)\n''',
    "generate_document_quiz": '''def generate_document_quiz(document_content_id, triggering_user_id, plan_tier="free", parameters=None):\n    from ai_reusable_generation import generate_document_material\n    return generate_document_material(material_type="quiz", document_content_id=document_content_id, triggering_user_id=triggering_user_id, plan_tier=plan_tier, parameters=parameters)\n''',
    "generate_document_flashcards": '''def generate_document_flashcards(document_content_id, triggering_user_id, plan_tier="free", parameters=None):\n    from ai_reusable_generation import generate_document_material\n    return generate_document_material(material_type="flashcards", document_content_id=document_content_id, triggering_user_id=triggering_user_id, plan_tier=plan_tier, parameters=parameters)\n''',
    "generate_document_podcast_script": '''def generate_document_podcast_script(document_content_id, triggering_user_id, plan_tier="free", parameters=None):\n    from ai_reusable_generation import generate_document_material\n    return generate_document_material(material_type="podcast", document_content_id=document_content_id, triggering_user_id=triggering_user_id, plan_tier=plan_tier, parameters=parameters)\n''',
    "generate_document_mindmap": '''def generate_document_mindmap(document_content_id, triggering_user_id, plan_tier="free", parameters=None):\n    from ai_reusable_generation import generate_document_material\n    return generate_document_material(material_type="mind_map", document_content_id=document_content_id, triggering_user_id=triggering_user_id, plan_tier=plan_tier, parameters=parameters)\n''',
}


def replace_functions(path: Path, replacements: dict[str, str]) -> None:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    nodes = {node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    lines = source.splitlines(keepends=True)
    edits = []
    for name, replacement in replacements.items():
        node = nodes.get(name)
        if node is None:
            raise RuntimeError(f"Could not find {name} in {path}")
        start = sum(len(line) for line in lines[: node.lineno - 1])
        end = sum(len(line) for line in lines[: node.end_lineno])
        edits.append((start, end, replacement + "\n"))
    for start, end, replacement in sorted(edits, reverse=True):
        source = source[:start] + replacement + source[end:]
    ast.parse(source)
    path.write_text(source, encoding="utf-8")


def patch_generated_material_model() -> None:
    path = ROOT / "app.py"
    source = path.read_text(encoding="utf-8")
    anchor = '    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)\n\n    # ---- Content review (Chunk 10) ----'
    addition = '''    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)\n\n    generation_fingerprint = db.Column(db.String(128), nullable=False)\n    generation_parameters = db.Column(db.JSON, nullable=True)\n    generation_version = db.Column(db.String(50), nullable=False, default="v1")\n    scope = db.Column(db.String(20), nullable=False, default="shared")\n    owner_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)\n\n    # ---- Content review (Chunk 10) ----'''
    if anchor not in source:
        raise RuntimeError("GeneratedMaterial model anchor not found")
    source = source.replace(anchor, addition, 1)
    old = '        db.UniqueConstraint("document_content_id", "material_type", name="uq_material_content_type"),'
    new = '        db.Index("uq_generated_material_fingerprint", "generation_fingerprint", unique=True),'
    if old not in source:
        raise RuntimeError("GeneratedMaterial legacy unique constraint not found")
    source = source.replace(old, new, 1)
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
            '            document_content_id=content.id,\n'
            '            triggering_user_id=user_id,\n'
            '            plan_tier=get_ai_plan_tier(user_id),\n'
        )
        new_call = old_call + '            parameters=request.get_json(silent=True) or {},\n'
        if old_call not in block:
            raise RuntimeError(f"AI call block missing for {material_type}")
        block = block.replace(old_call, new_call, 1)
        block = block.replace('        "reused": result["reused"],\n', '        "reused": False,\n', 1)
        source = source[:start] + block + source[end:]
    path.write_text(source, encoding="utf-8")


def patch_user_material_lookup() -> None:
    path = ROOT / "app.py"
    source = path.read_text(encoding="utf-8")
    anchor = '\n\nclass AiJob(db.Model):'
    helper = '''\n\ndef get_generated_material_for_user(document_content_id, material_type, user_id):\n    """Return the material visible to this user under the canonical/private boundary."""\n    public = (\n        db.session.query(LibraryPublication.id)\n        .join(Document, LibraryPublication.document_id == Document.id)\n        .filter(\n            Document.document_content_id == document_content_id,\n            LibraryPublication.status == "approved",\n        )\n        .first()\n    )\n    query = GeneratedMaterial.query.filter_by(\n        document_content_id=document_content_id, material_type=material_type, status="ready"\n    )\n    if public:\n        return query.filter(GeneratedMaterial.scope == "shared").first()\n    return query.filter(\n        GeneratedMaterial.scope == "private", GeneratedMaterial.owner_user_id == user_id\n    ).first()\n'''
    if anchor not in source:
        raise RuntimeError("AiJob model anchor not found")
    source = source.replace(anchor, helper + anchor, 1)

    replacements = [
        ('GeneratedMaterial.query.filter_by(\n        document_content_id=document.document_content_id, material_type="podcast"\n    ).first()', 'get_generated_material_for_user(document.document_content_id, "podcast", user_id)'),
        ('GeneratedMaterial.query.filter_by(\n        document_content_id=document.document_content_id, material_type="podcast"\n    ).first()', 'get_generated_material_for_user(document.document_content_id, "podcast", user_id)'),
    ]
    for old, new in replacements:
        source = source.replace(old, new)

    # Podcast library uses a content join; constrain the material to either a
    # public shared artifact or the requesting owner's private artifact.
    old_join = '            GeneratedMaterial.material_type == "podcast",\n            GeneratedMaterial.status == "ready",\n'
    new_join = '''            GeneratedMaterial.material_type == "podcast",\n            GeneratedMaterial.status == "ready",\n            db.or_(\n                GeneratedMaterial.scope == "shared",\n                db.and_(GeneratedMaterial.scope == "private", GeneratedMaterial.owner_user_id == user_id),\n            ),\n'''
    if old_join in source:
        source = source.replace(old_join, new_join, 1)
    path.write_text(source, encoding="utf-8")


def main() -> None:
    patch_generated_material_model()
    patch_user_material_lookup()
    patch_ai_routes()
    replace_functions(ROOT / "ai_service.py", AI_SERVICE_WRAPPERS)
    print("AI generation architecture patch applied")


if __name__ == "__main__":
    main()
