"""HFSS-like report planning for imported tabular data.

This layer describes how a CSV resembles an HFSS Report before any curve is
created.  It keeps the physical interpretation in the backend and gives the UI
an explicit structure to display and confirm.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .models import infer_x_unit, infer_y_quantity, infer_y_unit
from .pattern_analysis import recognize_pattern
from .reader import (
    HfssDataset,
    angle_column,
    axial_ratio_column,
    candidate_y_columns,
    complex_s_column,
    detect_kind,
    efficiency_column,
    frequency_column,
    gain_column,
    has_complex_values,
    hpbw_column,
    is_numeric_column,
    normalize,
    pattern_value_columns,
    phi_column,
    s11_column,
    smith_imag_column,
    smith_real_column,
    theta_column,
    vswr_column,
)


@dataclass
class SweepVariable:
    column: str
    quantity: str
    unit: str | None
    role: str
    minimum: float | None
    maximum: float | None
    unique_count: int
    values: list[float] = field(default_factory=list)


@dataclass
class QuantityColumn:
    column: str
    quantity: str
    unit: str | None
    role: str
    conversion: str | None = None


@dataclass
class CurvePlan:
    x_column: str
    y_column: str
    label: str
    x_quantity: str
    y_quantity: str
    x_unit: str | None
    y_unit: str | None
    fixed_context: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ReportPlan:
    dataset_id: str
    source_file: str
    result_domain: str
    data_type: str
    primary_sweep: SweepVariable | None
    fixed_variables: list[SweepVariable]
    family_variables: list[SweepVariable]
    quantity_columns: list[QuantityColumn]
    compatible_plot_types: list[str]
    recommended_plot_type: str
    recommended_display_mode: str | None
    curve_family_strategy: str
    curve_plans: list[CurvePlan]
    requires_confirmation: bool
    confirmation_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    report_model: ReportModel | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "source_file": self.source_file,
            "result_domain": self.result_domain,
            "data_type": self.data_type,
            "primary_sweep": _sweep_to_dict(self.primary_sweep),
            "fixed_variables": [_sweep_to_dict(item) for item in self.fixed_variables],
            "family_variables": [_sweep_to_dict(item) for item in self.family_variables],
            "quantity_columns": [item.__dict__ for item in self.quantity_columns],
            "compatible_plot_types": self.compatible_plot_types,
            "recommended_plot_type": self.recommended_plot_type,
            "recommended_display_mode": self.recommended_display_mode,
            "curve_family_strategy": self.curve_family_strategy,
            "curve_plans": [item.__dict__ for item in self.curve_plans],
            "requires_confirmation": self.requires_confirmation,
            "confirmation_reasons": self.confirmation_reasons,
            "warnings": self.warnings,
            "errors": self.errors,
            "report_model": self.report_model.to_dict() if self.report_model else None,
        }


@dataclass
class ReportFamily:
    name: str
    role: str
    column: str | None = None
    value: Any = None
    unit: str | None = None
    source: str | None = None


@dataclass
class ReportModel:
    dataset_id: str
    source_file: str
    report_domain: str
    report_type: str
    primary_sweep: str
    quantity: str
    families: list[ReportFamily]
    compatible_plot_types: list[str]
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    infos: list[str] = field(default_factory=list)
    requires_confirmation: bool = False
    data_class: str = "unknown"
    columns: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "source_file": self.source_file,
            "report_domain": self.report_domain,
            "report_type": self.report_type,
            "primary_sweep": self.primary_sweep,
            "quantity": self.quantity,
            "families": [item.__dict__ for item in self.families],
            "compatible_plot_types": self.compatible_plot_types,
            "warnings": self.warnings,
            "errors": self.errors,
            "infos": self.infos,
            "requires_confirmation": self.requires_confirmation,
            "data_class": self.data_class,
            "columns": self.columns,
        }


def _finite_unique(values: np.ndarray) -> np.ndarray:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return finite
    return np.unique(np.round(finite.astype(float), 6))


def _value_range(values: np.ndarray) -> tuple[float | None, float | None]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return None, None
    return float(np.nanmin(finite)), float(np.nanmax(finite))


def _small_values(unique_values: np.ndarray, limit: int = 12) -> list[float]:
    if unique_values.size > limit:
        return []
    return [float(item) for item in unique_values]


def _quantity_for_column(column: str) -> str:
    text = normalize(column)
    if "theta" in text:
        return "theta"
    if "phi" in text:
        return "phi"
    if "angle" in text or text in {"deg", "degree"}:
        return "angle"
    if "freq" in text:
        return "frequency"
    return "parameter"


def _sweep(dataset: HfssDataset, column: str, role: str) -> SweepVariable:
    values = dataset.column(column)
    unique = _finite_unique(values)
    minimum, maximum = _value_range(values)
    unit = dataset.parse_report.units.get(column) if dataset.parse_report else None
    if unit is None:
        unit = infer_x_unit(column, unit)
    return SweepVariable(
        column=column,
        quantity=_quantity_for_column(column),
        unit=unit,
        role=role,
        minimum=minimum,
        maximum=maximum,
        unique_count=int(unique.size),
        values=_small_values(unique),
    )


def _sweep_to_dict(item: SweepVariable | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return item.__dict__


def _is_generic_column(column: str) -> bool:
    return normalize(column) in {"x", "y", "data", "value", "formatteddata"}


def _parameter_pairs(text: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for name, value in re.findall(r"([A-Za-z_]\w*)\s*=\s*'([^']+)'", text):
        pairs[name] = value
    for name, value in re.findall(r"([A-Za-z_]\w*)\s*=\s*\"([^\"]+)\"", text):
        pairs.setdefault(name, value)
    return pairs


def _unique_count(dataset: HfssDataset, column: str | None) -> int:
    if not column:
        return 0
    return int(_finite_unique(dataset.column(column)).size)


def _single_value_family(dataset: HfssDataset, column: str, name: str) -> ReportFamily | None:
    values = _finite_unique(dataset.column(column))
    if values.size != 1:
        return None
    unit = dataset.parse_report.units.get(column) if dataset.parse_report else None
    return ReportFamily(name=name, role="fixed_variable", column=column, value=float(values[0]), unit=unit)


def _quantity_from_headers(dataset: HfssDataset) -> tuple[str, str | None]:
    headers = dataset.headers
    joined = " ".join(headers)
    text = normalize(joined)
    if smith_real_column(headers) and smith_imag_column(headers):
        if any("z" in normalize(column) for column in headers):
            return "Impedance", smith_real_column(headers)
        return "ComplexS", smith_real_column(headers)
    complex_col = complex_s_column(headers)
    if complex_col and has_complex_values(dataset, complex_col):
        return "ComplexS", complex_col
    if "mag" in text and "phase" in text and ("s11" in text or "s11" in text):
        return "ComplexS", next((column for column in headers if "mag" in normalize(column)), None)
    if s11_column(headers):
        s11 = s11_column(headers)
        stext = normalize(s11 or "")
        if "returnloss" in stext:
            return "ReturnLoss_dB", s11
        if "db" in stext or "logs" in stext or "logmag" in stext:
            return "S11_dB", s11
        if "mag" in stext:
            return "ComplexS", s11
        return "S11_dB", s11
    if vswr_column(headers):
        return "VSWR", vswr_column(headers)
    ar = axial_ratio_column(headers)
    if ar:
        return "AxialRatio", ar
    eff = efficiency_column(headers)
    if eff:
        etext = normalize(eff)
        if "total" in etext:
            return "TotalEfficiency", eff
        return "RadiationEfficiency", eff
    hpbw = hpbw_column(headers)
    if hpbw:
        return "HPBW", hpbw
    gain = gain_column(headers)
    if gain:
        gtext = normalize(gain)
        if "directivity" in gtext:
            return "Directivity", gain
        if "realized" in gtext:
            return "RealizedGain", gain
        return "Gain", gain
    if "phase" in text:
        return "Phase", next((column for column in headers if "phase" in normalize(column)), None)
    if any("zin" in normalize(column) or normalize(column).startswith("rez") or normalize(column).startswith("imz") for column in headers):
        return "Impedance", next((column for column in headers if "z" in normalize(column)), None)
    return "Unknown", None


def _compatible_plot_names(quantity: str, report_type: str) -> list[str]:
    if report_type in {"radiation_cartesian", "radiation_polar", "radiation_grid"}:
        if quantity == "AxialRatio":
            return ["Axial Ratio", "XY Multi-Curve"] if report_type != "radiation_grid" else ["Axial Ratio"]
        return ["Radiation Pattern", "XY Multi-Curve"] if report_type != "radiation_grid" else ["Radiation Pattern"]
    if report_type == "smith":
        return ["Smith Chart"]
    if quantity in {"S11_dB", "ReturnLoss_dB", "ComplexS"}:
        return ["S11", "VSWR", "Smith Chart"] if quantity in {"S11_dB", "ReturnLoss_dB"} else ["S11", "VSWR", "Smith Chart"]
    if quantity == "VSWR":
        return ["VSWR"]
    if quantity == "RealizedGain":
        return ["Realized Gain"]
    if quantity in {"Gain", "Directivity"}:
        return ["Realized Gain", "XY Multi-Curve"]
    if quantity == "AxialRatio":
        return ["Axial Ratio"]
    if quantity in {"RadiationEfficiency", "TotalEfficiency"}:
        return ["Efficiency"]
    if quantity == "HPBW":
        return ["HPBW"]
    return ["XY Multi-Curve"]


def build_report_model(dataset: HfssDataset, mode: str = "semiauto") -> ReportModel:
    model = dataset.to_model()
    headers = dataset.headers
    warnings: list[str] = []
    errors: list[str] = []
    infos: list[str] = []
    families: list[ReportFamily] = []
    requires_confirmation = mode in {"semiauto", "manual"}

    freq_col = frequency_column(headers)
    theta_col = theta_column(headers)
    phi_col = phi_column(headers)
    angle_col = angle_column(headers)
    if theta_col or phi_col:
        angle_col = None
    quantity, quantity_col = _quantity_from_headers(dataset)
    has_angle = bool(theta_col or phi_col or angle_col)
    has_freq = bool(freq_col)
    theta_varies = _unique_count(dataset, theta_col) > 1
    phi_varies = _unique_count(dataset, phi_col) > 1
    angle_varies = _unique_count(dataset, angle_col) > 1
    if quantity == "ReturnLoss_dB":
        infos.append("Return Loss is normally a positive dB quantity; use +10 dB as the pass threshold.")
        if quantity_col:
            values = dataset.column(quantity_col)
            finite = values[np.isfinite(values)]
            if finite.size and float(np.nanmedian(finite)) < 0:
                warnings.append("Return Loss column contains mostly negative values; this may actually be S11(dB). Confirm sign convention before engineering conclusions.")

    generic_columns = [column for column in headers if _is_generic_column(column)]
    if generic_columns:
        warnings.append("Generic column names detected; physical meaning requires user confirmation.")
        requires_confirmation = True
    if any(normalize(column) == "formatteddata" for column in headers):
        warnings.append("Formatted Data column detected; it may be S11(dB), but must be confirmed by the user.")
        requires_confirmation = True

    parameter_columns = []
    for column in headers:
        params = _parameter_pairs(column)
        if params:
            parameter_columns.append(column)
            for name, value in params.items():
                families.append(ReportFamily(name=name, role="parameter_sweep", column=column, value=value, source="column_name"))

    report_domain = "unknown"
    report_type = "table"
    primary_sweep = "unknown"
    data_class = "unknown"

    complex_col = complex_s_column(headers)
    is_complex = quantity in {"ComplexS", "Impedance"} or bool(smith_real_column(headers) and smith_imag_column(headers)) or bool(complex_col and has_complex_values(dataset, complex_col))
    if is_complex:
        report_domain = "complex_network"
        report_type = "smith"
        primary_sweep = "Freq" if has_freq else "unknown"
        data_class = "complex_network"
        infos.append("Complex network columns detected; Smith Chart is the recommended plot when reference impedance is confirmed.")
    elif has_angle and quantity in {"Gain", "RealizedGain", "Directivity", "AxialRatio", "Unknown"}:
        primary_info, fixed_info, family_info, strategy, pattern_warnings = _pattern_family(dataset)
        warnings.extend(pattern_warnings)
        primary_sweep = primary_info.quantity.title() if primary_info else "unknown"
        if primary_info and primary_info.quantity == "frequency":
            primary_sweep = "Freq"
        if primary_info:
            if primary_info.quantity == "angle":
                primary_sweep = "Angle"
            elif primary_info.quantity in {"theta", "phi"}:
                primary_sweep = primary_info.quantity.title()
        families.extend(ReportFamily(
            name=item.quantity.title() if item.quantity in {"theta", "phi", "angle"} else item.column,
            role=item.role,
            column=item.column,
            value=value,
            unit=item.unit,
        ) for item in fixed_info for value in (item.values or [item.minimum]))
        families.extend(ReportFamily(
            name=item.quantity.title() if item.quantity in {"theta", "phi", "angle"} else item.column,
            role="curve_family",
            column=item.column,
            value=value,
            unit=item.unit,
        ) for item in family_info for value in item.values)
        if strategy in {"2d_farfield_grid", "unconfirmed"}:
            report_domain = "far_field"
            report_type = "radiation_grid"
            data_class = "far_field_grid"
            infos.append(
                "Theta and Phi both vary without a reliable cut-family separation; "
                f"theta_unique={_unique_count(dataset, theta_col)}, phi_unique={_unique_count(dataset, phi_col)}. "
                "Data require cut/grid selection before ordinary curve plotting."
            )
        elif quantity == "AxialRatio":
            report_domain = "antenna_parameter"
            report_type = "rectangular"
            data_class = "angular_cut"
            infos.append("Axial Ratio uses an angular cut; it is not classified as a Radiation Pattern curve.")
        else:
            report_domain = "far_field"
            report_type = "radiation_polar" if strategy in {"single_cut", "split_by_family_variable", "single_angle_scan"} else "radiation_cartesian"
            data_class = "angular_cut"
            if strategy == "split_by_family_variable":
                infos.append("Theta/Phi data were interpreted as a cut family; each fixed family value should become a separate curve.")
        if not primary_info:
            warnings.append("Radiation/angle data have no confirmed primary sweep column.")
        if freq_col:
            fixed_freq = _single_value_family(dataset, freq_col, "Freq")
            if fixed_freq:
                families.append(fixed_freq)
        requires_confirmation = True
    elif has_freq and quantity in {
        "S11_dB",
        "ReturnLoss_dB",
        "VSWR",
        "Gain",
        "RealizedGain",
        "Directivity",
        "AxialRatio",
        "RadiationEfficiency",
        "TotalEfficiency",
        "HPBW",
        "Phase",
    }:
        report_domain = "antenna_parameter" if quantity not in {"S11_dB", "ReturnLoss_dB", "VSWR"} else "solution_data"
        report_type = "rectangular"
        primary_sweep = "Freq"
        data_class = "frequency_response"
    elif parameter_columns:
        report_domain = "parametric_sweep"
        report_type = "rectangular"
        primary_sweep = "Freq" if has_freq else "parameter"
        data_class = "parametric_sweep"
    else:
        warnings.append("Report domain could not be determined from column names.")
        requires_confirmation = True

    if parameter_columns and report_domain != "parametric_sweep":
        report_domain = "parametric_sweep"
        infos.append("Parameter expressions were found in column names; report also contains a parametric sweep family.")

    if quantity == "Unknown":
        warnings.append("Result quantity could not be determined from column names.")
        requires_confirmation = True

    compatible = _compatible_plot_names(quantity, report_type)
    if report_type == "radiation_grid":
        warnings.append("Far-field grid data require cut/grid selection before ordinary curve plotting.")

    return ReportModel(
        dataset_id=model.dataset_id or "",
        source_file=str(dataset.path),
        report_domain=report_domain,
        report_type=report_type,
        primary_sweep=primary_sweep,
        quantity=quantity,
        families=families,
        compatible_plot_types=compatible,
        warnings=warnings,
        errors=errors,
        infos=infos,
        requires_confirmation=requires_confirmation,
        data_class=data_class,
        columns={
            "frequency": freq_col,
            "theta": theta_col,
            "phi": phi_col,
            "angle": angle_col,
            "quantity": quantity_col,
        },
    )


def _result_domain(kind: str, dataset: HfssDataset) -> str:
    if kind == "pattern":
        return "far_field"
    if kind in {"s11", "vswr", "smith"}:
        return "modal_s_parameters"
    if kind in {"gain", "ar", "eff", "hpbw"}:
        return "antenna_parameters"
    if any("z" in normalize(column) and ("re" in normalize(column) or "im" in normalize(column)) for column in dataset.headers):
        return "impedance"
    return "unknown"


def _quantity_columns(dataset: HfssDataset, kind: str) -> list[QuantityColumn]:
    units = dataset.parse_report.units if dataset.parse_report else {}
    columns: list[str]
    if kind == "pattern":
        columns = pattern_value_columns(dataset.headers)
    elif kind == "smith":
        columns = [column for column in [smith_real_column(dataset.headers), smith_imag_column(dataset.headers)] if column]
    else:
        columns = candidate_y_columns(dataset)
    result: list[QuantityColumn] = []
    for column in columns:
        quantity = infer_y_quantity(column)
        conversion = None
        text = normalize(column)
        if quantity == "S11" and text.startswith("mag"):
            conversion = "20log10(abs(S11))"
        if quantity == "S11" and ("res11" in text or "ims11" in text):
            conversion = "complex S11 components"
        result.append(
            QuantityColumn(
                column=column,
                quantity=quantity,
                unit=infer_y_unit(column, quantity, units.get(column)),
                role="result",
                conversion=conversion,
            )
        )
    return result


def _pattern_family(dataset: HfssDataset) -> tuple[SweepVariable | None, list[SweepVariable], list[SweepVariable], str, list[str]]:
    warnings: list[str] = []
    theta_col = theta_column(dataset.headers)
    phi_col = phi_column(dataset.headers)
    angle_col = angle_column(dataset.headers)
    if angle_col and not (theta_col and phi_col):
        return _sweep(dataset, angle_col, "primary"), [], [], "single_angle_scan", warnings
    if not theta_col or not phi_col:
        warnings.append("Radiation-pattern angle columns are incomplete; cut plane requires user confirmation.")
        return None, [], [], "unconfirmed", warnings

    theta_unique = _finite_unique(dataset.column(theta_col))
    phi_unique = _finite_unique(dataset.column(phi_col))
    pattern_info = recognize_pattern(dataset)
    if pattern_info.scan_variable == "theta":
        primary = _sweep(dataset, theta_col, "primary")
        fixed = [_sweep(dataset, phi_col, "fixed")]
        return primary, fixed, [], "single_cut", warnings
    if pattern_info.scan_variable == "phi":
        primary = _sweep(dataset, phi_col, "primary")
        fixed = [_sweep(dataset, theta_col, "fixed")]
        return primary, fixed, [], "single_cut", warnings

    if theta_unique.size > 1 and phi_unique.size > 1:
        if phi_unique.size <= 4 and theta_unique.size > phi_unique.size:
            primary = _sweep(dataset, theta_col, "primary")
            family = [_sweep(dataset, phi_col, "family")]
            return primary, [], family, "split_by_family_variable", warnings
        if theta_unique.size <= 4 and phi_unique.size > theta_unique.size:
            primary = _sweep(dataset, phi_col, "primary")
            family = [_sweep(dataset, theta_col, "family")]
            return primary, [], family, "split_by_family_variable", warnings
        if theta_unique.size >= max(4, phi_unique.size * 3) and phi_unique.size <= 16:
            primary = _sweep(dataset, theta_col, "primary")
            family = [_sweep(dataset, phi_col, "family")]
            return primary, [], family, "split_by_family_variable", warnings
        if phi_unique.size >= max(4, theta_unique.size * 3) and theta_unique.size <= 16:
            primary = _sweep(dataset, phi_col, "primary")
            family = [_sweep(dataset, theta_col, "family")]
            return primary, [], family, "split_by_family_variable", warnings
        primary = _sweep(dataset, theta_col, "primary")
        family = [_sweep(dataset, phi_col, "family")]
        warnings.append("Theta and Phi both vary with many values; this may be a 2D far-field grid rather than a cut-family plot.")
        return primary, [], family, "2d_farfield_grid", warnings
    return None, [], [], "unconfirmed", warnings


def _compatible(kind: str, domain: str, curve_strategy: str) -> tuple[list[str], str, str | None]:
    if domain == "far_field":
        modes = ["radiation_cartesian", "radiation_polar"]
        display = "polar" if curve_strategy in {"single_cut", "split_by_family_variable", "single_angle_scan"} else "cartesian"
        return modes, "pattern", display
    if kind == "smith":
        return ["smith", "s11"], "smith", None
    if kind in {"s11", "vswr", "gain", "ar", "eff", "hpbw"}:
        return [kind], kind, None
    return ["xy"], "auto", None


def _curve_plans(dataset: HfssDataset, primary: SweepVariable | None, quantity_columns: list[QuantityColumn], family: list[SweepVariable]) -> list[CurvePlan]:
    if primary is None:
        return []
    plans: list[CurvePlan] = []
    if family:
        family_item = family[0]
        for quantity in quantity_columns:
            for value in family_item.values:
                label = f"{quantity.column}, {family_item.column}={value:g}"
                plans.append(
                    CurvePlan(
                        x_column=primary.column,
                        y_column=quantity.column,
                        label=label,
                        x_quantity=primary.quantity,
                        y_quantity=quantity.quantity,
                        x_unit=primary.unit,
                        y_unit=quantity.unit,
                        fixed_context={"family_variable": family_item.column, "family_value": value},
                    )
                )
        return plans
    for quantity in quantity_columns:
        plans.append(
            CurvePlan(
                x_column=primary.column,
                y_column=quantity.column,
                label=quantity.column,
                x_quantity=primary.quantity,
                y_quantity=quantity.quantity,
                x_unit=primary.unit,
                y_unit=quantity.unit,
            )
        )
    return plans


def plan_report_from_dataset(dataset: HfssDataset, mode: str = "semiauto") -> ReportPlan:
    kind = "unknown" if mode == "manual" else detect_kind(dataset)
    model = dataset.to_model()
    domain = _result_domain(kind, dataset)
    warnings: list[str] = []
    reasons: list[str] = []
    errors: list[str] = []
    fixed: list[SweepVariable] = []
    family: list[SweepVariable] = []
    strategy = "single_curve"

    if mode == "manual":
        reasons.append("Manual mode: no physical meaning is inferred until the user confirms mappings.")

    if domain == "far_field":
        primary, fixed, family, strategy, pattern_warnings = _pattern_family(dataset)
        warnings.extend(pattern_warnings)
    else:
        freq_col = frequency_column(dataset.headers)
        primary = _sweep(dataset, freq_col, "primary") if freq_col else None
        if not primary:
            reasons.append("No explicit primary sweep variable was detected.")

    for column in dataset.headers:
        if not is_numeric_column(dataset.rows, column):
            continue
        if primary and column == primary.column:
            continue
        if any(column == item.column for item in fixed + family):
            continue
        values = _finite_unique(dataset.column(column))
        if values.size == 1 and _quantity_for_column(column) in {"frequency", "theta", "phi", "angle", "parameter"}:
            fixed.append(_sweep(dataset, column, "fixed"))

    quantities = _quantity_columns(dataset, kind)
    if not quantities:
        warnings.append("No result quantity column was confidently detected.")
        reasons.append("User must select the result column.")

    compatible, recommended_plot_type, recommended_display = _compatible(kind, domain, strategy)
    if domain == "far_field" and not primary:
        errors.append("Radiation Pattern requires an angle sweep column such as Theta, Phi, or Angle.")

    if dataset.parse_report and not dataset.parse_report.header_rows:
        reasons.append("File has no detected header row; HFSS-like report interpretation requires confirmation.")
    if any(normalize(column) in {"x", "y", "value", "data"} for column in dataset.headers):
        reasons.append("Column names are generic; variable mapping must be confirmed.")
    if primary and primary.quantity == "frequency" and not (dataset.parse_report and dataset.parse_report.units.get(primary.column)):
        warnings.append("Frequency unit is inferred rather than explicitly confirmed.")
        reasons.append("Frequency unit requires confirmation.")
    if domain == "far_field":
        reasons.append("Radiation-pattern normalization and cut naming require user confirmation.")
    report_model = build_report_model(dataset, mode)

    return ReportPlan(
        dataset_id=model.dataset_id or "",
        source_file=str(dataset.path),
        result_domain=domain,
        data_type=model.data_type,
        primary_sweep=primary,
        fixed_variables=fixed,
        family_variables=family,
        quantity_columns=quantities,
        compatible_plot_types=compatible,
        recommended_plot_type=recommended_plot_type,
        recommended_display_mode=recommended_display,
        curve_family_strategy=strategy,
        curve_plans=_curve_plans(dataset, primary, quantities, family),
        requires_confirmation=mode in {"semiauto", "manual"} or bool(reasons) or bool(errors),
        confirmation_reasons=reasons,
        warnings=warnings,
        errors=errors,
        report_model=report_model,
    )
