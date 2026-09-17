from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
p = ROOT / 'app.py'
s = p.read_text(encoding='utf-8')
old = '    unit = None if group.unit_id else None\n'
if old in s:
    s = s.replace(old, '    unit = None\n', 1)
    p.write_text(s, encoding='utf-8')
    print('GROUP_BROWSE_SERIALIZER_FIXED')
elif '    unit = None\n' in s:
    print('GROUP_BROWSE_SERIALIZER_ALREADY_FIXED')
else:
    raise SystemExit('Expected groups serializer anchor not found')
