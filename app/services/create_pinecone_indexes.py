
import os
from pinecone import Pinecone, SchemaBuilder
from dotenv import load_dotenv
load_dotenv()

pc = Pinecone(
    api_key=os.environ["PINECONE_API_KEY"]
)
INDEX_NAME = "evidbud-chunks"
schema = (
    SchemaBuilder()
    .add_string_field(
        "chunk_text",
        embed=True
    )
    .build()
)
existing_indexes = pc.indexes.list()

if INDEX_NAME not in [
    index.name for index in existing_indexes
]:
    pc.indexes.create(
        name=INDEX_NAME,
        schema=schema,
        deployment={
            "deployment_type": "managed",
            "cloud": "aws",
            "region": "us-east-1"
        }
    )
    print(f"Index '{INDEX_NAME}' created successfully.")
else:
    print(f"Index '{INDEX_NAME}' already exists.")
