"""
Vector store abstraction layer for Wizard Store AI.

Supports two backends:
  - ChromaVectorStore: local persistent ChromaDB (default for development)
  - QdrantVectorStore: Qdrant Cloud (used in production)

Selection via env var: VECTOR_STORE=chroma (default) | qdrant
"""

import os
import uuid
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

logger = logging.getLogger("wizard_store.vector_store")

_DEFAULT_CHROMA_PATH = str(Path(__file__).parent.parent / 'database' / 'chroma_db')


@dataclass
class VectorResult:
    id: str
    text: str
    metadata: dict
    distance: float


@dataclass
class VectorDocument:
    id: str
    text: str
    embedding: list
    metadata: dict = field(default_factory=dict)


@runtime_checkable
class VectorStore(Protocol):
    def search(
        self, collection: str, query_vector: list, top_k: int, filters: dict | None = None
    ) -> list[VectorResult]: ...

    def upsert(self, collection: str, documents: list[VectorDocument]) -> None: ...

    def delete(self, collection: str, ids: list[str]) -> None: ...

    def count(self, collection: str) -> int: ...

    def reset_collection(self, collection: str) -> None: ...


# ── ChromaDB implementation ────────────────────────────────────────────────────

class ChromaVectorStore:
    """Wraps local ChromaDB. Behaviour identical to the original implementation."""

    def __init__(self, db_path: str):
        import chromadb
        self._db_path = db_path
        self._client = chromadb.PersistentClient(path=db_path)
        self._cache: dict = {}

    def _get_collection(self, name: str):
        if name not in self._cache:
            self._cache[name] = self._client.get_collection(name=name)
        return self._cache[name]

    def search(
        self, collection: str, query_vector: list, top_k: int, filters: dict | None = None
    ) -> list[VectorResult]:
        col = self._get_collection(collection)
        results = col.query(query_embeddings=[query_vector], n_results=top_k)
        docs = []
        for i in range(len(results['ids'][0])):
            docs.append(VectorResult(
                id=results['ids'][0][i],
                text=results['documents'][0][i],
                metadata=results['metadatas'][0][i],
                distance=results['distances'][0][i],
            ))
        return docs

    def upsert(self, collection: str, documents: list[VectorDocument]) -> None:
        col = self._get_collection(collection)
        col.add(
            ids=[d.id for d in documents],
            documents=[d.text for d in documents],
            embeddings=[d.embedding for d in documents],
            metadatas=[d.metadata for d in documents],
        )

    def delete(self, collection: str, ids: list[str]) -> None:
        col = self._get_collection(collection)
        col.delete(ids=ids)

    def count(self, collection: str) -> int:
        return self._get_collection(collection).count()

    def reset_collection(self, collection: str) -> None:
        """Delete and recreate the collection (used by ingest to rebuild from scratch)."""
        try:
            self._client.delete_collection(name=collection)
        except Exception:
            pass
        self._client.create_collection(name=collection)
        self._cache.pop(collection, None)


# ── Qdrant implementation ──────────────────────────────────────────────────────

def _to_qdrant_id(str_id: str) -> str:
    """Convert any string ID to a deterministic UUID for Qdrant (requires UUID or uint64)."""
    return str(uuid.uuid5(uuid.NAMESPACE_OID, str_id))


class QdrantVectorStore:
    """Wraps Qdrant Cloud. Used in production when VECTOR_STORE=qdrant."""

    _VECTOR_SIZE = 1536  # text-embedding-3-small

    def __init__(self, url: str, api_key: str, collection_name: str):
        from qdrant_client import QdrantClient
        self._client = QdrantClient(url=url, api_key=api_key)
        self._default_collection = collection_name

    def _ensure_collection(self, collection: str) -> None:
        from qdrant_client.models import Distance, VectorParams
        existing = {c.name for c in self._client.get_collections().collections}
        if collection not in existing:
            logger.info("Creating Qdrant collection '%s'", collection)
            self._client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=self._VECTOR_SIZE, distance=Distance.COSINE),
            )

    def search(
        self, collection: str, query_vector: list, top_k: int, filters: dict | None = None
    ) -> list[VectorResult]:
        results = self._client.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=top_k,
        )
        return [
            VectorResult(
                id=hit.payload.get('original_id', str(hit.id)),
                text=hit.payload.get('text', ''),
                metadata=hit.payload.get('metadata', {}),
                # Qdrant returns cosine similarity (1 = identical); convert to distance
                distance=1.0 - hit.score,
            )
            for hit in results
        ]

    def upsert(self, collection: str, documents: list[VectorDocument]) -> None:
        from qdrant_client.models import PointStruct
        self._ensure_collection(collection)
        points = [
            PointStruct(
                id=_to_qdrant_id(d.id),
                vector=d.embedding,
                payload={'original_id': d.id, 'text': d.text, 'metadata': d.metadata},
            )
            for d in documents
        ]
        self._client.upsert(collection_name=collection, points=points)

    def delete(self, collection: str, ids: list[str]) -> None:
        from qdrant_client.models import PointIdsList
        qdrant_ids = [_to_qdrant_id(id_) for id_ in ids]
        self._client.delete(
            collection_name=collection,
            points_selector=PointIdsList(points=qdrant_ids),
        )

    def count(self, collection: str) -> int:
        return self._client.count(collection_name=collection).count

    def reset_collection(self, collection: str) -> None:
        from qdrant_client.models import Distance, VectorParams
        try:
            self._client.delete_collection(collection_name=collection)
        except Exception:
            pass
        self._client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=self._VECTOR_SIZE, distance=Distance.COSINE),
        )


# ── Factory ────────────────────────────────────────────────────────────────────

def get_vector_store(db_path: str | None = None) -> ChromaVectorStore | QdrantVectorStore:
    """
    Return the configured vector store backend.

    Reads VECTOR_STORE env var: "chroma" (default) or "qdrant".
    """
    store_type = os.getenv('VECTOR_STORE', 'chroma').lower()

    if store_type == 'qdrant':
        url = os.getenv('QDRANT_URL', '')
        api_key = os.getenv('QDRANT_API_KEY', '')
        collection_name = os.getenv('QDRANT_COLLECTION_NAME', 'wizard_store')
        if not url:
            raise RuntimeError("QDRANT_URL must be set when VECTOR_STORE=qdrant")
        logger.info("Using QdrantVectorStore at %s", url)
        return QdrantVectorStore(url=url, api_key=api_key, collection_name=collection_name)

    resolved_path = db_path or _DEFAULT_CHROMA_PATH
    logger.info("Using ChromaVectorStore at %s", resolved_path)
    return ChromaVectorStore(db_path=resolved_path)
