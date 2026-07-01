# Azure AI Search Relevance Accelerator

Stand up an Azure AI Search relevance proof of concept in minutes, prove the
search quality lift with numbers, and keep the whole thing reproducible with
`azd`.

`azd up` provisions the infrastructure, builds two indexes from the same
content (a naive baseline and a tuned one), loads a small sample dataset, and
runs an objective before and after evaluation. The result is a report that
shows exactly how much a proper relevance configuration improves the answers.

The accelerator ships with a synthetic Dutch knowledge base so it runs end to
end out of the box. Bring your own content export when you are ready: any CMS
works, because the tooling reads a simple canonical JSON schema.

## Why this exists

Most "search is bad" problems are not model problems. They are configuration
problems: no language analysis, no synonyms, no scoring, no reranking, and no
measurement. This accelerator makes the configuration explicit and measurable
so you can decide what actually moves the needle before you build anything
bigger.

## What it does

1. **Provision** a small Azure AI Search service (plus storage, and optionally
   Azure OpenAI) with `azd`.
2. **Ingest** exported content, mapped to a canonical schema, cleaned, and
   pushed to the index.
3. **Configure** the relevance layer: a language analyzer with stemming and
   decompounding, a synonym map, a scoring profile, a suggester, and the
   semantic ranker.
4. **Evaluate** retrieval quality against a labelled test set and report
   Success@1, Success@3, MRR@10, found rate, and zero-result rate.

## Architecture

![Architecture: azd provisions Azure AI Search, storage and optional Azure OpenAI. A Python pipeline preprocesses exported content, builds a naive baseline index and a tuned index, then evaluates both against a test set and writes a relevance report.](docs/images/architecture.svg)

Two indexes are built from the same documents so the comparison is fair. The
baseline represents a typical out-of-the-box setup. The tuned index carries the
relevance configuration. The evaluation runs both and reports the delta. The
optional vector layer (Azure OpenAI embeddings) is off by default.

## What gets deployed

| Resource | Purpose | Notes |
| --- | --- | --- |
| Azure AI Search | Retrieval engine | Basic tier by default (the semantic ranker requires Basic or higher) |
| Azure Storage | Holds content exports | Blob container, private access |
| Azure OpenAI | Embeddings for the optional vector layer | Only deployed when `ENABLE_VECTOR=true` |

Access uses Azure AD (RBAC). The deploying user is granted the data-plane roles
needed to create indexes and push documents, so no keys are printed or stored.

## Prerequisites

- [Azure Developer CLI (`azd`)](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd)
- [Azure CLI (`az`)](https://learn.microsoft.com/cli/azure/install-azure-cli) and `az login`
- Python 3.10 or newer
- An Azure subscription with permission to create the resources above

## Quickstart

```bash
azd auth login
azd up
```

Pick a subscription and a region when prompted. When provisioning finishes, the
postprovision hook installs the Python dependencies, builds both indexes, loads
the sample data, and runs the evaluation. Open `reports/relevance-report.md` to
see the before and after numbers.

To tear everything down:

```bash
azd down
```

## Local usage (without azd)

If you already have a search service, you can run the tooling directly.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

cp .env.sample .env          # then set AZURE_SEARCH_ENDPOINT
az login                     # data-plane access uses your Azure AD identity

python -m src.ingest.push_to_index --both --load-sample
python -m src.search.query "paspoort aanvragen" --mode semantic
python -m src.eval.evaluate --compare
```

## Bring your own content

The tooling reads a canonical JSON document. Map your CMS export to this shape
and drop the files into a folder:

```json
{
  "id": "unique-stable-id",
  "title": "Human readable title",
  "body": "Clean text (HTML is stripped automatically)",
  "url": "https://example.org/page",
  "contentType": "article",
  "tags": ["tag-a", "tag-b"],
  "lastModified": "2026-01-31T00:00:00Z"
}
```

Then point the ingest at your folder:

```bash
python -m src.ingest.push_to_index --both --input ./path/to/export
```

See [`docs/01-export.md`](docs/01-export.md) for how to produce this export from
any content platform, and [`docs/02-preprocess.md`](docs/02-preprocess.md) for
the cleaning and field mapping.

## The relevance configuration

The tuned index applies, in layers from cheapest to most involved:

- **Language analyzer** (`nl.microsoft` by default): stemming and decompounding,
  so `zorgverzekering` also matches `zorg` and `verzekering`.
- **Synonym map**: query-side term expansion, so `id-kaart` finds
  `identiteitskaart`. Edit the clusters in `src/config/synonyms/`.
- **Scoring profile**: boosts matches in the title and tags, and gently favours
  fresher content. Defined in `src/config/scoring_profiles.json`.
- **Suggester**: powers autocomplete on title and tags.
- **Semantic ranker**: reranks the top results using a language model, at query
  time, with no embeddings and no Azure OpenAI. This is the highest-value,
  lowest-effort quality lever and it stays in the core configuration.

Details in [`docs/03-configure.md`](docs/03-configure.md).

## Evaluation

The test set is a CSV of `query, intended_id`. The evaluator runs each query and
records where the intended document lands. For navigational site search the
headline metric is Success@1 (the right page is the first result). See
[`docs/04-evaluate.md`](docs/04-evaluate.md) for the metric definitions and how
to build a good test set from real query logs.

## Optional vector and hybrid search

Vector and hybrid retrieval add semantic recall for paraphrased queries, at the
cost of an Azure OpenAI deployment and embedding compute. It is off by default.
Turn it on with:

```bash
azd env set ENABLE_VECTOR true
azd up
```

See [`docs/05-optional-vector.md`](docs/05-optional-vector.md).

## Cost and region notes

- **Tier**: the Search service uses the Basic tier, which is required for the
  semantic ranker. Free tier does not support it.
- **Semantic ranker**: the `free` plan includes a monthly query quota at no
  extra cost, which is plenty for a PoC. Beyond the quota it is billed per
  query, so the evaluation stays well within the free allowance.
- **Vector**: adds Azure OpenAI cost. That is why it is off by default.
- **Region**: pick a region that fits your data residency policy. All the
  common EU regions (West Europe, Sweden Central, North Europe, Germany West
  Central) support the semantic ranker. If a region reports capacity limits for
  new services, Sweden Central and North Europe are good alternatives with the
  same feature set.

## Security defaults

- Data-plane access uses Azure AD (RBAC), not shared keys.
- Storage blocks public blob access and enforces TLS 1.2.
- Secrets are never committed. Local runs read from `.env`, which is gitignored.

## Repository layout

```
infra/        Bicep: search (Basic + semantic), storage, optional Azure OpenAI
src/config/   index schema, synonyms, scoring profiles
src/ingest/   preprocess (clean + map) and push_to_index (create + upload)
src/search/   query helpers (keyword, semantic, hybrid)
src/eval/     evaluate (metrics) and report (markdown + CSV)
data/sample/  synthetic Dutch content + test set
scripts/      azd hooks and re-run helpers
docs/         export, preprocess, configure, evaluate, optional vector
```

## Scope

This is a relevance accelerator. Its job is to prove ranking quality quickly and
objectively, not to run a production content sync. When you are ready for
production, replace the one-off export with an event-driven pipeline and keep the
same index schema and relevance configuration.

## License

MIT. See [LICENSE](LICENSE).
