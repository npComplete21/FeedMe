import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user_id, get_db
from app.main import app


@pytest.fixture
def client(db_session, test_user_id):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = lambda: test_user_id
    yield TestClient(app)
    app.dependency_overrides.clear()
