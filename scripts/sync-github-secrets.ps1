# Sync local env values to GitHub Actions secrets (run locally; never commit .env).
# Usage: .\scripts\sync-github-secrets.ps1 -Repo adab-tech/OpportunityFinder -EnvFile backend\.env

param(
    [Parameter(Mandatory = $true)]
    [string]$Repo,

    [Parameter(Mandatory = $true)]
    [string]$EnvFile
)

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Error "GitHub CLI (gh) is required. Install from https://cli.github.com/"
}

if (-not (Test-Path $EnvFile)) {
    Write-Error "Env file not found: $EnvFile"
}

$map = @{}
Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -match '^\s*#' -or $line -notmatch '=') { return }
    $parts = $line -split '=', 2
    $key = $parts[0].Trim()
    $val = $parts[1].Trim().Trim('"').Trim("'")
    if ($val -and $val -notmatch 'your_.*_here') {
        $map[$key] = $val
    }
}

foreach ($key in $map.Keys) {
    Write-Host "Setting secret $key on $Repo ..."
    $map[$key] | gh secret set $key --repo $Repo
}

Write-Host "Done. See .github/SECRETS.md in each repo for the full list."
