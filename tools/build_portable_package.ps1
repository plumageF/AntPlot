param(
  [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$releaseDir = Join-Path $root "release"
$stageDir = Join-Path $releaseDir "AntPlot-Windows-Portable-v$Version"
$archivePath = Join-Path $releaseDir "AntPlot-Windows-Portable-v$Version.zip"

Remove-Item -Recurse -Force $stageDir -ErrorAction SilentlyContinue
Remove-Item -Force $archivePath -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $stageDir | Out-Null

New-Item -ItemType Directory -Force (Join-Path $stageDir "frontend") | Out-Null
New-Item -ItemType Directory -Force (Join-Path $stageDir "examples") | Out-Null

# Keep the portable package compact: runtime, curated examples, and the gallery.
Copy-Item -Recurse -Force (Join-Path $root "src") $stageDir
Copy-Item -Recurse -Force (Join-Path $root "frontend\dist") (Join-Path $stageDir "frontend")
Copy-Item -Recurse -Force (Join-Path $root "styles") $stageDir
Copy-Item -Recurse -Force (Join-Path $root "docs") $stageDir
foreach ($exampleSet in @("gallery", "s11_cases", "report_model_cases", "v02_acceptance")) {
  Copy-Item -Recurse -Force (Join-Path $root "examples\$exampleSet") (Join-Path $stageDir "examples")
}
foreach ($file in @("requirements.txt", "README.md", "LICENSE", "config.yaml", "install_and_start.bat", "start_portable.bat")) {
  Copy-Item -Force (Join-Path $root $file) $stageDir
}

Compress-Archive -Path (Join-Path $stageDir "*") -DestinationPath $archivePath -Force
Write-Host "Created $archivePath"
