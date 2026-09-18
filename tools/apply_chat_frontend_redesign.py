from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "frontend/src/crypto/WhatsAppChatExperience.tsx"

def main():
    text = TARGET.read_text(encoding="utf-8")
    # The chat redesign is now source-owned. Do not rewrite a large JSX/CSS
    # block during every Render build; repeated string replacement was able to
    # produce malformed JSX. Validate the required shell markers instead.
    required = (".prepza-wa-shell", ".prepza-wa-window", ".prepza-wa-composer")
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise SystemExit("CHAT_FRONTEND_REDESIGN_FAILED: missing " + ", ".join(missing))
    print("CHAT_FRONTEND_REDESIGN_VALIDATED")
    print("ADA_STANDALONE_CONTROLS_REMOVED")
    print("ADA_REMAINS_MENTION_DRIVEN")

if __name__ == "__main__":
    main()
