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

& $fly.Source auth whoami

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
