"""
Migrate all documents from local ChromaDB to Qdrant Cloud.

Usage:
  cd backend
  python scripts/migrate_chroma_to_qdrant.py

Prerequisites:
  - QDRANT_URL and QDRANT_API_KEY set in .env
  - QDRANT_COLLECTION_NAME set (default: wizard_store)
  - Local ChromaDB populated (run ingest first if not)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import os
import chromadb
from app.services.vector_store import QdrantVectorStore, VectorDocument, _DEFAULT_CHROMA_PATH

_COLLECTION = os.getenv('QDRANT_COLLECTION_NAME', 'wizard_store')


def main():
    # 1. Read from ChromaDB
    print("Reading documents from ChromaDB...")
    chroma_client = chromadb.PersistentClient(path=_DEFAULT_CHROMA_PATH)
    chroma_col = chroma_client.get_collection(name=_COLLECTION)
    results = chroma_col.get(include=['documents', 'embeddings', 'metadatas'])

    ids = results['ids']
    texts = results['documents']
    embeddings = results['embeddings']
    metadatas = results['metadatas']
    chroma_count = len(ids)
    print(f"ChromaDB: {chroma_count} documents")

    if chroma_count == 0:
        print("No documents found. Run 'python -m app.services.ingest' first.")
        return

    # 2. Connect to Qdrant
    url = os.getenv('QDRANT_URL', '')
    api_key = os.getenv('QDRANT_API_KEY', '')
    if not url:
        print("QDRANT_URL not set. Add it to .env and try again.")
        return

    print(f"Connecting to Qdrant at {url}...")
    store = QdrantVectorStore(url=url, api_key=api_key, collection_name=_COLLECTION)

    # 3. Reset and upsert
    print(f"Resetting Qdrant collection '{_COLLECTION}'...")
    store.reset_collection(_COLLECTION)

    docs = [
        VectorDocument(
            id=ids[i],
            text=texts[i],
            embedding=embeddings[i],
            metadata=metadatas[i],
        )
        for i in range(chroma_count)
    ]

    print(f"Upserting {chroma_count} documents to Qdrant...")
    store.upsert(_COLLECTION, docs)

    # 4. Verify counts
    qdrant_count = store.count(_COLLECTION)
    status = "✓" if qdrant_count == chroma_count else "✗ MISMATCH"
    print(f"\nChromaDB: {chroma_count} documents → Qdrant: {qdrant_count} documents {status}")


if __name__ == '__main__':
    main()
