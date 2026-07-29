"""Provider factory -- the one place a concrete provider is chosen."""

from nivesh.knowledge_layer.providers.base import EmbeddingProvider
from nivesh.knowledge_layer.providers.openai_provider import OpenAIEmbeddingProvider


def get_embedding_provider() -> EmbeddingProvider:
    return OpenAIEmbeddingProvider()
