# AntPlot

AntPlot is a local HFSS/antenna data plotting tool for turning exported simulation or measurement data into reproducible scientific figures. It provides CSV recognition, curve management, backend-rendered previews, engineering checks, and PNG/PDF/SVG/JSON/report exports.

AntPlot converts HFSS, ADS, VNA, CST, and manually prepared curve data into reproducible antenna figures. It is a local application: input data and exported figures remain on your computer.

Repository: <https://github.com/plumageF/AntPlot>

For a complete Chinese/English walkthrough, see [the user guide](docs/USER_GUIDE.md). Representative input files and generated figures are in [examples/gallery](examples/gallery).

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

## Windows portable package

Download [`AntPlot-Windows-Portable-v0.1.0.zip`](downloads/AntPlot-Windows-Portable-v0.1.0.zip). It contains the prebuilt frontend, source code, sample data, and generated example figures. Node.js and pnpm are not required for this package. A GitHub Release asset may be added later; this repository download is the current canonical package.

1. Extract the ZIP to a writable folder, such as `D:\AntPlot`.
2. Ensure Python 3.10+ is available through `py` or `python`.
3. Double-click `install_and_start.bat`.
4. On its first run, it creates `.venv` and installs `requirements.txt`.
5. Open <http://127.0.0.1:4173/>.

The first setup needs an internet connection for Python packages. Later launches use `start_portable.bat`.

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
docs/                   Deployment and operating guides
```

## Data and engineering notes

AntPlot does not use image pixels to calculate engineering metrics. It retains warnings when units, port reference planes, normalization, or pattern cuts cannot be confirmed. Review these warnings before using a figure in a publication.

## License

This project is released under the MIT License. See [LICENSE](LICENSE).
