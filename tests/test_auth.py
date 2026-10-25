from sqlalchemy import text

from app.database import SessionLocal
from app.security import hash_session_token


def test_register_normalizes_email_and_sends_verification_link(
    client, monkeypatch, cleanup_user
):
    sent_email = {}

    def capture_verification_email(email, token):
        sent_email.update(email=email, token=token)

    monkeypatch.setattr(
        "app.main.send_verification_email", capture_verification_email
    )

    response = client.post(
        "/api/v1/auth/register",
        json={"email": "  New.User@Example.com ", "password": "a-strong-password"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new.user@example.com"
    assert body["email_verified"] is False
    assert "password_hash" not in body
    assert sent_email["email"] == "new.user@example.com"
    cleanup_user("new.user@example.com")

    with SessionLocal() as db:
        stored_token = db.execute(
            text(
                "SELECT token_hash FROM email_verification_tokens "
                "WHERE user_id = :user_id"
            ),
            {"user_id": body["id"]},
        ).scalar_one()
    assert stored_token == hash_session_token(sent_email["token"])


def test_register_rejects_duplicate_email(client, monkeypatch, cleanup_user):
    monkeypatch.setattr("app.main.send_verification_email", lambda *args: None)
    payload = {"email": "duplicate-auth@example.com", "password": "a-strong-password"}

    first_response = client.post("/api/v1/auth/register", json=payload)
    second_response = client.post("/api/v1/auth/register", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == (
        "An account with this email already exists."
    )
    cleanup_user("duplicate-auth@example.com")


def test_register_validates_email_and_password(client):
    invalid_email = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "a-strong-password"},
    )
    short_password = client.post(
        "/api/v1/auth/register",
        json={"email": "valid-auth@example.com", "password": "short"},
    )

    assert invalid_email.status_code == 422
    assert short_password.status_code == 422


def test_verify_email_allows_login_and_profile_access(
    client, monkeypatch, cleanup_user
):
    sent_email = {}
    monkeypatch.setattr(
        "app.main.send_verification_email",
        lambda email, token: sent_email.update(email=email, token=token),
    )
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": "verify-auth@example.com", "password": "a-strong-password"},
    )
    assert registered.status_code == 201
    cleanup_user("verify-auth@example.com")

    verify_response = client.get(
        "/api/v1/auth/verify-email", params={"token": sent_email["token"]}
    )
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "VERIFY-AUTH@example.com", "password": "a-strong-password"},
    )

    assert verify_response.status_code == 200
    assert login_response.status_code == 200
    tokens = login_response.json()
    assert tokens["token_type"] == "bearer"
    assert tokens["expires_in"] == 900
    assert tokens["user"]["id"] == registered.json()["id"]
    assert tokens["user"]["email"] == "verify-auth@example.com"

    profile_response = client.get(
        "/api/v1/auth/my-profile",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert profile_response.status_code == 200
    assert profile_response.json() == {
        "id": registered.json()["id"],
        "email": "verify-auth@example.com",
        "email_verified": True,
        "is_active": True,
    }

    reused_link = client.get(
        "/api/v1/auth/verify-email", params={"token": sent_email["token"]}
    )
    assert reused_link.status_code == 400


def test_login_rejects_unknown_email_and_wrong_password(client, user_factory):
    user_factory(email="login-auth@example.com")

    unknown = client.post(
        "/api/v1/auth/login",
        json={"email": "missing-auth@example.com", "password": "a-strong-password"},
    )
    wrong_password = client.post(
        "/api/v1/auth/login",
        json={"email": "login-auth@example.com", "password": "incorrect-password"},
    )

    assert unknown.status_code == 401
    assert wrong_password.status_code == 401
    assert unknown.json()["detail"] == "Invalid username or password"


def test_login_requires_verified_and_active_account(client, user_factory):
    user_factory(email="unverified-auth@example.com", email_verified=False)
    user_factory(email="inactive-auth@example.com", is_active=False)

    unverified = client.post(
        "/api/v1/auth/login",
        json={"email": "unverified-auth@example.com", "password": "correct-horse-battery-staple"},
    )
    inactive = client.post(
        "/api/v1/auth/login",
        json={"email": "inactive-auth@example.com", "password": "correct-horse-battery-staple"},
    )

    assert unverified.status_code == 403
    assert unverified.json()["detail"] == "Please verify your email before logging in."
    assert inactive.status_code == 403
    assert inactive.json()["detail"] == "This account is inactive."


def test_profile_requires_valid_access_token(client):
    missing_token = client.get("/api/v1/auth/my-profile")
    invalid_token = client.get(
        "/api/v1/auth/my-profile",
        headers={"Authorization": "Bearer not-a-valid-token"},
    )

    assert missing_token.status_code == 401
    assert missing_token.headers["www-authenticate"] == "Bearer"
    assert invalid_token.status_code == 401


def test_refresh_rotates_token_and_logout_revokes_new_session(
    client, user_factory
):
    user_factory(email="refresh-auth@example.com")
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "refresh-auth@example.com", "password": "correct-horse-battery-staple"},
    )
    assert login.status_code == 200
    old_refresh_token = login.json()["refresh_token"]

    refreshed = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": old_refresh_token}
    )
    reused_old_token = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": old_refresh_token}
    )

    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] != old_refresh_token
    assert reused_old_token.status_code == 401

    logout = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refreshed.json()["refresh_token"]},
        headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"},
    )
    assert logout.status_code == 200
    assert logout.json()["message"] == "Logout Successful"

    revoked_refresh = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refreshed.json()["refresh_token"]},
    )
    assert revoked_refresh.status_code == 401
