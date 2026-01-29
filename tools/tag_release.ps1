$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$mainPath = Join-Path $root "main.py"
if (-not (Test-Path $mainPath)) {
    throw "main.py not found at $mainPath"
}

$content = Get-Content $mainPath -Raw
$match = [regex]::Match($content, 'APP_VERSION\\s*=\\s*\"([^\"]+)\"')
if (-not $match.Success) {
    throw "APP_VERSION not found in main.py"
}

$version = $match.Groups[1].Value.Trim()
if (-not $version) {
    throw "APP_VERSION is empty"
}

$tag = "v$version"

$currentTag = & git tag -l $tag
if ($currentTag) {
    throw "Tag $tag already exists"
}

& git tag -a $tag -m $tag
Write-Host "Created tag $tag"
