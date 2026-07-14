"""Sampling-point policy for imported electromagnetic data."""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from .models import Curve


LOW_SAMPLE_SEVERE_LIMIT = 10
LOW_SAMPLE_WARNING_LIMIT = 30
LARGE_PREVIEW_SAMPLE_LIMIT = 10000


def sample_count_from_xy(x_data: np.ndarray, y_data: np.ndarray) -> int:
    return int(min(len(x_data), len(y_data)))


def sample_count_warning(sample_count: int) -> str | None:
    if sample_count < LOW_SAMPLE_SEVERE_LIMIT:
        return (
            f"sample_count={sample_count} < 10: severe warning; curve trend and metric calculation "
            "may be unreliable."
        )
    if sample_count < LOW_SAMPLE_WARNING_LIMIT:
        return (
            f"sample_count={sample_count} is between 10 and 30: warning; radiation pattern, bandwidth, "
            "and HPBW calculations may be unstable."
        )
    return None


def duplicate_x_count(x_data: np.ndarray) -> int:
    finite = x_data[np.isfinite(x_data)]
    if finite.size == 0:
        return 0
    rounded = np.round(finite.astype(float), 12)
    return int(len(rounded) - len(set(rounded.tolist())))


def unique_x_count(x_data: np.ndarray) -> int:
    finite = x_data[np.isfinite(x_data)]
    if finite.size == 0:
        return 0
    rounded = np.round(finite.astype(float), 12)
    return int(len(set(rounded.tolist())))


def default_marker_every(sample_count: int) -> int:
    if sample_count < 30:
        return 1
    if sample_count < 300:
        return 10
    return 50


def curve_sampling_warnings(curve: Curve) -> list[str]:
    warnings: list[str] = []
    sample_count = sample_count_from_xy(curve.x_data, curve.y_data)
    low_sample = sample_count_warning(sample_count)
    if low_sample:
        warnings.append(low_sample)
    paired_len = min(len(curve.x_data), len(curve.y_data))
    if len(curve.x_data) != len(curve.y_data):
        warnings.append(
            f"X/Y sample lengths differ: len(x)={len(curve.x_data)}, len(y)={len(curve.y_data)}; "
            f"only {paired_len} paired samples can be plotted."
        )
    if paired_len:
        finite_pair = np.isfinite(curve.x_data[:paired_len]) & np.isfinite(curve.y_data[:paired_len])
        missing = int(paired_len - np.count_nonzero(finite_pair))
        if missing:
            warnings.append(f"Missing or non-finite X/Y values detected in {missing} paired samples.")
    duplicates = duplicate_x_count(curve.x_data[:paired_len])
    if duplicates:
        warnings.append(f"Duplicate X samples detected: {duplicates}. Original duplicated samples are preserved.")
    if sample_count > LARGE_PREVIEW_SAMPLE_LIMIT:
        warnings.append(
            f"sample_count={sample_count} > 10000: frontend preview may use display-only downsampling; "
            "formal export and metrics must use original samples."
        )
    return warnings


def sort_curve_by_x(curve: Curve) -> Curve:
    paired_len = min(len(curve.x_data), len(curve.y_data))
    if paired_len <= 1:
        return curve
    x_data = curve.x_data[:paired_len]
    y_data = curve.y_data[:paired_len]
    order = np.argsort(x_data, kind="mergesort")
    sorted_curve = replace(
        curve,
        x_data=x_data[order],
        y_data=y_data[order],
        metadata={
            **curve.metadata,
            "sampling_policy": "raw samples preserved; X/Y pairs sorted by X ascending only",
            "sample_count": int(paired_len),
            "sorted_by_x": True,
        },
    )
    if len(curve.x_data) != paired_len or len(curve.y_data) != paired_len:
        sorted_curve.metadata["original_x_length"] = int(len(curve.x_data))
        sorted_curve.metadata["original_y_length"] = int(len(curve.y_data))
    return sorted_curve


def apply_sampling_policy(curve: Curve) -> Curve:
    updated = curve if curve.metadata.get("preserve_order") else sort_curve_by_x(curve)
    sample_count = sample_count_from_xy(updated.x_data, updated.y_data)
    duplicates = duplicate_x_count(updated.x_data)
    existing = list(updated.warnings)
    if not updated.metadata.get("xy_multi_curve"):
        for warning in curve_sampling_warnings(updated):
            if warning not in existing:
                existing.append(warning)
    return replace(
        updated,
        warnings=existing,
        metadata={
            **updated.metadata,
            "sample_count": sample_count,
            "raw_sample_count": sample_count,
            "unique_x_count": unique_x_count(updated.x_data),
            "displayed_sample_count": sample_count,
            "duplicate_x_count": duplicates,
            "duplicate_x_count_after_grouping": duplicates,
            "marker_every": updated.metadata.get("marker_every", default_marker_every(sample_count)),
            "sample_display_policy": updated.metadata.get("sample_display_policy", "marker_only_decimate"),
            "plotting_default": "raw samples; no smoothing, interpolation, resampling, point filling, or outlier deletion",
        },
    )
