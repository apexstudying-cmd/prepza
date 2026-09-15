"""Correct the compact inline style emitted by the group-management build patch."""
from pathlib import Path
import re

TARGET = Path(__file__).resolve().parents[1] / "frontend" / "src" / "crypto" / "WhatsAppChatExperience.tsx"
PATTERN = re.compile(r"color:'#a33a35[^}]*?padding:'7px'")
GOOD = "color:'#a33a35',fontSize:10,fontWeight:800,cursor:'pointer',padding:'7px'"


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    if GOOD in text:
        print("Group member action button style already correct.")
        return
    text, count = PATTERN.subn(GOOD, text, count=1)
    if count != 1:
        raise RuntimeError("Could not locate the malformed group member action button style")
    TARGET.write_text(text, encoding="utf-8")
    print("Fixed group member action button style.")


if __name__ == "__main__":
    main()
