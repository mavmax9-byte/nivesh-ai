"""Embedding provider interface.

Mirrors every other module's adapter pattern (market_data, financials,
corporate_filings, document_intelligence, news_intelligence,
technical_intelligence): the application depends only on
`EmbeddingProvider`, never a concrete embedding backend. A provider takes a
batch of already-normalized text strings and returns one vector per input,
in the same order -- it does no chunking, truncation, or text selection of
its own (that's normalization.py's job, so it stays independently testable
and provider-agnostic). Swapping embedding backends later (a different
hosted API, a self-hosted model) means writing one new class and changing
one line in factory.py -- KnowledgeLayerService never needs to change.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderEmbedding:
    vector: tuple[float, ...]
    model: str
    dimensions: int


class EmbeddingProvider(ABC):
    """Abstract contract every embedding provider must implement."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[ProviderEmbedding]:
        """Embeds a batch of texts, returning one ProviderEmbedding per
        input text, in the same order as `texts`."""
        raise NotImplementedError
