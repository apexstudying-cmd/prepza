from pathlib import Path

APP = Path("app.py")


def main():
    s = APP.read_text()
    helper_start = s.find("def _ai_generation_parameters_from_request():")
    if helper_start < 0:
        print("AI generation parameter helper not present")
        return

    route_marker = '@app.route("/documents/<int:document_id>/summarize", methods=["POST"])'
    route_pos = s.find(route_marker)
    if route_pos < 0:
        raise SystemExit("summary route decorator not found")

    # Correct state: the helper is above the route decorator block.
    if helper_start < route_pos:
        print("AI generation parameter helper already correctly placed")
        return

    helper_end = s.find("\n\ndef summarize_document(document_id):", helper_start)
    if helper_end < 0:
        raise SystemExit("summary function not found after AI parameter helper")

    helper_block = s[helper_start:helper_end + 2]

    # The helper was accidentally inserted between the summary route's
    # decorators and its function definition. Move it above the decorator
    # block so Flask registers summarize_document itself.
    s = s[:helper_start] + s[helper_end + 2:]
    route_pos = s.find(route_marker)
    s = s[:route_pos] + helper_block + "\n\n" + s[route_pos:]
    APP.write_text(s)
    print("summary route decorators restored")


if __name__ == "__main__":
    main()
