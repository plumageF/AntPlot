# Contributing to AntPlot

## Development setup

Use Python 3.10+ and Node.js 20+ with pnpm:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
corepack enable
cd frontend
pnpm install --frozen-lockfile
```

Run the backend and frontend with `start_app.bat`, or run the regression and build commands in the README.

## Data and code contributions

- Add public, minimal fixtures under `examples/` for parser or plotting changes.
- Keep raw data, X/Y pairing, units and warnings explicit.
- Do not submit private measurement data, credentials, `.venv`, `node_modules`, build caches or local absolute paths.
- New plot behavior needs a regression case and an update to the data-format documentation.
- Do not claim a feature is supported until it has a reproducible test.

## Pull requests

Explain the user-facing behavior, test commands and known limitations. Keep changes focused and preserve the backend preview/export path.
