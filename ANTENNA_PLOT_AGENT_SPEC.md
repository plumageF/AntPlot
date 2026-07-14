# Antenna Plot Agent Specification

This project treats antenna plotting as an engineering data-processing task, not as image styling only.

## Mandatory Workflow

1. Read the input data and inspect explicit column names.
2. Confirm variables and units before plotting.
3. Confirm the target operating band and threshold conditions.
4. Convert frequency units consistently and sort data when needed.
5. Compute metrics from raw data or explicitly documented interpolation.
6. Draw the figure with engineering reference lines and band markers.
7. Export reproducible files, preferably PDF/SVG plus 600 dpi PNG.
8. Write a short plotting note and engineering conclusion.

## Data Rules

- Do not assume the first column is frequency or the second column is the response.
- Every plotted variable must be read by explicit column name or user selection.
- Frequency units must be checked from the header or conservatively inferred and reported.
- For 400-500 MHz antennas, prefer `Frequency (MHz)`.
- Do not label GHz data as MHz, or MHz data as GHz.
- Do not smooth, delete, modify, or fabricate data unless the user explicitly requests a documented visual-only operation.

## Variable Semantics

- `dB(S(1,1))` and `mag(S(1,1))` are different physical quantities.
- VSWR must come from a VSWR column or a documented calculation from `|S11|`.
- Impedance plots must distinguish real and imaginary parts.
- `GainTotal`, `RealizedGainTotal`, and `DirectivityTotal` must not be mixed.
- Realized Gain is preferred when port mismatch influence matters.
- Absolute radiation patterns use dBi; normalized patterns must be labeled `Normalized` and must not use dBi.

## Required Unknowns To Report

- Port reference impedance, reference plane, renormalization, and de-embed status for S11, VSWR, Smith, and impedance plots.
- Target operating band if the user has not specified it.
- Radiation-pattern cut definition: theta/phi sweep, fixed variable, and angle range.
- Polarization meaning: main/cross polarization or RHCP/LHCP/AR.
- Whether data are simulated or measured when not explicit.

## Engineering Thresholds

- S11: mark `-10 dB` unless the user provides another threshold.
- VSWR: mark `VSWR = 2`.
- Axial Ratio: mark `3 dB`.
- Target bands should be marked with vertical lines or a light shaded region.
- Metric conclusions must come from raw data or documented interpolation, not from image pixels.

## Output Note Contents

Every generated figure should have a short note containing:

- Input file name.
- Used columns and units.
- Unit conversions.
- Target band and thresholds.
- Normalization or interpolation status.
- Main engineering conclusion.
