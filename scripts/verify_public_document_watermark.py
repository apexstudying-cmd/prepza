from pathlib import Path

s = Path("app.py").read_text()

required = [
    'def _approved_library_publication(document):',
    'def _document_reader_watermark(user_id, document):',
    'return "SOURCED FROM PREPZA"',
    'watermark = _document_reader_watermark(user_id, document)',
]
for anchor in required:
    if anchor not in s:
        raise SystemExit(f"missing watermark safety anchor: {anchor}")

legacy = 'watermark = (viewer.email if viewer and viewer.email else "Prepza")'
if legacy in s:
    raise SystemExit("legacy unconditional viewer-email watermark remains")

print("public document watermark safety anchors verified")
