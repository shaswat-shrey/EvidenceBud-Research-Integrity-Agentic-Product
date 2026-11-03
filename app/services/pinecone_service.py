from app.services.pinecone_client import get_pinecone_index

BATCH_SIZE = 50

def index_document_chunks(
        project_id, 
        document_id, 
        chunks: list[dict]
):
    index = get_pinecone_index()
    namespace = str(project_id)
    record = []
    for chunk in chunks:
        record.append({
            "_id": str(chunk["id"]),
            "chunk_text": chunk["content"],

            "document_id": str(document_id),
            "project_id": str(project_id),

            "chunk_index": chunk["chunk_index"],
            "page_start": chunk["page_start"],
            "page_end": chunk["page_end"],
        })
    total_indexed = 0
    for start in range(0, len(record), BATCH_SIZE):
        batch = record[start: start+BATCH_SIZE]
        response = index.documents.upsert(
            namespace=namespace,
            documents=batch
        )

        total_indexed += response.upserted_count
    return {
        "total_chunks": len(chunks),
        "indexed_chunks": total_indexed
    }