import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

test_database_url = os.getenv("TEST_DATABASE_URL")
if not test_database_url:
    raise RuntimeError("TEST_DATABASE_URL must be set before running tests.")
if make_url(test_database_url).database != "evidenceos_test":
    raise RuntimeError("Tests may only run against the evidenceos_test database.")

os.environ["DATABASE_URL"] = test_database_url

from app.database import SessionLocal
from app.main import app
from app.models import User
from app.security import hash_password


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def user_factory():
    """Create test users and remove their dependent auth rows after each test."""
    created_user_ids = []

    def create_user(
        *,
        email="auth-test@example.com",
        password="correct-horse-battery-staple",
        email_verified=True,
        is_active=True,
    ):
        with SessionLocal() as db:
            user = User(
                email=email,
                password_hash=hash_password(password),
                email_verified=email_verified,
                is_active=is_active,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            created_user_ids.append(user.id)
            return {"id": user.id, "email": user.email, "password": password}

    yield create_user

    if created_user_ids:
        with SessionLocal() as db:
            for user_id in created_user_ids:
                _delete_auth_records(db, user_id)
            db.commit()


@pytest.fixture
def cleanup_user():
    """Track accounts created through the HTTP API and remove them afterward."""
    emails = []

    def track(email):
        emails.append(email)

    yield track

    if emails:
        with SessionLocal() as db:
            for email in emails:
                user_id = db.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": email},
                ).scalar_one_or_none()
                if user_id is not None:
                    _delete_auth_records(db, user_id)
            db.commit()


@pytest.fixture
def project_factory(user_factory):
    """Create a test project and remove it before its test user is deleted."""
    project_ids = []

    def create_project(
        owner_user_id, *, name="Test project", description="Test description"
    ):
        with SessionLocal() as db:
            project_id = db.execute(
                text(
                    "INSERT INTO projects "
                    "(name, description, owner_user_id, created_by_user_id) "
                    "VALUES (:name, :description, :owner_user_id, :created_by_user_id) "
                    "RETURNING id"
                ),
                {
                    "name": name,
                    "description": description,
                    "owner_user_id": owner_user_id,
                    "created_by_user_id": owner_user_id,
                },
            ).scalar_one()
            db.commit()
            project_ids.append(project_id)
            return project_id

    yield create_project

    if project_ids:
        with SessionLocal() as db:
            for project_id in project_ids:
                db.execute(
                    text("DELETE FROM projects WHERE id = :project_id"),
                    {"project_id": project_id},
                )
            db.commit()


def _delete_auth_records(db, user_id):
    db.execute(text("DELETE FROM sessions WHERE user_id = :user_id"), {"user_id": user_id})
    db.execute(
        text(
            "DELETE FROM email_verification_tokens WHERE user_id = :user_id"
        ),
        {"user_id": user_id},
    )
    db.query(User).filter(User.id == user_id).delete()
