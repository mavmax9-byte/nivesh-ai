from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nivesh.ai_agents.providers.exceptions import LLMProviderError, LLMResponseParsingError
from nivesh.ai_agents.providers.openai_provider import OpenAIChatProvider


def _mock_settings(api_key: str | None = "sk-test") -> MagicMock:
    settings = MagicMock()
    settings.OPENAI_API_KEY = api_key
    settings.LLM_MODEL = "gpt-4o-mini"
    settings.LLM_TEMPERATURE = 0.1
    settings.LLM_MAX_OUTPUT_TOKENS = 2000
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


def _chat_payload(content: str) -> dict:
    return {
        "model": "gpt-4o-mini",
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


@pytest.mark.asyncio
async def test_complete_raises_when_api_key_missing():
    provider = OpenAIChatProvider()
    with (
        patch(
            "nivesh.ai_agents.providers.openai_provider.get_settings",
            return_value=_mock_settings(api_key=None),
        ),
        pytest.raises(LLMProviderError),
    ):
        await provider.complete("system", "user", {"title": "x"})


@pytest.mark.asyncio
async def test_complete_parses_valid_json_response():
    provider = OpenAIChatProvider()
    response = _mock_response(json_body=_chat_payload('{"summary": "ok"}'))

    with (
        patch(
            "nivesh.ai_agents.providers.openai_provider.get_settings",
            return_value=_mock_settings(),
        ),
        patch("httpx.AsyncClient.post", new=AsyncMock(return_value=response)),
    ):
        completion = await provider.complete("system", "user", {"title": "x"})

    assert completion.parsed_json == {"summary": "ok"}
    assert completion.model == "gpt-4o-mini"
    assert completion.prompt_tokens == 10
    assert completion.completion_tokens == 5
    assert completion.finish_reason == "stop"


@pytest.mark.asyncio
async def test_complete_raises_on_http_error_status():
    provider = OpenAIChatProvider()
    response = _mock_response(status_code=401, text="invalid api key")

    with (
        patch(
            "nivesh.ai_agents.providers.openai_provider.get_settings",
            return_value=_mock_settings(),
        ),
        patch("httpx.AsyncClient.post", new=AsyncMock(return_value=response)),
        pytest.raises(LLMProviderError),
    ):
        await provider.complete("system", "user", {"title": "x"})


@pytest.mark.asyncio
async def test_complete_raises_llm_provider_error_on_malformed_response():
    provider = OpenAIChatProvider()
    response = _mock_response(json_body={"unexpected": "shape"})

    with (
        patch(
            "nivesh.ai_agents.providers.openai_provider.get_settings",
            return_value=_mock_settings(),
        ),
        patch("httpx.AsyncClient.post", new=AsyncMock(return_value=response)),
        pytest.raises(LLMProviderError),
    ):
        await provider.complete("system", "user", {"title": "x"})


@pytest.mark.asyncio
async def test_complete_raises_parsing_error_on_invalid_json_content():
    provider = OpenAIChatProvider()
    response = _mock_response(json_body=_chat_payload("not valid json"))

    with (
        patch(
            "nivesh.ai_agents.providers.openai_provider.get_settings",
            return_value=_mock_settings(),
        ),
        patch("httpx.AsyncClient.post", new=AsyncMock(return_value=response)),
        pytest.raises(LLMResponseParsingError),
    ):
        await provider.complete("system", "user", {"title": "x"})


@pytest.mark.asyncio
async def test_complete_sends_json_schema_response_format():
    provider = OpenAIChatProvider()
    response = _mock_response(json_body=_chat_payload('{"summary": "ok"}'))

    captured: dict = {}

    async def _fake_post(self, url, headers=None, json=None):
        captured.update(json)
        return response

    with (
        patch(
            "nivesh.ai_agents.providers.openai_provider.get_settings",
            return_value=_mock_settings(),
        ),
        patch("httpx.AsyncClient.post", new=_fake_post),
    ):
        await provider.complete("system prompt", "user prompt", {"title": "MySchema"})

    assert captured["messages"][0] == {"role": "system", "content": "system prompt"}
    assert captured["messages"][1] == {"role": "user", "content": "user prompt"}
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["response_format"]["json_schema"]["name"] == "MySchema"
