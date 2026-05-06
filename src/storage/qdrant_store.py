from __future__ import annotations

import uuid
from time import sleep
from typing import Iterable

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from src.models import ChunkRecord, RetrievalHit


class QdrantStore:
    def __init__(
        self,
        url: str,
        collection_name: str,
        *,
        timeout_seconds: int = 300,
        upsert_retries: int = 6,
        retry_backoff_seconds: int = 5,
    ) -> None:
        self.client = QdrantClient(url=url, timeout=timeout_seconds)
        self.collection_name = collection_name
        self.upsert_retries = upsert_retries
        self.retry_backoff_seconds = retry_backoff_seconds

    def ensure_collection(self, vector_size: int) -> None:
        collections = {item.name for item in self.client.get_collections().collections}
        if self.collection_name in collections:
            return
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=qmodels.VectorParams(size=vector_size, distance=qmodels.Distance.COSINE),
        )

    def collection_exists(self) -> bool:
        collections = {item.name for item in self.client.get_collections().collections}
        return self.collection_name in collections

    def point_count(self) -> int:
        if not self.collection_exists():
            return 0
        return int(self.client.count(collection_name=self.collection_name, exact=True).count)

    def upsert_chunks(self, chunks: Iterable[ChunkRecord], vectors: list[list[float]]) -> None:
        chunk_list = list(chunks)
        if not chunk_list:
            return
        points = [
            qmodels.PointStruct(
                id=self._point_id(chunk.chunk_id),
                vector=vector,
                payload={
                    "chunk_id": chunk.chunk_id,
                    "document_name": chunk.document_name,
                    "document_path": chunk.document_path,
                    "source_type": chunk.source_type,
                    "text": chunk.text,
                    "chunk_index": chunk.chunk_index,
                    "token_start": chunk.token_start,
                    "token_end": chunk.token_end,
                },
            )
            for chunk, vector in zip(chunk_list, vectors, strict=True)
        ]
        last_error: Exception | None = None
        for attempt in range(self.upsert_retries + 1):
            try:
                self.client.upsert(collection_name=self.collection_name, points=points, wait=True)
                return
            except Exception as exc:
                last_error = exc
                if attempt >= self.upsert_retries:
                    break
                sleep(self.retry_backoff_seconds * (attempt + 1))
        if last_error is not None:
            raise last_error

    @staticmethod
    def _point_id(chunk_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))

    def search(self, query_vector: list[float], discourse: str, top_k: int) -> list[RetrievalHit]:
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=top_k,
            query_filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="source_type",
                        match=qmodels.MatchValue(value=discourse),
                    )
                ]
            ),
            with_payload=True,
            with_vectors=False,
        )
        hits = response.points
        return [
            RetrievalHit(
                chunk_id=str(hit.payload["chunk_id"]),
                document_name=str(hit.payload["document_name"]),
                source_type=str(hit.payload["source_type"]),
                score=float(hit.score),
                text=str(hit.payload["text"]),
                dense_score=float(hit.score),
            )
            for hit in hits
        ]
