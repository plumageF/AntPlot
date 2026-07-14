# HFSS Paper Plotter

HFSS Paper Plotter creates TAP/AWPL-style publication figures from HFSS CSV exports.

## Design Rules

- Automatic detection is optional convenience, not a source of truth.
- Every plot operation can be manually controlled from CLI, terminal UI, or config.
- Original HFSS CSV files are never modified by plotting commands.
- PNG/PDF/SVG are exported together by default.

## V1 Commands

Inspect a CSV:

```powershell
python main.py inspect "D:\CSV\S Parameter Plot 1.csv"
```

Auto-detect and batch plot:

```powershell
python main.py auto "D:\CSV" --style ieee_tap
```

Manual S11:

```powershell
python main.py s11 "D:\CSV\S Parameter Plot 1.csv" --x-column "Freq [GHz]" --y-column "dB(S(1,1)) []" --xlim 1 2 --ylim -30 0 --fl 1.68 --fc 1.70 --fh 1.72
```

Manual realized gain:

```powershell
python main.py gain "D:\CSV\Realized Gain Plot 1.csv" --x-column "Freq [GHz]" --y-column "dB(RealizedGainTotal) []" --mark-peak
```

Manual radiation pattern:

```powershell
python main.py pattern "D:\CSV\11.7.csv" --theta-column "Theta [deg]" --phi-column "Phi [deg]" --gain-column "dB(RealizedGainTotal) []"
```

Manual axial ratio:

```powershell
python main.py ar "D:\CSV\axial_ratio.csv" --style paper_bold --ar-threshold 3
```

Manual VSWR:

```powershell
python main.py vswr "D:\CSV\vswr.csv" --style paper_bold --vswr-threshold 2
```

Auto-detected AR column patterns include `AxialRatio`, `Axial Ratio`, `dB(AxialRatioValue)`, and `AR`.
Auto-detected VSWR column patterns include `VSWR`, `VSMR`, and `Voltage Standing Wave Ratio`.

Manual efficiency:

```powershell
python main.py eff "D:\CSV\efficiency.csv" --style paper_bold
```

Auto-detected efficiency column patterns include `RadiationEfficiency`, `TotalEfficiency`, and `Efficiency`.

Manual HPBW:

```powershell
python main.py hpbw "D:\CSV\hpbw.csv" --style paper_bold
```

Auto-detected beamwidth column patterns include `HPBW`, `HalfPowerBeamwidth`, `3dBBeamwidth`, and `Beamwidth`.

Manual Smith chart:

```powershell
python main.py smith "D:\CSV\smith.csv" --real-column "re(S(1,1)) []" --imag-column "im(S(1,1)) []"
```

Co-pol / cross-pol radiation pattern:

```powershell
python main.py pattern "D:\CSV\pattern.csv" --theta-column "Theta [deg]" --phi-column "Phi [deg]" --gain-columns "Co-pol [dB]" "Cross-pol [dB]" --labels "Co-pol" "Cross-pol"
```

Manual reference-style multi-curve efficiency plot:

```powershell
python main.py xy "D:\CSV\efficiency.csv" --style paper_bold --x-column "Frequency [MHz]" --y-columns "Ref 1" "Ref 2" "Ref 3" "Ref 4" --ylabel "Radiation Efficiency (%)"
```

Sampling controls:

```powershell
python main.py xy "D:\CSV\efficiency.csv" --style paper_bold --sample-every 3 --marker-every 2
python main.py s11 "D:\CSV\s11.csv" --style paper_bold --sample-step 10MHz --marker-every 4 --smooth
```

- `--sample-every N`: plot every Nth point.
- `--sample-step 10MHz`: interpolate to a fixed frequency interval.
- `--marker-every N`: keep the plotted curve denser, but show markers every Nth point.
- `--smooth` / `--no-smooth`: force smoothing on or off.

S11 annotation controls:

```powershell
python main.py s11 "D:\CSV\s11.csv" --style paper_bold --band-label-loc auto
python main.py s11 "D:\CSV\s11.csv" --style paper_bold --band-label-loc lower-right
python main.py s11 "D:\CSV\s11.csv" --style paper_bold --no-band-label
```

- `--band-label-loc auto`: automatically chooses a less crowded corner.
- `--band-label-loc upper-left|upper-right|lower-left|lower-right`: manually places the band label box.
- `--no-band-label`: hides the `fL/fc/fH/BW` annotation box.

Terminal UI:

```powershell
python main.py ui "D:\CSV"
```

## Next Steps

- Add reference-paper style extraction after target TAP/AWPL PDFs or screenshots are provided.
- Add multi-subfigure composition.
- Add measured-vs-simulated curve merging.
- Add figure report files with resonance, bandwidth, peak gain, and plotted columns.
