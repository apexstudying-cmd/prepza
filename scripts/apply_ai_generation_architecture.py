from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MATERIALS = {
    "summary": "generate_document_summary",
    "quiz": "generate_document_quiz",
    "flashcards": "generate_document_flashcards",
    "podcast": "generate_document_podcast_script",
    "mind_map": "generate_document_mindmap",
}

WRAPPERS = {
    name: f'''def {name}(document_content_id, triggering_user_id, plan_tier="free", parameters=None):
    from ai_reusable_generation import generate_document_material
    return generate_document_material(
        material_type="{material_type}",
        document_content_id=document_content_id,
        triggering_user_id=triggering_user_id,
        plan_tier=plan_tier,
        parameters=parameters,
    )
'''
    for material_type, name in MATERIALS.items()
}


def replace_top_level_function(path: Path, name: str, replacement: str) -> None:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next((n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name), None)
    if node is None:
        raise RuntimeError(f"Could not find {name} in {path}")
    lines = source.splitlines(keepends=True)
    start = sum(len(line) for line in lines[: node.lineno - 1])
    end = sum(len(line) for line in lines[: node.end_lineno])
    source = source[:start] + replacement.rstrip() + "\n" + source[end:]
    ast.parse(source)
    path.write_text(source, encoding="utf-8")


def patch_legacy_generators() -> None:
    path = ROOT / "ai_service.py"
    source = path.read_text(encoding="utf-8")

    for material_type, public_name in MATERIALS.items():
        # A previous successful run already installed the public wrapper.
        # Do not rename or mutate it on subsequent CI runs.
        if f"def {public_name}(" in source and "return generate_document_material(" in source[source.find(f"def {public_name}("):source.find(f"def {public_name}(") + 700]:
            continue

        legacy_name = f"_legacy_{public_name}"
        source, count = re.subn(
            rf"(?m)^def {re.escape(public_name)}\(",
            f"def {legacy_name}(document_content_id, triggering_user_id, plan_tier=\"free\", parameters=None, scope=\"shared\", owner_user_id=None):",
            source,
            count=1,
        )
        if count == 0:
            raise RuntimeError(f"Could not rename {public_name}")

        cache_pattern = (
            rf"existing = GeneratedMaterial\.query\.filter_by\(\n"
            rf"\s*document_content_id=document_content_id, material_type={re.escape(repr(material_type))}\n"
            rf"\s*\)\.first\(\)"
        )
        cache_replacement = (
            "existing = GeneratedMaterial.query.filter_by(\n"
            f"        document_content_id=document_content_id, material_type={material_type!r},\n"
            "        scope=scope, owner_user_id=owner_user_id\n"
            "    ).first()"
        )
        source, count = re.subn(cache_pattern, cache_replacement, source, count=1)
        if count == 0:
            raise RuntimeError(f"Could not scope {material_type} legacy cache lookup")

        create_pattern = (
            rf"GeneratedMaterial\(\n"
            rf"\s*document_content_id=document_content_id, material_type={re.escape(repr(material_type))}\n"
            rf"\s*\)"
        )
        create_replacement = (
            "GeneratedMaterial(\n"
            f"        document_content_id=document_content_id, material_type={material_type!r},\n"
            "        scope=scope, owner_user_id=owner_user_id,\n"
            "        generation_parameters=parameters or {}, generation_version=\"v1\"\n"
            "    )"
        )
        source, count = re.subn(create_pattern, create_replacement, source, count=1)
        if count == 0:
            raise RuntimeError(f"Could not scope {material_type} legacy material creation")

    ast.parse(source)
    path.write_text(source, encoding="utf-8")


def patch_generated_material_model() -> None:
    path = ROOT / "app.py"
    source = path.read_text(encoding="utf-8")
    if "generation_fingerprint = db.Column" not in source:
        anchor = '    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)\n\n    # ---- Content review (Chunk 10) ----'
        addition = '''    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)\n\n    generation_fingerprint = db.Column(db.String(128), nullable=False)\n    generation_parameters = db.Column(db.JSON, nullable=True)\n    generation_version = db.Column(db.String(50), nullable=False, default="v1")\n    scope = db.Column(db.String(20), nullable=False, default="shared")\n    owner_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)\n\n    # ---- Content review (Chunk 10) ----'''
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
        helper = '''\n\ndef get_generated_material_for_user(document_content_id, material_type, user_id):\n    """Return ready material visible to this user under the public/private boundary."""\n    public = (\n        db.session.query(LibraryPublication.id)\n        .join(Document, LibraryPublication.document_id == Document.id)\n        .filter(Document.document_content_id == document_content_id, LibraryPublication.status == "approved")\n        .first()\n    )\n    query = GeneratedMaterial.query.filter_by(\n        document_content_id=document_content_id, material_type=material_type, status="ready"\n    )\n    if public:\n        return query.filter(GeneratedMaterial.scope == "shared").first()\n    return query.filter(\n        GeneratedMaterial.scope == "private", GeneratedMaterial.owner_user_id == user_id\n    ).first()\n'''
        if anchor not in source:
            raise RuntimeError("AiJob model anchor not found")
        source = source.replace(anchor, helper + anchor, 1)
    path.write_text(source, encoding="utf-8")


def main() -> None:
    patch_generated_material_model()
    patch_user_material_lookup()
    patch_ai_routes()
    patch_legacy_generators()
    for public_name, replacement in WRAPPERS.items():
        # Replacing a wrapper with itself is harmless and keeps this step
        # deterministic if a previous run partially completed.
        replace_top_level_function(ROOT / "ai_service.py", public_name, replacement)
    print("AI generation architecture patch applied")


if __name__ == "__main__":
    main()
