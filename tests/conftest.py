import os
from pathlib import Path
from uuid import uuid4

TEST_ROOT = Path("test-results") / str(uuid4())
TEST_ROOT.mkdir(parents=True)
os.environ["GALSTUDY_TEST_ROOT"] = str(TEST_ROOT)
test_database = os.getenv("GALSTUDY_TEST_DATABASE_URL")
if test_database:
    from sqlalchemy.engine import make_url

    target = make_url(test_database)
    if target.get_backend_name() != "postgresql" or not (
        target.database or ""
    ).startswith("galstudy_test_"):
        raise RuntimeError(
            "PostgreSQL tests require a separate galstudy_test_* database"
        )
    os.environ["DATABASE_URL"] = test_database
else:
    os.environ["DATABASE_URL"] = (
        "sqlite:///" + (TEST_ROOT / "test.db").resolve().as_posix()
    )
os.environ["LLM_MODE"] = "demo"
os.environ["LLM_CHAT_MODE"] = "demo"
os.environ["IMAGE_GENERATOR"] = "mock"
os.environ["PAYMENT_PROVIDER"] = "mock"
os.environ["OCR_MODE"] = "disabled"

import pytest


@pytest.fixture(autouse=True)
def clear_auth_attempts():
    from backend.security import auth_attempts

    with auth_attempts.lock:
        auth_attempts.addresses.clear()
        auth_attempts.total.clear()
