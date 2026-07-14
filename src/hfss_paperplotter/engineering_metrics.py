"""Engineering metric calculations from raw imported data and Curves."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import re

from .metrics import s11_band, threshold_crossings
from .messages import Message, format_messages, message_from_text
from .models import Curve
from .pattern_analysis import pattern_curves_from_dataset, polarization_role, recognize_pattern
from .project_settings import ProjectSettings
from .reader import (
    HfssDataset,
    axial_ratio_column,
    curve_from_columns,
    frequency_column,
    gain_column,
    pattern_value_columns,
    phi_column,
    s11_column,
    theta_column,
    to_ghz,
    vswr_column,
)
from .s11_import import s11_curves_from_dataset


@dataclass
class MetricResult:
    curve_label: str
    metric_type: str
    values: dict[str, object] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    interpolation_notes: list[str] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)


def _finite_xy(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mask = np.isfinite(x) & np.isfinite(y)
    x = x[mask]
    y = y[mask]
    if x.size <= 1:
        return x, y
    order = np.argsort(x)
    return x[order], y[order]


def _x_to_mhz(curve: Curve) -> np.ndarray:
    if curve.x_unit == "Hz":
        return curve.x_data / 1.0e6
    if curve.x_unit == "GHz":
        return curve.x_data * 1000.0
    return curve.x_data.copy()


def _coverage_status(x_mhz: np.ndarray, band: tuple[float, float] | None) -> tuple[bool | None, str]:
    finite = x_mhz[np.isfinite(x_mhz)]
    if finite.size == 0:
        return False, "No finite frequency samples."
    if band is None:
        return None, "Working band not specified; pass/fail target-band judgment was not made."
    lo, hi = band
    covered = float(np.nanmin(finite)) <= lo and float(np.nanmax(finite)) >= hi
    if covered:
        return True, f"Data covers target band {lo:g}-{hi:g} MHz."
    return False, f"Data range {float(np.nanmin(finite)):.6g}-{float(np.nanmax(finite)):.6g} MHz does not fully cover target band {lo:g}-{hi:g} MHz."


def _band_mask(x_mhz: np.ndarray, band: tuple[float, float] | None) -> np.ndarray:
    if band is None:
        return np.isfinite(x_mhz)
    lo, hi = band
    return np.isfinite(x_mhz) & (x_mhz >= lo) & (x_mhz <= hi)


def _format_ranges(ranges: list[tuple[float, float]]) -> str:
    if not ranges:
        return "none"
    return "; ".join(f"{lo:.6g}-{hi:.6g} MHz" for lo, hi in ranges)


def ranges_where(x: np.ndarray, mask: np.ndarray) -> list[tuple[float, float]]:
    ranges: list[tuple[float, float]] = []
    start: float | None = None
    for index, inside in enumerate(mask):
        if inside and start is None:
            start = float(x[index])
        if start is not None and (not inside or index == len(mask) - 1):
            end_index = index if inside and index == len(mask) - 1 else max(index - 1, 0)
            ranges.append((start, float(x[end_index])))
            start = None
    return ranges


def threshold_pass_ranges(x: np.ndarray, y: np.ndarray, threshold: float, *, less_equal: bool) -> list[tuple[float, float]]:
    x, y = _finite_xy(x, y)
    if x.size == 0:
        return []
    ok = y <= threshold if less_equal else y >= threshold
    return ranges_where(x, ok)


def threshold_fail_ranges(x: np.ndarray, y: np.ndarray, threshold: float, *, less_equal: bool) -> list[tuple[float, float]]:
    x, y = _finite_xy(x, y)
    if x.size == 0:
        return []
    failed = y > threshold if less_equal else y < threshold
    return ranges_where(x, failed)


def s11_metrics(curve: Curve, settings: ProjectSettings) -> MetricResult:
    x_mhz, y = _finite_xy(_x_to_mhz(curve), curve.y_data)
    result = MetricResult(curve.label, "S11")
    covered, coverage_note = _coverage_status(x_mhz, settings.working_band_mhz)
    result.values["data_covers_target_band"] = covered
    if covered is False:
        result.warnings.append(coverage_note)
        result.messages.append(message_from_text("warning", coverage_note, code="target_band_not_fully_covered"))
    mask = _band_mask(x_mhz, settings.working_band_mhz)
    if settings.working_band_mhz and np.any(mask):
        result.values["max_s11_in_target_band_db"] = float(np.nanmax(y[mask]))
        result.values["satisfies_s11_threshold_in_target_band"] = bool(np.nanmax(y[mask]) <= settings.s11_threshold_db)
    else:
        result.values["max_s11_in_target_band_db"] = "not available"
        result.values["satisfies_s11_threshold_in_target_band"] = "not judged"
    if y.size:
        min_index = int(np.nanargmin(y))
        result.values["lowest_resonance_frequency_mhz"] = float(x_mhz[min_index])
        result.values["lowest_s11_db"] = float(y[min_index])
    band = s11_band(x_mhz, y, settings.s11_threshold_db) if x_mhz.size >= 2 else None
    if band and {"fl", "fh", "bw"} <= set(band):
        result.values["minus_10db_band_mhz"] = f"{band['fl']:.6g}-{band['fh']:.6g}"
        result.values["minus_10db_bandwidth_mhz"] = float(band["bw"])
        result.values["minus_10db_center_mhz"] = float(band["fc"])
        result.values["minus_10db_fractional_bandwidth_percent"] = float(band["fbw"])
        result.interpolation_notes.append("S11 threshold crossings use linear interpolation between adjacent raw samples.")
    else:
        result.values["minus_10db_band_mhz"] = "not found"
    if settings.working_band_mhz and np.any(mask):
        result.values["all_target_band_s11_le_threshold"] = bool(np.nanmax(y[mask]) <= settings.s11_threshold_db)
    else:
        result.values["all_target_band_s11_le_threshold"] = "not judged"
    return result


def vswr_metrics(curve: Curve, settings: ProjectSettings) -> MetricResult:
    x_mhz, y = _finite_xy(_x_to_mhz(curve), curve.y_data)
    result = MetricResult(curve.label, "VSWR")
    covered, coverage_note = _coverage_status(x_mhz, settings.working_band_mhz)
    result.values["data_covers_target_band"] = covered
    if covered is False:
        result.warnings.append(coverage_note)
        result.messages.append(message_from_text("warning", coverage_note, code="target_band_not_fully_covered"))
    mask = _band_mask(x_mhz, settings.working_band_mhz)
    if settings.working_band_mhz and np.any(mask):
        band_y = y[mask]
        result.values["max_vswr_in_target_band"] = float(np.nanmax(band_y))
        result.values["min_vswr_in_target_band"] = float(np.nanmin(band_y))
        result.values["satisfies_vswr_threshold"] = bool(np.nanmax(band_y) <= settings.vswr_threshold)
    else:
        result.values["max_vswr_in_target_band"] = "not available"
        result.values["min_vswr_in_target_band"] = "not available"
        result.values["satisfies_vswr_threshold"] = "not judged"
    result.values["out_of_spec_ranges_mhz"] = _format_ranges(
        threshold_fail_ranges(x_mhz, y, settings.vswr_threshold, less_equal=True)
    )
    return result


def gain_metrics(curve: Curve, settings: ProjectSettings) -> MetricResult:
    x_mhz, y = _finite_xy(_x_to_mhz(curve), curve.y_data)
    result = MetricResult(curve.label, "Gain")
    covered, coverage_note = _coverage_status(x_mhz, settings.working_band_mhz)
    result.values["data_covers_target_band"] = covered
    if covered is False:
        result.warnings.append(coverage_note)
        result.messages.append(message_from_text("warning", coverage_note, code="target_band_not_fully_covered"))
    mask = _band_mask(x_mhz, settings.working_band_mhz)
    if settings.working_band_mhz and np.any(mask):
        band_y = y[mask]
        min_gain = float(np.nanmin(band_y))
        max_gain = float(np.nanmax(band_y))
        result.values["min_gain_in_target_band_dbi"] = min_gain
        result.values["max_gain_in_target_band_dbi"] = max_gain
        result.values["gain_ripple_db"] = max_gain - min_gain
        result.values["satisfies_min_gain"] = bool(min_gain >= settings.min_gain_dbi)
    else:
        result.values["min_gain_in_target_band_dbi"] = "not available"
        result.values["max_gain_in_target_band_dbi"] = "not available"
        result.values["gain_ripple_db"] = "not available"
        result.values["satisfies_min_gain"] = "not judged"
    return result


def ar_metrics(curve: Curve, settings: ProjectSettings) -> MetricResult:
    x_mhz, y = _finite_xy(_x_to_mhz(curve), curve.y_data)
    result = MetricResult(curve.label, "Axial Ratio")
    covered, coverage_note = _coverage_status(x_mhz, settings.working_band_mhz)
    result.values["data_covers_target_band"] = covered
    if covered is False:
        result.warnings.append(coverage_note)
        result.messages.append(message_from_text("warning", coverage_note, code="target_band_not_fully_covered"))
    mask = _band_mask(x_mhz, settings.working_band_mhz)
    if settings.working_band_mhz and np.any(mask):
        max_ar = float(np.nanmax(y[mask]))
        result.values["max_ar_in_target_band_db"] = max_ar
        result.values["satisfies_circular_polarization"] = bool(max_ar <= settings.axial_ratio_threshold_db)
    else:
        result.values["max_ar_in_target_band_db"] = "not available"
        result.values["satisfies_circular_polarization"] = "not judged"
    result.values["ar_le_threshold_ranges_mhz"] = _format_ranges(
        threshold_pass_ranges(x_mhz, y, settings.axial_ratio_threshold_db, less_equal=True)
    )
    return result


def _beamwidth_3db(angle: np.ndarray, gain: np.ndarray) -> tuple[float | None, str | None]:
    angle, gain = _finite_xy(angle, gain)
    if angle.size < 3:
        return None, "3 dB beamwidth requires at least three finite angular samples."
    max_index = int(np.nanargmax(gain))
    threshold = float(gain[max_index]) - 3.0
    crossings = threshold_crossings(angle, gain, threshold)
    left = [value for value in crossings if value <= angle[max_index]]
    right = [value for value in crossings if value >= angle[max_index]]
    if not left or not right:
        return None, "Could not find both 3 dB beamwidth crossings."
    return float(min(right) - max(left)), "3 dB beamwidth crossings use linear interpolation between adjacent raw angular samples."


def pattern_metrics(dataset: HfssDataset, settings: ProjectSettings, *, gain_col: str | None = None) -> list[MetricResult]:
    theta_col = theta_column(dataset.headers)
    phi_col = phi_column(dataset.headers)
    value_cols = [gain_col] if gain_col else pattern_value_columns(dataset.headers)
    value_cols = [column for column in value_cols if column]
    if not theta_col or not phi_col or not value_cols:
        return [MetricResult("Radiation Pattern", "Pattern", warnings=["Pattern metrics require theta, phi, and gain/polarization columns."])]

    theta = dataset.column(theta_col)
    phi = dataset.column(phi_col)
    pattern_info = recognize_pattern(dataset, value_cols)
    results: list[MetricResult] = []
    lowered = {column: re.sub(r"[^a-z0-9]", "", column.lower()) for column in value_cols}

    def paired_cross_column(main_column: str) -> str | None:
        name = lowered[main_column]
        if "cross" in name or "xpol" in name:
            return None
        if "copol" in name or name.startswith("co"):
            return next((column for column, text in lowered.items() if "cross" in text or "xpol" in text), None)
        if "rhcp" in name:
            return next((column for column, text in lowered.items() if "lhcp" in text), None)
        if "lhcp" in name:
            return next((column for column, text in lowered.items() if "rhcp" in text), None)
        return None

    for column in value_cols:
        gain = dataset.column(column)
        finite = np.isfinite(theta) & np.isfinite(phi) & np.isfinite(gain)
        if not np.any(finite):
            results.append(MetricResult(column, "Pattern", warnings=["No finite pattern samples."], messages=[Message("error", "empty_data", "No finite pattern samples.", {})]))
            continue
        theta_f = theta[finite]
        phi_f = phi[finite]
        gain_f = gain[finite]
        max_index = int(np.nanargmax(gain_f))
        result = MetricResult(column, "Pattern")
        result.values["cut_type"] = pattern_info.cut_type
        result.values["cut_description"] = pattern_info.description()
        result.values["polarization_role"] = polarization_role(column)
        result.values["max_gain_db"] = float(gain_f[max_index])
        result.values["max_radiation_direction"] = f"theta={theta_f[max_index]:.6g} deg, phi={phi_f[max_index]:.6g} deg"
        result.values["front_to_back_ratio_db"] = "not available"
        opposite_theta = (theta_f[max_index] + 180.0) % 360.0
        opposite_phi = (phi_f[max_index] + 180.0) % 360.0
        distance = np.abs(((theta_f - opposite_theta + 180.0) % 360.0) - 180.0) + np.abs(((phi_f - opposite_phi + 180.0) % 360.0) - 180.0)
        if distance.size:
            back_index = int(np.nanargmin(distance))
            if float(distance[back_index]) <= 5.0:
                result.values["front_to_back_ratio_db"] = float(gain_f[max_index] - gain_f[back_index])
            else:
                text = "No sampled point close to the opposite radiation direction; front-to-back ratio was not calculated."
                result.warnings.append(text)
                result.messages.append(Message("warning", "pattern_back_direction_missing", text, {}))
        result.values["omnidirectional_ripple_db"] = float(np.nanmax(gain_f) - np.nanmin(gain_f))

        unique_theta = np.unique(np.round(theta_f, 9))
        unique_phi = np.unique(np.round(phi_f, 9))
        if pattern_info.scan_variable == "theta" and unique_theta.size > 1:
            width, note = _beamwidth_3db(theta_f, gain_f)
            result.values["beamwidth_3db_deg"] = width if width is not None else "not available"
            if note:
                result.interpolation_notes.append(note)
        elif pattern_info.scan_variable == "phi" and unique_phi.size > 1:
            width, note = _beamwidth_3db(phi_f, gain_f)
            result.values["beamwidth_3db_deg"] = width if width is not None else "not available"
            if note:
                result.interpolation_notes.append(note)
        else:
            result.values["beamwidth_3db_deg"] = "not available"
            text = "Pattern cut is not a confirmed single theta or phi sweep; 3 dB beamwidth was not calculated."
            result.warnings.append(text)
            result.messages.append(Message("warning", "pattern_cut_unconfirmed", text, {}))
        if pattern_info.warnings:
            result.warnings.extend(pattern_info.warnings)
            result.messages.extend(message_from_text("warning", warning, code="pattern_cut_unconfirmed") for warning in pattern_info.warnings)

        cross_column = paired_cross_column(column)
        if cross_column:
            cross = dataset.column(cross_column)[finite]
            diff = gain_f - cross
            finite_diff = diff[np.isfinite(diff)]
            result.values["paired_cross_polarization_column"] = cross_column
            result.values["main_cross_difference_at_main_beam_db"] = float(diff[max_index]) if np.isfinite(diff[max_index]) else "not available"
            result.values["minimum_main_cross_difference_db"] = float(np.nanmin(finite_diff)) if finite_diff.size else "not available"
        elif "cross" in lowered[column] or "xpol" in lowered[column]:
            result.values["co_cross_polarization_difference_db"] = "not judged; this column appears to be cross-polarized, but the main-polarization column is not explicit."
        else:
            result.values["co_cross_polarization_difference_db"] = "not judged; main polarization is not explicit."
        results.append(result)
    return results


def metric_for_curve(curve: Curve, settings: ProjectSettings) -> MetricResult | None:
    if curve.metadata.get("cut_type"):
        angle, gain = _finite_xy(curve.x_data, curve.y_data)
        result = MetricResult(curve.label, "Pattern")
        result.values["cut_type"] = curve.metadata.get("cut_type")
        result.values["cut_description"] = curve.metadata.get("cut")
        result.values["polarization_role"] = curve.metadata.get("polarization_role", "unknown")
        if gain.size:
            max_index = int(np.nanargmax(gain))
            result.values["max_gain_db"] = float(gain[max_index])
            result.values["max_radiation_direction"] = f"{curve.x_quantity}={angle[max_index]:.6g} deg"
            result.values["omnidirectional_ripple_db"] = float(np.nanmax(gain) - np.nanmin(gain))
            width, note = _beamwidth_3db(angle, gain)
            result.values["beamwidth_3db_deg"] = width if width is not None else "not available"
            if note:
                result.interpolation_notes.append(note)
        else:
            text = "No finite pattern samples."
            result.warnings.append(text)
            result.messages.append(Message("error", "empty_data", text, {}))
        return result
    if curve.y_quantity == "S11":
        return s11_metrics(curve, settings)
    if curve.y_quantity == "VSWR":
        return vswr_metrics(curve, settings)
    if curve.y_quantity in {"Gain", "RealizedGain"}:
        return gain_metrics(curve, settings)
    if curve.y_quantity == "AR":
        return ar_metrics(curve, settings)
    return None


def curves_from_dataset_for_metrics(dataset: HfssDataset, command: str) -> list[Curve]:
    command = command.lower()
    if command == "s11":
        return s11_curves_from_dataset(dataset, x_unit="MHz").curves
    if command == "pattern":
        return pattern_curves_from_dataset(dataset, normalize=False)
    x_col = frequency_column(dataset.headers)
    if not x_col:
        return []
    y_cols: list[str] = []
    if command == "vswr":
        y_cols = [vswr_column(dataset.headers) or ""]
    elif command == "gain":
        y_cols = [gain_column(dataset.headers) or ""]
    elif command == "ar":
        y_cols = [axial_ratio_column(dataset.headers) or ""]
    return [
        curve_from_columns(dataset, x_col, y_col, x_unit="MHz", label=y_col)
        for y_col in y_cols
        if y_col
    ]


def metric_results_for_dataset(dataset: HfssDataset, command: str, settings: ProjectSettings) -> list[MetricResult]:
    if command == "pattern":
        return pattern_metrics(dataset, settings)
    results: list[MetricResult] = []
    for curve in curves_from_dataset_for_metrics(dataset, command):
        metric = metric_for_curve(curve, settings)
        if metric:
            results.append(metric)
    if not results:
        results.append(MetricResult(command, command, warnings=["No metric-compatible curve was detected."]))
    return results


def metric_results_for_curves(curves: Iterable[Curve], settings: ProjectSettings) -> list[MetricResult]:
    results: list[MetricResult] = []
    for curve in curves:
        metric = metric_for_curve(curve, settings)
        if metric:
            results.append(metric)
    return results


def format_metric_results(results: list[MetricResult]) -> str:
    lines = ["Engineering metrics:"]
    for result in results:
        lines.append(f"- Curve: {result.curve_label} [{result.metric_type}]")
        for key, value in result.values.items():
            lines.append(f"  {key}: {value}")
        if result.interpolation_notes:
            lines.append("  interpolation:")
            lines.extend(f"    - {item}" for item in result.interpolation_notes)
        if result.warnings:
            lines.append("  warnings:")
            lines.extend(f"    - {item}" for item in result.warnings)
        if result.messages:
            lines.append("  structured_messages:")
            for message in result.messages:
                lines.append(f"    - {message.severity.upper()} [{message.code}] {message.text}")
    return "\n".join(lines)


def collect_metric_messages(results: list[MetricResult]) -> list[Message]:
    messages: list[Message] = []
    for result in results:
        messages.extend(result.messages)
        for warning in result.warnings:
            if not any(message.text == warning for message in result.messages):
                messages.append(message_from_text("warning", warning))
        for note in result.interpolation_notes:
            messages.append(Message("info", "interpolation", note, {}))
    return messages
