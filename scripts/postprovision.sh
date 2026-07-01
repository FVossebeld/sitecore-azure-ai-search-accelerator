#!/bin/sh
# Postprovision hook for azd. Configures indexes, loads the sample dataset,
# and runs the before/after relevance evaluation.
set -e
cd "$(dirname "$0")/.."

PY="$(command -v python3 || command -v python)"
if [ -z "$PY" ]; then
  echo "Python 3 is required but was not found on PATH." >&2
  exit 1
fi

echo "==> Writing azd outputs to .env"
azd env get-values > .env

echo "==> Installing Python dependencies"
"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install --quiet -r requirements.txt

echo "==> Creating indexes and loading the sample dataset"
# RBAC role assignments can take a minute to propagate after provisioning, so retry.
attempt=1
max=6
while true; do
  if "$PY" -m src.ingest.push_to_index --both --load-sample; then
    break
  fi
  if [ "$attempt" -ge "$max" ]; then
    echo "Ingest failed after $max attempts." >&2
    exit 1
  fi
  echo "Ingest attempt $attempt failed. Waiting 30s for role propagation..." >&2
  attempt=$((attempt + 1))
  sleep 30
done

echo "==> Running the relevance evaluation"
"$PY" -m src.eval.evaluate --compare

echo ""
echo "Done. Open ./reports/relevance-report.md to see the before/after results."
