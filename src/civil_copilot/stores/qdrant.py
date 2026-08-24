"""Qdrant adapter for vector-searchable document chunks."""

from __future__ import annotations

import hashlib
import math
import re
import uuid
from collections import Counter
from datetime import date
from typing import Protocol

from openai import OpenAI
from qdrant_client import QdrantClient, models

from civil_copilot.data.models import DocumentChunk
from civil_copilot.retrieval.evidence import HybridCandidate
from civil_copilot.retrieval.rerank import extract_identifiers
from civil_copilot.stores.base import WriteStats, model_fingerprint

SAFE_METADATA_KEY = re.compile(r"^[a-zA-Z0-9_.-]+$")
LOCAL_QDRANT_COLLECTION = "civil_copilot_chunks_local_deterministic_v2"
LIVE_QDRANT_COLLECTION = "civil_copilot_chunks_live_openai_v2"
STORE_TIMEOUT_SECONDS = 1
OPENAI_EMBEDDING_TIMEOUT_SECONDS = 2.0


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
        self.client = OpenAI(
            api_key=api_key,
            timeout=OPENAI_EMBEDDING_TIMEOUT_SECONDS,
            max_retries=0,
        )
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
        collection_name: str = "civil_copilot_chunks_v2",
    ) -> None:
        self.client = QdrantClient(
            url=url,
            api_key=api_key or None,
            timeout=STORE_TIMEOUT_SECONDS,
        )
        self.embedding = embedding
        self.collection_name = collection_name
        self.initialize()

    def initialize(self) -> None:
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    "dense": models.VectorParams(
                        size=self.embedding.dimension,
                        distance=models.Distance.COSINE,
                    )
                },
                sparse_vectors_config={
                    "text": models.SparseVectorParams(modifier=models.Modifier.IDF)
                },
            )
        self._validate_vector_schema()
        if type(self.client._client).__module__.startswith("qdrant_client.local"):  # noqa: SLF001
            return
        indexes: dict[str, models.PayloadSchemaType | models.TextIndexParams] = {
            "chunk_id": models.PayloadSchemaType.KEYWORD,
            "record_id": models.PayloadSchemaType.KEYWORD,
            "project_id": models.PayloadSchemaType.KEYWORD,
            "access_scopes": models.PayloadSchemaType.KEYWORD,
            "text": models.TextIndexParams(
                type=models.TextIndexType.TEXT,
                tokenizer=models.TokenizerType.WORD,
                lowercase=True,
            ),
            "effective_date": models.PayloadSchemaType.DATETIME,
        }
        self._validate_payload_schema(indexes, allow_missing=True)
        for field_name, field_schema in indexes.items():
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name=field_name,
                field_schema=field_schema,
                wait=True,
            )
        self._validate_payload_schema(indexes)

    def _incompatible(self, detail: str) -> ValueError:
        return ValueError(
            f"Qdrant collection {self.collection_name!r} is incompatible ({detail}); "
            "reindex into the collection configured for this runtime mode"
        )

    def _validate_vector_schema(self) -> None:
        info = self.client.get_collection(self.collection_name)
        vectors = info.config.params.vectors
        sparse_vectors = info.config.params.sparse_vectors or {}
        if not isinstance(vectors, dict) or set(vectors) != {"dense"}:
            raise self._incompatible("expected exactly the named dense vector")
        dense = vectors["dense"]
        if dense.size != self.embedding.dimension:
            raise self._incompatible(
                f"dense dimension is {dense.size}, expected {self.embedding.dimension}"
            )
        if dense.distance != models.Distance.COSINE:
            raise self._incompatible("dense distance must be cosine")
        if set(sparse_vectors) != {"text"}:
            raise self._incompatible("expected exactly the named text sparse vector")
        if sparse_vectors["text"].modifier != models.Modifier.IDF:
            raise self._incompatible("text sparse vector must use the IDF modifier")

    def _validate_payload_schema(
        self,
        expected: dict[str, models.PayloadSchemaType | models.TextIndexParams],
        *,
        allow_missing: bool = False,
    ) -> None:
        payload_schema = self.client.get_collection(self.collection_name).payload_schema
        missing = sorted(set(expected) - set(payload_schema))
        if missing and not allow_missing:
            raise self._incompatible(f"missing payload indexes: {', '.join(missing)}")
        for field_name, configured in expected.items():
            if field_name not in payload_schema:
                continue
            actual_type = payload_schema[field_name].data_type
            expected_type = (
                models.PayloadSchemaType.TEXT
                if isinstance(configured, models.TextIndexParams)
                else configured
            )
            if actual_type != expected_type:
                raise self._incompatible(
                    f"payload index {field_name!r} is {actual_type}, expected {expected_type}"
                )
            if isinstance(configured, models.TextIndexParams):
                actual_params = payload_schema[field_name].params
                if not isinstance(actual_params, models.TextIndexParams):
                    raise self._incompatible(
                        f"payload text index {field_name!r} has no text configuration"
                    )
                if (
                    actual_params.tokenizer != configured.tokenizer
                    or actual_params.lowercase != configured.lowercase
                ):
                    raise self._incompatible(
                        f"payload text index {field_name!r} tokenizer/lowercase differs"
                    )

    @staticmethod
    def point_id(chunk_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"civil-copilot:{chunk_id}"))

    @staticmethod
    def _sparse_vector(text: str) -> models.SparseVector:
        counts = Counter(re.findall(r"[a-z0-9-]+", text.lower()))
        by_index: dict[int, float] = {}
        for token, count in counts.items():
            index = int.from_bytes(hashlib.sha256(token.encode()).digest()[:4], "big")
            by_index[index] = by_index.get(index, 0.0) + float(count)
        ordered = sorted(by_index.items())
        return models.SparseVector(
            indices=[index for index, _value in ordered],
            values=[value for _index, value in ordered],
        )

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
                        vector={
                            "dense": vector,
                            "text": self._sparse_vector(chunk.text),
                        },
                        payload={
                            **chunk.model_dump(mode="json"),
                            "effective_date": (
                                chunk.effective_date.isoformat() if chunk.effective_date else None
                            ),
                            "content_hash": model_fingerprint(chunk),
                        },
                    )
                    for chunk, vector in zip(batch, vectors, strict=True)
                ],
            )
        return WriteStats(created, updated, unchanged)

    def count(self) -> int:
        return int(
            self.client.count(
                self.collection_name,
                exact=True,
                timeout=STORE_TIMEOUT_SECONDS,
            ).count
        )

    def search(self, query: str, limit: int = 20) -> list[tuple[str, float]]:
        result = self.client.query_points(
            collection_name=self.collection_name,
            query=self.embedding.embed_query(query),
            using="dense",
            limit=limit,
            with_payload=True,
        )
        return [
            (str((point.payload or {})["chunk_id"]), float(point.score)) for point in result.points
        ]

    @staticmethod
    def _server_filter(
        *,
        project_id: str,
        access_scopes: list[str],
        metadata_filters: dict[str, object],
        as_of_date: date | None,
    ) -> models.Filter:
        must: list[models.FieldCondition | models.Filter] = [
            models.FieldCondition(
                key="project_id",
                match=models.MatchAny(any=[project_id, "PUBLIC-REFERENCE"]),
            ),
            models.FieldCondition(
                key="access_scopes",
                match=models.MatchAny(any=access_scopes),
            ),
        ]
        for key, value in metadata_filters.items():
            if not SAFE_METADATA_KEY.fullmatch(key):
                raise ValueError(f"Unsafe metadata filter key: {key}")
            must.append(
                models.FieldCondition(key=f"metadata.{key}", match=models.MatchValue(value=value))
            )
        if as_of_date is not None:
            must.append(
                models.Filter(
                    should=[
                        models.FieldCondition(
                            key="effective_date", range=models.DatetimeRange(lte=as_of_date)
                        ),
                        # Legacy chunks predate this field. Unknown dates stay eligible,
                        # matching the portable retriever, until ingestion can hydrate
                        # them from an authoritative parent record.
                        models.IsEmptyCondition(is_empty=models.PayloadField(key="effective_date")),
                    ]
                )
            )
        return models.Filter(must=must)

    def search_hybrid(
        self,
        *,
        query: str,
        project_id: str,
        access_scopes: list[str],
        metadata_filters: dict[str, object] | None = None,
        as_of_date: date | None = None,
        limit: int = 20,
    ) -> list[HybridCandidate]:
        """Run exact, sparse-text, and dense searches under one server-side filter."""

        if not access_scopes or limit < 1:
            return []
        server_filter = self._server_filter(
            project_id=project_id,
            access_scopes=access_scopes,
            metadata_filters=metadata_filters or {},
            as_of_date=as_of_date,
        )
        branch_limit = min(max(limit * 4, 20), 100)
        identifiers = extract_identifiers(query)
        exact_points = []
        if identifiers:
            exact_filter = models.Filter(
                must=[
                    *(server_filter.must or []),
                    models.Filter(
                        should=[
                            models.FieldCondition(
                                key="record_id", match=models.MatchValue(value=identifier)
                            )
                            for identifier in identifiers
                        ]
                    ),
                ]
            )
            exact_points, _offset = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=exact_filter,
                limit=branch_limit,
                with_payload=True,
                with_vectors=False,
                timeout=STORE_TIMEOUT_SECONDS,
            )
        text_points = self.client.query_points(
            collection_name=self.collection_name,
            query=self._sparse_vector(query),
            using="text",
            query_filter=server_filter,
            limit=branch_limit,
            with_payload=True,
            timeout=STORE_TIMEOUT_SECONDS,
        ).points
        dense_points = self.client.query_points(
            collection_name=self.collection_name,
            query=self.embedding.embed_query(query),
            using="dense",
            query_filter=server_filter,
            limit=branch_limit,
            with_payload=True,
            timeout=STORE_TIMEOUT_SECONDS,
        ).points

        ranks: dict[str, dict[str, int]] = {}
        payloads: dict[str, dict[str, object]] = {}
        for signal, points in (
            ("exact", exact_points),
            ("text", text_points),
            ("dense", dense_points),
        ):
            for rank, point in enumerate(points, start=1):
                payload = dict(point.payload or {})
                chunk_id = str(payload["chunk_id"])
                payloads[chunk_id] = payload
                ranks.setdefault(chunk_id, {})[signal] = rank

        candidates = [
            HybridCandidate(
                chunk=DocumentChunk.model_validate(payloads[chunk_id]),
                fused_score=sum(1 / (60 + rank) for rank in signal_ranks.values()),
                exact_rank=signal_ranks.get("exact"),
                text_rank=signal_ranks.get("text"),
                dense_rank=signal_ranks.get("dense"),
            )
            for chunk_id, signal_ranks in ranks.items()
        ]
        candidates.sort(
            key=lambda candidate: (
                -candidate.fused_score,
                candidate.exact_rank or 10_000,
                candidate.chunk.chunk_id,
            )
        )
        return candidates[:limit]

    def clear(self) -> None:
        if self.client.collection_exists(self.collection_name):
            self.client.delete_collection(self.collection_name)
        self.initialize()
