"""Builds the Azure AI Search index definitions and synonym map.

Two variants are produced from the same content so you can measure the lift
objectively:

- baseline: a naive keyword index (default analyzer, no synonyms, no scoring
  profile, no semantic configuration, no suggester). This represents a typical
  out-of-the-box setup.
- tuned: the relevance configuration (language analyzer with stemming and
  decompounding, synonym map, scoring profile, semantic configuration, and a
  suggester for autocomplete).
"""
from __future__ import annotations

import json
from pathlib import Path

from azure.search.documents.indexes.models import (
    FreshnessScoringFunction,
    FreshnessScoringParameters,
    HnswAlgorithmConfiguration,
    ScoringProfile,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SearchSuggester,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    SynonymMap,
    TextWeights,
    VectorSearch,
    VectorSearchProfile,
)

from src.common.settings import Settings, SCORING_PROFILES_FILE, SYNONYMS_DIR

VECTOR_FIELD = "contentVector"
VECTOR_PROFILE = "vector-profile"
VECTOR_ALGORITHM = "hnsw"


def analyzer_for(language: str) -> str:
    """Microsoft language analyzer name, for example nl.microsoft for Dutch.

    The Microsoft analyzers add stemming and, for Dutch and German, decompounding
    (parkeervergunning matches parkeren and vergunning).
    """
    return f"{language.lower()}.microsoft"


def read_synonym_rules() -> str:
    """Concatenate all *.txt files in the synonyms directory into one rule set."""
    rules: list[str] = []
    for path in sorted(Path(SYNONYMS_DIR).glob("*.txt")):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            rules.append(stripped)
    return "\n".join(rules)


def build_synonym_map(settings: Settings) -> SynonymMap:
    return SynonymMap(name=settings.synonym_map_name, synonyms=read_synonym_rules())


def _build_scoring_profiles() -> tuple[list[ScoringProfile], str | None]:
    if not Path(SCORING_PROFILES_FILE).exists():
        return [], None
    spec = json.loads(Path(SCORING_PROFILES_FILE).read_text(encoding="utf-8"))
    profiles: list[ScoringProfile] = []
    for item in spec.get("profiles", []):
        functions = []
        fresh = item.get("freshness")
        if fresh:
            functions.append(
                FreshnessScoringFunction(
                    field_name=fresh["field"],
                    boost=float(fresh.get("boost", 2.0)),
                    parameters=FreshnessScoringParameters(
                        boosting_duration=f"P{int(fresh.get('duration_days', 365))}D"
                    ),
                    interpolation=fresh.get("interpolation", "quadratic"),
                )
            )
        profiles.append(
            ScoringProfile(
                name=item["name"],
                text_weights=TextWeights(weights=item.get("text_weights", {})),
                functions=functions,
                function_aggregation="sum",
            )
        )
    return profiles, spec.get("default_profile")


def _fields(settings: Settings, tuned: bool, enable_vector: bool) -> list:
    analyzer = analyzer_for(settings.language) if tuned else None
    synonyms = [settings.synonym_map_name] if tuned else None

    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
        SearchableField(
            name="title",
            type=SearchFieldDataType.String,
            analyzer_name=analyzer,
            synonym_map_names=synonyms,
        ),
        SearchableField(
            name="body",
            type=SearchFieldDataType.String,
            analyzer_name=analyzer,
            synonym_map_names=synonyms,
        ),
        SearchableField(
            name="tags",
            type=SearchFieldDataType.String,
            collection=True,
            analyzer_name=analyzer,
            synonym_map_names=synonyms,
            filterable=True,
            facetable=True,
        ),
        SimpleField(name="url", type=SearchFieldDataType.String),
        SimpleField(
            name="contentType",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),
        SimpleField(
            name="lastModified",
            type=SearchFieldDataType.DateTimeOffset,
            filterable=True,
            sortable=True,
        ),
    ]

    if enable_vector:
        fields.append(
            SearchField(
                name=VECTOR_FIELD,
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                hidden=True,
                vector_search_dimensions=settings.embedding_dimensions,
                vector_search_profile_name=VECTOR_PROFILE,
            )
        )
    return fields


def build_index(settings: Settings, variant: str, enable_vector: bool | None = None) -> SearchIndex:
    variant = variant.lower()
    tuned = variant == "tuned"
    if enable_vector is None:
        enable_vector = settings.enable_vector

    index = SearchIndex(
        name=settings.index_name(variant),
        fields=_fields(settings, tuned=tuned, enable_vector=enable_vector),
    )

    if enable_vector:
        index.vector_search = VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name=VECTOR_ALGORITHM)],
            profiles=[
                VectorSearchProfile(
                    name=VECTOR_PROFILE,
                    algorithm_configuration_name=VECTOR_ALGORITHM,
                )
            ],
        )

    if tuned:
        profiles, default_profile = _build_scoring_profiles()
        if profiles:
            index.scoring_profiles = profiles
            index.default_scoring_profile = default_profile

        index.suggesters = [
            SearchSuggester(name="sg", source_fields=["title", "tags"])
        ]

        index.semantic_search = SemanticSearch(
            default_configuration_name=settings.semantic_config_name,
            configurations=[
                SemanticConfiguration(
                    name=settings.semantic_config_name,
                    prioritized_fields=SemanticPrioritizedFields(
                        title_field=SemanticField(field_name="title"),
                        content_fields=[SemanticField(field_name="body")],
                        keywords_fields=[SemanticField(field_name="tags")],
                    ),
                )
            ],
        )

    return index
