"""Optional Azure OpenAI embedding helper. Only used when ENABLE_VECTOR=true."""
from __future__ import annotations

from typing import Iterable

from src.common.settings import Settings, get_credential


def _client(settings: Settings):
    from openai import AzureOpenAI

    if not settings.openai_endpoint:
        raise RuntimeError(
            "ENABLE_VECTOR is true but AZURE_OPENAI_ENDPOINT is not set. "
            "Deploy the optional module with `azd env set ENABLE_VECTOR true` then `azd up`."
        )

    if settings.openai_api_key:
        return AzureOpenAI(
            azure_endpoint=settings.openai_endpoint,
            api_key=settings.openai_api_key,
            api_version="2024-10-21",
        )

    # Azure AD auth via a bearer token provider.
    from azure.identity import get_bearer_token_provider

    token_provider = get_bearer_token_provider(
        get_credential(), "https://cognitiveservices.azure.com/.default"
    )
    return AzureOpenAI(
        azure_endpoint=settings.openai_endpoint,
        azure_ad_token_provider=token_provider,
        api_version="2024-10-21",
    )


def embed_texts(settings: Settings, texts: Iterable[str]) -> list[list[float]]:
    """Return an embedding vector for each input text."""
    texts = [t if t else " " for t in texts]
    if not texts:
        return []
    client = _client(settings)
    result = client.embeddings.create(
        model=settings.openai_embedding_deployment,
        input=texts,
        dimensions=settings.embedding_dimensions,
    )
    return [item.embedding for item in result.data]
