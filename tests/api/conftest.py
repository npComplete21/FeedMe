import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
