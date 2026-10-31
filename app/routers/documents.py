import logging
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth_dependencies import get_current_user
from app.database import get_db
from app.models import Document
from app.services.file_storage import save_pdf, delete_Stored_file

router = APIRouter(
    prefix="/api/v1",
    tags=["Documents"]
)
logger = logging.getLogger(__name__)


@router.post(
    "/projects/{project_id}/documents",
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    project_id: UUID,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = UUID(str(current_user["id"]))

    # 1. Verify that the user can access this project.
    project_query = text("""
        SELECT p.id
        FROM projects p
        WHERE
            p.id = :project_id
            AND p.archived_at IS NULL
            AND (
                p.owner_user_id = :user_id
                OR p.organisation_id IN (
                    SELECT om.org_id
                    FROM organisation_members om
                    WHERE om.user_id = :user_id
                )
            )
    """)

    project = db.execute(
        project_query,
        {
            "project_id": project_id,
            "user_id": user_id,
        },
    ).mappings().first()

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found."
        )

    # 2. Validate and save the original file.
    stored_file = await save_pdf(project_id, file)

    try:
        # 3. Create the document metadata record.
        document = Document(
            project_id=project_id,
            uploaded_by_user_id=user_id,
            filename=stored_file["filename"],
            storage_key=stored_file["storage_key"],
            mime_type=stored_file["mime_type"],
            size_bytes=stored_file["size_bytes"],
            checksum=stored_file["checksum"],
            status="uploaded",
            metadata_={},
        )

        db.add(document)
        db.commit()
        db.refresh(document)

        # 4. Return the document information.
        return {
            "message": "Document uploaded successfully.",
            "data": {
                "id": str(document.id),
                "project_id": str(document.project_id),
                "filename": document.filename,
                "mime_type": document.mime_type,
                "size_bytes": document.size_bytes,
                "status": document.status,
                "created_at": document.created_at,
            },
        }

    except Exception:
        db.rollback()

        # Remove the saved file if its database record could not be created.
        try:
            delete_stored_file(stored_file["storage_key"])
        except Exception:
            logger.exception("Failed to clean up uploaded file.")

        logger.exception("Failed to create document record.")

        raise HTTPException(
            status_code=500,
            detail="Unable to save document metadata."
        )