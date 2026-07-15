# AntPlot User Guide / 使用说明

## 1. Installation / 安装

Recommended for Windows users: download `AntPlot-Windows-Portable-v0.1.0.zip` from the GitHub Releases page, extract it, and run `install_and_start.bat`. Python 3.10 or newer is required; Node.js is not required for the portable package.

For developers, follow the source deployment instructions in the root [README](../README.md).

After startup, open `http://127.0.0.1:4173/`.

## 2. Five-step workflow / 五步流程

1. **Import data / 导入数据**: choose one file, multiple files, a directory scan, or a previously exported JSON project configuration.
2. **Recognition and mapping / 识别与映射**: review the detected report domain, primary sweep, quantity, candidate curves, and warnings. Confirm the mapping if it is not unambiguous.
3. **Curve manager / 曲线管理**: enable required curves, rename them, reorder their legend order, and adjust color, line style, linewidth, and marker display.
4. **Plot settings / 单图设置**: choose axis ranges and labels; set the working band and threshold for the relevant engineering plot type. Radiation patterns support Cartesian and polar layouts.
5. **Preview and export / 预览与导出**: generate the backend-rendered preview, then export PNG, PDF, SVG, JSON, and TXT/Markdown reports.

The preview and final exports use the same Python plotting logic. Changing a curve style and refreshing the preview changes exported figures too.

## 3. Importing HFSS-like data / 导入 HFSS 数据

Use **single/multiple files** for a few known files, or **directory scan** to build an index before selecting files. Supported data extensions include CSV, TXT, DAT, XLSX/XLS, S1P/S2P/SNP.

AntPlot does not assume that the first column is frequency or the second is S11. It inspects headers, units, and ranges. If headers are generic (`X`, `Y`, `Data`, `Value`) or the unit is unknown, AntPlot asks for confirmation and retains a warning.

### Common engineering data

| Intended figure | Typical X column | Typical Y column |
| --- | --- | --- |
| S11 / Return Loss | `Freq [GHz]` | `dB(S(1,1)) []`, `S11 (dB)` |
| VSWR | `Freq` | `VSWR(1)` or a confirmed S11-derived curve |
| Realized Gain | `Freq` | `RealizedGainTotal [dB]` |
| Axial Ratio | `Freq`, `Theta`, or `Phi` | `dB(AxialRatioValue)` |
| Radiation Pattern | `Theta [deg]`, `Phi [deg]`, or `Angle` | Gain, Realized Gain, RHCP/LHCP, co-/cross-pol |
| Smith Chart | `Freq` | real/imaginary S11 or Zin; magnitude/phase is also supported |

For S11, linear magnitude is converted with `20 log10(|S11|)`. Real/imaginary values are combined into a complex quantity before conversion. `Formatted Data` from a VNA is treated as a candidate rather than a certain S11 quantity.

## 4. Curve manager / 曲线管理器

Only enabled and plot-compatible curves participate in preview, export, and engineering metrics. The curve order is the legend order.

- Use one curve for a simple trace, or overlay simulated/measured/parameter-sweep cases.
- Marker display is off by default for dense curves. `marker_every` changes only marker display, never the original data or metrics.
- For long-form parameter sweeps, AntPlot groups by parameter columns before checking duplicate frequency points. Repeated frequencies belonging to separate parameter combinations are not an error.
- Curves with incompatible quantities are dimmed and excluded. For example, a Theta/Phi Realized Gain curve cannot be rendered as an S11 frequency response.

## 5. Plot-specific settings / 图类型设置

### S11 / Return Loss

Set the working band in MHz and the S11 threshold (default `-10 dB`). The figure displays the threshold and working-band boundaries. The report calculates resonance and bandwidth from data; linear interpolation is used only for threshold crossings and is recorded in the report.

### Radiation Pattern

Choose **Cartesian Pattern** for angle-versus-gain curves or **Polar Pattern** for circular plots. In polar mode, choose radial limits, optional normalization, angle labels, and legend position. Polar plots use 0° at the top and increase clockwise by default. A `0–180°` cut is not mirrored automatically.

### Smith Chart

Set the reference impedance, normally `50 ohm`. Check the warnings about reference plane, renormalization, and de-embedding before drawing conclusions.

### XY Multi-Curve

This is a free-form plotting mode rather than an engineering report. It accepts a strict wide table: one header row, first column as X, remaining numeric columns as Y curves. It preserves file row order by default and reports data ranges only, not antenna pass/fail conclusions.

## 6. Exports / 导出

Choose an output directory and filename prefix. Recommended outputs:

- **PDF/SVG**: vector figures for paper layout and editing.
- **PNG (600 dpi)**: Word, PowerPoint, or manuscript systems that need raster images.
- **JSON**: recover the curve selection, styles, mapping, project settings, and export settings later.
- **TXT/Markdown**: retain per-curve metrics, warnings, and unconfirmed engineering conditions.

If errors remain, AntPlot can create a debugging image but suppresses a definitive engineering conclusion report.

## 7. Included sample set / 附带测试样例

`examples/gallery` contains public input CSVs and their representative generated figures:

- `s11_standard.csv` and `s11_standard.png`: S11 with threshold and working band.
- `gain_frequency.csv` and `gain_frequency.png`: Realized Gain versus frequency.
- `pattern_polar.csv` and `pattern_polar.png`: polar radiation pattern.
- `smith.csv` and `smith.png`: Smith chart.
- `axial_ratio.csv` and `axial_ratio.png`: axial-ratio curve.
- `vswr.csv` and `vswr.png`: VSWR curve.

## 8. Engineering cautions / 工程注意事项

The application calculates from raw data, not image pixels. It does not smooth, resample, delete outliers, or infer missing frequency regions by default. Warnings should be reviewed when frequency units, port reference impedance, reference plane, normalization, pattern cut, or polarization are not confirmed.
