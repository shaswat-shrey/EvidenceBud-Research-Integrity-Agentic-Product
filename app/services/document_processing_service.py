
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID
from fastapi import Depends
from app.database import SessionLocal
from app.models.documents import Document
from app.services.file_storage import STORAGE_PATH
from app.services.pdf_processor import extract_and_chunk_pdf
from app.services.document_chunk_service import save_document_chunks
from app.services.pinecone_service import index_document_chunks
from app.database import get_db
from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)


def process_document(document_id: UUID) -> None:
    """
    Extract, chunk, persist and index an uploaded PDF.
    Uses its own database session.
    """
    db = SessionLocal()
    try:
        # 1. Fetch the document
        document = (
            db.query(Document)
            .filter(
                Document.id == document_id,
                Document.deleted_at.is_(None)
            )
            .with_for_update()
            .first()
        )
        if document is None:
            logger.warning(
                "Document %s does not exist.", document_id
            )
            return
        if document.status == "indexed":
            logger.info(
                "Document %s is already indexed.", document_id
            )
            return

        # 2. Update document status
        document.status = "processing"
        document.error_message = None
        db.commit()

        # 3. Resolve and validate the original PDF path
        documents_root = (STORAGE_PATH / "documents").resolve()
        file_path = (STORAGE_PATH / document.storage_key).resolve()

        if not file_path.is_relative_to(documents_root):
            raise ValueError("Invalid document storage path.")

        if not file_path.is_file():
            raise FileNotFoundError("Stored PDF file not found.")

        # 4. Extract text and create chunks
        chunks = extract_and_chunk_pdf(file_path)

        if not chunks:
            raise ValueError(
                "No extractable text found in the PDF. "
                "The document may be scanned or empty."
            )
        logger.info(
            "Extracted %s chunks from document %s.",
            len(chunks),
            document_id
        )
        # 5. Save chunks in PostgreSQL
        saved_chunks = save_document_chunks(
            db=db,
            document_id=document.id,
            chunks=chunks
        )
        # 6. Index chunks in Pinecone
        indexing_result = index_document_chunks(
            project_id=document.project_id,
            document_id=document.id,
            chunks=saved_chunks
        )

        if indexing_result["indexed_chunks"] != len(saved_chunks):
            raise RuntimeError(
                "Pinecone indexing did not complete successfully."
            )
        # 7. Mark document as indexed
        document.status = "indexed"
        document.error_message = None
        document.processed_at = datetime.now(timezone.utc)

        db.commit()

        logger.info(
            "Document %s successfully indexed. Total chunks: %s",
            document_id,
            len(saved_chunks)
        )

    except Exception as exc:
        db.rollback()

        logger.exception(
            "Document processing failed for %s.",
            document_id
        )

        # 8. Mark document as failed
        try:
            document = (
                db.query(Document)
                .filter(Document.id == document_id)
                .first()
            )

            if document is not None:
                document.status = "failed"
                document.error_message = str(exc)[:2000]
                db.commit()

        except Exception:
            db.rollback()
            logger.exception(
                "Could not update failed status for document %s.",
                document_id
            )

    finally:
        db.close()
