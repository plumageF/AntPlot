"""Stable backend API facade for frontend data and plotting workflows."""

from __future__ import annotations

import json
import hashlib
import csv
import contextvars
import re
import threading
import time
from argparse import Namespace
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .config import load_project_config
from .curve_manager import CurveManager, curves_from_dataset, infer_curve_source, metric_enabled_curves, plot_overlay
from .engineering_metrics import format_metric_results, metric_results_for_curves
from .export_artifacts import jsonable, split_export_formats
from .models import Curve, CurveSource, infer_file_format, infer_source_type
from .project_settings import ProjectSettings, apply_project_settings, project_settings_from_config
from .reader import CsvParseReport, HfssDataset, clean_number, curve_from_columns, detect_kind, has_complex_values, recognition_from_dataset, read_hfss_csv
from .report_planner import plan_report_from_dataset
from .sample_policy import apply_sampling_policy, sample_count_warning
from .style import load_style


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config.yaml"
DEFAULT_PREVIEW_DIR = ROOT / "outputs" / "api_preview"
DEFAULT_EXPORT_DIR = ROOT / "outputs" / "api_export"
SUPPORTED_SCAN_EXTENSIONS = {".csv", ".txt", ".dat", ".xlsx", ".xls", ".s1p", ".s2p", ".snp"}


def _messages() -> dict[str, list[dict[str, Any]]]:
    return {"errors": [], "warnings": [], "infos": []}


def _item(message: str, code: str = "message", **context: Any) -> dict[str, Any]:
    return {"code": code, "message": message, "context": jsonable(context)}


def _response(ok: bool, data: dict[str, Any] | None = None, **messages: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "ok": ok,
        "data": jsonable(data or {}),
        "errors": messages.get("errors", []),
        "warnings": messages.get("warnings", []),
        "infos": messages.get("infos", []),
    }


def _curve_id(curve: Curve, ordinal: int) -> str:
    if curve.metadata.get("curve_id"):
        return str(curve.metadata["curve_id"])
    seed = "|".join(
        [
            curve.dataset_id,
            curve.x_column,
            curve.y_column,
            curve.label,
            str(curve.conversion or ""),
            str(ordinal),
        ]
    )
    return "curve_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def _range(values: np.ndarray) -> dict[str, float | None]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {"min": None, "max": None}
    return {"min": float(np.nanmin(finite)), "max": float(np.nanmax(finite))}


def _ordered_family_values(dataset: HfssDataset, family_column: str) -> list[str]:
    """Return non-empty family values in file order for manual multi-curve grouping."""

    values: list[str] = []
    seen: set[str] = set()
    for row in dataset.rows:
        value = str(row.get(family_column, "")).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return values


def _family_mask(dataset: HfssDataset, family_column: str, family_value: str) -> np.ndarray:
    return np.asarray([str(row.get(family_column, "")).strip() == family_value for row in dataset.rows], dtype=bool)


def _format_family_label(column: str, value: str) -> str:
    text = str(value).strip().strip("\"'")
    try:
        number = float(text)
        text = f"{number:g}"
    except ValueError:
        pass
    lower = column.lower()
    if any(token in lower for token in ["phi", "theta", "angle"]) and "deg" not in text.lower() and "°" not in text:
        text = f"{text}°"
    name = re.sub(r"\s*\[[^\]]+\]", "", column).strip().strip("\"'") or column.strip().strip("\"'")
    return f"{name} = {text}"


def _read_xy_standard_csv(path: Path) -> tuple[HfssDataset, list[str], list[str]]:
    """Read strict wide-table XY CSV without interpreting engineering meaning."""

    errors: list[str] = []
    warnings: list[str] = []
    if path.suffix.lower() != ".csv":
        errors.append("XY Multi-Curve only accepts standard CSV files; convert XLSX/TXT to CSV first.")
        return HfssDataset(path=path, headers=[], rows=[]), warnings, errors
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    if not lines:
        errors.append("XY CSV is empty.")
        return HfssDataset(path=path, headers=[], rows=[]), warnings, errors
    if any(not line.strip() for line in lines):
        errors.append("XY CSV must not contain empty lines.")
    reader = csv.reader(lines)
    records = list(reader)
    if not records:
        errors.append("XY CSV has no records.")
        return HfssDataset(path=path, headers=[], rows=[]), warnings, errors
    headers = [item.strip().replace("\ufeff", "") for item in records[0]]
    if len(headers) < 2:
        errors.append("XY CSV must contain at least two columns: X and one Y curve.")
    if any(not header for header in headers):
        errors.append("XY CSV header cells must not be empty.")
    rows: list[dict[str, str]] = []
    numeric_columns: dict[str, list[float]] = {header: [] for header in headers}
    for row_index, record in enumerate(records[1:], start=2):
        if len(record) != len(headers):
            errors.append(f"Row {row_index} has {len(record)} columns; expected {len(headers)}.")
            continue
        row: dict[str, str] = {}
        for header, raw_value in zip(headers, record):
            value = str(raw_value).strip()
            number = clean_number(value)
            if value == "" or not np.isfinite(number):
                errors.append(f"Row {row_index}, column {header} is not a finite number.")
            row[header] = value
            numeric_columns[header].append(number)
        rows.append(row)
    if not rows:
        errors.append("XY CSV must contain at least one numeric data row.")
    x_values = np.asarray(numeric_columns.get(headers[0], []), dtype=float) if headers else np.asarray([])
    if x_values.size:
        if np.any(np.diff(x_values) < 0):
            warnings.append("X is not monotonic; XY plot will preserve the original row order.")
        unique_x = np.unique(x_values[np.isfinite(x_values)])
        duplicate_count = int(x_values.size - unique_x.size)
        if duplicate_count > 0:
            warnings.append(f"Duplicate X values detected: {duplicate_count}; plotting is allowed.")
    if max(0, len(headers) - 1) > 10:
        warnings.append("More than 10 Y curves detected; select a subset before plotting.")
    ranges = {}
    for header, values in numeric_columns.items():
        array = np.asarray(values, dtype=float)
        finite = array[np.isfinite(array)]
        ranges[header] = (float(np.nanmin(finite)), float(np.nanmax(finite))) if finite.size else None
    report = CsvParseReport(
        columns=headers,
        row_count=len(rows),
        units={header: None for header in headers},
        ranges=ranges,
        has_missing_values=bool(errors),
        missing_values={},
        has_duplicate_points=any("Duplicate X" in warning for warning in warnings),
        duplicate_point_count=int(x_values.size - np.unique(x_values[np.isfinite(x_values)]).size) if x_values.size else 0,
        possible_data_type="xy_multi_curve",
        warnings=warnings,
        delimiter=",",
        header_rows=[1],
    )
    return HfssDataset(path=path, headers=headers, rows=rows, parse_report=report), warnings, errors


def _xy_curves_from_dataset(dataset: HfssDataset) -> list[Curve]:
    if len(dataset.headers) < 2:
        return []
    x_column = dataset.headers[0]
    x_data = dataset.column(x_column)
    curves: list[Curve] = []
    for index, y_column in enumerate(dataset.headers[1:]):
        y_data = dataset.column(y_column)
        finite_y = y_data[np.isfinite(y_data)]
        curve = Curve(
            dataset_id=dataset.to_model().dataset_id or "",
            x_data=x_data.copy(),
            y_data=y_data,
            x_column=x_column,
            y_column=y_column,
            x_quantity="x",  # type: ignore[arg-type]
            y_quantity="Value",  # type: ignore[arg-type]
            x_unit="linear",  # type: ignore[arg-type]
            y_unit="linear",
            label=y_column,
            source_role="Manual",
            metadata={
                "source_file": str(dataset.path),
                "report_domain": "free_xy",
                "compatible_plot_types": ["XY Multi-Curve"],
                "default_selected": index < 10,
                "manual_confirmed": True,
                "xy_multi_curve": True,
                "preserve_order": True,
                "participate_metrics": False,
                "y_range": {
                    "min": float(np.nanmin(finite_y)) if finite_y.size else None,
                    "max": float(np.nanmax(finite_y)) if finite_y.size else None,
                },
            },
            conversion="standard XY wide table; no engineering interpretation",
        )
        curves.append(curve)
    return curves


def _xy_basic_report(curves: list[Curve]) -> str:
    if not curves:
        return "XY Multi-Curve report: no curves selected."
    first = curves[0]
    x = first.x_data[np.isfinite(first.x_data)]
    duplicate_x = int(x.size - np.unique(x).size) if x.size else 0
    lines = [
        "XY Multi-Curve Basic Plot Report",
        f"File: {first.metadata.get('source_file', '')}",
        f"Title: {first.metadata.get('title', '') or 'XY Multi-Curve'}",
        f"X column: {first.x_column}",
        f"X min / X max: {float(np.nanmin(x)) if x.size else 'n/a'} / {float(np.nanmax(x)) if x.size else 'n/a'}",
        f"Y curve count: {len(curves)}",
        "Preserve original row order: yes",
        f"Duplicate X count: {duplicate_x}",
        "Missing values: no",
        "Engineering pass/fail metrics: skipped",
        "",
        "Curves:",
    ]
    for curve in curves:
        y = curve.y_data[np.isfinite(curve.y_data)]
        lines.append(
            f"- {curve.label}: sample_count={min(len(curve.x_data), len(curve.y_data))}, "
            f"Y min={float(np.nanmin(y)) if y.size else 'n/a'}, Y max={float(np.nanmax(y)) if y.size else 'n/a'}"
        )
    return "\n".join(lines)


def _curve_summary(curve: Curve) -> dict[str, Any]:
    curve_id = str(curve.metadata.get("curve_id", ""))
    sample_count = int(curve.metadata.get("sample_count", min(len(curve.x_data), len(curve.y_data))))
    raw_sample_count = int(curve.metadata.get("raw_sample_count", sample_count))
    return {
        "curve_id": curve_id,
        "dataset_id": curve.dataset_id,
        "x_column": curve.x_column,
        "y_column": curve.y_column,
        "x_quantity": curve.x_quantity,
        "y_quantity": curve.y_quantity,
        "x_unit": curve.x_unit,
        "y_unit": curve.y_unit,
        "label": curve.label,
        "is_enabled": curve.is_enabled,
        "is_normalized": curve.is_normalized,
        "conversion": curve.conversion,
        "source_role": curve.source_role,
        "source_type": curve.source_role,
        "order": curve.order,
        "point_count": sample_count,
        "sample_count": sample_count,
        "raw_sample_count": raw_sample_count,
        "unique_x_count": curve.metadata.get("unique_x_count"),
        "displayed_sample_count": curve.metadata.get("displayed_sample_count", sample_count),
        "duplicate_x_count_after_grouping": curve.metadata.get("duplicate_x_count_after_grouping", curve.metadata.get("duplicate_x_count", 0)),
        "sample_display_policy": curve.metadata.get("sample_display_policy", "marker_only_decimate"),
        "x_range": _range(curve.x_data),
        "y_range": _range(curve.y_data),
        "warnings": list(curve.warnings),
        "metadata": curve.metadata,
        "source_file": str(curve.metadata.get("source_file") or ""),
        "report_domain": curve.metadata.get("report_domain", "unknown"),
        "family_info": curve.metadata.get("family_info", {}),
        "compatible_plot_types": curve.metadata.get("compatible_plot_types", []),
        "default_selected": bool(curve.metadata.get("default_selected", True)),
        "line_width": curve.metadata.get("line_width", 1.5),
        "line_style": curve.metadata.get("line_style", "-"),
        "color": curve.metadata.get("color"),
        "marker_enabled": curve.metadata.get("marker_enabled", False),
        "marker": curve.metadata.get("marker", "o"),
        "marker_size": curve.metadata.get("marker_size", 3.0),
        "marker_every": curve.metadata.get("marker_every", 10),
        "alpha": curve.metadata.get("alpha", 1.0),
        "participate_metrics": curve.metadata.get("participate_metrics", True),
    }


def _family_info_for_curve(curve: Curve, report_plan: dict[str, Any] | None = None) -> dict[str, Any]:
    report_plan = report_plan or {}
    info: dict[str, Any] = {}
    parameter_pairs: dict[str, str] = {}
    for key, value in re.findall(r"\b([A-Za-z_]\w*)\s*=\s*([+-]?\d+(?:\.\d+)?\s*(?:pF|nF|uF|µF|mF|F|nH|uH|µH|mH|H|ohm|kOhm|MOhm|mm|cm|m))\b", str(curve.label or ""), flags=re.IGNORECASE):
        parameter_pairs[key] = value.replace(" ", "")
    if parameter_pairs:
        info["parameters"] = parameter_pairs
    for key in [
        "family_variable",
        "family_value",
        "family_value_deg",
        "fixed_variable",
        "fixed_value_deg",
        "scan_variable",
        "cut_type",
        "cut",
    ]:
        if curve.metadata.get(key) is not None:
            info[key] = curve.metadata.get(key)
    family_variables = report_plan.get("family_variables") or []
    if family_variables and "report_family_variables" not in info:
        info["report_family_variables"] = family_variables
    fixed_variables = report_plan.get("fixed_variables") or []
    if fixed_variables and "report_fixed_variables" not in info and not parameter_pairs:
        info["report_fixed_variables"] = fixed_variables
    return info


def _enrich_curve_summary(summary: dict[str, Any], curve: Curve, report_plan: dict[str, Any] | None, default_selected: bool) -> dict[str, Any]:
    report_plan = report_plan or {}
    report_model = report_plan.get("report_model") or {}
    return {
        **summary,
        "source_file": str(curve.metadata.get("source_file") or ""),
        "report_domain": report_model.get("report_domain") or report_plan.get("result_domain") or "unknown",
        "family_info": _family_info_for_curve(curve, report_plan),
        "compatible_plot_types": report_model.get("compatible_plot_types") or report_plan.get("compatible_plot_types") or [],
        "default_selected": bool(default_selected),
    }


def _candidate_default_selection(curves: list[Curve]) -> tuple[list[bool], list[str]]:
    count = len(curves)
    warnings: list[str] = []
    if count == 0:
        return [], warnings
    if count <= 5:
        return [True] * count, warnings
    if count <= 10:
        warnings.append(f"{count} candidate curves detected; all are selected by default, but the legend may be crowded.")
        return [True] * count, warnings
    if count <= 20:
        warnings.append(f"{count} candidate curves detected; more than 10 curves are not all selected by default. Select the curves to plot.")
        return [False] * count, warnings
    warnings.append(f"{count} candidate curves detected; curve filtering mode is required. Select by parameter, frequency, Phi/Theta, or source before plotting.")
    return [False] * count, warnings


def _candidate_set_warnings(curves: list[Curve]) -> list[str]:
    warnings: list[str] = []
    if not curves:
        return warnings
    x_keys = {(curve.x_column, curve.x_quantity, curve.x_unit) for curve in curves}
    y_quantities = {curve.y_quantity for curve in curves}
    y_units = {curve.y_unit for curve in curves}
    if len(x_keys) > 1:
        warnings.append("Candidate curves do not share one X-axis mapping; confirm variables before creating curves.")
    if len(y_quantities) > 1:
        warnings.append("Candidate curves contain mixed physical quantities; current plot type filtering should be reviewed before overlay.")
    if len(y_units) > 1:
        warnings.append("Candidate curves contain mixed Y units; they should not share one ordinary Y axis unless XY Multi-Curve or dual-axis mode is explicitly selected.")
    return warnings


STYLE_COLORS = [
    "#EF4444",
    "#4B5563",
    "#2563EB",
    "#16A34A",
    "#F97316",
    "#7C3AED",
    "#0891B2",
    "#DB2777",
    "#A16207",
    "#111827",
]
STYLE_LINES = ["-", "--", "-.", ":"]


def _default_line_style(curve: Curve, index: int, total: int) -> str:
    role = str(curve.source_role or "").lower()
    label = str(curve.label or "").lower()
    text = f"{role} {label}"
    if "meas" in text:
        return "--"
    if "reference" in text or re.search(r"\bref\b", text):
        return ":"
    if "sim" in text:
        return "-"
    if total >= 6:
        return STYLE_LINES[(index // len(STYLE_COLORS)) % len(STYLE_LINES)]
    return "-"


def _apply_default_curve_styles(curves: list[Curve], default_selected_flags: list[bool]) -> list[Curve]:
    total = len(curves)
    styled: list[Curve] = []
    for index, curve in enumerate(curves):
        metadata = dict(curve.metadata)
        metadata.setdefault("color", STYLE_COLORS[index % len(STYLE_COLORS)])
        metadata.setdefault("line_width", 1.5)
        metadata.setdefault("line_style", _default_line_style(curve, index, total))
        metadata.setdefault("marker", "o")
        metadata.setdefault("marker_size", 3.0)
        sample_count = min(len(curve.x_data), len(curve.y_data))
        metadata.setdefault("marker_every", 1 if sample_count < 30 else 10 if sample_count < 300 else 50)
        metadata.setdefault("marker_enabled", sample_count < 30)
        metadata.setdefault("alpha", 1.0)
        metadata.setdefault("sample_display_policy", "marker_only_decimate")
        metadata["default_selected"] = default_selected_flags[index] if index < len(default_selected_flags) else False
        curve.is_enabled = bool(metadata["default_selected"])
        styled.append(replace(curve, metadata=metadata))
    return styled


def _style_flags_from_created(curves: list[Curve]) -> list[bool]:
    if len(curves) > 10:
        return [index < 10 and curve.is_enabled for index, curve in enumerate(curves)]
    return [curve.is_enabled for curve in curves]


def _coerce_curve_style_updates(update_config: dict[str, Any]) -> dict[str, Any]:
    coerced = dict(update_config)
    if "line_width" in coerced:
        try:
            coerced["line_width"] = max(0.3, min(6.0, float(coerced["line_width"])))
        except (TypeError, ValueError):
            coerced.pop("line_width", None)
    if "marker_size" in coerced:
        try:
            coerced["marker_size"] = max(0.1, min(30.0, float(coerced["marker_size"])))
        except (TypeError, ValueError):
            coerced.pop("marker_size", None)
    if "marker_every" in coerced:
        try:
            coerced["marker_every"] = max(1, int(float(coerced["marker_every"])))
        except (TypeError, ValueError):
            coerced.pop("marker_every", None)
    if "alpha" in coerced:
        try:
            coerced["alpha"] = max(0.05, min(1.0, float(coerced["alpha"])))
        except (TypeError, ValueError):
            coerced.pop("alpha", None)
    return coerced


def _rebuild_curve_from_dataset(curve: Curve, *, normalize_curve: bool) -> Curve | None:
    dataset = default_session.datasets.get(curve.dataset_id)
    if dataset is None:
        return None
    rebuilt = curve_from_columns(
        dataset,
        curve.x_column,
        curve.y_column,
        x_unit=curve.x_unit,
        y_unit=curve.y_unit,
        label=curve.label,
        normalize_curve=normalize_curve,
    )
    rebuilt.source_role = curve.source_role
    rebuilt.is_enabled = curve.is_enabled
    rebuilt.order = curve.order
    rebuilt.y_quantity = curve.y_quantity
    rebuilt.y_unit = curve.y_unit if not normalize_curve else rebuilt.y_unit
    preserved_metadata = {
        key: value
        for key, value in curve.metadata.items()
        if key
        in {
            "curve_id",
            "source_file",
            "report_domain",
            "family_info",
            "compatible_plot_types",
            "default_selected",
            "line_width",
            "line_style",
            "color",
            "marker_enabled",
            "marker",
            "marker_style",
            "marker_size",
            "marker_every",
            "alpha",
            "sample_display_policy",
            "participate_metrics",
            "cut_type",
            "scan_variable",
            "family_variable",
            "fixed_variable",
            "fixed_value_deg",
            "fixed_frequency",
        }
    }
    rebuilt.metadata.update(preserved_metadata)
    rebuilt.warnings = [warning for warning in curve.warnings if "Cannot restore absolute values after normalization" not in warning]
    return rebuilt


def _dataset_summary(dataset: HfssDataset) -> dict[str, Any]:
    model = dataset.to_model()
    warnings = list(model.warnings)
    low_sample = sample_count_warning(model.row_count)
    if low_sample and low_sample not in warnings:
        warnings.append(low_sample)
    metadata = dict(model.metadata)
    metadata["sample_count"] = model.row_count
    metadata["sampling_policy"] = "raw rows preserved; curves may be sorted by X ascending while preserving X/Y pairs"
    return {
        "dataset_id": model.dataset_id,
        "source_file": str(model.source_file),
        "source_type": model.source_type,
        "file_format": model.file_format,
        "data_type": model.data_type,
        "columns": model.columns,
        "units": model.units,
        "row_count": model.row_count,
        "sample_count": model.row_count,
        "warnings": warnings,
        "metadata": metadata,
    }


def _recognition_summary(recognition: Any) -> dict[str, Any]:
    return {
        "mode": recognition.mode,
        "detected_delimiter": recognition.detected_delimiter,
        "detected_header_rows": recognition.detected_header_rows,
        "detected_x_column": recognition.detected_x_column,
        "detected_y_columns": recognition.detected_y_columns,
        "detected_units": recognition.detected_units,
        "detected_plot_type": recognition.detected_plot_type,
        "detected_curves": recognition.detected_curves,
        "requires_confirmation": recognition.requires_confirmation,
        "confirmation_reasons": recognition.confirmation_reasons,
        "warnings": recognition.warnings,
        "user_overrides": recognition.user_overrides,
    }


def _settings_from_payload(payload: dict[str, Any] | None = None) -> ProjectSettings:
    payload = payload or {}
    if "project" in payload:
        return project_settings_from_config(payload)
    config = load_project_config(Path(payload.get("config", DEFAULT_CONFIG)))
    settings = project_settings_from_config(config)
    if payload.get("target_band_mhz") is not None and payload.get("working_band_mhz") is None:
        payload["working_band_mhz"] = payload["target_band_mhz"]
    for key, value in payload.items():
        if hasattr(settings, key):
            setattr(settings, key, tuple(value) if key == "working_band_mhz" and isinstance(value, list) else value)
    return settings


def _style_from_config(style_name: str | None, formats: list[str] | None, dpi: int | None = None) -> dict:
    style = load_style(style_name or "ieee_tap")
    image_formats, requested_formats = split_export_formats(formats)
    style["export"]["formats"] = image_formats
    style["export"]["requested_formats"] = requested_formats
    if dpi:
        style["figure"]["dpi"] = int(dpi)
    return style


def _namespace(config: dict[str, Any], settings: ProjectSettings, *, export: bool = False) -> Namespace:
    axis = config.get("axis") or {}
    polar = config.get("polar_config") or {}
    args = Namespace(
        output_name=config.get("output_name") or ("export_plot" if export else "preview_plot"),
        plot_type=config.get("plot_type") or "s11",
        command=config.get("plot_type") or "s11",
        inputs=[],
        x_unit=config.get("x_unit") or "auto",
        xlabel=axis.get("xlabel"),
        ylabel=axis.get("ylabel"),
        xlim=axis.get("xlim"),
        ylim=axis.get("ylim"),
        xtick_major=axis.get("xtick_major"),
        ytick_major=axis.get("ytick_major"),
        xtick_minor=axis.get("xtick_minor"),
        ytick_minor=axis.get("ytick_minor"),
        grid_enabled=axis.get("grid_enabled"),
        annotations=axis.get("annotations") or [],
        legend_loc=config.get("legend_loc") or "best",
        no_markers=bool(config.get("no_markers", False)),
        no_grid=bool(config.get("no_grid", False)),
        threshold=config.get("threshold"),
        no_threshold=not bool(config.get("draw_threshold", True)) or bool(config.get("no_threshold", False)),
        fl=config.get("fl"),
        fc=config.get("fc"),
        fh=config.get("fh"),
        project_settings=settings,
        manual_config=config.get("manual_config"),
        export_scope=config.get("export_scope"),
        dpi=config.get("dpi"),
        display_mode=config.get("display_mode") or config.get("pattern_display_mode") or polar.get("display_mode"),
        pattern_display_mode=config.get("pattern_display_mode") or config.get("display_mode") or polar.get("display_mode") or "cartesian",
        r_min=config.get("r_min", polar.get("r_min")),
        r_max=config.get("r_max", polar.get("r_max")),
        pattern_normalize=bool(config.get("pattern_normalize", config.get("normalize", polar.get("normalize", False)))),
        theta_zero_location=config.get("theta_zero_location") or polar.get("theta_zero_location") or "N",
        theta_direction=int(config.get("theta_direction", polar.get("theta_direction", -1)) or -1),
        polar_style=config.get("polar_style") or polar.get("polar_style") or "paper",
        angle_label_mode=config.get("angle_label_mode") or polar.get("angle_label_mode"),
        title=config.get("title") or polar.get("title"),
    )
    apply_project_settings(args, settings)
    return args


def _selected_curves(curves: Iterable[str | Curve | dict[str, Any]]) -> tuple[list[Curve], list[dict[str, Any]]]:
    selected: list[Curve] = []
    errors: list[dict[str, Any]] = []
    for item in curves:
        if isinstance(item, Curve):
            selected.append(item)
            continue
        curve_id = item.get("curve_id") if isinstance(item, dict) else str(item)
        curve = default_session.curves.get(str(curve_id))
        if curve is None:
            errors.append(_item(f"Curve not found: {curve_id}", "curve_not_found", curve_id=curve_id))
        else:
            selected.append(curve)
    return selected, errors


class BackendSession:
    """In-memory state used by the stable API facade."""

    def __init__(self) -> None:
        self.datasets: dict[str, HfssDataset] = {}
        self.recognitions: dict[str, Any] = {}
        self.report_plans: dict[str, dict[str, Any]] = {}
        self.candidates: dict[str, dict[str, Curve]] = {}
        self.curves: dict[str, Curve] = {}
        self._counter = 0

    def clear(self) -> None:
        self.datasets.clear()
        self.recognitions.clear()
        self.report_plans.clear()
        self.candidates.clear()
        self.curves.clear()
        self._counter = 0

    def next_curve(self, curve: Curve) -> Curve:
        self._counter += 1
        curve = apply_sampling_policy(curve)
        seed_curve = replace(curve, metadata={key: value for key, value in curve.metadata.items() if key != "curve_id"})
        curve_id = _curve_id(seed_curve, self._counter)
        while curve_id in self.curves or any(curve_id in group for group in self.candidates.values()):
            self._counter += 1
            curve_id = _curve_id(seed_curve, self._counter)
        return replace(curve, metadata={**curve.metadata, "curve_id": curve_id})


_base_session = BackendSession()
_session_context: contextvars.ContextVar[BackendSession] = contextvars.ContextVar("hfss_paperplotter_session", default=_base_session)
_sessions: dict[str, BackendSession] = {}
_session_last_seen: dict[str, float] = {}
_sessions_lock = threading.RLock()
SESSION_TTL_SECONDS = 60 * 60 * 6
SESSION_CLEANUP_INTERVAL_SECONDS = 60 * 10
_last_session_cleanup = 0.0


def _cleanup_sessions(now: float | None = None) -> None:
    global _last_session_cleanup
    current = now or time.time()
    if current - _last_session_cleanup < SESSION_CLEANUP_INTERVAL_SECONDS:
        return
    _last_session_cleanup = current
    expired = [
        key
        for key, last_seen in _session_last_seen.items()
        if current - last_seen > SESSION_TTL_SECONDS
    ]
    for key in expired:
        _sessions.pop(key, None)
        _session_last_seen.pop(key, None)


def _session_for(session_id: str | None) -> BackendSession:
    key = str(session_id or "").strip()
    if not key:
        return _base_session
    with _sessions_lock:
        now = time.time()
        _cleanup_sessions(now)
        session = _sessions.get(key)
        if session is None:
            session = BackendSession()
            _sessions[key] = session
        _session_last_seen[key] = now
        return session


class _SessionProxy:
    def __getattr__(self, name: str) -> Any:
        return getattr(_session_context.get(), name)


default_session = _SessionProxy()


def import_files(files: list[str | Path], mode: str = "semiauto", parse_options: dict[str, Any] | None = None) -> dict[str, Any]:
    """Import one or more files and return Dataset summaries plus recognition results."""

    messages = _messages()
    datasets: list[dict[str, Any]] = []
    recognitions: list[dict[str, Any]] = []
    for file_item in files:
        path = Path(file_item)
        try:
            if not path.exists():
                messages["errors"].append(_item(f"Input file does not exist: {path}", "file_not_found", path=str(path)))
                continue
            if mode == "xy":
                dataset, xy_warnings, xy_errors = _read_xy_standard_csv(path)
                if xy_errors:
                    for error in xy_errors:
                        messages["errors"].append(_item(error, "xy_standard_csv_error", path=str(path)))
                    continue
            else:
                dataset = read_hfss_csv(path, parse_options=parse_options)
                xy_warnings = []
            summary = _dataset_summary(dataset)
            if mode == "xy":
                summary["source_type"] = "Manual"
                summary["data_type"] = "unknown"
                summary["metadata"]["xy_multi_curve"] = True
                summary["metadata"]["report_plan"] = None
                summary["metadata"]["report_model"] = {
                    "report_domain": "free_xy",
                    "report_type": "xy_multi_curve",
                    "primary_sweep": dataset.headers[0] if dataset.headers else "X",
                    "quantity": "Value",
                    "compatible_plot_types": ["XY Multi-Curve"],
                    "warnings": xy_warnings,
                    "errors": [],
                    "infos": ["Standard XY wide table; engineering recognition skipped."],
                }
                xy_summary_warnings = [
                    warning
                    for warning in [*summary.get("warnings", []), *xy_warnings]
                    if "frequency column" not in str(warning).lower()
                    and "metric calculation" not in str(warning).lower()
                    and "curve trend" not in str(warning).lower()
                ]
                summary["warnings"] = list(dict.fromkeys(str(warning) for warning in xy_summary_warnings))
                dataset_id = str(summary["dataset_id"])
                default_session.datasets[dataset_id] = dataset
                default_session.recognitions[dataset_id] = None
                default_session.report_plans[dataset_id] = summary["metadata"]["report_model"]
                datasets.append(summary)
                recognitions.append(
                    {
                        "dataset_id": dataset_id,
                        "detected_plot_type": "xy",
                        "detected_x_column": dataset.headers[0] if dataset.headers else None,
                        "detected_y_columns": dataset.headers[1:],
                        "detected_units": {header: None for header in dataset.headers},
                        "requires_confirmation": True,
                        "confirmation_reasons": ["XY Multi-Curve requires the user to select enabled Y curves and styling."],
                        "warnings": xy_warnings,
                        "report_plan": summary["metadata"]["report_model"],
                        "report_model": summary["metadata"]["report_model"],
                    }
                )
                for warning in summary.get("warnings", []):
                    messages["warnings"].append(_item(str(warning), "xy_dataset_warning", dataset_id=dataset_id))
                messages["infos"].append(_item("Standard XY wide table imported; engineering recognition skipped.", "xy_standard_imported", dataset_id=dataset_id))
                continue
            if mode == "manual":
                summary["source_type"] = "Unknown"
                summary["data_type"] = "unknown"
                summary["metadata"]["manual_mode"] = True
                summary["warnings"] = [
                    *summary.get("warnings", []),
                    "Manual mode: backend only parsed table structure; physical meaning must be specified by the user.",
                ]
            dataset_id = str(summary["dataset_id"])
            recognition = recognition_from_dataset(dataset, mode)  # type: ignore[arg-type]
            report_plan = plan_report_from_dataset(dataset, mode).to_dict()
            report_model = report_plan.get("report_model")
            summary["metadata"]["report_plan"] = report_plan
            summary["metadata"]["report_model"] = report_model
            default_session.datasets[dataset_id] = dataset
            default_session.recognitions[dataset_id] = recognition
            default_session.report_plans[dataset_id] = report_plan
            datasets.append(summary)
            recognitions.append({"dataset_id": dataset_id, **_recognition_summary(recognition), "report_plan": report_plan, "report_model": report_model})
            for warning in summary.get("warnings", []):
                messages["warnings"].append(_item(str(warning), "dataset_warning", dataset_id=dataset_id))
            for warning in recognition.warnings:
                messages["warnings"].append(_item(str(warning), "recognition_warning", dataset_id=dataset_id))
            for warning in report_plan.get("warnings", []):
                messages["warnings"].append(_item(str(warning), "report_plan_warning", dataset_id=dataset_id))
            for error in report_plan.get("errors", []):
                messages["errors"].append(_item(str(error), "report_plan_error", dataset_id=dataset_id))
            if recognition.requires_confirmation:
                messages["infos"].append(_item("Dataset requires user confirmation before formal conclusions.", "confirmation_required", dataset_id=dataset_id))
            messages["infos"].append(
                _item(
                    "HFSS-like report plan detected.",
                    "report_plan_detected",
                    dataset_id=dataset_id,
                    result_domain=report_plan.get("result_domain"),
                    report_domain=(report_model or {}).get("report_domain") if isinstance(report_model, dict) else None,
                    report_type=(report_model or {}).get("report_type") if isinstance(report_model, dict) else None,
                    primary_sweep=report_plan.get("primary_sweep"),
                    recommended_plot_type=report_plan.get("recommended_plot_type"),
                    recommended_display_mode=report_plan.get("recommended_display_mode"),
                )
            )
        except Exception as exc:  # noqa: BLE001 - stable API surfaces per-file import errors.
            messages["errors"].append(_item(str(exc), "import_failed", path=str(path)))
    return _response(not messages["errors"], {"datasets": datasets, "recognitions": recognitions}, **messages)


def _guess_plot_label(kind: str) -> str:
    labels = {
        "s11": "S11",
        "vswr": "VSWR",
        "gain": "Gain",
        "pattern": "Radiation Pattern",
        "ar": "Axial Ratio",
        "eff": "Efficiency",
        "hpbw": "HPBW",
        "smith": "Smith",
    }
    return labels.get(kind, "Unknown")


def _scan_file_entry(path: Path, supported_extensions: set[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    extension = path.suffix.lower()
    supported = extension in supported_extensions
    stat = path.stat()
    guessed_data_type = "Unknown"
    guessed_source_type = "Unknown"
    file_warnings: list[str] = []
    if supported and extension in {".csv", ".txt", ".dat"}:
        try:
            dataset = read_hfss_csv(path)
            kind = detect_kind(dataset)
            guessed_data_type = _guess_plot_label(kind)
            guessed_source_type = infer_source_type(path, dataset.headers)
            file_warnings.extend(dataset.to_model().warnings)
            recognition = recognition_from_dataset(dataset, "semiauto")
            file_warnings.extend(recognition.warnings)
            if recognition.requires_confirmation:
                file_warnings.extend(recognition.confirmation_reasons)
        except Exception as exc:  # noqa: BLE001 - scanning must keep indexing mixed folders.
            supported = False
            file_warnings.append(f"File is listed but could not be parsed during indexing: {exc}")
            warnings.append(_item(str(exc), "file_probe_failed", path=str(path)))
    elif supported:
        guessed_data_type = "Unknown"
        file_warnings.append("Supported extension detected; parser for this format is not connected to import_files yet.")
    else:
        file_warnings.append("Unsupported extension; file will not be passed to import_files by default.")
    return (
        {
            "path": str(path),
            "name": path.name,
            "extension": extension,
            "size": int(stat.st_size),
            "modified_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
            "supported": supported,
            "guessed_data_type": guessed_data_type,
            "guessed_source_type": guessed_source_type,
            "file_format": infer_file_format(path) if extension in supported_extensions else "Unknown",
            "warnings": file_warnings,
        },
        warnings,
    )


def scan_directory(directory_path: str | Path, recursive: bool = False, file_types: list[str] | None = None) -> dict[str, Any]:
    """Scan a local directory and return an importable file index without creating datasets."""

    messages = _messages()
    directory = Path(directory_path)
    if not directory_path or not str(directory_path).strip():
        messages["errors"].append(_item("Directory path is empty.", "directory_path_empty"))
        return _response(False, {"directory_path": str(directory_path), "files": [], "unsupported_files": []}, **messages)
    if not directory.exists():
        messages["errors"].append(_item(f"Directory does not exist: {directory}", "directory_not_found", path=str(directory)))
        return _response(False, {"directory_path": str(directory), "files": [], "unsupported_files": []}, **messages)
    if not directory.is_dir():
        messages["errors"].append(_item(f"Path is not a directory: {directory}", "not_a_directory", path=str(directory)))
        return _response(False, {"directory_path": str(directory), "files": [], "unsupported_files": []}, **messages)

    allowed = {item.lower() if str(item).startswith(".") else f".{str(item).lower()}" for item in (file_types or SUPPORTED_SCAN_EXTENSIONS)}
    supported_extensions = allowed & SUPPORTED_SCAN_EXTENSIONS
    files: list[dict[str, Any]] = []
    unsupported_files: list[dict[str, Any]] = []
    try:
        iterator = directory.rglob("*") if recursive else directory.glob("*")
        paths = sorted(path for path in iterator if path.is_file())
    except PermissionError as exc:
        messages["errors"].append(_item(str(exc), "directory_permission_denied", path=str(directory)))
        return _response(False, {"directory_path": str(directory), "files": [], "unsupported_files": []}, **messages)

    if not paths:
        messages["warnings"].append(_item(f"Directory is empty: {directory}", "directory_empty", path=str(directory)))
        return _response(True, {"directory_path": str(directory), "files": [], "unsupported_files": []}, **messages)

    for path in paths:
        try:
            entry, entry_warnings = _scan_file_entry(path, supported_extensions)
            messages["warnings"].extend(entry_warnings)
            if entry["supported"]:
                files.append(entry)
            else:
                unsupported_files.append(entry)
        except PermissionError as exc:
            unsupported_files.append(
                {
                    "path": str(path),
                    "name": path.name,
                    "extension": path.suffix.lower(),
                    "size": None,
                    "modified_time": None,
                    "supported": False,
                    "guessed_data_type": "Unknown",
                    "guessed_source_type": "Unknown",
                    "warnings": [str(exc)],
                }
            )
            messages["warnings"].append(_item(str(exc), "file_permission_denied", path=str(path)))

    if not files:
        messages["warnings"].append(_item("No supported import files were found in this directory.", "no_supported_files", path=str(directory)))
    messages["infos"].append(_item(f"Scanned {len(paths)} files; {len(files)} supported, {len(unsupported_files)} unsupported.", "directory_scanned"))
    return _response(
        True,
        {
            "directory_path": str(directory),
            "files": files,
            "unsupported_files": unsupported_files,
        },
        **messages,
    )


def get_available_curves(dataset_id: str, plot_type: str = "auto", x_unit: str | None = None) -> dict[str, Any]:
    """Return Curve candidates that can be generated from one Dataset."""

    messages = _messages()
    dataset = default_session.datasets.get(dataset_id)
    if dataset is None:
        messages["errors"].append(_item(f"Dataset not found: {dataset_id}", "dataset_not_found", dataset_id=dataset_id))
        return _response(False, {"curves": []}, **messages)
    try:
        curves = _xy_curves_from_dataset(dataset) if _normalize_plot_type(plot_type) == "xy" else curves_from_dataset(dataset, plot_type, x_unit=x_unit)
        report_plan = default_session.report_plans.get(dataset_id) or {}
        default_selected_flags, selection_warnings = _candidate_default_selection(curves)
        curves = _apply_default_curve_styles(curves, default_selected_flags)
        for warning in [*_candidate_set_warnings(curves), *selection_warnings]:
            messages["warnings"].append(_item(warning, "candidate_selection_warning", dataset_id=dataset_id))
        candidate_map: dict[str, Curve] = {}
        summaries: list[dict[str, Any]] = []
        for index, curve in enumerate(curves):
            curve.source_role = infer_curve_source(dataset, curve)
            curve.metadata["source_file"] = str(dataset.path)
            curve.metadata["report_domain"] = (report_plan.get("report_model") or {}).get("report_domain") or report_plan.get("result_domain") or "unknown"
            curve.metadata["family_info"] = _family_info_for_curve(curve, report_plan)
            curve.metadata["compatible_plot_types"] = (report_plan.get("report_model") or {}).get("compatible_plot_types") or report_plan.get("compatible_plot_types") or []
            candidate = default_session.next_curve(curve)
            candidate_id = str(candidate.metadata["curve_id"])
            candidate_map[candidate_id] = candidate
            summaries.append(_enrich_curve_summary(_curve_summary(candidate), candidate, report_plan, default_selected_flags[index] if index < len(default_selected_flags) else False))
            for warning in candidate.warnings:
                messages["warnings"].append(_item(warning, "curve_warning", curve_id=candidate_id))
        default_session.candidates[dataset_id] = candidate_map
        if not summaries:
            report_model = (default_session.report_plans.get(dataset_id) or {}).get("report_model") or {}
            if report_model.get("data_class") == "far_field_grid" or report_model.get("report_type") == "radiation_grid":
                messages["warnings"].append(
                    _item(
                        "Far-field grid data were detected; choose a fixed Theta/Phi cut or use a grid/3D plot workflow before generating ordinary curves.",
                        "far_field_grid_requires_cut",
                        dataset_id=dataset_id,
                    )
                )
            else:
                messages["warnings"].append(_item("No curve candidates were detected for this dataset.", "no_curve_candidates", dataset_id=dataset_id))
        return _response(
            True,
            {
                "dataset_id": dataset_id,
                "plot_type": plot_type,
                "curves": summaries,
                "candidate_count": len(summaries),
                "report_plan": report_plan,
            },
            **messages,
        )
    except Exception as exc:  # noqa: BLE001
        messages["errors"].append(_item(str(exc), "curve_detection_failed", dataset_id=dataset_id))
        return _response(False, {"dataset_id": dataset_id, "curves": []}, **messages)


def create_curves(mapping_config: dict[str, Any]) -> dict[str, Any]:
    """Create active Curve objects from confirmed candidates or manual mappings."""

    messages = _messages()
    dataset_id = str(mapping_config.get("dataset_id", ""))
    dataset = default_session.datasets.get(dataset_id)
    if dataset is None:
        messages["errors"].append(_item(f"Dataset not found: {dataset_id}", "dataset_not_found", dataset_id=dataset_id))
        return _response(False, {"curves": []}, **messages)

    created: list[Curve] = []
    candidate_ids = [str(item) for item in mapping_config.get("candidate_ids", [])]
    candidate_map = default_session.candidates.get(dataset_id, {})
    for candidate_id in candidate_ids:
        candidate = candidate_map.get(candidate_id)
        if candidate is None:
            messages["errors"].append(_item(f"Curve candidate not found: {candidate_id}", "candidate_not_found", candidate_id=candidate_id))
            continue
        created.append(default_session.next_curve(replace(candidate, is_enabled=True)))

    for item in mapping_config.get("candidate_updates", []):
        try:
            candidate_id = str(item["candidate_id"])
            candidate = candidate_map.get(candidate_id)
            if candidate is None:
                messages["errors"].append(_item(f"Curve candidate not found: {candidate_id}", "candidate_not_found", candidate_id=candidate_id))
                continue
            updated = replace(candidate)
            if item.get("label"):
                updated.label = str(item["label"])
            if item.get("source_role"):
                updated.source_role = item["source_role"]
            if item.get("x_unit") and item.get("x_unit") != updated.x_unit:
                manager = CurveManager([updated])
                manager.set_unit_conversion(0, x_unit=item["x_unit"])
                updated = manager.curves[0]
            if "is_normalized" in item and bool(item["is_normalized"]) != updated.is_normalized:
                manager = CurveManager([updated])
                manager.set_normalized(0, bool(item["is_normalized"]))
                updated = manager.curves[0]
            if item.get("is_enabled") is not None:
                updated.is_enabled = bool(item["is_enabled"])
            updated.metadata["source_file"] = str(dataset.path)
            created.append(default_session.next_curve(updated))
        except Exception as exc:  # noqa: BLE001
            messages["errors"].append(_item(str(exc), "candidate_update_failed", candidate=item))

    for mapping in mapping_config.get("mappings", []):
        try:
            normalize_requested = bool(mapping.get("is_normalized", False))
            family_column = str(mapping.get("family_column") or "").strip()
            y_column = str(mapping.get("y_column") or "").strip()
            if y_column in dataset.headers and has_complex_values(dataset, y_column):
                smith_candidates = [
                    curve
                    for curve in curves_from_dataset(dataset, "smith")
                    if curve.metadata.get("complex_column") == y_column or curve.x_column == y_column or curve.y_column == y_column
                ]
                if smith_candidates:
                    smith_curve = smith_candidates[0]
                    if mapping.get("label"):
                        smith_curve.label = str(mapping["label"])
                    smith_curve.source_role = mapping.get("source_role", "Manual")
                    smith_curve.metadata.update(
                        {
                            "source_file": str(dataset.path),
                            "manual_confirmed": bool(mapping.get("manual_confirmed", True)),
                            "manual_config": mapping.get("manual_config", {}),
                            "original_frequency_column": mapping.get("x_column"),
                            "compatible_plot_types": ["Smith Chart"],
                            "report_domain": "complex_network",
                        }
                    )
                    if mapping.get("manual_confirmed", False):
                        smith_curve.warnings.append("Manual mapping confirmed by user; complex S-parameter column was parsed as a Smith Chart trajectory.")
                    created.append(default_session.next_curve(smith_curve))
                    continue
            base_curve = curve_from_columns(
                dataset,
                mapping["x_column"],
                mapping["y_column"],
                x_unit=mapping.get("x_unit"),
                y_unit=mapping.get("y_unit"),
                label=mapping.get("label"),
                normalize_curve=False,
            )
            base_curve.source_role = mapping.get("source_role", "Manual")
            if mapping.get("x_quantity"):
                base_curve.x_quantity = mapping["x_quantity"]
            if mapping.get("y_quantity"):
                base_curve.y_quantity = mapping["y_quantity"]
            if mapping.get("y_unit"):
                base_curve.y_unit = mapping["y_unit"]
            if mapping.get("conversion"):
                base_curve.conversion = mapping["conversion"]

            curves_to_add: list[Curve] = []
            if family_column:
                if family_column not in dataset.headers:
                    messages["warnings"].append(_item(f"Family/group column not found: {family_column}; created one curve without grouping.", "family_column_not_found", dataset_id=dataset_id, family_column=family_column))
                elif family_column in {mapping["x_column"], mapping["y_column"]}:
                    messages["warnings"].append(_item(f"Family/group column {family_column} is also X or Y; created one curve without grouping.", "family_column_invalid", dataset_id=dataset_id, family_column=family_column))
                else:
                    family_values = _ordered_family_values(dataset, family_column)
                    if len(family_values) > 1:
                        for family_value in family_values:
                            mask = _family_mask(dataset, family_column, family_value)
                            if not np.any(mask):
                                continue
                            family_label = _format_family_label(family_column, family_value)
                            user_label = str(mapping.get("label") or "").strip()
                            label = f"{user_label} ({family_label})" if user_label else family_label
                            grouped = replace(
                                base_curve,
                                x_data=base_curve.x_data[mask],
                                y_data=base_curve.y_data[mask],
                                label=label,
                                metadata={
                                    **base_curve.metadata,
                                    "source_file": str(dataset.path),
                                    "manual_confirmed": bool(mapping.get("manual_confirmed", True)),
                                    "manual_config": mapping.get("manual_config", {}),
                                    "family_column": family_column,
                                    "family_info": {family_column: family_value},
                                    "manual_family_grouped": True,
                                },
                            )
                            curves_to_add.append(grouped)
                        messages["infos"].append(_item(f"Manual mapping split by {family_column} into {len(curves_to_add)} curves.", "manual_family_grouped", dataset_id=dataset_id, family_column=family_column, curve_count=len(curves_to_add)))

            if not curves_to_add:
                base_curve.metadata.update(
                    {
                        "source_file": str(dataset.path),
                        "manual_confirmed": bool(mapping.get("manual_confirmed", True)),
                        "manual_config": mapping.get("manual_config", {}),
                    }
                )
                curves_to_add = [base_curve]

            for curve in curves_to_add:
                if normalize_requested:
                    manager = CurveManager([curve])
                    manager.set_normalized(0, True)
                    curve = manager.curves[0]
                if mapping.get("manual_confirmed", False):
                    curve.warnings.append("Manual mapping confirmed by user; engineering conclusions depend on user-provided variable meanings and units.")
                created.append(default_session.next_curve(curve))
        except Exception as exc:  # noqa: BLE001
            messages["errors"].append(_item(str(exc), "mapping_failed", mapping=mapping))

    if created:
        created = _apply_default_curve_styles(created, _style_flags_from_created(created))
        if len(created) > 10:
            messages["warnings"].append(_item("More than 10 curves were created; only the first 10 remain enabled by default. Use the curve manager to filter.", "many_curves_filter_required"))

    summaries: list[dict[str, Any]] = []
    for index, curve in enumerate(created):
        curve.order = len(default_session.curves) + index
        curve_id = str(curve.metadata["curve_id"])
        default_session.curves[curve_id] = curve
        summaries.append(_curve_summary(curve))
        for warning in curve.warnings:
            messages["warnings"].append(_item(warning, "curve_warning", curve_id=curve_id))
    return _response(not messages["errors"], {"curves": summaries}, **messages)


def update_curve(curve_id: str, update_config: dict[str, Any]) -> dict[str, Any]:
    """Update label, enabled state, units, normalization, source role, or order for one Curve."""

    messages = _messages()
    curve = default_session.curves.get(curve_id)
    if curve is None:
        messages["errors"].append(_item(f"Curve not found: {curve_id}", "curve_not_found", curve_id=curve_id))
        return _response(False, {}, **messages)

    manager = CurveManager([curve])
    try:
        if "label" in update_config:
            manager.rename(0, str(update_config["label"]))
        if "is_enabled" in update_config:
            manager.set_enabled(0, bool(update_config["is_enabled"]))
        if "source_role" in update_config:
            manager.set_source(0, update_config["source_role"])
        if "x_unit" in update_config:
            manager.set_unit_conversion(0, x_unit=update_config["x_unit"])
        if "is_normalized" in update_config:
            requested_normalized = bool(update_config["is_normalized"])
            rebuilt = _rebuild_curve_from_dataset(manager.curves[0], normalize_curve=requested_normalized)
            if rebuilt is not None:
                manager.curves[0] = rebuilt
            else:
                manager.set_normalized(0, requested_normalized)
        updated = apply_sampling_policy(manager.curves[0])
        style_keys = {
            "line_width",
            "line_style",
            "color",
            "marker_enabled",
            "marker",
            "marker_style",
            "marker_size",
            "marker_every",
            "alpha",
            "sample_display_policy",
            "participate_metrics",
        }
        coerced_updates = _coerce_curve_style_updates(update_config)
        style_updates = {key: coerced_updates[key] for key in style_keys if key in coerced_updates}
        if style_updates:
            updated = replace(updated, metadata={**updated.metadata, **style_updates})
        if "order" in update_config:
            updated.order = int(update_config["order"])
        default_session.curves[curve_id] = replace(updated, metadata={**updated.metadata, "curve_id": curve_id})
        for warning in default_session.curves[curve_id].warnings:
            messages["warnings"].append(_item(warning, "curve_warning", curve_id=curve_id))
        return _response(True, {"curve": _curve_summary(default_session.curves[curve_id])}, **messages)
    except Exception as exc:  # noqa: BLE001
        messages["errors"].append(_item(str(exc), "curve_update_failed", curve_id=curve_id))
        return _response(False, {"curve": _curve_summary(curve)}, **messages)


def delete_curve(curve_id: str) -> dict[str, Any]:
    """Delete one active Curve from backend state."""

    messages = _messages()
    curve = default_session.curves.pop(curve_id, None)
    if curve is None:
        messages["errors"].append(_item(f"Curve not found: {curve_id}", "curve_not_found", curve_id=curve_id))
        return _response(False, {}, **messages)
    messages["infos"].append(_item("Curve deleted.", "curve_deleted", curve_id=curve_id))
    return _response(True, {"curve_id": curve_id}, **messages)


def _normalize_plot_type(plot_type: str) -> str:
    text = str(plot_type or "auto").lower().replace("_", " ").replace("-", " ")
    if "return" in text or "s11" in text:
        return "s11"
    if "radiation" in text or "pattern" in text:
        return "pattern"
    if "realized" in text or text.strip() == "gain":
        return "gain"
    if "vswr" in text or "vsmr" in text:
        return "vswr"
    if "axial" in text or text.strip() in {"ar", "axialratio"}:
        return "ar"
    if "eff" in text:
        return "efficiency"
    if "hpbw" in text or "beamwidth" in text:
        return "hpbw"
    if "smith" in text:
        return "smith"
    if text.strip() in {"xy", "xymulticurve", "xy multi curve", "multi curve"}:
        return "xy"
    return text.strip() or "auto"


def _curve_text(curve: Curve) -> str:
    return " ".join(
        [
            curve.label,
            curve.x_column,
            curve.y_column,
            curve.x_quantity,
            curve.y_quantity,
            curve.x_unit,
            curve.y_unit,
            str(curve.conversion or ""),
            " ".join(str(value) for value in curve.metadata.values()),
        ]
    ).lower()


def _is_angle_curve(curve: Curve) -> bool:
    return curve.x_quantity in {"theta", "phi", "angle"} or curve.x_unit == "deg"


def _is_frequency_curve(curve: Curve) -> bool:
    return curve.x_quantity == "frequency" and curve.x_unit in {"Hz", "MHz", "GHz"}


def _is_s11_like(curve: Curve) -> bool:
    text = _curve_text(curve)
    return curve.y_quantity == "S11" or "s11" in text or "s(1,1)" in text or "returnloss" in text or "return loss" in text


def _is_vswr_like(curve: Curve) -> bool:
    text = _curve_text(curve)
    return curve.y_quantity == "VSWR" or "vswr" in text or "vsmr" in text


def _is_gain_like(curve: Curve) -> bool:
    text = _curve_text(curve)
    return (
        curve.y_quantity in {"Gain", "RealizedGain"}
        or "realizedgain" in text
        or "gaintotal" in text
        or "directivity" in text
        or "rhcp" in text
        or "lhcp" in text
        or "co-pol" in text
        or "copol" in text
        or "cross" in text
    )


def _is_realized_gain_freq_like(curve: Curve) -> bool:
    text = _curve_text(curve)
    return _is_frequency_curve(curve) and (
        curve.y_quantity in {"Gain", "RealizedGain"}
        or "realizedgain" in text
        or "gaintotal" in text
        or "directivity" in text
    )


def _is_axial_ratio_like(curve: Curve) -> bool:
    text = _curve_text(curve)
    return curve.y_quantity == "AR" or "axialratio" in text or "axial ratio" in text


def _is_efficiency_like(curve: Curve) -> bool:
    text = _curve_text(curve)
    return curve.y_quantity == "Efficiency" or "efficiency" in text or "antennaefficiency" in text


def _is_hpbw_like(curve: Curve) -> bool:
    text = _curve_text(curve)
    return "hpbw" in text or "beamwidth" in text or "halfpower" in text


def _is_complex_network_like(curve: Curve) -> bool:
    text = _curve_text(curve)
    if curve.metadata.get("smith_chart") or curve.metadata.get("complex_network"):
        return True
    compatible = " ".join(str(item).lower() for item in curve.metadata.get("compatible_plot_types", []))
    if "smith" in compatible:
        return True
    return any(token in text for token in ["re(s", "im(s", "mag(s", "phase(s", "re(z", "im(z", "zin", "yin", "complex s11", "complexs", "s(1,1)"])


def _plot_validation_error(messages: dict[str, list[dict[str, Any]]], curve: Curve, message: str, suggestion: str) -> None:
    messages["errors"].append(
        _item(
            message,
            "plot_curve_incompatible",
            curve_id=curve.metadata.get("curve_id"),
            label=curve.label,
            suggested_action=suggestion,
        )
    )


def validate_plot(
    plot_type: str,
    curves: list[str | Curve | dict[str, Any]],
    project_settings: dict[str, Any] | None = None,
    plot_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate whether selected curves are compatible with a plot type."""

    messages = _messages()
    selected, selection_errors = _selected_curves(curves)
    messages["errors"].extend(selection_errors)
    if selection_errors:
        return _response(False, {"allowed": False}, **messages)
    if not selected:
        messages["errors"].append(_item("No curves selected.", "no_curves_selected"))
        return _response(False, {"allowed": False}, **messages)

    normalized_plot_type = _normalize_plot_type(plot_type)
    plot_settings = plot_settings or {}
    plot_text = str(plot_type or "").lower()
    suggested_plot_type: str | None = None
    suggested_axis: dict[str, str] | None = None
    if normalized_plot_type == "xy":
        messages["infos"].append(_item("XY Multi-Curve uses ordinary X/Y data only; engineering compatibility and pass/fail checks are skipped.", "xy_validation_basic"))
        return _response(
            True,
            {
                "allowed": True,
                "plot_type": plot_type,
                "normalized_plot_type": normalized_plot_type,
                "curve_ids": [curve.metadata.get("curve_id") for curve in selected],
                "suggested_plot_type": None,
                "suggested_axis": None,
                "plot_settings": plot_settings,
            },
            **messages,
        )
    for curve in selected:
        if normalized_plot_type == "s11":
            if not (_is_frequency_curve(curve) and _is_s11_like(curve)):
                if _is_angle_curve(curve) and _is_gain_like(curve):
                    suggested_plot_type = "pattern"
                    suggested_axis = {"xlabel": "Angle (deg)", "ylabel": "Realized Gain (dBi)"}
                    _plot_validation_error(
                        messages,
                        curve,
                        f"Curve {curve.label} is angular radiation-pattern data, not Freq + S11/ReturnLoss.",
                        "Switch plot type to Radiation Pattern.",
                    )
                else:
                    _plot_validation_error(
                        messages,
                        curve,
                        f"Curve {curve.label} is not compatible with S11 / Return Loss. Expected Freq + S11/ReturnLoss.",
                        "Select an S11 curve or switch to the matching plot type.",
                    )
            elif curve.y_unit != "dB":
                messages["warnings"].append(_item(f"Curve {curve.label} is S11-like but y_unit={curve.y_unit}; S11/Return Loss plots expect dB.", "s11_unit_warning", curve_id=curve.metadata.get("curve_id")))
        if normalized_plot_type == "vswr":
            if not (_is_frequency_curve(curve) and (_is_vswr_like(curve) or _is_s11_like(curve))):
                _plot_validation_error(
                    messages,
                    curve,
                    f"Curve {curve.label} is not compatible with VSWR. Expected Freq + VSWR or Freq + S11 convertible to VSWR.",
                    "Use a VSWR/S11 frequency-response curve.",
                )
            elif _is_s11_like(curve) and not _is_vswr_like(curve):
                messages["warnings"].append(_item(f"Curve {curve.label} is S11-like; VSWR is derived from S11 and must be reported.", "vswr_from_s11_requires_conversion", curve_id=curve.metadata.get("curve_id")))
        if normalized_plot_type in {"gain", "realizedgain"}:
            if _is_angle_curve(curve) and _is_gain_like(curve):
                suggested_plot_type = "pattern"
                suggested_axis = {"xlabel": "Angle (deg)", "ylabel": "Realized Gain (dBi)"}
                _plot_validation_error(
                    messages,
                    curve,
                    f"Curve {curve.label} uses an angle axis; this is radiation-pattern data, not Realized Gain versus frequency.",
                    "Switch plot type to Radiation Pattern.",
                )
            elif not _is_realized_gain_freq_like(curve):
                _plot_validation_error(
                    messages,
                    curve,
                    f"Curve {curve.label} is not compatible with Realized Gain. Expected Freq + RealizedGain/GainTotal/Directivity.",
                    "Use a gain frequency-response curve or switch plot type.",
                )
        if normalized_plot_type == "pattern":
            if curve.x_quantity not in {"theta", "phi", "angle"}:
                _plot_validation_error(
                    messages,
                    curve,
                    f"Curve {curve.label} does not use Theta/Phi/Angle for Radiation Pattern.",
                    "Select an angular radiation-pattern curve.",
                )
            if _is_axial_ratio_like(curve):
                _plot_validation_error(
                    messages,
                    curve,
                    f"Curve {curve.label} is Axial Ratio data, not a radiation gain/polarization pattern.",
                    "Switch plot type to Axial Ratio.",
                )
            elif not _is_gain_like(curve):
                _plot_validation_error(
                    messages,
                    curve,
                    f"Curve {curve.label} is not Gain/RealizedGain/NormalizedGain/RHCP/LHCP/Co-pol/Cross-pol angular data.",
                    "Select a radiation-pattern quantity.",
                )
            if curve.metadata.get("cut_type") == "2d_farfield_grid":
                _plot_validation_error(
                    messages,
                    curve,
                    f"Curve {curve.label} comes from a Theta/Phi far-field grid.",
                    "Choose a fixed Theta/Phi cut before plotting an ordinary Radiation Pattern.",
                )
            elif curve.metadata.get("cut_type") == "cut_family":
                messages["infos"].append(_item(f"Curve {curve.label} is a selected cut from a Theta/Phi family.", "radiation_cut_family", curve_id=curve.metadata.get("curve_id")))
        if normalized_plot_type == "ar":
            if not ((_is_frequency_curve(curve) or _is_angle_curve(curve)) and _is_axial_ratio_like(curve)):
                _plot_validation_error(
                    messages,
                    curve,
                    f"Curve {curve.label} is not compatible with Axial Ratio.",
                    "Use Freq + AxialRatio, or Angle/Theta/Phi + AxialRatio for an axial-ratio pattern.",
                )
            elif _is_angle_curve(curve):
                messages["warnings"].append(_item(f"Curve {curve.label} is an axial-ratio pattern, not frequency-response AR.", "axial_ratio_pattern", curve_id=curve.metadata.get("curve_id")))
        if normalized_plot_type == "efficiency":
            if not (_is_frequency_curve(curve) and _is_efficiency_like(curve)):
                _plot_validation_error(
                    messages,
                    curve,
                    f"Curve {curve.label} is not compatible with Efficiency. Expected Freq + RadiationEfficiency/TotalEfficiency/AntennaEfficiency.",
                    "Use an efficiency frequency-response curve.",
                )
            elif curve.metadata.get("efficiency_unit_note"):
                messages["warnings"].append(_item(f"Curve {curve.label} efficiency unit is marked as {curve.metadata.get('efficiency_unit_note')}; confirm/normalize units before overlay.", "efficiency_unit_confirmation", curve_id=curve.metadata.get("curve_id")))
        if normalized_plot_type == "hpbw":
            if not ((_is_frequency_curve(curve) and _is_hpbw_like(curve)) or (_is_angle_curve(curve) and _is_gain_like(curve))):
                _plot_validation_error(
                    messages,
                    curve,
                    f"Curve {curve.label} is not compatible with HPBW.",
                    "Use Freq + HPBW, or derive HPBW from a radiation pattern after selecting a cut.",
                )
            elif _is_angle_curve(curve):
                messages["warnings"].append(_item(f"Curve {curve.label} is radiation-pattern data; HPBW is a derived metric, not a direct curve plot.", "hpbw_derived_from_pattern", curve_id=curve.metadata.get("curve_id")))
        if normalized_plot_type == "smith":
            if not _is_complex_network_like(curve):
                _plot_validation_error(
                    messages,
                    curve,
                    f"Curve {curve.label} is not compatible with Smith Chart. Expected re/im(S11), mag/phase(S11), re/im(Zin), or re/im(Yin).",
                    "Select complex network data for Smith Chart.",
                )

    if normalized_plot_type == "s11":
        if "return" in plot_text:
            messages["infos"].append(_item("Return Loss mode should use a +10 dB threshold; S11(dB) mode uses -10 dB. Confirm sign convention before conclusions.", "return_loss_threshold_convention"))
        else:
            messages["infos"].append(_item("S11 mode threshold is -10 dB by default.", "s11_threshold_convention"))
    if normalized_plot_type == "vswr":
        has_direct_vswr = any(_is_vswr_like(curve) for curve in selected)
        has_s11_source = any(_is_s11_like(curve) and not _is_vswr_like(curve) for curve in selected)
        if has_direct_vswr and has_s11_source:
            messages["warnings"].append(_item("Both direct VSWR and S11-derived VSWR are selected; direct VSWR columns should be preferred unless the user explicitly selects derivation.", "vswr_direct_preferred"))
    if normalized_plot_type == "pattern":
        cut_descriptions = []
        for curve in selected:
            cut_descriptions.append(str(curve.metadata.get("cut") or curve.metadata.get("cut_type") or curve.x_quantity))
        if len(set(cut_descriptions)) > 1:
            messages["warnings"].append(_item("Multiple radiation-pattern cuts are selected. Legend/report must explicitly identify each cut; do not automatically call them E/H plane unless confirmed.", "pattern_mixed_cut_warning", cuts=cut_descriptions))
        messages["infos"].append(_item("Polar Pattern uses one shared radial range for all enabled curves.", "polar_shared_radial_range"))
    if normalized_plot_type == "efficiency":
        names = " ".join(curve.y_column.lower() for curve in selected)
        if "radiation" in names and "total" in names:
            messages["infos"].append(_item("Radiation Efficiency and Total Efficiency are both selected; legend labels must remain explicit.", "efficiency_type_labels"))
    if normalized_plot_type == "hpbw" and any(_is_angle_curve(curve) for curve in selected):
        messages["warnings"].append(_item("HPBW derived from radiation-pattern curves is only reliable when angular sampling covers the beam and 3 dB crossings.", "hpbw_direction_pattern_requirements"))
    if normalized_plot_type == "smith":
        z0_values = {curve.metadata.get("z0_ohm") for curve in selected if curve.metadata.get("z0_ohm") is not None}
        if len(z0_values) > 1:
            messages["errors"].append(_item(f"Smith Chart curves use inconsistent Z0 values: {sorted(z0_values)}.", "smith_z0_mismatch"))
        if len(selected) > 3:
            messages["warnings"].append(_item("More than 3 Smith Chart traces are selected; the chart may be crowded. Consider filtering curves.", "smith_trace_crowding"))

    manager = CurveManager(sorted(selected, key=lambda item: item.order))
    if not messages["errors"]:
        validation = manager.validate_overlay(normalized_plot_type)
        messages["errors"].extend(_item(item, "overlay_incompatible") for item in validation.errors)
        messages["warnings"].extend(_item(item, "overlay_warning") for item in validation.warnings)
        messages["infos"].extend(_item(item, "interpolation_info") for item in validation.interpolation_notes or [])
    else:
        messages["warnings"].append(_item("Preview/export is blocked; previous axis labels should not be reused for this incompatible plot type.", "axis_labels_invalidated"))
    settings = _settings_from_payload(project_settings)
    if settings.working_band_mhz is None:
        messages["infos"].append(_item("No working band is set; pass/fail bandwidth judgment will be skipped.", "working_band_not_set"))
    return _response(
        not messages["errors"],
        {
            "allowed": not messages["errors"],
            "plot_type": plot_type,
            "normalized_plot_type": normalized_plot_type,
            "curve_ids": [curve.metadata.get("curve_id") for curve in selected],
            "suggested_plot_type": suggested_plot_type,
            "suggested_axis": suggested_axis,
            "plot_settings": plot_settings,
        },
        **messages,
    )


def _render_plot(config: dict[str, Any], *, export: bool) -> dict[str, Any]:
    messages = _messages()
    curve_ids = config.get("curve_ids") or config.get("curves") or []
    selected, selection_errors = _selected_curves(curve_ids)
    messages["errors"].extend(selection_errors)
    if selection_errors or not selected:
        if not selected:
            messages["errors"].append(_item("No curves selected.", "no_curves_selected"))
        return _response(False, {}, **messages)

    skip_engineering_metrics = bool(config.get("skip_engineering_metrics", False))
    settings = _settings_from_payload(config.get("project_settings"))
    validation = validate_plot(
        config.get("plot_type", "s11"),
        [curve.metadata["curve_id"] for curve in selected],
        config.get("project_settings"),
        config.get("plot_settings") or config,
    )
    if validation["errors"]:
        return validation

    output_dir = Path(config.get("output_dir") or (DEFAULT_EXPORT_DIR if export else DEFAULT_PREVIEW_DIR))
    output_dir = output_dir / str(int(time.time() * 1000)) if not config.get("output_dir") else output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    formats = config.get("formats") or (["png", "pdf", "svg", "json", "txt", "md"] if export else ["png"])
    style = _style_from_config(config.get("style"), formats, config.get("dpi"))
    args = _namespace(config, settings, export=export)
    if skip_engineering_metrics:
        args.project_settings = None
    manager = CurveManager(sorted(selected, key=lambda item: item.order))
    try:
        outputs = plot_overlay(manager, output_dir, style, args)
        metric_results = [] if skip_engineering_metrics else metric_results_for_curves(metric_enabled_curves(manager.enabled_curves()), settings)
        metrics_report = _xy_basic_report(manager.enabled_curves()) if skip_engineering_metrics else format_metric_results(metric_results)
        requested_formats = {str(item).lower() for item in style["export"].get("requested_formats", [])}
        if export and ({"md", "markdown"} & requested_formats):
            md_path = output_dir / f"{args.output_name}_metrics_report.md"
            md_path.write_text("# Engineering Metrics Report\n\n```text\n" + metrics_report + "\n```\n", encoding="utf-8")
            outputs.append(md_path)
        png = next((path for path in outputs if path.suffix.lower() == ".png"), None)
        data = {
            "preview_path": str(png) if png else None,
            "outputs": [str(path) for path in outputs],
            "metrics": [jsonable(result) for result in metric_results],
            "metrics_report": metrics_report,
            "plot_type": config.get("plot_type", "s11"),
            "curve_ids": [curve.metadata.get("curve_id") for curve in manager.enabled_curves()],
        }
        messages["infos"].append(_item("Plot generated by backend Python plotting logic.", "backend_rendered"))
        return _response(True, data, **messages)
    except Exception as exc:  # noqa: BLE001
        messages["errors"].append(_item(str(exc), "plot_render_failed"))
        return _response(False, {}, **messages)


def generate_preview(plot_config: dict[str, Any]) -> dict[str, Any]:
    """Generate a temporary backend-rendered preview image."""

    return _render_plot(plot_config, export=False)


def export_plot(export_config: dict[str, Any]) -> dict[str, Any]:
    """Export final plot images, JSON configuration, and engineering reports."""

    return _render_plot(export_config, export=True)


def _project_settings_to_payload(config: dict[str, Any]) -> dict[str, Any]:
    settings = config.get("project_settings") or {}
    if not settings:
        settings = {}
    if not settings.get("working_band_mhz") and config.get("target_band"):
        settings["working_band_mhz"] = config.get("target_band")
    threshold = (config.get("threshold_conditions") or {}).get("threshold")
    if threshold is not None and settings.get("s11_threshold_db") is None:
        settings["s11_threshold_db"] = threshold
    return settings


def _restore_curve_from_config(dataset: HfssDataset, curve_config: dict[str, Any], plot_type: str) -> Curve:
    candidates = curves_from_dataset(dataset, plot_type, x_unit=curve_config.get("x_unit"))
    x_column = curve_config.get("x_column")
    y_column = curve_config.get("y_column")
    conversion = curve_config.get("conversion")
    matched = next(
        (
            curve
            for curve in candidates
            if curve.x_column == x_column
            and curve.y_column == y_column
            and (conversion is None or curve.conversion == conversion or curve.conversion is not None)
        ),
        None,
    )
    if matched is None:
        matched = curve_from_columns(
            dataset,
            x_column,
            y_column,
            x_unit=curve_config.get("x_unit"),
            y_unit=curve_config.get("y_unit"),
            label=curve_config.get("label"),
            normalize_curve=False,
        )
    restored = replace(matched)
    restored.label = curve_config.get("label") or restored.label
    restored.is_enabled = bool(curve_config.get("is_enabled", True))
    restored.source_role = curve_config.get("source_role", "Unknown")
    restored.order = int(curve_config.get("order", 0) or 0)
    restored.x_quantity = curve_config.get("x_quantity") or restored.x_quantity
    restored.y_quantity = curve_config.get("y_quantity") or restored.y_quantity
    restored.x_unit = curve_config.get("x_unit") or restored.x_unit
    restored.y_unit = curve_config.get("y_unit") or restored.y_unit
    if curve_config.get("conversion") and not restored.conversion:
        restored.conversion = curve_config.get("conversion")
    restored.metadata.update(curve_config.get("metadata") or {})
    restored.metadata["source_file"] = str(dataset.path)
    if curve_config.get("is_normalized") and not restored.is_normalized:
        manager = CurveManager([restored])
        manager.set_normalized(0, True)
        restored = manager.curves[0]
    restored.warnings.extend(item for item in curve_config.get("warnings", []) if item not in restored.warnings)
    return restored


def restore_project(json_config: dict[str, Any] | str | Path) -> dict[str, Any]:
    """Restore project state from an exported plot configuration JSON."""

    messages = _messages()
    if isinstance(json_config, (str, Path)):
        path = Path(json_config)
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            messages["errors"].append(_item(str(exc), "restore_json_read_failed", path=str(path)))
            return _response(False, {}, **messages)
    else:
        config = dict(json_config)

    default_session.clear()
    plot_type = config.get("plot_type", "s11")
    curve_configs = config.get("curves") or []
    source_paths = [Path(path) for path in config.get("input_file_path", []) if path]
    for curve_config in curve_configs:
        source_file = (curve_config.get("metadata") or {}).get("source_file")
        if source_file:
            source_paths.append(Path(source_file))
    unique_paths: list[Path] = []
    seen: set[str] = set()
    for path in source_paths:
        key = str(path)
        if key not in seen:
            unique_paths.append(path)
            seen.add(key)

    datasets_by_id: dict[str, HfssDataset] = {}
    for path in unique_paths:
        if not path.exists():
            messages["warnings"].append(
                _item(
                    "Configuration was read, but one original data source could not be reloaded. Deterministic engineering conclusions are disabled unless curve data cache is available.",
                    "source_file_missing",
                    path=str(path),
                )
            )
            continue
        try:
            dataset = read_hfss_csv(path)
            dataset_id = dataset.to_model().dataset_id or ""
            report_plan = plan_report_from_dataset(dataset, "semiauto").to_dict()
            default_session.datasets[dataset_id] = dataset
            default_session.recognitions[dataset_id] = recognition_from_dataset(dataset, "semiauto")
            default_session.report_plans[dataset_id] = report_plan
            datasets_by_id[dataset_id] = dataset
        except Exception as exc:  # noqa: BLE001
            messages["warnings"].append(_item(str(exc), "source_reload_failed", path=str(path)))

    restored_curves: list[Curve] = []
    for curve_config in curve_configs:
        dataset = datasets_by_id.get(str(curve_config.get("dataset_id")))
        source_file = (curve_config.get("metadata") or {}).get("source_file")
        if dataset is None and source_file:
            dataset = next((item for item in datasets_by_id.values() if str(item.path) == str(source_file)), None)
        if dataset is None:
            messages["warnings"].append(
                _item(
                    "Curve could not be restored because its source dataset is unavailable.",
                    "curve_source_unavailable",
                    curve=curve_config.get("label"),
                )
            )
            continue
        try:
            curve = _restore_curve_from_config(dataset, curve_config, plot_type)
            curve = default_session.next_curve(curve)
            curve_id = str(curve.metadata["curve_id"])
            default_session.curves[curve_id] = curve
            restored_curves.append(curve)
        except Exception as exc:  # noqa: BLE001
            messages["warnings"].append(_item(str(exc), "curve_restore_failed", curve=curve_config.get("label")))

    dataset_summaries = []
    for dataset in default_session.datasets.values():
        summary = _dataset_summary(dataset)
        dataset_id = str(summary["dataset_id"])
        if dataset_id in default_session.report_plans:
            summary["metadata"]["report_plan"] = default_session.report_plans[dataset_id]
            summary["metadata"]["report_model"] = default_session.report_plans[dataset_id].get("report_model")
        dataset_summaries.append(summary)
    recognition_summaries = [
        {
            "dataset_id": dataset_id,
            **_recognition_summary(recognition),
            "report_plan": default_session.report_plans.get(dataset_id),
            "report_model": (default_session.report_plans.get(dataset_id) or {}).get("report_model"),
        }
        for dataset_id, recognition in default_session.recognitions.items()
    ]
    if messages["warnings"]:
        messages["infos"].append(_item("Project restored with warnings; review data sources before drawing conclusions.", "restore_with_warnings"))
    else:
        messages["infos"].append(_item("Project restored from JSON configuration.", "restore_complete"))
    return _response(
        True,
        {
            "datasets": dataset_summaries,
            "recognitions": recognition_summaries,
            "curves": [_curve_summary(curve) for curve in sorted(restored_curves, key=lambda item: item.order)],
            "plot_config": {
                "plot_type": plot_type,
                "display_mode": config.get("display_mode") or config.get("pattern_display_mode"),
                "pattern_display_mode": config.get("pattern_display_mode") or config.get("display_mode"),
                "polar_config": config.get("polar_config"),
                "axis_range": config.get("axis_range"),
                "threshold_conditions": config.get("threshold_conditions"),
                "target_band": config.get("target_band"),
            },
            "project_settings": _project_settings_to_payload(config),
            "export_config": {
                "formats": config.get("export_formats"),
                "scope": config.get("export_scope"),
                "manual_config": config.get("manual_config"),
                "style": config.get("style"),
            },
            "messages": config.get("messages", []),
        },
        **messages,
    )


def import_plot_config(json_path: str | Path) -> dict[str, Any]:
    """Restore project state from an exported plot config file."""

    return restore_project(Path(json_path))


def dispatch(action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Dispatch a stable API action by name for HTTP or plugin callers."""

    payload = payload or {}
    token = _session_context.set(_session_for(str(payload.get("session_id") or payload.get("sessionId") or "")))
    try:
        return _dispatch_in_session(action, payload)
    finally:
        _session_context.reset(token)


def _dispatch_in_session(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    if action == "scan_directory":
        return scan_directory(
            payload.get("directory_path") or payload.get("path") or "",
            recursive=bool(payload.get("recursive", False)),
            file_types=payload.get("file_types"),
        )
    if action == "import_files":
        return import_files(
            payload.get("files", []),
            mode=payload.get("mode", "semiauto"),
            parse_options=payload.get("parse_options") or payload.get("parseConfig"),
        )
    if action == "get_available_curves":
        return get_available_curves(payload["dataset_id"], payload.get("plot_type", "auto"), payload.get("x_unit"))
    if action == "create_curves":
        return create_curves(payload)
    if action == "update_curve":
        return update_curve(payload["curve_id"], payload.get("update_config", {}))
    if action == "delete_curve":
        return delete_curve(payload["curve_id"])
    if action == "validate_plot":
        return validate_plot(payload.get("plot_type", "s11"), payload.get("curves", []), payload.get("project_settings"), payload.get("plot_settings"))
    if action == "generate_preview":
        return generate_preview(payload)
    if action == "export_plot":
        return export_plot(payload)
    if action == "restore_project":
        return restore_project(payload.get("json_config") or payload.get("config") or payload.get("config_path") or payload)
    if action == "import_plot_config":
        return import_plot_config(payload.get("json_path") or payload.get("config_path"))
    return _response(False, {}, errors=[_item(f"Unknown API action: {action}", "unknown_action", action=action)], warnings=[], infos=[])
