import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.auth import create_access_token
from app.api.auth_routes import FEEDME_REGISTRATION_CODE
from app.api.deps import get_db
from app.main import app
from app.models import User


@pytest.fixture
def unauthenticated_client(db_session):
    """A TestClient with the DB overridden but get_current_user_id left real -
    for testing the auth mechanism itself, unlike the `client` fixture in
    conftest.py which bypasses auth for every other test's convenience."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- protected routes require a valid token ---


def test_request_without_token_is_rejected(unauthenticated_client):
    response = unauthenticated_client.get("/recipes")

    assert response.status_code == 401


def test_request_with_malformed_token_is_rejected(unauthenticated_client):
    response = unauthenticated_client.get(
        "/recipes", headers={"Authorization": "Bearer not-a-real-token"}
    )

    assert response.status_code == 401


def test_request_with_valid_token_succeeds(unauthenticated_client, test_user_id):
    token = create_access_token(test_user_id)

    response = unauthenticated_client.get("/recipes", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200


def test_health_endpoint_does_not_require_token(unauthenticated_client):
    response = unauthenticated_client.get("/health")

    assert response.status_code == 200


# --- registration ---


def test_register_creates_user_and_returns_token(unauthenticated_client, db_session):
    response = unauthenticated_client.post(
        "/auth/register",
        json={
            "email": "new-user@example.com",
            "password": "correct horse battery staple",
            "registration_code": FEEDME_REGISTRATION_CODE,
        },
    )

    assert response.status_code == 201
    assert "access_token" in response.json()

    user = db_session.scalars(select(User).where(User.email == "new-user@example.com")).first()
    assert user is not None
    assert user.password_hash != "correct horse battery staple"  # never stored plaintext


def test_register_rejects_wrong_registration_code(unauthenticated_client):
    response = unauthenticated_client.post(
        "/auth/register",
        json={
            "email": "new-user@example.com",
            "password": "hunter2",
            "registration_code": "definitely-wrong",
        },
    )

    assert response.status_code == 403


def test_register_rejects_duplicate_email(unauthenticated_client, db_session):
    from tests.conftest import create_test_user

    create_test_user(db_session, email="taken@example.com")

    response = unauthenticated_client.post(
        "/auth/register",
        json={
            "email": "taken@example.com",
            "password": "hunter2",
            "registration_code": FEEDME_REGISTRATION_CODE,
        },
    )

    assert response.status_code == 409


# --- login ---


def test_login_with_correct_password_succeeds(unauthenticated_client, db_session):
    unauthenticated_client.post(
        "/auth/register",
        json={
            "email": "user@example.com",
            "password": "hunter2",
            "registration_code": FEEDME_REGISTRATION_CODE,
        },
    )

    response = unauthenticated_client.post(
        "/auth/login", json={"email": "user@example.com", "password": "hunter2"}
    )

    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_with_wrong_password_is_rejected(unauthenticated_client, db_session):
    unauthenticated_client.post(
        "/auth/register",
        json={
            "email": "user@example.com",
            "password": "hunter2",
            "registration_code": FEEDME_REGISTRATION_CODE,
        },
    )

    response = unauthenticated_client.post(
        "/auth/login", json={"email": "user@example.com", "password": "wrong-password"}
    )

    assert response.status_code == 401


def test_login_with_unknown_email_is_rejected(unauthenticated_client):
    response = unauthenticated_client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "anything"}
    )

    assert response.status_code == 401


# --- data isolation between users - the actual point of this whole feature ---


def test_recipes_are_isolated_between_users(unauthenticated_client, db_session):
    alice_token = unauthenticated_client.post(
        "/auth/register",
        json={
            "email": "alice@example.com",
            "password": "alice-password",
            "registration_code": FEEDME_REGISTRATION_CODE,
        },
    ).json()["access_token"]
    bob_token = unauthenticated_client.post(
        "/auth/register",
        json={
            "email": "bob@example.com",
            "password": "bob-password",
            "registration_code": FEEDME_REGISTRATION_CODE,
        },
    ).json()["access_token"]

    alice_headers = {"Authorization": f"Bearer {alice_token}"}
    bob_headers = {"Authorization": f"Bearer {bob_token}"}

    from app.models import Recipe

    alice_id = db_session.scalars(
        select(User.id).where(User.email == "alice@example.com")
    ).first()
    db_session.add(
        Recipe(
            user_id=alice_id,
            source_url="https://youtube.com/watch?v=abc",
            source_platform="youtube",
            title="Alice's Secret Recipe",
            steps=["step"],
        )
    )
    db_session.commit()

    alice_recipes = unauthenticated_client.get("/recipes", headers=alice_headers).json()
    bob_recipes = unauthenticated_client.get("/recipes", headers=bob_headers).json()

    assert [r["title"] for r in alice_recipes] == ["Alice's Secret Recipe"]
    assert bob_recipes == []
