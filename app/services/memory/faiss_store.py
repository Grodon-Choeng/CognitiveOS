import json
from pathlib import Path

import faiss
import numpy as np

from app.config import settings
from app.utils import logger


class MemoryFAISSStore:
    def __init__(self) -> None:
        self.index_path = Path(settings.memory_vector_index_path)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.dimension = settings.embedding_dimension
        self.index = self._load_or_create()
        self.id_map: dict[int, int] = {}
        self._load_id_map()

    def _load_or_create(self):
        if self.index_path.exists():
            logger.info(f"Loading memory FAISS index from {self.index_path}")
            return faiss.read_index(str(self.index_path))

        logger.info(f"Creating memory FAISS index with dimension {self.dimension}")
        return faiss.IndexFlatIP(self.dimension)

    def _id_map_path(self) -> Path:
        return self.index_path.with_suffix(".ids.json")

    def _load_id_map(self) -> None:
        path = self._id_map_path()
        if not path.exists():
            return

        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.id_map = {int(k): int(v) for k, v in data.items()}

    def _save_id_map(self) -> None:
        with open(self._id_map_path(), "w", encoding="utf-8") as f:
            json.dump(self.id_map, f)

    @staticmethod
    def _normalize(vector: list[float]) -> np.ndarray:
        arr = np.array([vector], dtype=np.float32)
        faiss.normalize_L2(arr)
        return arr

    def add(self, memory_id: int, embedding: list[float]) -> int:
        vector_id = int(self.index.ntotal)
        self.index.add(self._normalize(embedding))
        self.id_map[vector_id] = memory_id
        self._save_id_map()
        return vector_id

    def search(self, query_embedding: list[float], top_k: int = 8) -> list[dict[str, float | int]]:
        if self.index.ntotal == 0:
            return []

        distances, indices = self.index.search(self._normalize(query_embedding), top_k)
        results: list[dict[str, float | int]] = []

        for score, vector_id in zip(distances[0], indices[0], strict=False):
            if vector_id == -1:
                continue
            memory_id = self.id_map.get(int(vector_id))
            if memory_id is None:
                continue
            results.append(
                {
                    "memory_id": int(memory_id),
                    "vector_id": int(vector_id),
                    "similarity": float(score),
                }
            )

        return results

    def save(self) -> None:
        faiss.write_index(self.index, str(self.index_path))
        self._save_id_map()
