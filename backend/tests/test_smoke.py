"""Smoke tests for API boot and core routes (no external network)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["service"] == "OpportunityFinder"


def test_api_root():
    response = client.get("/api")
    assert response.status_code == 200
    assert response.json()["service"] == "OpportunityFinder API"
