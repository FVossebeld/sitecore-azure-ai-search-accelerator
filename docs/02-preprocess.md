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

You do not need to rename Sitecore fields before export. The preprocessor
recognises common Sitecore field names alongside generic ones and maps them to
the canonical schema. The defaults cover:

| Canonical | Recognised aliases |
| --- | --- |
| `id` | `id`, `ItemID`, `itemId`, `ItemId`, `documentId`, `_id`, `key` |
| `title` | `title`, `Title`, `NavigationTitle`, `PageTitle`, `MetaTitle`, `name`, `heading`, `pageTitle` |
| `body` | `body`, `Content`, `Text`, `MainText`, `content`, `text`, `html`, `Summary`, `Abstract`, `Introduction`, `description` |
| `url` | `url`, `ItemUrl`, `Url`, `link`, `permalink`, `path` |
| `contentType` | `contentType`, `TemplateName`, `type`, `template`, `category` |
| `tags` | `tags`, `Tags`, `keywords`, `Keywords`, `Categories`, `labels`, `topics` |
| `lastModified` | `lastModified`, `__Updated`, `Updated`, `updated`, `modified`, `__Created`, `date`, `updatedAt` |

The `__typename` that the Experience Edge extractor emits is already the
canonical `contentType`, and the raw Sitecore field names (`ItemID`,
`TemplateName`, `Content`, `__Updated`) from a PowerShell or Item Service export
are covered above. If your export uses a name that is not listed, either rename
it during export or add the alias to the mapping in `preprocess.py`. The mapping
is a plain dictionary, so extending it is a one line change.

## HTML stripping

Bodies from Sitecore rich text fields contain HTML. The preprocessor removes
tags and decodes entities, keeping only readable text. This matters because the
analyzer should index words, not `<div>` and `&nbsp;`. Titles are treated as
plain text and only trimmed. Sitecore basic ISO dates such as `20260131T000000Z`
and multivalue fields delimited by `|` are normalised here too.

## Why not chunk here

Chunking (splitting long pages into passages) helps vector search and long
documents. For a navigational relevance PoC it usually adds noise, because the
unit you want to return is the page, not a fragment of it. The accelerator keeps
one document per page by default. If you enable the optional vector layer and
your pages are long, chunking is the first thing to add, and
[05-optional-vector.md](05-optional-vector.md) points to where.

## Running it

Preprocessing runs automatically as part of ingest. You rarely call it directly.
To see the raw-to-canonical mapping on the bundled Sitecore sample, run it with
`--show`:

```bash
python -m src.ingest.preprocess --input data/sample/sitecore-raw --show 2
```

That reads `data/sample/sitecore-raw/raw-sitecore-export.json` (PascalCase
`TemplateName`, HTML bodies, pipe-delimited tags, basic ISO dates) and prints the
cleaned canonical documents: HTML stripped, tags split into a list, dates
normalised, and `contentType` lowercased. Point `--input` at your own export
folder to check your content the same way:

```bash
python -m src.ingest.preprocess --input ./path/to/export --show 2
```

Check that titles and bodies look clean and that `lastModified` parsed correctly.
If a lot of documents were dropped, your alias mapping probably missed the title
or body field.

## Next

Continue to [03-configure.md](03-configure.md) to see the relevance
configuration that is applied to the tuned index.
