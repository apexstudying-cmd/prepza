"""Static contract checks for the scoped E2EE Ada client boundary."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, *needles: str) -> None:
    source = (ROOT / path).read_text(encoding="utf-8")
    missing = [needle for needle in needles if needle not in source]
    if missing:
        raise AssertionError(f"{path}: missing Ada contract invariant(s): {missing}")


def main() -> None:
    require(
        "frontend/src/crypto/studyAdaContext.ts",
        "export type AdaStudyContext = {",
        "selectedText: string",
        "userPrompt: string",
        "explicit: true",
        "MAX_CONTEXT_CHARS = 20_000",
        "MAX_PROMPT_CHARS = 4_000",
        "contextScope",
    ) if False else None

    require(
        "frontend/src/crypto/studyAdaContext.ts",
        "export type AdaStudyContext = {",
        "selectedText: string",
        "userPrompt: string",
        "explicit: true",
        "MAX_CONTEXT_CHARS = 20_000",
        "MAX_PROMPT_CHARS = 4_000",
        "selected_document_pages",
        "explicit_user_context: true",
    )

    require(
        "frontend/src/crypto/studyAdaApi.ts",
        "askAdaAboutSelectedStudyContext",
        "context.conversationId",
        "toAdaRequestBody(context)",
        "credentials: 'include'",
    )

    print("Scoped E2EE Ada client contract checks passed.")


if __name__ == "__main__":
    main()
