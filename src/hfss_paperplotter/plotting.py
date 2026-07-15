"""Plotting routines for HFSS paper figures."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator
import numpy as np

from .metrics import s11_band
from .pattern_analysis import compact_pattern_label, normalized_pattern_label, polarization_role, recognize_pattern
from .reader import (
    HfssDataset,
    axial_ratio_column,
    convert_frequency,
    efficiency_column,
    frequency_column,
    gain_column,
    hpbw_column,
    pattern_value_columns,
    phi_column,
    s11_column,
    smith_imag_column,
    smith_real_column,
    theta_column,
    vswr_column,
)
from .s11_import import s11_curves_from_dataset
from .style import apply_style, figure_size


def ensure_output(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)


def save_figure(fig: plt.Figure, output_base: Path, style: dict) -> list[Path]:
    ensure_output(output_base.parent)
    outputs: list[Path] = []
    for ext in style["export"]["formats"]:
        suffix = "." + str(ext).lower().lstrip(".")
        target = output_base.with_suffix(suffix)
        fig.savefig(target, dpi=style["figure"]["dpi"], bbox_inches="tight")
        outputs.append(target)
    plt.close(fig)
    return outputs


def curve_style(style: dict, index: int, default_color: str) -> dict:
    colors = style["colors"].get("cycle") or [default_color]
    markers = style.get("markers", {}).get("cycle") or ["o"]
    use_markers = bool(style["line"].get("markers", False))
    return {
        "color": colors[index % len(colors)],
        "marker": markers[index % len(markers)] if use_markers else None,
        "markersize": style["line"]["marker_size"],
        "linewidth": style["line"]["width"],
    }


def smooth_xy(x: np.ndarray, y: np.ndarray, samples_per_segment: int = 24) -> tuple[np.ndarray, np.ndarray]:
    """Catmull-Rom smoothing through the plotted data points."""
    finite = np.isfinite(x) & np.isfinite(y)
    x = x[finite]
    y = y[finite]
    if len(x) < 4:
        return x, y
    xs: list[float] = []
    ys: list[float] = []
    for index in range(len(x) - 1):
        x0 = x[max(index - 1, 0)]
        x1 = x[index]
        x2 = x[index + 1]
        x3 = x[min(index + 2, len(x) - 1)]
        y0 = y[max(index - 1, 0)]
        y1 = y[index]
        y2 = y[index + 1]
        y3 = y[min(index + 2, len(y) - 1)]
        for step in range(samples_per_segment):
            t = step / samples_per_segment
            t2 = t * t
            t3 = t2 * t
            xs.append(0.5 * ((2 * x1) + (-x0 + x2) * t + (2 * x0 - 5 * x1 + 4 * x2 - x3) * t2 + (-x0 + 3 * x1 - 3 * x2 + x3) * t3))
            ys.append(0.5 * ((2 * y1) + (-y0 + y2) * t + (2 * y0 - 5 * y1 + 4 * y2 - y3) * t2 + (-y0 + 3 * y1 - 3 * y2 + y3) * t3))
    xs.append(float(x[-1]))
    ys.append(float(y[-1]))
    return np.asarray(xs), np.asarray(ys)


def parse_step_to_axis_units(step: str, axis_unit_label: str) -> float:
    text = step.strip().lower().replace(" ", "")
    if not text:
        raise ValueError("Sample step cannot be empty.")
    units = {
        "ghz": 1.0,
        "mhz": 1e-3,
        "khz": 1e-6,
        "hz": 1e-9,
    }
    unit = ""
    for candidate in sorted(units, key=len, reverse=True):
        if text.endswith(candidate):
            unit = candidate
            text = text[: -len(candidate)]
            break
    value = float(text)
    axis_unit = axis_unit_label.lower()
    axis_scale_from_ghz = {"ghz": 1.0, "mhz": 1000.0, "hz": 1e9}.get(axis_unit, 1.0)
    if unit:
        return value * units[unit] * axis_scale_from_ghz
    return value


def sample_every(x: np.ndarray, y: np.ndarray, every: int | None) -> tuple[np.ndarray, np.ndarray]:
    if every is None or every <= 1 or len(x) <= 2:
        return x, y
    indices = list(range(0, len(x), every))
    if indices[-1] != len(x) - 1:
        indices.append(len(x) - 1)
    return x[indices], y[indices]


def resample_by_step(x: np.ndarray, y: np.ndarray, step: float | None) -> tuple[np.ndarray, np.ndarray]:
    if step is None or step <= 0 or len(x) <= 2:
        return x, y
    finite = np.isfinite(x) & np.isfinite(y)
    x = x[finite]
    y = y[finite]
    if len(x) <= 2:
        return x, y
    start = float(np.nanmin(x))
    stop = float(np.nanmax(x))
    new_x = np.arange(start, stop + step * 0.5, step)
    if new_x[-1] > stop:
        new_x[-1] = stop
    elif new_x[-1] < stop:
        new_x = np.append(new_x, stop)
    new_y = np.interp(new_x, x, y)
    return new_x, new_y


def prepare_curve_data(
    x: np.ndarray,
    y: np.ndarray,
    args: Namespace,
    unit_label: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    curve_x = x
    curve_y = y
    step_text = getattr(args, "sample_step", None)
    if step_text:
        curve_x, curve_y = resample_by_step(
            curve_x,
            curve_y,
            parse_step_to_axis_units(step_text, unit_label),
        )
    curve_x, curve_y = sample_every(curve_x, curve_y, getattr(args, "sample_every", None))
    marker_x, marker_y = sample_every(curve_x, curve_y, getattr(args, "marker_every", None))
    return curve_x, curve_y, marker_x, marker_y


def plot_curve(
    ax: plt.Axes,
    x: np.ndarray,
    y: np.ndarray,
    label: str,
    options: dict,
    style: dict,
    no_markers: bool = False,
    marker_x: np.ndarray | None = None,
    marker_y: np.ndarray | None = None,
) -> None:
    marker = None if no_markers else options.get("marker")
    marker_x = x if marker_x is None else marker_x
    marker_y = y if marker_y is None else marker_y
    if style["line"].get("smooth", False) and len(x) >= 4:
        xs, ys = smooth_xy(x, y)
        ax.plot(
            [],
            [],
            color=options["color"],
            linewidth=options["linewidth"],
            linestyle=options.get("linestyle", "-"),
            alpha=options.get("alpha", 1.0),
            marker=marker,
            markersize=options["markersize"],
            label=label,
        )
        ax.plot(xs, ys, color=options["color"], linewidth=options["linewidth"], linestyle=options.get("linestyle", "-"), alpha=options.get("alpha", 1.0), label="_nolegend_")
        if marker:
            ax.plot(marker_x, marker_y, linestyle="none", color=options["color"], marker=marker, markersize=options["markersize"], alpha=options.get("alpha", 1.0))
        return
    ax.plot(
        x,
        y,
        color=options["color"],
        linewidth=options["linewidth"],
        linestyle=options.get("linestyle", "-"),
        alpha=options.get("alpha", 1.0),
        marker=None,
        label=label,
    )
    if marker:
        ax.plot(
            marker_x,
            marker_y,
            linestyle="none",
            color=options["color"],
            marker=marker,
            markersize=options["markersize"],
            alpha=options.get("alpha", 1.0),
            label="_nolegend_",
        )


def grid(ax: plt.Axes, style: dict, args: Namespace | None = None) -> None:
    if args is not None and getattr(args, "grid_enabled", None) is False:
        return
    if style["axis"].get("grid", True):
        ax.grid(True, which="major", linestyle="-", linewidth=0.4, alpha=style["axis"]["grid_alpha"])
        ax.grid(True, which="minor", linestyle=":", linewidth=0.3, alpha=style["axis"]["grid_alpha"] * 0.7)
    ax.minorticks_on()


def manual_or_detect_columns(dataset: HfssDataset, args: Namespace, y_detector) -> tuple[str, str]:
    x_col = getattr(args, "x_column", None) or frequency_column(dataset.headers)
    y_col = getattr(args, "y_column", None) or y_detector(dataset.headers)
    if not x_col or not y_col:
        raise ValueError("Could not detect x/y columns. Use --x-column and --y-column.")
    return x_col, y_col


def y_columns(dataset: HfssDataset, args: Namespace, y_detector) -> list[str]:
    columns = getattr(args, "y_columns", None)
    if columns:
        missing = [column for column in columns if column not in dataset.headers]
        if missing:
            raise ValueError(f"Y columns not found: {', '.join(missing)}")
        return columns
    y_col = getattr(args, "y_column", None) or y_detector(dataset.headers)
    if not y_col:
        raise ValueError("Could not detect y column. Use --y-column or --y-columns.")
    return [y_col]


def curve_labels(args: Namespace, columns: list[str], default: str) -> list[str]:
    labels = getattr(args, "labels", None)
    if labels:
        return labels + columns[len(labels) :]
    label = getattr(args, "label", None)
    if label and len(columns) == 1:
        return [label]
    if len(columns) == 1:
        return [default]
    return columns


def frequency_values(dataset: HfssDataset, args: Namespace, style: dict) -> tuple[np.ndarray, str, str]:
    x_col = getattr(args, "x_column", None) or frequency_column(dataset.headers)
    if not x_col:
        raise ValueError("Could not detect frequency column. Use --x-column.")
    unit = getattr(args, "x_unit", None) or style.get("frequency", {}).get("unit", "ghz")
    x, unit_label = convert_frequency(dataset.column(x_col), x_col, unit)
    return x, unit_label, x_col


def ghz_to_axis(value: float | None, unit_label: str) -> float | None:
    if value is None:
        return None
    unit = unit_label.lower()
    if unit == "mhz":
        return value * 1000.0
    if unit == "hz":
        return value * 1e9
    return value


def draw_frequency_band(ax: plt.Axes, args: Namespace, unit_label: str, color: str, alpha: float = 0.06) -> tuple[float | None, float | None]:
    fl = ghz_to_axis(getattr(args, "fl", None), unit_label)
    fh = ghz_to_axis(getattr(args, "fh", None), unit_label)
    if fl is not None and fh is not None:
        ax.axvspan(fl, fh, color=color, alpha=alpha, linewidth=0)
        ax.axvline(fl, color="#666666", linestyle=":", linewidth=0.8)
        ax.axvline(fh, color="#666666", linestyle=":", linewidth=0.8)
    return fl, fh


def frequency_text(value: float, unit_label: str) -> str:
    return f"{value:.2f} {unit_label}"


def bandwidth_text(width: float, unit_label: str) -> str:
    if unit_label.lower() == "ghz":
        return f"{width * 1000.0:.1f} MHz"
    if unit_label.lower() == "mhz":
        return f"{width:.1f} MHz"
    return f"{width:.3g} {unit_label}"


def below_threshold_band(x: np.ndarray, y: np.ndarray, threshold: float) -> dict | None:
    finite = np.isfinite(x) & np.isfinite(y)
    x = x[finite]
    y = y[finite]
    if len(x) < 2:
        return None

    candidates: list[tuple[float, float]] = []
    in_band = y[0] <= threshold
    start = float(x[0]) if in_band else None
    for index in range(len(x) - 1):
        y1 = y[index]
        y2 = y[index + 1]
        crosses = (y1 - threshold) * (y2 - threshold) < 0
        if crosses:
            t = (threshold - y1) / (y2 - y1)
            crossing = float(x[index] + t * (x[index + 1] - x[index]))
            if not in_band:
                start = crossing
                in_band = True
            else:
                candidates.append((float(start), crossing))
                start = None
                in_band = False
    if in_band and start is not None:
        candidates.append((float(start), float(x[-1])))
    if not candidates:
        return None
    fl, fh = max(candidates, key=lambda item: item[1] - item[0])
    return {"fl": fl, "fh": fh, "fc": (fl + fh) / 2.0, "bw": fh - fl}


def axes_corner(location: str) -> tuple[float, float, str, str]:
    corners = {
        "upper-left": (0.04, 0.96, "left", "top"),
        "upper-right": (0.96, 0.96, "right", "top"),
        "lower-left": (0.04, 0.06, "left", "bottom"),
        "lower-right": (0.96, 0.06, "right", "bottom"),
    }
    return corners.get(location, corners["upper-left"])


def auto_band_label_location(x: np.ndarray, y: np.ndarray, ax: plt.Axes) -> str:
    """Pick the least crowded corner for an annotation box."""
    points = np.column_stack([x[np.isfinite(x) & np.isfinite(y)], y[np.isfinite(x) & np.isfinite(y)]])
    if len(points) == 0:
        return "upper-left"

    display_points = ax.transData.transform(points)
    axes_points = ax.transAxes.inverted().transform(display_points)
    candidates = {
        "upper-left": (0.00, 0.46, 0.42, 1.00),
        "upper-right": (0.58, 0.46, 1.00, 1.00),
        "lower-left": (0.00, 0.00, 0.42, 0.54),
        "lower-right": (0.58, 0.00, 1.00, 0.54),
    }
    scores: dict[str, int] = {}
    for name, (xmin, ymin, xmax, ymax) in candidates.items():
        inside = (
            (axes_points[:, 0] >= xmin)
            & (axes_points[:, 0] <= xmax)
            & (axes_points[:, 1] >= ymin)
            & (axes_points[:, 1] <= ymax)
        )
        scores[name] = int(np.count_nonzero(inside))
    return min(scores, key=scores.get)


def apply_limits_labels(ax: plt.Axes, args: Namespace, xlabel: str, ylabel: str) -> None:
    ax.set_xlabel(getattr(args, "xlabel", None) or xlabel)
    ax.set_ylabel(getattr(args, "ylabel", None) or ylabel)
    if getattr(args, "xlim", None):
        ax.set_xlim(args.xlim)
    if getattr(args, "ylim", None):
        ax.set_ylim(args.ylim)
    for attr, setter in [
        ("xtick_major", ax.xaxis.set_major_locator),
        ("ytick_major", ax.yaxis.set_major_locator),
        ("xtick_minor", ax.xaxis.set_minor_locator),
        ("ytick_minor", ax.yaxis.set_minor_locator),
    ]:
        value = getattr(args, attr, None)
        if value not in (None, ""):
            try:
                step = float(value)
            except (TypeError, ValueError):
                continue
            if step > 0:
                setter(MultipleLocator(step))
    for item in getattr(args, "annotations", None) or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        try:
            x = float(item.get("x", 0.05))
            y = float(item.get("y", 0.95))
        except (TypeError, ValueError):
            x, y = 0.05, 0.95
        ax.text(
            x,
            y,
            text,
            transform=ax.transAxes,
            ha=str(item.get("ha") or "left"),
            va=str(item.get("va") or "top"),
            fontsize=float(item.get("fontsize") or 8.0),
            color=str(item.get("color") or "#111111"),
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.72, "pad": 2.0},
        )


def plot_s11(dataset: HfssDataset, output_dir: Path, style: dict, args: Namespace) -> list[Path]:
    apply_style(style)
    manual_y_columns = bool(getattr(args, "y_column", None) or getattr(args, "y_columns", None))
    curve_items: list[tuple[np.ndarray, np.ndarray, str]] = []
    unit_label = ""

    if not manual_y_columns:
        s11_result = s11_curves_from_dataset(dataset, x_unit=getattr(args, "x_unit", None))
        for curve in s11_result.curves:
            x_data = np.asarray(curve.x_data, dtype=float)
            y_data = np.asarray(curve.y_data, dtype=float)
            order = np.argsort(x_data)
            curve_items.append((x_data[order], y_data[order], curve.label or r"$S_{11}$"))
            unit_label = curve.x_unit

    if not curve_items:
        x, unit_label, _ = frequency_values(dataset, args, style)
        y_cols = y_columns(dataset, args, s11_column)
        labels = curve_labels(args, y_cols, r"$S_{11}$")
        order = np.argsort(x)
        x = x[order]
        for index, y_col in enumerate(y_cols):
            y = dataset.column(y_col)[order]
            curve_items.append((x, y, labels[index]))

    fig, ax = plt.subplots(figsize=figure_size(style), constrained_layout=True)
    color = style["colors"]["s11"]
    primary_y = None
    primary_x = None
    for index, (x_data, y, label) in enumerate(curve_items):
        if primary_y is None:
            primary_y = y
            primary_x = x_data
        options = curve_style(style, index, color)
        curve_x, curve_y, marker_x, marker_y = prepare_curve_data(x_data, y, args, unit_label)
        plot_curve(
            ax,
            curve_x,
            curve_y,
            label,
            options,
            style,
            getattr(args, "no_markers", False),
            marker_x,
            marker_y,
        )
    if primary_y is None or primary_x is None:
        raise ValueError("No S11 curve data was found.")

    threshold = getattr(args, "threshold", None)
    if threshold is None:
        threshold = -10.0
    if not getattr(args, "no_threshold", False):
        ax.axhline(threshold, color=style["colors"]["gray"], linestyle="--", linewidth=0.9)
        ax.text(0.985, threshold + 0.3, f"{threshold:g} dB", transform=ax.get_yaxis_transform(), ha="right", va="bottom", color=style["colors"]["gray"])

    fl = ghz_to_axis(getattr(args, "fl", None), unit_label)
    fc = ghz_to_axis(getattr(args, "fc", None), unit_label)
    fh = ghz_to_axis(getattr(args, "fh", None), unit_label)
    metrics = s11_band(primary_x, primary_y, threshold)
    if fl is None and metrics and "fl" in metrics:
        fl = metrics["fl"]
    if fc is None and metrics and "fc" in metrics:
        fc = metrics["fc"]
    if fh is None and metrics and "fh" in metrics:
        fh = metrics["fh"]

    notes: list[str] = []
    if fl is not None and fh is not None:
        ax.axvspan(fl, fh, color=color, alpha=0.08, linewidth=0)
        ax.axvline(fl, color=style["colors"]["gray"], linestyle=":", linewidth=0.8)
        ax.axvline(fh, color=style["colors"]["gray"], linestyle=":", linewidth=0.8)
        notes.extend(
            [
                rf"$f_L$ = {frequency_text(fl, unit_label)}",
                rf"$f_H$ = {frequency_text(fh, unit_label)}",
                f"BW = {bandwidth_text(fh - fl, unit_label)}",
            ]
        )
    if fc is not None:
        ax.axvline(fc, color=style["colors"]["black"], linestyle=":", linewidth=0.9)
        notes.insert(1 if notes else 0, rf"$f_c$ = {frequency_text(fc, unit_label)}")
    if notes and not getattr(args, "no_band_label", False):
        label_location = getattr(args, "band_label_loc", "auto")
        if label_location == "auto":
            label_location = auto_band_label_location(primary_x, primary_y, ax)
        text_x, text_y, ha, va = axes_corner(label_location)
        ax.text(
            text_x,
            text_y,
            "\n".join(notes),
            transform=ax.transAxes,
            ha=ha,
            va=va,
            zorder=30,
            bbox={
                "facecolor": "white",
                "edgecolor": "none",
                "alpha": 1.0,
                "pad": 3.0,
            },
        )

    if getattr(args, "mark_min", False):
        index = int(np.nanargmin(primary_y))
        ax.plot(primary_x[index], primary_y[index], marker="o", color=color, markersize=style["line"]["marker_size"])
        ax.annotate(
            f"{primary_x[index]:.3f} {unit_label}\n{primary_y[index]:.1f} dB",
            (primary_x[index], primary_y[index]),
            xytext=(6, 8),
            textcoords="offset points",
        )

    apply_limits_labels(ax, args, f"Frequency ({unit_label})", r"$S_{11}$ (dB)")
    if not getattr(args, "ylim", None):
        ax.set_ylim(min(-30.0, float(np.nanmin(primary_y)) - 2.0), 0.0)
    grid(ax, style)
    ax.legend(loc=getattr(args, "legend_loc", None) or style.get("legend", {}).get("loc", "best"))
    return save_figure(fig, output_dir / f"{dataset.path.stem}_S11", style)


def plot_gain(dataset: HfssDataset, output_dir: Path, style: dict, args: Namespace) -> list[Path]:
    apply_style(style)
    x, unit_label, _ = frequency_values(dataset, args, style)
    y_cols = y_columns(dataset, args, gain_column)
    labels = curve_labels(args, y_cols, "Realized Gain")
    order = np.argsort(x)
    x = x[order]

    fig, ax = plt.subplots(figsize=figure_size(style), constrained_layout=True)
    color = style["colors"]["gain"]
    primary_y = None
    for index, y_col in enumerate(y_cols):
        y = dataset.column(y_col)[order]
        if primary_y is None:
            primary_y = y
        options = curve_style(style, index, color)
        curve_x, curve_y, marker_x, marker_y = prepare_curve_data(x, y, args, unit_label)
        plot_curve(
            ax,
            curve_x,
            curve_y,
            labels[index],
            options,
            style,
            getattr(args, "no_markers", False),
            marker_x,
            marker_y,
        )
    if primary_y is None:
        raise ValueError("No gain curve data was found.")
    if getattr(args, "mark_peak", False):
        index = int(np.nanargmax(primary_y))
        ax.plot(x[index], primary_y[index], marker="o", color=color, markersize=style["line"]["marker_size"])
        ax.annotate(f"{x[index]:.3f} {unit_label}\n{primary_y[index]:.2f} dB", (x[index], primary_y[index]), xytext=(6, 8), textcoords="offset points")
    draw_frequency_band(ax, args, unit_label, color)
    apply_limits_labels(ax, args, f"Frequency ({unit_label})", "Realized Gain (dB)")
    grid(ax, style)
    ax.legend(loc=getattr(args, "legend_loc", None) or style.get("legend", {}).get("loc", "best"))
    return save_figure(fig, output_dir / f"{dataset.path.stem}_Gain", style)


def plot_frequency_response(
    dataset: HfssDataset,
    output_dir: Path,
    style: dict,
    args: Namespace,
    detector,
    default_label: str,
    ylabel: str,
    output_suffix: str,
    color_key: str = "gain",
    mark_peak: bool = False,
) -> list[Path]:
    apply_style(style)
    x, unit_label, _ = frequency_values(dataset, args, style)
    y_cols = y_columns(dataset, args, detector)
    labels = curve_labels(args, y_cols, default_label)
    order = np.argsort(x)
    x = x[order]

    fig, ax = plt.subplots(figsize=figure_size(style), constrained_layout=True)
    primary_y = None
    color = style["colors"].get(color_key, style["colors"]["gain"])
    for index, y_col in enumerate(y_cols):
        y = dataset.column(y_col)[order]
        if primary_y is None:
            primary_y = y
        options = curve_style(style, index, color)
        curve_x, curve_y, marker_x, marker_y = prepare_curve_data(x, y, args, unit_label)
        plot_curve(
            ax,
            curve_x,
            curve_y,
            labels[index],
            options,
            style,
            getattr(args, "no_markers", False),
            marker_x,
            marker_y,
        )
    if primary_y is None:
        raise ValueError(f"No {default_label} data was found.")
    if mark_peak or getattr(args, "mark_peak", False):
        index = int(np.nanargmax(primary_y))
        ax.plot(x[index], primary_y[index], marker="o", color=color, markersize=style["line"]["marker_size"])
        ax.annotate(
            f"{x[index]:.3f} {unit_label}\n{primary_y[index]:.2f}",
            (x[index], primary_y[index]),
            xytext=(6, 8),
            textcoords="offset points",
        )
    draw_frequency_band(ax, args, unit_label, color)
    apply_limits_labels(ax, args, f"Frequency ({unit_label})", ylabel)
    grid(ax, style)
    ax.legend(loc=getattr(args, "legend_loc", None) or style.get("legend", {}).get("loc", "best"))
    return save_figure(fig, output_dir / f"{dataset.path.stem}_{output_suffix}", style)


def plot_efficiency(dataset: HfssDataset, output_dir: Path, style: dict, args: Namespace) -> list[Path]:
    return plot_frequency_response(
        dataset,
        output_dir,
        style,
        args,
        efficiency_column,
        "Efficiency",
        "Efficiency (%)",
        "Efficiency",
        "gain",
    )


def plot_hpbw(dataset: HfssDataset, output_dir: Path, style: dict, args: Namespace) -> list[Path]:
    return plot_frequency_response(
        dataset,
        output_dir,
        style,
        args,
        hpbw_column,
        "HPBW",
        "HPBW (deg)",
        "HPBW",
        "gain",
    )


def plot_threshold_response(
    dataset: HfssDataset,
    output_dir: Path,
    style: dict,
    args: Namespace,
    detector,
    default_label: str,
    ylabel: str,
    output_suffix: str,
    threshold: float,
    threshold_label: str,
) -> list[Path]:
    apply_style(style)
    x, unit_label, _ = frequency_values(dataset, args, style)
    y_cols = y_columns(dataset, args, detector)
    labels = curve_labels(args, y_cols, default_label)
    order = np.argsort(x)
    x = x[order]

    fig, ax = plt.subplots(figsize=figure_size(style), constrained_layout=True)
    primary_y = None
    for index, y_col in enumerate(y_cols):
        y = dataset.column(y_col)[order]
        if primary_y is None:
            primary_y = y
        options = curve_style(style, index, style["colors"]["gain"])
        curve_x, curve_y, marker_x, marker_y = prepare_curve_data(x, y, args, unit_label)
        plot_curve(
            ax,
            curve_x,
            curve_y,
            labels[index],
            options,
            style,
            getattr(args, "no_markers", False),
            marker_x,
            marker_y,
        )
    if primary_y is None:
        raise ValueError(f"No {default_label} curve data was found.")

    if not getattr(args, "no_threshold", False):
        ax.axhline(threshold, color=style["colors"]["gray"], linestyle="--", linewidth=0.9)
        ax.text(
            0.985,
            threshold + 0.05,
            threshold_label,
            transform=ax.get_yaxis_transform(),
            ha="right",
            va="bottom",
            color=style["colors"]["gray"],
            zorder=30,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.9, "pad": 1.5},
        )

    fl = ghz_to_axis(getattr(args, "fl", None), unit_label)
    fh = ghz_to_axis(getattr(args, "fh", None), unit_label)
    band = below_threshold_band(x, primary_y, threshold)
    if fl is None and band:
        fl = band["fl"]
    if fh is None and band:
        fh = band["fh"]

    notes: list[str] = []
    if fl is not None and fh is not None:
        ax.axvspan(fl, fh, color=style["colors"]["gain"], alpha=0.08, linewidth=0)
        ax.axvline(fl, color=style["colors"]["gray"], linestyle=":", linewidth=0.8)
        ax.axvline(fh, color=style["colors"]["gray"], linestyle=":", linewidth=0.8)
        notes.extend(
            [
                rf"$f_L$ = {frequency_text(fl, unit_label)}",
                rf"$f_H$ = {frequency_text(fh, unit_label)}",
                f"BW = {bandwidth_text(fh - fl, unit_label)}",
            ]
        )
    if notes and not getattr(args, "no_band_label", False):
        label_location = getattr(args, "band_label_loc", "auto")
        if label_location == "auto":
            label_location = auto_band_label_location(x, primary_y, ax)
        text_x, text_y, ha, va = axes_corner(label_location)
        ax.text(
            text_x,
            text_y,
            "\n".join(notes),
            transform=ax.transAxes,
            ha=ha,
            va=va,
            zorder=30,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 1.0, "pad": 3.0},
        )

    apply_limits_labels(ax, args, f"Frequency ({unit_label})", ylabel)
    grid(ax, style)
    ax.legend(loc=getattr(args, "legend_loc", None) or style.get("legend", {}).get("loc", "best"))
    return save_figure(fig, output_dir / f"{dataset.path.stem}_{output_suffix}", style)


def plot_ar(dataset: HfssDataset, output_dir: Path, style: dict, args: Namespace) -> list[Path]:
    threshold = getattr(args, "threshold", None)
    if threshold is None:
        threshold = getattr(args, "ar_threshold", 3.0)
    return plot_threshold_response(
        dataset,
        output_dir,
        style,
        args,
        axial_ratio_column,
        "Axial Ratio",
        "Axial Ratio (dB)",
        "Axial_Ratio",
        threshold,
        f"{threshold:g} dB",
    )


def plot_vswr(dataset: HfssDataset, output_dir: Path, style: dict, args: Namespace) -> list[Path]:
    threshold = getattr(args, "threshold", None)
    if threshold is None:
        threshold = getattr(args, "vswr_threshold", 2.0)
    return plot_threshold_response(
        dataset,
        output_dir,
        style,
        args,
        vswr_column,
        "VSWR",
        "VSWR",
        "VSWR",
        threshold,
        f"VSWR = {threshold:g}",
    )


def plot_xy(dataset: HfssDataset, output_dir: Path, style: dict, args: Namespace) -> list[Path]:
    apply_style(style)
    x, unit_label, _ = frequency_values(dataset, args, style)
    columns = getattr(args, "y_columns", None)
    if not columns:
        if getattr(args, "y_column", None):
            columns = [args.y_column]
        else:
            numeric_headers = []
            for header in dataset.headers:
                values = dataset.column(header)
                if np.isfinite(values).sum() >= 2 and header != getattr(args, "x_column", None):
                    numeric_headers.append(header)
            columns = numeric_headers[1:] if len(numeric_headers) > 1 else numeric_headers
    if not columns:
        raise ValueError("No y columns selected. Use --y-column or --y-columns.")
    labels = curve_labels(args, columns, columns[0])
    order = np.argsort(x)
    x = x[order]

    fig, ax = plt.subplots(figsize=figure_size(style), constrained_layout=True)
    for index, column in enumerate(columns):
        y = dataset.column(column)[order]
        options = curve_style(style, index, style["colors"]["black"])
        curve_x, curve_y, marker_x, marker_y = prepare_curve_data(x, y, args, unit_label)
        plot_curve(
            ax,
            curve_x,
            curve_y,
            labels[index],
            options,
            style,
            getattr(args, "no_markers", False),
            marker_x,
            marker_y,
        )
    ylabel = getattr(args, "ylabel", None) or "Response"
    draw_frequency_band(ax, args, unit_label, style["colors"]["black"])
    apply_limits_labels(ax, args, f"Frequency ({unit_label})", ylabel)
    grid(ax, style)
    ax.legend(loc=getattr(args, "legend_loc", None) or style.get("legend", {}).get("loc", "best"))
    return save_figure(fig, output_dir / f"{dataset.path.stem}_XY", style)


def plot_pattern(dataset: HfssDataset, output_dir: Path, style: dict, args: Namespace) -> list[Path]:
    apply_style(style)
    phi_col = getattr(args, "phi_column", None) or phi_column(dataset.headers)
    theta_col = getattr(args, "theta_column", None) or theta_column(dataset.headers)
    value_cols = (
        getattr(args, "gain_columns", None)
        or getattr(args, "y_columns", None)
        or None
    )
    if value_cols is None:
        value_col = getattr(args, "gain_column", None) or getattr(args, "y_column", None)
        value_cols = [value_col] if value_col else pattern_value_columns(dataset.headers)
    if not phi_col or not theta_col or not value_cols:
        raise ValueError("Could not detect phi/theta/gain columns for radiation pattern.")
    pattern_info = recognize_pattern(dataset, value_cols)
    phi = dataset.column(phi_col)
    theta = dataset.column(theta_col)
    gains = [dataset.column(column) for column in value_cols]
    labels = curve_labels(args, value_cols, "Gain")
    cuts = getattr(args, "cuts", None)
    if cuts is None and pattern_info.cut_type == "2d_farfield_grid":
        cuts = sorted(float(value) for value in np.unique(np.round(phi[np.isfinite(phi)], 6)))
    elif cuts is None:
        cuts = [pattern_info.fixed_value_deg] if pattern_info.fixed_value_deg is not None else [0.0]
    is_normalized = not getattr(args, "absolute", False)
    if is_normalized:
        global_max = max(float(np.nanmax(gain)) for gain in gains)
        gains = [gain - global_max for gain in gains]

    base_width, _ = figure_size(style, ratio=0.86)
    fig = plt.figure(figsize=(max(base_width, 4.6), 4.2), constrained_layout=True)
    ax = fig.add_subplot(111, projection="polar")
    colors = style["colors"].get("cycle") or [style["colors"]["s11"], style["colors"]["gain"], style["colors"]["black"], style["colors"]["gray"]]
    line_index = 0
    for cut in cuts:
        if pattern_info.scan_variable == "phi":
            mask = np.isclose(theta, pattern_info.fixed_value_deg, atol=1e-6) if pattern_info.fixed_value_deg is not None else np.isfinite(phi)
            angle_values = phi
            cut_text = (
                rf"$\theta$ = {pattern_info.fixed_value_deg:g}$^\circ$"
                if pattern_info.fixed_value_deg is not None
                else r"$\phi$ sweep"
            )
        else:
            mask = np.isclose(phi, cut, atol=1e-6)
            angle_values = theta
            cut_text = rf"$\phi$ = {cut:g}$^\circ$"
        if mask.sum() < 3:
            continue
        order = np.argsort(angle_values[mask])
        t = np.deg2rad(angle_values[mask][order])
        for column_index, gain in enumerate(gains):
            g = gain[mask][order]
            role = polarization_role(value_cols[column_index])
            role_text = "" if role == "unknown" else f" ({role.replace('_', ' ')})"
            quantity_label = compact_pattern_label(value_cols[column_index])
            label = cut_text if len(value_cols) == 1 else f"{cut_text} / {quantity_label}"
            ax.plot(
                t,
                g,
                linewidth=style["line"]["width"],
                color=colors[line_index % len(colors)],
                label=label,
            )
            line_index += 1
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_rlabel_position(135)
    ax.set_ylabel(normalized_pattern_label(is_normalized), labelpad=22)
    ax.grid(True, alpha=style["axis"]["grid_alpha"])
    ax.legend(
        loc="center left",
        bbox_to_anchor=(1.08, 0.5),
        ncol=1,
        fontsize=style.get("font", {}).get("legend_size", 8),
        frameon=False,
    )
    title = f"{pattern_info.short_title()}\n{normalized_pattern_label(is_normalized)}"
    freq_col = frequency_column(dataset.headers)
    if freq_col:
        freq, _ = convert_frequency(dataset.column(freq_col), freq_col, "ghz")
        finite = freq[np.isfinite(freq)]
        if len(finite):
            title += f" at {float(np.nanmedian(finite)):.2f} GHz"
    ax.set_title(title, pad=10, fontsize=style.get("font", {}).get("label_size", 9))
    if pattern_info.warnings:
        ax.text(
            0.02,
            0.02,
            "; ".join(pattern_info.warnings),
            transform=ax.transAxes,
            ha="left",
            va="bottom",
            fontsize=style.get("font", {}).get("small_size", 7),
        )
    suffix = "Radiation_Pattern_abs" if getattr(args, "absolute", False) else "Radiation_Pattern"
    return save_figure(fig, output_dir / f"{dataset.path.stem}_{suffix}", style)


def draw_smith_grid(ax: plt.Axes) -> None:
    theta = np.linspace(0, 2 * np.pi, 512)
    ax.plot(np.cos(theta), np.sin(theta), color="#222222", linewidth=1.0)
    for r in [0, 0.2, 0.5, 1, 2, 5]:
        center = r / (r + 1)
        radius = 1 / (r + 1)
        t = np.linspace(0, 2 * np.pi, 512)
        x = center + radius * np.cos(t)
        y = radius * np.sin(t)
        mask = x * x + y * y <= 1.0001
        ax.plot(x[mask], y[mask], color="#CFCFCF", linewidth=0.55)
    for x_reactance in [0.2, 0.5, 1, 2, 5]:
        for sign in [1, -1]:
            center_x = 1.0
            center_y = sign / x_reactance
            radius = abs(1 / x_reactance)
            t = np.linspace(0, 2 * np.pi, 512)
            x = center_x + radius * np.cos(t)
            y = center_y + radius * np.sin(t)
            mask = x * x + y * y <= 1.0001
            ax.plot(x[mask], y[mask], color="#D9D9D9", linewidth=0.5)
    ax.axhline(0, color="#B0B0B0", linewidth=0.6)


def plot_smith(dataset: HfssDataset, output_dir: Path, style: dict, args: Namespace) -> list[Path]:
    apply_style(style)
    real_col = getattr(args, "real_column", None) or smith_real_column(dataset.headers)
    imag_col = getattr(args, "imag_column", None) or smith_imag_column(dataset.headers)
    if not real_col or not imag_col:
        raise ValueError("Could not detect Smith chart real/imag columns.")
    gamma = dataset.column(real_col) + 1j * dataset.column(imag_col)
    finite = np.isfinite(gamma.real) & np.isfinite(gamma.imag)
    gamma = gamma[finite]

    fig, ax = plt.subplots(figsize=figure_size(style, ratio=1.0), constrained_layout=True)
    draw_smith_grid(ax)
    ax.plot(
        gamma.real,
        gamma.imag,
        color=style["colors"]["s11"],
        linewidth=style["line"]["width"],
        marker=None if getattr(args, "no_markers", False) else "o",
        markersize=style["line"]["marker_size"],
        label=getattr(args, "label", None) or r"$S_{11}$",
    )
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(-1.05, 1.05)
    ax.set_ylim(-1.05, 1.05)
    ax.set_xlabel("Real")
    ax.set_ylabel("Imaginary")
    ax.legend(loc=getattr(args, "legend_loc", None) or "upper right")
    ax.grid(False)
    return save_figure(fig, output_dir / f"{dataset.path.stem}_Smith", style)
