from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.schemas import (
    ChallengeRequest,
    ChallengeResponse,
    RefreshResponse,
    VerifyRequest,
    VerifyResponse,
)
from app.services.auth_service import (
    RefreshSessionFailure,
    create_challenge,
    refresh_session,
    revoke_refresh_session,
    sha256_hex,
    verify_challenge_and_login,
)

router = APIRouter()
REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"
NO_STORE_HEADERS = {"Cache-Control": "no-store"}


def set_refresh_cookie(response: Response, token: str) -> None:
    """Set the same-origin refresh cookie shared by refresh and logout."""
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
        path=REFRESH_COOKIE_PATH,
        max_age=settings.JWT_REFRESH_EXPIRY_HOURS * 60 * 60,
    )


def clear_refresh_cookie(response: Response) -> None:
    """Expire the refresh cookie with attributes matching its creation."""
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=True,
        samesite="strict",
    )


def prevent_auth_response_caching(response: Response) -> None:
    """Prevent browsers and reverse proxies from caching auth material."""
    response.headers["Cache-Control"] = "no-store"


def auth_error(status_code: int, detail: str) -> HTTPException:
    """Build an explicit auth rejection that reverse proxies must not cache."""
    return HTTPException(status_code=status_code, detail=detail, headers=NO_STORE_HEADERS)


def require_browser_origin(request: Request) -> None:
    """Reject cross-site or non-browser use of refresh-cookie mutations."""
    origin = request.headers.get("origin")
    if origin is None or origin != settings.FRONTEND_URL:
        raise auth_error(status_code=403, detail="Origin is not allowed")


@router.post("/challenge", response_model=ChallengeResponse)
async def auth_challenge(
    req: ChallengeRequest, response: Response, db: AsyncSession = Depends(get_db)
) -> ChallengeResponse:
    prevent_auth_response_caching(response)
    challenge = await create_challenge(db, req.wallet_address)
    return ChallengeResponse(
        challenge=challenge.message,
        nonce=challenge.nonce,
        expires_at=challenge.expires_at,
    )


@router.post("/verify", response_model=VerifyResponse)
async def auth_verify(
    req: VerifyRequest,
    response: Response,
    _: None = Depends(require_browser_origin),
    db: AsyncSession = Depends(get_db),
) -> VerifyResponse:
    prevent_auth_response_caching(response)
    result = await verify_challenge_and_login(db, req.wallet_address, req.signature, req.nonce)
    if not result:
        raise auth_error(status_code=401, detail="Invalid signature or expired challenge")

    _session, access_token, refresh_token = result
    set_refresh_cookie(response, refresh_token)

    return VerifyResponse(access_token=access_token)


@router.post("/refresh", response_model=RefreshResponse)
async def auth_refresh(
    response: Response,
    refresh_token: str = Cookie(None),
    _: None = Depends(require_browser_origin),
    db: AsyncSession = Depends(get_db),
) -> RefreshResponse | JSONResponse:
    prevent_auth_response_caching(response)
    if not refresh_token:
        raise auth_error(status_code=401, detail="No refresh token provided")

    result = await refresh_session(db, refresh_token)
    if result is RefreshSessionFailure.REUSE_DETECTED:
        # Return instead of raising so get_db commits the family revocation.
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid or revoked refresh token"},
            headers=NO_STORE_HEADERS,
        )
    if not result:
        raise auth_error(status_code=401, detail="Invalid or revoked refresh token")

    _session, new_access_token, new_refresh_token = result
    set_refresh_cookie(response, new_refresh_token)

    return RefreshResponse(access_token=new_access_token)


@router.post("/logout")
async def auth_logout(
    response: Response,
    db: AsyncSession = Depends(get_db),
    refresh_token: str = Cookie(None),
    _: None = Depends(require_browser_origin),
) -> dict[str, str]:
    prevent_auth_response_caching(response)
    if refresh_token:
        token_hash = sha256_hex(refresh_token)
        await revoke_refresh_session(db, token_hash)
    clear_refresh_cookie(response)
    return {"detail": "Logged out"}
