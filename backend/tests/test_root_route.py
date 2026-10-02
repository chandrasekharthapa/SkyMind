from fastapi.testclient import TestClient

from backend.main import app


def test_root_explains_itself_instead_of_404():
    r = TestClient(app).get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "SkyMind API" and body["health"] == "/health"
