# AntPlot Data Formats

AntPlot accepts HFSS/CST/ADS/VNA-style CSV and related text data through the importer. The importer inspects headers, units, sweeps, fixed variables and curve families; it does not blindly assume that column 1 is frequency or column 2 is S11.

## Engineering plots

Common recognized forms include:

```csv
Freq [GHz],dB(S(1,1)) []
0.40,-8
0.45,-18
```

```csv
Freq [GHz],RealizedGainTotal [dBi]
0.40,0.5
0.45,1.2
```

```csv
Theta [deg],Phi [deg],dB(RealizedGainTotal) []
0,0,-6
30,0,0
```

The importer supports dB S11, linear magnitude, re/im pairs, mag/phase pairs, VSWR, gain, axial ratio, efficiency, angle cuts and Smith-chart impedance/S-parameter data. Ambiguous units, `Formatted Data`, missing headers and unknown cuts remain warnings or require mapping confirmation.

## XY Multi-Curve

XY Multi-Curve is intentionally non-semantic. It requires a standard wide table: the first row is the header, the first column is X, and all later columns are numeric Y curves.

```csv
X,Curve A,Curve B
0,0,1
1,1,2
2,4,3
```

The original row order is preserved by default. Non-monotonic X is informational and repeated X is a warning. No S11, VSWR, gain, AR or HPBW engineering conclusion is produced for this mode.

## Data integrity

Missing/non-finite values and duplicate X points are retained as warnings. Curves are not silently smoothed, resampled, mirrored or stripped of outliers. Any interpolation used for a threshold or bandwidth calculation is recorded in the report.
