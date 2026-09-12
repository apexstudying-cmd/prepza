from pathlib import Path

APP = Path("app.py")


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

    podcast_shared = '''    if document.user_id != user_id:\n        material = GeneratedMaterial.query.filter_by(\n            document_content_id=document.document_content_id,\n            material_type="podcast",\n            status="ready",\n            scope="shared",\n            owner_user_id=None,\n        ).first()'''
    s = collapse_after_first(s, podcast_shared, "published podcast shared lookup")

    podcast_error = '            return jsonify({"error": "Podcast has not been published yet"}), 404\n'
    if s.count(podcast_error) != 1:
        # Keep the first published-viewer error and remove only duplicate
        # occurrences introduced by older patch runs.
        first = s.find(podcast_error)
        head = s[: first + len(podcast_error)]
        tail = s[first + len(podcast_error):]
        s = head + tail.replace(podcast_error, "")

    audio_guard = '''    if document.user_id != user_id:\n        return jsonify({"error": "Podcast audio is not ready yet"}), 409\n\n'''
    s = collapse_after_first(s, audio_guard, "podcast audio owner-only synthesis guard")

    # The shared artifact lookup must be explicit in both podcast paths.
    shared_audio = '''    else:\n        material = GeneratedMaterial.query.filter_by(\n            document_content_id=document.document_content_id,\n            material_type="podcast",\n            status="ready",\n            scope="shared",\n            owner_user_id=None,\n        ).first()'''
    if s.count(shared_audio) < 2:
        raise SystemExit("expected shared podcast lookup in both audio endpoints")

    APP.write_text(s)
    print("study-flow access blocks normalized")


if __name__ == "__main__":
    main()
