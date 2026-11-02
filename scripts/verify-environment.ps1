[CmdletBinding()]
param(
    [string]$Python = "D:\Python\python.exe",
    [string]$InnoSetup = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    [string]$Requirements = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $Requirements) {
    $Requirements = Join-Path $PSScriptRoot "..\requirements.txt"
}

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Python interpreter not found: $Python"
}
if (-not (Test-Path -LiteralPath $InnoSetup -PathType Leaf)) {
    throw "Inno Setup compiler not found: $InnoSetup"
}
if (-not (Test-Path -LiteralPath $Requirements -PathType Leaf)) {
    throw "requirements.txt not found: $Requirements"
}

$pythonDetailsJson = & $Python -c "import json,struct,sys; print(json.dumps({'version': '.'.join(map(str, sys.version_info[:3])), 'major': sys.version_info.major, 'minor': sys.version_info.minor, 'pointerBits': struct.calcsize('P') * 8}))"
if ($LASTEXITCODE -ne 0) {
    throw "Python interpreter failed: $Python; exit code: $LASTEXITCODE"
}
$pythonDetails = $pythonDetailsJson | ConvertFrom-Json
if ($pythonDetails.major -ne 3 -or $pythonDetails.minor -ne 13) {
    throw "Python 3.13 required; actual version: $($pythonDetails.version); interpreter: $Python"
}
if ($pythonDetails.pointerBits -ne 64) {
    throw "Python 3.13 64-bit required; actual bits: $($pythonDetails.pointerBits); interpreter: $Python"
}

$requiredVersions = @{}
foreach ($line in Get-Content -LiteralPath $Requirements -Encoding UTF8) {
    $requirement = $line.Trim()
    if (-not $requirement -or $requirement.StartsWith("#")) {
        continue
    }
    if ($requirement -notmatch "^([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+)$") {
        throw "Dependency must use exact name==version format; actual value: $requirement; file: $Requirements"
    }
    $packageName = $Matches[1].ToLowerInvariant().Replace("_", "-")
    if ($requiredVersions.ContainsKey($packageName)) {
        throw "Duplicate dependency: $packageName; file: $Requirements"
    }
    $requiredVersions[$packageName] = $Matches[2]
}
if ($requiredVersions.Count -eq 0) {
    throw "requirements.txt contains no dependencies: $Requirements"
}

$installedVersionsJson = & $Python -c "from importlib.metadata import distributions; import json; print(json.dumps({str(item.metadata.get('Name') or '').lower().replace('_','-'): item.version for item in distributions()}))"
if ($LASTEXITCODE -ne 0) {
    throw "Cannot read installed Python packages; interpreter: $Python; exit code: $LASTEXITCODE"
}
$installedVersions = @{}
($installedVersionsJson | ConvertFrom-Json).PSObject.Properties | ForEach-Object {
    $installedVersions[$_.Name] = [string]$_.Value
}

$missingRequirements = @()
$versionMismatches = @()
foreach ($packageName in $requiredVersions.Keys | Sort-Object) {
    $expectedVersion = $requiredVersions[$packageName]
    if (-not $installedVersions.ContainsKey($packageName)) {
        $missingRequirements += "$packageName==$expectedVersion"
        continue
    }
    $installedVersion = $installedVersions[$packageName]
    if ($installedVersion -ne $expectedVersion) {
        $versionMismatches += "$packageName expected $expectedVersion but found $installedVersion"
    }
}

if ($missingRequirements.Count -gt 0) {
    $missingText = $missingRequirements -join ", "
    throw "Missing Python packages: $missingText; interpreter: $Python; requirements: $Requirements"
}
if ($versionMismatches.Count -gt 0) {
    $mismatchText = $versionMismatches -join "; "
    throw "Python package version mismatch: $mismatchText; interpreter: $Python; requirements: $Requirements"
}

Write-Host "Python 3.13 64-bit verified: $Python"
Write-Host "Inno Setup verified: $InnoSetup"
Write-Host "Python dependencies verified: $($requiredVersions.Count); requirements: $Requirements"
