import os
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()
pc = Pinecone(
    api_key=os.environ["PINECONE_API_KEY"]
)

PINECONE_INDEX_NAME = os.getenv(
    "PINECONE_INDEX_NAME",
    "evidenceos-chunks"
)
def get_pinecone_index():
    return pc.Index(PINECONE_INDEX_NAME)