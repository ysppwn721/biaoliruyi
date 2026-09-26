$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)

$python = if (Test-Path '.venv\Scripts\python.exe') { '.venv\Scripts\python.exe' } else { 'python' }
& $python -m PyInstaller --clean --noconfirm packaging\zhilian.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }

$version = '0.2.1'
$artifactDir = Join-Path (Get-Location) 'artifacts'
New-Item -ItemType Directory -Force -Path $artifactDir | Out-Null
$zip = Join-Path $artifactDir "Zhilian-$version-windows-x64.zip"
if (Test-Path $zip) { Remove-Item -LiteralPath $zip -Force }
Compress-Archive -Path 'dist\Zhilian' -DestinationPath $zip -CompressionLevel Optimal
Write-Host "Created $zip"
