"""Exercise actual app routes without connecting to or changing customer data."""
import pytest
from fastapi.testclient import TestClient
from ternfold.app import app
from ternfold.db import get_db
from ternfold import auth


@pytest.fixture
def anonymous_client(monkeypatch):
    monkeypatch.setattr(auth, "current_user", lambda request, db: None)
    app.dependency_overrides[get_db] = lambda: None
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("path", ["/", "/cases/example", "/documents/example", "/reports/example/download"])
def test_signed_out_browser_opens_login(anonymous_client, path):
    response = anonymous_client.get(path, headers={"accept": "text/html"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert response.headers["cache-control"] == "no-store"


def test_home_redirect_renders_real_login_page(anonymous_client):
    response = anonymous_client.get("/", headers={"accept": "text/html"})
    assert response.status_code == 200
    assert response.url.path == "/login"
    assert "Open a decision workspace" in response.text
    assert 'name="password"' in response.text


def test_api_and_post_requests_keep_authentication_error(anonymous_client):
    response = anonymous_client.get("/", headers={"accept": "application/json"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Sign in required"}
    response = anonymous_client.post("/logout", data={"csrf": "expired"}, headers={"accept": "text/html"})
    assert response.status_code == 401
    assert "location" not in response.headers
