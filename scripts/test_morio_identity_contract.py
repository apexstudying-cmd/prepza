"""Regression checks for Prepza's student-facing Morio identity.

These checks protect the identity/prompt/UI contract without changing stable
internal route names or API payload contracts.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_scoped_tutor_prompt_uses_morio_and_preserves_context_boundaries():
    text = source("e2ee_ada_routes.py")
    assert "You are Morio, Prepza's AI study tutor." in text
    assert "do not identify yourself as Ada or ChatGPT" in text
    assert "explicitly selected study context" in text
    assert "explicit_user_context" in text
    assert "MAX_SELECTED_TEXT = 20_000" in text
    assert "MAX_PAGE_SPAN = 50" in text


def test_main_document_tutor_prompt_uses_morio():
    text = source("ai_service.py")
    start = text.index("def _build_tutor_system_prompt")
    end = text.index("def _format_mastery_context", start)
    prompt = text[start:end]
    assert "You are Morio, Prepza's AI tutor." in prompt
    assert "You are Ada" not in prompt


def test_group_mention_and_visible_copy_use_morio():
    text = source("frontend/src/crypto/inChatAdaEnhancer.tsx")
    assert "MORIO_MENTION_RE = /(^|\\s)@morio\\b/i" in text
    assert "Morio · Shared study" in text
    assert "Ask Morio" in text
    assert "@Ada" not in text
    assert "@ada\\b" not in text


def test_home_study_screens_and_composer_use_morio():
    app = source("frontend/src/App.tsx")
    chat = source("frontend/src/crypto/WhatsAppChatExperience.tsx")
    assert "Study with Morio" in app
    assert "Use Morio while this document is your study context." in app
    assert ">Morio</div>" in app
    assert "}>@Morio</button>" in chat
    assert "}>@Ada</button>" not in chat


def test_direct_tutor_uses_morio_and_keeps_internal_event_compatible():
    text = source("frontend/src/crypto/directInChatAdaEnhancer.tsx")
    assert "Study with Morio" in text
    assert "Ask Morio" in text
    # The event name is an internal compatibility contract; user-facing copy is Morio.
    assert "prepza-open-ada" in text


def test_home_and_prebuild_patch_keep_morio_label():
    text = source("scripts/apply_shop_frontend.py")
    assert "label: 'Morio', action: () => setScreen('ai-tutor')" in text
    patch = source("tools/fix_chat_ada_mention_trigger.py")
    assert "@morio" in patch


def test_home_quick_actions_are_the_approved_five_in_order():
    app = source("frontend/src/App.tsx")
    start = app.index("function HomeScreen(")
    end = app.find("\nfunction ", start + 1)
    home = app[start:end if end >= 0 else None]
    marker = home.index("AI Study Tools")
    actions_start = home.index("{[", marker)
    actions_end = home.index("].map((t, i) => (", actions_start)
    actions = home[actions_start:actions_end]

    expected = [
        "label: 'Upload'",
        "label: 'My Study'",
        "label: 'Library'",
        "label: 'Morio'",
        "label: 'Shop'",
    ]
    positions = [actions.index(label) for label in expected]
    assert positions == sorted(positions)
    assert "label: 'Podcasts'" not in actions
    assert "label: 'Shop', action: () => setScreen('shop')" in actions


def test_splash_screen_uses_the_canonical_192px_icon():
    app = source("frontend/src/App.tsx")
    splash = app.split("function SplashScreen", 1)[1].split("// ─── LOGIN", 1)[0]
    assert '<img src="/icon-192.png" alt="Prepza" width={192} height={192}' in splash
    assert "src={logoImg}" not in splash
    # All React app-shell brand marks use the canonical public PNG, not the SVG import.
    assert 'src={logoImg}' not in app
    assert app.count('src="/icon-192.png"') >= 9

    manifest = source("frontend/public/manifest.json")
    assert '"src": "/icon-192.png"' in manifest


if __name__ == "__main__":
    checks = [
        test_scoped_tutor_prompt_uses_morio_and_preserves_context_boundaries,
        test_main_document_tutor_prompt_uses_morio,
        test_group_mention_and_visible_copy_use_morio,
        test_home_study_screens_and_composer_use_morio,
        test_direct_tutor_uses_morio_and_keeps_internal_event_compatible,
        test_home_and_prebuild_patch_keep_morio_label,
        test_home_quick_actions_are_the_approved_five_in_order,
        test_splash_screen_uses_the_canonical_192px_icon,
    ]
    for check in checks:
        check()
        print(f"PASS {check.__name__}")
    print(f"{len(checks)} Morio identity contract checks passed.")
