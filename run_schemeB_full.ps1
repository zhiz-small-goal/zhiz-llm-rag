$ErrorActionPreference = "Stop"

# Ensure we run from repo root (this script's directory)
Set-Location -Path $PSScriptRoot

# Choose python: prefer venv if present
$py = "python"
if (Test-Path ".\.venv_rag\Scripts\python.exe") {
  $py = ".\.venv_rag\Scripts\python.exe"
}

# Ensure output dirs exist
if (-not (Test-Path ".\data_processed")) { New-Item -ItemType Directory -Path ".\data_processed" | Out-Null }
if (-not (Test-Path ".\data_processed\build_reports")) { New-Item -ItemType Directory -Path ".\data_processed\build_reports" | Out-Null }

Write-Host "[1/2] Capture environment report..."
& $py "tools\capture_rag_env.py" --out "data_processed\env_report.json"

Write-Host "[2/2] Run profile with timing (smoke)..."
& $py "tools\run_profile_with_timing.py" --profile "build_profile_schemeB.json" --smoke

Write-Host "[OK] smoke run finished."
