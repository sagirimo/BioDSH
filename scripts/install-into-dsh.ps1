# Install BioDSH's official skills into a DeepSeek Harness (dsh) skills directory (Windows).
# BioDSH skills are dsh-native SKILL.md skills; dsh auto-discovers them from a skills folder it scans:
#   .\.agents\skills  (default, per-project)  or  $HOME\.agents\skills  (with -Global)
# Usage:
#   .\scripts\install-into-dsh.ps1
#   .\scripts\install-into-dsh.ps1 -Global
#   .\scripts\install-into-dsh.ps1 -Dest C:\path\to\skills
param([switch]$Global, [string]$Dest)
$ErrorActionPreference = 'Stop'
$src = Join-Path (Split-Path $PSScriptRoot -Parent) 'biodsh-core\skills'
if ($Dest) { }
elseif ($Global) { $Dest = Join-Path $HOME '.agents\skills' }
else { $Dest = Join-Path (Get-Location) '.agents\skills' }
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
$n = 0
Get-ChildItem -Directory $src | ForEach-Object {
  if (Test-Path (Join-Path $_.FullName 'SKILL.md')) {
    $target = Join-Path $Dest $_.Name
    if (Test-Path $target) { Remove-Item -Recurse -Force $target }
    Copy-Item -Recurse $_.FullName $target
    Write-Host "  installed: $($_.Name)"
    $n++
  }
}
Write-Host "Installed $n BioDSH skill(s) into: $Dest"
Write-Host "Start dsh from a workspace that sees this folder and the skills are ready to use."
Write-Host "Note: the scRNA / plotting skills expect a Python env with scanpy, anndata, pandas, matplotlib on PATH."
