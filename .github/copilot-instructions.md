# Copilot instructions

This repo is a **Sitecore + Azure AI Search relevance accelerator**: an anonymous, customer-agnostic
Proof of Concept that stands up a Dutch-language search relevance comparison with `azd up`. It exports
content from headless Sitecore (Experience Edge), preprocesses it, indexes it into two Azure AI Search
indexes, and measures the relevance lift of a tuned index over a naive baseline.

## Non-negotiable rules

1. **No em-dash or en-dash characters.** Never use those dash characters in docs, comments, commit
   messages, or any prose. Use commas, parentheses, or rewrite the sentence. Before committing prose,
   grep for those characters (exclude `*.svg`, where the arrow glyph is fine) and remove any hits.
2. **Keep the repo customer-anonymous.** No customer names, contacts, tenant IDs, or identifying details
   anywhere: code, docs, sample data, or commit messages. Azure and Sitecore product names are fine.
   Sample content in `data/sample` is synthetic Dutch civic content and must stay generic.
3. **Do not assume or fabricate customer inputs.** There is no real customer query-log export, index dump,
   or content feed in this repo. `data/sample` is synthetic. Do not present bundled data as if it were
   real customer data, and do not assume an artifact exists unless it is actually in the repo.

## Design intent

This is a relevance PoC, not production infrastructure. Prefer the simplest thing that proves the lift.
Do not add sync pipelines, extra services, or operational machinery unless asked. The core value is the
**two-index contract**, and it must stay intact:

- `kb-baseline`: naive index. Default analyzer, no synonyms, no scoring profile, no semantic config,
  no suggester.
- `kb-tuned`: the improvement. `nl.microsoft` analyzer, synonym map, scoring profile, semantic
  configuration, and suggester. Vectors are added only here and only when `ENABLE_VECTOR` is set.

Both indexes are built from the same content by `src/config/index_schema.py` so the only variable is
configuration. Index base name defaults to `kb` (`SEARCH_INDEX_BASE`).

## Facts to verify, not guess

Sitecore and Azure AI Search details change; check current docs before stating specifics. Known gotchas
already baked into this repo:

- Sitecore deprecated its **Lucene** index provider, not Azure AI Search. Do not conflate the two.
- Experience Edge GraphQL `search` is for **filtered content retrieval**, not end-user site search. This
  repo uses Edge as an export source, then does relevance ranking in Azure AI Search.
- `azure-search-documents` 11.6 removed `query_speller` and `query_language`. Do not reintroduce them;
  the typo lever is fuzzy matching in the query builder.

## Conventions

- Content language is Dutch. The env var is `CONTENT_LANGUAGE` (default `nl`), not `SEARCH_LANGUAGE`.
- Canonical document schema (see `src/ingest/preprocess.py`): `id`, `title`, `body`, `url`,
  `contentType` (lowercased), `tags`, `lastModified`. Field aliases are Sitecore-aware.
- Other env vars: `SYNONYM_MAP_NAME` (default `content-synonyms`), `ENABLE_VECTOR`.
- When the user writes in Dutch, reply and draft any emails in Dutch.

## Layout

- `src/ingest/` export, preprocess, and load: `export_edge.py` (Experience Edge extractor),
  `preprocess.py` (HTML strip + alias map), `push_to_index.py` (builds both indexes).
- `src/config/` index schema, synonyms, best-bets, scoring profiles, and `validate_synonyms.py`.
- `src/search/query.py` keyword, semantic, hybrid, best-bet curation, fuzzy fallback, and telemetry hooks.
- `src/search/curation.py`, `src/search/suggest.py`, and `src/search/telemetry.py` hold curation,
  suggestions, and local query logging.
- `src/eval/` `evaluate.py`, `report.py`, and `zero_results.py` produce evaluation and query-mining
  reports under `reports/`.
- `data/sample/` synthetic content, graded testset, and raw Sitecore export samples.
- `docs/` numbered walkthrough (`01`..`06`), including field-schema design guidance in `03-configure.md`
  and relevance engineering in `06-relevance-engineering.md`.

## Dev loop

Local Python venv lives at `.venv\Scripts\python.exe`. There is **no test suite and no linter** in this
repo. Verify changes with `python -m py_compile` and the offline smoke runs below before committing.

```
# offline demos (no Azure needed)
python -m src.ingest.export_edge --dry-run
python -m src.ingest.preprocess --input data/sample/sitecore-raw --show 2
python -m src.config.validate_synonyms --strict
python -m src.eval.zero_results
python -m py_compile src/search/query.py src/search/curation.py src/search/suggest.py src/search/telemetry.py src/config/validate_synonyms.py src/eval/evaluate.py src/eval/report.py src/eval/zero_results.py

# full flow (needs Azure AI Search)
python -m src.ingest.push_to_index --both --load-sample
python -m src.search.query "paspoort" --mode semantic --variant tuned
python -m src.search.query "paspoort" --mode semantic --variant tuned --no-curation
python -m src.search.suggest "pas" --variant tuned --kind autocomplete
python -m src.eval.evaluate --compare        # writes reports/relevance-report.md
python -m src.eval.evaluate --compare --curated
```

Helper scripts: `scripts/run_eval.ps1` / `scripts/run_eval.sh`. Full deploy is `azd up` (use the Basic
tier or higher for the semantic ranker; see the region and cost note in the README for EU capacity
fallbacks such as Sweden Central or North Europe).
