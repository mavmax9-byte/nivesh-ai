from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from nivesh.core.exceptions import NotFoundError
from nivesh.knowledge_layer.models import KnowledgeEmbedding
from nivesh.knowledge_layer.router import get_knowledge_layer_service
from nivesh.knowledge_layer.service import KnowledgeSearchHit
from nivesh.main import create_app


def _embedding_row(**overrides) -> KnowledgeEmbedding:
    defaults = dict(
        id=uuid4(),
        company_id=uuid4(),
        source_type="news_article",
        source_table="news_articles",
        source_id=uuid4(),
        title="TCS beats estimates",
        content_text="TCS beats estimates. Revenue rose.",
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
    )
    defaults.update(overrides)
    row = KnowledgeEmbedding(**defaults)
    row.created_at = datetime(2026, 7, 10, 4, 0, 0, tzinfo=UTC)
    row.updated_at = datetime(2026, 7, 10, 4, 0, 0, tzinfo=UTC)
    return row


@pytest.mark.asyncio
async def test_list_embeddings_returns_list():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.list_embeddings.return_value = [_embedding_row()]
    app.dependency_overrides[get_knowledge_layer_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/knowledge/tcs")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["source_type"] == "news_article"
    mock_service.list_embeddings.assert_awaited_once_with("tcs", limit=50, offset=0)


@pytest.mark.asyncio
async def test_list_embeddings_returns_404_for_unknown_symbol():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.list_embeddings.side_effect = NotFoundError("No company found with symbol 'NOPE'")
    app.dependency_overrides[get_knowledge_layer_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/knowledge/NOPE")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_search_knowledge_returns_ranked_results():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.search.return_value = [
        KnowledgeSearchHit(
            source_type="news_article",
            source_table="news_articles",
            source_id=uuid4(),
            title="TCS beats estimates",
            content_text="TCS beats estimates. Revenue rose.",
            similarity=0.87,
        )
    ]
    app.dependency_overrides[get_knowledge_layer_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/knowledge/tcs/search", params={"query": "revenue"})

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "TCS"
    assert body["query"] == "revenue"
    assert len(body["results"]) == 1
    assert body["results"][0]["similarity"] == pytest.approx(0.87)
    mock_service.search.assert_awaited_once_with("tcs", "revenue", limit=10)


@pytest.mark.asyncio
async def test_search_knowledge_requires_query_param():
    app = create_app()
    app.dependency_overrides[get_knowledge_layer_service] = lambda: AsyncMock()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/knowledge/tcs/search")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_generate_embeddings_enqueues_celery_task_and_returns_202():
    app = create_app()
    transport = ASGITransport(app=app)

    with patch("nivesh.knowledge_layer.router.generate_knowledge_embeddings") as mock_task:
        mock_task.delay.return_value = MagicMock(id="task-777")
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/knowledge/generate/tcs")

    assert response.status_code == 202
    body = response.json()
    assert body["symbol"] == "TCS"
    assert body["status"] == "queued"
    assert body["task_id"] == "task-777"
    mock_task.delay.assert_called_once_with("TCS")
