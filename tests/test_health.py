from fastapi.testclient import TestClient

from app.main import app


def test_health():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_request_id_header():
    response = TestClient(app).get("/health", headers={"X-Request-ID": "abc123"})
    assert response.headers["X-Request-ID"] == "abc123"


def test_chat_page_and_its_scripts_are_served():
    client = TestClient(app)

    page = client.get("/")
    script = client.get("/static/api.js")

    assert "text/html" in page.headers["content-type"]
    assert 'src="/static/main.js"' in page.text
    assert "javascript" in script.headers["content-type"]
    assert script.headers["cache-control"] == "no-cache"
    assert "/chat" in script.text
