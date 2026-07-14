#!/usr/bin/env python3
"""Retune an HFSS S11 CSV to a target center frequency and -10 dB bandwidth.

This creates a processed copy of the original CSV and publication-style figures.
The original CSV is never overwritten.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


THRESHOLD_DB = -10.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a processed S11 CSV with a target resonance and bandwidth."
    )
    parser.add_argument("input_csv", type=Path, help="HFSS S11 CSV file.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory. Default: same folder as the input CSV.",
    )
    parser.add_argument("--fc", type=float, default=1.70, help="Target center frequency in GHz.")
    parser.add_argument(
        "--bw-mhz",
        type=float,
        default=40.0,
        help="-10 dB target bandwidth in MHz.",
    )
    parser.add_argument(
        "--min-db",
        type=float,
        default=None,
        help="Target resonance depth in dB. Default: keep original minimum depth.",
    )
    parser.add_argument(
        "--formats",
        nargs="+",
        default=["png", "pdf", "svg"],
        help="Figure formats to export.",
    )
    return parser.parse_args()


def detect_columns(fieldnames: list[str]) -> tuple[str, str]:
    freq_col = next((c for c in fieldnames if "freq" in c.lower()), None)
    s11_col = next(
        (
            c
            for c in fieldnames
            if "db" in c.lower() and ("s(1,1)" in c.lower() or "s11" in c.lower())
        ),
        None,
    )
    if freq_col is None:
        raise ValueError("Could not find a frequency column, such as 'Freq [GHz]'.")
    if s11_col is None:
        raise ValueError("Could not find an S11 dB column, such as 'dB(S(1,1)) []'.")
    return freq_col, s11_col


def moving_average(values: np.ndarray, window: int = 7) -> np.ndarray:
    if window <= 1:
        return values.copy()
    pad_left = window // 2
    pad_right = window - 1 - pad_left
    padded = np.pad(values, (pad_left, pad_right), mode="edge")
    kernel = np.ones(window, dtype=float) / window
    return np.convolve(padded, kernel, mode="valid")


def crossings_for_threshold(freq: np.ndarray, y_db: np.ndarray, threshold: float) -> list[float]:
    crossings: list[float] = []
    for index in range(len(freq) - 1):
        left = y_db[index] - threshold
        right = y_db[index + 1] - threshold
        if left == 0:
            crossings.append(float(freq[index]))
        if left * right < 0:
            t = (threshold - y_db[index]) / (y_db[index + 1] - y_db[index])
            crossings.append(float(freq[index] + t * (freq[index + 1] - freq[index])))
    if y_db[-1] == threshold:
        crossings.append(float(freq[-1]))
    return crossings


def band_around_fc(freq: np.ndarray, y_db: np.ndarray, fc: float) -> tuple[float, float] | None:
    crossings = crossings_for_threshold(freq, y_db, THRESHOLD_DB)
    left = [value for value in crossings if value <= fc]
    right = [value for value in crossings if value >= fc]
    if not left or not right:
        return None
    return max(left), min(right)


def make_retuned_curve(
    freq: np.ndarray,
    original_y: np.ndarray,
    fc: float,
    bw_ghz: float,
    min_db: float,
) -> np.ndarray:
    """Create a smooth single-notch S11 curve with the requested -10 dB bandwidth."""
    clipped = np.maximum(original_y, -7.2)
    baseline = moving_average(clipped, window=7)
    baseline = np.clip(baseline, -7.2, -3.4)

    baseline_at_fc = float(np.interp(fc, freq, baseline))
    amplitude = baseline_at_fc - min_db
    if amplitude <= baseline_at_fc - THRESHOLD_DB:
        raise ValueError("The requested minimum is not deep enough to cross -10 dB.")

    def curve_for_sigma(sigma: float) -> np.ndarray:
        notch = amplitude * np.exp(-0.5 * ((freq - fc) / sigma) ** 2)
        return baseline - notch

    target_width = bw_ghz
    low_sigma = max(target_width / 100.0, 1e-5)
    high_sigma = target_width * 10.0

    for _ in range(80):
        sigma = (low_sigma + high_sigma) / 2.0
        candidate = curve_for_sigma(sigma)
        band = band_around_fc(freq, candidate, fc)
        width = 0.0 if band is None else band[1] - band[0]
        if width < target_width:
            low_sigma = sigma
        else:
            high_sigma = sigma

    retuned = curve_for_sigma((low_sigma + high_sigma) / 2.0)
    nearest_fc = int(np.argmin(np.abs(freq - fc)))
    if abs(float(freq[nearest_fc]) - fc) < 1e-9:
        retuned[nearest_fc] = min_db
    return retuned


def write_retuned_csv(
    rows: list[dict[str, str]],
    fieldnames: list[str],
    s11_col: str,
    y_db: np.ndarray,
    output_csv: Path,
) -> None:
    output_rows = [dict(row) for row in rows]
    for row, value in zip(output_rows, y_db, strict=True):
        row[s11_col] = f"{value:.12g}"

    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)


def plot_retuned(
    freq: np.ndarray,
    y_db: np.ndarray,
    output_base: Path,
    fc: float,
    bw_ghz: float,
    formats: list[str],
) -> None:
    half_bw = bw_ghz / 2.0
    fl = fc - half_bw
    fh = fc + half_bw

    plt.rcParams.update(
        {
            "font.family": "Arial",
            "font.size": 10,
            "axes.linewidth": 1.0,
            "xtick.direction": "in",
            "ytick.direction": "in",
            "xtick.major.size": 4,
            "ytick.major.size": 4,
            "xtick.minor.size": 2,
            "ytick.minor.size": 2,
        }
    )

    fig, ax = plt.subplots(figsize=(6.3, 4.2), constrained_layout=True)
    ax.plot(freq, y_db, color="#c62828", linewidth=2.2, label=r"$S_{11}$")
    ax.axhline(THRESHOLD_DB, color="#555555", linestyle="--", linewidth=1.0)
    ax.axvspan(fl, fh, color="#c62828", alpha=0.09, linewidth=0)
    ax.axvline(fc, color="#333333", linestyle=":", linewidth=1.0)
    ax.axvline(fl, color="#777777", linestyle=":", linewidth=0.9)
    ax.axvline(fh, color="#777777", linestyle=":", linewidth=0.9)

    ax.text(
        0.045,
        0.95,
        "\n".join(
            [
                r"$f_L$ = %.2f GHz" % fl,
                r"$f_c$ = %.2f GHz" % fc,
                r"$f_H$ = %.2f GHz" % fh,
                "BW = %.0f MHz" % (bw_ghz * 1000.0),
            ]
        ),
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=9,
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.8, "pad": 3},
    )
    ax.text(
        0.985,
        THRESHOLD_DB + 0.35,
        "-10 dB",
        transform=ax.get_yaxis_transform(),
        ha="right",
        va="bottom",
        fontsize=8,
        color="#555555",
    )

    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel(r"$S_{11}$ (dB)")
    ax.set_xlim(float(freq.min()), float(freq.max()))
    ax.set_ylim(min(-30.0, float(np.floor(y_db.min() / 5.0) * 5.0)), 0.0)
    ax.minorticks_on()
    ax.grid(True, which="major", linestyle="-", linewidth=0.45, alpha=0.22)
    ax.grid(True, which="minor", linestyle=":", linewidth=0.35, alpha=0.15)

    for ext in formats:
        ext = ext.lower().lstrip(".")
        fig.savefig(output_base.with_suffix(f".{ext}"), dpi=600)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    input_csv = args.input_csv
    output_dir = args.output_dir or input_csv.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    with input_csv.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    if not fieldnames or not rows:
        raise SystemExit("The CSV file is empty or missing headers.")

    freq_col, s11_col = detect_columns(fieldnames)
    freq = np.array([float(row[freq_col]) for row in rows], dtype=float)
    original_y = np.array([float(row[s11_col]) for row in rows], dtype=float)

    order = np.argsort(freq)
    if not np.all(order == np.arange(len(freq))):
        raise SystemExit("Frequency values must be sorted in ascending order.")

    bw_ghz = args.bw_mhz / 1000.0
    min_db = args.min_db if args.min_db is not None else float(original_y.min())
    retuned_y = make_retuned_curve(freq, original_y, args.fc, bw_ghz, min_db)

    tag = f"retuned_{args.fc:.2f}GHz_BW{args.bw_mhz:.0f}MHz".replace(".", "p")
    output_base = output_dir / f"{input_csv.stem}_{tag}"
    output_csv = output_base.with_suffix(".csv")
    write_retuned_csv(rows, fieldnames, s11_col, retuned_y, output_csv)
    plot_retuned(freq, retuned_y, output_base, args.fc, bw_ghz, args.formats)

    band = band_around_fc(freq, retuned_y, args.fc)
    min_index = int(np.argmin(retuned_y))
    print(f"Output CSV: {output_csv}")
    for ext in args.formats:
        print(f"Output figure: {output_base.with_suffix('.' + ext.lower().lstrip('.'))}")
    print(f"Minimum: {freq[min_index]:.4f} GHz, {retuned_y[min_index]:.4f} dB")
    if band:
        print(
            "Estimated -10 dB band: "
            f"{band[0]:.4f}-{band[1]:.4f} GHz, "
            f"BW={(band[1] - band[0]) * 1000.0:.2f} MHz"
        )


if __name__ == "__main__":
    main()
