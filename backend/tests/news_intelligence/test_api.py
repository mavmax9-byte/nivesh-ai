from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from nivesh.core.exceptions import NotFoundError
from nivesh.main import create_app
from nivesh.news_intelligence.models import NewsArticle
from nivesh.news_intelligence.router import get_news_intelligence_service


def _article(**overrides) -> NewsArticle:
    defaults = dict(
        id=uuid4(),
        company_id=uuid4(),
        title="India's TCS rises after quarterly revenue beat",
        source="Reuters",
        author=None,
        published_at=datetime(2026, 7, 10, 3, 56, 27, tzinfo=UTC),
        url="https://sg.finance.yahoo.com/news/indias-tcs-rises-quarterly-revenue.html",
        summary="TCS shares rose after reporting quarterly revenue ahead of estimates.",
        full_content=None,
        language="en",
        category="markets",
        provider="yfinance-dev",
    )
    defaults.update(overrides)
    article = NewsArticle(**defaults)
    article.ingestion_timestamp = datetime(2026, 7, 10, 4, 0, 0, tzinfo=UTC)
    article.created_at = datetime(2026, 7, 10, 4, 0, 0, tzinfo=UTC)
    article.updated_at = datetime(2026, 7, 10, 4, 0, 0, tzinfo=UTC)
    return article


@pytest.mark.asyncio
async def test_get_news_returns_article_list():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_news.return_value = [_article()]
    app.dependency_overrides[get_news_intelligence_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/news/tcs")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["source"] == "Reuters"
    assert body[0]["category"] == "markets"
    assert body[0]["provider"] == "yfinance-dev"
    mock_service.get_news.assert_awaited_once_with("tcs", limit=50, offset=0)


@pytest.mark.asyncio
async def test_get_news_returns_404_for_unknown_symbol():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_news.side_effect = NotFoundError("No company found with symbol 'NOPE'")
    app.dependency_overrides[get_news_intelligence_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/news/NOPE")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_news_by_category_returns_filtered_list():
    app = create_app()
    mock_service = AsyncMock()
    mock_service.get_news_by_category.return_value = [_article(category="earnings")]
    app.dependency_overrides[get_news_intelligence_service] = lambda: mock_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/news/tcs/category/earnings")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["category"] == "earnings"
    mock_service.get_news_by_category.assert_awaited_once_with("tcs", "earnings", limit=50)


@pytest.mark.asyncio
async def test_sync_news_enqueues_celery_task_and_returns_202():
    app = create_app()
    transport = ASGITransport(app=app)

    with patch("nivesh.news_intelligence.router.sync_company_news") as mock_task:
        mock_task.delay.return_value = MagicMock(id="task-321")
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/news/sync/tcs")

    assert response.status_code == 202
    body = response.json()
    assert body["symbol"] == "TCS"
    assert body["status"] == "queued"
    assert body["task_id"] == "task-321"
    mock_task.delay.assert_called_once_with("TCS")
