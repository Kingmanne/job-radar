import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture
def load():
    return lambda name: json.loads((FIXTURES / name).read_text())


@pytest.fixture(autouse=True)
def no_aws(monkeypatch):
    """Tests never touch SSM or real keys."""
    monkeypatch.setenv("JOBRADAR_LOCAL_ONLY", "1")
    for var in ("REED_API_KEY", "ADZUNA_APP_ID", "ADZUNA_APP_KEY", "JOBRADAR_SEARCHES"):
        monkeypatch.delenv(var, raising=False)
