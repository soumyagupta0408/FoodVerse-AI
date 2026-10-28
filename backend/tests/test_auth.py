from tests.conftest import register


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/health/ready").json()["database"] == "ok"


def test_register_login_refresh_logout(client):
    r = client.post("/api/v1/auth/register", json={"email": "Me@Example.com", "password": "correct-horse-battery"})
    assert r.status_code == 201
    login = client.post("/api/v1/auth/login", json={"email": "me@example.com", "password": "correct-horse-battery"})
    assert login.status_code == 200
    tokens = login.json()
    me = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.json()["email"] == "me@example.com"
    ref = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert ref.status_code == 200
    # rotated: the old refresh token is now dead
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    new = ref.json()["refresh_token"]
    assert client.post("/api/v1/auth/logout", json={"refresh_token": new}).status_code == 204
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": new}).status_code == 401


def test_rejects_bad_credentials_and_duplicates(client):
    register(client)
    assert client.post("/api/v1/auth/register", json={"email": "a@example.com", "password": "correct-horse-battery"}).status_code == 409
    assert client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "wrong-password-x"}).status_code == 401
    assert client.post("/api/v1/auth/register", json={"email": "c@example.com", "password": "short"}).status_code == 422


def test_protected_routes_need_token(client):
    assert client.get("/api/v1/users/me").status_code == 401
    assert client.get("/api/v1/users/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401
    r = client.get("/api/v1/food/recognize/abc")
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"


def test_refresh_token_cannot_be_used_as_access(client):
    r = client.post("/api/v1/auth/register", json={"email": "z@example.com", "password": "correct-horse-battery"})
    refresh = r.json()["refresh_token"]
    assert client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {refresh}"}).status_code == 401


def test_profile_update(client, auth):
    r = client.patch("/api/v1/users/me/profile", headers=auth, json={"diet_pattern": "vegan", "allergies": ["peanut"]})
    assert r.status_code == 200 and r.json()["allergies"] == ["peanut"]
    assert client.patch("/api/v1/users/me/profile", headers=auth, json={"diet_pattern": "carnivore-only"}).status_code == 422


def test_error_has_request_id(client):
    r = client.get("/api/v1/users/me", headers={"X-Request-ID": "req-123"})
    assert r.headers["X-Request-ID"] == "req-123" and r.json()["error"]["request_id"] == "req-123"
