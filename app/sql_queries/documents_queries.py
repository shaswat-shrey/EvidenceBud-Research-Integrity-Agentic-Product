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

fetch_document_query = text("""
        SELECT
            d.id,
            d.project_id,
            d.uploaded_by_user_id,
            d.filename,
            d.mime_type,
            d.size_bytes,
            d.checksum,
            d.status,
            d.created_at,
            d.updated_at
        FROM documents d
        JOIN projects p
            ON p.id = d.project_id
        WHERE
            d.id = :document_id
            AND d.deleted_at IS NULL
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

delete_document_query = text(
    """
        DELETE FROM documents AS d
        USING projects AS p
        WHERE
            d.id = :document_id
            AND d.project_id = p.id
            AND d.deleted_at IS NULL
            AND p.archived_at IS NULL
            AND (
                p.owner_user_id = :user_id
                OR p.organisation_id IN (
                    SELECT om.org_id
                    FROM organisation_members as om
                    WHERE om.user_id = :user_id
                )
            )
        RETURNING d.id, d.filename, d.storage_key
    """
    )