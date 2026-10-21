from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.database import get_db
from app.services.auth_service import decode_access_token, get_user_by_token_hash, sha256_hex

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db=Depends(get_db),
):
    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    token_hash = sha256_hex(token)
    user = await get_user_by_token_hash(db, token_hash)
    if not user:
        raise HTTPException(status_code=401, detail="Session revoked or not found")

    return user


async def get_current_user_optional(
    request: Request,
    db=Depends(get_db),
):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    payload = decode_access_token(token)
    if not payload:
        return None
    token_hash = sha256_hex(token)
    return await get_user_by_token_hash(db, token_hash)
