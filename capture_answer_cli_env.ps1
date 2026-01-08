# capture_answer_cli_env.ps1
# 用途：把 answer_cli 相关的环境变量与可能的配置项快速抓取出来，便于定位你到底在连哪一个 LLM base_url。
# 说明：不会上传任何内容；只是输出到本地终端。

Write-Host "== Python ==" -ForegroundColor Cyan
python --version

Write-Host "`n== Venv ==" -ForegroundColor Cyan
python -c "import sys; print(sys.executable); print(sys.prefix)"

Write-Host "`n== Key ENV ==" -ForegroundColor Cyan
$keys = @(
  "OPENAI_API_BASE","OPENAI_BASE_URL","OPENAI_API_KEY",
  "LLM_BASE_URL","LLM_API_BASE","LLM_API_KEY",
  "HTTP_PROXY","HTTPS_PROXY","ALL_PROXY","NO_PROXY"
)
foreach ($k in $keys) {
  $v = [Environment]::GetEnvironmentVariable($k, "Process")
  if (-not $v) { $v = [Environment]::GetEnvironmentVariable($k, "User") }
  if (-not $v) { $v = [Environment]::GetEnvironmentVariable($k, "Machine") }
  if ($v) { Write-Host ("{0}={1}" -f $k,$v) }
}

Write-Host "`n== Config files (best-effort) ==" -ForegroundColor Cyan
$paths = @(".\config.yaml",".\config.yml",".\rag\config.yaml",".\rag\config.yml",".\settings.json",".\rag\settings.json")
foreach ($p in $paths) {
  if (Test-Path $p) {
    Write-Host "---- $p ----" -ForegroundColor Yellow
    Get-Content $p -TotalCount 200
  }
}

Write-Host "`nDONE" -ForegroundColor Green
