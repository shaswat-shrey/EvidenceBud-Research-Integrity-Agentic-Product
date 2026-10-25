from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from datetime import datetime, timezone, timedelta
from app.auth_dependencies import get_current_user
from app.database import get_db
from app.email_service import send_verification_email
from app.models.user import User
from app.schemas import UserLogin, UserRegister, UserResponse, RefreshAccessTokens
from app.security import (
    create_access_token,
    create_refresh_token,
    create_session_token,
    hash_password,
    hash_refresh_token,
    hash_session_token,
    verify_password,
)

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


#######################################################################################################
# -------------------------------------- REGISTER ------------------------------------------
#######################################################################################################

@router.post(
    "/register",
    response_model=UserResponse,            #REGISTER ENDPOINT, WHERE THE RESPONSE MODEL IS STRICTLY FIXED TO USER_RESPONSE MODEL
    status_code=status.HTTP_201_CREATED,
    )
def register_user(payload: UserRegister, db: Session = Depends(get_db)):
    email = str(payload.email).strip().lower()
    query = text("""
        SELECT id
        FROM users
        WHERE LOWER(email) = :email
    """)
    existing_user = db.execute(
        query,
        {
            "email": email
        }
    ).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )
    user = User(
        email=email,
        password_hash = hash_password(payload.password),
        email_verified = False,
        is_active = True,
    )
    created_at = datetime.now(timezone.utc)
    try:
        db.add(user)
        db.flush()

        if payload.organisation_name is not None:
            organisation = db.execute(
                text(
                    """
                        INSERT INTO organisations
                        (name, slug, created_at) VALUES
                        (:name, :slug, :created_at)
                        RETURNING id
                    """
                ),
                {
                    "name": payload.organisation_name.strip(),
                    "slug": payload.organisation_slug,
                    "created_at": created_at,
                }
            ).mappings().one()

            db.execute(
                text(
                    """
                        INSERT INTO organisation_members
                        (org_id, user_id, role)
                        VALUES
                        (:org_id, :user_id, :role)
                    """
                ),
                {
                    "org_id": organisation["id"],
                    "user_id": user.id,
                    "role": "owner",
                },
            )

        token = create_session_token()
        hash_token = hash_session_token(token=token)

        expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
        db.execute(
            text("""
                INSERT INTO email_verification_tokens
                    (user_id, token_hash, expires_at)
                VALUES
                    (:user_id, :token_hash, :expires_at)
            """),
            {
                "user_id": user.id,
                "token_hash": hash_token,
                "expires_at": expires_at,
            },
        )

        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to create an account with these details.",
        )
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to register your account.",
        )
    try:
        send_verification_email(email, token)

    except Exception as exc:
        print("EMAIL DELIVERY ERROR:", repr(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Account created, but the verification email could not "
                "be sent. Please request a new verification email."
            ),
        )
    return user

#######################################################################################################
# -------------------------------------- LOGIN ------------------------------------------
#######################################################################################################

@router.post("/login",)
def login_user(payload: UserLogin, db: Session = Depends(get_db)):
    email = str(payload.email).strip().lower()
    query = text("""
        SELECT id, email, password_hash, is_active, email_verified
        FROM users
        WHERE LOWER(email) = :email
    """)
    user = db.execute(
        query,
        {"email": email}
    ).mappings().first()
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is inactive.",
        )
    if not user["email_verified"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before logging in.",
        )

    access_token = create_access_token(str(user["id"]))
    refresh_token = create_refresh_token()
    refresh_token_hash = hash_refresh_token(refresh_token)

    now = datetime.now(timezone.utc)
    expire_at = now + timedelta(days=7)

    insert_session_query = text(
        """
        INSERT INTO sessions (user_id, token_hash, expires_at, last_seen_at)
        VALUES (:user_id, :token_hash, :expires_at, :last_seen_at)
        """
    )
    try:
        db.execute(
            insert_session_query,
            {
                "user_id": user["id"],
                "token_hash": refresh_token_hash,
                "expires_at": expire_at,
                "last_seen_at": now,
            },
        )
        db.commit()
    except  Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create a session.",
        )
    return {
        "message": "Login successful.",
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": 900,
        "refresh_token": refresh_token,
        "refresh_expires_at": expire_at,
        "user": {
            "id": str(user["id"]),
            "email": user["email"],
        },
    }

#######################################################################################################
# -------------------------------------- EMAIL VERIFICATION ------------------------------------------
#######################################################################################################

@router.get("/verify-email")
def verify_email(token: str = Query(..., min_length=20), db: Session = Depends(get_db)):
    token_hash = hash_session_token(token)

    try:
        # Consume the token only if it is valid, unused and unexpired.
        result = db.execute(
            text("""
                UPDATE email_verification_tokens
                SET used_at = NOW()
                WHERE token_hash = :token_hash
                  AND used_at IS NULL
                  AND expires_at > NOW()
                RETURNING user_id
            """),
            {"token_hash": token_hash},
        ).mappings().first()

        if not result:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail="Invalid, expired, or already-used verification link.",
            )
        db.execute(
            text("""
                UPDATE users
                SET email_verified = TRUE,
                    updated_at = NOW()
                WHERE id = :user_id
            """),
            {"user_id": result["user_id"]},
        )

        db.commit()

    except HTTPException:
        raise

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not verify email.",
        )

    return {
        "message": "Email verified successfully. You can now log in."
    }

#######################################################################################################
# -------------------------------------- AUTH FUNCTION ------------------------------------------
#######################################################################################################

@router.get("/my-profile")
def get_my_profile(
    current_user: dict = Depends(get_current_user),
):
    return {
        "id": str(current_user["id"]),
        "email": current_user["email"],
        "email_verified": current_user["email_verified"],
        "is_active": current_user["is_active"],
    }

#######################################################################################################
# -------------------------------------- REFRESH TOKENS ------------------------------------------
#######################################################################################################

@router.post("/api/v1/auth/refresh")
def refresh_access_token(
    payload: RefreshAccessTokens,
    db: Session = Depends(get_db)
):
    old_token_hash = hash_refresh_token(payload.refresh_token)
    now = datetime.now(timezone.utc)

    try:
        session_query = text(
        """
            SELECT
                s.id AS session_id,
                s.user_id,
                s.expires_at,
                s.revoked_at,
                u.email,
                u.is_active,
                u.email_verified
            FROM sessions AS s
            JOIN users AS u ON u.id = s.user_id
            WHERE s.token_hash = :token_hash
            FOR UPDATE OF s
        """
        )
        session = db.execute(
            session_query,
            {
                "token_hash": old_token_hash
            }
        ).mappings().first()

        if (
            not session 
            or session["revoked_at"] is not None
            or session["expires_at"] <= now
        ):
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token.",
            )

        if not session["is_active"] or not session["email_verified"]:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="The Account cannot refresh its session.",
            ) 

        new_access_token = create_access_token(str(session["user_id"]))
        new_refresh_token = create_refresh_token()
        new_refresh_hash = hash_refresh_token(new_refresh_token)

        expire_at = now + timedelta(days=7)

        revoke_query = text(
            """
                UPDATE sessions
                SET revoked_at = :revoked_at
                WHERE id = :session_id
                AND revoked_at IS NULL
            """
        )
        db.execute(
            revoke_query,
            {
                "revoked_at": now,
                "session_id": session["session_id"],
            }
        )
        insert_query = text(
            """
                INSERT INTO sessions (
                    user_id,
                    token_hash,
                    expires_at,
                    last_seen_at
                )
                VALUES (
                    :user_id,
                    :token_hash,
                    :expires_at,
                    :last_seen_at
                )
            """
        )
        db.execute(
            insert_query,
            {
                "user_id": session["user_id"],
                "token_hash": new_refresh_hash,
                "expires_at": expire_at,
                "last_seen_at": now,
            }
        )
        db.commit()

        return {
            "access_token": new_access_token,
            "token_type": "bearer",
            "expires_in": 900,
            "refresh_token": new_refresh_token,
            "refresh_expires_at": expire_at,
        }
    except HTTPException:
        raise

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to refresh the session.",
        )

#######################################################################################################
# -------------------------------------- LOGOUT FUNCTION ------------------------------------------
#######################################################################################################

@router.post("/logout")
def logout(
    payload: RefreshAccessTokens,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
    ):
    refresh_token = payload.refresh_token
    refresh_token_hash = hash_refresh_token(refresh_token)
    now = datetime.now(timezone.utc)

    query = text(
        """
            UPDATE sessions
            SET revoked_at = :revoked_at
            WHERE token_hash = :token_hash
            AND user_id = :user_id
            AND revoked_at is NULL
            RETURNING id
        """
        )
    try:
        result = db.execute(
            query,
            {
                "revoked_at": now,
                "token_hash": refresh_token_hash,
                "user_id": current_user["id"],
            }
        )
        revoked_session = result.first()
        db.commit()
        if not revoked_session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or already-revoked refresh token."
            )
        return {
            "message": "Logout Successful"
        }
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to log out."
        )
