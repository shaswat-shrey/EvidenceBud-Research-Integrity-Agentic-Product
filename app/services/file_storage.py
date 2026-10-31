import hashlib
import os
import uuid
from pathlib import Path
from fastapi import HTTPException, UploadFile
from dotenv import load_dotenv
load_dotenv()

STORAGE_PATH = Path(
    os.getenv("STORAGE_ROOT", "./storage")
).resolve()

MAX_FILE_SIZE = 25 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024

async def save_pdf(project_id: uuid.UUID, upload: UploadFile) -> dict:
    """
    Validate and save an uploaded PDF.

    Returns the file metadata required by the documents table.
    """
    original_name = (upload.filename or "documents.pdf").replace("\\", "/")
    original_name = Path(original_name).name

    if not original_name.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=415,
            detail="Only PDFs are supported currently..."
        )
    storage_name = f"{uuid.uuid4()}.pdf"

    relative_key = (
        Path("documents") / str(project_id) / storage_name
    )
    destination = STORAGE_PATH / relative_key
    destination.parent.mkdir(parents=True, exist_ok=True)

    file_hash = hashlib.sha256()
    total_size = 0
    header = b""

    try:
        with destination.open("xb") as stored_file:
            while True:
                chunk = await upload.read(CHUNK_SIZE)
                if not chunk:
                    break
                total_size += len(chunk)

                if total_size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="File exceeds the 25 MB limit."
                    )
                if len(header) < 5:
                    header += chunk[:5 - len(header)]

                file_hash.update(chunk)
                stored_file.write(chunk)

        if total_size == 0:
            raise HTTPException(
                status_code=422,
                detail="The uploaded file is empty."
            )
        
        if header != b"%PDF-":
            raise HTTPException(
                status_code=422,
                detail="The uploaded file does not have a valid PDF signature."
            )

        return {
            "filename": original_name,
            "storage_key": relative_key.as_posix(),
            "mime_type": "application/pdf",
            "size_bytes": total_size,
            "checksum": file_hash.hexdigest(),
        }
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    finally:
        await upload.close()

def delete_Stored_file(storage_key: str) -> None:
    """
    Delete a stored file without allowing paths outside our
    documents storage directory.
    """

    documents_root = (STORAGE_PATH / "documents").resolve()
    target = (STORAGE_PATH / storage_key).resolve()

    if not target.is_relative_to(documents_root):
        raise ValueError("Invalid storage key.")

    target.unlink(missing_ok=True)