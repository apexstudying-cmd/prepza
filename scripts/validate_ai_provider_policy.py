"""Static regression checks for the locked OpenAI-only AI provider policy."""
from pathlib import Path

SOURCE = Path("ai_service.py").read_text(encoding="utf-8")
ENV = Path(".env.example.vps").read_text(encoding="utf-8")

if "GEMINI_API_KEY" in SOURCE or "gemini:" in SOURCE.lower():
    raise SystemExit("AI provider policy regression: Gemini provider code remains")

if 'if not model.startswith("openai:"):' not in SOURCE:
    raise SystemExit("AI provider policy regression: configured-model provider guard is missing")

if "OPENAI_API_KEY" not in ENV:
    raise SystemExit("AI provider policy regression: OPENAI_API_KEY is missing from the VPS environment example")

if "GEMINI_API_KEY" in ENV:
    raise SystemExit("AI provider policy regression: GEMINI_API_KEY must not be configured")

print("OpenAI-only AI provider policy passed.")
