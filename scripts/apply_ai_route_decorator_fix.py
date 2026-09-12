from pathlib import Path
import re

APP = Path("app.py")


def _remove_ai_helper_definitions(source):
    marker = "def _ai_generation_parameters_from_request():"
    blocks = []
    search_from = 0
    while True:
        start = source.find(marker, search_from)
        if start < 0:
            break
        block_end = re.search(r"(?m)^@|^def ", source[start + len(marker):])
        if block_end:
            end = start + len(marker) + block_end.start()
        else:
            end = len(source)
        blocks.append((start, end, source[start:end]))
        search_from = end

    if not blocks:
        return source, None

    helper_block = blocks[0][2]
    for start, end, _ in reversed(blocks):
        source = source[:start] + source[end:]
    return source, helper_block


def _summary_route_pos(source):
    pattern = re.compile(
        r'@app\.route\(\s*["\']/documents/<int:document_id>/summarize["\']\s*'
        r'(?:,\s*methods\s*=\s*\[[^\]]+\])?\s*\)'
    )
    match = pattern.search(source)
    return match.start() if match else -1


def main():
    s = APP.read_text()
    function_marker = "def summarize_document(document_id):"
    s, helper_block = _remove_ai_helper_definitions(s)
    if helper_block is None:
        print("AI generation parameter helper not present")
        return

    route_pos = _summary_route_pos(s)
    if route_pos < 0:
        raise SystemExit("summary route decorator not found")
    function_pos = s.find(function_marker, route_pos)
    if function_pos < 0:
        raise SystemExit("summary function not found")

    s = s[:route_pos] + helper_block + "\n\n" + s[route_pos:]
    APP.write_text(s)
    print("summary route decorators and AI helper normalized")


if __name__ == "__main__":
    main()
