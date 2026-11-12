from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/apply_offline_status_ui.py"
SPEC = importlib.util.spec_from_file_location("apply_offline_status_ui", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_offline_status_banner_transform_survives_chat_realtime_extraction() -> None:
    app = """import { resetChatRealtime } from './crypto/chatRealtime'
import CallExperience from './crypto/CallExperience'
export default function App() {
  return <div style={{ width: '100%', height: '100dvh' }}>
      {/* Content */}
  </div>
}
"""
    transformed = MODULE.transform(app)
    assert "import OfflineStatusBanner from './offline/OfflineStatusBanner'" in transformed
    assert "      <OfflineStatusBanner />\n      {/* Content */}" in transformed


def test_offline_status_banner_transform_is_idempotent() -> None:
    app = """import CallExperience from './crypto/CallExperience'
export default function App() {
  return <div style={{ width: '100%', height: '100dvh' }}>
      {/* Content */}
  </div>
}
"""
    transformed = MODULE.transform(app)
    assert MODULE.transform(transformed) == transformed


def test_offline_status_transform_fails_clearly_without_app_shell_anchor() -> None:
    app = """export default function App() {
  return <div style={{ width: '100%', height: '100dvh' }}>
      {/* Content */}
  </div>
}
"""
    try:
        MODULE.transform(app)
    except SystemExit as error:
        assert "app-shell call overlay import anchor missing" in str(error)
    else:
        raise AssertionError("expected a missing app-shell import anchor to fail")
