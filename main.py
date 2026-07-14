#!/usr/bin/env python3
"""Command line entry point for HFSS Paper Plotter."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.hfss_paperplotter.audit import audit_csv, audit_dataset, format_audit
from src.hfss_paperplotter.config import load_project_config
from src.hfss_paperplotter.engineering_metrics import curves_from_dataset_for_metrics, metric_results_for_dataset
from src.hfss_paperplotter.export_artifacts import split_export_formats, write_export_artifacts
from src.hfss_paperplotter.project_settings import (
    apply_project_settings,
    project_metric_summary,
    project_settings_from_config,
)
from src.hfss_paperplotter.reporting import assemble_report
from src.hfss_paperplotter.reader import format_parse_report, read_hfss_csv


def add_common_plot_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", type=Path, help="HFSS CSV file or folder.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Output directory.")
    parser.add_argument("--style", default=None, help="Style preset name or style file.")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"), help="Config file.")
    parser.add_argument("--x-column", default=None, help="Manual x-axis column name.")
    parser.add_argument("--y-column", default=None, help="Manual y-axis column name.")
    parser.add_argument("--y-columns", nargs="+", default=None, help="Manual multiple y-axis columns.")
    parser.add_argument("--label", default=None, help="Legend label.")
    parser.add_argument("--labels", nargs="+", default=None, help="Legend labels for --y-columns.")
    parser.add_argument("--xlabel", default=None, help="Manual x-axis label.")
    parser.add_argument("--ylabel", default=None, help="Manual y-axis label.")
    parser.add_argument("--x-unit", choices=["auto", "ghz", "mhz", "hz"], default=None)
    parser.add_argument("--xlim", nargs=2, type=float, metavar=("MIN", "MAX"))
    parser.add_argument("--ylim", nargs=2, type=float, metavar=("MIN", "MAX"))
    parser.add_argument("--width", choices=["single", "double"], default=None)
    parser.add_argument("--formats", nargs="+", default=None, help="png pdf svg json txt md")
    parser.add_argument("--dpi", type=int, default=None)
    parser.add_argument("--no-grid", action="store_true")
    parser.add_argument("--no-markers", action="store_true")
    parser.add_argument("--legend-loc", default=None, help="Matplotlib legend location.")
    parser.add_argument(
        "--sample-every",
        type=int,
        default=None,
        metavar="N",
        help="Plot every Nth data point for the curve.",
    )
    parser.add_argument(
        "--sample-step",
        default=None,
        metavar="STEP",
        help="Resample the curve by frequency interval, such as 10MHz or 0.01GHz.",
    )
    parser.add_argument(
        "--marker-every",
        type=int,
        default=None,
        metavar="N",
        help="Show markers every Nth plotted point while keeping the curve denser.",
    )
    parser.add_argument("--smooth", action="store_true", help="Force smooth curves.")
    parser.add_argument("--no-smooth", action="store_true", help="Disable smooth curves.")


def add_overlay_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("inputs", nargs="+", type=Path, help="CSV files or folders to overlay.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Output directory.")
    parser.add_argument("--output-name", default="multi_csv_overlay", help="Output file base name.")
    parser.add_argument("--plot-type", choices=["auto", "s11", "vswr", "gain", "realizedgain", "ar", "efficiency", "phase", "pattern"], default="s11")
    parser.add_argument("--style", default=None, help="Style preset name or style file.")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"), help="Config file.")
    parser.add_argument("--xlabel", default=None, help="Manual x-axis label.")
    parser.add_argument("--ylabel", default=None, help="Manual y-axis label.")
    parser.add_argument("--x-unit", choices=["auto", "ghz", "mhz", "hz", "deg"], default="auto")
    parser.add_argument("--xlim", nargs=2, type=float, metavar=("MIN", "MAX"))
    parser.add_argument("--ylim", nargs=2, type=float, metavar=("MIN", "MAX"))
    parser.add_argument("--width", choices=["single", "double"], default=None)
    parser.add_argument("--formats", nargs="+", default=None, help="png pdf svg json txt md")
    parser.add_argument("--dpi", type=int, default=None)
    parser.add_argument("--no-grid", action="store_true")
    parser.add_argument("--no-markers", action="store_true")
    parser.add_argument("--legend-loc", default=None, help="Matplotlib legend location.")
    parser.add_argument("--threshold", type=float, default=None, help="Reference threshold for S11/VSWR overlays.")
    parser.add_argument("--no-threshold", action="store_true")
    parser.add_argument("--smooth", action="store_true", help="Force smooth curves.")
    parser.add_argument("--no-smooth", action="store_true", help="Disable smooth curves.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create TAP/AWPL-style paper figures from HFSS CSV exports."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    auto = subparsers.add_parser("auto", help="Auto-detect CSV types and plot all files.")
    add_common_plot_args(auto)

    overlay = subparsers.add_parser("overlay", help="Overlay curves from multiple CSV files without merging tables.")
    add_overlay_args(overlay)

    inspect = subparsers.add_parser("inspect", help="Inspect detected HFSS CSV columns.")
    inspect.add_argument("input", type=Path, help="HFSS CSV file.")
    inspect.add_argument("--band", nargs=2, type=float, metavar=("F_LOW_MHZ", "F_HIGH_MHZ"), help="Target band in MHz for coverage checks.")

    ui = subparsers.add_parser("ui", help="Open terminal UI.")
    ui.add_argument("input", nargs="?", type=Path, default=Path("."), help="CSV folder.")
    ui.add_argument("--config", type=Path, default=Path("config.yaml"), help="Config file.")

    s11 = subparsers.add_parser("s11", help="Manual S11 plot.")
    add_common_plot_args(s11)
    s11.add_argument("--threshold", type=float, default=None, help="S11 reference level.")
    s11.add_argument("--no-threshold", action="store_true")
    s11.add_argument("--fl", type=float, default=None, help="Lower band edge in GHz.")
    s11.add_argument("--fc", type=float, default=None, help="Center frequency in GHz.")
    s11.add_argument("--fh", type=float, default=None, help="Upper band edge in GHz.")
    s11.add_argument("--mark-min", action="store_true", help="Mark resonant minimum.")
    s11.add_argument(
        "--band-label-loc",
        choices=["auto", "upper-left", "upper-right", "lower-left", "lower-right"],
        default="auto",
        help="Location for S11 band annotation box.",
    )
    s11.add_argument("--no-band-label", action="store_true", help="Hide S11 band annotation box.")

    ar = subparsers.add_parser("ar", help="Manual axial-ratio plot.")
    add_common_plot_args(ar)
    ar.add_argument("--ar-threshold", type=float, default=None, help="Axial-ratio threshold in dB.")
    ar.add_argument("--threshold", type=float, default=None, help="Alias for --ar-threshold.")
    ar.add_argument("--no-threshold", action="store_true")
    ar.add_argument("--fl", type=float, default=None, help="Lower AR band edge in GHz.")
    ar.add_argument("--fh", type=float, default=None, help="Upper AR band edge in GHz.")
    ar.add_argument(
        "--band-label-loc",
        choices=["auto", "upper-left", "upper-right", "lower-left", "lower-right"],
        default="auto",
        help="Location for AR bandwidth annotation box.",
    )
    ar.add_argument("--no-band-label", action="store_true", help="Hide AR bandwidth annotation box.")

    vswr = subparsers.add_parser("vswr", help="Manual VSWR plot.")
    add_common_plot_args(vswr)
    vswr.add_argument("--vswr-threshold", type=float, default=None, help="VSWR threshold.")
    vswr.add_argument("--threshold", type=float, default=None, help="Alias for --vswr-threshold.")
    vswr.add_argument("--no-threshold", action="store_true")
    vswr.add_argument("--fl", type=float, default=None, help="Lower VSWR band edge in GHz.")
    vswr.add_argument("--fh", type=float, default=None, help="Upper VSWR band edge in GHz.")
    vswr.add_argument(
        "--band-label-loc",
        choices=["auto", "upper-left", "upper-right", "lower-left", "lower-right"],
        default="auto",
        help="Location for VSWR bandwidth annotation box.",
    )
    vswr.add_argument("--no-band-label", action="store_true", help="Hide VSWR bandwidth annotation box.")

    eff = subparsers.add_parser("eff", help="Manual efficiency-vs-frequency plot.")
    add_common_plot_args(eff)
    eff.add_argument("--mark-peak", action="store_true", help="Mark peak efficiency.")

    hpbw = subparsers.add_parser("hpbw", help="Manual half-power beamwidth plot.")
    add_common_plot_args(hpbw)

    smith = subparsers.add_parser("smith", help="Manual Smith chart from real/imag S-parameter columns.")
    add_common_plot_args(smith)
    smith.add_argument("--real-column", default=None, help="Real part column, e.g. re(S(1,1)).")
    smith.add_argument("--imag-column", default=None, help="Imaginary part column, e.g. im(S(1,1)).")

    gain = subparsers.add_parser("gain", help="Manual gain-vs-frequency plot.")
    add_common_plot_args(gain)
    gain.add_argument("--mark-peak", action="store_true", help="Mark peak gain.")

    xy = subparsers.add_parser("xy", help="Manual generic x-y plot, including efficiency curves.")
    add_common_plot_args(xy)

    pattern = subparsers.add_parser("pattern", help="Manual radiation pattern plot.")
    add_common_plot_args(pattern)
    pattern.add_argument("--phi-column", default=None)
    pattern.add_argument("--theta-column", default=None)
    pattern.add_argument("--gain-column", default=None)
    pattern.add_argument("--gain-columns", nargs="+", default=None)
    pattern.add_argument("--absolute", action="store_true", help="Use absolute gain values.")
    pattern.add_argument("--cuts", nargs="+", type=float, default=None, help="Phi cuts to plot.")
    return parser


def style_from_args(args: argparse.Namespace, config: dict) -> dict:
    from src.hfss_paperplotter.style import load_style

    style_name = args.style or config.get("style", {}).get("preset", "ieee_tap")
    style = load_style(style_name)
    if getattr(args, "dpi", None):
        style["figure"]["dpi"] = args.dpi
    if getattr(args, "width", None):
        style["figure"]["width"] = args.width
    configured_formats = getattr(args, "formats", None) or config.get("export", {}).get("formats")
    if configured_formats:
        image_formats, requested_formats = split_export_formats(configured_formats)
        style["export"]["formats"] = image_formats
        style["export"]["requested_formats"] = requested_formats
    if getattr(args, "no_grid", False):
        style["axis"]["grid"] = False
    if getattr(args, "smooth", False):
        style["line"]["smooth"] = True
    if getattr(args, "no_smooth", False):
        style["line"]["smooth"] = False
    return style


def output_dir_from_args(args: argparse.Namespace, config: dict) -> Path:
    if getattr(args, "output_dir", None):
        return args.output_dir
    configured = config.get("export", {}).get("output_dir")
    if configured:
        configured_path = Path(str(configured))
        if configured_path.is_absolute():
            return configured_path
        inputs = getattr(args, "inputs", None)
        input_path = inputs[0] if inputs else getattr(args, "input", Path("."))
        return (input_path if input_path.is_dir() else input_path.parent) / configured_path
    inputs = getattr(args, "inputs", None)
    input_path = inputs[0] if inputs else getattr(args, "input", Path("."))
    return (input_path if input_path.is_dir() else input_path.parent) / "figures"


def target_band_mhz_from_args(args: argparse.Namespace) -> tuple[float, float] | None:
    fl = getattr(args, "fl", None)
    fh = getattr(args, "fh", None)
    if fl is None or fh is None:
        return None
    return float(fl) * 1000.0, float(fh) * 1000.0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "inspect":
        band = tuple(args.band) if args.band else None
        dataset = read_hfss_csv(args.input)
        if dataset.parse_report:
            print(format_parse_report(dataset.parse_report))
            print("")
        print(format_audit(audit_csv(args.input, band)))
        return

    if args.command == "ui":
        from src.hfss_paperplotter.tui import run_tui

        config = load_project_config(args.config)
        run_tui(args.input, config)
        return

    config = load_project_config(args.config)
    project_settings = project_settings_from_config(config)
    apply_project_settings(args, project_settings)
    style = style_from_args(args, config)
    if "requested_formats" not in style.get("export", {}):
        image_formats, requested_formats = split_export_formats(style.get("export", {}).get("formats"))
        style["export"]["formats"] = image_formats
        style["export"]["requested_formats"] = requested_formats
    output_dir = output_dir_from_args(args, config)

    if args.command == "auto":
        from src.hfss_paperplotter.batch import run_auto

        run_auto(args.input, output_dir, style, args)
        return

    if args.command == "overlay":
        from src.hfss_paperplotter.curve_manager import overlay_csv_files

        outputs = overlay_csv_files(args.inputs, output_dir, style, args)
        for output in outputs:
            print(f"Created {output}")
        return

    from src.hfss_paperplotter.plotting import (
        plot_ar,
        plot_efficiency,
        plot_gain,
        plot_hpbw,
        plot_pattern,
        plot_s11,
        plot_smith,
        plot_vswr,
        plot_xy,
    )

    dataset = read_hfss_csv(args.input)
    audit_report = audit_dataset(dataset, target_band_mhz_from_args(args))
    project_text = project_metric_summary(dataset, args.command, project_settings)
    metric_curves = curves_from_dataset_for_metrics(dataset, args.command)
    metric_results = metric_results_for_dataset(dataset, args.command, project_settings)
    report_text, messages = assemble_report(audit_report, project_text, metric_results)
    print(report_text)
    print("")
    if args.command == "s11":
        outputs = plot_s11(dataset, output_dir, style, args)
    elif args.command == "ar":
        outputs = plot_ar(dataset, output_dir, style, args)
    elif args.command == "vswr":
        outputs = plot_vswr(dataset, output_dir, style, args)
    elif args.command == "eff":
        outputs = plot_efficiency(dataset, output_dir, style, args)
    elif args.command == "hpbw":
        outputs = plot_hpbw(dataset, output_dir, style, args)
    elif args.command == "smith":
        outputs = plot_smith(dataset, output_dir, style, args)
    elif args.command == "gain":
        outputs = plot_gain(dataset, output_dir, style, args)
    elif args.command == "pattern":
        outputs = plot_pattern(dataset, output_dir, style, args)
    elif args.command == "xy":
        outputs = plot_xy(dataset, output_dir, style, args)
    else:
        outputs = []
    if outputs:
        outputs.extend(
            write_export_artifacts(
                output_dir,
                f"{dataset.path.stem}_{args.command}",
                dataset,
                args.command,
                args,
                style,
                style["export"].get("requested_formats", style["export"].get("formats", [])),
                project_settings,
                report_text,
                messages=messages,
                curves=metric_curves,
            )
        )
    for output in outputs:
        print(f"Created {output}")


if __name__ == "__main__":
    main()
