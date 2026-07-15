# AntPlot v0.1.0 Test Report / 测试报告

**Date:** 2026-07-15
**Repository:** [plumageF/AntPlot](https://github.com/plumageF/AntPlot)
**Runners:** `tools/final_acceptance.py`, `tools/recognition_regression.py`

## Summary

| Check | Result |
| --- | --- |
| Acceptance checks | **12/12 passed** |
| Recognition regression | **passed** |
| Frontend production build | **passed** with the repository's Node/Vite runtime |

The public acceptance suite uses repository fixtures only. It does not depend on `D:\CSV`, `G:\` or another developer-specific drive.

## Acceptance coverage

1. Standard HFSS S11 recognition and export.
2. Simulated/Measured wide-table overlay.
3. Multiple CSV S11 overlay.
4. VNA Hz to MHz conversion.
5. Linear magnitude to dB conversion.
6. Re/Im S11 conversion and Smith Chart export.
7. No-header confirmation requirement.
8. 410–490 MHz band and -10 dB threshold configuration.
9. PNG/PDF/JSON/report export.
10. Out-of-range target-band warning.
11. Automatic, semi-automatic and manual workflows.
12. Backend preview/export parity.

## Recognition regression

The regression suite covers non-standard S11 names, positive and negative Return Loss conventions, far-field grids, and Theta/Phi angular families. It verifies the report domain, plot type, primary sweep, quantity and grid classification.

## Reproduce

```powershell
python -m pip install -r requirements.txt
python tools\recognition_regression.py
python tools\final_acceptance.py

cd frontend
pnpm install --frozen-lockfile
pnpm build
```

Generated artifacts are available in [AntPlot-Test-Results-v0.1.0.zip](https://github.com/plumageF/AntPlot/releases/download/v0.1.0/AntPlot-Test-Results-v0.1.0.zip). Input fixtures are available in [AntPlot-Test-Data-v0.1.0.zip](https://github.com/plumageF/AntPlot/releases/download/v0.1.0/AntPlot-Test-Data-v0.1.0.zip).

## Engineering limitations

AntPlot assists with visualization and engineering checks. It does not replace simulation setup review, VNA calibration verification, reference-plane review, de-embedding review, or professional engineering judgment. Ambiguous units, reference impedance, pattern cuts, polarization and normalization remain warnings or require user confirmation.
