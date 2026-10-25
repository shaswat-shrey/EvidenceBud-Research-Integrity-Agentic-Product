from fastapi import FastAPI, HTTPException, Depends, status, Query
from datetime import datetime, timezone, timedelta

from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import func, select, text, or_
from sqlalchemy.exc import IntegrityError

from app.auth_dependencies import get_current_user
from app.models import User, Project
from app.schemas import (
    UserRegister, 
    UserResponse, 
    UserLogin, 
    RefreshAccessTokens, 
    ProjectCreate, 
    ProjectResponse, 
    ProjectUpdate
)
from app.security import ( 
    hash_password, 
    create_session_token, 
    hash_session_token, 
    verify_password,
    create_access_token,
    create_refresh_token,
    hash_refresh_token
)
from app.database import get_db
from app.email_service import send_verification_email

app = FastAPI(title="Blue Backend")
SESSION_DURATION_HOURS = 24

@app.get("/")
def home():
    return {"message": "Blue API is running"}  #THIS IS JUST TO CHECK WHETHER ENDPOINT IS CONNECTED OR NOT.

@app.get("/api/v1/health/database")
def health_database(db: Session = Depends(get_db)):  #HEALTH OF THE DATABASE, AND GETTING THE STATUS OF THE CONNECTION.
    result = db.execute(
        text("SELECT current_database()")
    )
    database_name = result.scalar_one()
    return {
        "status": "connected",
        "database": database_name,
    }

#######################################################################################################
# -------------------------------------- REGISTER ------------------------------------------
#######################################################################################################

@app.post(
    "/api/v1/auth/register",
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

@app.post("/api/v1/auth/login",)
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

@app.get("/api/v1/auth/verify-email")
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

@app.get("/api/v1/auth/my-profile")
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

@app.post("/api/v1/auth/refresh")
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

@app.post("/api/v1/auth/logout")
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

######################################################################################################
# -------------------------------------- HELPER FUNCTION ------------------------------------------
######################################################################################################

def get_organisation_role(
    db: Session,
    organisation_id: UUID,
    user_id: UUID,
) -> str | None:
    query = text(
        """
            SELECT role FROM
            organisation_members
            WHERE org_id = :organisation_id
            AND user_id = :user_id
        """
    )
    result = db.execute(
        query,
        {
            "organisation_id": str(organisation_id),
            "user_id": str(user_id)
        }
    ).scalar_one_or_none()

    return result

def check_project_access(
        project: Project,
        current_user: dict,
        db: Session, 
        *,
        archive: bool = False
) -> None:
    user_id = UUID(str(current_user["id"]))

    if project.owner_user_id is not None:
        if project.owner_user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Project not found"
            )
        if archive:
            return
        return

    role = get_organisation_role(
        db,
        project.organisation_id,
        user_id
    )
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found."
        )
    if archive and role not in {"owner", "admin", "member"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to archive this project."
        )

################################################################################################################
# -------------------------------------- PUT PROJECTS API FUNCTION ------------------------------------------
################################################################################################################

@app.post(
    "/api/v1/projects",
    response_model= ProjectResponse,
    status_code=status.HTTP_201_CREATED
)
def create_project(
    payload: ProjectCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = UUID(str(current_user["id"]))
    print("USER")
    print(user_id)
    if payload.organisation_id is not None:
        role = get_organisation_role(
            db, 
            payload.organisation_id,
            user_id
        )
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this organisation."
            )
        owner_user_id = None
        organisation_id = payload.organisation_id
    else:
        owner_user_id = user_id
        organisation_id = None

    print("owner:", owner_user_id, "\n", "Org_id", organisation_id)
    project = Project(
        name=payload.name.strip(),
        description=payload.description,
        owner_user_id=owner_user_id,
        organisation_id=organisation_id,
        created_by_user_id=user_id,
    )
    if not project.name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Project name cannot be blank"
        )
    print(project.owner_user_id)

    try:
        db.add(project)
        db.commit()
        db.refresh(project)
        print("Successfully created")
        return project
    except Exception as exc:
        db.rollback()
        print("PROJECT CREATION ERROR:", repr(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create project."
        )

###############################################################################################################
# -------------------------------------- GET PROJECTS API FUNCTION ------------------------------------------
###############################################################################################################

@app.get(
    "/api/v1/projects",
    response_model=list[ProjectResponse]
)
def list_projects(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_id = UUID(str(current_user["id"]))
    query = text(
        """
            SELECT org_id
            FROM organisation_members
            WHERE user_id = :user_id
        """
    )
    org_ids = db.execute(
        query,
        {
            "user_id": str(user_id)
        },
    ).scalars().all()

    projects = db.query(Project).filter(
        Project.archived_at.is_(None),
        or_(
            Project.owner_user_id == user_id,
            Project.organisation_id.in_(org_ids)
        )
    ).order_by(Project.created_at.desc()).all()
    return projects

###############################################################################################################
# -------------------------------------- GET PROJECT_ID API FUNCTION -----------------------------------------
###############################################################################################################    

@app.get(
    "/api/v1/projects/{project_id}",
    response_model=ProjectResponse,
)
def get_project(
    project_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)

    if project is None or project.archived_at is not None:
        raise HTTPException(status_code=404, detail="Project not found.")

    check_project_access(project, current_user, db)
    return project

###############################################################################################################
# -------------------------------------- UPDATE PROJECT_ID API FUNCTION --------------------------------------
###############################################################################################################

@app.patch(
    "/api/v1/projects/{project_id}",
    response_model=ProjectResponse
)
def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if project is None or project.archived_at is not None:
        raise HTTPException(status_code=404, detail="Project not found.")

    check_project_access(project, current_user, db)
    changes = payload.model_dump(exclude_unset=True)

    if "name" in changes:
        if changes["name"] is None or not changes["name"].strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Project name can not be blank."
            )
        changes["name"] = changes["name"].strip()

    for field, value in changes.items():
        setattr(project, field, value)

    project.updated_at = datetime.now(timezone.utc)
    try: 
        db.commit()
        db.refresh(project)
        return project
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to update project."
        )

###############################################################################################################
# -------------------------------------- POST PROJECT_ID API FUNCTION --------------------------------------
###############################################################################################################

@app.post(
    "/api/v1/projects/{project_id}/archive",
    response_model=ProjectResponse,
)
def archive_project(
    project_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)

    if project is None or project.archived_at is not None:
        raise HTTPException(status_code=404, detail="Project not found.")

    check_project_access(project, current_user, db, archive=True)
    project.archived_at = datetime.now(timezone.utc)
    project.updated_at = datetime.now(timezone.utc)

    try:
        db.commit()
        db.refresh(project)
        return project
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to archive project.",
        )
