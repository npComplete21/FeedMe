import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://feedme:feedme@localhost:5432/feedme"
)


class Base(DeclarativeBase):
    pass


# pool_pre_ping issues a cheap SELECT 1 before handing out a pooled connection,
# transparently discarding ones the server has already closed. Without it, the
# first request after any Postgres restart fails with
# `psycopg.errors.AdminShutdown: terminating connection due to administrator
# command` - the pool doesn't notice the connection is dead until it tries to
# use it. That matters here because the db Deployment uses strategy: Recreate
# (ADR-0018), so every database rollout kills every open connection.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
