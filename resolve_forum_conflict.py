#!/usr/bin/env python3
"""
Resolves the two git merge-conflict blocks in frontend/src/App.tsx left
over from `git stash pop` (activeForumPostId vs activeDocumentId lifted
state, and the adjacent 'summary'/'forum'/'comments' switch cases).

Run from the repo root:
    cd ~/Desktop/prepza
    python3 resolve_forum_conflict.py

Safe to re-run: if conflict markers are already gone and the resolved
text is present, it exits cleanly instead of erroring.
"""
import sys
from pathlib import Path

TARGET = Path.cwd() / "frontend" / "src" / "App.tsx"
BACKEND_MARKER = Path.cwd() / "app.py"

CONFLICT_1 = """<<<<<<< Updated upstream
  // Which ForumPost is open in CommentsScreen. Screens communicate purely
  // via the Screen string (no route params), so this - like other
  // "currently open X" ids - has to be lifted here rather than living
  // inside ForumScreen/CommentsScreen, which unmount on navigation.
  const [activeForumPostId, setActiveForumPostId] = useState<number | null>(null)
=======
  const [activeDocumentId, setActiveDocumentId] = useState<number | null>(null)
>>>>>>> Stashed changes"""

RESOLVED_1 = """  // Which ForumPost is open in CommentsScreen, and which Document is open
  // in SummaryScreen. Screens communicate purely via the Screen string (no
  // route params), so these - like other "currently open X" ids - have to
  // be lifted here rather than living inside the screens themselves, which
  // unmount on navigation.
  const [activeForumPostId, setActiveForumPostId] = useState<number | null>(null)
  const [activeDocumentId, setActiveDocumentId] = useState<number | null>(null)"""

CONFLICT_2 = """<<<<<<< Updated upstream
      case 'summary':           return <SummaryScreen setScreen={setScreen} />
      case 'forum':             return <ForumScreen setScreen={setScreen} setActiveForumPostId={setActiveForumPostId} />
      case 'comments':          return <CommentsScreen setScreen={setScreen} postId={activeForumPostId} />
=======
      case 'summary':           return <SummaryScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />
      case 'forum':             return <ForumScreen setScreen={setScreen} />
      case 'comments':          return <CommentsScreen setScreen={setScreen} />
>>>>>>> Stashed changes"""

RESOLVED_2 = """      case 'summary':           return <SummaryScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />
      case 'forum':             return <ForumScreen setScreen={setScreen} setActiveForumPostId={setActiveForumPostId} />
      case 'comments':          return <CommentsScreen setScreen={setScreen} postId={activeForumPostId} />"""


def fail(msg):
    print(f"ERROR: {msg}")
    sys.exit(1)


def main():
    if not BACKEND_MARKER.exists():
        fail("app.py not found here - run this from ~/Desktop/prepza (repo root).")
    if not TARGET.exists():
        fail(f"{TARGET} not found.")

    content = TARGET.read_text(encoding="utf-8")

    already_resolved = RESOLVED_1 in content and RESOLVED_2 in content
    has_markers = "<<<<<<<" in content or "=======" in content or ">>>>>>>" in content

    if already_resolved and not has_markers:
        print("Already resolved - no conflict markers found, resolved text present. Nothing to do.")
        sys.exit(0)

    if CONFLICT_1 not in content:
        fail("Conflict block 1 not found verbatim - the file may have changed since this "
             "script was written, or it's already been partially resolved by hand. "
             "Aborting without touching anything.")
    if CONFLICT_2 not in content:
        fail("Conflict block 2 not found verbatim - aborting without touching anything.")

    content = content.replace(CONFLICT_1, RESOLVED_1, 1)
    content = content.replace(CONFLICT_2, RESOLVED_2, 1)

    if "<<<<<<<" in content or "=======" in content or ">>>>>>>" in content:
        fail("Unexpected leftover conflict markers after replacement - aborting without writing.")

    TARGET.write_text(content, encoding="utf-8")
    print("Resolved both conflict blocks in frontend/src/App.tsx")
    print("Next: cd frontend && npx tsc --noEmit   (sanity check)")
    print("Then: git add frontend/src/App.tsx && git commit -m \"Merge: resolve activeForumPostId/activeDocumentId conflict\"")


if __name__ == "__main__":
    main()
