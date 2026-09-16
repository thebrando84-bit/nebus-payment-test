import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/test")

from app.main import create_app


@pytest.fixture
def api_key() -> str:
    return "test-api-key"


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())
