"""Create the index (and synonym map) then upload the content.

Usage examples:
    python -m src.ingest.push_to_index --variant tuned --load-sample
    python -m src.ingest.push_to_index --both --input ./data/sample/content
    python -m src.ingest.push_to_index --both --load-sample   # baseline + tuned
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from src.common.settings import SAMPLE_CONTENT_DIR, get_index_client, get_search_client, get_settings
from src.config.index_schema import VECTOR_FIELD, build_index, build_synonym_map
from src.ingest.preprocess import load_and_preprocess

BATCH_SIZE = 1000


def _ensure_synonym_map(index_client, settings) -> None:
    synonym_map = build_synonym_map(settings)
    index_client.create_or_update_synonym_map(synonym_map)
    print(f"  synonym map '{synonym_map.name}' created or updated")


def _add_vectors(settings, docs: list[dict[str, Any]]) -> None:
    from src.common.embeddings import embed_texts

    texts = [f"{d.get('title', '')}\n{d.get('body', '')}".strip() for d in docs]
    print(f"  embedding {len(texts)} documents with '{settings.openai_embedding_deployment}'")
    vectors = embed_texts(settings, texts)
    for doc, vector in zip(docs, vectors):
        doc[VECTOR_FIELD] = vector


def _upload(index_name: str, docs: list[dict[str, Any]]) -> None:
    client = get_search_client(index_name)
    total = 0
    for start in range(0, len(docs), BATCH_SIZE):
        batch = docs[start : start + BATCH_SIZE]
        results = client.upload_documents(documents=batch)
        failed = [r for r in results if not r.succeeded]
        if failed:
            raise RuntimeError(f"{len(failed)} documents failed to upload, first key {failed[0].key}")
        total += len(batch)
    print(f"  uploaded {total} documents to index '{index_name}'")


def push_variant(variant: str, docs: list[dict[str, Any]], enable_vector: bool | None = None) -> None:
    settings = get_settings()
    index_client = get_index_client()

    variant = variant.lower()
    tuned = variant == "tuned"
    # Vectors only ever apply to the tuned variant; baseline stays keyword-only.
    variant_vector = bool(enable_vector if enable_vector is not None else settings.enable_vector) and tuned

    print(f"[{variant}] preparing index '{settings.index_name(variant)}'")
    if tuned:
        _ensure_synonym_map(index_client, settings)

    index = build_index(settings, variant=variant, enable_vector=variant_vector)
    index_client.create_or_update_index(index)
    print(f"  index '{index.name}' created or updated")

    payload = [dict(d) for d in docs]
    if variant_vector:
        _add_vectors(settings, payload)
    else:
        for d in payload:
            d.pop(VECTOR_FIELD, None)

    _upload(index.name, payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create indexes and upload content.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--variant", choices=["baseline", "tuned"], help="Push a single variant.")
    group.add_argument("--both", action="store_true", help="Push baseline and tuned (default).")
    parser.add_argument("--input", type=Path, help="Folder with source *.json files.")
    parser.add_argument("--load-sample", action="store_true", help="Use the bundled sample dataset.")
    parser.add_argument(
        "--enable-vector",
        dest="enable_vector",
        action="store_true",
        default=None,
        help="Force the optional vector layer on the tuned index (needs Azure OpenAI).",
    )
    args = parser.parse_args()

    input_dir = SAMPLE_CONTENT_DIR if (args.load_sample or not args.input) else args.input
    docs = load_and_preprocess(input_dir)
    print(f"Loaded {len(docs)} documents from {input_dir}\n")

    variants = [args.variant] if args.variant else ["baseline", "tuned"]
    for variant in variants:
        push_variant(variant, docs, enable_vector=args.enable_vector)
        print()

    print("Done.")


if __name__ == "__main__":
    main()
