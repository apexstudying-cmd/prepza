from pathlib import Path
import re

app = Path('frontend/src/App.tsx').read_text(encoding='utf-8')

patterns = [
    r'if\\s*\\([^\\n)]*\\bloading\\b[^\\n)]*\\)[^\\n]*return',
    r'return\\s*<Skeleton[A-Za-z0-9_]*',
    r'<GenerationLoading\\b',
    r'Opening your document',
    r'Loading[.…]{3}',
]

print('SCREEN_LOADING_AUDIT_BEGIN')
for pattern in patterns:
    matches = list(re.finditer(pattern, app, flags=re.IGNORECASE))
    print(f'{pattern}: {len(matches)}')
    for match in matches[:40]:
        start = max(0, match.start() - 140)
        end = min(len(app), match.end() + 180)
        excerpt = ' '.join(app[start:end].split())
        print(f'  - {excerpt}')
print(f'App.tsx characters: {len(app)}')
print('SCREEN_LOADING_AUDIT_END')
