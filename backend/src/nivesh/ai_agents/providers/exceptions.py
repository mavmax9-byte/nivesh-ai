"""LLM provider-layer exceptions.

Subclasses NiveshError, the same wiring-free pattern every other
provider-layer exception module uses. Two classes here, unlike
knowledge_layer's single-class EmbeddingProviderError -- this module's
caller (agents/fundamental/agent.py) needs to distinguish "the request
never produced a usable response at all" (network/HTTP/auth failure)
from "a response came back but its content is unusable" (invalid JSON,
doesn't match the requested schema). The second case is a materially
different signal -- it means the model actually ran but the structured-
output guarantee didn't hold -- and is worth its own error code for
logging/monitoring even though both are retried the same way at the
Celery task layer today (see ingestion/tasks.py).
"""

from fastapi import status

from nivesh.core.exceptions import NiveshError


class LLMProviderError(NiveshError):
    """Raised when the LLM provider fails outright (missing/invalid API
    key, network failure, upstream HTTP error)."""

    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "LLM_PROVIDER_ERROR"


class LLMResponseParsingError(LLMProviderError):
    """Raised when the LLM responded, but the response body isn't valid
    JSON or doesn't match the requested schema."""

    error_code = "LLM_RESPONSE_PARSING_ERROR"
