from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nivesh.knowledge_layer.providers.exceptions import EmbeddingProviderError
from nivesh.knowledge_layer.providers.openai_provider import OpenAIEmbeddingProvider


def _mock_settings(api_key: str | None = "sk-test") -> MagicMock:
    settings = MagicMock()
    settings.OPENAI_API_KEY = api_key
    settings.EMBEDDING_MODEL = "text-embedding-3-small"
    return settings


def _mock_response(
    *, status_code: int = 200, json_body: dict | None = None, text: str = ""
) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.is_error = status_code >= 400
    response.text = text
    response.json.return_value = json_body or {}
    return response


@pytest.mark.asyncio
async def test_embed_returns_empty_list_for_empty_input():
    provider = OpenAIEmbeddingProvider()
    assert await provider.embed([]) == []


@pytest.mark.asyncio
async def test_embed_raises_when_api_key_missing():
    provider = OpenAIEmbeddingProvider()
    with (
        patch(
            "nivesh.knowledge_layer.providers.openai_provider.get_settings",
            return_value=_mock_settings(api_key=None),
        ),
        pytest.raises(EmbeddingProviderError),
    ):
        await provider.embed(["hello"])


@pytest.mark.asyncio
async def test_embed_parses_response_in_index_order():
    provider = OpenAIEmbeddingProvider()
    payload = {
        "model": "text-embedding-3-small",
        "data": [
            {"index": 1, "embedding": [0.2, 0.3]},
            {"index": 0, "embedding": [0.1, 0.1]},
        ],
    }
    response = _mock_response(json_body=payload)

    with (
        patch(
            "nivesh.knowledge_layer.providers.openai_provider.get_settings",
            return_value=_mock_settings(),
        ),
        patch("httpx.AsyncClient.post", new=AsyncMock(return_value=response)),
    ):
        results = await provider.embed(["first", "second"])

    assert len(results) == 2
    assert results[0].vector == (0.1, 0.1)
    assert results[1].vector == (0.2, 0.3)
    assert results[0].model == "text-embedding-3-small"
    assert results[0].dimensions == 2


@pytest.mark.asyncio
async def test_embed_raises_on_http_error_status():
    provider = OpenAIEmbeddingProvider()
    response = _mock_response(status_code=401, text="invalid api key")

    with (
        patch(
            "nivesh.knowledge_layer.providers.openai_provider.get_settings",
            return_value=_mock_settings(),
        ),
        patch("httpx.AsyncClient.post", new=AsyncMock(return_value=response)),
        pytest.raises(EmbeddingProviderError),
    ):
        await provider.embed(["hello"])


@pytest.mark.asyncio
async def test_embed_raises_on_malformed_response():
    provider = OpenAIEmbeddingProvider()
    response = _mock_response(json_body={"unexpected": "shape"})

    with (
        patch(
            "nivesh.knowledge_layer.providers.openai_provider.get_settings",
            return_value=_mock_settings(),
        ),
        patch("httpx.AsyncClient.post", new=AsyncMock(return_value=response)),
        pytest.raises(EmbeddingProviderError),
    ):
        await provider.embed(["hello"])


@pytest.mark.asyncio
async def test_embed_chunks_large_batches():
    provider = OpenAIEmbeddingProvider()
    texts = [f"text-{i}" for i in range(150)]

    def _response_for(request_json: dict) -> MagicMock:
        count = len(request_json["input"])
        return _mock_response(
            json_body={
                "model": "text-embedding-3-small",
                "data": [{"index": i, "embedding": [0.0]} for i in range(count)],
            }
        )

    calls: list[int] = []

    async def _fake_post(self, url, headers=None, json=None):
        calls.append(len(json["input"]))
        return _response_for(json)

    with (
        patch(
            "nivesh.knowledge_layer.providers.openai_provider.get_settings",
            return_value=_mock_settings(),
        ),
        patch("httpx.AsyncClient.post", new=_fake_post),
    ):
        results = await provider.embed(texts)

    assert len(results) == 150
    assert sum(calls) == 150
    assert len(calls) == 2  # 96 + 54, given _MAX_BATCH_SIZE = 96
