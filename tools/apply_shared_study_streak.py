from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "frontend" / "src" / "crypto" / "WhatsAppChatExperience.tsx"


def main():
    source = TARGET.read_text(encoding="utf-8")
    import_line = "import SharedStudyStreak from './SharedStudyStreak'"

    if import_line not in source:
        anchor = "import { provisionInitialGroupKey } from './groupProvisioning'"
        if source.count(anchor) != 1:
            raise SystemExit("Shared streak patch: chat import anchor missing or ambiguous")
        source = source.replace(anchor, anchor + "\n" + import_line, 1)

    marker = "<SharedStudyStreak conversationId={detail.id} isGroup={detail.is_group} csrfToken={csrfToken} userId={meId} />"
    if marker not in source:
        header_start = '<header className="prepza-wa-head">'
        header_end = "</header>"
        start = source.find(header_start)
        end = source.find(header_end, start + len(header_start)) if start >= 0 else -1
        if start < 0 or end < 0:
            raise SystemExit("Shared streak patch: chat header anchors missing")
        source = source[:end] + "{view === 'detail' && detail && " + marker + "}" + source[end:]

    TARGET.write_text(source, encoding="utf-8")


if __name__ == "__main__":
    main()
