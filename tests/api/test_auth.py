import pytest
from fastapi.testclient import TestClient

from app.api.deps import FEEDME_API_TOKEN, get_db
from app.main import app


@pytest.fixture
def unauthenticated_client(db_session):
    """A TestClient with the DB overridden but require_auth_token left real -
    for testing the auth mechanism itself, unlike the `client` fixture in
    conftest.py which bypasses auth for every other test's convenience."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_request_without_token_is_rejected(unauthenticated_client):
    response = unauthenticated_client.get("/recipes")

    assert response.status_code == 401


def test_request_with_wrong_token_is_rejected(unauthenticated_client):
    response = unauthenticated_client.get(
        "/recipes", headers={"Authorization": "Bearer wrong-token"}
    )

    assert response.status_code == 401


def test_request_with_correct_token_succeeds(unauthenticated_client):
    response = unauthenticated_client.get(
        "/recipes", headers={"Authorization": f"Bearer {FEEDME_API_TOKEN}"}
    )

    assert response.status_code == 200


def test_health_endpoint_does_not_require_token(unauthenticated_client):
    response = unauthenticated_client.get("/health")

    assert response.status_code == 200
