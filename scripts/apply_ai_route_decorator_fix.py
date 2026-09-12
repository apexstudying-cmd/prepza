from pathlib import Path

APP = Path("app.py")


def main():
    s = APP.read_text()
    helper_marker = "def _ai_generation_parameters_from_request():"
    route_marker = '@app.route("/documents/<int:document_id>/summarize", methods=["POST"])'
    function_marker = "def summarize_document(document_id):"

    helper_start = s.find(helper_marker)
    if helper_start < 0:
        print("AI generation parameter helper not present")
        return

    route_pos = s.find(route_marker)
    if route_pos < 0:
        raise SystemExit("summary route decorator not found")

    function_pos = s.find(function_marker, route_pos)
    if function_pos < 0:
        raise SystemExit("summary function not found")

    # Extract the helper body from its current location, regardless of
    # whether an earlier patch left it between Flask decorators.
    helper_end = s.find("\n\ndef ", helper_start)
    if helper_end < 0:
        raise SystemExit("could not determine AI helper boundary")
    helper_block = s[helper_start:helper_end + 2]

    # Remove the helper from wherever it currently lives.
    s = s[:helper_start] + s[helper_end + 2:]

    # Re-locate the summary decorator and function after removal.
    route_pos = s.find(route_marker)
    function_pos = s.find(function_marker, route_pos)
    if route_pos < 0 or function_pos < 0:
        raise SystemExit("summary route/function could not be relocated")

    # Flask decorators must remain directly attached to the route function.
    # Insert the helper immediately before the decorator block.
    s = s[:route_pos] + helper_block + "\n\n" + s[route_pos:]
    APP.write_text(s)
    print("summary route decorators restored")


if __name__ == "__main__":
    main()
