"""Curve management and multi-dataset overlay plotting."""

from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass, replace
from pathlib import Path
import re
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .models import Curve, CurveSource
from .engineering_metrics import format_metric_results, metric_results_for_curves
from .export_artifacts import curve_summary, jsonable, write_json_config
from .messages import Message, format_messages
from .pattern_analysis import pattern_curves_from_dataset
from .plotting import apply_limits_labels, curve_style, draw_frequency_band, draw_smith_grid, grid, plot_curve, save_figure
from .reader import HfssDataset, auto_curves_from_hfss, clean_complex, complex_s_column, curve_from_columns, csv_files, read_hfss_csv, smith_imag_column, smith_real_column, normalize
from .reader import axial_ratio_column, detect_kind, efficiency_column, frequency_column, is_numeric_column, theta_column, phi_column, angle_column, vswr_column
from .s11_import import s11_curves_from_dataset
from .style import apply_style, figure_size


FREQUENCY_FACTORS_TO_HZ = {
    "Hz": 1.0,
    "MHz": 1.0e6,
    "GHz": 1.0e9,
}


@dataclass
class OverlayValidationResult:
    allowed: bool
    errors: list[str]
    warnings: list[str]
    interpolation_required: bool = False
    interpolation_notes: list[str] | None = None

    def report_lines(self) -> list[str]:
        lines = [f"Overlay allowed: {self.allowed}"]
        if self.errors:
            lines.append("Errors:")
            lines.extend(f"- {item}" for item in self.errors)
        if self.warnings:
            lines.append("Warnings:")
            lines.extend(f"- {item}" for item in self.warnings)
        notes = self.interpolation_notes or []
        if notes:
            lines.append("Interpolation:")
            lines.extend(f"- {item}" for item in notes)
        return lines


def frequency_units_convertible(unit_a: str, unit_b: str) -> bool:
    return unit_a in FREQUENCY_FACTORS_TO_HZ and unit_b in FREQUENCY_FACTORS_TO_HZ


def units_convertible(quantity: str, unit_a: str, unit_b: str) -> bool:
    if unit_a == unit_b:
        return True
    if quantity == "frequency":
        return frequency_units_convertible(unit_a, unit_b)
    return False


def _is_pattern_gain_like(curve: Curve) -> bool:
    text = " ".join([str(curve.y_quantity), str(curve.y_column), str(curve.label)]).lower()
    return curve.y_quantity in {"Gain", "RealizedGain"} or any(
        token in text for token in ("realizedgain", "gaintotal", "directivity", "rhcp", "lhcp", "co-pol", "copol", "cross")
    )


def convert_x_data(curve: Curve, target_unit: str) -> tuple[np.ndarray, str | None]:
    if curve.x_unit == target_unit:
        return curve.x_data.copy(), None
    if not units_convertible(curve.x_quantity, curve.x_unit, target_unit):
        raise ValueError(f"Cannot convert x unit from {curve.x_unit} to {target_unit}.")
    if curve.x_quantity == "frequency":
        source_factor = FREQUENCY_FACTORS_TO_HZ[curve.x_unit]
        target_factor = FREQUENCY_FACTORS_TO_HZ[target_unit]
        return curve.x_data * source_factor / target_factor, f"x unit converted from {curve.x_unit} to {target_unit}"
    return curve.x_data.copy(), None


def infer_curve_source(dataset: HfssDataset, curve: Curve) -> CurveSource:
    text = " ".join([dataset.path.name, curve.label, curve.y_column]).lower()
    if any(token in text for token in ["measured", "measurement", "vna", "test"]):
        return "Measured"
    if any(token in text for token in ["simulated", "simulation", "hfss", "ansys", "setup"]):
        return "Simulated"
    if any(token in text for token in ["reference", "ref"]):
        return "Reference"
    return "Unknown"


def y_axis_label(quantity: str, unit: str, *, normalized: bool = False) -> str:
    if normalized and quantity in {"Gain", "RealizedGain"}:
        return "Normalized Gain (dB)"
    labels = {
        "S11": r"$S_{11}$",
        "VSWR": "VSWR",
        "Gain": "Gain",
        "RealizedGain": "Realized Gain",
        "AR": "Axial Ratio",
        "Efficiency": "Efficiency",
        "Phase": "Phase",
    }
    base = labels.get(quantity, quantity)
    if unit == "linear":
        return base
    return f"{base} ({unit})"


def x_axis_label(quantity: str, unit: str) -> str:
    labels = {
        "frequency": "Frequency",
        "theta": r"$\theta$",
        "phi": r"$\phi$",
        "angle": "Angle",
    }
    base = labels.get(quantity, quantity)
    return f"{base} ({unit})"


def styled_curve_options(curve: Curve, style: dict, index: int, default_color: str) -> dict:
    options = curve_style(style, index, default_color)
    metadata = curve.metadata or {}
    marker_map = {
        "none": None,
        "circle": "o",
        "triangle": "^",
        "square": "s",
        "point": ".",
    }
    if metadata.get("color"):
        options["color"] = str(metadata["color"])
    if metadata.get("line_width") not in (None, ""):
        options["linewidth"] = float(metadata["line_width"])
    if metadata.get("line_style"):
        options["linestyle"] = str(metadata["line_style"])
    if metadata.get("marker_size") not in (None, ""):
        options["markersize"] = float(metadata["marker_size"])
    if metadata.get("alpha") not in (None, ""):
        options["alpha"] = float(metadata["alpha"])
    if metadata.get("marker_enabled") is False:
        options["marker"] = None
    elif metadata.get("marker_style") in marker_map:
        options["marker"] = marker_map[str(metadata["marker_style"])]
    elif metadata.get("marker"):
        options["marker"] = str(metadata["marker"])
    return options


def marker_samples(curve: Curve, x_data: np.ndarray, y_data: np.ndarray) -> tuple[np.ndarray | None, np.ndarray | None]:
    if curve.metadata.get("marker_enabled") is False:
        return None, None
    try:
        every = int(curve.metadata.get("marker_every", 1) or 1)
    except (TypeError, ValueError):
        every = 1
    if every <= 1:
        return x_data, y_data
    return x_data[::every], y_data[::every]


def metric_enabled_curves(curves: list[Curve]) -> list[Curve]:
    return [curve for curve in curves if curve.metadata.get("participate_metrics", True) is not False]


class CurveManager:
    """Keeps plotted curves separate from their source datasets."""

    def __init__(self, curves: Iterable[Curve] | None = None) -> None:
        self.curves: list[Curve] = []
        if curves:
            self.add_curves(curves)

    def add_curves(self, curves: Iterable[Curve]) -> None:
        for curve in curves:
            self.curves.append(replace(curve, order=len(self.curves)))

    def list_curves(self) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        for index, curve in enumerate(self.curves):
            result.append(
                {
                    "index": index,
                    "enabled": curve.is_enabled,
                    "label": curve.label,
                    "dataset_id": curve.dataset_id,
                    "x_column": curve.x_column,
                    "y_column": curve.y_column,
                    "x_quantity": curve.x_quantity,
                    "y_quantity": curve.y_quantity,
                    "x_unit": curve.x_unit,
                    "y_unit": curve.y_unit,
                    "normalized": curve.is_normalized,
                    "source": curve.source_role,
                    "conversion": curve.conversion,
                    "warnings": list(curve.warnings),
                    "sample_count": int(curve.metadata.get("sample_count", min(len(curve.x_data), len(curve.y_data)))),
                    "raw_sample_count": curve.metadata.get("raw_sample_count"),
                    "unique_x_count": curve.metadata.get("unique_x_count"),
                    "displayed_sample_count": curve.metadata.get("displayed_sample_count"),
                    "sampling_policy": curve.metadata.get("sampling_policy") or "raw samples preserved",
                    "duplicate_x_count": curve.metadata.get("duplicate_x_count"),
                    "duplicate_x_count_after_grouping": curve.metadata.get("duplicate_x_count_after_grouping"),
                    "sample_display_policy": curve.metadata.get("sample_display_policy"),
                    "line_width": curve.metadata.get("line_width"),
                    "line_style": curve.metadata.get("line_style"),
                    "color": curve.metadata.get("color"),
                    "marker_enabled": curve.metadata.get("marker_enabled", True),
                    "marker": curve.metadata.get("marker"),
                    "marker_size": curve.metadata.get("marker_size"),
                    "marker_every": curve.metadata.get("marker_every"),
                    "alpha": curve.metadata.get("alpha"),
                    "participate_metrics": curve.metadata.get("participate_metrics", True),
                    "cut": curve.metadata.get("cut"),
                    "polarization_role": curve.metadata.get("polarization_role"),
                }
            )
        return result

    def enabled_curves(self) -> list[Curve]:
        return [curve for curve in self.curves if curve.is_enabled]

    def set_enabled(self, index: int, enabled: bool) -> None:
        self.curves[index].is_enabled = enabled

    def delete(self, index: int) -> Curve:
        removed = self.curves.pop(index)
        self._refresh_order()
        return removed

    def rename(self, index: int, label: str) -> None:
        self.curves[index].label = label

    def move(self, old_index: int, new_index: int) -> None:
        curve = self.curves.pop(old_index)
        self.curves.insert(new_index, curve)
        self._refresh_order()

    def set_source(self, index: int, source: CurveSource) -> None:
        self.curves[index].source_role = source

    def set_unit_conversion(self, index: int, *, x_unit: str | None = None) -> None:
        curve = self.curves[index]
        if x_unit:
            x_data, note = convert_x_data(curve, x_unit)
            conversion = curve.conversion
            if note:
                conversion = f"{conversion}; {note}" if conversion else note
            self.curves[index] = replace(curve, x_data=x_data, x_unit=x_unit, conversion=conversion)

    def set_normalized(self, index: int, normalized: bool) -> None:
        curve = self.curves[index]
        if curve.is_normalized == normalized:
            return
        if not normalized:
            warning = "Cannot restore absolute values after normalization without rebuilding the curve from its Dataset."
            self.curves[index].warnings.append(warning)
            return
        finite = curve.y_data[np.isfinite(curve.y_data)]
        if finite.size == 0:
            self.curves[index].warnings.append("Normalization requested but y data has no finite values.")
            return
        y_data = curve.y_data - float(np.nanmax(finite))
        conversion = curve.conversion
        note = "normalized to 0 dB max"
        conversion = f"{conversion}; {note}" if conversion else note
        self.curves[index] = replace(curve, y_data=y_data, y_unit="dB", is_normalized=True, conversion=conversion)

    def set_columns(
        self,
        index: int,
        dataset: HfssDataset,
        *,
        x_column: str,
        y_column: str,
        x_unit: str | None = None,
        y_unit: str | None = None,
        label: str | None = None,
        normalize_curve: bool | None = None,
    ) -> None:
        current = self.curves[index]
        rebuilt = curve_from_columns(
            dataset,
            x_column,
            y_column,
            x_unit=x_unit,
            y_unit=y_unit,
            label=label or current.label,
            normalize_curve=current.is_normalized if normalize_curve is None else normalize_curve,
        )
        self.curves[index] = replace(
            rebuilt,
            is_enabled=current.is_enabled,
            source_role=current.source_role,
            order=current.order,
            metadata=dict(current.metadata),
        )

    def validate_overlay(self, plot_type: str | None = None) -> OverlayValidationResult:
        curves = self.enabled_curves()
        errors: list[str] = []
        warnings: list[str] = []
        if not curves:
            errors.append("No enabled curves are available for overlay plotting.")
            return OverlayValidationResult(False, errors, warnings, False, ["No interpolation performed."])

        x_quantities = {curve.x_quantity for curve in curves}
        y_quantities = {curve.y_quantity for curve in curves}
        x_units = {curve.x_unit for curve in curves}
        y_units = {curve.y_unit for curve in curves}
        normalized_states = {curve.is_normalized for curve in curves}

        if len(x_quantities) > 1:
            if x_quantities <= {"theta", "phi", "angle"}:
                warnings.append("Theta/Phi/Angle cuts are overlaid; legend and report must explicitly identify each cut.")
            else:
                errors.append(f"X-axis physical quantities are inconsistent: {', '.join(sorted(x_quantities))}.")
        normalized_plot_type = str(plot_type or "").lower().replace("_", " ").replace("-", " ").strip()
        pattern_gain_overlay = (
            normalized_plot_type in {"pattern", "radiation pattern", "radiation"}
            and all(curve.x_quantity in {"theta", "phi", "angle"} for curve in curves)
            and all(_is_pattern_gain_like(curve) for curve in curves)
            and len({curve.y_unit for curve in curves}) == 1
        )
        if len(y_quantities) > 1:
            if pattern_gain_overlay:
                warnings.append("Gain, RealizedGain, RHCP/LHCP and polarization gain traces share one angular dB/dBi radial axis for Radiation Pattern.")
            elif {"S11", "VSWR"} <= y_quantities:
                errors.append("S11 and VSWR cannot share one ordinary Y axis.")
            elif "S11" in y_quantities and ({"Gain", "RealizedGain"} & y_quantities):
                errors.append("Gain and S11 cannot share one ordinary Y axis.")
            else:
                errors.append(f"Y-axis physical quantities are inconsistent: {', '.join(sorted(y_quantities))}.")
        if len(normalized_states) > 1:
            errors.append("Normalized and absolute curves cannot be overlaid without an explicit dual-axis or separate plot.")

        reference = curves[0]
        for curve in curves[1:]:
            if not units_convertible(reference.x_quantity, reference.x_unit, curve.x_unit):
                errors.append(f"X units are not convertible: {reference.x_unit} vs {curve.x_unit}.")
            if reference.y_unit != curve.y_unit:
                errors.append(f"Y units are inconsistent: {reference.y_unit} vs {curve.y_unit}.")

        y_text = " ".join([curve.y_quantity + " " + curve.y_column + " " + curve.label for curve in curves]).lower()
        gain_mix_text = y_text.replace("realizedgaintotal", "").replace("realized gain total", "")
        if "gaintotal" in gain_mix_text and "realizedgain" in y_text:
            warnings.append("GainTotal and RealizedGainTotal appear mixed; explain this in the report or split the plot.")

        cut_keys = {
            (
                curve.metadata.get("cut_type"),
                curve.metadata.get("scan_variable"),
                curve.metadata.get("fixed_variable"),
                curve.metadata.get("fixed_value_deg"),
            )
            for curve in curves
            if curve.metadata.get("cut_type")
        }
        if len(cut_keys) > 1:
            family_variables = {curve.metadata.get("family_variable") for curve in curves if curve.metadata.get("cut_type")}
            scan_variables = {curve.metadata.get("scan_variable") for curve in curves if curve.metadata.get("cut_type")}
            is_cut_family = len(family_variables) == 1 and None not in family_variables and len(scan_variables) == 1
            if is_cut_family:
                warnings.append("Radiation-pattern cut-family curves are overlaid; confirm the cuts are intended for comparison.")
            else:
                errors.append("Radiation-pattern cuts are inconsistent across curves.")
        angle_axes = {curve.x_quantity for curve in curves if curve.x_quantity in {"theta", "phi", "angle"}}
        if len(angle_axes) > 1:
            warnings.append("Theta cut and Phi cut appear mixed; this is allowed for Radiation Pattern only when labels are explicit.")

        for curve in curves:
            warnings.extend(curve.warnings)

        notes = [
            "No interpolation performed for overlay plotting.",
            "Different frequency grids are allowed; each curve is plotted on its own X samples.",
        ]
        return OverlayValidationResult(not errors, errors, warnings, False, notes)

    def _refresh_order(self) -> None:
        for index, curve in enumerate(self.curves):
            curve.order = index


def curves_from_dataset(dataset: HfssDataset, plot_type: str, *, x_unit: str | None = None) -> list[Curve]:
    raw_plot_type = str(plot_type or "auto").lower().replace("_", " ").replace("-", " ").strip()
    plot_type = raw_plot_type
    if plot_type in {"axial ratio", "axialratio"}:
        plot_type = "ar"
    elif plot_type in {"return loss", "returnloss"}:
        plot_type = "s11"
    elif plot_type in {"half power beamwidth", "half-power beamwidth", "beamwidth", "h p b w"}:
        plot_type = "hpbw"
    elif plot_type in {"radiation pattern", "radiation"}:
        plot_type = "pattern"
    elif plot_type in {"realized gain", "realizedgain"}:
        plot_type = "gain"
    elif plot_type in {"smith chart", "smithchart"}:
        plot_type = "smith"
    if plot_type == "auto":
        detected_kind = detect_kind(dataset)
        if detected_kind == "s11":
            return s11_curves_from_dataset(dataset, x_unit=x_unit).curves
        if detected_kind == "smith":
            return smith_curves_from_dataset(dataset)
        if detected_kind == "pattern":
            return pattern_curves_from_dataset(dataset, normalize=False)
        if detected_kind == "ar":
            return axial_ratio_curves_from_dataset(dataset, x_unit=x_unit)
        if detected_kind == "vswr":
            return vswr_curves_from_dataset(dataset, x_unit=x_unit)
        if detected_kind == "eff":
            return efficiency_curves_from_dataset(dataset, x_unit=x_unit)
        if detected_kind == "hpbw":
            return [curve_from_columns(dataset, frequency_column(dataset.headers) or "", column, x_unit=x_unit, label=column) for column in _all_columns_matching(dataset, ["hpbw", "beamwidth", "halfpower"], exclude={frequency_column(dataset.headers) or ""})]
    if plot_type == "s11":
        result = s11_curves_from_dataset(dataset, x_unit=x_unit)
        curves = result.curves
        for curve in curves:
            if result.requires_confirmation:
                curve.warnings.extend(result.warnings)
        return curves
    if plot_type == "smith":
        return smith_curves_from_dataset(dataset)
    if plot_type == "pattern":
        return pattern_curves_from_dataset(dataset, normalize=False)
    if plot_type == "vswr":
        return vswr_curves_from_dataset(dataset, x_unit=x_unit)
    if plot_type in {"ar", "axialratio"}:
        return axial_ratio_curves_from_dataset(dataset, x_unit=x_unit)
    if plot_type in {"efficiency", "eff"}:
        return efficiency_curves_from_dataset(dataset, x_unit=x_unit)
    if plot_type == "hpbw":
        x_col = frequency_column(dataset.headers)
        if not x_col:
            return []
        columns = _all_columns_matching(dataset, ["hpbw", "beamwidth", "halfpower"], exclude={x_col})
        return [curve_from_columns(dataset, x_col, column, x_unit=x_unit, label=column) for column in columns]
    curves = auto_curves_from_hfss(dataset, x_unit=x_unit)
    if plot_type != "auto":
        aliases = {
            "gain": {"gain", "realizedgain"},
            "realizedgain": {"gain", "realizedgain"},
            "efficiency": {"efficiency"},
            "eff": {"efficiency"},
            "ar": {"ar"},
            "axialratio": {"ar"},
            "vswr": {"vswr"},
            "hpbw": {"hpbw"},
        }
        allowed = aliases.get(plot_type, {plot_type})
        filtered = [curve for curve in curves if curve.y_quantity.lower() in allowed]
        curves = filtered
    return curves


def build_curve_manager_from_csv_files(paths: Iterable[Path], plot_type: str, *, x_unit: str | None = None) -> CurveManager:
    manager = CurveManager()
    for path in paths:
        dataset = read_hfss_csv(path)
        curves = curves_from_dataset(dataset, plot_type, x_unit=x_unit)
        for curve in curves:
            curve.source_role = infer_curve_source(dataset, curve)
            curve.metadata["source_file"] = str(path)
        manager.add_curves(curves)
    return manager


def write_overlay_report(
    output_dir: Path,
    output_name: str,
    manager: CurveManager,
    validation: OverlayValidationResult,
    outputs: list[Path],
    unit_notes: list[str],
    metrics_text: str | None = None,
    messages: list[Message] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{output_name}_overlay_report.txt"
    lines = [
        "Multi-CSV Overlay Report",
        "",
    ]
    if messages is not None:
        lines.extend([format_messages(messages), ""])
    lines.extend([
        "Curves:",
    ])
    for item in manager.list_curves():
        lines.append(
            "- #{index}: {label} | enabled={enabled} | source={source} | "
            "x={x_column} [{x_unit}] | y={y_column} [{y_unit}] | normalized={normalized} | "
            "sample_count={sample_count}".format(**item)
        )
        lines.append(f"  sampling: {item.get('sampling_policy')}")
        if item.get("duplicate_x_count"):
            lines.append(f"  duplicate_x_count: {item['duplicate_x_count']}")
        if item["conversion"]:
            lines.append(f"  conversion: {item['conversion']}")
        if item.get("cut"):
            lines.append(f"  cut: {item['cut']}")
        if item.get("polarization_role"):
            lines.append(f"  polarization: {item['polarization_role']}")
    lines.append("")
    lines.extend(validation.report_lines())
    if unit_notes:
        lines.append("")
        lines.append("Unit conversions:")
        lines.extend(f"- {item}" for item in unit_notes)
    if metrics_text:
        lines.append("")
        lines.append(metrics_text)
    lines.append("")
    lines.append("Generated files:")
    lines.extend(f"- {item}" for item in outputs)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _report_file_requested(style: dict) -> bool:
    requested = {str(item).lower().lstrip(".") for item in style.get("export", {}).get("requested_formats", [])}
    return bool({"txt", "md", "markdown"} & requested)


def _as_float(value: object, default: float) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _is_impedance_column(column: str) -> bool:
    text = normalize(column)
    return "z" in text and "s11" not in text and "s1" not in text


def smith_curves_from_dataset(dataset: HfssDataset, *, z0: float = 50.0) -> list[Curve]:
    real_col = smith_real_column(dataset.headers)
    imag_col = smith_imag_column(dataset.headers)
    if not real_col or not imag_col:
        complex_col = complex_s_column(dataset.headers)
        values = [clean_complex(row.get(complex_col, "")) for row in dataset.rows] if complex_col else []
        gamma = np.asarray([value for value in values if value is not None], dtype=complex)
        if gamma.size == 0:
            return []
        return [
            Curve(
                dataset_id=dataset.to_model().dataset_id or "",
                x_data=gamma.real,
                y_data=gamma.imag,
                x_column=complex_col or "",
                y_column=complex_col or "",
                x_quantity="frequency",  # type: ignore[arg-type]
                y_quantity="S11",
                x_unit="linear",  # type: ignore[arg-type]
                y_unit="linear",
                label="S11",
                conversion="complex S11 parsed from single HFSS complex column",
                warnings=[
                    "Reference impedance, renormalization, de-embed state, and port reference plane require user confirmation.",
                ],
                metadata={
                    "smith_chart": True,
                    "complex_network": True,
                    "complex_column": complex_col,
                    "z0_ohm": z0,
                    "source_file": str(dataset.path),
                    "preserve_order": True,
                    "sampling_policy": "Smith Chart trajectory preserves original sweep order; no sorting by Real axis",
                },
            )
        ]
    real = dataset.column(real_col)
    imag = dataset.column(imag_col)
    finite = np.isfinite(real) & np.isfinite(imag)
    real = real[finite]
    imag = imag[finite]
    if real.size == 0:
        return []
    if _is_impedance_column(real_col) or _is_impedance_column(imag_col):
        z = real + 1j * imag
        gamma = (z - z0) / (z + z0)
        conversion = f"Zin normalized to reflection coefficient using Z0={z0:g} ohm"
        label = "Zin / Z0"
        warnings = [
            f"Smith Chart uses Z0={z0:g} ohm by default.",
            "Reference impedance, renormalization, de-embed state, and port reference plane require user confirmation.",
        ]
    else:
        gamma = real + 1j * imag
        conversion = "complex S11 from re/im"
        label = "S11"
        warnings = [
            "Reference impedance, renormalization, de-embed state, and port reference plane require user confirmation.",
        ]
    return [
        Curve(
            dataset_id=dataset.to_model().dataset_id or "",
            x_data=gamma.real,
            y_data=gamma.imag,
            x_column=real_col,
            y_column=imag_col,
            x_quantity="frequency",  # type: ignore[arg-type]
            y_quantity="S11",
            x_unit="linear",  # type: ignore[arg-type]
            y_unit="linear",
            label=label,
            conversion=conversion,
            warnings=warnings,
            metadata={
                "smith_chart": True,
                "complex_network": True,
                "real_column": real_col,
                "imag_column": imag_col,
                "z0_ohm": z0,
                "source_file": str(dataset.path),
                "preserve_order": True,
                "sampling_policy": "Smith Chart trajectory preserves original sweep order; no sorting by Real axis",
            },
        )
    ]


def _numeric_values(dataset: HfssDataset, column: str) -> np.ndarray:
    return dataset.column(column)


def _all_columns_matching(dataset: HfssDataset, tokens: list[str], *, exclude: set[str] | None = None) -> list[str]:
    exclude = exclude or set()
    result: list[str] = []
    for header in dataset.headers:
        if header in exclude or not is_numeric_column(dataset.rows, header):
            continue
        text = normalize(header)
        if any(token in text for token in tokens):
            result.append(header)
    return result


def _header_suffix(column: str) -> str:
    match = re.search(r"_(\d+)$", column)
    return f"_{match.group(1)}" if match else ""


def _paired_column(headers: list[str], base_tokens: list[str], suffix: str) -> str | None:
    candidates = [header for header in headers if any(token in normalize(header) for token in base_tokens)]
    if suffix:
        return next((header for header in candidates if header.endswith(suffix)), None)
    return next((header for header in candidates if not re.search(r"_\d+$", header)), None) or (candidates[0] if candidates else None)


def _unique_finite_count(values: np.ndarray) -> int:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return 0
    return int(np.unique(np.round(finite, 9)).size)


def _constant_value_text(dataset: HfssDataset, column: str | None) -> str | None:
    if not column:
        return None
    values = dataset.column(column)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return None
    unique = np.unique(np.round(finite, 9))
    if unique.size != 1:
        return None
    unit = "deg" if "deg" in column.lower() else ""
    value = float(unique[0])
    return f"{value:g}{(' ' + unit) if unit else ''}"


def vswr_curves_from_dataset(dataset: HfssDataset, *, x_unit: str | None = None) -> list[Curve]:
    x_col = frequency_column(dataset.headers)
    if not x_col:
        return []
    direct_cols = _all_columns_matching(dataset, ["vswr", "vsmr", "voltagestandingwaveratio"], exclude={x_col})
    if not direct_cols and vswr_column(dataset.headers):
        direct_cols = [vswr_column(dataset.headers) or ""]
    curves: list[Curve] = []
    for column in [item for item in direct_cols if item]:
        curve = curve_from_columns(dataset, x_col, column, x_unit=x_unit, label=column)
        curve.y_quantity = "VSWR"
        curve.y_unit = "linear"
        curve.conversion = curve.conversion or "direct VSWR column"
        curves.append(curve)
    if curves:
        return curves
    s11_result = s11_curves_from_dataset(dataset, x_unit=x_unit)
    for s11_curve in s11_result.curves:
        mag = np.power(10.0, s11_curve.y_data / 20.0)
        with np.errstate(divide="ignore", invalid="ignore"):
            vswr = (1.0 + mag) / (1.0 - mag)
        curve = replace(
            s11_curve,
            y_data=vswr,
            y_quantity="VSWR",
            y_unit="linear",
            label=f"VSWR from {s11_curve.label}",
            conversion=f"{s11_curve.conversion or 'S11 dB'}; VSWR=(1+|S11|)/(1-|S11|)",
            warnings=[
                *s11_curve.warnings,
                "VSWR was derived from S11 because no direct VSWR column was selected; report this conversion.",
            ],
        )
        curves.append(curve)
    return curves


def axial_ratio_curves_from_dataset(dataset: HfssDataset, *, x_unit: str | None = None) -> list[Curve]:
    freq_col = frequency_column(dataset.headers)
    ar_cols = _all_columns_matching(dataset, ["axialratio", "axialratiovalue", "ar"], exclude={freq_col} if freq_col else set())
    if not ar_cols and axial_ratio_column(dataset.headers):
        ar_cols = [axial_ratio_column(dataset.headers) or ""]
    curves: list[Curve] = []
    for column in [item for item in ar_cols if item]:
        suffix = _header_suffix(column)
        theta_col = _paired_column(dataset.headers, ["theta"], suffix)
        phi_col = _paired_column(dataset.headers, ["phi"], suffix)
        angle_col = _paired_column(dataset.headers, ["angle"], suffix)
        paired_freq_col = _paired_column(dataset.headers, ["freq", "frequency"], suffix) or freq_col
        x_col = paired_freq_col
        if theta_col and _unique_finite_count(dataset.column(theta_col)) > 1:
            x_col = theta_col
        elif phi_col and _unique_finite_count(dataset.column(phi_col)) > 1:
            x_col = phi_col
        elif angle_col and _unique_finite_count(dataset.column(angle_col)) > 1:
            x_col = angle_col
        if not x_col:
            continue
        fixed_phi = _constant_value_text(dataset, phi_col)
        fixed_theta = _constant_value_text(dataset, theta_col)
        label = column
        if x_col == theta_col and fixed_phi:
            label = f"Phi = {fixed_phi}"
        elif x_col == phi_col and fixed_theta:
            label = f"Theta = {fixed_theta}"
        curve = curve_from_columns(dataset, x_col, column, x_unit=x_unit if frequency_column([x_col]) else "deg", label=label)
        curve.y_quantity = "AR"
        curve.y_unit = "dB"
        theta_values = dataset.column(theta_col) if theta_col else np.asarray([])
        phi_values = dataset.column(phi_col) if phi_col else np.asarray([])
        theta_unique = np.unique(theta_values[np.isfinite(theta_values)]) if theta_values.size else np.asarray([])
        phi_unique = np.unique(phi_values[np.isfinite(phi_values)]) if phi_values.size else np.asarray([])
        family_column = None
        family_values = np.asarray([])
        if x_col == theta_col and phi_unique.size > 1 and phi_unique.size <= 16:
            family_column, family_values = phi_col, phi_unique
        elif x_col == phi_col and theta_unique.size > 1 and theta_unique.size <= 16:
            family_column, family_values = theta_col, theta_unique
        if family_column is not None:
            family_data = dataset.column(family_column)
            grouped: list[Curve] = []
            for family_value in family_values:
                mask = np.isfinite(family_data) & (np.abs(family_data - family_value) <= 1e-9)
                if not np.any(mask):
                    continue
                order = np.argsort(dataset.column(x_col)[mask])
                group = replace(
                    curve,
                    x_data=curve.x_data[mask][order],
                    y_data=curve.y_data[mask][order],
                    label=f"{family_column} = {float(family_value):g} deg",
                    warnings=[*curve.warnings, "Angular Axial Ratio data were split by the family variable before duplicate-X checks."],
                    metadata={
                        **curve.metadata,
                        "family_info": {family_column: float(family_value)},
                        "family_variable": family_column,
                        "fixed_variable": family_column,
                        "fixed_value_deg": float(family_value),
                        "cut_type": "axial_ratio_cut_family",
                    },
                )
                grouped.append(group)
            if grouped:
                curves.extend(grouped)
                continue
        if curve.x_quantity in {"theta", "phi", "angle"}:
            curve.metadata["cut_type"] = curve.metadata.get("cut_type") or "axial_ratio_angle_cut"
            curve.metadata["scan_variable"] = "Theta" if x_col == theta_col else "Phi" if x_col == phi_col else "Angle"
            curve.metadata["fixed_frequency"] = _constant_value_text(dataset, paired_freq_col)
            if x_col == theta_col and fixed_phi:
                curve.metadata["family_info"] = {"Phi": fixed_phi}
                curve.metadata["family_variable"] = "Phi"
                curve.metadata["fixed_variable"] = "Phi"
                curve.metadata["fixed_value_deg"] = fixed_phi.replace(" deg", "")
            elif x_col == phi_col and fixed_theta:
                curve.metadata["family_info"] = {"Theta": fixed_theta}
                curve.metadata["family_variable"] = "Theta"
                curve.metadata["fixed_variable"] = "Theta"
                curve.metadata["fixed_value_deg"] = fixed_theta.replace(" deg", "")
            curve.warnings.append("Axial Ratio uses an angular X axis; do not label this as frequency-response AR.")
        curves.append(curve)
    return curves


def efficiency_curves_from_dataset(dataset: HfssDataset, *, x_unit: str | None = None) -> list[Curve]:
    x_col = frequency_column(dataset.headers)
    if not x_col:
        return []
    eff_cols = _all_columns_matching(dataset, ["radiationefficiency", "totalefficiency", "antennaefficiency", "efficiency"], exclude={x_col})
    if not eff_cols and efficiency_column(dataset.headers):
        eff_cols = [efficiency_column(dataset.headers) or ""]
    curves: list[Curve] = []
    for column in [item for item in eff_cols if item]:
        curve = curve_from_columns(dataset, x_col, column, x_unit=x_unit, label=column)
        curve.y_quantity = "Efficiency"
        unit_text = normalize(column)
        curve.y_unit = "linear"
        if "%" in column or "percent" in unit_text:
            curve.y_unit = "linear"
            curve.metadata["efficiency_unit_note"] = "percent"
        curves.append(curve)
    return curves


def _polar_pattern_messages(curves: list[Curve], *, normalized: bool, clipped: bool, r_min: float, r_max: float) -> list[Message]:
    messages = [
        Message("info", "polar_pattern", "Plot rendered as polar radiation pattern.", {}),
        Message("info", "polar_axis", f"Polar radial display range is {r_min:g} to {r_max:g}; raw data are not modified for metrics.", {}),
    ]
    descriptions = sorted({str(curve.metadata.get("cut") or "Pattern cut not confirmed") for curve in curves})
    for description in descriptions:
        severity = "warning" if "not confirmed" in description.lower() else "info"
        messages.append(Message(severity, "pattern_cut", f"Pattern cut: {description}", {}))
    if normalized:
        messages.append(Message("info", "polar_normalized", "Polar plot uses Normalized Gain (dB); each curve is normalized to 0 dB maximum for display.", {}))
    if clipped:
        messages.append(Message("warning", "polar_radial_clip", f"Values below r_min={r_min:g} were clipped for display only; metrics use original data.", {}))
    messages.append(Message("info", "polar_radius_mapping", f"Polar radius uses display mapping r = max(y, {r_min:g}) - ({r_min:g}); tick labels show the original dB/dBi values.", {}))
    for curve in curves:
        finite = curve.x_data[np.isfinite(curve.x_data)]
        if finite.size:
            minimum = float(np.nanmin(finite))
            maximum = float(np.nanmax(finite))
            if minimum >= -1e-6 and maximum <= 180.0 + 1e-6:
                messages.append(Message("info", "polar_half_space", f"{curve.label}: angle range is {minimum:g}-{maximum:g} deg, treated as a half-space cut; no mirroring was applied.", {}))
    return messages


def _polar_angles_for_display(raw_angles: np.ndarray) -> np.ndarray:
    finite = raw_angles[np.isfinite(raw_angles)]
    if finite.size == 0:
        return raw_angles.astype(float)
    minimum = float(np.nanmin(finite))
    maximum = float(np.nanmax(finite))
    if minimum < 0.0 or maximum > 360.0:
        return np.mod(raw_angles.astype(float), 360.0)
    return raw_angles.astype(float)


def _append_display_closure(angles: np.ndarray, values: np.ndarray) -> tuple[np.ndarray, np.ndarray, bool]:
    if angles.size < 3:
        return angles, values, False
    finite = np.isfinite(angles) & np.isfinite(values)
    if finite.sum() < 3:
        return angles, values, False
    a = angles[finite]
    minimum = float(np.nanmin(a))
    maximum = float(np.nanmax(a))
    has_zero = bool(np.any(np.isclose(a, 0.0, atol=1e-6)))
    has_360 = bool(np.any(np.isclose(a, 360.0, atol=1e-6)))
    span = maximum - minimum
    if has_zero and not has_360 and span >= 330.0:
        zero_index = int(np.flatnonzero(np.isclose(angles, 0.0, atol=1e-6))[0])
        return np.append(angles, 360.0), np.append(values, values[zero_index]), True
    return angles, values, False


def _radial_ticks(r_min: float, r_max: float) -> tuple[np.ndarray, list[str]]:
    if r_max <= r_min:
        return np.array([0.0]), [f"{r_min:g}"]
    step = 10.0 if (r_max - r_min) >= 20.0 else max(1.0, round((r_max - r_min) / 4.0, 2))
    start = np.ceil(r_min / step) * step
    stop = np.floor(r_max / step) * step
    true_ticks = np.arange(start, stop + step * 0.5, step)
    if true_ticks.size == 0 or not np.isclose(true_ticks[0], r_min):
        true_ticks = np.insert(true_ticks, 0, r_min)
    if not np.isclose(true_ticks[-1], r_max):
        true_ticks = np.append(true_ticks, r_max)
    display_ticks = true_ticks - r_min
    labels = [f"{tick:g}" for tick in true_ticks]
    return display_ticks, labels


def _polar_figure_size(style: dict, polar_style: str) -> tuple[float, float]:
    if polar_style == "hfss_like":
        return 7.0, 4.2
    return 5.8, 4.2


def _polar_angle_ticks(angle_label_mode: str) -> tuple[list[float], list[str]]:
    if angle_label_mode == "minus180_180":
        ticks = list(range(0, 360, 30))
        labels = [f"{item}\N{DEGREE SIGN}" for item in [0, 30, 60, 90, 120, 150, -180, -150, -120, -90, -60, -30]]
        return [float(item) for item in ticks], labels
    ticks = list(range(0, 360, 45))
    labels = [f"{item}\N{DEGREE SIGN}" for item in ticks]
    return [float(item) for item in ticks], labels


def _clean_polar_label(curve: Curve) -> str:
    text = str(curve.label or curve.y_column or "").strip()
    haystack = " ".join(
        str(item or "")
        for item in [
            curve.label,
            curve.y_column,
            curve.metadata.get("cut"),
            curve.metadata.get("cut_type"),
            curve.metadata.get("polarization_role"),
            curve.metadata.get("family_value"),
        ]
    )
    lowered = haystack.lower()
    if "e-plane" in lowered or "e plane" in lowered:
        return "E-plane"
    if "h-plane" in lowered or "h plane" in lowered:
        return "H-plane"
    if "rhcp" in lowered:
        return "RHCP"
    if "lhcp" in lowered:
        return "LHCP"
    if "cross" in lowered and "polar" in lowered:
        return "Cross-pol"
    if ("co" in lowered or "main" in lowered) and "polar" in lowered:
        return "Co-pol"

    for pattern in [
        r"(?:phi|\bPhi\b)(?:\s*\[[^\]]+\])?[\"']?\s*=?\s*[\"']?\s*(-?\d+(?:\.\d+)?)\s*(?:deg|degree|\N{DEGREE SIGN})",
        r"(?:theta|\bTheta\b)(?:\s*\[[^\]]+\])?[\"']?\s*=?\s*[\"']?\s*(-?\d+(?:\.\d+)?)\s*(?:deg|degree|\N{DEGREE SIGN})",
        r"(?:freq|frequency)(?:\s*\[[^\]]+\])?[\"']?\s*=?\s*[\"']?\s*(-?\d+(?:\.\d+)?)\s*(ghz|mhz|hz)",
    ]:
        match = re.search(pattern, haystack, flags=re.IGNORECASE)
        if match:
            value = float(match.group(1))
            quantity = "Phi" if "phi" in pattern.lower() else "Theta" if "theta" in pattern.lower() else ""
            if quantity:
                return f"{quantity} = {value:g}\N{DEGREE SIGN}"
            unit = match.group(2)
            return f"{value:g} {unit.upper() if unit.lower() == 'hz' else unit.capitalize()}"

    for key, quantity in [("fixed_phi_deg", "Phi"), ("fixed_theta_deg", "Theta"), ("frequency_mhz", "")]:
        value = curve.metadata.get(key)
        if value is not None:
            number = _as_float(value, float("nan"))
            if np.isfinite(number):
                if quantity:
                    return f"{quantity} = {number:g}\N{DEGREE SIGN}"
                return f"{number:g} MHz"

    cleaned = re.sub(r"^\"?dB\s*\[\]\"?\s*", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" \"")
    return cleaned or text or "Pattern"


def plot_radiation_pattern_polar(manager: CurveManager, output_dir: Path, style: dict, args: Namespace, validation: OverlayValidationResult) -> list[Path]:
    curves = manager.enabled_curves()
    if not curves:
        raise ValueError("No enabled curves are available for polar radiation pattern.")
    for curve in curves:
        if curve.x_quantity not in {"theta", "phi", "angle"}:
            raise ValueError(f"Polar Pattern requires an angle curve; {curve.label} uses {curve.x_quantity}.")
        if curve.x_unit != "deg":
            raise ValueError(f"Polar Pattern requires angle unit deg; {curve.label} uses {curve.x_unit}.")

    apply_style(style)
    polar_style = str(getattr(args, "polar_style", None) or "paper").lower()
    if polar_style not in {"paper", "hfss_like"}:
        polar_style = "paper"
    angle_label_mode = str(getattr(args, "angle_label_mode", None) or ("minus180_180" if polar_style == "hfss_like" else "0_360")).lower()
    if angle_label_mode not in {"0_360", "minus180_180"}:
        angle_label_mode = "minus180_180" if polar_style == "hfss_like" else "0_360"
    fig = plt.figure(figsize=_polar_figure_size(style, polar_style), constrained_layout=False)
    if polar_style == "paper":
        ax = fig.add_axes([0.08, 0.13, 0.66, 0.72], projection="polar")
    else:
        ax = fig.add_axes([0.07, 0.10, 0.64, 0.78], projection="polar")

    normalize_display = bool(getattr(args, "pattern_normalize", False)) or any(curve.is_normalized for curve in curves)
    r_min = _as_float(getattr(args, "r_min", None), -30.0)
    if normalize_display:
        r_max = _as_float(getattr(args, "r_max", None), 0.0)
    else:
        finite_chunks = [curve.y_data[np.isfinite(curve.y_data)] for curve in curves if curve.y_data[np.isfinite(curve.y_data)].size]
        finite_all = np.concatenate(finite_chunks) if finite_chunks else np.array([])
        default_max = float(np.nanmax(finite_all)) if finite_all.size else 10.0
        r_max = _as_float(getattr(args, "r_max", None), max(0.0, default_max))
    if r_max <= r_min:
        raise ValueError("Polar Pattern requires r_max greater than r_min.")

    clipped_any = False
    display_closed_any = False
    unit_notes: list[str] = []
    for index, curve in enumerate(curves):
        angles = _polar_angles_for_display(curve.x_data.astype(float))
        values = curve.y_data.astype(float).copy()
        finite = np.isfinite(angles) & np.isfinite(values)
        angles = angles[finite]
        values = values[finite]
        if angles.size == 0:
            continue
        order = np.argsort(angles)
        angles = angles[order]
        values = values[order]
        if normalize_display and not curve.is_normalized:
            values = values - float(np.nanmax(values))
            unit_notes.append(f"{curve.label}: normalized to 0 dB max for polar display")
        angles, values, display_closed = _append_display_closure(angles, values)
        if display_closed:
            display_closed_any = True
            unit_notes.append(f"{curve.label}: first sample was appended at 360 deg for display-only closure")
        clipped_true_values = np.maximum(values, r_min)
        if np.any(clipped_true_values != values):
            clipped_any = True
        radius_display = clipped_true_values - r_min
        color_key = "gain"
        options = styled_curve_options(curve, style, index, style["colors"].get(color_key, style["colors"]["black"]))
        ax.plot(
            np.deg2rad(angles),
            radius_display,
            label=_clean_polar_label(curve),
            color=options.get("color"),
            linewidth=options.get("linewidth"),
            linestyle=options.get("linestyle", "-"),
            alpha=options.get("alpha", 1.0),
            marker=None if getattr(args, "no_markers", False) else options.get("marker"),
            markersize=options.get("markersize"),
            markevery=max(1, int(curve.metadata.get("marker_every", 1) or 1)),
        )

    ax.set_theta_zero_location(str(getattr(args, "theta_zero_location", "N") or "N"))
    ax.set_theta_direction(int(getattr(args, "theta_direction", -1) or -1))
    theta_ticks, theta_labels = _polar_angle_ticks(angle_label_mode)
    ax.set_thetagrids(theta_ticks, labels=theta_labels)
    ax.set_rlim(0, r_max - r_min)
    radial_ticks, radial_tick_labels = _radial_ticks(r_min, r_max)
    radial_label = "Normalized Gain (dB)" if normalize_display else y_axis_label(curves[0].y_quantity, curves[0].y_unit, normalized=False)
    label_angle = 210 if polar_style == "hfss_like" else 210
    ax.set_rgrids(
        radial_ticks,
        labels=radial_tick_labels,
        angle=label_angle,
        fontsize=style["font"]["tick_size"],
    )
    ax.set_rlabel_position(label_angle)
    for label in ax.get_yticklabels():
        label.set_bbox({"facecolor": "white", "edgecolor": "none", "alpha": 0.72, "pad": 0.8})
    title = getattr(args, "title", None) or ("Gain Plot" if polar_style == "hfss_like" else "Polar Radiation Pattern")
    if str(title).strip():
        ax.set_title(str(title), pad=14 if polar_style == "paper" else 12)
    ax.grid(True, color="#9CA3AF", linewidth=0.45 if polar_style == "paper" else 0.55, alpha=0.32 if polar_style == "paper" else 0.45)
    ax.spines["polar"].set_linewidth(1.15 if polar_style == "paper" else 1.35)
    ax.spines["polar"].set_color("#111111")
    ax.tick_params(pad=3, width=0.8)
    requested_legend_loc = str(getattr(args, "legend_loc", None) or "").strip().lower()
    legend_y = 0.58 if polar_style == "paper" else 0.88
    if "lower" in requested_legend_loc:
        legend_y = 0.34 if polar_style == "paper" else 0.36
    legend_loc = "upper left"
    legend_anchor = (0.78 if polar_style == "paper" else 0.76, legend_y)
    fig.legend(
        *ax.get_legend_handles_labels(),
        loc=legend_loc,
        bbox_to_anchor=legend_anchor,
        borderaxespad=0.0,
        frameon=False,
        fontsize=style["font"]["legend_size"],
    )
    fig.text(
        0.78,
        0.18 if polar_style == "paper" else 0.12,
        radial_label,
        ha="left",
        va="center",
        fontsize=style["font"]["tick_size"],
        color="#374151",
    )

    output_name = getattr(args, "output_name", None) or "polar_radiation_pattern"
    outputs = save_figure(fig, output_dir / output_name, style)
    settings = getattr(args, "project_settings", None)
    metrics_text = format_metric_results(metric_results_for_curves(metric_enabled_curves(curves), settings)) if settings is not None else None
    messages = [
        *(Message("error", "overlay_incompatible", item, {}) for item in validation.errors),
        *(Message("warning", "overlay_warning", item, {}) for item in validation.warnings),
        *_polar_pattern_messages(curves, normalized=normalize_display, clipped=clipped_any, r_min=r_min, r_max=r_max),
    ]
    if display_closed_any:
        messages.append(Message("info", "polar_display_closure", "A first sample was appended at 360 deg for display-only closure; raw data and metrics were not changed.", {}))
    if _report_file_requested(style):
        report = write_overlay_report(output_dir, output_name, manager, validation, outputs, unit_notes, metrics_text, messages)
        outputs.append(report)
    requested_formats = style.get("export", {}).get("requested_formats", style.get("export", {}).get("formats", []))
    if "json" in {str(item).lower() for item in requested_formats}:
        project_settings = getattr(args, "project_settings", None)
        overlay_config = {
            "plot_type": getattr(args, "plot_type", "pattern"),
            "display_mode": "polar",
            "pattern_display_mode": "polar",
            "polar_config": {
                "r_min": r_min,
                "r_max": r_max,
                "normalize": normalize_display,
                "theta_zero_location": getattr(args, "theta_zero_location", "N"),
                "theta_direction": getattr(args, "theta_direction", -1),
                "polar_style": polar_style,
                "angle_label_mode": angle_label_mode,
                "clip_below_r_min": True,
                "legend_loc": getattr(args, "legend_loc", None),
            },
            "input_file_path": sorted({str(curve.metadata.get("source_file")) for curve in manager.curves if curve.metadata.get("source_file")}),
            "curves": [curve_summary(curve) for curve in manager.curves],
            "pattern_cuts": [
                {
                    "curve": curve.label,
                    "angle_column": curve.x_column,
                    "radial_column": curve.y_column,
                    "cut": curve.metadata.get("cut"),
                    "cut_type": curve.metadata.get("cut_type"),
                    "scan_variable": curve.metadata.get("scan_variable"),
                }
                for curve in manager.curves
            ],
            "overlay_validation": {
                "allowed": validation.allowed,
                "errors": validation.errors,
                "warnings": validation.warnings,
                "interpolation_required": validation.interpolation_required,
                "interpolation_notes": validation.interpolation_notes or [],
            },
            "messages": [message.__dict__ for message in messages],
            "project_settings": {
                "working_band_mhz": getattr(project_settings, "working_band_mhz", None),
                "pattern_frequencies_mhz": getattr(project_settings, "pattern_frequencies_mhz", None),
                "prefer_realized_gain": getattr(project_settings, "prefer_realized_gain", None),
            } if project_settings is not None else None,
            "export_formats": requested_formats,
            "style": {
                "font": style.get("font", {}),
                "line": style.get("line", {}),
                "axis": style.get("axis", {}),
                "figure": style.get("figure", {}),
            },
        }
        outputs.append(write_json_config(output_dir, output_name, jsonable(overlay_config)))
    return outputs


def plot_overlay(manager: CurveManager, output_dir: Path, style: dict, args: Namespace) -> list[Path]:
    validation = manager.validate_overlay(getattr(args, "plot_type", None))
    validation_messages = [
        *(Message("error", "overlay_incompatible", item, {}) for item in validation.errors),
        *(Message("warning", "overlay_warning", item, {}) for item in validation.warnings),
        *(Message("info", "interpolation", item, {}) for item in (validation.interpolation_notes or [])),
    ]
    if not validation.allowed:
        raise ValueError("\n".join(validation.report_lines()))
    if str(getattr(args, "plot_type", "")).lower() == "smith":
        curves = manager.enabled_curves()
        apply_style(style)
        fig, ax = plt.subplots(figsize=figure_size(style, ratio=1.0), constrained_layout=True)
        draw_smith_grid(ax)
        for index, curve in enumerate(curves):
            options = styled_curve_options(curve, style, index, style["colors"].get("s11", style["colors"]["black"]))
            ax.plot(
                curve.x_data,
                curve.y_data,
                color=options.get("color"),
                linewidth=options.get("linewidth"),
                linestyle=options.get("linestyle", "-"),
                alpha=options.get("alpha", 1.0),
                marker=None if getattr(args, "no_markers", False) else options.get("marker"),
                markersize=options.get("markersize"),
                markevery=max(1, int(curve.metadata.get("marker_every", 1) or 1)),
                label=curve.label,
            )
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlim(-1.05, 1.05)
        ax.set_ylim(-1.05, 1.05)
        ax.set_xlabel("Real")
        ax.set_ylabel("Imaginary")
        ax.legend(loc=getattr(args, "legend_loc", None) or "upper right")
        ax.grid(False)
        output_name = getattr(args, "output_name", None) or "smith_chart"
        outputs = save_figure(fig, output_dir / output_name, style)
        messages = [
            *(Message("error", "overlay_incompatible", item, {}) for item in validation.errors),
            *(Message("warning", "overlay_warning", item, {}) for item in validation.warnings),
            Message("warning", "smith_reference_plane", "Reference impedance, renormalization, de-embed state, and port reference plane require user confirmation.", {}),
        ]
        if _report_file_requested(style):
            report = write_overlay_report(output_dir, output_name, manager, validation, outputs, [], None, messages)
            outputs.append(report)
        return outputs
    if str(getattr(args, "plot_type", "")).lower() == "pattern" and str(getattr(args, "pattern_display_mode", getattr(args, "display_mode", "cartesian"))).lower() == "polar":
        return plot_radiation_pattern_polar(manager, output_dir, style, args, validation)
    curves = manager.enabled_curves()
    apply_style(style)
    target_unit = getattr(args, "x_unit", None)
    if not target_unit or target_unit == "auto":
        target_unit = curves[0].x_unit
    target_unit = str(target_unit)
    target_unit = {"ghz": "GHz", "mhz": "MHz", "hz": "Hz", "deg": "deg"}.get(target_unit.lower(), target_unit)

    fig, ax = plt.subplots(figsize=figure_size(style), constrained_layout=True)
    unit_notes: list[str] = []
    for index, curve in enumerate(curves):
        x_data, note = convert_x_data(curve, target_unit)
        if note:
            unit_notes.append(f"{curve.label}: {note}")
        y_data = curve.y_data
        finite = np.isfinite(x_data) & np.isfinite(y_data)
        x_data = x_data[finite]
        y_data = y_data[finite]
        if x_data.size == 0:
            continue
        if not curve.metadata.get("preserve_order"):
            order = np.argsort(x_data)
            x_data = x_data[order]
            y_data = y_data[order]
        color_key = "s11" if curve.y_quantity == "S11" else "gain"
        options = styled_curve_options(curve, style, index, style["colors"].get(color_key, style["colors"]["black"]))
        marker_x, marker_y = marker_samples(curve, x_data, y_data)
        plot_curve(
            ax,
            x_data,
            y_data,
            curve.label,
            options,
            style,
            getattr(args, "no_markers", False),
            marker_x,
            marker_y,
        )

    first = curves[0]
    if first.metadata.get("xy_multi_curve"):
        default_xlabel = first.x_column
        default_ylabel = first.y_column if len(curves) == 1 else "Value"
    else:
        default_xlabel = x_axis_label(first.x_quantity, target_unit)
        default_ylabel = y_axis_label(first.y_quantity, first.y_unit, normalized=first.is_normalized)
    apply_limits_labels(
        ax,
        args,
        default_xlabel,
        default_ylabel,
    )
    if first.y_quantity == "S11" and not getattr(args, "no_threshold", False):
        threshold = getattr(args, "threshold", None)
        if threshold is None:
            threshold = 10.0 if "return" in str(getattr(args, "plot_type", "")).lower() else -10.0
        ax.axhline(threshold, color=style["colors"]["gray"], linestyle="--", linewidth=0.9)
        ax.text(0.985, threshold + 0.3, f"{threshold:g} dB", transform=ax.get_yaxis_transform(), ha="right", va="bottom", color=style["colors"]["gray"])
    if first.y_quantity == "VSWR" and not getattr(args, "no_threshold", False):
        threshold = getattr(args, "threshold", None)
        if threshold is None:
            threshold = 2.0
        ax.axhline(threshold, color=style["colors"]["gray"], linestyle="--", linewidth=0.9)
        ax.text(0.985, threshold + 0.05, f"VSWR = {threshold:g}", transform=ax.get_yaxis_transform(), ha="right", va="bottom", color=style["colors"]["gray"])
    if first.y_quantity == "AR" and not getattr(args, "no_threshold", False):
        threshold = getattr(args, "threshold", None)
        if threshold is None:
            threshold = getattr(args, "ar_threshold", 3.0)
        ax.axhline(threshold, color=style["colors"]["gray"], linestyle="--", linewidth=0.9)
        ax.text(0.985, threshold + 0.15, f"{threshold:g} dB", transform=ax.get_yaxis_transform(), ha="right", va="bottom", color=style["colors"]["gray"])
    if first.x_quantity == "frequency":
        draw_frequency_band(ax, args, target_unit, style["colors"].get("gray", "#666666"))
    grid(ax, style, args)
    ax.legend(loc=getattr(args, "legend_loc", None) or style.get("legend", {}).get("loc", "best"))
    output_name = getattr(args, "output_name", None) or "multi_csv_overlay"
    outputs = save_figure(fig, output_dir / output_name, style)
    settings = getattr(args, "project_settings", None)
    metrics_text = None
    if settings is not None:
        metrics_text = format_metric_results(metric_results_for_curves(metric_enabled_curves(curves), settings))
    if _report_file_requested(style):
        report = write_overlay_report(output_dir, output_name, manager, validation, outputs, unit_notes, metrics_text, validation_messages)
        outputs.append(report)
    requested_formats = style.get("export", {}).get("requested_formats", style.get("export", {}).get("formats", []))
    if "json" in {str(item).lower() for item in requested_formats}:
        project_settings = getattr(args, "project_settings", None)
        input_paths = [str(path) for path in getattr(args, "inputs", [])]
        if not input_paths:
            input_paths = sorted(
                {
                    str(curve.metadata.get("source_file"))
                    for curve in manager.curves
                    if curve.metadata.get("source_file")
                }
            )
        overlay_config = {
            "plot_type": getattr(args, "plot_type", "overlay"),
            "input_file_path": input_paths,
            "curves": [curve_summary(curve) for curve in manager.curves],
            "overlay_validation": {
                "allowed": validation.allowed,
                "errors": validation.errors,
                "warnings": validation.warnings,
                "interpolation_required": validation.interpolation_required,
                "interpolation_notes": validation.interpolation_notes or [],
            },
            "messages": [message.__dict__ for message in validation_messages],
            "has_errors": any(message.severity == "error" for message in validation_messages),
            "has_warnings": any(message.severity == "warning" for message in validation_messages),
            "axis_range": {
                "xlabel": getattr(args, "xlabel", None),
                "ylabel": getattr(args, "ylabel", None),
                "xlim": getattr(args, "xlim", None),
                "ylim": getattr(args, "ylim", None),
            },
            "target_band": getattr(getattr(args, "project_settings", None), "working_band_mhz", None),
            "project_settings": {
                "working_band_mhz": getattr(project_settings, "working_band_mhz", None),
                "s11_threshold_db": getattr(project_settings, "s11_threshold_db", None),
                "vswr_threshold": getattr(project_settings, "vswr_threshold", None),
                "axial_ratio_threshold_db": getattr(project_settings, "axial_ratio_threshold_db", None),
                "min_gain_dbi": getattr(project_settings, "min_gain_dbi", None),
                "port_impedance_ohm": getattr(project_settings, "port_impedance_ohm", None),
                "pattern_frequencies_mhz": getattr(project_settings, "pattern_frequencies_mhz", None),
                "prefer_realized_gain": getattr(project_settings, "prefer_realized_gain", None),
            } if project_settings is not None else None,
            "threshold_conditions": {
                "threshold": getattr(args, "threshold", None),
            },
            "export_formats": requested_formats,
            "export_scope": getattr(args, "export_scope", None),
            "manual_config": getattr(args, "manual_config", None),
            "style": {
                "font": style.get("font", {}),
                "line": style.get("line", {}),
                "axis": style.get("axis", {}),
                "figure": style.get("figure", {}),
            },
        }
        outputs.append(write_json_config(output_dir, output_name, jsonable(overlay_config)))
    return outputs


def overlay_csv_files(input_paths: Iterable[Path], output_dir: Path, style: dict, args: Namespace) -> list[Path]:
    files: list[Path] = []
    for path in input_paths:
        files.extend(csv_files(path))
    plot_type = getattr(args, "plot_type", "s11")
    manager = build_curve_manager_from_csv_files(files, plot_type, x_unit=getattr(args, "x_unit", None))
    if not manager.curves:
        raise ValueError("No curves were created from the selected CSV files.")
    return plot_overlay(manager, output_dir, style, args)
