# AntPlot

AntPlot is a local HFSS/antenna data plotting tool for turning exported simulation or measurement data into reproducible scientific figures. It provides CSV recognition, curve management, backend-rendered previews, engineering checks, and PNG/PDF/SVG/JSON/report exports.

The project description and example gallery are being prepared. This README currently focuses on local deployment.

## Features

- HFSS-style CSV recognition for S11, VSWR, realized gain, axial ratio, efficiency, HPBW, radiation patterns, and Smith charts.
- Automatic, semi-automatic, and manual mapping when data columns cannot be identified reliably.
- Multiple CSV and parameter-sweep curve overlays with per-curve style controls.
- Cartesian and polar radiation-pattern rendering.
- Backend-matched preview and export to PNG, PDF, SVG, JSON, and engineering reports.
- XY Multi-Curve mode for strictly formatted generic XY data.

## Requirements

- Windows 10/11
- Python 3.10 or newer
- Node.js 20 or newer
- pnpm, enabled through Corepack (`corepack enable`)

## Local deployment

Clone the repository and enter it:

```powershell
git clone https://github.com/<your-account>/antplot.git
cd antplot
```

Create a Python environment and install backend packages:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Install and build the frontend:

```powershell
corepack enable
cd frontend
pnpm install --frozen-lockfile
pnpm build
cd ..
```

Start both services:

```powershell
.\start_app.bat
```

Open `http://127.0.0.1:4173/` in a browser. The local Python API runs on `http://127.0.0.1:8765/`.

If PowerShell blocks script execution, use the `.bat` launcher above or run the commands manually.

## Development checks

```powershell
.\.venv\Scripts\python.exe tools\recognition_regression.py
cd frontend
pnpm build
```

## Repository layout

```text
src/hfss_paperplotter/  Python parsing, recognition, plotting, metrics, and API
frontend/               React + Tailwind user interface
examples/               Sample CSV data
tools/                  Regression and acceptance scripts
styles/                 Paper/HFSS-like style definitions
```

## Data and engineering notes

AntPlot does not use image pixels to calculate engineering metrics. It retains warnings when units, port reference planes, normalization, or pattern cuts cannot be confirmed. Review these warnings before using a figure in a publication.

## License

License information will be added before the public release.
