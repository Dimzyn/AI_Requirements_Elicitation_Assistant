from app.services.invite_service import new_token, accept_url_for


def test_new_token_is_unique_and_urlsafe():
    a, b = new_token(), new_token()
    assert a != b
    assert len(a) >= 20
    assert "/" not in a and "+" not in a


def test_accept_url_contains_token():
    url = accept_url_for("abc123", base="http://localhost:5173")
    assert url == "http://localhost:5173/invite/abc123"
