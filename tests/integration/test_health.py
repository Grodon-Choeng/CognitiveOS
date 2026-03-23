from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_health_endpoint(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "CognitiveOS"}
