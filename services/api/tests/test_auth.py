from conftest import auth, login


async def test_login_success_and_me(ctx):
    client, _ = ctx
    token = await login(client)
    r = await client.get("/api/auth/me", headers=auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "admin@test.local"
    assert body["role"] == "super_admin"
    assert body["is_super_admin"] is True


async def test_login_wrong_password(ctx):
    client, _ = ctx
    r = await client.post("/api/auth/login",
                          json={"email": "admin@test.local", "password": "nope"})
    assert r.status_code == 401


async def test_login_unknown_user(ctx):
    client, _ = ctx
    r = await client.post("/api/auth/login",
                          json={"email": "ghost@test.local", "password": "whatever"})
    assert r.status_code == 401


async def test_me_requires_token(ctx):
    client, _ = ctx
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_invalid_token_rejected(ctx):
    client, _ = ctx
    r = await client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


async def test_password_is_hashed_not_plaintext(ctx):
    _, app = ctx
    user = await app.state.store.get_user_by_email("admin@test.local")
    assert user is not None
    assert user.password_hash != "adminpass123"
    assert user.password_hash.startswith("$2")  # bcrypt
