# Screenshot both ports with headless Edge (public UI + admin UI).
# Logs in as admin through the API and passes the session token via ?token=...
# NOTE: keep this file ASCII-only so Windows PowerShell 5.1 parses it correctly.
param(
  [string]$MainBase = "http://127.0.0.1:8090",
  [string]$AdminBase = "http://127.0.0.1:8091",
  [string]$OutDir = "",
  [int]$Width = 1460,
  [int]$Height = 1560,
  [string]$As = "life-committee",
  [string]$AdminUser = "admin",
  [string]$AdminPass = "testadmin123",
  [string]$PublicPages = "home,report,dashboard,stats,records",
  [string]$AdminPages = "overview,fund,accounts,logs,console,dorms,push,config"
)

$root = Split-Path -Parent $PSScriptRoot
if (-not $OutDir) { $OutDir = Join-Path $root "data\shots" }
$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path $edge)) { $edge = "C:\Program Files\Microsoft\Edge\Application\msedge.exe" }
if (-not (Test-Path $edge)) { Write-Error "Edge not found"; exit 1 }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$errors = @()

# 1) log in to get a session token
$token = ""
try {
  $body = @{ username = $AdminUser; password = $AdminPass } | ConvertTo-Json
  $login = Invoke-RestMethod -Uri "$AdminBase/api/auth/login" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 20
  $token = $login.token
  Write-Host ("login ok: {0}" -f $login.account.username) -ForegroundColor Green
} catch {
  Write-Host ("login failed: {0}" -f $_.Exception.Message) -ForegroundColor Yellow
}

function Clear-OldShots {
  for ($i = 0; $i -lt 6; $i++) {
    $procs = Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" -ErrorAction SilentlyContinue |
      Where-Object { $_.CommandLine -and $_.CommandLine -like '*edge-shot-*' }
    if (-not $procs) { break }
    $procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 500
  }
  Start-Sleep -Milliseconds 300
}

function Invoke-Shot {
  param([string]$Url, [string]$Out, [string]$Profile)
  $log = @()
  for ($try = 1; $try -le 3; $try++) {
    Clear-OldShots
    $p = "$Profile-$try"
    Remove-Item -Recurse -Force $p -ErrorAction SilentlyContinue
    Remove-Item -Force $Out -ErrorAction SilentlyContinue
    $log = & $edge --headless=new --disable-gpu --no-first-run --no-default-browser-check `
      --user-data-dir="$p" --window-size="$Width,$Height" `
      --screenshot="$Out" --virtual-time-budget=13000 `
      --enable-logging=stderr --log-level=0 `
      $Url 2>&1
    Start-Sleep -Milliseconds 600
    if (Test-Path $Out) { break }
    Start-Sleep -Seconds 2
  }
  return $log
}

function Shoot-Page {
  param([string]$Base, [string]$Page, [string]$Prefix, [string]$Dir, [bool]$Admin)
  $profile = Join-Path $env:TEMP "edge-shot-$Prefix-$Page"
  $out = Join-Path $Dir "$Prefix-$Page.png"
  $url = "$Base/?as=$([uri]::EscapeDataString($As))#/$Page"
  if ($Admin -and $token) {
    $url = "$Base/?token=$([uri]::EscapeDataString($token))#/$Page"
  }
  $log = Invoke-Shot -Url $url -Out $out -Profile $profile
  $log | Select-String -Pattern "CONSOLE.*(Uncaught|is not a function|is not defined|Failed to load)" | ForEach-Object {
    $errors += "[$Prefix/$Page] $_"
    Write-Host "  [$Prefix/$Page] $_" -ForegroundColor Yellow
  }
  if (Test-Path $out) {
    $kb = [math]::Round((Get-Item $out).Length / 1024, 1)
    Write-Host ("{0,-20} {1} KB" -f "$Prefix/$Page", $kb)
  } else {
    Write-Host ("{0}/{1} FAILED" -f $Prefix, $Page) -ForegroundColor Red
  }
}

Write-Host "=== public port ===" -ForegroundColor Cyan
foreach ($page in $PublicPages.Split(",")) {
  if ($page.Trim()) { Shoot-Page -Base $MainBase -Page $page.Trim() -Prefix "public" -Dir $OutDir -Admin $false }
}

Write-Host "=== admin port ===" -ForegroundColor Cyan
foreach ($page in $AdminPages.Split(",")) {
  if ($page.Trim()) { Shoot-Page -Base $AdminBase -Page $page.Trim() -Prefix "admin" -Dir $OutDir -Admin $true }
}

if ($errors.Count -eq 0) { Write-Host "No frontend script errors detected" -ForegroundColor Green }
