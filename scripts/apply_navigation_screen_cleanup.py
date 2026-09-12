from pathlib import Path

APP = Path("frontend/src/App.tsx")


def main():
    text = APP.read_text()
    old = "'library','mind-map'].includes(active)"
    new = "'library','mind-map','document-reader'].includes(active)"
    if new in text:
        print("document reader navigation state already normalized")
        return
    if old not in text:
        raise SystemExit("Home navigation screen list anchor not found")
    APP.write_text(text.replace(old, new, 1))
    print("document reader added to Home navigation state")


if __name__ == "__main__":
    main()
