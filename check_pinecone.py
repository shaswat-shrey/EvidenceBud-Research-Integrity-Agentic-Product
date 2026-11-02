from app.services.pinecone_client import pc, PINECONE_INDEX_NAME

print("Configured index:", PINECONE_INDEX_NAME)

indexes = pc.list_indexes()

print("\nAvailable indexes:")

for index in indexes:
    print(index["name"])