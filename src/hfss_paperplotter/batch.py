"""Batch and automatic plotting."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from .plotting import (
    plot_ar,
    plot_efficiency,
    plot_gain,
    plot_hpbw,
    plot_pattern,
    plot_s11,
    plot_smith,
    plot_vswr,
)
from .reader import csv_files, detect_kind, read_hfss_csv


def run_auto(input_path: Path, output_dir: Path, style: dict, args: Namespace) -> None:
    files = csv_files(input_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in files:
        try:
            dataset = read_hfss_csv(path)
            kind = detect_kind(dataset)
            if kind == "s11":
                outputs = plot_s11(dataset, output_dir, style, args)
            elif kind == "ar":
                outputs = plot_ar(dataset, output_dir, style, args)
            elif kind == "vswr":
                outputs = plot_vswr(dataset, output_dir, style, args)
            elif kind == "eff":
                outputs = plot_efficiency(dataset, output_dir, style, args)
            elif kind == "hpbw":
                outputs = plot_hpbw(dataset, output_dir, style, args)
            elif kind == "smith":
                outputs = plot_smith(dataset, output_dir, style, args)
            elif kind == "gain":
                outputs = plot_gain(dataset, output_dir, style, args)
            elif kind == "pattern":
                outputs = plot_pattern(dataset, output_dir, style, args)
            else:
                print(f"Skipped {path.name}: unknown data type")
                continue
            print(f"{path.name}: {kind}")
            for output in outputs:
                print(f"  Created {output}")
        except Exception as error:  # Keep batch mode moving across mixed HFSS files.
            print(f"Skipped {path.name}: {error}")
