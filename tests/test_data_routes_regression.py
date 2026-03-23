from api.server import app
from core.account_service import get_accounts_raw_text
from core.data_text_service import get_location_text, get_website_text


def test_data_routes_and_removed_migrate_route():
    assert isinstance(get_accounts_raw_text(), str)
    assert isinstance(get_location_text(), str)
    assert isinstance(get_website_text(), str)

    assert "/api/data/migrate" not in {route.path for route in app.routes}
