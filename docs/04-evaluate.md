# 04. Evaluate

A relevance PoC is only convincing if it is measured. This step runs a fixed set of queries against the indexes and reports where the intended answers land. The logic is in `src/eval/evaluate.py` and the reporting in `src/eval/report.py`.

## The test set

The test set is a CSV with `query`, `intended_id`, and an optional `relevance` column:

```csv
query,intended_id,relevance
paspoort aanvragen,doc-001,3
paspoort aanvragen,doc-008,1
id kaart,doc-008,3
identiteitskart,doc-008,3
```

- `query`: what a user types. Include messy real-world variants: synonyms, abbreviations, and misspellings.
- `intended_id`: the `id` of a document judged for that query.
- `relevance`: graded relevance from 0 to 3. Use 3 for the best answer, 2 for a strong secondary answer, 1 for a partial or related answer, and 0 for not relevant. If the column is missing or blank, it defaults to 3.

Rows are not deduplicated. A query can appear multiple times with different judged documents, which lets NDCG@10 measure whether the best answer ranks above partial matches.

The bundled `data/sample/testset.csv` has primary judgments plus a few partial judgments over the sample content.

## Metrics

For each unique query, the evaluator finds the first relevant document with relevance at least 1 and also computes graded gain:

| Metric | Meaning | Why it matters |
| --- | --- | --- |
| **Success@1** | A relevant doc is the first result | The headline metric for navigational site search |
| **Success@3** | A relevant doc is in the top 3 | Tolerance for near misses |
| **MRR@10** | Mean reciprocal rank over the top 10 | Rewards getting a relevant answer higher, not just present |
| **NDCG@10** | Normalized discounted cumulative gain using relevance 0 to 3 | Rewards ranking the most relevant pages above partial matches |
| **Found@10** | A relevant doc appears anywhere in the top 10 | Recall check |
| **Zero-result rate** | Share of queries returning nothing | Directly ties to the no-results complaint |

For website search where people expect to land on the right page immediately, Success@1 is usually the number to lead with. NDCG@10 adds nuance when there are multiple judged pages. Zero-result rate is the second operational metric because empty results are the most visible failure.

## Running the evaluation

The default run compares the configurations side by side and leaves best-bet curation off so the ranker is measured by itself:

```bash
python -m src.eval.evaluate --compare
```

This evaluates:

- baseline, keyword only
- tuned, keyword only
- tuned, semantic ranker
- tuned, hybrid (only when the vector layer is enabled)

It writes `reports/relevance-report.md` with a table and a lift line, plus CSV summaries under `reports/`. To evaluate a single configuration:

```bash
python -m src.eval.evaluate --variant tuned --mode semantic
```

To measure the deterministic best-bets layer as well, add:

```bash
python -m src.eval.evaluate --compare --curated
```

Best-bets are measured separately because they are curated intent routing, not algorithmic ranking.

## Reading the report

The report shows each configuration in a row so the progression is obvious: baseline keyword at the bottom, tuned semantic at the top, with the lift between them called out. A healthy result looks like a clear jump in Success@1 and NDCG@10, plus a drop in zero-result rate from baseline to tuned.

If tuned is not clearly better than baseline, that is a finding, not a failure. It usually means the test set does not exercise the weaknesses the configuration fixes, or the content genuinely does not contain the answer. Both are worth knowing before you invest further.

## What a report looks like

`reports/relevance-report.md` comes out roughly like this. The numbers below are illustrative, not a promise, but they show the shape of a healthy result.

| Configuration | Success@1 | Success@3 | MRR@10 | NDCG@10 | Zero-result rate |
| --- | --- | --- | --- | --- | --- |
| baseline, keyword | 0.54 | 0.71 | 0.63 | 0.66 | 0.14 |
| tuned, keyword | 0.71 | 0.86 | 0.79 | 0.82 | 0.03 |
| tuned, semantic | 0.83 | 0.94 | 0.88 | 0.90 | 0.03 |

Lift, baseline keyword to tuned semantic: Success@1 +0.29, zero-result rate -0.11.

The exact figures depend on your content and test set. What you are looking for is the direction and size of the gap, not a specific score.

## Building a good test set from query logs

The sample test set is synthetic. For a real PoC, build one from your own search logs:

1. **Take the top queries by volume.** Optimising the head of the distribution helps the most users.
2. **Add the painful tail.** Pull queries that currently return zero results or that users repeat and refine, because those are the failures people remember.
3. **Label the intended documents.** For each query, decide which pages are perfect, strong, partial, or irrelevant answers.
4. **Include variants deliberately.** Add synonyms, abbreviations, and common misspellings of your important queries so the configuration is tested on the messiness it is meant to handle.
5. **Keep it fixed.** Once labelled, do not change the test set between runs, or you cannot compare. Version it alongside the code.

A few hundred labelled queries is plenty to make a confident call. Even fifty well-chosen ones will tell you most of the story.

## Next

For the relevance engineering loop around curation, zero-results, synonyms, typo tolerance, and NDCG, see [06-relevance-engineering.md](06-relevance-engineering.md). If keyword plus semantic is not enough for heavily paraphrased queries, see [05-optional-vector.md](05-optional-vector.md) for the vector and hybrid layer.
