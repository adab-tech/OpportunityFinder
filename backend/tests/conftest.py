"""Test configuration: isolate every test run in a throwaway SQLite database.

The DATABASE_URL override must happen before any `app.*` import, because
`app.config.Settings` reads the environment at import time. pytest imports
conftest.py before the test modules, so this runs first.
"""

import os
import tempfile
from pathlib import Path

_TEST_DB_DIR = tempfile.mkdtemp(prefix="opportunityfinder-tests-")
_TEST_DB_PATH = Path(_TEST_DB_DIR) / "test_opportunities.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.as_posix()}"
os.environ["ENABLE_SCHEDULER"] = "false"

import pytest  # noqa: E402

from app.database import Base, engine  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
