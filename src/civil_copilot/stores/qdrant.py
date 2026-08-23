"""Qdrant adapter for vector-searchable document chunks."""

from __future__ import annotations

import hashlib
import math
import re
import uuid
from typing import Protocol

from openai import OpenAI
from qdrant_client import QdrantClient, models

from civil_copilot.data.models import DocumentChunk
from civil_copilot.stores.base import WriteStats, model_fingerprint


class EmbeddingProvider(Protocol):
    dimension: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class DeterministicEmbedding:
    """Offline token-hashing vectors for tests; production can use OpenAI embeddings."""

    dimension = 128

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in re.findall(r"[a-z0-9-]+", text.lower()):
            digest = hashlib.sha256(token.encode()).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            vector[index] += 1.0 if digest[4] % 2 else -1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class OpenAIEmbedding:
    dimension = 1536

    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class QdrantSearchStore:
    def __init__(
        self,
        url: str,
        embedding: EmbeddingProvider,
        api_key: str | None = None,
        collection_name: str = "civil_copilot_chunks",
    ) -> None:
        self.client = QdrantClient(url=url, api_key=api_key or None)
        self.embedding = embedding
        self.collection_name = collection_name
        self.initialize()

    def initialize(self) -> None:
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=self.embedding.dimension,
                    distance=models.Distance.COSINE,
                ),
            )

    @staticmethod
    def point_id(chunk_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"civil-copilot:{chunk_id}"))

    def upsert_chunks(self, chunks: list[DocumentChunk]) -> WriteStats:
        if not chunks:
            return WriteStats()
        point_ids = [self.point_id(chunk.chunk_id) for chunk in chunks]
        existing_points = self.client.retrieve(
            collection_name=self.collection_name,
            ids=point_ids,
            with_payload=True,
            with_vectors=False,
        )
        existing = {
            str(point.id): (point.payload or {}).get("content_hash") for point in existing_points
        }
        created = updated = unchanged = 0
        changed: list[DocumentChunk] = []
        for chunk, point_id in zip(chunks, point_ids, strict=True):
            fingerprint = model_fingerprint(chunk)
            if point_id not in existing:
                created += 1
                changed.append(chunk)
            elif existing[point_id] == fingerprint:
                unchanged += 1
            else:
                updated += 1
                changed.append(chunk)

        for start in range(0, len(changed), 64):
            batch = changed[start : start + 64]
            vectors = self.embedding.embed_documents([chunk.text for chunk in batch])
            self.client.upsert(
                collection_name=self.collection_name,
                wait=True,
                points=[
                    models.PointStruct(
                        id=self.point_id(chunk.chunk_id),
                        vector=vector,
                        payload={
                            **chunk.model_dump(mode="json"),
                            "content_hash": model_fingerprint(chunk),
                        },
                    )
                    for chunk, vector in zip(batch, vectors, strict=True)
                ],
            )
        return WriteStats(created, updated, unchanged)

    def count(self) -> int:
        return int(self.client.count(self.collection_name, exact=True).count)

    def search(self, query: str, limit: int = 20) -> list[tuple[str, float]]:
        result = self.client.query_points(
            collection_name=self.collection_name,
            query=self.embedding.embed_query(query),
            limit=limit,
            with_payload=True,
        )
        return [
            (str((point.payload or {})["chunk_id"]), float(point.score)) for point in result.points
        ]

    def clear(self) -> None:
        if self.client.collection_exists(self.collection_name):
            self.client.delete_collection(self.collection_name)
        self.initialize()
