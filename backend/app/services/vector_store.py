# Copyright (c) 2026 Jinan Kordab
# SPDX-License-Identifier: MIT

"""
FAISS Vector Store Service [J7]
================================
Tier-1 in-memory vector evidence cache.
Used for:
  - Semantic near-duplicate detection (cosine similarity > 0.95)
  - Previously verified claim lookup (cosine similarity > 0.92)
  - VERIFAID offline pipeline evidence enrichment (Loop 2)

Uses FAISS IndexFlatIP (inner product = cosine similarity for L2-normalized vectors).
"""

import numpy as np
from pathlib import Path
from typing import Optional, List, Tuple

from app.core.config import settings

def _get_faiss():
    """Lazy-import FAISS to avoid OpenMP hang in container environments."""
    import faiss
    return faiss


class FAISSStore:
    """In-memory FAISS vector index for evidence cache and semantic dedup."""

    def __init__(self):
        self.index = None  # faiss.IndexFlatIP — lazy-loaded
        self.dimension: int = settings.FAISS_DIMENSION
        self.id_to_metadata: dict[int, dict] = {}  # FAISS internal ID → metadata
        self.next_id: int = 0

    def initialize(self):
        """Create or load the FAISS index."""
        try:
            faiss = _get_faiss()
            index_path = Path(settings.FAISS_INDEX_PATH)
            if index_path.exists():
                self.index = faiss.read_index(str(index_path))
                self.dimension = self.index.d
                self.next_id = self.index.ntotal
                print(f"FAISS index loaded: {index_path} ({self.index.ntotal} vectors)")
            else:
                self.index = faiss.IndexFlatIP(self.dimension)
                print(f"FAISS index created: dim={self.dimension} (empty)")
        except Exception as e:
            print(f"WARNING: FAISS initialization failed ({e}). Running without vector index.")

    def _normalize(self, vectors: np.ndarray) -> np.ndarray:
        """L2-normalize vectors for cosine similarity via inner product."""
        faiss = _get_faiss()
        faiss.normalize_L2(vectors)
        return vectors

    def add_vectors(
        self, vectors: np.ndarray, metadata_list: List[dict]
    ) -> List[int]:
        """Add normalized vectors with metadata to the index. Returns FAISS IDs."""
        vectors = vectors.astype("float32")
        vectors = self._normalize(vectors)
        ids = list(range(self.next_id, self.next_id + len(vectors)))
        self.index.add(vectors)
        for faiss_id, meta in zip(ids, metadata_list):
            self.id_to_metadata[faiss_id] = meta
        self.next_id += len(vectors)
        return ids

    def search(
        self, query_vector: np.ndarray, k: int = 5
    ) -> List[Tuple[float, int, dict]]:
        """Search for k nearest neighbors. Returns [(similarity, faiss_id, metadata), ...]."""
        if self.index is None or self.index.ntotal == 0:
            return []
        query_vector = query_vector.astype("float32").reshape(1, -1)
        query_vector = self._normalize(query_vector)
        distances, indices = self.index.search(query_vector, k)
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1:  # No result
                continue
            meta = self.id_to_metadata.get(int(idx), {})
            results.append((float(dist), int(idx), meta))
        return results

    def find_semantic_duplicate(
        self, query_vector: np.ndarray
    ) -> Optional[dict]:
        """
        Check if a semantically near-duplicate claim exists.
        Returns cached verdict metadata if cosine similarity > threshold.
        """
        results = self.search(query_vector, k=1)
        if results and results[0][0] >= settings.FAISS_CACHE_THRESHOLD:
            return results[0][2]  # metadata of the nearest match
        return None

    def save(self):
        """Persist index to disk."""
        if self.index is not None:
            faiss = _get_faiss()
            path = Path(settings.FAISS_INDEX_PATH)
            path.parent.mkdir(parents=True, exist_ok=True)
            faiss.write_index(self.index, str(path))
            print(f"FAISS index saved: {path} ({self.index.ntotal} vectors)")

    def __len__(self) -> int:
        return self.index.ntotal if self.index else 0


# Singleton
faiss_store = FAISSStore()
