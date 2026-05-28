[CmdletBinding()]
param(
  [string]$Distro = "Ubuntu-24.04",
  [string]$Repo = "",
  [string]$ClientDir = "C:\CodexWSL\NWN\linux-client\English_linuxclient_xp2",
  [switch]$InstallWsl,
  [switch]$Bootstrap,
  [switch]$AllowDriveMount
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $Repo) {
  $Repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
}
$Repo = (Resolve-Path -LiteralPath $Repo).Path
if (Test-Path -LiteralPath $ClientDir) {
  $ClientDir = (Resolve-Path -LiteralPath $ClientDir).Path
}
$safeWslLaunchDir = Join-Path $env:SystemDrive "\"
if (Test-Path -LiteralPath $safeWslLaunchDir) {
  Set-Location $safeWslLaunchDir
}

function Test-IsAdmin {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = [Security.Principal.WindowsPrincipal]$identity
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-WslReady {
  $oldPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $output = (& wsl.exe --status 2>&1 | Out-String) -replace "`0", ""
    $code = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $oldPreference
  }
  if ($code -ne 0) {
    return $false
  }
  if ($output -match "not installed|unable to start|required feature is not installed") {
    return $false
  }
  return $true
}

function Install-WslPackage {
  $winget = Get-Command winget -ErrorAction SilentlyContinue
  if (-not $winget) {
    throw "winget is required to install the Microsoft.WSL package automatically."
  }
  $installed = & winget list -e --id Microsoft.WSL 2>$null
  if ($LASTEXITCODE -eq 0 -and ($installed | Select-String -Pattern "Microsoft.WSL" -Quiet)) {
    return
  }
  & winget install -e --id Microsoft.WSL --accept-package-agreements --accept-source-agreements --disable-interactivity
  if ($LASTEXITCODE -ne 0) {
    throw "winget failed to install Microsoft.WSL."
  }
}

function Enable-WslFeatures {
  & wsl.exe --install --no-distribution
  if ($LASTEXITCODE -ne 0) {
    & dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
    & dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
  }
}

function Get-WslDistros {
  $oldPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $output = & wsl.exe --list --quiet 2>$null
    $code = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $oldPreference
  }
  if ($code -ne 0) {
    return @()
  }
  return @(
    $output |
      ForEach-Object { ($_ -replace "`0", "").Trim() } |
      Where-Object { $_ }
  )
}

function Convert-ToWslPath {
  param(
    [string]$WindowsPath,
    [string]$TargetDistro
  )

  $resolved = (Resolve-Path -LiteralPath $WindowsPath).Path
  $qualifier = Split-Path -Qualifier $resolved
  if ($qualifier) {
    $drive = $qualifier.TrimEnd(":")
    $systemDrive = $env:SystemDrive.TrimEnd(":")
    if ($drive.ToUpperInvariant() -ne $systemDrive.ToUpperInvariant() -and -not $AllowDriveMount) {
      throw "Refusing to mount '${drive}:' into WSL. Copy the files to ${systemDrive}: or rerun with -AllowDriveMount."
    }
    $mount = "/mnt/" + $drive.ToLowerInvariant()
    $mountCommand = "mkdir -p '$mount' && mountpoint -q '$mount' || mount -t drvfs '$drive" + ":' '$mount'"
    & wsl.exe -d $TargetDistro -- bash -lc $mountCommand | Out-Null
  }
  $wslInputPath = $resolved -replace "\\", "/"
  $output = & wsl.exe -d $TargetDistro -- wslpath -a "$wslInputPath" 2>&1
  if ($LASTEXITCODE -ne 0) {
    throw "wslpath failed for '$resolved': $output"
  }
  return (($output | Select-Object -Last 1) -replace "`0", "").Trim()
}

function Quote-Bash {
  param([string]$Value)
  if ($Value.Contains("'")) {
    throw "Bash quoting for paths containing single quotes is not supported: $Value"
  }
  return "'" + $Value + "'"
}

if (-not (Test-WslReady)) {
  if (-not $InstallWsl) {
    Write-Host "WSL is not installed. Run this script with -InstallWsl from an elevated PowerShell, or run:"
    Write-Host "  wsl.exe --install -d $Distro"
    exit 2
  }

  if (-not (Test-IsAdmin)) {
    $args = @(
      "-NoExit",
      "-ExecutionPolicy", "Bypass",
      "-File", "`"$PSCommandPath`"",
      "-Distro", $Distro,
      "-Repo", "`"$Repo`"",
      "-ClientDir", "`"$ClientDir`"",
      "-InstallWsl"
    )
    if ($Bootstrap) {
      $args += "-Bootstrap"
    }
    Start-Process powershell -Verb RunAs -ArgumentList $args
    Write-Host "Opened an elevated PowerShell to install WSL. Finish the UAC/admin flow there."
    exit 0
  }

  Write-Host "Installing WSL package and optional features. A restart may be required."
  Install-WslPackage
  Enable-WslFeatures

  if (-not (Test-WslReady)) {
    Write-Host "WSL is installed and Windows features are enabled, but WSL cannot start yet."
    Write-Host "Restart Windows, then rerun this command:"
    Write-Host "  powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\setup_linux_test_env.ps1 -InstallWsl -Bootstrap"
    exit 3
  }
}

$distros = Get-WslDistros
if ($distros -notcontains $Distro) {
  if (-not $InstallWsl) {
    Write-Host "WSL is installed, but '$Distro' is not present. Run:"
    Write-Host "  wsl.exe --install -d $Distro"
    exit 2
  }
  & wsl.exe --install -d $Distro
  if ($LASTEXITCODE -ne 0) {
    Write-Host "Distro installation failed. If this is 0x80370114, restart Windows and rerun this script."
    exit $LASTEXITCODE
  }
}

Write-Host "WSL distro '$Distro' is present."

if (-not $Bootstrap) {
  Write-Host "Run again with -Bootstrap to install Linux build/test packages and build the hook inside WSL."
  exit 0
}

$repoLinux = Convert-ToWslPath -WindowsPath $Repo -TargetDistro $Distro
$clientLinux = Convert-ToWslPath -WindowsPath $ClientDir -TargetDistro $Distro
$repoQ = Quote-Bash $repoLinux
$clientQ = Quote-Bash ($clientLinux.TrimEnd("/") + "/nwmain")

$bootstrapScript = @"
set -euo pipefail
if [ "`$(id -u)" -eq 0 ]; then SUDO=""; else SUDO="sudo"; fi
`$SUDO dpkg --add-architecture i386 || true
`$SUDO apt-get update
`$SUDO apt-get install -y python3 g++-multilib gdb file binutils libc6-dev-i386 libgl1:i386 libglu1-mesa:i386 libsdl1.2debian:i386
cd $repoQ
chmod +x ./src/native/SimKeysHookLinux/build.sh ./simkeys_linux_client.sh
./src/native/SimKeysHookLinux/build.sh
python3 tools/match_linux_client.py --linux-client $clientQ
if ! ldd $clientQ | grep -q 'not found'; then
  echo "nwmain runtime dependencies are satisfied."
else
  echo "nwmain still has missing runtime dependencies:"
  ldd $clientQ | grep 'not found'
  echo "For NWN Diamond, libmss.so.6 should come from the full install's miles_linux directory."
fi
file ./src/native/SimKeysHookLinux/libSimKeysHookLinux.so
"@

& wsl.exe -d $Distro -- bash -lc $bootstrapScript
exit $LASTEXITCODE
