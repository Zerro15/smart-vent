#requires -Version 7.0
Set-StrictMode -Version Latest
$ErrorActionPreference = 'SilentlyContinue'

$Root = $PSScriptRoot
if (-not $Root -or [string]::IsNullOrWhiteSpace($Root)) {
  if ($PSCommandPath) { $Root = Split-Path -LiteralPath $PSCommandPath -Parent }
  elseif ($MyInvocation.MyCommand.Path) { $Root = Split-Path -LiteralPath $MyInvocation.MyCommand.Path -Parent }
  else { $Root = (Get-Location).Path }
}

$RunDir  = Join-Path $Root '.run'
$WaitPid = Join-Path $RunDir 'waitress.pid'
$CfPid   = Join-Path $RunDir 'cloudflared.pid'

function Stop-ByPidFile([string]$pidFile,[string]$name){
  if (Test-Path $pidFile) {
    $pidText = Get-Content $pidFile | Select-Object -First 1
    if ($pidText -and $pidText -as [int]) { Stop-Process -Id ($pidText -as [int]) -Force }
    Remove-Item $pidFile -Force
  }
  Get-Process -Name $name | ForEach-Object { Stop-Process -Id $_.Id -Force }
}
Stop-ByPidFile -pidFile $WaitPid -name 'waitress-serve'
Stop-ByPidFile -pidFile $CfPid   -name 'cloudflared'
Write-Host "Stopped (if running)."
