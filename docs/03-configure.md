# 03. Configure relevance

This is where search quality is won. The accelerator builds two indexes from the
same documents so you can see the effect of each layer:

- `kb-baseline`: a naive index. Default analyzer, no synonyms, no scoring, no
  semantic ranker, no suggester. This is what "we just turned search on" looks
  like.
- `kb-tuned`: the same content with the full relevance configuration.

The schema and configuration are built in `src/config/index_schema.py`. Each
layer below maps to a piece of that file.

## The field schema: what to make searchable, filterable, facetable

Before any relevance tuning, the biggest quiet mistake is a lazy schema where
every field is marked searchable and retrievable "just in case". In Azure AI
Search each attribute has a cost and a purpose, so set them deliberately. The
attributes that matter:

| Attribute | What it enables | Cost if switched on needlessly |
| --- | --- | --- |
| `searchable` | Full-text matching and analysis on the field | Larger index, and noise: a URL or an id that is searchable pollutes keyword matches |
| `filterable` | Exact `$filter` clauses (`contentType eq 'faq'`) | Extra index storage |
| `facetable` | Facet counts for navigation ("23 FAQs, 11 articles") | Extra index storage |
| `sortable` | `$orderby` on the field | Extra index storage |
| `retrievable` | The field comes back in results | Bandwidth; also a chance to leak internal fields |
| `key` | The unique document id (exactly one per index) | Required |

The accelerator's canonical schema applies those rules like this:

| Field | searchable | filterable | facetable | sortable | Why |
| --- | --- | --- | --- | --- | --- |
| `id` | no | yes | no | no | The key. Filterable so you can fetch or exclude a specific document, but never a full-text field. |
| `title` | yes | no | no | no | Primary relevance signal. Analyzed with `nl.microsoft` and weighted highest in scoring. |
| `body` | yes | no | no | no | The main text to match on. Analyzed, but weighted below the title. |
| `tags` | yes | yes | yes | no | Does triple duty: searchable for recall, filterable and facetable so tags drive navigation and facet counts. A string collection. |
| `url` | no | no | no | no | Display only. Retrievable, but keeping it out of search stops link fragments from matching queries. |
| `contentType` | no | yes | yes | no | A short label (`article`, `faq`). Filter and facet on it; there is no value in full-text searching it. |
| `lastModified` | no | yes | no | yes | Sortable so you can order by recency, and it feeds the freshness boost in the scoring profile. |

The rules of thumb behind that table:

- **Make a field `searchable` only if a user would type words that should match
  its content.** Titles and bodies yes; ids, URLs, and type codes no. Searchable
  junk fields are the most common cause of "why did this irrelevant page match".
- **Use `filterable` / `facetable` for the short, controlled-vocabulary fields**
  people navigate by (content type, tags, language, section). Do not facet a
  free-text body.
- **Keep `sortable` for the one or two fields you actually sort on** (usually a
  date). Every sortable field adds storage.
- **One analyzed field per language purpose.** If you later index multiple
  languages, prefer a field per language (`body_nl`, `body_en`) each with its own
  analyzer over one field you try to make multilingual.
- **Do not over-retrieve.** Return only the fields the UI renders. It saves
  bandwidth and avoids exposing internal fields.

This schema is the same in both the baseline and tuned indexes. What differs is
everything below: the baseline leaves the analyzer, synonyms, scoring, suggester,
and semantic ranker off, and the tuned index turns them on.

## Layer 1: language analyzer

The single biggest lever for a non-English site. The tuned index uses the
`nl.microsoft` analyzer on the title and body fields. It provides:

- **Stemming**: `verzekeringen` and `verzekering` are treated as the same root.
- **Decompounding**: `zorgverzekering` also matches `zorg` and `verzekering`,
  which matters a lot in Dutch and German where compound words are everywhere.

The baseline index uses the default analyzer, which does neither well for Dutch.

Change the language by setting `CONTENT_LANGUAGE` (default `nl`). The analyzer name
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
about, and the semantic ranker tolerates noisy phrasing when it reranks. For what
slips through, the practical lever in Azure AI Search is **fuzzy matching** in a
full Lucene query, where `verzekereng~` matches `verzekering` within an edit
distance. Add fuzzy matching in `src/search/query.py` if your evaluation shows
misspellings are still slipping through. (Older guidance mentions a separate
"speller"; recent SDK versions dropped that parameter, so fuzzy matching is the
option to reach for.) Combined with the analyzer and synonyms, this covers most of
the "the search does not understand me" complaints.

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
