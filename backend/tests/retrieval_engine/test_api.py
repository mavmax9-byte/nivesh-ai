from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from nivesh.core.exceptions import NotFoundError
from nivesh.main import create_app
from nivesh.retrieval_engine.normalization import ContextPackage, EvidenceItem
from nivesh.retrieval_engine.router import get_retrieval_engine_service
from nivesh.retrieval_engine.service import RetrievalDiagnostics


def _evidence_item(**overrides) -> EvidenceItem:
    defaults = dict(
        source_type="news_article",
        source_table="news_articles",
        source_id=uuid4(),
        title="TCS beats estimates",
        snippet="Revenue rose.",
        evidence_date=datetime(2026, 7, 25, tzinfo=UTC).date(),
        relevance_score=0.87,
        retrieved_via=("structured",),
    )
    defaults.update(overrides)
    return EvidenceItem(**defaults)


@pytest.mark.asyncio
async def test_retrieve_evidence_returns_ranked_list():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.retrieve_evidence.return_value = [_evidence_item()]
    app.dependency_overrides[get_retrieval_engine_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/retrieval/tcs/evidence", params={"query": "revenue growth"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "TCS"
    assert body["query"] == "revenue growth"
    assert len(body["evidence"]) == 1
    assert body["evidence"][0]["source_type"] == "news_article"
    assert body["evidence"][0]["relevance_score"] == pytest.approx(0.87)
    mock_service.retrieve_evidence.assert_awaited_once_with("tcs", "revenue growth", limit=20)


@pytest.mark.asyncio
async def test_retrieve_evidence_returns_404_for_unknown_symbol():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.retrieve_evidence.side_effect = NotFoundError(
        "No company found with symbol 'NOPE'"
    )
    app.dependency_overrides[get_retrieval_engine_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/retrieval/NOPE/evidence", params={"query": "x"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_retrieve_evidence_requires_query_param():
    app = create_app()
    app.dependency_overrides[get_retrieval_engine_service] = lambda: AsyncMock()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/retrieval/tcs/evidence")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_retrieve_context_package_returns_text_and_evidence():
    app = create_app()
    mock_service = AsyncMock()
    item = _evidence_item()
    mock_service.build_context_package.return_value = ContextPackage(
        symbol="TCS",
        query="revenue",
        generated_at=datetime(2026, 7, 30, tzinfo=UTC),
        evidence=(item,),
        context_text='Evidence for TCS -- query: "revenue"\n[1] ...',
    )
    app.dependency_overrides[get_retrieval_engine_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/retrieval/tcs/context", params={"query": "revenue"})

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "TCS"
    assert "Evidence for TCS" in body["context_text"]
    assert len(body["evidence"]) == 1


@pytest.mark.asyncio
async def test_inspect_retrieval_returns_diagnostics():
    app = create_app()
    mock_service = AsyncMock()
    item = _evidence_item()
    mock_service.inspect_retrieval.return_value = RetrievalDiagnostics(
        symbol="TCS",
        query="revenue",
        fetched_counts={"news_article": 1},
        total_fetched=1,
        total_after_dedup=1,
        total_returned=1,
        evidence=(item,),
    )
    app.dependency_overrides[get_retrieval_engine_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/retrieval/tcs/inspect", params={"query": "revenue"})

    assert response.status_code == 200
    body = response.json()
    assert body["fetched_counts"] == {"news_article": 1}
    assert body["total_fetched"] == 1
