
import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

def save_document_chunks(
        db: Session,
        document_id: UUID,
        chunks: list[dict]

) -> list[dict]:
    query = text(
        """
            INSERT INTO document_chunks (
            document_id,
            chunk_index,
            content,
            page_start,
            page_end,
            metadata
        )
        VALUES (
            :document_id,
            :chunk_index,
            :content,
            :page_start,
            :page_end,
            CAST(:metadata AS JSONB)
        )
        RETURNING id
        """
    )
    saved_chunks = []
    try:
        for chunk in chunks:
            result = db.execute(
                query,
                {
                    "document_id": document_id,
                    "chunk_index": chunk["chunk_index"],
                    "content": chunk["content"],
                    "page_start": chunk["page_start"],
                    "page_end": chunk["page_end"],
                    "metadata": json.dumps(chunk["metadata"])
                }
            ).mappings().one()

            saved_chunks.append({
                **chunk,
                "id": result["id"]
            })
        db.commit()
        return saved_chunks
    except Exception:
        db.rollback()
        raise
            