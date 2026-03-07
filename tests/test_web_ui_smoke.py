from fastapi.testclient import TestClient

from api.server import app


def test_web_ui_page_is_served():
    client = TestClient(app)
    response = client.get("/web")
    assert response.status_code == 200
    assert "WebRPA" in response.text
