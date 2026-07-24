"""Smoke tests for the health and version endpoints.

These intentionally don't require a live database/Redis -- the health
endpoint reports individual dependency failures rather than raising, so the
scaffold's test suite passes without any docker services running.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint_responds(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert "database" in body["checks"]
    assert "redis" in body["checks"]


@pytest.mark.asyncio
async def test_version_endpoint_responds(client: AsyncClient) -> None:
    response = await client.get("/api/v1/version")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Nivesh AI"
    assert "version" in body
    assert "environment" in body
