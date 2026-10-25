from uuid import uuid4

import pytest
from sqlalchemy import text

from app.database import SessionLocal
from app.security import create_access_token


def auth_headers(user):
    token = create_access_token(str(user["id"]))
    return {"Authorization": f"Bearer {token}"}


def test_projects_require_authentication(client):
    response = client.get("/api/v1/projects")

    assert response.status_code == 401


def test_create_personal_project(client, user_factory):
    user = user_factory(email="project-create@example.com")

    response = client.post(
        "/api/v1/projects",
        json={"name": "  Evidence review  ", "description": "Collect evidence."},
        headers=auth_headers(user),
    )

    assert response.status_code == 201
    project = response.json()
    assert project["name"] == "Evidence review"
    assert project["description"] == "Collect evidence."
    assert project["owner_user_id"] == str(user["id"])
    assert project["organisation_id"] is None
    assert project["created_by_user_id"] == str(user["id"])


def test_create_project_rejects_empty_name(client, user_factory):
    user = user_factory(email="project-validation@example.com")

    response = client.post(
        "/api/v1/projects",
        json={"name": "", "description": "Invalid project."},
        headers=auth_headers(user),
    )

    assert response.status_code == 422


def test_list_projects_returns_only_current_users_active_projects(
    client, user_factory, project_factory
):
    owner = user_factory(email="project-list-owner@example.com")
    other_user = user_factory(email="project-list-other@example.com")
    owned_project_id = project_factory(
        owner["id"], name="Owned project", description="Visible to owner"
    )
    project_factory(other_user["id"], name="Other project")

    response = client.get("/api/v1/projects", headers=auth_headers(owner))

    assert response.status_code == 200
    projects = response.json()
    assert [project["id"] for project in projects] == [str(owned_project_id)]
    assert projects[0]["name"] == "Owned project"


def test_get_project_returns_owned_project(client, user_factory, project_factory):
    owner = user_factory(email="project-get-owner@example.com")
    project_id = project_factory(owner["id"], name="Requested project")

    response = client.get(
        f"/api/v1/projects/{project_id}", headers=auth_headers(owner)
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(project_id)
    assert response.json()["name"] == "Requested project"


def test_get_project_returns_not_found_for_unknown_or_archived_project(
    client, user_factory, project_factory
):
    user = user_factory(email="project-missing@example.com")
    headers = auth_headers(user)
    unknown = client.get(f"/api/v1/projects/{uuid4()}", headers=headers)

    assert unknown.status_code == 404
    assert unknown.json()["detail"] == "Project not found."

    archived_project_id = project_factory(user["id"], name="Archived project")
    with SessionLocal() as db:
        db.execute(
            text("UPDATE projects SET archived_at = NOW() WHERE id = :project_id"),
            {"project_id": archived_project_id},
        )
        db.commit()

    archived = client.get(
        f"/api/v1/projects/{archived_project_id}", headers=headers
    )
    assert archived.status_code == 404


def test_user_cannot_get_another_users_project(
    client, user_factory, project_factory
):
    owner = user_factory(email="project-private-owner@example.com")
    other_user = user_factory(email="project-private-other@example.com")
    project_id = project_factory(owner["id"])

    response = client.get(
        f"/api/v1/projects/{project_id}", headers=auth_headers(other_user)
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Project not found"


def test_update_project_trims_name_and_updates_description(
    client, user_factory, project_factory
):
    owner = user_factory(email="project-update-owner@example.com")
    project_id = project_factory(owner["id"], name="Before update")

    response = client.patch(
        f"/api/v1/projects/{project_id}",
        json={"name": "  Updated project  ", "description": "Updated details."},
        headers=auth_headers(owner),
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated project"
    assert response.json()["description"] == "Updated details."


@pytest.mark.parametrize("name", ["", "   "])
def test_update_project_rejects_blank_name(client, user_factory, project_factory, name):
    owner = user_factory(email=f"project-blank-{len(name)}@example.com")
    project_id = project_factory(owner["id"])

    response = client.patch(
        f"/api/v1/projects/{project_id}",
        json={"name": name},
        headers=auth_headers(owner),
    )

    assert response.status_code == 422


def test_user_cannot_update_another_users_project(
    client, user_factory, project_factory
):
    owner = user_factory(email="project-update-private-owner@example.com")
    other_user = user_factory(email="project-update-private-other@example.com")
    project_id = project_factory(owner["id"])

    response = client.patch(
        f"/api/v1/projects/{project_id}",
        json={"description": "Unauthorized change"},
        headers=auth_headers(other_user),
    )

    assert response.status_code == 401


def test_archive_project_hides_it_from_future_requests(
    client, user_factory, project_factory
):
    owner = user_factory(email="project-archive-owner@example.com")
    project_id = project_factory(owner["id"], name="Archive me")
    headers = auth_headers(owner)

    archived = client.post(
        f"/api/v1/projects/{project_id}/archive", headers=headers
    )
    get_archived = client.get(f"/api/v1/projects/{project_id}", headers=headers)
    archive_again = client.post(
        f"/api/v1/projects/{project_id}/archive", headers=headers
    )

    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert get_archived.status_code == 404
    assert archive_again.status_code == 404


def test_user_cannot_archive_another_users_project(
    client, user_factory, project_factory
):
    owner = user_factory(email="project-archive-private-owner@example.com")
    other_user = user_factory(email="project-archive-private-other@example.com")
    project_id = project_factory(owner["id"])

    response = client.post(
        f"/api/v1/projects/{project_id}/archive",
        headers=auth_headers(other_user),
    )

    assert response.status_code == 401
