$ErrorActionPreference = 'Stop'
$root = Join-Path $PSScriptRoot 'public_data'
New-Item -ItemType Directory -Force $root | Out-Null

function Clone-Shallow($url, $name, $commit) {
  $target = Join-Path $root $name
  if (-not (Test-Path $target)) {
    git clone --depth 1 $url $target
  }
  git -C $target fetch --depth 1 origin $commit
  git -C $target checkout --detach $commit
}

# MIT datasets. Keep them outside the source package and retain LICENSE files.
Clone-Shallow 'https://github.com/czyssrs/FinQA.git' 'FinQA' '0f16e2867befa6840783e58be38c9efb9229d742'
Clone-Shallow 'https://github.com/NExTplusplus/TAT-QA.git' 'TAT-QA' '870accc41953dcde885aabeb963d94aabdc0fbc3'

Write-Host "Downloaded public dataset repositories to $root"
