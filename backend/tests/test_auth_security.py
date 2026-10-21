"""Browser authentication security tests at the public HTTP interface."""

from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import settings
from app.database import get_db
from app.main import app
from app.models import AuthChallenge, AuthSession
from app.services.auth_service import sha256_hex

ALLOWED_ORIGIN = settings.FRONTEND_URL


def _cookie_value(set_cookie: str) -> str:
    parsed = SimpleCookie()
    parsed.load(set_cookie)
    return parsed["refresh_token"].value


async def _login(client: AsyncClient) -> tuple[str, str]:
    account = Account.create()
    wallet = account.address.lower()
    challenge = await client.post("/v1/auth/challenge", json={"wallet_address": wallet})
    body = challenge.json()
    signature = Account.sign_message(encode_defunct(text=body["challenge"]), account.key).signature.hex()
    verified = await client.post(
        "/v1/auth/verify",
        json={"wallet_address": wallet, "signature": signature, "nonce": body["nonce"]},
        headers={"Origin": ALLOWED_ORIGIN},
    )
    assert verified.status_code == 200
    assert verified.headers["cache-control"] == "no-store"
    return verified.json()["access_token"], verified.headers["set-cookie"]


@pytest.mark.asyncio
async def test_verify_cookie_matches_same_origin_proxy_auth_scope():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        _, cookie = await _login(client)

    lowered = cookie.lower()
    assert "httponly" in lowered
    assert "secure" in lowered
    assert "samesite=strict" in lowered
    assert "path=/api/v1/auth" in lowered


@pytest.mark.asyncio
async def test_challenge_is_single_use():
    account = Account.create()
    wallet = account.address.lower()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        challenge = (await client.post("/v1/auth/challenge", json={"wallet_address": wallet})).json()
        signature = Account.sign_message(encode_defunct(text=challenge["challenge"]), account.key).signature.hex()
        payload = {"wallet_address": wallet, "signature": signature, "nonce": challenge["nonce"]}
        first = await client.post("/v1/auth/verify", json=payload, headers={"Origin": ALLOWED_ORIGIN})
        replay = await client.post("/v1/auth/verify", json=payload, headers={"Origin": ALLOWED_ORIGIN})

    assert first.status_code == 200
    assert replay.status_code == 401
    assert replay.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_challenge_rejects_wallet_mismatch():
    challenged = Account.create()
    attacker = Account.create()
    wallet = challenged.address.lower()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        challenge = (await client.post("/v1/auth/challenge", json={"wallet_address": wallet})).json()
        signature = Account.sign_message(encode_defunct(text=challenge["challenge"]), attacker.key).signature.hex()
        response = await client.post(
            "/v1/auth/verify",
            json={"wallet_address": wallet, "signature": signature, "nonce": challenge["nonce"]},
            headers={"Origin": ALLOWED_ORIGIN},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_challenge_rejects_expired_nonce(db: AsyncSession):
    account = Account.create()
    wallet = account.address.lower()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        challenge = (await client.post("/v1/auth/challenge", json={"wallet_address": wallet})).json()
        row = (await db.execute(select(AuthChallenge).where(AuthChallenge.nonce == challenge["nonce"]))).scalar_one()
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
        signature = Account.sign_message(encode_defunct(text=challenge["challenge"]), account.key).signature.hex()
        response = await client.post(
            "/v1/auth/verify",
            json={"wallet_address": wallet, "signature": signature, "nonce": challenge["nonce"]},
            headers={"Origin": ALLOWED_ORIGIN},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_verify_rejects_disallowed_origin_before_setting_cookie():
    account = Account.create()
    wallet = account.address.lower()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        challenge = (await client.post("/v1/auth/challenge", json={"wallet_address": wallet})).json()
        signature = Account.sign_message(encode_defunct(text=challenge["challenge"]), account.key).signature.hex()
        response = await client.post(
            "/v1/auth/verify",
            json={"wallet_address": wallet, "signature": signature, "nonce": challenge["nonce"]},
            headers={"Origin": "https://evil.example"},
        )

    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
    assert "set-cookie" not in response.headers


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", [None, "https://evil.example", f"{ALLOWED_ORIGIN}/"])
async def test_refresh_rejects_missing_or_disallowed_origin(origin: str | None):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        _, set_cookie = await _login(client)
        headers = {"Cookie": f"refresh_token={_cookie_value(set_cookie)}"}
        if origin:
            headers["Origin"] = origin
        response = await client.post("/v1/auth/refresh", headers=headers)

    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_refresh_rotates_token_and_reuse_revokes_descendant_session(engine: AsyncEngine):
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def transactional_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = transactional_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        _, original_cookie = await _login(client)
        original = _cookie_value(original_cookie)
        first_refresh = await client.post(
            "/v1/auth/refresh",
            headers={"Origin": ALLOWED_ORIGIN, "Cookie": f"refresh_token={original}"},
        )
        rotated = _cookie_value(first_refresh.headers["set-cookie"])
        rotated_cookie = first_refresh.headers["set-cookie"].lower()
        replay = await client.post(
            "/v1/auth/refresh",
            headers={"Origin": ALLOWED_ORIGIN, "Cookie": f"refresh_token={original}"},
        )
        descendant = await client.post(
            "/v1/auth/refresh",
            headers={"Origin": ALLOWED_ORIGIN, "Cookie": f"refresh_token={rotated}"},
        )

    assert first_refresh.status_code == 200
    assert first_refresh.headers["cache-control"] == "no-store"
    assert rotated != original
    assert "httponly" in rotated_cookie
    assert "secure" in rotated_cookie
    assert "samesite=strict" in rotated_cookie
    assert "path=/api/v1/auth" in rotated_cookie
    assert replay.status_code == 401
    assert descendant.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_refresh_session_and_clears_cookie():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        _, set_cookie = await _login(client)
        refresh_token = _cookie_value(set_cookie)
        logout = await client.post(
            "/v1/auth/logout",
            headers={"Origin": ALLOWED_ORIGIN, "Cookie": f"refresh_token={refresh_token}"},
        )
        after_logout = await client.post(
            "/v1/auth/refresh",
            headers={"Origin": ALLOWED_ORIGIN, "Cookie": f"refresh_token={refresh_token}"},
        )

    assert logout.status_code == 200
    assert logout.headers["cache-control"] == "no-store"
    cleared = logout.headers["set-cookie"].lower()
    assert "path=/api/v1/auth" in cleared
    assert "max-age=0" in cleared
    assert after_logout.status_code == 401


@pytest.mark.asyncio
async def test_logout_rejects_disallowed_origin_without_revoking_session():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        _, set_cookie = await _login(client)
        refresh_token = _cookie_value(set_cookie)
        rejected = await client.post(
            "/v1/auth/logout",
            headers={"Origin": "https://evil.example", "Cookie": f"refresh_token={refresh_token}"},
        )
        still_valid = await client.post(
            "/v1/auth/refresh",
            headers={"Origin": ALLOWED_ORIGIN, "Cookie": f"refresh_token={refresh_token}"},
        )

    assert rejected.status_code == 403
    assert still_valid.status_code == 200


@pytest.mark.asyncio
async def test_expired_access_token_is_rejected():
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": "00000000-0000-0000-0000-000000000000",
            "wallet": "0x" + "11" * 20,
            "role": "user",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
            "jti": "expired",
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        response = await client.get("/v1/jobs", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_expired_refresh_session_is_rejected(db: AsyncSession):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        _, set_cookie = await _login(client)
        refresh_token = _cookie_value(set_cookie)
        session = (
            await db.execute(select(AuthSession).where(AuthSession.refresh_token_hash == sha256_hex(refresh_token)))
        ).scalar_one()
        session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
        response = await client.post(
            "/v1/auth/refresh",
            headers={"Origin": ALLOWED_ORIGIN, "Cookie": f"refresh_token={refresh_token}"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("origin", "allowed"),
    [(ALLOWED_ORIGIN, True), ("https://evil.example", False)],
)
async def test_cors_preflight_allows_only_configured_frontend(origin: str, allowed: bool):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        response = await client.options(
            "/v1/auth/refresh",
            headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
        )

    if allowed:
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
        assert response.headers["access-control-allow-credentials"] == "true"
    else:
        assert response.status_code == 400
        assert "access-control-allow-origin" not in response.headers
