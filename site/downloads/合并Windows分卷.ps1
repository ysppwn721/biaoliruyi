$ErrorActionPreference = 'Stop'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$part0 = Join-Path $dir '知链_v0.2.1_Windows免安装.zip.000'
$part1 = Join-Path $dir '知链_v0.2.1_Windows免安装.zip.001'
$out = Join-Path $dir '知链_v0.2.1_Windows免安装.zip'
$stream = [System.IO.File]::Open($out, [System.IO.FileMode]::Create)
try {
  foreach ($part in @($part0, $part1)) {
    $bytes = [System.IO.File]::ReadAllBytes($part)
    $stream.Write($bytes, 0, $bytes.Length)
  }
} finally { $stream.Dispose() }
Write-Host "已生成 $out"
