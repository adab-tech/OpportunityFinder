# OpportunityFinder — first-time Fly.io deploy
# Prerequisite: flyctl auth login

$ErrorActionPreference = "Stop"
$AppName = "adab-opportunityfinder"
$DbName = "adab-opportunityfinder-db"
$Region = "lhr"
$Root = Split-Path -Parent $PSScriptRoot

Set-Location $Root

$fly = Get-Command flyctl -ErrorAction SilentlyContinue
if (-not $fly) { $fly = Get-Command fly -ErrorAction SilentlyContinue }
if (-not $fly) { throw "Fly CLI not found. Install: winget install Fly-io.flyctl" }

if (-not $env:FLY_API_TOKEN) {
    $whoami = & $fly.Source auth whoami 2>&1 | Out-String
    if ($whoami -match "Error:") {
        Write-Host ""
        Write-Host "Fly.io is not authenticated." -ForegroundColor Red
        Write-Host ""
        Write-Host "Option A — browser login (run in YOUR terminal, not the agent):"
        Write-Host "  flyctl auth login"
        Write-Host ""
        Write-Host "Option B — dashboard token (no browser CLI):"
        Write-Host "  1. https://fly.io/dashboard → Account → Access Tokens → Create"
        Write-Host "  2. `$env:FLY_API_TOKEN = 'your-token-here'"
        Write-Host "  3. Re-run this script"
        Write-Host ""
        Write-Host "Option C — use Render instead (no Fly): see docs/DEPLOY-RENDER.md"
        exit 1
    }
} else {
    Write-Host "Using FLY_API_TOKEN from environment."
}

$appExists = & $fly.Source apps list --json | ConvertFrom-Json | Where-Object { $_.Name -eq $AppName }
if (-not $appExists) {
    Write-Host "Creating Fly app $AppName ..."
    & $fly.Source launch --no-deploy --yes --name $AppName --region $Region --copy-config
}

$secrets = & $fly.Source secrets list -a $AppName 2>&1 | Out-String
if ($secrets -notmatch "DATABASE_URL") {
    $dbs = & $fly.Source postgres list --json 2>$null | ConvertFrom-Json
    $db = $dbs | Where-Object { $_.Name -eq $DbName }
    if (-not $db) {
        Write-Host "Creating Postgres $DbName (smallest tier) ..."
        & $fly.Source postgres create --name $DbName --region $Region --vm-size shared-cpu-1x --volume-size 1 --initial-cluster-size 1
    }
    Write-Host "Attaching Postgres to $AppName ..."
    & $fly.Source postgres attach $DbName -a $AppName --yes
}

Write-Host "Deploying $AppName ..."
& $fly.Source deploy -a $AppName

$Url = "https://$AppName.fly.dev"
Write-Host "`nPublic URL: $Url"
Write-Host "Health:     $Url/health"
& $fly.Source open -a $AppName
