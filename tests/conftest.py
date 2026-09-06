import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import db  # noqa: E402

# Point the database at a scratch file before app.py imports and initialises it,
# so tests never touch data/tra.db.
_scratch = tempfile.TemporaryDirectory()
db.DB_PATH = Path(_scratch.name) / "test.db"

import app as app_module  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    """Give every test an empty database."""
    for path in db.DB_PATH.parent.glob("test.db*"):
        path.unlink()
    db.init_db()
    yield


@pytest.fixture
def conn():
    connection = db.get_db()
    yield connection
    connection.close()


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as test_client:
        with test_client.session_transaction() as sess:
            sess["user"] = "tester"
            sess["user_role"] = "admin"
        yield test_client


@pytest.fixture
def sample_csv():
    """The real Metro Bank export, if it is present in the working tree."""
    path = ROOT / "metro_export.csv"
    if not path.exists():
        pytest.skip("metro_export.csv not present")
    return path.read_text(encoding="utf-8-sig")
