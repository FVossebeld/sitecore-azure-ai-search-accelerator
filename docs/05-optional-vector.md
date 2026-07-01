# 05. Optional vector and hybrid search

Keyword search with a language analyzer, synonyms, and the semantic ranker
handles the large majority of site-search queries. The vector layer adds one more
capability: matching on meaning when the words do not overlap at all. It is
optional and off by default because it introduces an Azure OpenAI dependency and
extra cost.

## When you actually need it

Turn it on when your evaluation shows a specific gap that the keyword layers do
not close:

- Users describe a concept in their own words rather than the site's vocabulary,
  and no reasonable synonym list would cover it.
- Queries are long and conversational rather than a couple of keywords.
- You are heading toward a retrieval-augmented generation experience later, where
  vector recall is the foundation.

If your evaluation already shows strong Success@1 with the semantic ranker, you
probably do not need vectors for a navigational site search. Measure first.

## What it adds

When `ENABLE_VECTOR=true`:

- The infrastructure deploys an **Azure OpenAI** resource with a text embedding
  model.
- Ingest computes an embedding per document and stores it in a vector field on
  the tuned index. The baseline index never gets vectors, so the comparison stays
  honest.
- The query helper gains a **hybrid** mode: it runs keyword and vector search
  together and fuses the results, then the semantic ranker reranks the fused set.
  Hybrid plus semantic reranking is the strongest configuration available here.
- The evaluation adds a tuned-hybrid row so you can see whether vectors actually
  beat semantic-over-keyword for your content.

## Enabling it

```bash
azd env set ENABLE_VECTOR true
azd up
```

Or for a local run against your own service, set `ENABLE_VECTOR=true` and the
Azure OpenAI settings in `.env`, then re-ingest so the vectors are written:

```bash
python -m src.ingest.push_to_index --variant tuned --load-sample --enable-vector
python -m src.search.query "waar vind ik hulp bij mijn aanvraag" --mode hybrid
python -m src.eval.evaluate --compare
```

## Cost and the off-by-default choice

Vectors cost money in two places: the Azure OpenAI embedding calls at ingest time
and the storage of vectors in the index. For a PoC the amounts are small, but the
dependency is real: you now need an Azure OpenAI deployment, which not every
subscription or region has readily available. That combination is why the layer
is off by default. The core accelerator proves relevance with no Azure OpenAI at
all, and you add vectors only when the numbers say it is worth it.

## If your documents are long

Embedding a whole long page into one vector blurs its meaning. If your content
has long pages and you enable vectors, add chunking: split each page into
passages, embed each passage, and index passages that point back to their parent
page. Preprocessing is the place to add that split. For short, focused pages the
one-vector-per-page default is fine.

## Where the code lives

- `infra/modules/openai.bicep`: the conditional Azure OpenAI deployment.
- `src/common/embeddings.py`: the embedding client and helper.
- `src/ingest/push_to_index.py`: writes vectors when the flag is set.
- `src/search/query.py`: the hybrid query path.

All of it is gated on the same `ENABLE_VECTOR` flag, so with the flag off none of
it runs and no Azure OpenAI resource is created.
