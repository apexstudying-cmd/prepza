from pathlib import Path

APP = Path("app.py")


def _remove_ai_helper_definitions(source):
    marker = "def _ai_generation_parameters_from_request():"
    blocks = []
    search_from = 0
    while True:
        start = source.find(marker, search_from)
        if start < 0:
            break
        block_end = source.find("\n\ndef ", start)
        if block_end < 0:
            raise SystemExit("could not determine AI helper boundary")
        blocks.append((start, block_end + 2, source[start:block_end + 2]))
        search_from = block_end + 2

    if not blocks:
        return source, None

    # The helper itself is short and has no decorators/imports that belong
    # to its surrounding code. Remove every stale copy, then reinstall one
    # canonical copy immediately before the summary route decorator block.
    helper_block = blocks[0][2]
    for start, end, _ in reversed(blocks):
        source = source[:start] + source[end:]
    return source, helper_block


def main():
    s = APP.read_text()
    route_marker = '@app.route("/documents/<int:document_id>/summarize", methods=["POST"])'
    function_marker = "def summarize_document(document_id):"

    s, helper_block = _remove_ai_helper_definitions(s)
    if helper_block is None:
        print("AI generation parameter helper not present")
        return

    route_pos = s.find(route_marker)
    if route_pos < 0:
        raise SystemExit("summary route decorator not found")
    function_pos = s.find(function_marker, route_pos)
    if function_pos < 0:
        raise SystemExit("summary function not found")

    # Flask decorators must remain directly attached to the route function.
    s = s[:route_pos] + helper_block + "\n\n" + s[route_pos:]
    APP.write_text(s)
    print("summary route decorators and AI helper normalized")


if __name__ == "__main__":
    main()
