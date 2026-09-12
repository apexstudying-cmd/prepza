from pathlib import Path

APP = Path("app.py")


def remove_duplicate_unscoped_podcast_blocks(text):
    block = '''    if document.user_id != user_id:\n        material = GeneratedMaterial.query.filter_by(\n            document_content_id=document.document_content_id,\n            material_type="podcast",\n            status="ready",\n        ).first()\n        if not material or not material.payload:\n            return jsonify({"error": "Podcast has not been published yet"}), 404\n        record_document_studied(user_id, content.id)\n        db.session.commit()\n        return jsonify({\n            "material_id": material.id,\n            "reused": True,\n            "podcast": json.loads(material.payload),\n        }), 200\n\n'''
    if block in text:
        text = text.replace(block, "")
    return text


def collapse_after_first(text, block, label):
    count = text.count(block)
    if count == 0:
        raise SystemExit(f"{label}: expected block not found")
    if count == 1:
        return text
    first = text.find(block)
    head = text[: first + len(block)]
    tail = text[first + len(block):]
    return head + tail.replace(block, "")


def main():
    s = APP.read_text()

    # Older patch runs could leave an unscoped published-podcast branch
    # alongside the current shared-artifact branch. Remove the legacy
    # branch as a whole; never delete only its return statement, which can
    # leave a syntactically empty `if` block.
    s = remove_duplicate_unscoped_podcast_blocks(s)

    podcast_shared = '''    if document.user_id != user_id:\n        material = GeneratedMaterial.query.filter_by(\n            document_content_id=document.document_content_id,\n            material_type="podcast",\n            status="ready",\n            scope="shared",\n            owner_user_id=None,\n        ).first()'''
    s = collapse_after_first(s, podcast_shared, "published podcast shared lookup")

    audio_guard = '''    if document.user_id != user_id:\n        return jsonify({"error": "Podcast audio is not ready yet"}), 409\n\n'''
    s = collapse_after_first(s, audio_guard, "podcast audio owner-only synthesis guard")

    APP.write_text(s)
    print("study-flow access blocks normalized")


if __name__ == "__main__":
    main()
