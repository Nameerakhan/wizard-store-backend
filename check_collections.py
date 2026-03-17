import chromadb

client = chromadb.PersistentClient(path='./chroma_db')
collections = client.list_collections()
print(f"\nFound {len(collections)} collection(s):")
for c in collections:
    print(f"  - {c.name}")
    count = c.count()
    print(f"    Documents: {count}")
