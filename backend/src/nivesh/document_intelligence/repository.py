"""Document Intelligence data-access layer.

`DocumentExtraction` is treated as an aggregate root together with its
`DocumentSection` children, the same way `FinancialStatement` and
`CorporateFiling` are in their own repositories: writes use `flush()`
(visible within the transaction, not yet durable) and only
`commit_extraction` -- the last step of persisting one extraction --
actually commits, so an extraction's row and its section breakdown are
always written together or not at all.

There is no update path here: a filing version has at most one extraction
(models.py), and re-extracting an already-extracted version is rejected as
a duplicate before this repository is ever called to write anything (see
validation.py / service.py) -- so the only writes this repository performs
are first-time creates.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from nivesh.document_intelligence.models import DocumentExtraction, DocumentSection

_DETAIL_OPTIONS = (selectinload(DocumentExtraction.sections),)


class DocumentExtractionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- reads -----------------------------------------------------------

    async def get_by_filing_version(
        self, filing_version_id: uuid.UUID
    ) -> DocumentExtraction | None:
        result = await self._session.execute(
            select(DocumentExtraction)
            .options(*_DETAIL_OPTIONS)
            .where(DocumentExtraction.filing_version_id == filing_version_id)
        )
        return result.scalar_one_or_none()

    async def list_by_company(
        self, company_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> list[DocumentExtraction]:
        result = await self._session.execute(
            select(DocumentExtraction)
            .where(DocumentExtraction.company_id == company_id)
            .order_by(DocumentExtraction.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_by_company_with_sections(
        self, company_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> list[DocumentExtraction]:
        """Same as list_by_company, but with `sections` eager loaded --
        added for knowledge_layer (v0.7), which embeds each DocumentSection
        individually and would otherwise trigger a lazy load that fails
        under an async session."""
        result = await self._session.execute(
            select(DocumentExtraction)
            .options(*_DETAIL_OPTIONS)
            .where(DocumentExtraction.company_id == company_id)
            .order_by(DocumentExtraction.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    # -- writes (flush only, except commit_extraction) --------------------

    async def create_extraction(self, data: dict) -> DocumentExtraction:
        extraction = DocumentExtraction(**data)
        self._session.add(extraction)
        await self._session.flush()
        return extraction

    async def create_sections(self, document_extraction_id: uuid.UUID, rows: list[dict]) -> int:
        if not rows:
            return 0
        sections = [
            DocumentSection(document_extraction_id=document_extraction_id, **row) for row in rows
        ]
        self._session.add_all(sections)
        await self._session.flush()
        return len(sections)

    async def commit_extraction(self, extraction: DocumentExtraction) -> DocumentExtraction:
        """Commits the whole write sequence for one extraction -- the one
        write in this repository that is not just a flush."""
        await self._session.commit()
        await self._session.refresh(extraction, attribute_names=["sections"])
        return extraction

    async def commit(self) -> None:
        """Commits whatever is pending on this repository's session.

        Used by DocumentIntelligenceService to durably persist Research
        Dossier evidence rows written through ResearchDossierRepository's
        flush-only methods on this same shared session -- see
        DocumentIntelligenceService._link_to_research_dossier.
        """
        await self._session.commit()
