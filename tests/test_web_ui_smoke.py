# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false
from starlette.testclient import TestClient

from api.server import app


def test_root_redirects_to_web():
    client = TestClient(app)
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "health": "/health",
        "docs": "/docs",
        "web": "(set MYT_FRONTEND_URL or access via Nginx)",
    }


def test_web_ui_page_is_served():
    client = TestClient(app)
    response = client.get("/web")
    assert response.status_code == 501
    assert response.headers["content-type"].startswith("text/plain")
    assert "frontend build" in response.text
