"""Knowledge Layer data-access layer.

Bulk upsert is the primary write path, mirroring
technical_intelligence's own `bulk_upsert` -- a single generation run
writes many embedding rows across many source units, always written (and
conflict-resolved) as a batch keyed by `(source_type, source_id)`. Each
repository write commits its own batch directly, the same "no
flush-then-final-commit aggregate root" shape technical_intelligence and
market_data use, since there is no parent/child row pair here that must
land together.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from nivesh.knowledge_layer.models import KnowledgeEmbedding


class KnowledgeEmbeddingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- reads -----------------------------------------------------------

    async def get_checksums_by_company(
        self, company_id: uuid.UUID
    ) -> dict[tuple[str, uuid.UUID], str]:
        """Maps `(source_type, source_id) -> content_checksum` for every
        embedding already stored for a company -- used by the service to
        skip calling the (paid, networked) embedding provider for source
        units whose text hasn't changed since the last run."""
        result = await self._session.execute(
            select(
                KnowledgeEmbedding.source_type,
                KnowledgeEmbedding.source_id,
                KnowledgeEmbedding.content_checksum,
            ).where(KnowledgeEmbedding.company_id == company_id)
        )
        return {(row[0], row[1]): row[2] for row in result.all()}

    async def list_by_company(
        self, company_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> list[KnowledgeEmbedding]:
        """Caution for callers reusing one session across a `bulk_upsert`
        and a `list_by_company` of the same rows: `bulk_upsert` writes via
        a raw Core statement, which the ORM identity map never observes --
        a row already cached from an earlier read in this session will
        come back stale here after a later `bulk_upsert`, unless the
        session expires it first. No current caller does this (see
        `ai_agents/repository.py`'s `get_latest` for the fuller version of
        this note, found the same way during v1.2 live verification)."""
        result = await self._session.execute(
            select(KnowledgeEmbedding)
            .where(KnowledgeEmbedding.company_id == company_id)
            .order_by(KnowledgeEmbedding.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def search_similar_by_company(
        self, company_id: uuid.UUID, query_vector: list[float], limit: int = 10
    ) -> list[tuple[KnowledgeEmbedding, float]]:
        """Cosine-distance nearest neighbors within one company's own
        embeddings. Returns `(row, distance)` pairs, closest first --
        `distance` is pgvector's cosine distance (0 = identical direction,
        2 = opposite), not a similarity score; the service layer converts
        it for API responses."""
        distance = KnowledgeEmbedding.embedding.cosine_distance(query_vector).label("distance")
        result = await self._session.execute(
            select(KnowledgeEmbedding, distance)
            .where(KnowledgeEmbedding.company_id == company_id)
            .order_by(distance)
            .limit(limit)
        )
        return [(row[0], row[1]) for row in result.all()]

    # -- writes ------------------------------------------------------------

    async def bulk_upsert(self, rows: list[dict]) -> int:
        if not rows:
            return 0

        statement = pg_insert(KnowledgeEmbedding).values(rows)
        statement = statement.on_conflict_do_update(
            index_elements=["source_type", "source_id"],
            set_={
                "title": statement.excluded.title,
                "content_text": statement.excluded.content_text,
                "content_checksum": statement.excluded.content_checksum,
                "embedding": statement.excluded.embedding,
                "embedding_model": statement.excluded.embedding_model,
                "embedding_dimensions": statement.excluded.embedding_dimensions,
                # ORM `onupdate=func.now()` never fires for this Core-level upsert --
                # must be set explicitly or a re-run leaves `updated_at` stale
                # (same bug, same fix, as ai_agents/repository.py -- see its comment).
                "updated_at": func.now(),
            },
        )
        await self._session.execute(statement)
        await self._session.commit()
        return len(rows)

    async def commit(self) -> None:
        """Commits whatever is pending on this repository's session --
        used by KnowledgeLayerService to durably persist Research Dossier
        evidence rows written through ResearchDossierRepository's
        flush-only methods on this same shared session (see
        KnowledgeLayerService._link_to_research_dossier).
        """
        await self._session.commit()
