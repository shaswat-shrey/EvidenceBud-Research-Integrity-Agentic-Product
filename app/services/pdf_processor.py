import re
from pathlib import Path
import fitz

CHUNK_SIZE = 450
CHUNK_OVERLAP = 75

def extract_and_chunk_pdf(file_path: Path) -> list[dict]:
    """
    Extract text from a PDF and split it into chunks.

    Each chunk retains its original page number and
    character offsets within that page.
    """
    if not file_path.exists():
        raise FileNotFoundError("PDF file not found")

    chunks = []
    chunk_index = 0

    pdf = fitz.open(file_path)
    try:
        for page_number, page in enumerate(pdf, start=1):
            page_text = page.get_text("text")
            if not page_text.strip():
                continue
            words = list(re.finditer(r"\S+", page_text))

            if not words:
                continue
            start = 0

            while start < len(words):
                end = min(start + CHUNK_SIZE, len(words))

                start_offset = words[start].start()
                end_offset = words[end - 1].end()
                chunk_text = page_text[start_offset:end_offset].strip()
                if chunk_text:
                    chunks.append({
                        "chunk_index": chunk_index,
                        "content": chunk_text,
                        "page_start": page_number,
                        "page_end": page_number,
                        "metadata": {
                            "page_number": page_number,
                            "char_start": start_offset,
                            "char_end": end_offset,
                        }
                    })
                    chunk_index += 1

                if end == len(words):
                    break
                start = end - CHUNK_OVERLAP

    finally:
        pdf.close()
    return chunks

