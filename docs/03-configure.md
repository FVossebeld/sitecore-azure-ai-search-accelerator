# 03. Configure relevance

This is where search quality is won. The accelerator builds two indexes from the
same documents so you can see the effect of each layer:

- `kb-baseline`: a naive index. Default analyzer, no synonyms, no scoring, no
  semantic ranker, no suggester. This is what "we just turned search on" looks
  like.
- `kb-tuned`: the same content with the full relevance configuration.

The schema and configuration are built in `src/config/index_schema.py`. Each
layer below maps to a piece of that file.

## Layer 1: language analyzer

The single biggest lever for a non-English site. The tuned index uses the
`nl.microsoft` analyzer on the title and body fields. It provides:

- **Stemming**: `verzekeringen` and `verzekering` are treated as the same root.
- **Decompounding**: `zorgverzekering` also matches `zorg` and `verzekering`,
  which matters a lot in Dutch and German where compound words are everywhere.

The baseline index uses the default analyzer, which does neither well for Dutch.

Change the language by setting `SEARCH_LANGUAGE` (default `nl`). The analyzer name
is built as `{language}.microsoft`, so `de` gives `de.microsoft`, `fr` gives
`fr.microsoft`, and so on.

## Layer 2: synonym map

Synonyms expand a query so different words for the same thing return the same
results. The rules live in `src/config/synonyms/` as plain text, one rule per
line, in Solr format:

```
# equivalent terms (all map to each other)
id-kaart, identiteitskaart, identiteitsbewijs

# explicit expansion (left expands to right)
ov => openbaar vervoer
```

Lines starting with `#` are comments. Edit these files to match your domain.
Business and content teams can own this file directly, which is often the point:
relevance tuning should not require a developer.

The synonym map is applied to the tuned index only, so its effect is visible in
the evaluation.

## Layer 3: scoring profile

The scoring profile in `src/config/scoring_profiles.json` shapes ranking beyond
raw text match:

- **Field weights**: a match in the `title` counts more than a match in the
  `body`, and `tags` sit in between. Defaults are title 3.0, tags 2.0, body 1.0.
- **Freshness**: newer content gets a gentle boost based on `lastModified`, so
  when two pages are equally relevant the more recent one wins.

The profile is set as the default on the tuned index, so every query benefits
without extra query code.

## Layer 4: suggester

A suggester powers autocomplete and "did you mean" style helpers. The tuned index
defines one over the title and tags. It does not change ranking of full queries
but it improves the experience as the user types, which is a common ask for site
search.

## Layer 5: semantic ranker

The highest-value, lowest-effort quality lever. The semantic ranker takes the top
keyword results and reranks them with a language model at query time. It runs as
a managed capability of the search service, so it needs no embeddings and no
Azure OpenAI resource.

The tuned index defines a semantic configuration that tells the ranker which
fields carry the title, the main content, and the keywords. Queries opt in with
the semantic mode:

```bash
python -m src.search.query "hoe vraag ik een toeslag aan" --mode semantic
```

Because it reranks, it fixes the common case where the right page is on the first
result page but not at the top. The semantic ranker requires the Basic tier or
higher, which is why the infrastructure provisions Basic.

## Typo tolerance

Real users misspell. Several layers here already absorb that: the `nl.microsoft`
analyzer stems word variants, the synonym map covers alternate spellings you know
about, and the semantic ranker tolerates noisy phrasing when it reranks. For
harder cases you have two options in Azure AI Search: enable spelling correction
(the speller, where your service API version supports it) or use fuzzy matching
in a full Lucene query, where `verzekereng~` matches `verzekering` within an edit
distance. Add fuzzy matching in `src/search/query.py` if your evaluation shows
misspellings are still slipping through. Combined with the analyzer and synonyms,
this covers most of the "the search does not understand me" complaints.

## How the layers combine

Order of impact for a typical navigational site search:

1. Language analyzer (correct tokenisation and decompounding).
2. Semantic ranker (reranks the near-misses to the top).
3. Synonyms (covers vocabulary gaps the analyzer cannot).
4. Scoring profile (breaks ties toward titles and fresher pages).
5. Suggester (helps before the query is even finished).

You do not have to guess which ones matter for your content. The evaluation in
[04-evaluate.md](04-evaluate.md) measures it.

## Next

Continue to [04-evaluate.md](04-evaluate.md) to measure the lift.
