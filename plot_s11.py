#!/usr/bin/env python3
"""Create publication-ready S11 and realized-gain figures from HFSS CSV files.

Examples:
    python plot_s11.py                    # Open the terminal menu.
    python plot_s11.py D:\\CSV\\my_s11.csv --label "Prototype"
    python plot_s11.py D:\\CSV --xlim 8 20 --mark-minima --mark-peak
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Iterable

try:
    import matplotlib.pyplot as plt
    import numpy as np
except ModuleNotFoundError as error:
    raise SystemExit(
        "Missing Python dependencies. Install them once with:\n"
        "  py -m pip install numpy matplotlib"
    ) from error


S11_LINE_COLOR = "#C62828"
GAIN_LINE_COLOR = "#1565C0"
THRESHOLD_COLOR = "#555555"
DEFAULT_THRESHOLD_DB = -10.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export publication-ready S11 and realized-gain figures from HFSS CSV files."
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=None,
        help="CSV file or directory. Omit it to open the terminal menu.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for figures (default: <input directory>/figures).",
    )
    parser.add_argument(
        "--label",
        default=None,
        help="Legend label for a single input file (default: detected automatically).",
    )
    parser.add_argument(
        "--xlim",
        nargs=2,
        type=float,
        metavar=("FMIN", "FMAX"),
        help="Frequency limits in GHz, for example: --xlim 8 20.",
    )
    parser.add_argument(
        "--ylim",
        nargs=2,
        type=float,
        metavar=("YMIN", "YMAX"),
        help="S11 limits in dB, for example: --ylim -35 0.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD_DB,
        help="S11 reference level in dB (default: -10).",
    )
    parser.add_argument(
        "--no-threshold",
        action="store_true",
        help="Do not draw the S11 reference level.",
    )
    parser.add_argument(
        "--mark-minima",
        action="store_true",
        help="Mark local S11 minima below the reference level.",
    )
    parser.add_argument(
        "--mark-peak",
        action="store_true",
        help="Mark the maximum realized-gain point.",
    )
    parser.add_argument(
        "--center-frequencies",
        nargs="+",
        type=float,
        default=None,
        metavar="FC",
        help="Mark center frequencies in GHz, for example: --center-frequencies 11.27 16.05.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=600,
        help="PNG resolution (default: 600 DPI).",
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        help="Open the terminal menu for the selected directory.",
    )
    return parser.parse_args()


def clean_number(value: str) -> float | None:
    """Return a number from a CSV cell, accepting common HFSS notations."""
    text = value.strip().replace("\ufeff", "")
    if not text:
        return None
    text = text.replace("dB", "").replace("DB", "")
    try:
        return float(text)
    except ValueError:
        return None


def read_hfss_csv(path: Path) -> tuple[np.ndarray, np.ndarray, str, str]:
    """Read the first numeric frequency/S-parameter pair from a HFSS CSV."""
    raw_lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    raw_lines = [line for line in raw_lines if line.strip()]
    if not raw_lines:
        raise ValueError("The file is empty.")

    sample = "\n".join(raw_lines[:20])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel

    rows = list(csv.reader(raw_lines, dialect))
    data_start = None
    numeric_columns: list[int] = []
    for index, row in enumerate(rows):
        numeric_columns = [i for i, cell in enumerate(row) if clean_number(cell) is not None]
        if len(numeric_columns) >= 2:
            data_start = index
            break
    if data_start is None:
        raise ValueError("Could not find two numeric data columns.")

    header_row = rows[data_start - 1] if data_start else []
    normalized_headers = [re.sub(r"[^a-z0-9]", "", cell.lower()) for cell in header_row]
    frequency_col = next(
        (index for index, header in enumerate(normalized_headers) if "freq" in header),
        numeric_columns[0],
    )
    response_col = next(
        (
            index
            for index, header in enumerate(normalized_headers)
            if index != frequency_col
            and ("realizedgain" in header or "s11" in header)
        ),
        next((index for index in numeric_columns if index != frequency_col), numeric_columns[1]),
    )
    frequency_header = (
        header_row[frequency_col].strip() if frequency_col < len(header_row) else "Frequency"
    )
    response_header = (
        header_row[response_col].strip() if response_col < len(header_row) else "S11"
    )

    frequency: list[float] = []
    response: list[float] = []
    for row in rows[data_start:]:
        if max(frequency_col, response_col) >= len(row):
            continue
        x = clean_number(row[frequency_col])
        y = clean_number(row[response_col])
        if x is not None and y is not None:
            frequency.append(x)
            response.append(y)

    if len(frequency) < 2:
        raise ValueError("Fewer than two valid data points were found.")

    x = np.asarray(frequency, dtype=float)
    y = np.asarray(response, dtype=float)
    order = np.argsort(x)
    return x[order], y[order], frequency_header, response_header


def to_ghz(frequency: np.ndarray, header: str) -> np.ndarray:
    """Convert frequency to GHz from HFSS header units or sensible magnitudes."""
    unit_match = re.search(r"(?:\[|\()\s*((?:k|m|g|t)?hz)\s*(?:\]|\))", header, re.I)
    unit = unit_match.group(1).lower() if unit_match else ""
    scale = {
        "khz": 1e-6,
        "mhz": 1e-3,
        "ghz": 1.0,
        "thz": 1e3,
        "hz": 1e-9,
    }.get(unit)
    if scale is not None:
        return frequency * scale

    maximum = float(np.nanmax(np.abs(frequency)))
    if maximum >= 1e8:
        return frequency * 1e-9
    if maximum >= 1e5:
        return frequency * 1e-3
    return frequency


def local_minima(x: np.ndarray, y: np.ndarray, threshold: float) -> Iterable[tuple[float, float]]:
    """Yield local minima below the selected reference level."""
    for index in range(1, len(y) - 1):
        if y[index] <= y[index - 1] and y[index] < y[index + 1] and y[index] < threshold:
            yield float(x[index]), float(y[index])


def response_kind(response_header: str) -> str:
    """Classify the HFSS response using its CSV column header."""
    normalized = re.sub(r"[^a-z0-9]", "", response_header.lower())
    if "realizedgain" in normalized:
        return "gain"
    if "s11" in normalized:
        return "s11"
    return "response"


def response_style(kind: str) -> tuple[str, str, str, str]:
    if kind == "gain":
        return "Realized Gain", "Realized Gain (dB)", "Realized_Gain", GAIN_LINE_COLOR
    if kind == "s11":
        return r"$S_{11}$", r"$S_{11}$ (dB)", "S11", S11_LINE_COLOR
    return "Response", "Response (dB)", "Response", S11_LINE_COLOR


def plot_response(
    frequency_ghz: np.ndarray,
    response_db: np.ndarray,
    source_name: str,
    label: str,
    kind: str,
    output_base: Path,
    args: argparse.Namespace,
) -> None:
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["Times New Roman", "DejaVu Serif"],
            "font.size": 11,
            "mathtext.fontset": "stix",
            "axes.linewidth": 1.0,
            "axes.labelpad": 7,
            "legend.frameon": False,
            "savefig.facecolor": "white",
        }
    )

    fig, ax = plt.subplots(figsize=(7.2, 4.5), constrained_layout=True)
    _, y_label, _, line_color = response_style(kind)
    ax.plot(frequency_ghz, response_db, color=line_color, linewidth=2.0, label=label)

    if kind == "s11" and not args.no_threshold:
        ax.axhline(
            args.threshold,
            color=THRESHOLD_COLOR,
            linestyle="--",
            linewidth=1.0,
            label=rf"{args.threshold:g} dB",
        )

    if kind == "s11" and args.mark_minima:
        for x_min, y_min in local_minima(frequency_ghz, response_db, args.threshold):
            ax.plot(x_min, y_min, marker="o", color=line_color, markersize=4)
            ax.annotate(
                rf"{x_min:.2f} GHz",
                (x_min, y_min),
                xytext=(0, -17),
                textcoords="offset points",
                ha="center",
                va="top",
                fontsize=9,
            )

    if kind == "gain" and args.mark_peak:
        peak_index = int(np.nanargmax(response_db))
        peak_x = float(frequency_ghz[peak_index])
        peak_y = float(response_db[peak_index])
        ax.plot(peak_x, peak_y, marker="o", color=line_color, markersize=5)
        ax.annotate(
            f"{peak_x:.2f} GHz\n{peak_y:.2f} dB",
            (peak_x, peak_y),
            xytext=(0, 15),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel(y_label)
    ax.set_title(source_name, pad=10, fontsize=12)
    ax.grid(True, which="major", color="#D9D9D9", linewidth=0.65)
    ax.grid(True, which="minor", color="#EEEEEE", linewidth=0.45)
    ax.minorticks_on()
    ax.tick_params(which="both", direction="in", top=True, right=True)

    if args.xlim:
        ax.set_xlim(args.xlim)
    else:
        ax.margins(x=0.02)
    if args.ylim:
        ax.set_ylim(args.ylim)
    else:
        lower = float(np.nanmin(response_db))
        upper = float(np.nanmax(response_db))
        if kind == "s11" and not args.no_threshold:
            lower = min(lower, args.threshold)
            upper = max(upper, args.threshold)
        padding = max(1.0, (upper - lower) * 0.1)
        ax.set_ylim(lower - padding, upper + padding)

    if kind == "s11" and args.center_frequencies:
        for center_frequency in args.center_frequencies:
            ax.axvline(
                center_frequency,
                color="#424242",
                linestyle=":",
                linewidth=1.15,
                zorder=1,
            )
            ax.text(
                center_frequency,
                0.97,
                rf"$f_c$ = {center_frequency:.2f} GHz",
                transform=ax.get_xaxis_transform(),
                ha="center",
                va="top",
                fontsize=9,
                color="#333333",
            )

    ax.legend(loc="best")
    for extension in ("png", "pdf", "svg"):
        fig.savefig(output_base.with_suffix(f".{extension}"), dpi=args.dpi, bbox_inches="tight")
    plt.close(fig)


def csv_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        if input_path.suffix.lower() != ".csv":
            raise ValueError("Input file must have a .csv extension.")
        return [input_path]
    if not input_path.is_dir():
        raise ValueError(f"Input path does not exist: {input_path}")
    return sorted(path for path in input_path.glob("*.csv") if path.is_file())


def process_files(files: list[Path], args: argparse.Namespace) -> None:
    output_dir = args.output_dir or (files[0].parent / "figures")
    output_dir.mkdir(parents=True, exist_ok=True)

    for path in files:
        try:
            frequency, response_db, frequency_header, response_header = read_hfss_csv(path)
            frequency_ghz = to_ghz(frequency, frequency_header)
            kind = response_kind(response_header)
            default_label, _, output_suffix, _ = response_style(kind)
            label = args.label or default_label
            output_base = output_dir / f"{path.stem}_{output_suffix}"
            plot_response(
                frequency_ghz,
                response_db,
                path.stem,
                label,
                kind,
                output_base,
                args,
            )
            print(f"Created: {output_base.with_suffix('.png')}")
            print(f"Created: {output_base.with_suffix('.pdf')}")
            print(f"Created: {output_base.with_suffix('.svg')}")
        except (OSError, ValueError, csv.Error) as error:
            print(f"Skipped {path.name}: {error}")


def prompt_range(label: str, unit: str) -> list[float] | None:
    while True:
        value = input(f"{label} ({unit}, blank = automatic): ").strip()
        if not value:
            return None
        try:
            lower, upper = (float(item) for item in value.replace(",", " ").split())
            if lower >= upper:
                raise ValueError
            return [lower, upper]
        except ValueError:
            print("  Please enter two numbers, for example: 8 20")


def prompt_yes_no(label: str, default: bool = False) -> bool:
    default_text = "Y/n" if default else "y/N"
    while True:
        value = input(f"{label} [{default_text}]: ").strip().lower()
        if not value:
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("  Please enter y or n.")


def select_files(directory: Path) -> list[Path] | None:
    try:
        files = csv_files(directory)
    except ValueError as error:
        print(f"\nError: {error}")
        return None

    if not files:
        print(f"\nNo CSV files found in: {directory}")
        print("Export the S11 data from HFSS as CSV and place it in this folder.")
        return None

    print("\nAvailable CSV files:")
    print("  0. All files")
    for index, path in enumerate(files, start=1):
        print(f"  {index}. {path.name}")

    while True:
        value = input("\nChoose a file (0 = all, q = quit): ").strip().lower()
        if value in {"q", "quit"}:
            return None
        if value in {"", "0", "all"}:
            return files
        try:
            selected = int(value)
            if 1 <= selected <= len(files):
                return [files[selected - 1]]
        except ValueError:
            pass
        print("  Choose a number from the list.")


def detected_kinds(files: list[Path]) -> set[str]:
    """Inspect the selected headers so the menu shows relevant controls."""
    kinds: set[str] = set()
    for path in files:
        try:
            _, _, _, response_header = read_hfss_csv(path)
            kinds.add(response_kind(response_header))
        except (OSError, ValueError, csv.Error):
            continue
    return kinds


def run_terminal_ui(directory: Path, args: argparse.Namespace) -> None:
    print("=" * 62)
    print("    HFSS S11 and Realized Gain Figure Generator")
    print("=" * 62)
    print(f"Data folder: {directory}")

    files = select_files(directory)
    if not files:
        return
    kinds = detected_kinds(files)
    kind_names = {
        "s11": "S11",
        "gain": "Realized Gain",
        "response": "Response",
    }
    print("Detected: " + ", ".join(kind_names[kind] for kind in sorted(kinds)))

    print("\nFigure settings (press Enter to use the shown default):")
    label = input("Legend label [automatic]: ").strip()
    args.label = label or None
    args.xlim = prompt_range("Frequency range", "GHz")
    args.ylim = prompt_range("Response range", "dB")

    if "s11" in kinds:
        threshold = input(f"S11 reference level in dB [{args.threshold:g}; n = hide]: ").strip()
        if threshold.lower() == "n":
            args.no_threshold = True
        elif threshold:
            try:
                args.threshold = float(threshold)
                args.no_threshold = False
            except ValueError:
                print(f"  Invalid value; using {args.threshold:g} dB.")
        args.mark_minima = prompt_yes_no("Mark S11 resonant minima", default=False)
    else:
        args.no_threshold = True
        args.mark_minima = False
    args.mark_peak = "gain" in kinds and prompt_yes_no(
        "Mark realized-gain peak", default=False
    )
    output_text = input("Output folder [figures]: ").strip()
    if output_text:
        requested_output = Path(output_text)
        args.output_dir = (
            requested_output if requested_output.is_absolute() else directory / requested_output
        )
    else:
        args.output_dir = directory / "figures"

    dpi_text = input(f"PNG resolution in DPI [{args.dpi}]: ").strip()
    if dpi_text:
        try:
            dpi = int(dpi_text)
            if dpi <= 0:
                raise ValueError
            args.dpi = dpi
        except ValueError:
            print(f"  Invalid value; using {args.dpi} DPI.")

    print("\nSummary")
    print(f"  Files: {len(files)}")
    print(f"  Output: {args.output_dir}")
    print(f"  Formats: PNG ({args.dpi} DPI), PDF, SVG")
    if "s11" not in kinds:
        print("  S11 reference: not applicable")
    elif args.no_threshold:
        print("  S11 reference: hidden")
    else:
        print(f"  Reference: {args.threshold:g} dB")

    if prompt_yes_no("\nCreate figures now", default=True):
        process_files(files, args)
        print("\nDone. Press Enter to close.")
        input()
    else:
        print("\nCancelled.")


def main() -> None:
    args = parse_args()
    if args.ui or args.input is None:
        requested_path = args.input or Path(__file__).resolve().parent
        directory = requested_path if requested_path.is_dir() else requested_path.parent
        run_terminal_ui(directory.resolve(), args)
        return

    try:
        files = csv_files(args.input.resolve())
    except ValueError as error:
        raise SystemExit(f"Error: {error}") from error
    if not files:
        raise SystemExit(f"No CSV files found in: {args.input.resolve()}")
    process_files(files, args)


if __name__ == "__main__":
    main()
