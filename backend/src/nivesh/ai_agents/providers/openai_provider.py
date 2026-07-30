"""Production LLM provider, backed by OpenAI's chat completions API.

Uses `httpx.AsyncClient` directly against the REST endpoint rather than
adding the `openai` SDK as a dependency -- the same "reuse the one HTTP
library the project already has" choice
`knowledge_layer.providers.openai_provider.OpenAIEmbeddingProvider` and
`document_intelligence`'s `HttpDocumentExtractionProvider` both made.
Reuses the existing `OPENAI_API_KEY` setting (added in v0.7 for
embeddings) rather than introducing a second secret -- one OpenAI account
now covers both the embedding and the chat-completion call.

Requests the vendor's JSON-schema structured-output mode
(`response_format: {"type": "json_schema", ...}`) so schema drift is
caught at the API boundary, not only after the fact in Python -- a
load-bearing choice for the Fundamental Analyst's hallucination-
prevention strategy (see agents/fundamental/validation.py and
FUNDAMENTAL_ANALYST_DESIGN.md §5/§9). `"strict": False` is used
deliberately, not `True`: OpenAI's strict structured-output mode imposes
extra constraints on the schema (every property required,
`additionalProperties: false` at every nesting level) that a
Pydantic-`model_json_schema()`-generated schema is not guaranteed to
satisfy without hand-tuning, and this provider has not been exercised
against the real API yet (no `OPENAI_API_KEY` was available during v0.9
development -- see PROJECT_CONTEXT.md's known limitations). Non-strict
`json_schema` mode still validates the response against the schema; it
is the safer default until a live call can confirm strict mode works
against this project's actual generated schemas.
"""

import json
from typing import Any

import httpx

from nivesh.ai_agents.providers.base import LLMCompletion, LLMProvider
from nivesh.ai_agents.providers.exceptions import LLMProviderError, LLMResponseParsingError
from nivesh.config import Settings, get_settings

_API_URL = "https://api.openai.com/v1/chat/completions"
_REQUEST_TIMEOUT_SECONDS = 60.0


class OpenAIChatProvider(LLMProvider):
    async def complete(
        self, system_prompt: str, user_prompt: str, json_schema: dict[str, Any]
    ) -> LLMCompletion:
        settings = get_settings()
        if not settings.OPENAI_API_KEY:
            raise LLMProviderError(
                "OPENAI_API_KEY is not configured; cannot request an LLM completion."
            )

        response = await self._request(system_prompt, user_prompt, json_schema, settings)

        if response.is_error:
            raise LLMProviderError(
                f"LLM completion request failed: HTTP {response.status_code} {response.text}"
            )

        try:
            body = response.json()
            choice = body["choices"][0]
            content = choice["message"]["content"]
            usage = body.get("usage", {})
            model = body.get("model", settings.LLM_MODEL)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMProviderError(f"Malformed LLM completion response: {exc}") from exc

        try:
            parsed_json = json.loads(content)
        except (TypeError, json.JSONDecodeError) as exc:
            raise LLMResponseParsingError(f"LLM response content is not valid JSON: {exc}") from exc

        return LLMCompletion(
            raw_text=content,
            parsed_json=parsed_json,
            model=model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            finish_reason=choice.get("finish_reason", "unknown"),
        )

    async def _request(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
        settings: Settings,
    ) -> httpx.Response:
        payload = {
            "model": settings.LLM_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": settings.LLM_TEMPERATURE,
            "max_tokens": settings.LLM_MAX_OUTPUT_TOKENS,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": json_schema.get("title", "llm_response"),
                    "schema": json_schema,
                    "strict": False,
                },
            },
        }
        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
                return await client.post(
                    _API_URL,
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"LLM completion request failed: {exc}") from exc
