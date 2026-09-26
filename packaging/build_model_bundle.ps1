$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$model = 'models\bge-reranker-v2-m3-onnx-int8'
if (-not (Test-Path -LiteralPath $model)) { throw "Model directory missing: $model" }
$artifactDir = 'artifacts'
New-Item -ItemType Directory -Force -Path $artifactDir | Out-Null
$zip = Join-Path $artifactDir 'Zhilian-bge-reranker-v2-m3-onnx-int8.zip'
if (Test-Path $zip) { Remove-Item -LiteralPath $zip -Force }
Compress-Archive -Path $model -DestinationPath $zip -CompressionLevel Optimal
Write-Host "Created $zip"
