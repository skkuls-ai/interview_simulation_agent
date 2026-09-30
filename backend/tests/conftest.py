import os

os.environ.setdefault("FAKE_GRAPH_DELAY_SEC", "0")
os.environ.setdefault("INTERVIEW_GRAPH_MODE", "fake")

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.store import store


@pytest.fixture()
def client():
    store._records.clear()
    return TestClient(app)
