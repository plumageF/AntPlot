"""Radiation-pattern cut and polarization recognition."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

import numpy as np

from .models import Curve
from .reader import HfssDataset, angle_column, pattern_value_columns, phi_column, theta_column


PatternCutType = Literal[
    "horizontal_plane",
    "vertical_plane",
    "theta_cut",
    "phi_cut",
    "2d_farfield_grid",
    "unconfirmed",
]
PolarizationRole = Literal[
    "main_polarization",
    "cross_polarization",
    "RHCP",
    "LHCP",
    "unknown",
]


@dataclass
class PatternInfo:
    theta_column: str | None
    phi_column: str | None
    value_columns: list[str]
    cut_type: PatternCutType
    scan_variable: str | None
    fixed_variable: str | None
    fixed_value_deg: float | None
    is_horizontal_plane: bool = False
    is_vertical_plane: bool = False
    is_grid: bool = False
    warnings: list[str] | None = None

    def description(self) -> str:
        if self.cut_type == "horizontal_plane":
            return "Horizontal plane: theta = 90 deg, phi scan"
        if self.cut_type == "vertical_plane":
            return f"Vertical plane: phi = {self.fixed_value_deg:g} deg, theta scan" if self.fixed_value_deg is not None else "Vertical plane: fixed phi, theta scan"
        if self.cut_type == "theta_cut":
            return f"Theta cut: phi = {self.fixed_value_deg:g} deg" if self.fixed_value_deg is not None else "Theta cut"
        if self.cut_type == "phi_cut":
            return f"Phi cut: theta = {self.fixed_value_deg:g} deg" if self.fixed_value_deg is not None else "Phi cut"
        if self.cut_type == "2d_farfield_grid":
            return "2D far-field grid: theta and phi both vary"
        return "Pattern cut not confirmed"

    def short_title(self) -> str:
        if self.cut_type == "horizontal_plane":
            return "Horizontal Plane Pattern"
        if self.cut_type == "vertical_plane":
            return f"Vertical Plane Pattern, phi = {self.fixed_value_deg:g} deg" if self.fixed_value_deg is not None else "Vertical Plane Pattern"
        if self.cut_type == "theta_cut":
            return f"Theta Cut, phi = {self.fixed_value_deg:g} deg" if self.fixed_value_deg is not None else "Theta Cut"
        if self.cut_type == "phi_cut":
            return f"Phi Cut, theta = {self.fixed_value_deg:g} deg" if self.fixed_value_deg is not None else "Phi Cut"
        if self.cut_type == "2d_farfield_grid":
            return "2D Far-Field Grid"
        return "Radiation Pattern"


def _finite_unique(values: np.ndarray) -> np.ndarray:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return finite
    return np.unique(np.round(finite.astype(float), 6))


def _covers_full_circle(values: np.ndarray) -> bool:
    finite = values[np.isfinite(values)]
    if finite.size < 3:
        return False
    minimum = float(np.nanmin(finite))
    maximum = float(np.nanmax(finite))
    span = maximum - minimum
    return span >= 359.0 or (minimum <= 0.5 and maximum >= 359.0)


def _family_split(theta_unique: np.ndarray, phi_unique: np.ndarray) -> tuple[str | None, str | None, np.ndarray]:
    if theta_unique.size > 1 and phi_unique.size > 1:
        if theta_unique.size >= max(4, phi_unique.size * 3) and phi_unique.size <= 16:
            return "theta", "phi", phi_unique
        if phi_unique.size >= max(4, theta_unique.size * 3) and theta_unique.size <= 16:
            return "phi", "theta", theta_unique
        if theta_unique.size > phi_unique.size and phi_unique.size <= 16:
            return "theta", "phi", phi_unique
        if phi_unique.size > theta_unique.size and theta_unique.size <= 16:
            return "phi", "theta", theta_unique
    return None, None, np.array([])


def recognize_pattern(dataset: HfssDataset, value_columns: list[str] | None = None) -> PatternInfo:
    theta_col = theta_column(dataset.headers)
    phi_col = phi_column(dataset.headers)
    values = value_columns or pattern_value_columns(dataset.headers)
    warnings: list[str] = []
    if not theta_col or not phi_col:
        return PatternInfo(theta_col, phi_col, values, "unconfirmed", None, None, None, warnings=["Theta or phi column is missing; cut plane is not confirmed."])

    theta = dataset.column(theta_col)
    phi = dataset.column(phi_col)
    theta_unique = _finite_unique(theta)
    phi_unique = _finite_unique(phi)
    theta_constant = theta_unique.size == 1
    phi_constant = phi_unique.size == 1

    if theta_constant and phi_unique.size > 1:
        fixed = float(theta_unique[0])
        if abs(fixed - 90.0) <= 1e-3 and _covers_full_circle(phi):
            return PatternInfo(theta_col, phi_col, values, "horizontal_plane", "phi", "theta", fixed, True, False, False, warnings)
        return PatternInfo(theta_col, phi_col, values, "phi_cut", "phi", "theta", fixed, False, False, False, warnings)
    if phi_constant and theta_unique.size > 1:
        fixed = float(phi_unique[0])
        return PatternInfo(theta_col, phi_col, values, "vertical_plane", "theta", "phi", fixed, False, True, False, warnings)
    if theta_unique.size > 1 and phi_unique.size > 1:
        return PatternInfo(theta_col, phi_col, values, "2d_farfield_grid", None, None, None, False, False, True, warnings)
    warnings.append("Theta and phi do not provide a clear scan/fixed-variable pattern; cut plane is not confirmed.")
    return PatternInfo(theta_col, phi_col, values, "unconfirmed", None, None, None, False, False, False, warnings)


def polarization_role(column: str) -> PolarizationRole:
    text = re.sub(r"[^a-z0-9]", "", column.lower())
    if "rhcp" in text:
        return "RHCP"
    if "lhcp" in text:
        return "LHCP"
    if "cross" in text or "xpol" in text or "xp" == text:
        return "cross_polarization"
    if "copol" in text or "mainpol" in text or "principal" in text:
        return "main_polarization"
    return "unknown"


def normalized_pattern_label(is_normalized: bool) -> str:
    return "Normalized Gain (dB)" if is_normalized else "Gain (dBi)"


def compact_pattern_label(column: str) -> str:
    role = polarization_role(column)
    if role == "main_polarization":
        return "Co-pol"
    if role == "cross_polarization":
        return "Cross-pol"
    if role == "RHCP":
        return "RHCP"
    if role == "LHCP":
        return "LHCP"
    text = re.sub(r"\s*\[[^\]]+\]", "", column).strip()
    text = re.sub(r"\s*\([^\)]*\)", "", text).strip()
    return text or column


def pattern_curves_from_dataset(dataset: HfssDataset, *, normalize: bool = False) -> list[Curve]:
    info = recognize_pattern(dataset)
    angle_col = angle_column(dataset.headers)
    if (not info.theta_column or not info.phi_column) and angle_col:
        values = pattern_value_columns(dataset.headers)
        if not values:
            return []
        x_data = dataset.column(angle_col)
        curves: list[Curve] = []
        for column in values:
            y_data = dataset.column(column)
            conversion = None
            y_unit = "dBi"
            if normalize:
                finite = y_data[np.isfinite(y_data)]
                if finite.size:
                    y_data = y_data - float(np.nanmax(finite))
                    y_unit = "dB"
                    conversion = "normalized to 0 dB max"
            lower = column.lower()
            y_quantity = "RealizedGain" if "realized" in lower else "Gain"
            curve = Curve(
                dataset_id=dataset.to_model().dataset_id or "",
                x_data=x_data,
                y_data=y_data,
                x_column=angle_col,
                y_column=column,
                x_quantity="angle",
                y_quantity=y_quantity,  # type: ignore[arg-type]
                x_unit="deg",
                y_unit=y_unit,  # type: ignore[arg-type]
                label=compact_pattern_label(column),
                is_normalized=normalize,
                conversion=conversion,
                warnings=["Pattern cut is not confirmed from Angle-only data; do not label it E-plane or H-plane unless confirmed by the user."],
                metadata={
                    "cut_type": "unconfirmed",
                    "cut": "Angle scan; cut plane not confirmed",
                    "scan_variable": "angle",
                    "fixed_variable": None,
                    "fixed_value_deg": None,
                    "polarization_role": polarization_role(column),
                },
            )
            curves.append(curve)
        return curves
    if not info.theta_column or not info.phi_column or not info.value_columns:
        return []
    theta = dataset.column(info.theta_column)
    phi = dataset.column(info.phi_column)
    theta_unique = _finite_unique(theta)
    phi_unique = _finite_unique(phi)
    split_scan, split_family, split_values = _family_split(theta_unique, phi_unique)
    if info.cut_type == "2d_farfield_grid" and not (split_scan and split_family):
        return []
    if info.cut_type == "2d_farfield_grid" and split_scan and split_family:
        curves: list[Curve] = []
        x_data_all = theta if split_scan == "theta" else phi
        x_column = info.theta_column if split_scan == "theta" else info.phi_column
        family_data = phi if split_family == "phi" else theta
        family_column = info.phi_column if split_family == "phi" else info.theta_column
        for column in info.value_columns:
            lower = column.lower()
            y_quantity = "RealizedGain" if "realized" in lower else "Gain"
            for family_value in split_values:
                mask = np.isfinite(family_data) & (np.abs(family_data - family_value) <= 1e-6)
                if not np.any(mask):
                    continue
                order = np.argsort(x_data_all[mask])
                x_data = x_data_all[mask][order]
                y_data = dataset.column(column)[mask][order]
                conversion = None
                y_unit = "dBi"
                if normalize:
                    finite = y_data[np.isfinite(y_data)]
                    if finite.size:
                        y_data = y_data - float(np.nanmax(finite))
                        y_unit = "dB"
                        conversion = "normalized to 0 dB max"
                family_label = f"{family_column}={float(family_value):g} deg"
                curve_label = f"{compact_pattern_label(column)} ({family_label})"
                curves.append(
                    Curve(
                        dataset_id=dataset.to_model().dataset_id or "",
                        x_data=x_data,
                        y_data=y_data,
                        x_column=x_column,
                        y_column=column,
                        x_quantity=split_scan,  # type: ignore[arg-type]
                        y_quantity=y_quantity,  # type: ignore[arg-type]
                        x_unit="deg",
                        y_unit=y_unit,  # type: ignore[arg-type]
                        label=curve_label,
                        is_normalized=normalize,
                        conversion=conversion,
                        warnings=[
                            "2D far-field table was split into cut-family curves; confirm whether these cuts should be labeled E-plane/H-plane."
                        ],
                        metadata={
                            "cut_type": "cut_family",
                            "cut": f"{split_scan.capitalize()} scan, {family_label}",
                            "scan_variable": split_scan,
                            "fixed_variable": family_column,
                            "fixed_value_deg": float(family_value),
                            "family_variable": family_column,
                            "family_value_deg": float(family_value),
                            "polarization_role": polarization_role(column),
                        },
                    )
                )
        if curves:
            return curves
        return []
    if info.scan_variable == "phi":
        x_data = phi
        x_column = info.phi_column
        x_quantity = "phi"
    else:
        x_data = theta
        x_column = info.theta_column
        x_quantity = "theta"
    curves: list[Curve] = []
    for column in info.value_columns:
        y_data = dataset.column(column)
        conversion = None
        y_unit = "dBi"
        if normalize:
            finite = y_data[np.isfinite(y_data)]
            if finite.size:
                y_data = y_data - float(np.nanmax(finite))
                y_unit = "dB"
                conversion = "normalized to 0 dB max"
        lower = column.lower()
        y_quantity = "RealizedGain" if "realized" in lower else "Gain"
        curve = Curve(
            dataset_id=dataset.to_model().dataset_id or "",
            x_data=x_data,
            y_data=y_data,
            x_column=x_column,
            y_column=column,
            x_quantity=x_quantity,  # type: ignore[arg-type]
            y_quantity=y_quantity,  # type: ignore[arg-type]
            x_unit="deg",
            y_unit=y_unit,  # type: ignore[arg-type]
            label=column,
            is_normalized=normalize,
            conversion=conversion,
            warnings=list(info.warnings or []),
            metadata={
                "cut_type": info.cut_type,
                "cut": info.description(),
                "scan_variable": info.scan_variable,
                "fixed_variable": info.fixed_variable,
                "fixed_value_deg": info.fixed_value_deg,
                "polarization_role": polarization_role(column),
            },
        )
        curves.append(curve)
    return curves
