# Re-run the relevance evaluation against the current indexes.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot/..
python -m src.eval.evaluate --compare
