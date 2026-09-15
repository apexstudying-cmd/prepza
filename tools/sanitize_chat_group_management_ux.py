"""Normalize the generated group-member action button after the UI patch."""
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "frontend" / "src" / "crypto" / "WhatsAppChatExperience.tsx"
ANCHOR = '<button type="button" onClick={() => void removeGroupMember(member)}'
END = '>Remove</button>'
GOOD = '<button type="button" onClick={() => void removeGroupMember(member)} disabled={groupMemberBusy} style={{border:0,background:\'transparent\',color:\'#a33a35\',fontSize:10,fontWeight:800,cursor:\'pointer\',padding:\'7px\'}}>Remove</button>'


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    if GOOD in text:
        print("Group member action markup already normalized.")
        return
    start = text.find(ANCHOR)
    if start < 0:
        raise RuntimeError("Could not locate group member action button")
    end_marker = text.find(END, start)
    if end_marker < 0:
        raise RuntimeError("Could not locate end of group member action button")
    end = end_marker + len(END)
    text = text[:start] + GOOD + text[end:]
    TARGET.write_text(text, encoding="utf-8")
    print("Normalized group member action markup.")


if __name__ == "__main__":
    main()
