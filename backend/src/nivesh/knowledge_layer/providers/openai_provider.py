"""Production embedding provider, backed by OpenAI's embeddings API.

Uses `httpx.AsyncClient` directly against the REST endpoint rather than
adding the `openai` SDK as a dependency -- `httpx` is already this
project's one outbound-HTTP library (document_intelligence's
`HttpDocumentExtractionProvider` uses it the same way), and the embeddings
endpoint is a single simple POST, so a full SDK would only add weight
without buying anything the project doesn't already have.

Chosen (over a local sentence-transformers model) to keep the project's
dependency footprint light -- no `torch`, no multi-hundred-MB model
download -- at the cost of needing a real `OPENAI_API_KEY` and a per-call
cost, the same "real, honest external provider" tradeoff `yfinance`-backed
providers elsewhere in this codebase already make (just with a paid API
instead of a free one). This was an explicit user decision made during
v0.7 planning, not assumed.

Requests are chunked into batches of at most `_MAX_BATCH_SIZE` texts, since
a single generation run can gather many knowledge units (company profile +
every filing + every document section + every news article + every
research summary) and OpenAI's embeddings endpoint accepts a bounded list
of inputs per request -- chunking keeps every request comfortably under
that limit regardless of how many texts a caller passes.
"""

import httpx

from nivesh.config import Settings, get_settings
from nivesh.knowledge_layer.providers.base import EmbeddingProvider, ProviderEmbedding
from nivesh.knowledge_layer.providers.exceptions import EmbeddingProviderError

_API_URL = "https://api.openai.com/v1/embeddings"
_REQUEST_TIMEOUT_SECONDS = 30.0
_MAX_BATCH_SIZE = 96


class OpenAIEmbeddingProvider(EmbeddingProvider):
    async def embed(self, texts: list[str]) -> list[ProviderEmbedding]:
        if not texts:
            return []

        settings = get_settings()
        if not settings.OPENAI_API_KEY:
            raise EmbeddingProviderError(
                "OPENAI_API_KEY is not configured; cannot generate embeddings."
            )

        results: list[ProviderEmbedding] = []
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            for start in range(0, len(texts), _MAX_BATCH_SIZE):
                batch = texts[start : start + _MAX_BATCH_SIZE]
                results.extend(await self._embed_batch(client, batch, settings))
        return results

    async def _embed_batch(
        self, client: httpx.AsyncClient, batch: list[str], settings: Settings
    ) -> list[ProviderEmbedding]:
        try:
            response = await client.post(
                _API_URL,
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                json={"model": settings.EMBEDDING_MODEL, "input": batch},
            )
        except httpx.HTTPError as exc:
            raise EmbeddingProviderError(f"Embedding request failed: {exc}") from exc

        if response.is_error:
            raise EmbeddingProviderError(
                f"Embedding request failed: HTTP {response.status_code} {response.text}"
            )

        try:
            payload = response.json()
            items = sorted(payload["data"], key=lambda item: item["index"])
            return [
                ProviderEmbedding(
                    vector=tuple(item["embedding"]),
                    model=payload["model"],
                    dimensions=len(item["embedding"]),
                )
                for item in items
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbeddingProviderError(f"Malformed embedding response: {exc}") from exc
