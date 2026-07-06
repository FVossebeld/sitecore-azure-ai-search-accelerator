# 06. Relevance engineering field guide

This guide covers the practical relevance levers added on top of the core Azure AI Search configuration. The order below follows expected return on investment for a proof of concept and for early production hardening.

## 1. Head-query curation and best-bets

Best-bets pin a known-best page for high-traffic navigational queries. They beat algorithmic tuning for the top head queries because there is no ambiguity once the content team knows the single correct destination.

The curated list lives in `src/config/best_bets.json`. Each entry has lowercase Dutch triggers, a document id, title, url, and a short note. Keep the list small. Use it only for queries where the destination is known and stable, such as `paspoort aanvragen` or `id kaart` in the sample set.

At query time, `src/search/curation.py` normalizes the user query, matches an exact normalized trigger, pins that page, removes duplicates from algorithmic results, and caps the list at the requested `top`.

Honesty note: best-bets are deterministic intent routing, not ranker quality. The default evaluator keeps curation off so the ranker is measured by itself. Run `python -m src.eval.evaluate --curated` when you want to see the lift from the curation layer.

## 2. Zero-result and low-result mining

The CLI query path writes local JSONL telemetry to `reports/query-log.jsonl` when it runs. Each line records the query, index, mode, result count, top ids, curation hit, and fallback path.

Run:

```bash
python -m src.eval.zero_results
```

The report at `reports/zero-results.md` groups zero-result queries and low-result queries. Triage each pattern into one of three actions:

- Synonyms, when the content exists but the vocabulary does not match.
- Best-bets, when a high-traffic query has one known destination.
- New or improved content, when the answer is missing or unclear.

In production, send Azure AI Search diagnostic logs to Log Analytics and mine the same patterns there. The JSONL logger is the local PoC stand-in.

## 3. Synonym governance

Synonyms are powerful, but they can damage precision. Apache Solr format supports two useful patterns:

- Equivalency: `identiteitskaart, id-kaart, idkaart, id kaart`. All terms are interchangeable in both directions.
- Directional: `reisdocument => paspoort`. The left term is rewritten to the right canonical term, one way.

Governance rules:

- Keep clusters strict and small.
- A term should live in only one cluster.
- Over-expansion is the #1 precision killer. Each added synonym widens recall and can bury the right page.
- Test against real query logs before shipping.
- Treat synonyms as governed content owned by content and business teams.

Validate offline before shipping:

```bash
python -m src.config.validate_synonyms --strict
```

## 4. Typo tolerance and suggestions

`src/search/query.py` adds a fuzzy keyword fallback for zero-result keyword and semantic queries. If the primary query returns no rows, it retries a Lucene full query with one-edit fuzzy terms for normal alphabetic words. Acronyms and tokens with digits are protected.

The tuned index also has a suggester named `sg` on `title` and `tags`. Use:

```bash
python -m src.search.suggest "pas" --kind autocomplete
python -m src.search.suggest "pasprt" --kind suggest
```

These suggestion commands require a live Azure AI Search service. Offline, they should import and compile cleanly.

Azure Search SDK note: `query_speller` was removed in `azure-search-documents` 11.6, so fuzzy query construction is the typo lever in this repo.

## 5. Graded evaluation with NDCG@10

`data/sample/testset.csv` now supports a `relevance` column from 0 to 3:

- 3: perfect or primary answer.
- 2: strong secondary answer.
- 1: partial or related answer.
- 0: judged not relevant.

When the column is missing or blank, the evaluator defaults to 3 for backward compatibility.

NDCG@10 complements Success@1 and MRR@10. Success@1 asks whether the best known page is first. MRR rewards an intended page appearing high. NDCG rewards ordering the most relevant pages above partially relevant pages, which matters when a query has several judged documents.

Honesty caveat: offline metrics do not fully predict user satisfaction. Once live, pair them with click-through rate, reformulation rate, abandonment, and A/B tests. Keep a keyword/BM25 baseline as a resilience fallback.

## Next-level Dutch tuning (not yet in this repo)

- Add an exact-match companion field with a keyword analyzer for codes, acronyms, and product names.
- Add asciifolding for diacritics, for variants such as `reintegratie` and `cooerdinator` style misspellings.
- Add a stem-exclusion list so acronyms and product names are not over-stemmed.
- Test Dutch compounds carefully. `nl.microsoft` already does stemming and compound splitting, but real compounds still need query-log validation.
- For high-stakes content, precision at rank 1 matters most. The semantic reranker is the main lever there.
