#!/usr/bin/env python3
"""Create normalized polar radiation-pattern figures from HFSS CSV exports."""

from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

try:
    import matplotlib.pyplot as plt
    import numpy as np
except ModuleNotFoundError as error:
    raise SystemExit(
        "Missing Python dependencies. Install them once with:\n"
        "  python -m pip install numpy matplotlib"
    ) from error


PLANE_COLORS = ("#C62828", "#1565C0", "#2E7D32", "#6A1B9A")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export polar radiation-pattern figures from HFSS CSV files."
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="CSV file or directory (default: the script directory).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for figures (default: <input directory>/figures).",
    )
    parser.add_argument(
        "--absolute",
        action="store_true",
        help="Plot absolute realized gain instead of normalizing the peak to 0 dB.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=600,
        help="PNG resolution (default: 600 DPI).",
    )
    return parser.parse_args()


def normalized_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def clean_number(value: str) -> float | None:
    try:
        return float(value.strip())
    except ValueError:
        return None


def header_index(headers: list[str], keyword: str) -> int:
    for index, header in enumerate(headers):
        if keyword in normalized_header(header):
            return index
    raise ValueError(f"Could not find a '{keyword}' column in the CSV header.")


def read_direction_csv(path: Path) -> tuple[float, dict[float, tuple[np.ndarray, np.ndarray]]]:
    """Read HFSS phi/theta realized-gain data and group it by phi cut."""
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as source:
        rows = list(csv.reader(source))
    rows = [row for row in rows if row]
    if len(rows) < 3:
        raise ValueError("The CSV does not contain enough data rows.")

    headers = [cell.strip() for cell in rows[0]]
    frequency_index = header_index(headers, "freq")
    phi_index = header_index(headers, "phi")
    theta_index = header_index(headers, "theta")
    gain_index = header_index(headers, "realizedgain")
    maximum_index = max(frequency_index, phi_index, theta_index, gain_index)

    planes: dict[float, list[tuple[float, float]]] = defaultdict(list)
    frequencies: list[float] = []
    for row in rows[1:]:
        if len(row) <= maximum_index:
            continue
        frequency = clean_number(row[frequency_index])
        phi = clean_number(row[phi_index])
        theta = clean_number(row[theta_index])
        gain = clean_number(row[gain_index])
        if None in {frequency, phi, theta, gain}:
            continue
        frequencies.append(float(frequency))
        planes[round(float(phi), 6)].append((float(theta), float(gain)))

    if not planes:
        raise ValueError("No valid phi/theta/gain samples were found.")

    grouped: dict[float, tuple[np.ndarray, np.ndarray]] = {}
    for phi, samples in planes.items():
        samples.sort(key=lambda item: item[0])
        theta, gain = zip(*samples)
        theta_array = np.asarray(theta, dtype=float)
        gain_array = np.asarray(gain, dtype=float)
        unique_theta = np.unique(np.round(theta_array, 6))
        if len(unique_theta) < 10 or float(np.ptp(theta_array)) < 300.0:
            continue
        if theta_array[-1] < 359.0:
            theta_array = np.append(theta_array, theta_array[0] + 360.0)
            gain_array = np.append(gain_array, gain_array[0])
        grouped[phi] = (np.deg2rad(theta_array), gain_array)

    if not grouped:
        raise ValueError("No full 0-360 degree direction-pattern sweep was found.")

    return float(np.median(frequencies)), grouped


def figure_limits(values: list[np.ndarray], absolute: bool) -> tuple[float, float, list[float]]:
    data_min = min(float(np.nanmin(value)) for value in values)
    data_max = max(float(np.nanmax(value)) for value in values)
    if absolute:
        lower = np.floor((data_min - 1.0) / 5.0) * 5.0
        upper = np.ceil((data_max + 1.0) / 5.0) * 5.0
        ticks = list(np.arange(lower, upper + 0.1, 5.0))
        return float(lower), float(upper), ticks

    lower = min(-5.0, float(np.floor(data_min / 5.0) * 5.0))
    ticks = list(np.arange(lower, 0.1, 5.0))
    return lower, 0.0, ticks


def plot_pattern(
    frequency_ghz: float,
    planes: dict[float, tuple[np.ndarray, np.ndarray]],
    source_name: str,
    output_base: Path,
    absolute: bool,
    dpi: int,
) -> None:
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["Times New Roman", "DejaVu Serif"],
            "font.size": 10,
            "mathtext.fontset": "stix",
            "axes.linewidth": 1.0,
            "legend.frameon": False,
            "savefig.facecolor": "white",
        }
    )

    all_gain = np.concatenate([gain for _, gain in planes.values()])
    peak_gain = float(np.nanmax(all_gain))
    plot_values = [gain if absolute else gain - peak_gain for _, gain in planes.values()]
    radial_min, radial_max, radial_ticks = figure_limits(plot_values, absolute)

    fig, ax = plt.subplots(figsize=(6.2, 5.7), subplot_kw={"projection": "polar"}, constrained_layout=True)
    for index, (phi, (theta, gain)) in enumerate(sorted(planes.items())):
        radial_gain = gain if absolute else gain - peak_gain
        ax.plot(
            theta,
            radial_gain,
            color=PLANE_COLORS[index % len(PLANE_COLORS)],
            linewidth=2.0,
            label=rf"$\phi$ = {phi:g} deg",
        )

    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_thetagrids(range(0, 360, 30))
    ax.set_rlim(radial_min, radial_max)
    ax.set_rticks(radial_ticks)
    ax.set_rlabel_position(135)
    ax.grid(True, color="#D5D5D5", linewidth=0.7)
    ax.set_title(f"Radiation Pattern at {frequency_ghz:.2f} GHz", pad=22, fontsize=13)
    ax.legend(loc="upper right", bbox_to_anchor=(1.26, 1.16))

    for extension in ("png", "pdf", "svg"):
        fig.savefig(
            output_base.parent / f"{output_base.name}.{extension}",
            dpi=dpi,
            bbox_inches="tight",
        )
    plt.close(fig)


def csv_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    if not input_path.is_dir():
        raise ValueError(f"Input path does not exist: {input_path}")
    return sorted(path for path in input_path.glob("*.csv") if path.is_file())


def main() -> None:
    args = parse_args()
    try:
        files = csv_files(args.input.resolve())
    except ValueError as error:
        raise SystemExit(f"Error: {error}") from error

    created = 0
    for path in files:
        try:
            frequency, planes = read_direction_csv(path)
        except (OSError, ValueError, csv.Error):
            continue

        output_dir = args.output_dir or (path.parent / "figures")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_base = output_dir / f"{path.stem}_Radiation_Pattern"
        plot_pattern(
            frequency,
            planes,
            path.stem,
            output_base,
            args.absolute,
            args.dpi,
        )
        for extension in ("png", "pdf", "svg"):
            print(f"Created: {output_base.parent / f'{output_base.name}.{extension}'}")
        created += 1

    if not created:
        raise SystemExit("No direction-pattern CSV files were detected.")


if __name__ == "__main__":
    main()
