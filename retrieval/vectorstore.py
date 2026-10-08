"""
Qdrant vector store client — upsert, dense search, sparse search.
"""

import logging
import os
import uuid

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    SparseVectorParams,
    VectorParams,
)

from ingestion.embedder import embed_texts

logger = logging.getLogger(__name__)

COLLECTION = os.getenv("QDRANT_COLLECTION_NAME", "financebench")
DENSE_DIM = 384  # all-MiniLM-L6-v2 output dimension

_client = None


def get_vectorstore() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(
            url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            api_key=os.getenv("QDRANT_API_KEY") or None,
        )
        _ensure_collection(_client)
    return _client


def _ensure_collection(client: QdrantClient):
    """Create collection with both dense and sparse vector support."""
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION not in existing:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config={
                "dense": VectorParams(size=DENSE_DIM, distance=Distance.DOT)
            },
            sparse_vectors_config={"sparse": SparseVectorParams()},
        )
        logger.info(f"Created Qdrant collection: {COLLECTION}")


def upsert_nodes(nodes: list, batch_size: int = 100):
    """
    Upsert LlamaIndex nodes into Qdrant.
    Generates dense embeddings; sparse vectors populated separately in hybrid.py
    """
    client = get_vectorstore()
    texts = [n.get_content() for n in nodes]
    dense_vecs = embed_texts(texts, normalize=True)  # L2 normalized

    points = []
    for i, (node, vec) in enumerate(zip(nodes, dense_vecs)):
        points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector={"dense": vec.tolist()},
                payload={
                    "text": node.get_content(),
                    **node.metadata,
                },
            )
        )

    # Batch upsert
    for i in range(0, len(points), batch_size):
        client.upsert(collection_name=COLLECTION, points=points[i : i + batch_size])

    logger.info(f"Upserted {len(points)} vectors into Qdrant")


def dense_search(
    query_vec: np.ndarray, top_k: int = 20, filters: dict | None = None
) -> list[dict]:
    """Dense similarity search with optional metadata pre-filtering."""
    client = get_vectorstore()

    qdrant_filter = None
    if filters:
        conditions = [
            FieldCondition(key=k, match=MatchValue(value=v)) for k, v in filters.items()
        ]
        qdrant_filter = Filter(must=conditions)

    results = client.search(
        collection_name=COLLECTION,
        query_vector=("dense", query_vec.tolist()),
        query_filter=qdrant_filter,
        limit=top_k,
        with_payload=True,
    )

    return [
        {"text": r.payload.get("text", ""), "metadata": r.payload, "score": r.score}
        for r in results
    ]
