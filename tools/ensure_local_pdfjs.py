from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'frontend' / 'public' / 'vendor' / 'pdfjs'
VERSION = '6.3.289'
BASE = f'https://cdn.jsdelivr.net/npm/pdfjs-dist@{VERSION}/build'
FILES = ('pdf.mjs', 'pdf.worker.mjs')


def download(name: str) -> None:
    target = OUT / name
    if target.exists() and target.stat().st_size > 100_000:
        return
    req = Request(f'{BASE}/{name}', headers={'User-Agent': 'Prepza-build/1.0'})
    with urlopen(req, timeout=60) as response:
        data = response.read()
    if len(data) <= 100_000:
        raise SystemExit(f'Local PDF engine download is unexpectedly small: {name}')
    OUT.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


for filename in FILES:
    download(filename)

print(f'Local PDF.js runtime ready ({VERSION}); Study PDFs no longer require a CDN at runtime.')
