"""Export JSON configurations and text/Markdown engineering reports."""

from __future__ import annotations

import json
from argparse import Namespace
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .models import Curve
from .messages import Message
from .project_settings import ProjectSettings
from .reader import HfssDataset


IMAGE_FORMATS = {"png", "pdf", "svg"}
CONFIG_FORMATS = {"json"}
REPORT_FORMATS = {"txt", "md", "markdown"}


def split_export_formats(formats: list[str] | None) -> tuple[list[str], list[str]]:
    requested = [str(item).lower().lstrip(".") for item in (formats or ["png", "pdf", "svg"])]
    image_formats = [item for item in requested if item in IMAGE_FORMATS]
    if not image_formats:
        image_formats = ["png"]
    return image_formats, requested


def jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if is_dataclass(value):
        return jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(item) for item in value]
    return value


def curve_summary(curve: Curve) -> dict[str, Any]:
    sample_count = int(curve.metadata.get("sample_count", min(len(curve.x_data), len(curve.y_data))))
    return {
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
        "order": curve.order,
        "sample_count": sample_count,
        "point_count": sample_count,
        "raw_sample_count": curve.metadata.get("raw_sample_count", sample_count),
        "unique_x_count": curve.metadata.get("unique_x_count"),
        "displayed_sample_count": curve.metadata.get("displayed_sample_count", sample_count),
        "duplicate_x_count_after_grouping": curve.metadata.get("duplicate_x_count_after_grouping", curve.metadata.get("duplicate_x_count", 0)),
        "sample_display_policy": curve.metadata.get("sample_display_policy", "marker_only_decimate"),
        "line_width": curve.metadata.get("line_width"),
        "line_style": curve.metadata.get("line_style"),
        "color": curve.metadata.get("color"),
        "marker_enabled": curve.metadata.get("marker_enabled"),
        "marker": curve.metadata.get("marker"),
        "marker_size": curve.metadata.get("marker_size"),
        "marker_every": curve.metadata.get("marker_every"),
        "alpha": curve.metadata.get("alpha"),
        "metadata": curve.metadata,
        "warnings": curve.warnings,
    }


def args_mapping(args: Namespace) -> dict[str, Any]:
    return {
        "x_column": getattr(args, "x_column", None),
        "y_column": getattr(args, "y_column", None),
        "y_columns": getattr(args, "y_columns", None),
        "theta_column": getattr(args, "theta_column", None),
        "phi_column": getattr(args, "phi_column", None),
        "gain_column": getattr(args, "gain_column", None),
        "gain_columns": getattr(args, "gain_columns", None),
        "real_column": getattr(args, "real_column", None),
        "imag_column": getattr(args, "imag_column", None),
        "x_unit": getattr(args, "x_unit", None),
        "label": getattr(args, "label", None),
        "labels": getattr(args, "labels", None),
        "is_normalized": not bool(getattr(args, "absolute", True)) if getattr(args, "command", "") == "pattern" else None,
    }


def axis_config(args: Namespace) -> dict[str, Any]:
    return {
        "xlabel": getattr(args, "xlabel", None),
        "ylabel": getattr(args, "ylabel", None),
        "xlim": getattr(args, "xlim", None),
        "ylim": getattr(args, "ylim", None),
        "legend_loc": getattr(args, "legend_loc", None),
    }


def threshold_config(args: Namespace, settings: ProjectSettings | None) -> dict[str, Any]:
    return {
        "s11_threshold_db": getattr(args, "threshold", None) if getattr(args, "command", "") == "s11" else (settings.s11_threshold_db if settings else None),
        "vswr_threshold": getattr(args, "vswr_threshold", None) or (settings.vswr_threshold if settings else None),
        "axial_ratio_threshold_db": getattr(args, "ar_threshold", None) or (settings.axial_ratio_threshold_db if settings else None),
        "min_gain_dbi": settings.min_gain_dbi if settings else None,
    }


def build_plot_config(
    dataset: HfssDataset,
    command: str,
    args: Namespace,
    style: dict,
    requested_formats: list[str],
    settings: ProjectSettings | None,
    recognition: Any | None = None,
    curves: list[Curve] | None = None,
    messages: list[Message] | None = None,
) -> dict[str, Any]:
    model = dataset.to_model()
    config = {
        "input_file_path": str(dataset.path),
        "dataset": {
            "dataset_id": model.dataset_id,
            "source_file": model.source_file,
            "source_type": model.source_type,
            "file_format": model.file_format,
            "data_type": model.data_type,
            "columns": model.columns,
            "units": model.units,
            "row_count": model.row_count,
            "warnings": model.warnings,
            "metadata": model.metadata,
        },
        "plot_type": command,
        "variable_mapping": args_mapping(args),
        "unit_conversion": {
            "x_unit": getattr(args, "x_unit", None),
            "curve_conversions": [curve.conversion for curve in curves or [] if curve.conversion],
        },
        "curve_labels": [curve.label for curve in curves or []] or [getattr(args, "label", None)],
        "normalization": {
            "curves": [{"label": curve.label, "is_normalized": curve.is_normalized} for curve in curves or []],
            "pattern_absolute": getattr(args, "absolute", None),
        },
        "interpolation_state": {
            "plotting_interpolation": "none unless sample_step/smoothing is explicitly requested",
            "sample_step": getattr(args, "sample_step", None),
            "smooth": bool(getattr(args, "smooth", False)),
        },
        "axis_range": axis_config(args),
        "target_band": settings.working_band_mhz if settings else None,
        "threshold_conditions": threshold_config(args, settings),
        "export_formats": requested_formats,
        "style": {
            "font": style.get("font", {}),
            "line": style.get("line", {}),
            "axis": style.get("axis", {}),
            "figure": style.get("figure", {}),
        },
        "recognition": recognition,
        "messages": [message.__dict__ for message in messages or []],
        "has_errors": any(message.severity == "error" for message in messages or []),
        "has_warnings": any(message.severity == "warning" for message in messages or []),
    }
    return jsonable(config)


def write_json_config(output_dir: Path, output_base: str, config: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{output_base}_plot_config.json"
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_reports(output_dir: Path, output_base: str, report_text: str, requested_formats: list[str]) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    requested = set(requested_formats)
    if "txt" in requested or not requested.intersection(REPORT_FORMATS):
        txt = output_dir / f"{output_base}_metrics_report.txt"
        txt.write_text(report_text + "\n", encoding="utf-8")
        outputs.append(txt)
    if "md" in requested or "markdown" in requested:
        md = output_dir / f"{output_base}_metrics_report.md"
        md.write_text("# Engineering Metrics Report\n\n```text\n" + report_text + "\n```\n", encoding="utf-8")
        outputs.append(md)
    return outputs


def write_export_artifacts(
    output_dir: Path,
    output_base: str,
    dataset: HfssDataset,
    command: str,
    args: Namespace,
    style: dict,
    requested_formats: list[str],
    settings: ProjectSettings | None,
    report_text: str,
    recognition: Any | None = None,
    curves: list[Curve] | None = None,
    messages: list[Message] | None = None,
) -> list[Path]:
    outputs: list[Path] = []
    if "json" in set(requested_formats):
        config = build_plot_config(dataset, command, args, style, requested_formats, settings, recognition, curves, messages)
        outputs.append(write_json_config(output_dir, output_base, config))
    outputs.extend(write_reports(output_dir, output_base, report_text, requested_formats))
    return outputs
