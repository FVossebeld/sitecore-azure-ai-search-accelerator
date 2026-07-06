"""Offline validator for Solr synonym rules."""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from src.common.settings import SYNONYMS_DIR

DEFAULT_SYNONYMS_FILE = SYNONYMS_DIR / "nl-synonyms.txt"
MAX_CLUSTER_SIZE = 8


@dataclass(frozen=True)
class ParsedRule:
    line_no: int
    raw: str
    kind: str
    left_terms: list[str]
    right_terms: list[str]

    @property
    def trigger_terms(self) -> list[str]:
        return self.left_terms

    @property
    def all_terms(self) -> list[str]:
        return [*self.left_terms, *self.right_terms]


def _split_terms(value: str) -> list[str]:
    return [term.strip() for term in value.split(",") if term.strip()]


def _load_rule_lines(path: Path) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append((line_no, stripped))
    return lines


def parse_rules(path: Path) -> tuple[list[ParsedRule], list[str]]:
    rules: list[ParsedRule] = []
    errors: list[str] = []
    for line_no, raw in _load_rule_lines(path):
        if "=>" in raw:
            left, right = raw.split("=>", 1)
            left_terms = _split_terms(left)
            right_terms = _split_terms(right)
            if not left_terms or not right_terms:
                errors.append(f"line {line_no}: malformed directional rule, left and right must be non-empty")
            rules.append(ParsedRule(line_no, raw, "directional", left_terms, right_terms))
            continue

        terms = _split_terms(raw)
        if len(terms) <= 1:
            errors.append(f"line {line_no}: malformed equivalency rule, need at least two terms")
        rules.append(ParsedRule(line_no, raw, "equivalency", terms, []))
    return rules, errors


def validate(path: Path) -> tuple[list[ParsedRule], list[str], list[str]]:
    rules, errors = parse_rules(path)
    warnings: list[str] = []
    trigger_locations: dict[str, list[int]] = defaultdict(list)

    for rule in rules:
        trigger_size = len(rule.trigger_terms)
        if trigger_size > MAX_CLUSTER_SIZE:
            warnings.append(
                f"line {rule.line_no}: trigger set has {trigger_size} terms, possibly over-broad"
            )
        for term in rule.trigger_terms:
            key = term.casefold()
            if rule.line_no not in trigger_locations[key]:
                trigger_locations[key].append(rule.line_no)

    for term, line_numbers in sorted(trigger_locations.items()):
        if len(line_numbers) > 1:
            refs = ", ".join(str(n) for n in line_numbers)
            errors.append(f"term {term!r} appears in more than one trigger set, lines {refs}")

    return rules, warnings, errors


def print_report(path: Path, rules: list[ParsedRule], warnings: list[str], errors: list[str]) -> None:
    equivalency = sum(1 for rule in rules if rule.kind == "equivalency")
    directional = sum(1 for rule in rules if rule.kind == "directional")
    unique_terms = {term.casefold() for rule in rules for term in rule.all_terms}

    print(f"Synonym validation: {path}")
    print(f"Total rules: {len(rules)}")
    print(f"Equivalency rules: {equivalency}")
    print(f"Directional rules: {directional}")
    print(f"Unique terms: {len(unique_terms)}")
    print(f"Warnings: {len(warnings)}")
    for warning in warnings:
        print(f"  WARN {warning}")
    print(f"Errors: {len(errors)}")
    for error in errors:
        print(f"  ERROR {error}")
    if not warnings and not errors:
        print("Summary: OK")
    elif errors:
        print("Summary: errors found")
    else:
        print("Summary: warnings only")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Solr synonym rules offline.")
    parser.add_argument("--path", type=Path, default=DEFAULT_SYNONYMS_FILE)
    parser.add_argument("--strict", action="store_true", help="Exit with code 1 when error-level issues exist.")
    args = parser.parse_args()

    rules, warnings, errors = validate(args.path)
    print_report(args.path, rules, warnings, errors)
    if args.strict and errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
