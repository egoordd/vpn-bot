from services.sub_gateway import happ_redirect_page


def test_happ_redirect_page_embeds_add_deeplink():
    page = happ_redirect_page("https://sub.unlockvpn.org:8444/sub/abc123")
    assert "happ://add/https://sub.unlockvpn.org:8444/sub/abc123" in page
    assert "location.replace" in page
    assert "Открыть в Happ" in page


def test_happ_redirect_page_is_valid_html_document():
    page = happ_redirect_page("https://sub.unlockvpn.org:8444/sub/a-b_c")
    assert page.startswith("<!doctype html>")
    assert "<a href=" in page
    assert 'http-equiv="refresh"' in page
