[CmdletBinding()]
param(
  [string]$Out = "",
  [string]$BundleOut = "",
  [string]$Zig = "",
  [string]$Target = "x86-linux-gnu"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-Zig {
  param([string]$Requested)

  if ($Requested) {
    $cmd = Get-Command $Requested -ErrorAction SilentlyContinue
    if ($cmd) {
      return $cmd.Source
    }
    if (Test-Path -LiteralPath $Requested) {
      return (Resolve-Path -LiteralPath $Requested).Path
    }
    throw "Could not find Zig at '$Requested'."
  }

  $pathCmd = Get-Command zig -ErrorAction SilentlyContinue
  if ($pathCmd) {
    return $pathCmd.Source
  }

  $wingetRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
  if (Test-Path -LiteralPath $wingetRoot) {
    $candidate = Get-ChildItem -LiteralPath $wingetRoot -Directory -Filter "zig.zig_*" -ErrorAction SilentlyContinue |
      Get-ChildItem -Recurse -Filter "zig.exe" -ErrorAction SilentlyContinue |
      Sort-Object FullName -Descending |
      Select-Object -First 1
    if ($candidate) {
      return $candidate.FullName
    }
  }

  throw "Could not find Zig. Install it with: winget install -e --id zig.zig --scope user"
}

$zigExe = Resolve-Zig -Requested $Zig
$src = Join-Path $PSScriptRoot "SimKeysHookLinux.cpp"
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")).Path
if (-not $Out) {
  $Out = Join-Path $PSScriptRoot "libSimKeysHookLinux.so"
}
if (-not $BundleOut) {
  $BundleOut = Join-Path $repoRoot "bin\libSimKeysHookLinux.so"
}

& $zigExe c++ `
  -target $Target `
  -m32 `
  -std=gnu++11 `
  -O2 `
  -fPIC `
  -shared `
  -fno-exceptions `
  -fno-rtti `
  -nostdlib++ `
  -Wall `
  -Wextra `
  -Wno-unused-parameter `
  -Wno-unused-const-variable `
  -Wno-nullability-completeness `
  -o $Out `
  $src `
  -ldl `
  -lpthread

if ($LASTEXITCODE -ne 0) {
  throw "Zig exited with code $LASTEXITCODE."
}

if ($BundleOut) {
  $bundleDir = Split-Path -Parent $BundleOut
  if (-not (Test-Path -LiteralPath $bundleDir)) {
    New-Item -ItemType Directory -Path $bundleDir | Out-Null
  }
  Copy-Item -LiteralPath $Out -Destination $BundleOut -Force
  Write-Host "Copied $BundleOut"
}

Write-Host "Built $Out with $zigExe"
