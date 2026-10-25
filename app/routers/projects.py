from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.auth_dependencies import get_current_user
from app.database import get_db
from app.models.project import Project
from app.schemas import ProjectCreate, ProjectResponse, ProjectUpdate

router = APIRouter(
    prefix="/api/v1/projects", 
    tags=["Projects"]
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

@router.post(
    "",
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

@router.get(
    "",
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

@router.get(
    "/{project_id}",
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

@router.patch(
    "/{project_id}",
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

@router.post(
    "/{project_id}/archive",
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
