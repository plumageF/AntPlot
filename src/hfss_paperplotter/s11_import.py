"""S11-specific CSV interpretation helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

from .models import Curve, infer_x_unit
from .reader import HfssDataset, clean_number, convert_frequency, frequency_column, generic_column_name, is_numeric_column, normalize


@dataclass
class S11ImportResult:
    curves: list[Curve] = field(default_factory=list)
    phase_curves: list[Curve] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    requires_confirmation: bool = False


def _values(dataset: HfssDataset, column: str) -> np.ndarray:
    return dataset.column(column)


def _row_values(rows: list[dict[str, str]], column: str) -> list[str]:
    return [str(row.get(column, "")).strip() for row in rows]


def _is_db_s11(column: str) -> bool:
    n = normalize(column)
    return ("s11" in n or "returnloss" in n or "s1,1" in column.lower() or "s(1,1)" in column.lower()) and (
        "db" in n or "logmag" in n
    )


def _is_plain_s11(column: str) -> bool:
    n = normalize(column)
    if any(token in n for token in ["mag", "phase", "real", "imag", "vswr"]):
        return False
    return "s11" in n or "s1,1" in column.lower() or "s(1,1)" in column.lower()


def _is_mag_s11(column: str) -> bool:
    n = normalize(column)
    return ("s11" in n or "s1,1" in column.lower() or "s(1,1)" in column.lower()) and "mag" in n and "logmag" not in n


def _is_phase_s11(column: str) -> bool:
    n = normalize(column)
    return ("s11" in n or "s1,1" in column.lower() or "s(1,1)" in column.lower()) and "phase" in n


def _is_real_s11(column: str) -> bool:
    n = normalize(column)
    return ("s11" in n or "s1,1" in column.lower() or "s(1,1)" in column.lower()) and (
        n.startswith("re") or "real" in n or "res11" in n
    )


def _is_imag_s11(column: str) -> bool:
    n = normalize(column)
    return ("s11" in n or "s1,1" in column.lower() or "s(1,1)" in column.lower()) and (
        n.startswith("im") or "imag" in n or "ims11" in n
    )


def _is_formatted_data(column: str) -> bool:
    return normalize(column) == "formatteddata"


def _label_from_column(column: str) -> str:
    params = re.findall(r"([A-Za-z_]\w*)\s*=\s*'([^']+)'", column)
    if params:
        return ", ".join(f"{name}={value}" for name, value in params)
    params = re.findall(r"([A-Za-z_]\w*)\s*=\s*([+-]?\d+(?:\.\d+)?\s*[A-Za-z]+)", column)
    if params:
        return ", ".join(f"{name}={value.replace(' ', '')}" for name, value in params)
    if ":" in column:
        tail = column.split(":", 1)[1].strip()
        if tail:
            return tail
    text = re.sub(r"dB\s*\(|\)\s*\[\]|\[\]", "", column).strip()
    return text or column


def _categorical_columns(dataset: HfssDataset) -> list[str]:
    result: list[str] = []
    for column in dataset.headers:
        if is_numeric_column(dataset.rows, column):
            continue
        values = [value for value in _row_values(dataset.rows, column) if value]
        unique = set(values)
        if 1 < len(unique) < max(10, len(values)):
            result.append(column)
    return result


def _numeric_parameter_columns(dataset: HfssDataset, x_col: str, y_cols: list[str]) -> list[str]:
    excluded = {x_col, *y_cols}
    response_tokens = ["s11", "s1", "vswr", "gain", "efficiency", "axial", "phase", "theta", "phi", "freq"]
    result: list[str] = []
    row_count = len(dataset.rows)
    if row_count < 2:
        return result
    for column in dataset.headers:
        if column in excluded or not is_numeric_column(dataset.rows, column):
            continue
        normalized = normalize(column)
        if any(token in normalized for token in response_tokens):
            continue
        values = np.asarray([clean_number(value) for value in _row_values(dataset.rows, column)], dtype=float)
        finite = values[np.isfinite(values)]
        unique = np.unique(np.round(finite, 12)) if finite.size else np.asarray([])
        if 0 < unique.size < row_count:
            result.append(column)
    return result


def _group_label(columns: list[str], key: tuple[str, ...]) -> str:
    parts: list[str] = []
    for column, value in zip(columns, key, strict=False):
        name = re.sub(r"\s*\[[^\]]+\]|\s*\([^\)]*\)", "", column).strip() or column
        parts.append(f"{name}={value}")
    return ", ".join(parts)


def _frequency_data(dataset: HfssDataset, x_column: str, target_unit: str | None) -> tuple[np.ndarray, str, list[str]]:
    warnings: list[str] = []
    unit = None if target_unit in {None, "", "auto"} else target_unit
    unit = unit or infer_x_unit(x_column)
    if unit == "GHz" and not re.search(r"(?:\[|\()\s*(?:g|m|k)?hz\s*(?:\]|\))", x_column, re.I):
        warnings.append("Frequency unit is not explicit; confirm x-axis unit before drawing engineering conclusions.")
    values, unit_label = convert_frequency(_values(dataset, x_column), x_column, unit.lower())
    return values, unit_label, warnings


def _curve(
    dataset: HfssDataset,
    x_column: str,
    y_column: str,
    x_data: np.ndarray,
    y_data: np.ndarray,
    x_unit: str,
    label: str,
    conversion: str | None,
    warnings: list[str],
) -> Curve:
    return Curve(
        dataset_id=dataset.to_model().dataset_id or "",
        x_data=x_data,
        y_data=y_data,
        x_column=x_column,
        y_column=y_column,
        x_quantity="frequency",
        y_quantity="S11",
        x_unit=x_unit,  # type: ignore[arg-type]
        y_unit="dB",
        label=label,
        conversion=conversion,
        warnings=warnings,
    )


def _phase_curve(
    dataset: HfssDataset,
    x_column: str,
    y_column: str,
    x_data: np.ndarray,
    y_data: np.ndarray,
    x_unit: str,
    label: str,
    warnings: list[str],
) -> Curve:
    return Curve(
        dataset_id=dataset.to_model().dataset_id or "",
        x_data=x_data,
        y_data=y_data,
        x_column=x_column,
        y_column=y_column,
        x_quantity="frequency",
        y_quantity="Phase",
        x_unit=x_unit,  # type: ignore[arg-type]
        y_unit="degree",
        label=label,
        conversion=None,
        warnings=warnings,
    )


def s11_curves_from_dataset(dataset: HfssDataset, *, x_unit: str | None = None) -> S11ImportResult:
    result = S11ImportResult()
    if dataset.parse_report and not dataset.parse_report.header_rows:
        result.requires_confirmation = True
        result.warnings.append("No header detected; S11 mapping requires manual confirmation.")
        return result
    if any(generic_column_name(header) for header in dataset.headers):
        result.requires_confirmation = True
        result.warnings.append("Generic column names detected; S11 mapping requires manual confirmation.")

    x_col = frequency_column(dataset.headers)
    if not x_col:
        result.requires_confirmation = True
        result.warnings.append("No explicit frequency column detected.")
        return result

    x_data, x_unit_label, x_warnings = _frequency_data(dataset, x_col, x_unit)
    result.warnings.extend(x_warnings)
    case_cols = _categorical_columns(dataset)
    case_col = next((column for column in case_cols if normalize(column) in {"case", "sweep", "trace", "state"}), None)

    def add_grouped_curve(y_col: str, y_data: np.ndarray, label: str, conversion: str | None, warnings: list[str]) -> None:
        parameter_cols = _numeric_parameter_columns(dataset, x_col, [y_col])
        if case_col:
            for case in sorted(set(_row_values(dataset.rows, case_col))):
                if not case:
                    continue
                mask = np.asarray([str(row.get(case_col, "")).strip() == case for row in dataset.rows], dtype=bool)
                curve = _curve(dataset, x_col, y_col, x_data[mask], y_data[mask], x_unit_label, f"{label} - {case}", conversion, warnings)
                curve.metadata.update({"family_info": {case_col: case}, "family_columns": [case_col], "long_form_grouped": True})
                result.curves.append(curve)
        elif parameter_cols:
            keys = [
                tuple(str(row.get(column, "")).strip() for column in parameter_cols)
                for row in dataset.rows
            ]
            unique_keys = sorted({key for key in keys if any(item != "" for item in key)})
            if 1 < len(unique_keys) <= max(200, len(dataset.rows)):
                for key in unique_keys:
                    mask = np.asarray([row_key == key for row_key in keys], dtype=bool)
                    group_name = _group_label(parameter_cols, key)
                    curve = _curve(dataset, x_col, y_col, x_data[mask], y_data[mask], x_unit_label, group_name, conversion, warnings)
                    curve.metadata.update(
                        {
                            "family_info": {column: value for column, value in zip(parameter_cols, key, strict=False)},
                            "family_columns": parameter_cols,
                            "long_form_grouped": True,
                            "group_label": group_name,
                            "total_rows": len(dataset.rows),
                            "curve_count_in_dataset": len(unique_keys),
                        }
                    )
                    result.curves.append(curve)
                result.warnings.append(
                    f"Long-form parameter sweep detected; grouped {len(dataset.rows)} rows into {len(unique_keys)} S11 curves by {', '.join(parameter_cols)}."
                )
            else:
                result.curves.append(_curve(dataset, x_col, y_col, x_data, y_data, x_unit_label, label, conversion, warnings))
        else:
            result.curves.append(_curve(dataset, x_col, y_col, x_data, y_data, x_unit_label, label, conversion, warnings))

    db_cols = [column for column in dataset.headers if column != x_col and _is_db_s11(column)]
    plain_cols = [
        column
        for column in dataset.headers
        if column != x_col and _is_plain_s11(column) and column not in db_cols and not _is_real_s11(column) and not _is_imag_s11(column)
    ]
    formatted_cols = [column for column in dataset.headers if _is_formatted_data(column)]
    mag_cols = [column for column in dataset.headers if column != x_col and _is_mag_s11(column)]
    phase_cols = [column for column in dataset.headers if column != x_col and _is_phase_s11(column)]
    real_cols = [column for column in dataset.headers if column != x_col and _is_real_s11(column)]
    imag_cols = [column for column in dataset.headers if column != x_col and _is_imag_s11(column)]

    for column in db_cols:
        add_grouped_curve(column, _values(dataset, column), _label_from_column(column), "used as S11 dB", [])
    for column in plain_cols:
        warning = "S11 column does not explicitly state dB or linear magnitude; confirm before engineering conclusions."
        result.requires_confirmation = True
        result.warnings.append(warning)
        add_grouped_curve(column, _values(dataset, column), _label_from_column(column), "assumed S11 dB after user confirmation", [warning])
    for column in formatted_cols:
        warning = "VNA Formatted Data is only a possible S11(dB) column; user confirmation is required."
        result.requires_confirmation = True
        result.warnings.append(warning)
        add_grouped_curve(column, _values(dataset, column), "Formatted Data", "possible S11 dB from VNA", [warning])
    for column in mag_cols:
        mag = np.abs(_values(dataset, column))
        with np.errstate(divide="ignore", invalid="ignore"):
            y_data = 20.0 * np.log10(mag)
        add_grouped_curve(column, y_data, _label_from_column(column), "20log10(abs(S11)) from linear magnitude", [])
    for real_col in real_cols:
        imag_col = next((column for column in imag_cols if normalize(column).replace("im", "").replace("imag", "") == normalize(real_col).replace("re", "").replace("real", "")), None)
        if imag_col is None and imag_cols:
            imag_col = imag_cols[0]
        if imag_col:
            real = _values(dataset, real_col)
            imag = _values(dataset, imag_col)
            with np.errstate(divide="ignore", invalid="ignore"):
                y_data = 20.0 * np.log10(np.sqrt(real**2 + imag**2))
            add_grouped_curve(f"{real_col} + {imag_col}", y_data, "S11 from re/im", "20log10(sqrt(re^2+im^2))", [])
    for column in phase_cols:
        result.phase_curves.append(
            _phase_curve(dataset, x_col, column, x_data, _values(dataset, column), x_unit_label, _label_from_column(column), [])
        )

    if len(result.curves) > 1:
        result.warnings.append("Multiple S11 curves detected; labels are derived from column names or parameter text and can be edited.")
    if not result.curves:
        result.requires_confirmation = True
        result.warnings.append("No confirmed S11 curve was created.")
    return result
