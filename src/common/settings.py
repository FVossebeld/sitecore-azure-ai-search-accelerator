"""Central configuration and Azure client factory.

Values are read from environment variables (optionally via a local .env file).
Local runs authenticate with Azure AD through DefaultAzureCredential, so run
`az login` first. An admin API key can be supplied instead for quick tests.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# Load .env if present. Existing environment variables win (azd sets them directly).
load_dotenv(override=False)

# Repository root (two levels up from this file: src/common/settings.py -> repo root).
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
SAMPLE_CONTENT_DIR = DATA_DIR / "sample" / "content"
SAMPLE_TESTSET = DATA_DIR / "sample" / "testset.csv"
CONFIG_DIR = REPO_ROOT / "src" / "config"
SYNONYMS_DIR = CONFIG_DIR / "synonyms"
SCORING_PROFILES_FILE = CONFIG_DIR / "scoring_profiles.json"
REPORTS_DIR = REPO_ROOT / "reports"


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    search_endpoint: str
    search_api_key: str
    index_base: str
    language: str
    semantic_config_name: str
    synonym_map_name: str
    enable_vector: bool
    openai_endpoint: str
    openai_embedding_deployment: str
    openai_api_key: str
    embedding_dimensions: int

    def index_name(self, variant: str) -> str:
        """Return the concrete index name for a variant (baseline or tuned)."""
        variant = variant.lower()
        if variant not in {"baseline", "tuned"}:
            raise ValueError(f"variant must be 'baseline' or 'tuned', got {variant!r}")
        return f"{self.index_base}-{variant}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT", "").rstrip("/")
    return Settings(
        search_endpoint=endpoint,
        search_api_key=os.environ.get("AZURE_SEARCH_API_KEY", ""),
        index_base=os.environ.get("SEARCH_INDEX_BASE", "kb"),
        language=os.environ.get("CONTENT_LANGUAGE", "nl").lower(),
        semantic_config_name=os.environ.get("SEMANTIC_CONFIG_NAME", "default-semantic"),
        synonym_map_name=os.environ.get("SYNONYM_MAP_NAME", "content-synonyms"),
        enable_vector=_as_bool(os.environ.get("ENABLE_VECTOR"), False),
        openai_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/"),
        openai_embedding_deployment=os.environ.get(
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small"
        ),
        openai_api_key=os.environ.get("AZURE_OPENAI_API_KEY", ""),
        embedding_dimensions=int(os.environ.get("AZURE_OPENAI_EMBEDDING_DIMENSIONS", "1536")),
    )


def get_credential():
    """Return a DefaultAzureCredential (used when no API key is provided)."""
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential()


def _search_credential(settings: Settings):
    if settings.search_api_key:
        from azure.core.credentials import AzureKeyCredential

        return AzureKeyCredential(settings.search_api_key)
    return get_credential()


def get_index_client():
    """SearchIndexClient for creating indexes and synonym maps."""
    from azure.search.documents.indexes import SearchIndexClient

    settings = get_settings()
    if not settings.search_endpoint:
        raise RuntimeError(
            "AZURE_SEARCH_ENDPOINT is not set. Copy .env.sample to .env or run `azd up`."
        )
    return SearchIndexClient(
        endpoint=settings.search_endpoint,
        credential=_search_credential(settings),
    )


def get_search_client(index_name: str):
    """SearchClient bound to a specific index for querying and uploading."""
    from azure.search.documents import SearchClient

    settings = get_settings()
    if not settings.search_endpoint:
        raise RuntimeError(
            "AZURE_SEARCH_ENDPOINT is not set. Copy .env.sample to .env or run `azd up`."
        )
    return SearchClient(
        endpoint=settings.search_endpoint,
        index_name=index_name,
        credential=_search_credential(settings),
    )
