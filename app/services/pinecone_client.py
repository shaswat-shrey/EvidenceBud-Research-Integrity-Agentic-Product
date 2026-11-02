import os
from pinecone import Pinecone

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv(
    "PINECONE_INDEX_NAME",
    "evidbud-chunks"
)
if not PINECONE_API_KEY:
    raise RuntimeError("PINECONE_API_KEY is missing.")
pc = Pinecone(api_key=PINECONE_API_KEY)

def get_pinecone_index():
    return pc.index(PINECONE_INDEX_NAME)