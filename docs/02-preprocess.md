# 02. Preprocess and map to the canonical schema

Preprocessing turns your raw export into clean, consistent documents ready for
indexing. It is deliberately small and readable so you can adapt it to your
content. The logic lives in `src/ingest/preprocess.py`.

## What preprocessing does

For every input document it:

1. **Maps field aliases** to the canonical names (`title`, `body`, and so on).
2. **Strips HTML** from the body and collapses whitespace, so ranking sees clean
   text instead of markup.
3. **Normalises tags** into a list of trimmed strings.
4. **Normalises `lastModified`** into an ISO 8601 timestamp with a `Z` suffix,
   which is what the index expects.
5. **Drops documents** that have no usable title or body.

The output is a list of canonical documents held in memory and passed straight to
the indexer. Nothing is written to disk in between.

## Field alias mapping

You do not need to rename fields before export. The preprocessor recognises
common names and maps them to the canonical schema. The defaults cover:

| Canonical | Recognised aliases |
| --- | --- |
| `id` | `id`, `itemId`, `documentId`, `key` |
| `title` | `title`, `name`, `heading`, `pageTitle` |
| `body` | `body`, `content`, `text`, `html`, `description` |
| `url` | `url`, `link`, `permalink`, `path` |
| `contentType` | `contentType`, `type`, `template`, `category` |
| `tags` | `tags`, `keywords`, `labels`, `topics` |
| `lastModified` | `lastModified`, `updated`, `modified`, `date`, `updatedAt` |

If your export uses a name that is not listed, either rename it during export or
add the alias to the mapping in `preprocess.py`. The mapping is a plain
dictionary, so extending it is a one line change.

## HTML stripping

Bodies often contain HTML from the CMS. The preprocessor removes tags and
decodes entities, keeping only readable text. This matters because the analyzer
should index words, not `<div>` and `&nbsp;`. Titles are treated as plain text
and only trimmed.

## Why not chunk here

Chunking (splitting long pages into passages) helps vector search and long
documents. For a navigational relevance PoC it usually adds noise, because the
unit you want to return is the page, not a fragment of it. The accelerator keeps
one document per page by default. If you enable the optional vector layer and
your pages are long, chunking is the first thing to add, and
[05-optional-vector.md](05-optional-vector.md) points to where.

## Running it

Preprocessing runs automatically as part of ingest. You rarely call it directly.
To inspect the result for your own export:

```bash
python -c "from src.ingest.preprocess import load_and_preprocess; \
docs = load_and_preprocess('./path/to/export'); \
print(len(docs), 'documents'); print(docs[0])"
```

Check that titles and bodies look clean and that `lastModified` parsed correctly.
If a lot of documents were dropped, your alias mapping probably missed the title
or body field.

## Next

Continue to [03-configure.md](03-configure.md) to see the relevance
configuration that is applied to the tuned index.
