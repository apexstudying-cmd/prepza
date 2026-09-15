from pathlib import Path
TARGET = Path(__file__).resolve().parents[1] / 'frontend' / 'src' / 'crypto' / 'WhatsAppChatExperience.tsx'
text = TARGET.read_text(encoding='utf-8').splitlines()
for number in (315, 316, 317, 318, 319):
    if number <= len(text):
        print(f'CHAT_GROUP_DEBUG_LINE_{number}={text[number-1]}')
