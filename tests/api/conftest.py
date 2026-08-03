import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db, require_auth_token
from app.main import app


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_auth_token] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()
