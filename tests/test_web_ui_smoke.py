# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false
from fastapi.responses import PlainTextResponse

from api.server import root, web_index


def test_root_redirects_to_web():
    payload = root()
    assert payload == {
        "status": "ok",
        "health": "/health",
        "docs": "/docs",
        "web": "(set MYT_FRONTEND_URL or access via Nginx)",
    }


def test_web_ui_page_is_served():
    response = web_index()
    assert isinstance(response, PlainTextResponse)
    assert response.status_code == 501
    assert response.media_type == "text/plain"
    assert "frontend build" in response.body.decode("utf-8")
