#requires -Version 7.0
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ---------- Версия и корень проекта ----------
$ScriptVersion = 'run_dashboard v3.1'
$Root = $PSScriptRoot
if (-not $Root -or [string]::IsNullOrWhiteSpace($Root)) {
  if ($PSCommandPath) { $Root = Split-Path -LiteralPath $PSCommandPath -Parent }
  elseif ($MyInvocation.MyCommand.Path) { $Root = Split-Path -LiteralPath $MyInvocation.MyCommand.Path -Parent }
  else { $Root = (Get-Location).Path }
}

# ---------- Пути/настройки ----------
$LogsDir   = Join-Path $Root 'logs'
$RunDir    = Join-Path $Root '.run'
$ToolsDir  = Join-Path $Root 'tools'

# ВАЖНО: путь к вашему WSGI-объекту (Dash → Flask WSGI)
# software/dash_app.py должен содержать переменную app, у которой есть .server
$AppTarget = 'software.dash_app:server'

# слушаем только локалку; наружу выходим через cloudflared
$BindAddr  = '127.0.0.1'
$ProtoPref = @('quic','http2')

New-Item -ItemType Directory -Force -Path $LogsDir,$RunDir,$ToolsDir | Out-Null

$WaitOut = Join-Path $LogsDir 'waitress.out.log'
$WaitErr = Join-Path $LogsDir 'waitress.err.log'
$CfOut   = Join-Path $LogsDir 'cloudflared.out.log'
$CfErr   = Join-Path $LogsDir 'cloudflared.err.log'

$WaitPid = Join-Path $RunDir  'waitress.pid'
$CfPid   = Join-Path $RunDir  'cloudflared.pid'
$UrlFile = Join-Path $RunDir  'public_url.txt'

# ---------- Утилиты ----------
function Box([string]$title, [string[]]$lines) {
  $maxLine = 0
  if ($lines -and $lines.Count -gt 0) {
    $maxLine = ($lines | Measure-Object -Maximum -Property Length).Maximum
  }
  $a = $title.Length + 2
  $b = $maxLine + 2
  $c = 11
  $w = [Math]::Max($a, [Math]::Max($b, $c))

  $hr = '+' + ('-' * $w) + '+'
  Write-Host "`n$hr" -ForegroundColor DarkGray
  Write-Host ('| ' + $title.PadRight($w-2) + ' |') -ForegroundColor Gray
  Write-Host ('|' + ('-' * $w) + '|') -ForegroundColor DarkGray
  if ($lines) {
    foreach ($l in $lines) {
      $line = if ($null -ne $l) { $l } else { '' }
      Write-Host ('| ' + $line.PadRight($w-2) + ' |')
    }
  }
  Write-Host $hr -ForegroundColor DarkGray
}

function Get-LocalIPv4 {
  $ips = [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() |
    Where-Object { $_.OperationalStatus -eq 'Up' } |
    ForEach-Object {
      $_.GetIPProperties().UnicastAddresses |
      Where-Object { $_.Address.AddressFamily -eq 'InterNetwork' -and -not $_.Address.Equals([Net.IPAddress]::Parse('127.0.0.1')) } |
      Select-Object -ExpandProperty Address
    }
  ($ips | Select-Object -First 1 | ForEach-Object { $_.ToString() }) ?? '0.0.0.0'
}

function Test-PortFree([int]$Port, [string]$Addr='127.0.0.1'){
  try {
    $l=[System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse($Addr),$Port)
    $l.Start(); $l.Stop(); $true
  } catch { $false }
}
function Get-FreePort([int]$start=8050, [int]$maxTries=100){
  for($p=$start;$p -lt ($start+$maxTries);$p++){ if (Test-PortFree -Port $p) { return $p } }
  throw "Не удалось подобрать свободный порт."
}

function Find-Exe([string[]]$candidates){
  foreach($c in $candidates){
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Path) { return $cmd.Path }
    if (Test-Path $c) { return (Resolve-Path $c).Path }
  }
  $null
}

function Stop-ByPidFile([string]$pidFile,[string]$name){
  if (Test-Path $pidFile) {
    $pidText = Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pidText -and $pidText -as [int]) {
      $p = Get-Process -Id ($pidText -as [int]) -ErrorAction SilentlyContinue
      if ($p) { try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch {} }
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
  }
  Get-Process -Name $name -ErrorAction SilentlyContinue | ForEach-Object {
    try { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } catch {}
  }
}

function Start-LoggedProc {
  param(
    [Parameter(Mandatory=$true)] [string]$Exe,
    [Parameter(Mandatory=$true)] [string[]]$Args,
    [Parameter(Mandatory=$true)] [string]$OutFile,
    [Parameter(Mandatory=$true)] [string]$ErrFile,
    [string]$WorkingDirectory = $Root,
    [hashtable]$Environment = @{}
  )
  # В PS7 есть -Environment
  Start-Process -FilePath $Exe -ArgumentList $Args `
    -RedirectStandardOutput $OutFile `
    -RedirectStandardError  $ErrFile `
    -NoNewWindow -PassThru `
    -WorkingDirectory $WorkingDirectory `
    -Environment $Environment
}

# ---------- Баннер ----------
Box "Launcher" @("$ScriptVersion", "Root: $Root")

# ---------- Гасим старые процессы ----------
Stop-ByPidFile -pidFile $WaitPid -name 'waitress-serve'
Stop-ByPidFile -pidFile $CfPid   -name 'cloudflared'

# ---------- Чистим логи/ссылку ----------
foreach ($f in @($WaitOut,$WaitErr,$CfOut,$CfErr,$UrlFile)) { try { '' | Set-Content -NoNewline -Encoding UTF8 $f } catch {} }

# ---------- Стартуем waitress ----------
$Port     = Get-FreePort -start 8050
$LocalUrl = "http://$($BindAddr):$Port"
$LocalIP  = Get-LocalIPv4
Box "Starting local server" @("URL: $LocalUrl")

$WaitressExe = Find-Exe @(
  (Join-Path $Root '.venv/Scripts/waitress-serve.exe'),
  (Join-Path $Root '.venv/bin/waitress-serve'),
  'waitress-serve'
)

# Формируем окружение для импорта вашего пакета из корня проекта
$EnvTable = @{
  'PYTHONUNBUFFERED' = '1'
  'PYTHONPATH'       = $Root
}

if ($WaitressExe) {
  # Нативный CLI
  $wArgs = @('--listen', "$($BindAddr):$Port", $AppTarget)
  $wProc = Start-LoggedProc -Exe $WaitressExe -Args $wArgs -OutFile $WaitOut -ErrFile $WaitErr -Environment $EnvTable
} else {
  # Фолбэк через python -m waitress
  $Py = Find-Exe @(
    (Join-Path $Root '.venv/Scripts/python.exe'),
    (Join-Path $Root '.venv/bin/python'),
    'python','py'
  )
  if (-not $Py) { throw "Не найден ни waitress-serve, ни python в venv. Установите venv и waitress." }
  $wArgs = @('-m','waitress','--listen', "$($BindAddr):$Port", $AppTarget)
  $wProc = Start-LoggedProc -Exe $Py -Args $wArgs -OutFile $WaitOut -ErrFile $WaitErr -Environment $EnvTable
}
$wProc.Id | Set-Content -Encoding ASCII $WaitPid

# Ждём, пока порт реально занят приложением
$deadline = (Get-Date).AddSeconds(30)
do {
  Start-Sleep -Milliseconds 300
  $ok = -not (Test-PortFree -Port $Port -Addr $BindAddr)
} until ($ok -or (Get-Date) -ge $deadline)

if (-not $ok) {
  throw "waitress не поднялся на $LocalUrl. Смотри лог: $WaitErr"
}

# ---------- Cloudflared ----------
$Cf = Find-Exe @(
  (Join-Path $ToolsDir 'cloudflared.exe'),
  (Join-Path $ToolsDir 'cloudflared'),
  'cloudflared'
)

if (-not $Cf) {
  if ($IsWindows) {
    try {
      $url = 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe'
      $Cf  = Join-Path $ToolsDir 'cloudflared.exe'
      Invoke-WebRequest -Uri $url -OutFile $Cf -UseBasicParsing -TimeoutSec 120
    } catch {
      throw "cloudflared не найден и не скачался. Положите бинарник в $ToolsDir вручную."
    }
  } else {
    throw "cloudflared не найден. Установите его через менеджер пакетов."
  }
}

$PublicUrl = $null
foreach($proto in $ProtoPref){
  Box "Starting Cloudflare Tunnel" @("Protocol: $proto")
  $cfArgs = @('tunnel','--no-autoupdate','--edge-ip-version','auto','--protocol', $proto, '--url', $LocalUrl)
  $cfProc = Start-LoggedProc -Exe $Cf -Args $cfArgs -OutFile $CfOut -ErrFile $CfErr -Environment @{}
  $cfProc.Id | Set-Content -Encoding ASCII $CfPid

  $deadline = (Get-Date).AddSeconds(40)
  $rx = 'https://[a-z0-9-]+\.trycloudflare\.com'
  do {
    Start-Sleep -Milliseconds 600
    $txt1 = Get-Content $CfOut -Raw -ErrorAction SilentlyContinue
    $txt2 = Get-Content $CfErr -Raw -ErrorAction SilentlyContinue
    $all  = ($txt1 + "`n" + $txt2)
    if ($all -match $rx) { $PublicUrl = $Matches[0] }
  } until ($PublicUrl -or (Get-Date) -ge $deadline)

  if ($PublicUrl) { break }
  try { Stop-Process -Id $cfProc.Id -Force -ErrorAction SilentlyContinue } catch {}
  Remove-Item $CfPid -ErrorAction SilentlyContinue
  Box "Retry with http2" @("quic не дал ссылку вовремя, переключаюсь…")
}

if (-not $PublicUrl) {
  Box "ERROR: could not obtain public URL" @(
    "Проверь Интернет/VPN и логи:",
    $CfOut,
    $CfErr
  )
  exit 1
}

$PublicUrl | Set-Content -Encoding UTF8 $UrlFile
try { Set-Clipboard -Value $PublicUrl -ErrorAction SilentlyContinue } catch {}

Box "Smart Vent is LIVE" @(
  "Local:  $LocalUrl",
  "Public: $PublicUrl",
  "",
  "Local IPv4 (info): $(Get-LocalIPv4)",
  "",
  "Ссылка скопирована в буфер."
)

try {
  if ($IsWindows) { Start-Process $PublicUrl }
  elseif ($IsMacOS) { & open $PublicUrl }
  else { & xdg-open $PublicUrl 2>$null }
} catch {}

if ($Host.Name -notmatch 'ConsoleHost') { Start-Sleep -Seconds 3 }
