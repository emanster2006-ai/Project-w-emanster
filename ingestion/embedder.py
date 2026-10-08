"""
Embedding generation with L2 normalization.
L2-normalized vectors enable dot product as a proxy for cosine similarity,
which is significantly faster at scale (no sqrt needed per comparison).
"""

import logging
import os

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

_embedder = None


def get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        model_name = os.getenv(
            "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
        )
        _embedder = SentenceTransformer(model_name)
        logger.info(f"Loaded embedding model: {model_name}")
    return _embedder


def embed_texts(texts: list[str], normalize: bool = True) -> np.ndarray:
    """
    Encode a list of texts into L2-normalized dense vectors.
    normalize=True is critical — enables fast dot-product similarity in Qdrant.
    """
    embedder = get_embedder()
    vectors = embedder.encode(
        texts,
        batch_size=64,
        show_progress_bar=len(texts) > 100,
        normalize_embeddings=normalize,  # L2 normalization applied here
        convert_to_numpy=True,
    )
    return vectors
