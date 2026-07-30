"""LLM provider interface.

Mirrors every other module's adapter pattern (market_data, financials,
corporate_filings, document_intelligence, and knowledge_layer's
EmbeddingProvider): business logic (agents/fundamental/agent.py) depends
only on `LLMProvider`, never a concrete vendor SDK or client. A provider
takes a system prompt, a user prompt, and a JSON schema describing the
exact output shape the caller requires, and returns one `LLMCompletion`
-- it performs no prompt construction, no output validation, and no
retry policy of its own (those stay in the agent and the Celery task
layer, the same separation every other provider keeps). Swapping LLM
vendors later means writing one new class and changing one line in
factory.py -- callers never change.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMCompletion:
    raw_text: str
    parsed_json: dict[str, Any]
    model: str
    prompt_tokens: int
    completion_tokens: int
    finish_reason: str


class LLMProvider(ABC):
    """Abstract contract every LLM chat/completion provider must implement."""

    @abstractmethod
    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
    ) -> LLMCompletion:
        """Requests one structured completion, using the vendor's
        JSON-schema/structured-output mode where available -- see
        openai_provider.py for how this is applied concretely."""
        raise NotImplementedError
