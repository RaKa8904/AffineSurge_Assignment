"""Pytest fixtures for database and API testing.
"""

from pathlib import Path
import pytest
import app.services.pdf_runtime  # noqa: F401
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.services.ingestion import ingest_document_version
from app import models  # noqa: F401


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enforce SQLite foreign key constraints in test databases."""
    if hasattr(dbapi_connection, "cursor"):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON;")
        finally:
            cursor.close()


from sqlalchemy.pool import StaticPool


@pytest.fixture(scope="function")
def db_session():
    """Provides a fresh, isolated in-memory SQLite database session per test function."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    """FastAPI TestClient wired to the isolated test database session."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def seeded_db(db_session):
    """Seeds both CT-200 v1.0 and v2.0 manuals into the test database."""
    v1_path = Path("ct200_manual.pdf")
    v2_path = Path("ct200_manual_v2.pdf")
    assert v1_path.exists(), f"v1 PDF missing: {v1_path}"
    assert v2_path.exists(), f"v2 PDF missing: {v2_path}"

    v1_version = ingest_document_version(
        db=db_session,
        pdf_path=v1_path,
        document_name="CT-200",
        version_tag="v1.0"
    )
    v2_version = ingest_document_version(
        db=db_session,
        pdf_path=v2_path,
        document_name="CT-200",
        version_tag="v2.0",
        prior_version_tag="v1.0"
    )
    return {"v1": v1_version, "v2": v2_version, "session": db_session}
