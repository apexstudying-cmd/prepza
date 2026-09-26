from pathlib import Path
import re

app = Path('frontend/src/App.tsx').read_text(encoding='utf-8')
api_module = Path('frontend/src/lib/api.ts').read_text(encoding='utf-8')

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

api_count = len(re.findall(r'async function request<T>\(', api_module))
base_api_count = 0
cache_count = len(re.findall(r'const screenApiCache = new Map', app))
refresh_count = len(re.findall(r'function refreshScreenApiCache<T>', app))
offline_db_count = 0
delayed_skeleton_count = len(re.findall(r'function DelayedScreenSkeleton', app))
un_gated_skeleton_count = len(re.findall(r'if\s*\(loading\)\s*return\s*<Skeleton[A-Za-z0-9_]+\s*/>', app))

print(f'api_helper_count: {api_count}')
print(f'base_api_helper_count: {base_api_count}')
print(f'screen_cache_definition_count: {cache_count}')
print(f'background_refresh_helper_count: {refresh_count}')
print(f'offline_db_definition_count: {offline_db_count}')
print(f'delayed_skeleton_helper_count: {delayed_skeleton_count}')
print(f'un_gated_skeleton_return_count: {un_gated_skeleton_count}')

if api_count != 1:
    raise SystemExit('SCREEN_LOADING_AUDIT_FAILED: duplicate or missing modular API request layer')
if cache_count > 1 or refresh_count > 1:
    raise SystemExit('SCREEN_LOADING_AUDIT_FAILED: duplicate legacy screen cache implementation')
if delayed_skeleton_count > 1:
    raise SystemExit('SCREEN_LOADING_AUDIT_FAILED: duplicate delayed skeleton helper')
if un_gated_skeleton_count != 0:
    raise SystemExit('SCREEN_LOADING_AUDIT_FAILED: skeleton rendered without delayed gate')

print(f'App.tsx characters: {len(app)}')
print('SCREEN_LOADING_AUDIT_END')
