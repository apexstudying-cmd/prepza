from pathlib import Path
p = Path('app.py')
s = p.read_text()
s = s.replace('return bool(pub and document.id not in _flagged_document_ids())', 'return bool(pub)', 1)
old = '''    try:\n        pdf = fitz.open(stream=file_bytes, filetype="pdf")\n        try:\n            pix = pdf.load_page(page_num).get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False)\n            image_bytes = pix.tobytes("png")\n        finally: pdf.close()\n    except Exception: return jsonify({"error": "Document page could not be rendered"}), 500\n'''
new = '''    viewer = db.session.get(User, user_id)\n    watermark = (viewer.email if viewer and viewer.email else "Prepza")\n    try:\n        image_bytes, _ = render_watermarked_page(file_bytes, page_num, watermark, zoom=1.6)\n    except Exception:\n        return jsonify({"error": "Document page could not be rendered"}), 500\n'''
if old in s: s = s.replace(old, new, 1)
elif new not in s: raise SystemExit('reader rendering block not found')
p.write_text(s)
print('reader security patch applied')
