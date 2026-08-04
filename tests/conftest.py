import os

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401 - ensures models are registered on Base.metadata
from app.api.auth import hash_password
from app.db import Base
from app.models import User

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://feedme:feedme@localhost:5432/feedme_test"
)


@pytest.fixture(scope="session")
def engine():
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(engine):
    """Isolate each test in a SAVEPOINT so a test that triggers an IntegrityError
    (e.g. asserting a constraint is enforced) doesn't invalidate the outer
    transaction used to roll back all changes after the test."""
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = sessionmaker(bind=connection)()

    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(session, transaction):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    yield session

    session.close()
    outer_transaction.rollback()
    connection.close()


def create_test_user(db_session, email: str = "test@feedme.local") -> int:
    """Plain helper (not a fixture) for tests that need more than one user, or
    that don't use the `test_user_id` fixture below - e.g. a second user to
    verify data isolation between accounts."""
    user = User(email=email, password_hash=hash_password("test-password"))
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user.id


@pytest.fixture
def test_user_id(db_session) -> int:
    """A real User row for tests that need a valid user_id - replaces the old
    get_current_user_id(db_session) get-or-create-the-one-hardcoded-user
    pattern from the single-shared-token era (see ADR-0015)."""
    return create_test_user(db_session)
