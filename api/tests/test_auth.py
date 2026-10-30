"""Authentication tests: register, login, /me, protected endpoints, WebSocket auth."""

import jwt
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.config import settings
from app.main import app
from app.security import create_access_token
from tests.conftest import TEST_PASSWORD


async def _login(client, email: str, password: str):
    # OAuth2 password flow sends form data, not JSON
    return await client.post("/api/auth/login", data={"username": email, "password": password})


async def test_login_returns_token_and_user(anon_client, auth):
    resp = await _login(anon_client, "alice@test.dev", TEST_PASSWORD)
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "alice@test.dev"
    assert body["user"]["display_name"] == "Alice"
    assert "password" not in str(body)  # never leak the hash


async def test_login_email_is_case_insensitive(anon_client, auth):
    resp = await _login(anon_client, "  ALICE@Test.dev ", TEST_PASSWORD)
    assert resp.status_code == 200


async def test_wrong_password_and_unknown_user_get_the_same_error(anon_client, auth):
    wrong_password = await _login(anon_client, "alice@test.dev", "nope-nope-nope")
    unknown_user = await _login(anon_client, "nobody@test.dev", TEST_PASSWORD)
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()


async def test_register_rejects_duplicate_email(anon_client, auth):
    resp = await anon_client.post(
        "/api/auth/register",
        json={"email": "Alice@test.dev", "display_name": "Alice 2", "password": TEST_PASSWORD},
    )
    assert resp.status_code == 409


async def test_register_rejects_short_password(anon_client):
    resp = await anon_client.post(
        "/api/auth/register",
        json={"email": "dan@test.dev", "display_name": "Dan", "password": "short"},
    )
    assert resp.status_code == 422


async def test_me_returns_current_user(client):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == "alice@test.dev"


async def test_study_endpoints_require_authentication(anon_client):
    endpoints = [
        ("GET", "/api/studies"),
        ("POST", "/api/studies"),
        ("GET", "/api/studies/1"),
        ("PATCH", "/api/studies/1"),
        ("GET", "/api/studies/1/audit"),
        ("DELETE", "/api/arms/1?version=1"),
    ]
    for method, url in endpoints:
        resp = await anon_client.request(method, url, json={})
        assert resp.status_code == 401, f"{method} {url} should need auth"


async def test_expired_token_is_rejected(anon_client, auth):
    expired = jwt.encode(
        {"sub": "1", "exp": 1}, settings.jwt_secret, algorithm=settings.jwt_algorithm
    )
    resp = await anon_client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert resp.status_code == 401


async def test_token_signed_with_another_secret_is_rejected(anon_client, auth):
    forged = jwt.encode({"sub": "1"}, "not-the-real-secret-0123456789abcdef", algorithm="HS256")
    resp = await anon_client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 401


async def test_websocket_rejects_missing_token(session_factory):
    with TestClient(app) as tc, pytest.raises(WebSocketDisconnect) as exc:
        with tc.websocket_connect("/ws/studies/1") as ws:
            ws.receive_text()
    assert exc.value.code == 1008


async def test_websocket_accepts_valid_token(session_factory, auth):
    token = create_access_token(1)  # alice is user 1
    with TestClient(app) as tc, tc.websocket_connect(f"/ws/studies/1?token={token}") as ws:
        ws.send_text("ping")  # connection stays open
