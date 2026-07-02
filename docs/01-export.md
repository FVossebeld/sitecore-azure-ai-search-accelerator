# 01. Export content from Sitecore

This accelerator indexes a folder of JSON documents that follow one canonical
schema. Your job at export time is to get Sitecore content into that shape. This
page covers the headless path first (Sitecore Experience Edge over GraphQL),
then a short note on classic Sitecore XP.

## Why export to Azure AI Search at all

Sitecore's own documentation is clear that the Experience Edge GraphQL `search`
field is designed for filtering content, not for full text or site search, and
recommends a dedicated search service for advanced search. That is the whole
point of this accelerator: pull the published content out of Sitecore once, push
it into Azure AI Search, and do relevance there where you have analyzers,
synonyms, scoring profiles, semantic ranking, and a suggester.

So the flow is not "search Sitecore live." It is "export from Sitecore, index in
Azure AI Search, search there."

## The canonical document

Every document you index is one JSON object like this:

```json
{
  "id": "unique-stable-id",
  "title": "Human readable title",
  "body": "Clean text content. HTML is allowed and will be stripped.",
  "url": "https://example.org/the-page",
  "contentType": "Article",
  "tags": ["topic-a", "topic-b"],
  "lastModified": "2026-01-31T00:00:00Z"
}
```

| Field | Required | Description |
| --- | --- | --- |
| `id` | yes | Stable unique key. In Sitecore this is the item GUID. Reusing it on re-export updates the same document. |
| `title` | yes | Page or article title. Weighted heavily in ranking. |
| `body` | yes | Main text. HTML is stripped during preprocessing. |
| `url` | recommended | Canonical link, used in results and reports. |
| `contentType` | optional | Template or type label (for example Article or FAQ). Lowercased during preprocessing so facets stay consistent. Useful for filtering. |
| `tags` | optional | List of strings. Weighted in ranking and usable as facets. |
| `lastModified` | optional | ISO 8601 timestamp. Drives the freshness boost. |

You can store one object per file, or an array of objects in a single file. Both
are accepted. Put the files in a folder and point the ingest at it.

## Headless: export over Sitecore Experience Edge

Experience Edge is the delivery API for headless Sitecore (XM Cloud and the
Experience Edge for XM connector). It serves published content over GraphQL from
a CDN backed endpoint. The accelerator ships an extractor that talks to it:
`src/ingest/export_edge.py`.

### 1. Get the connection details

You need three things, set in `.env`:

| Variable | What it is |
| --- | --- |
| `SITECORE_EDGE_ENDPOINT` | Delivery GraphQL endpoint, usually `https://edge.sitecorecloud.io/api/graphql/v1`. |
| `SITECORE_EDGE_API_KEY` | A delivery API key. It is sent in the `X-GQL-Token` header. |
| `SITECORE_SITE_ROOT_ID` | The GUID of your site content root. Everything under it is exported. |

Optional variables tune the mapping:

| Variable | Default | What it does |
| --- | --- | --- |
| `SITECORE_LANGUAGE` | `nl-NL` | Language variant to export. |
| `SITECORE_BASE_URL` | empty | Public site base, prefixed to each item path so `url` is absolute. |
| `SITECORE_TEMPLATES` | empty | Comma separated template GUIDs to restrict the export. |
| `SITECORE_TITLE_FIELD` | `Title` | Field mapped to `title`. |
| `SITECORE_BODY_FIELDS` | `Content` | Comma separated fields concatenated into `body`. |
| `SITECORE_TAGS_FIELD` | empty | Field mapped to `tags`. |

Experience Edge has two endpoints. The Delivery endpoint serves published,
CDN backed content and matches values as they are, which is what you want for an
export. The Preview endpoint is tokenized and behaves differently for some
operators. Use Delivery.

### 2. How the export query works

The extractor enumerates published pages with the Edge `search` field. It filters
to items that render as pages and that live under your site root:

```graphql
query Export($after: String, $first: Int) {
  search(
    where: {
      AND: [
        { name: "_path", value: "<SITE-ROOT-GUID>", operator: CONTAINS }
        { name: "_hasLayout", value: "true", operator: EQ }
      ]
    }
    first: $first
    after: $after
  ) {
    total
    pageInfo { endCursor hasNext }
    results {
      id
      __typename
      url { path }
      fields { name value }
    }
  }
}
```

A few things to understand here:

- `_path CONTAINS <guid>` returns the item with that GUID and all of its
  descendants, so pointing it at the site root walks the whole published tree.
- `_hasLayout EQ true` keeps only items that render as pages and drops folders,
  settings items, and datasource plumbing. Add `_templates CONTAINS <guid>`
  clauses (the extractor does this from `SITECORE_TEMPLATES`) to narrow further.
- `results` is a plain list of items, and paging is cursor based. The extractor
  loops on `pageInfo { hasNext endCursor }` until everything is retrieved. Edge
  caps `first` and limits query complexity, so the default page size is small.
- `fields { name value }` returns every published content field, so you do not
  have to hardcode a fragment per template. `__typename` gives the template
  projected type, which the extractor uses as `contentType`.

### 3. Publish the standard fields you need

Standard fields such as `__Updated` and `__Created` are not published to
Experience Edge by default. If you want the freshness boost to work, publish the
standard fields (or the specific ones you need) from the Experience Edge
Connector settings and republish. If they are missing, `lastModified` is simply
left empty and everything else still works.

### 4. Body lives in datasources for component driven pages

On a headless site, the visible copy of a page often does not sit on the route
item. It sits on the datasource items of the components placed on that page. This
accelerator's extractor takes the simple, robust path: it indexes the route
item's own fields (`Title`, `Content`, and whatever you list in
`SITECORE_BODY_FIELDS`). That is a good fit for structured templates such as
Article, FAQ, or Product pages, which is exactly the content that benefits most
from better search.

If your pages are pure component compositions with little on the route item, you
have two options: extend the extractor to read each item's `rendered` Layout
Service JSON and flatten the component datasource fields into `body`, or add the
key content fields directly to your page templates. Start simple and only reach
for the layout flattening if the route item bodies come back thin.

### 5. Run it

First, see the mapping offline with no endpoint or key. The dry run maps a bundled
sample Edge response and prints the canonical documents it would write:

```bash
python -m src.ingest.export_edge --dry-run
```

When your `.env` is set, run the real export:

```bash
python -m src.ingest.export_edge --output ./export
```

This writes `./export/edge-export.json`, an array of canonical documents. Feed
that folder into preprocessing and indexing (see
[02-preprocess.md](02-preprocess.md)).

## Classic Sitecore XP (not headless)

If you are on classic Sitecore XP without Experience Edge, the shape of the task
is the same: enumerate published pages, take the fields you need, and emit
canonical JSON. Common ways to do that:

- **Sitecore PowerShell Extensions.** Script over the published items in the
  Master or Web database, select `Title`, the rich text body field, the URL, and
  `__Updated`, and export to JSON. `data/sample/sitecore-raw/raw-sitecore-export.json` shows
  the raw field names this produces and how they map.
- **Item Service or a custom API.** Page through items over REST and write JSON.
- **Rendered-page crawl.** As a last resort, crawl the published site and take
  the main content region, title, and last modified header. This is the least
  precise option because you inherit navigation and boilerplate, so prefer a
  structured export.

## Field mapping is flexible

You do not have to rename Sitecore fields before export. Preprocessing recognises
common Sitecore field names (`ItemID`, `TemplateName`, `Content`, `__Updated`,
and so on) and maps them to the canonical names. See
[02-preprocess.md](02-preprocess.md) for the full alias list and how to extend
it.

## Practical tips

- **Export published content only.** Use the Delivery endpoint or the Web
  database. Drafts and workflow states add noise.
- **One language at a time.** Export the language you are optimising for and set
  the matching analyzer (see [03-configure.md](03-configure.md)).
- **Keep ids stable.** The item GUID is stable across exports, so re-exporting
  updates documents instead of duplicating them.
- **Include `lastModified` when you can.** Publish `__Updated` to Edge so the
  freshness boost has something to work with.
- **Do not over-collect.** Title, body, url, tags, and a timestamp are enough to
  prove relevance. You can enrich later.

## Next

Once you have a folder of exports, continue to
[02-preprocess.md](02-preprocess.md) to see how the content is cleaned and
mapped before indexing.
