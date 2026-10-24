"""Tests verifying FastAPI initialization and health endpoints.
"""

from fastapi.testclient import TestClient
from app.main import app


def test_api_health():
    """Verify FastAPI /health endpoint responds with 200 OK."""
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


def test_api_root():
    """Verify root endpoint returns system metadata and docs link."""
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"
        assert "AffineSurge" in data["service"]
        assert data["api_v1"] == "/api/v1"
