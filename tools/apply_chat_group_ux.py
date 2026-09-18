from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / 'frontend' / 'src' / 'crypto' / 'WhatsAppChatExperience.tsx'

def main():
    text = TARGET.read_text(encoding='utf-8')
    required = [
        'const [showGroupCreator, setShowGroupCreator] = useState(false)',
        'const createChatGroup = async () =>',
        'aria-label="Create group chat"',
        'aria-label="New group"',
        'New study group',
    ]
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise RuntimeError('Chat group UX validation failed: ' + ', '.join(missing))
    print('CHAT_GROUP_UX_VALIDATED')

if __name__ == '__main__':
    main()
