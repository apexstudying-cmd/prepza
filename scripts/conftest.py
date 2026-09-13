"""CI-only pytest bootstrap for isolated realtime regression tests."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "realtime-test-secret")
