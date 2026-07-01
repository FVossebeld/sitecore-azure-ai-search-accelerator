# 01. Export content from any CMS

The accelerator is content-platform agnostic. It reads a folder of JSON files
that follow one canonical schema. Your only job at export time is to get your
content into that shape. This page explains the shape and the common ways to
produce it.

## The canonical document

Every document you index is one JSON object like this:

```json
{
  "id": "unique-stable-id",
  "title": "Human readable title",
  "body": "Clean text content. HTML is allowed and will be stripped.",
  "url": "https://example.org/the-page",
  "contentType": "article",
  "tags": ["topic-a", "topic-b"],
  "lastModified": "2026-01-31T00:00:00Z"
}
```

| Field | Required | Description |
| --- | --- | --- |
| `id` | yes | Stable unique key. Reusing it on re-export updates the same document. |
| `title` | yes | Page or article title. Weighted heavily in ranking. |
| `body` | yes | Main text. HTML is stripped during preprocessing. |
| `url` | recommended | Canonical link, used in results and reports. |
| `contentType` | optional | Free text label (article, faq, product, and so on). Useful for filtering. |
| `tags` | optional | List of strings. Weighted in ranking and usable as facets. |
| `lastModified` | optional | ISO 8601 timestamp. Drives the freshness boost. |

You can store one object per file, or an array of objects in a single file. Both
are accepted. Put the files in a folder and point the ingest at it.

## Field mapping is flexible

You do not have to rename your fields before export. The preprocessing step
recognises common aliases and maps them to the canonical names. For example
`name`, `heading`, or `pageTitle` map to `title`, and `content`, `text`, or
`html` map to `body`. See [02-preprocess.md](02-preprocess.md) for the full
alias list and how to extend it.

## Common ways to produce the export

The right approach depends on your platform, but they fall into a few patterns.

### Content API or headless query

Most modern CMS platforms expose a REST or GraphQL API. Page through the
published items and write each one as a JSON object. This is the cleanest option
because you control exactly which fields and which language variants you take.

### Built-in item or page export

Many platforms have an export function (item export, site export, or a content
migration tool). Export the published tree, then run a small transform to select
the fields you need and drop them into the canonical shape.

### Rendered-page crawl

If you cannot get structured content, crawl the published site. Fetch each URL,
take the main content region, the title, and the last-modified header, and emit
the canonical JSON. This is the least precise option because you inherit
navigation and boilerplate, so prefer a structured export when one exists.

## Practical tips

- **Export published content only.** Drafts and archived items add noise.
- **One language at a time.** If your site is multilingual, export the language
  you are optimising for and set the matching analyzer (see
  [03-configure.md](03-configure.md)).
- **Keep ids stable.** If ids change on every export you will create duplicates
  instead of updates.
- **Include `lastModified` when you can.** The freshness boost is only as good as
  the timestamps you provide.
- **Do not over-collect.** Title, body, url, tags, and a timestamp are enough to
  prove relevance. You can enrich later.

## Next

Once you have a folder of exports, continue to
[02-preprocess.md](02-preprocess.md) to see how the content is cleaned and
mapped before indexing.
