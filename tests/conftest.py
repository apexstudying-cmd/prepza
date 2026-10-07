"""Shared pytest fixtures for the disposable full local QA suite.

The real-world database fixture is intentionally opt-in. Focused contract tests
import the application but must not inherit PostgreSQL-only reset logic.
"""

import os

if os.environ.get("PREPZA_FULL_QA") == "1":
    pytest_plugins = ("test_local_qa_real_world",)
else:
    pytest_plugins = ()
