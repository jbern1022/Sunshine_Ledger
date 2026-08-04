"""Shared pytest fixtures.

Tests run against a real ephemeral Postgres/PostGIS instance (see
docker-compose.test.yml + scripts/run-tests.sh) rather than SQLite,
since several models use PostGIS geometry columns. Env vars below are
only fallback defaults for ad-hoc local runs -- the test compose file
sets them explicitly.
"""

import os
from datetime import date

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://sunshine:sunshine_test_only@localhost:5434/sunshine_ledger_test",
)
os.environ.setdefault("ADMIN_USERNAME", "testadmin")
os.environ.setdefault("ADMIN_PASSWORD", "testpass")
os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://testserver")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Bill, Entity  # noqa: E402


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(settings.database_url, future=True)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db_session(engine):
    """One test, one transaction. Uses a SAVEPOINT-backed session (SQLAlchemy
    2.0's `join_transaction_mode="create_savepoint"`) so that code under test
    calling `session.commit()` -- as the real API routes do -- doesn't end
    the outer transaction we roll back at teardown."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, future=True, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db_session):
    def _get_db_override():
        yield db_session

    app.dependency_overrides[get_db] = _get_db_override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def bill_factory(db_session):
    """Insert a minimal bill Entity + Bill row, return the Entity."""

    def _factory(*, bill_number: str = "HB 123", name: str = "Test Bill", status: str = "Introduced") -> Entity:
        entity = Entity(
            entity_type="bill",
            name=name,
            jurisdiction_level="state",
            jurisdiction_name="FL",
            external_ids={},
            attributes={},
        )
        db_session.add(entity)
        db_session.flush()

        bill = Bill(
            entity_id=entity.id,
            bill_number=bill_number,
            session="2026 Regular Session",
            chamber="House",
            status=status,
            introduced_date=date(2026, 1, 1),
            last_action_date=date(2026, 2, 1),
            full_text_url="https://example.com/bill",
            source_system="legiscan",
            geo_scope_type="statewide",
            geo_scope_names=["FL"],
        )
        db_session.add(bill)
        db_session.commit()
        return entity

    return _factory
