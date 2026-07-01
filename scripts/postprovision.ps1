# Postprovision hook for azd. Configures indexes, loads the sample dataset,
# and runs the before/after relevance evaluation.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot/..

Write-Host "==> Writing azd outputs to .env"
azd env get-values | Out-File -FilePath ".env" -Encoding utf8

Write-Host "==> Installing Python dependencies"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

Write-Host "==> Creating indexes and loading the sample dataset"
# RBAC role assignments can take a minute to propagate after provisioning, so retry.
$max = 6
for ($attempt = 1; $attempt -le $max; $attempt++) {
    python -m src.ingest.push_to_index --both --load-sample
    if ($LASTEXITCODE -eq 0) { break }
    if ($attempt -eq $max) { throw "Ingest failed after $max attempts." }
    Write-Warning "Ingest attempt $attempt failed (exit $LASTEXITCODE). Waiting 30s for role propagation..."
    Start-Sleep -Seconds 30
}

Write-Host "==> Running the relevance evaluation"
python -m src.eval.evaluate --compare

Write-Host ""
Write-Host "Done. Open ./reports/relevance-report.md to see the before/after results."
