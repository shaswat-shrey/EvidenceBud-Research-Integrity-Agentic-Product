from sqlalchemy import text

project_exist_access_query = text(
    """
        SELECT p.id
        FROM projects p
        WHERE p.id = :project_id
        AND p.archived_at IS NULL
        AND (
            p.owner_user_id = :user_id
            OR p.organisation_id IN (
                SELECT om.org_id 
                FROM organisation_members om
                WHERE om.user_id = :user_id
            )
        )
    """
)
docs_fetch_query = text(
        """
            SELECT
                id,
                project_id,
                uploaded_by_user_id,
                filename,
                mime_type,
                size_bytes,
                checksum,
                status,
                created_at,
                updated_at
            FROM documents
            WHERE project_id = :project_id
            AND deleted_at IS NULL
            ORDER BY created_at DESC
        """
    )