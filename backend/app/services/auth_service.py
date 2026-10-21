import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from enum import Enum
from uuid import UUID

from eth_account.messages import encode_defunct
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import AuthChallenge, AuthSession, User

WALLET_RE = re.compile(r"^0x[0-9a-f]{40}$")


class RefreshSessionFailure(Enum):
    """A refresh outcome that requires a non-success HTTP response."""

    REUSE_DETECTED = "reuse_detected"


def _as_utc(value: datetime) -> datetime:
    """Normalize persisted timestamps across SQLite and PostgreSQL adapters."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def normalize_wallet(address: str) -> str:
    """Canonical lowercase, validating ^0x[0-9a-f]{40}$."""
    normalized = address.lower()
    if not WALLET_RE.match(normalized):
        raise ValueError(f"Invalid wallet address format: {address}")
    return normalized


def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def generate_nonce() -> str:
    return secrets.token_hex(32)


def create_access_token(user_id: str, wallet: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "wallet": wallet,
        "role": role,
        "iat": now,
        "exp": now + timedelta(hours=settings.JWT_EXPIRY_HOURS),
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def create_refresh_token() -> str:
    return secrets.token_hex(32)


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        return payload
    except JWTError:
        return None


async def create_challenge(db: AsyncSession, wallet_address: str) -> AuthChallenge:
    wallet_address = normalize_wallet(wallet_address)
    nonce = generate_nonce()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=5)
    message = (
        f"Sign this message to authenticate with Nebula AI Cloud.\n\n"
        f"Wallet: {wallet_address}\n"
        f"Nonce: {nonce}\n"
        f"Issued: {now.isoformat()}\n"
        f"Expires: {expires_at.isoformat()}"
    )
    challenge = AuthChallenge(
        wallet_address=wallet_address,
        nonce=nonce,
        message=message,
        expires_at=expires_at,
    )
    db.add(challenge)
    await db.flush()
    return challenge


async def verify_challenge_and_login(
    db: AsyncSession,
    wallet_address: str,
    signature: str,
    nonce: str,
) -> tuple[AuthSession, str, str] | None:
    wallet_address = normalize_wallet(wallet_address)
    # Find the challenge
    result = await db.execute(
        select(AuthChallenge)
        .where(
            AuthChallenge.wallet_address == wallet_address,
            AuthChallenge.nonce == nonce,
            AuthChallenge.used.is_(False),
        )
        .with_for_update()
    )
    challenge = result.scalar_one_or_none()
    if not challenge:
        return None
    if _as_utc(challenge.expires_at) < datetime.now(timezone.utc):
        return None

    # Verify signature
    try:
        message_encode = encode_defunct(text=challenge.message)
        from eth_account import Account

        recovered = Account.recover_message(message_encode, signature=signature)
    except Exception:
        return None

    if recovered.lower() != wallet_address.lower():
        return None

    # Mark challenge as used
    challenge.used = True

    # Find or create user
    result = await db.execute(select(User).where(User.wallet_address == wallet_address))
    user = result.scalar_one_or_none()
    if not user:
        user = User(wallet_address=wallet_address, role="user")
        db.add(user)
        await db.flush()

    # Create session
    access_token = create_access_token(str(user.id), wallet_address, user.role or "user")
    refresh_token = create_refresh_token()
    now = datetime.now(timezone.utc)

    session = AuthSession(
        user_id=user.id,
        token_hash=sha256_hex(access_token),
        refresh_token_hash=sha256_hex(refresh_token),
        expires_at=now + timedelta(hours=settings.JWT_REFRESH_EXPIRY_HOURS),
    )
    db.add(session)
    await db.flush()

    return session, access_token, refresh_token


async def refresh_session(
    db: AsyncSession,
    refresh_token: str,
) -> tuple[AuthSession, str, str] | RefreshSessionFailure | None:
    token_hash = sha256_hex(refresh_token)

    # Find session by refresh token hash
    result = await db.execute(select(AuthSession).where(AuthSession.refresh_token_hash == token_hash).with_for_update())
    session = result.scalar_one_or_none()
    if not session:
        return None
    if session.revoked_at is not None:
        # Reuse detection: revoke all sessions for this user
        await revoke_all_user_sessions(db, session.user_id)
        return RefreshSessionFailure.REUSE_DETECTED
    if _as_utc(session.expires_at) < datetime.now(timezone.utc):
        return None

    # Get user
    result = await db.execute(select(User).where(User.id == session.user_id))
    user = result.scalar_one_or_none()
    if not user:
        return None

    # Create new session
    new_access_token = create_access_token(str(user.id), user.wallet_address, user.role or "user")
    new_refresh_token = create_refresh_token()
    now = datetime.now(timezone.utc)

    new_session = AuthSession(
        user_id=user.id,
        token_hash=sha256_hex(new_access_token),
        refresh_token_hash=sha256_hex(new_refresh_token),
        expires_at=now + timedelta(hours=settings.JWT_REFRESH_EXPIRY_HOURS),
    )
    db.add(new_session)
    await db.flush()

    # Mark old session as replaced
    session.revoked_at = now
    session.replaced_by_session_id = new_session.id
    await db.flush()

    return new_session, new_access_token, new_refresh_token


async def revoke_all_user_sessions(db: AsyncSession, user_id: UUID) -> None:
    """Revoke every active refresh-token session owned by a user."""
    result = await db.execute(
        select(AuthSession)
        .where(
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
        )
        .with_for_update()
    )
    sessions = result.scalars().all()
    now = datetime.now(timezone.utc)
    for s in sessions:
        s.revoked_at = now
    await db.flush()


async def revoke_refresh_session(db: AsyncSession, refresh_token_hash: str) -> bool:
    """Revoke the session identified by its hashed refresh cookie."""
    result = await db.execute(
        select(AuthSession).where(AuthSession.refresh_token_hash == refresh_token_hash).with_for_update()
    )
    session = result.scalar_one_or_none()
    if not session:
        return False
    session.revoked_at = datetime.now(timezone.utc)
    await db.flush()
    return True


async def get_user_by_token_hash(db: AsyncSession, token_hash: str) -> User | None:
    result = await db.execute(
        select(User)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(
            AuthSession.token_hash == token_hash,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > datetime.now(timezone.utc),
        )
    )
    return result.scalar_one_or_none()
