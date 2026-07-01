# 04. Evaluate

A relevance PoC is only convincing if it is measured. This step runs a fixed set
of queries against both indexes and reports where the intended answer lands. The
logic is in `src/eval/evaluate.py` and the reporting in `src/eval/report.py`.

## The test set

The test set is a CSV with two columns:

```csv
query,intended_id
paspoort aanvragen,doc-paspoort
id kaart kind,doc-identiteitskaart
fysio vergoeding,doc-fysiotherapie
```

- `query`: what a user types. Include the messy real-world variants: synonyms,
  abbreviations, and misspellings.
- `intended_id`: the `id` of the document that should come back for that query.

The bundled `data/sample/testset.csv` has 35 rows over the sample content,
including synonym and misspelling cases, so you can see the metrics move.

## Metrics

For each query the evaluator finds the rank of the intended document and
aggregates:

| Metric | Meaning | Why it matters |
| --- | --- | --- |
| **Success@1** | The intended doc is the first result | The headline metric for navigational site search |
| **Success@3** | It is in the top 3 | Tolerance for near-misses |
| **MRR@10** | Mean reciprocal rank over the top 10 | Rewards getting the answer higher, not just present |
| **Found@10** | It appears anywhere in the top 10 | Recall check |
| **Zero-result rate** | Share of queries returning nothing | Directly ties to the "no results" complaint |

For a website search where people expect to land on the right page immediately,
Success@1 is usually the number to lead with. Zero-result rate is the second,
because empty results are the most visible failure.

## Running the evaluation

The default run compares the configurations side by side:

```bash
python -m src.eval.evaluate --compare
```

This evaluates:

- baseline, keyword only
- tuned, keyword only
- tuned, semantic ranker
- tuned, hybrid (only when the vector layer is enabled)

It writes `reports/relevance-report.md` with a table and a lift line, plus CSV
summaries under `reports/`. To evaluate a single configuration:

```bash
python -m src.eval.evaluate --variant tuned --mode semantic
```

## Reading the report

The report shows each configuration in a row so the progression is obvious:
baseline keyword at the bottom, tuned semantic at the top, with the lift between
them called out. A healthy result looks like a clear jump in Success@1 and a drop
in zero-result rate from baseline to tuned.

If tuned is not clearly better than baseline, that is a finding, not a failure. It
usually means the test set does not exercise the weaknesses the configuration
fixes, or the content genuinely does not contain the answer. Both are worth
knowing before you invest further.

## Building a good test set from query logs

The sample test set is synthetic. For a real PoC, build one from your own search
logs:

1. **Take the top queries by volume.** Optimising the head of the distribution
   helps the most users.
2. **Add the painful tail.** Pull queries that currently return zero results or
   that users repeat and refine, because those are the failures people remember.
3. **Label the intended document.** For each query, decide which page is the right
   answer and record its `id`. This is the only manual step and it is worth doing
   carefully, because the whole evaluation rests on it.
4. **Include variants deliberately.** Add synonyms, abbreviations, and common
   misspellings of your important queries so the configuration is tested on the
   messiness it is meant to handle.
5. **Keep it fixed.** Once labelled, do not change the test set between runs, or
   you cannot compare. Version it alongside the code.

A few hundred labelled queries is plenty to make a confident call. Even fifty
well-chosen ones will tell you most of the story.

## Next

If keyword plus semantic is not enough for heavily paraphrased queries, see
[05-optional-vector.md](05-optional-vector.md) for the vector and hybrid layer.
