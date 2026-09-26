$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)

$python = if (Test-Path '.venv\Scripts\python.exe') { '.venv\Scripts\python.exe' } else { 'python' }
& $python -m PyInstaller --clean --noconfirm packaging\zhilian.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }

# Pillow's optional AVIF codec is not used by the document workflow and adds
# about 7.5 MB to the frozen Windows bundle. Keep the base package below the
# 25 MiB per-file limit of static download hosts.
Get-ChildItem -Path 'dist\Zhilian' -Recurse -File -Filter '*avif*' |
    Remove-Item -Force -ErrorAction SilentlyContinue

$version = '0.2.1'
$artifactDir = Join-Path (Get-Location) 'artifacts'
New-Item -ItemType Directory -Force -Path $artifactDir | Out-Null
$zip = Join-Path $artifactDir "Zhilian-$version-windows-x64.zip"
if (Test-Path $zip) { Remove-Item -LiteralPath $zip -Force }
Compress-Archive -Path 'dist\Zhilian' -DestinationPath $zip -CompressionLevel Optimal
Write-Host "Created $zip"
