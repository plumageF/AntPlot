$ErrorActionPreference = "Stop"

$root = "C:\Users\26246\Documents\Codex\2026-06-21\lei"
$node = "C:\Users\26246\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
$python = Join-Path $root ".venv\Scripts\python.exe"

Write-Host "Starting backend preview server on http://127.0.0.1:8765 ..."
Start-Process -WindowStyle Minimized -FilePath $python `
  -ArgumentList "-m", "src.hfss_paperplotter.preview_server" `
  -WorkingDirectory $root

Write-Host "Starting frontend preview server on http://127.0.0.1:4173 ..."
Start-Process -WindowStyle Minimized -FilePath $node `
  -ArgumentList ".\node_modules\vite\bin\vite.js", "preview", "--host", "127.0.0.1", "--port", "4173" `
  -WorkingDirectory (Join-Path $root "frontend")

Start-Sleep -Seconds 2
Write-Host ""
Write-Host "Frontend: http://127.0.0.1:4173/"
Write-Host "Backend : http://127.0.0.1:8765/"
