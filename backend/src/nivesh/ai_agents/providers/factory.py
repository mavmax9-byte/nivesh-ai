"""Provider factory -- the one place a concrete LLM provider is chosen."""

from nivesh.ai_agents.providers.base import LLMProvider
from nivesh.ai_agents.providers.openai_provider import OpenAIChatProvider


def get_llm_provider() -> LLMProvider:
    return OpenAIChatProvider()
