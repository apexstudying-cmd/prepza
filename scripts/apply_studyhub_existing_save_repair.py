from pathlib import Path

path = Path("app.py")
s = path.read_text()

old = '''    if existing:\n        db.session.commit()\n        return jsonify({\n            "message": "Already saved",\n            "document_id": studyhub_document.id,\n            "in_studyhub": True,\n            "save_count": publication.save_count,\n        }), 200\n'''

new = '''    if existing:\n        # A legacy SavedLibraryMaterial row may predate the StudyHub-document\n        # guarantee. In that case _ensure_studyhub_document_for_publication\n        # returns a new, transient Document that must be persisted here.\n        if studyhub_document.id is None:\n            db.session.add(studyhub_document)\n            db.session.flush()\n        db.session.commit()\n        return jsonify({\n            "message": "Already saved",\n            "document_id": studyhub_document.id,\n            "in_studyhub": True,\n            "save_count": publication.save_count,\n        }), 200\n'''

if old in s:
    s = s.replace(old, new, 1)
elif new in s:
    print("StudyHub existing-save repair already applied")
else:
    raise SystemExit("could not find existing Library save branch")

path.write_text(s)
print("Applied StudyHub existing-save repair")
