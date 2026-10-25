from uuid import UUID 
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.orm import session

from app.database import get_db
from app.security import decode_access_token

bearer_Scheme = HTTPBearer(auto_error=False)

def get_current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(
            bearer_Scheme
            ),
            db: session = Depends(get_db)
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credentials are none",
            headers={"WWW-Authenticate": "Bearer"}
        )
    access_token = credentials.credentials
    try:
        payload = decode_access_token(access_token)
        user_id = UUID(payload["sub"])

    except (jwt.InvalidTokenError, ValueError, KeyError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers = {"WWW-Authentication": "Bearer"},
        )

    query = text("""
        SELECT id, email, email_verified, is_active
        FROM users
        WHERE id = :user_id
    """)
    user = db.execute(
        query,
        {"user_id": str(user_id)},
    ).mappings().first()

    if not user or not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is unavailable.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user["email_verified"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification is required.",
        )

    return dict(user)

    