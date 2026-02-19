import json
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from app.config import settings
from app.models.knowledge_item import KnowledgeItem
from app.utils.logging import logger


class VectorStore:
    def __init__(self) -> None:
        self.index_path = Path(settings.vector_index_path)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

        self.dimension = settings.embedding_dimension
        self.index = self._load_or_create_index()
        self.id_map: dict[int, int] = {}
        self._load_id_map()

    def _load_or_create_index(self):
        if self.index_path.exists():
            logger.info(f"Loading existing FAISS index from {self.index_path}")
            index = faiss.read_index(str(self.index_path))
            return index
        else:
            logger.info(f"Creating new FAISS index with dimension {self.dimension}")
            return faiss.IndexFlatL2(self.dimension)

    def _load_id_map(self):
        map_path = self.index_path.with_suffix(".json")
        if map_path.exists():
            with open(map_path) as f:
                self.id_map = json.load(f)
            logger.info(f"Loaded ID map with {len(self.id_map)} entries")

    def _save_id_map(self):
        map_path = self.index_path.with_suffix(".json")
        with open(map_path, "w") as f:
            json.dump(self.id_map, f)

    def add(self, item: KnowledgeItem, embedding: list[float]) -> None:
        if not embedding:
            logger.warning(f"No embedding for item {item.id}, skipping")
            return

        vector = np.array([embedding], dtype=np.float32)
        faiss_id = self.index.ntotal

        self.index.add(vector)
        self.id_map[faiss_id] = item.id
        self._save_id_map()

        logger.debug(f"Added vector for item {item.id} as FAISS ID {faiss_id}")

    def add_batch(self, items: list[KnowledgeItem], embeddings: list[list[float]]) -> None:
        if not items or not embeddings:
            return

        vectors = np.array(embeddings, dtype=np.float32)
        start_id = self.index.ntotal

        self.index.add(vectors)

        for i, item in enumerate(items):
            self.id_map[start_id + i] = item.id

        self._save_id_map()
        logger.info(f"Added {len(items)} vectors to index")

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        if not query_embedding:
            return []

        query_vector = np.array([query_embedding], dtype=np.float32)
        distances, indices = self.index.search(query_vector, top_k)

        results = []
        for distance, faiss_id in zip(distances[0], indices[0], strict=False):
            if faiss_id == -1:
                continue
            item_id = self.id_map.get(faiss_id)
            if item_id:
                results.append({"item_id": item_id, "distance": float(distance)})

        logger.debug(f"Found {len(results)} results for query")
        return results

    def save(self) -> None:
        faiss.write_index(self.index, str(self.index_path))
        self._save_id_map()
        logger.info(f"Saved FAISS index to {self.index_path}")

    def delete(self, item_id: int) -> bool:
        faiss_id = None
        for fid, iid in self.id_map.items():
            if iid == item_id:
                faiss_id = fid
                break

        if faiss_id is None:
            return False

        del self.id_map[faiss_id]
        self._save_id_map()
        logger.info(f"Deleted item {item_id} from vector store")
        return True
