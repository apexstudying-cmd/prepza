from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / 'frontend' / 'src' / 'crypto' / 'WhatsAppChatExperience.tsx'

def main():
    text = TARGET.read_text(encoding='utf-8')
    required = [
        'const [showNewChat, setShowNewChat] = useState(false)',
        'const createDirectChat = async (user: GroupPickerUser)',
        'const openNewChat = () =>',
        'Start secure chat',
        'aria-label="New chat"',
    ]
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise RuntimeError('New chat source validation failed: ' + ', '.join(missing))
    print('NEW_DIRECT_CHAT_VALIDATED')

if __name__ == '__main__':
    main()
