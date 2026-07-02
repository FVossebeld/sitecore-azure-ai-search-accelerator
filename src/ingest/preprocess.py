"""Turn a raw Sitecore export into the canonical schema the index expects.

Canonical document contract (this is what a Sitecore item export must map to):

    {
      "id":           "unique-stable-id",
      "title":        "Human readable title",
      "body":         "Clean plain text (HTML is stripped)",
      "url":          "https://example.org/page",
      "contentType":  "article | faq | product | ...",
      "tags":         ["tag-a", "tag-b"],
      "lastModified": "2026-01-31T00:00:00Z"
    }

The loader accepts JSON files that contain either a single object or an array of
objects, so you can drop your own export into a folder and point the tooling at it.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from src.common.settings import SAMPLE_CONTENT_DIR

CANONICAL_FIELDS = ("id", "title", "body", "url", "contentType", "tags", "lastModified")

# Source field names mapped to the canonical name. Canonical names win when both
# are present. The aliases cover the field names Sitecore items commonly expose
# (template fields plus standard fields such as __Updated). Extend for your own
# templates.
FIELD_ALIASES = {
    "id": ["id", "ItemID", "itemId", "ItemId", "documentId", "_id", "key"],
    "title": ["title", "Title", "NavigationTitle", "PageTitle", "MetaTitle", "name", "heading", "pageTitle"],
    "body": ["body", "Content", "Text", "MainText", "content", "text", "html", "Summary", "Abstract", "Introduction", "description"],
    "url": ["url", "ItemUrl", "Url", "link", "permalink", "path"],
    "contentType": ["contentType", "TemplateName", "type", "template", "category"],
    "tags": ["tags", "Tags", "keywords", "Keywords", "Categories", "labels", "topics"],
    "lastModified": ["lastModified", "__Updated", "Updated", "updated", "modified", "__Created", "date", "updatedAt"],
}


def strip_html(value: str) -> str:
    if not value:
        return ""
    if "<" in value and ">" in value:
        text = BeautifulSoup(value, "html.parser").get_text(separator=" ")
    else:
        text = value
    return " ".join(text.split())


def _first_present(raw: dict[str, Any], names: list[str]) -> Any:
    for name in names:
        if name in raw and raw[name] not in (None, ""):
            return raw[name]
    return None


def _normalize_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        # Sitecore multilist fields are pipe delimited; also accept comma/semicolon.
        parts = [p.strip() for p in value.replace(";", ",").replace("|", ",").split(",")]
        return [p for p in parts if p]
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value)]


def _normalize_datetime(value: Any) -> str:
    if not value:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, str):
        text = value.strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            pass
        # Sitecore stores dates in basic ISO 8601 form, e.g. 20260131T000000Z.
        try:
            parsed = datetime.strptime(text, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            # Unparseable date: fall back to "now" so the freshness scoring
            # profile still has a value to work with. If exact freshness matters,
            # fix the source field rather than trusting this fallback.
            return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(value)


def to_canonical(raw: dict[str, Any]) -> dict[str, Any]:
    doc = {}
    for field, aliases in FIELD_ALIASES.items():
        doc[field] = _first_present(raw, aliases)
    doc["title"] = strip_html(doc.get("title") or "")
    doc["body"] = strip_html(doc.get("body") or "")
    doc["tags"] = _normalize_tags(doc.get("tags"))
    doc["url"] = (doc.get("url") or "").strip()
    # Lowercase so a Sitecore template name (for example "Article") and a hand
    # written "article" land in the same facet bucket regardless of source.
    doc["contentType"] = (doc.get("contentType") or "page").strip().lower()
    doc["lastModified"] = _normalize_datetime(doc.get("lastModified"))
    if not doc.get("id"):
        raise ValueError(f"Document is missing an id: {raw!r}")
    doc["id"] = str(doc["id"])
    return doc


def load_raw(input_dir: Path) -> list[dict[str, Any]]:
    input_dir = Path(input_dir)
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")
    raws: list[dict[str, Any]] = []
    for path in sorted(input_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            raws.extend(data)
        elif isinstance(data, dict) and "value" in data and isinstance(data["value"], list):
            raws.extend(data["value"])
        else:
            raws.append(data)
    return raws


def load_and_preprocess(input_dir: Path | None = None) -> list[dict[str, Any]]:
    input_dir = Path(input_dir) if input_dir else SAMPLE_CONTENT_DIR
    return [to_canonical(raw) for raw in load_raw(input_dir)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Preprocess a content export into canonical JSON.")
    parser.add_argument("--input", type=Path, default=SAMPLE_CONTENT_DIR, help="Folder with source *.json files.")
    parser.add_argument("--output", type=Path, help="Optional path to write the canonical JSON array.")
    parser.add_argument("--show", type=int, metavar="N", help="Print the first N canonical documents to the screen.")
    args = parser.parse_args()

    docs = load_and_preprocess(args.input)
    print(f"Preprocessed {len(docs)} documents from {args.input}")
    if args.show:
        preview = docs[: args.show]
        print(json.dumps(preview, ensure_ascii=False, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote canonical documents to {args.output}")


if __name__ == "__main__":
    main()
