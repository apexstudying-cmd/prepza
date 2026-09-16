from pathlib import Path
import re

app = Path('frontend/src/App.tsx').read_text(encoding='utf-8')

patterns = [
    r'if\s*\([^\n)]*\bloading\b[^\n)]*\)[^\n]*return',
    r'return\s*<Skeleton[A-Za-z0-9_]*',
    r'<GenerationLoading\b',
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

api_count = len(re.findall(r'async function api<T = any>\(', app))
request_count = len(re.findall(r'async function requestApiJson<T>', app))
cache_count = len(re.findall(r'const screenApiCache = new Map', app))
offline_db_count = len(re.findall(r"const PREPZA_OFFLINE_DB = 'prepza-offline-v1'", app))
refresh_count = len(re.findall(r'function refreshScreenApiCache<T>', app))

print(f'api_helper_count: {api_count}')
print(f'request_json_helper_count: {request_count}')
print(f'screen_cache_definition_count: {cache_count}')
print(f'offline_db_definition_count: {offline_db_count}')
print(f'background_refresh_helper_count: {refresh_count}')

if api_count != 1:
    raise SystemExit('SCREEN_LOADING_AUDIT_FAILED: duplicate or missing api helper')
if request_count != 1 or cache_count != 1 or offline_db_count != 1 or refresh_count != 1:
    raise SystemExit('SCREEN_LOADING_AUDIT_FAILED: duplicate or missing cache/offline implementation')

print(f'App.tsx characters: {len(app)}')
print('SCREEN_LOADING_AUDIT_END')
