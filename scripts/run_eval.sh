#!/bin/sh
# Re-run the relevance evaluation against the current indexes.
set -e
cd "$(dirname "$0")/.."
PY="$(command -v python3 || command -v python)"
"$PY" -m src.eval.evaluate --compare
