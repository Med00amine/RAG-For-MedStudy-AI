from fastapi.testclient import TestClient

from app.main import app


def test_health():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_request_id_header():
    response = TestClient(app).get("/health", headers={"X-Request-ID": "abc123"})
    assert response.headers["X-Request-ID"] == "abc123"


def test_chat_page_is_served():
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "/chat" in response.text
