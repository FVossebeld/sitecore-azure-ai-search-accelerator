"""Export published content from Sitecore Experience Edge (headless) to canonical JSON.

Sitecore's own guidance is that the Experience Edge GraphQL ``search`` is meant
for filtering content, not for site search, and that you should push content to a
dedicated search service for real relevance. That is exactly what this script
does: it enumerates the published pages of a headless site over Experience Edge
and writes them as the canonical documents the accelerator indexes.

How it works:

* Runs the Edge ``search`` query filtered to items that render as pages
  (``_hasLayout = true``) under a site root (``_path CONTAINS <root id>``), with
  optional template filtering.
* Pages through the cursor connection (``pageInfo { hasNext endCursor }``) until
  every published item is retrieved. Experience Edge caps ``first`` and limits
  query complexity, so the default page size is conservative.
* Reads each item's content fields with ``fields { name value }`` and maps them
  to the canonical schema. Rich-text HTML is left in place and stripped later by
  the preprocessing step.

Standard fields such as ``__Updated`` are only present if they were published to
Experience Edge. If they are missing, publish the standard fields (or the
specific ones you need) from the Experience Edge Connector and republish.

Configuration is read from environment variables (see ``.env.sample``):

    SITECORE_EDGE_ENDPOINT   Delivery GraphQL endpoint, e.g.
                             https://edge.sitecorecloud.io/api/graphql/v1
    SITECORE_EDGE_API_KEY    Delivery API key, sent in the X-GQL-Token header
    SITECORE_SITE_ROOT_ID    GUID of the site content root (used in _path)
    SITECORE_LANGUAGE        Language to export, e.g. nl-NL
    SITECORE_BASE_URL        Public site base URL, prefixed to each item path
    SITECORE_TEMPLATES       Optional comma separated template GUIDs to include
    SITECORE_TITLE_FIELD     Field mapped to title (default: Title)
    SITECORE_BODY_FIELDS     Comma separated fields concatenated into body
                             (default: Content)
    SITECORE_TAGS_FIELD      Optional field mapped to tags

Usage:

    python -m src.ingest.export_edge --output ./export
    python -m src.ingest.push_to_index --both --input ./export
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_ENDPOINT = "https://edge.sitecorecloud.io/api/graphql/v1"
DEFAULT_PAGE_SIZE = 20

# Bundled Experience Edge "search" response used by --dry-run so the mapping can
# be demonstrated offline, with no endpoint, API key, or site root required.
SAMPLE_EDGE_RESPONSE = Path(__file__).resolve().parents[2] / "data" / "sample" / "edge-response-sample.json"


def _clause(name: str, value: str, operator: str) -> str:
    return f'{{ name: "{name}", value: "{value}", operator: {operator} }}'


def build_search_query(
    root_id: str,
    template_ids: list[str] | None = None,
    has_layout: bool = True,
) -> str:
    """Return the Experience Edge search query used to enumerate published pages.

    ``after`` is supplied as a GraphQL variable so the same query text is reused
    for every page of the cursor connection.
    """
    clauses = [_clause("_path", root_id, "CONTAINS")]
    if has_layout:
        clauses.append(_clause("_hasLayout", "true", "EQ"))
    if template_ids:
        template_or = ", ".join(_clause("_templates", t.strip(), "CONTAINS") for t in template_ids if t.strip())
        if template_or:
            clauses.append(f"{{ OR: [ {template_or} ] }}")
    where = "{ AND: [ " + ", ".join(clauses) + " ] }"
    return (
        "query Export($after: String, $first: Int) {\n"
        f"  search(where: {where}, first: $first, after: $after) {{\n"
        "    total\n"
        "    pageInfo { endCursor hasNext }\n"
        "    results {\n"
        "      id\n"
        "      __typename\n"
        "      url { path }\n"
        "      fields { name value }\n"
        "    }\n"
        "  }\n"
        "}\n"
    )


def edge_item_to_canonical(
    item: dict[str, Any],
    base_url: str = "",
    title_field: str = "Title",
    body_fields: tuple[str, ...] = ("Content",),
    tags_field: str | None = None,
) -> dict[str, Any]:
    """Map one Experience Edge search result to a canonical document.

    HTML is preserved here and stripped later by the preprocessing step, so this
    stays a pure, side-effect-free mapping that is easy to unit test.
    """
    field_map = {f.get("name"): f.get("value") for f in item.get("fields", []) if f.get("name")}
    path = ((item.get("url") or {}).get("path") or "").strip()
    url = f"{base_url.rstrip('/')}{path}" if base_url and path.startswith("/") else (base_url or path)

    body_parts = [field_map.get(name, "") for name in body_fields]
    doc: dict[str, Any] = {
        "id": item.get("id"),
        "title": field_map.get(title_field, ""),
        "body": " ".join(part for part in body_parts if part),
        "url": url,
        "contentType": item.get("__typename") or "page",
        "lastModified": field_map.get("__Updated") or field_map.get("__Created"),
    }
    if tags_field:
        doc["tags"] = field_map.get(tags_field, "")
    return doc


def _post_graphql(endpoint: str, api_key: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = urllib.request.Request(endpoint, data=payload, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("X-GQL-Token", api_key)
    with urllib.request.urlopen(request, timeout=60) as response:
        body = json.loads(response.read().decode("utf-8"))
    if body.get("errors"):
        raise RuntimeError(f"Experience Edge returned errors: {body['errors']}")
    return body["data"]["search"]


def export_all(
    endpoint: str,
    api_key: str,
    root_id: str,
    template_ids: list[str] | None = None,
    base_url: str = "",
    title_field: str = "Title",
    body_fields: tuple[str, ...] = ("Content",),
    tags_field: str | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    throttle_seconds: float = 0.0,
) -> list[dict[str, Any]]:
    """Page through the Edge search connection and return canonical documents."""
    query = build_search_query(root_id, template_ids)
    docs: list[dict[str, Any]] = []
    after: str | None = None
    while True:
        search = _post_graphql(endpoint, api_key, query, {"after": after, "first": page_size})
        for item in search.get("results", []):
            docs.append(
                edge_item_to_canonical(item, base_url, title_field, body_fields, tags_field)
            )
        page_info = search.get("pageInfo") or {}
        if not page_info.get("hasNext"):
            break
        after = page_info.get("endCursor")
        if throttle_seconds:
            time.sleep(throttle_seconds)
    return docs


def main() -> None:
    parser = argparse.ArgumentParser(description="Export published content from Sitecore Experience Edge.")
    parser.add_argument("--output", type=Path, default=Path("export"), help="Folder to write the export JSON into.")
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE, help="Items per Edge request (keep small for query complexity).")
    parser.add_argument("--throttle", type=float, default=0.0, help="Seconds to wait between pages.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Map the bundled sample Edge response offline (no endpoint/key needed) and print the canonical documents.",
    )
    args = parser.parse_args()

    title_field = os.environ.get("SITECORE_TITLE_FIELD", "Title")
    body_fields = tuple(f.strip() for f in os.environ.get("SITECORE_BODY_FIELDS", "Content").split(",") if f.strip())
    tags_field = os.environ.get("SITECORE_TAGS_FIELD") or "Tags"

    if args.dry_run:
        sample = json.loads(SAMPLE_EDGE_RESPONSE.read_text(encoding="utf-8"))
        docs = [
            edge_item_to_canonical(item, "https://www.example.org", title_field, body_fields, tags_field)
            for item in sample.get("results", [])
        ]
        print(f"Dry run mapped {len(docs)} sample Edge items (no network calls).")
        print(json.dumps(docs, ensure_ascii=False, indent=2))
        print(
            "\nThis is exactly what export_edge writes. The next step "
            "(python -m src.ingest.preprocess) strips the HTML and lowercases contentType."
        )
        return

    endpoint = os.environ.get("SITECORE_EDGE_ENDPOINT", DEFAULT_ENDPOINT)
    api_key = os.environ.get("SITECORE_EDGE_API_KEY", "")
    root_id = os.environ.get("SITECORE_SITE_ROOT_ID", "")
    base_url = os.environ.get("SITECORE_BASE_URL", "")
    templates = [t for t in os.environ.get("SITECORE_TEMPLATES", "").split(",") if t.strip()] or None
    tags_field = os.environ.get("SITECORE_TAGS_FIELD") or None

    if not api_key or not root_id:
        raise SystemExit(
            "Set SITECORE_EDGE_API_KEY and SITECORE_SITE_ROOT_ID (and usually "
            "SITECORE_EDGE_ENDPOINT and SITECORE_BASE_URL). See .env.sample."
        )

    docs = export_all(
        endpoint=endpoint,
        api_key=api_key,
        root_id=root_id,
        template_ids=templates,
        base_url=base_url,
        title_field=title_field,
        body_fields=body_fields,
        tags_field=tags_field,
        page_size=args.page_size,
        throttle_seconds=args.throttle,
    )

    args.output.mkdir(parents=True, exist_ok=True)
    out_file = args.output / "edge-export.json"
    out_file.write_text(json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Exported {len(docs)} items to {out_file}")


if __name__ == "__main__":
    main()
