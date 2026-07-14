"""Terminal UI for manual plotting."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from .plotting import plot_gain, plot_pattern, plot_s11
from .reader import csv_files, detect_kind, inspect_csv, read_hfss_csv
from .style import load_style


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def ask_float(prompt: str, default: float | None = None) -> float | None:
    text = ask(prompt, "" if default is None else str(default))
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        print("Invalid number; using automatic value.")
        return default


def ask_range(prompt: str) -> list[float] | None:
    text = ask(prompt + " (blank = auto)", "")
    if not text:
        return None
    try:
        a, b = [float(item) for item in text.replace(",", " ").split()]
        return [a, b]
    except ValueError:
        print("Invalid range; using automatic limits.")
        return None


def select_file(folder: Path) -> Path | None:
    files = csv_files(folder)
    if not files:
        print(f"No CSV files found in {folder}")
        return None
    print("\nCSV files:")
    for index, path in enumerate(files, 1):
        try:
            info = inspect_csv(path)
            print(f"  {index}. {path.name}  ({info.kind})")
        except Exception:
            print(f"  {index}. {path.name}")
    while True:
        value = ask("Choose file number, or q to quit", "1").lower()
        if value in {"q", "quit"}:
            return None
        try:
            selected = int(value)
            if 1 <= selected <= len(files):
                return files[selected - 1]
        except ValueError:
            pass
        print("Choose a valid number.")


def choose_column(headers: list[str], label: str, default: str | None) -> str | None:
    print(f"\n{label} columns:")
    for index, header in enumerate(headers, 1):
        marker = " *" if header == default else ""
        print(f"  {index}. {header}{marker}")
    value = ask(f"Choose {label} column number (blank = automatic)", "")
    if not value:
        return default
    try:
        index = int(value)
        if 1 <= index <= len(headers):
            return headers[index - 1]
    except ValueError:
        pass
    print("Invalid column; using automatic value.")
    return default


def run_tui(folder: Path, config: dict) -> None:
    folder = folder.resolve()
    style = load_style(str(config.get("style", {}).get("preset", "ieee_tap")))
    print("=" * 60)
    print("HFSS Paper Plotter")
    print("=" * 60)
    print(f"Folder: {folder}")
    selected = select_file(folder)
    if not selected:
        return
    dataset = read_hfss_csv(selected)
    detected = detect_kind(dataset)
    kind = ask("Plot type: s11 / gain / pattern / auto", detected)
    if kind == "auto":
        kind = detected

    args = Namespace(
        x_column=None,
        y_column=None,
        label=None,
        xlabel=None,
        ylabel=None,
        xlim=None,
        ylim=None,
        threshold=-10.0,
        no_threshold=False,
        fl=None,
        fc=None,
        fh=None,
        mark_min=False,
        mark_peak=False,
        phi_column=None,
        theta_column=None,
        gain_column=None,
        cuts=None,
        absolute=False,
    )
    args.x_column = choose_column(dataset.headers, "x-axis", None)
    if kind in {"s11", "gain"}:
        args.y_column = choose_column(dataset.headers, "y-axis", None)
    elif kind == "pattern":
        args.theta_column = choose_column(dataset.headers, "theta", None)
        args.phi_column = choose_column(dataset.headers, "phi", None)
        args.gain_column = choose_column(dataset.headers, "gain", None)

    args.label = ask("Legend label (blank = automatic)", "") or None
    args.xlabel = ask("X label (blank = automatic)", "") or None
    args.ylabel = ask("Y label (blank = automatic)", "") or None
    args.xlim = ask_range("X range")
    args.ylim = ask_range("Y range")
    output_dir = Path(ask("Output folder", str(folder / "figures")))

    if kind == "s11":
        args.threshold = ask_float("S11 threshold", -10.0)
        args.no_threshold = ask("Hide threshold? y/N", "N").lower().startswith("y")
        args.fl = ask_float("fL in GHz (blank = auto)")
        args.fc = ask_float("fC in GHz (blank = auto)")
        args.fh = ask_float("fH in GHz (blank = auto)")
        args.mark_min = ask("Mark minimum? y/N", "N").lower().startswith("y")
        outputs = plot_s11(dataset, output_dir, style, args)
    elif kind == "gain":
        args.mark_peak = ask("Mark gain peak? y/N", "N").lower().startswith("y")
        outputs = plot_gain(dataset, output_dir, style, args)
    elif kind == "pattern":
        args.absolute = ask("Use absolute gain? y/N", "N").lower().startswith("y")
        outputs = plot_pattern(dataset, output_dir, style, args)
    else:
        print(f"Unknown plot type: {kind}")
        return

    print("\nCreated:")
    for output in outputs:
        print(f"  {output}")
