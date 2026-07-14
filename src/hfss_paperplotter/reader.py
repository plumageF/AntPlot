"""HFSS CSV reading and detection."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .models import (
    Curve,
    Dataset,
    OperationMode,
    RecognitionResult,
    infer_data_type,
    infer_file_format,
    infer_source_type,
    infer_units,
    infer_x_quantity,
    infer_x_unit,
    infer_y_quantity,
    infer_y_unit,
)


@dataclass
class ColumnInfo:
    name: str
    is_numeric: bool


@dataclass
class CsvInfo:
    path: Path
    columns: list[ColumnInfo]
    row_count: int
    kind: str


@dataclass
class CsvParseReport:
    columns: list[str]
    row_count: int
    units: dict[str, str | None]
    ranges: dict[str, tuple[float, float] | None]
    has_missing_values: bool
    missing_values: dict[str, int]
    has_duplicate_points: bool
    duplicate_point_count: int
    possible_data_type: str
    warnings: list[str] = field(default_factory=list)
    delimiter: str | None = None
    header_rows: list[int] = field(default_factory=list)
    skipped_rows: list[int] = field(default_factory=list)
    metadata_rows: list[str] = field(default_factory=list)


@dataclass
class HfssDataset:
    path: Path
    headers: list[str]
    rows: list[dict[str, str]]
    parse_report: CsvParseReport | None = None

    def column(self, name: str) -> np.ndarray:
        return np.asarray([clean_number(row.get(name, "")) for row in self.rows], dtype=float)

    def to_model(self) -> Dataset:
        return dataset_model_from_hfss(self)


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def clean_number(value: str | None) -> float:
    if value is None:
        return float("nan")
    text = str(value).strip().replace("\ufeff", "")
    if not text:
        return float("nan")
    text = text.replace("dB", "").replace("DB", "")
    text = text.replace("\u2212", "-")
    text = text.replace("NA", "").replace("N/A", "").replace("--", "")
    if "," in text and "." not in text and re.fullmatch(r"[-+]?\d+,\d+(?:[eE][-+]?\d+)?", text):
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return float("nan")


def clean_complex(value: str | None) -> complex | None:
    if value is None:
        return None
    text = str(value).strip().replace("\ufeff", "")
    if not text:
        return None
    text = text.replace("\u2212", "-").replace("I", "j").replace("i", "j")
    text = re.sub(r"\s+", "", text)
    try:
        result = complex(text)
        if np.isfinite(result.real) and np.isfinite(result.imag):
            return result
    except ValueError:
        pass
    match = re.fullmatch(r"([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)([-+]\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)j", text)
    if match:
        try:
            return complex(float(match.group(1)), float(match.group(2)))
        except ValueError:
            return None
    return None


def is_numeric_column(rows: list[dict[str, str]], column: str) -> bool:
    values = [clean_number(row.get(column, "")) for row in rows[:50]]
    valid = [value for value in values if np.isfinite(value)]
    required = max(1, int(len(values) * 0.6))
    return len(valid) >= required


def possible_family_columns(headers: list[str], rows: list[dict[str, str]], x_column: str | None) -> list[str]:
    response_tokens = [
        "freq",
        "frequency",
        "s11",
        "s1",
        "vswr",
        "gain",
        "directivity",
        "efficiency",
        "axial",
        "phase",
        "theta",
        "phi",
        "angle",
        "realized",
        "formatted",
        "data",
        "value",
    ]
    result: list[str] = []
    row_count = len(rows)
    for header in headers:
        if header == x_column or not is_numeric_column(rows, header):
            continue
        normalized = normalize(header)
        if any(token in normalized for token in response_tokens):
            continue
        values = np.asarray([clean_number(row.get(header, "")) for row in rows], dtype=float)
        finite = values[np.isfinite(values)]
        unique = np.unique(np.round(finite, 12)) if finite.size else np.asarray([])
        if 1 < unique.size < row_count:
            result.append(header)
    return result


def split_line(line: str, delimiter: str) -> list[str]:
    def clean_token(token: str) -> str:
        text = token.strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
            return text[1:-1].strip()
        return text

    text = line.strip().replace("\ufeff", "")
    if delimiter == "space":
        return [clean_token(token) for token in re.split(r"\s+", text) if token.strip()]
    tokens: list[str] = []
    current: list[str] = []
    depth = 0
    quote: str | None = None
    for char in text:
        if char in {"'", '"'}:
            quote = None if quote == char else char if quote is None else quote
        elif quote is None and char in "([{":
            depth += 1
        elif quote is None and char in ")]}" and depth > 0:
            depth -= 1
        if quote is None and depth == 0 and char == delimiter:
            tokens.append(clean_token("".join(current)))
            current = []
        else:
            current.append(char)
    tokens.append(clean_token("".join(current)))
    return tokens


def numeric_count(tokens: list[str]) -> int:
    return sum(1 for token in tokens if np.isfinite(clean_number(token)))


def scalar_or_complex_count(tokens: list[str]) -> int:
    count = 0
    for token in tokens:
        if np.isfinite(clean_number(token)) or clean_complex(token) is not None:
            count += 1
    return count


def choose_delimiter(lines: list[str]) -> str:
    candidates = [",", ";", "\t", "space"]
    scores: dict[str, tuple[int, int, int]] = {}
    sample = [line for line in lines if line.strip()][:80]
    for delimiter in candidates:
        widths: list[int] = []
        numeric_rows = 0
        for line in sample:
            tokens = split_line(line, delimiter)
            if len(tokens) >= 2:
                widths.append(len(tokens))
                if scalar_or_complex_count(tokens) >= 2:
                    numeric_rows += 1
        stable_width = 0
        if widths:
            stable_width = max(widths.count(width) for width in set(widths))
        scores[delimiter] = (numeric_rows, stable_width, -max(widths or [0]))
    return max(scores, key=scores.get)


def looks_like_data_row(tokens: list[str]) -> bool:
    if len(tokens) < 2:
        return False
    return scalar_or_complex_count(tokens) >= max(2, int(len(tokens) * 0.6))


def find_data_start(tokenized: list[list[str]]) -> int | None:
    for index in range(len(tokenized)):
        window = tokenized[index : index + 3]
        if not window:
            continue
        if looks_like_data_row(window[0]) and sum(1 for row in window if looks_like_data_row(row)) >= min(2, len(window)):
            return index
    for index, tokens in enumerate(tokenized):
        if looks_like_data_row(tokens):
            return index
    return None


def make_unique_headers(headers: list[str]) -> list[str]:
    unique: list[str] = []
    counts: dict[str, int] = {}
    for index, header in enumerate(headers, start=1):
        name = header.strip() or f"Column {index}"
        counts[name] = counts.get(name, 0) + 1
        if counts[name] > 1:
            name = f"{name}_{counts[name]}"
        unique.append(name)
    return unique


def merge_header_rows(rows: list[list[str]], width: int) -> list[str]:
    if not rows:
        return [f"Column {index}" for index in range(1, width + 1)]
    padded = [row + [""] * max(0, width - len(row)) for row in rows]
    headers: list[str] = []
    for column_index in range(width):
        parts = [row[column_index].strip() for row in padded if column_index < len(row) and row[column_index].strip()]
        if len(parts) >= 2:
            unit_like = parts[-1].strip()
            if re.fullmatch(r"\[?.{1,12}\]?", unit_like) and not any(char.isdigit() for char in unit_like):
                unit_text = unit_like.strip("[]()")
                headers.append(f"{parts[0]} [{unit_text}]")
                continue
        headers.append(" ".join(parts) if parts else f"Column {column_index + 1}")
    return make_unique_headers(headers)


def _delimiter_from_option(delimiter: str | None) -> str | None:
    if delimiter is None:
        return None
    text = str(delimiter).strip().lower()
    if text in {"", "auto"}:
        return None
    aliases = {"comma": ",", "semicolon": ";", "tab": "\t", "space": "space"}
    return aliases.get(text, delimiter)


def parse_csv_structure(
    path: Path,
    *,
    delimiter: str | None = None,
    header_rows: list[int] | None = None,
) -> tuple[list[str], list[dict[str, str]], CsvParseReport]:
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    nonempty: list[tuple[int, str]] = [(index, line) for index, line in enumerate(lines, start=1) if line.strip()]
    if not nonempty:
        raise ValueError(f"Empty or invalid CSV: {path}")

    selected_delimiter = _delimiter_from_option(delimiter) or choose_delimiter([line for _, line in nonempty])
    tokenized = [(line_number, split_line(line, selected_delimiter)) for line_number, line in nonempty]
    manual_header_rows = sorted({int(row) for row in (header_rows or []) if int(row) > 0})
    if manual_header_rows:
        last_header = max(manual_header_rows)
        data_pos = next(
            (
                index
                for index, (line_number, tokens) in enumerate(tokenized)
                if line_number > last_header and looks_like_data_row(tokens)
            ),
            None,
        )
    else:
        data_pos = find_data_start([tokens for _, tokens in tokenized])
    if data_pos is None:
        raise ValueError(f"Could not find numeric data rows in CSV: {path}")

    warnings: list[str] = []
    data_width = len(tokenized[data_pos][1])
    metadata_rows = [",".join(tokens) for _, tokens in tokenized[:data_pos]]
    if manual_header_rows:
        by_line = {line_number: tokens for line_number, tokens in tokenized}
        missing_headers = [row for row in manual_header_rows if row not in by_line]
        if missing_headers:
            warnings.append(f"Manual header row(s) not found after empty-line filtering: {', '.join(str(row) for row in missing_headers)}.")
        header_candidates = [(row, by_line[row]) for row in manual_header_rows if row in by_line]
        warnings.append("CSV structure parsed with user-specified header row/delimiter settings.")
    else:
        header_candidates = []
        for line_number, tokens in reversed(tokenized[:data_pos]):
            if len(tokens) == data_width and numeric_count(tokens) == 0:
                header_candidates.insert(0, (line_number, tokens))
                if len(header_candidates) >= 2:
                    break
            elif header_candidates:
                break
    if header_candidates:
        headers = merge_header_rows([tokens for _, tokens in header_candidates], data_width)
        header_rows = [line_number for line_number, _ in header_candidates]
        skipped_rows = [line_number for line_number, _ in tokenized[:data_pos] if line_number not in header_rows]
    else:
        headers = make_unique_headers([f"Column {index}" for index in range(1, data_width + 1)])
        header_rows = []
        skipped_rows = [line_number for line_number, _ in tokenized[:data_pos]]
        warnings.append("No explicit header row detected; generated generic column names.")

    rows: list[dict[str, str]] = []
    skipped_data_rows: list[int] = []
    for line_number, tokens in tokenized[data_pos:]:
        if numeric_count(tokens) < 1:
            skipped_data_rows.append(line_number)
            continue
        values = tokens + [""] * max(0, data_width - len(tokens))
        rows.append({header: values[index] if index < len(values) else "" for index, header in enumerate(headers)})
    if skipped_data_rows:
        warnings.append(f"Skipped {len(skipped_data_rows)} non-data rows inside data block.")
    if not rows:
        raise ValueError(f"No numeric data rows found in CSV: {path}")
    empty_separator_columns = [
        header
        for header in headers
        if re.fullmatch(r"Column \d+", header)
        and all(str(row.get(header, "")).strip() == "" for row in rows)
    ]
    if empty_separator_columns:
        headers = [header for header in headers if header not in empty_separator_columns]
        rows = [{header: row.get(header, "") for header in headers} for row in rows]
        warnings.append(f"Dropped empty separator column(s): {', '.join(empty_separator_columns)}.")

    ranges: dict[str, tuple[float, float] | None] = {}
    missing: dict[str, int] = {}
    for header in headers:
        values = np.asarray([clean_number(row.get(header, "")) for row in rows], dtype=float)
        finite = values[np.isfinite(values)]
        ranges[header] = (float(np.nanmin(finite)), float(np.nanmax(finite))) if finite.size else None
        missing[header] = int(len(values) - finite.size)
    has_missing = any(count > 0 for count in missing.values())
    if has_missing:
        warnings.append("Missing or non-numeric values detected.")

    freq_col = frequency_column(headers)
    duplicate_count = 0
    if freq_col:
        values = [row.get(freq_col, "") for row in rows]
        finite_values = [clean_number(value) for value in values if np.isfinite(clean_number(value))]
        duplicate_count = len(finite_values) - len(set(np.round(finite_values, 12)))
        duplicate_count_for_report = duplicate_count
        if duplicate_count > 0:
            angle_sweep_columns = []
            for header in headers:
                normalized = normalize(header)
                if not any(token in normalized for token in ["theta", "phi", "angle"]):
                    continue
                angle_values = np.asarray([clean_number(row.get(header, "")) for row in rows], dtype=float)
                finite_angles = angle_values[np.isfinite(angle_values)]
                if np.unique(np.round(finite_angles, 9)).size > 1:
                    angle_sweep_columns.append(header)
            family_cols = possible_family_columns(headers, rows, freq_col)
            if len(set(np.round(finite_values, 12))) == 1 and angle_sweep_columns:
                warnings.append(
                    f"Frequency is fixed at {finite_values[0]:g}; angular sweep column(s) detected: {', '.join(angle_sweep_columns)}."
                )
            elif family_cols:
                warnings.append(
                    "Repeated frequency values detected across possible parameter/family columns "
                    f"({', '.join(family_cols)}). Duplicate X will be checked within each generated Curve."
                )
                duplicate_count_for_report = 0
            else:
                warnings.append(
                    f"Duplicate frequency/X points detected: {duplicate_count}. If this is a parameter sweep or long-form multi-curve file, choose grouping columns before plotting."
                )
        duplicate_count = duplicate_count_for_report
    else:
        warnings.append("No confirmed frequency column; duplicate frequency check was not performed.")

    dataset_probe = HfssDataset(path=path, headers=headers, rows=rows, parse_report=None)
    possible_data_type = detect_kind(dataset_probe)
    report = CsvParseReport(
        columns=headers,
        row_count=len(rows),
        units=infer_units(headers),
        ranges=ranges,
        has_missing_values=has_missing,
        missing_values=missing,
        has_duplicate_points=duplicate_count > 0,
        duplicate_point_count=duplicate_count,
        possible_data_type=possible_data_type,
        warnings=warnings,
        delimiter=selected_delimiter,
        header_rows=header_rows,
        skipped_rows=skipped_rows,
        metadata_rows=metadata_rows,
    )
    return headers, rows, report


def read_hfss_csv(path: Path, parse_options: dict[str, object] | None = None) -> HfssDataset:
    options = parse_options or {}
    header_option = options.get("header_row") or options.get("headerRow") or options.get("header_rows")
    header_rows: list[int] | None = None
    if isinstance(header_option, list):
        header_rows = [int(item) for item in header_option if str(item).strip().lower() not in {"", "auto", "none"}]
    elif header_option is not None and str(header_option).strip().lower() not in {"", "auto", "none"}:
        header_rows = [int(float(str(header_option).strip()))]
    delimiter = options.get("delimiter")
    headers, rows, report = parse_csv_structure(path, delimiter=str(delimiter) if delimiter is not None else None, header_rows=header_rows)
    if not headers or not rows:
        raise ValueError(f"Empty or invalid CSV: {path}")
    return HfssDataset(path=path, headers=headers, rows=rows, parse_report=report)


def find_column(headers: list[str], preferred: str | None, patterns: list[str]) -> str | None:
    if preferred and preferred in headers:
        return preferred
    normalized = [(header, normalize(header)) for header in headers]
    for pattern in patterns:
        for header, normalized_header in normalized:
            if pattern in normalized_header:
                return header
    return None


def frequency_column(headers: list[str], preferred: str | None = None) -> str | None:
    return find_column(headers, preferred, ["freq", "frequency", "sweepfreq", "solutionfreq", "fghz", "fmhz"])


def s11_column(headers: list[str], preferred: str | None = None) -> str | None:
    return find_column(
        headers,
        preferred,
        [
            "s11",
            "s1,1",
            "s(1,1)",
            "dbs11",
            "dbs1",
            "sparameter11",
            "sparam11",
            "returnloss",
            "return loss",
            "reflectioncoefficient",
        ],
    )


def gain_column(headers: list[str], preferred: str | None = None) -> str | None:
    return find_column(
        headers,
        preferred,
        [
            "realizedgaintotal",
            "realizedgain",
            "realized gain",
            "peakgaintotal",
            "gaintotal",
            "totalgain",
            "peakgain",
            "directivitytotal",
            "directivity",
            "gain",
        ],
    )


def pattern_value_columns(headers: list[str]) -> list[str]:
    patterns = [
        "realizedgain",
        "gaintotal",
        "gain",
        "copol",
        "co-pol",
        "crosspol",
        "cross-pol",
        "rhcp",
        "lhcp",
        "eplane",
        "hplane",
        "e-plane",
        "h-plane",
        "etheta",
        "ephi",
    ]
    values: list[str] = []
    for header in headers:
        normalized = normalize(header)
        if any(pattern.replace("-", "") in normalized for pattern in patterns):
            values.append(header)
    return values


def efficiency_column(headers: list[str], preferred: str | None = None) -> str | None:
    return find_column(
        headers,
        preferred,
        ["radiationefficiency", "radiation efficiency", "radeff", "totalefficiency", "total efficiency", "antennaefficiency", "antenna efficiency", "efficiency"],
    )


def hpbw_column(headers: list[str], preferred: str | None = None) -> str | None:
    return find_column(
        headers,
        preferred,
        ["halfpowerbeamwidth", "half power beamwidth", "3dbbeamwidth", "beamwidth3db", "hpbw", "beamwidth"],
    )


def axial_ratio_column(headers: list[str], preferred: str | None = None) -> str | None:
    return find_column(
        headers,
        preferred,
        ["axialratiovalue", "axialratio", "axial ratio", "axisratio", "axis ratio", "axial", "ar"],
    )


def vswr_column(headers: list[str], preferred: str | None = None) -> str | None:
    return find_column(headers, preferred, ["vswr", "vsmr", "voltagestandingwaveratio"])


def smith_real_column(headers: list[str], preferred: str | None = None) -> str | None:
    return find_column(
        headers,
        preferred,
        ["res11", "reals11", "realofs11", "rez", "rez11", "rezin", "realz", "realzin", "re"],
    )


def smith_imag_column(headers: list[str], preferred: str | None = None) -> str | None:
    return find_column(
        headers,
        preferred,
        ["ims11", "imags11", "imaginarys11", "imz", "imz11", "imzin", "imagz", "imaginaryz", "imaginary"],
    )


def complex_s_column(headers: list[str], preferred: str | None = None) -> str | None:
    if preferred and preferred in headers:
        return preferred
    for header in headers:
        normalized = normalize(header)
        if normalized in {"s11", "s1"} or normalized.startswith("s11"):
            if not any(token in normalized for token in ["db", "mag", "phase", "re", "real", "im", "imag", "vswr"]):
                return header
    return None


def has_complex_values(dataset: HfssDataset, column: str | None) -> bool:
    if not column:
        return False
    checked = 0
    valid = 0
    for row in dataset.rows[:25]:
        raw = str(row.get(column, "")).strip()
        if not raw:
            continue
        checked += 1
        if clean_complex(raw) is not None:
            valid += 1
    return checked > 0 and valid >= max(1, int(checked * 0.8))


def theta_column(headers: list[str], preferred: str | None = None) -> str | None:
    return find_column(headers, preferred, ["theta"])


def phi_column(headers: list[str], preferred: str | None = None) -> str | None:
    return find_column(headers, preferred, ["phi"])


def angle_column(headers: list[str], preferred: str | None = None) -> str | None:
    return find_column(headers, preferred, ["angle", "ang"])


def to_ghz(values: np.ndarray, header: str) -> np.ndarray:
    unit_match = re.search(r"(?:\[|\()\s*((?:k|m|g|t)?hz)\s*(?:\]|\))", header, re.I)
    unit = unit_match.group(1).lower() if unit_match else ""
    scales = {"hz": 1e-9, "khz": 1e-6, "mhz": 1e-3, "ghz": 1.0, "thz": 1e3}
    if unit in scales:
        return values * scales[unit]
    maximum = float(np.nanmax(np.abs(values)))
    if maximum >= 1e8:
        return values * 1e-9
    if maximum >= 1e5:
        return values * 1e-3
    return values


def convert_frequency(values: np.ndarray, header: str, unit: str | None) -> tuple[np.ndarray, str]:
    target = (unit or "auto").lower()
    if target == "auto":
        target = "ghz"
    ghz = to_ghz(values, header)
    if target == "mhz":
        return ghz * 1000.0, "MHz"
    if target == "hz":
        return ghz * 1e9, "Hz"
    return ghz, "GHz"


def detect_kind(dataset: HfssDataset) -> str:
    headers = dataset.headers
    if hpbw_column(headers):
        return "hpbw"
    if theta_column(headers) and phi_column(headers) and pattern_value_columns(headers):
        theta_values = dataset.column(theta_column(headers) or "")
        finite = theta_values[np.isfinite(theta_values)]
        if len(np.unique(np.round(finite, 6))) >= 10:
            return "pattern"
    if angle_column(headers) and pattern_value_columns(headers):
        angle_values = dataset.column(angle_column(headers) or "")
        finite = angle_values[np.isfinite(angle_values)]
        if len(np.unique(np.round(finite, 6))) >= 3:
            return "pattern"
    if smith_real_column(headers) and smith_imag_column(headers):
        return "smith"
    if has_complex_values(dataset, complex_s_column(headers)):
        return "smith"
    if s11_column(headers):
        return "s11"
    if axial_ratio_column(headers):
        return "ar"
    if vswr_column(headers):
        return "vswr"
    if efficiency_column(headers):
        return "eff"
    if hpbw_column(headers):
        return "hpbw"
    if gain_column(headers):
        return "gain"
    return "response"


def inspect_csv(path: Path) -> CsvInfo:
    dataset = read_hfss_csv(path)
    columns = [
        ColumnInfo(name=header, is_numeric=is_numeric_column(dataset.rows, header))
        for header in dataset.headers
    ]
    return CsvInfo(path=path, columns=columns, row_count=len(dataset.rows), kind=detect_kind(dataset))


def format_parse_report(report: CsvParseReport) -> str:
    lines = [
        f"Columns: {', '.join(report.columns)}",
        f"Rows: {report.row_count}",
        f"Delimiter: {report.delimiter or 'unknown'}",
        f"Possible data type: {report.possible_data_type}",
        f"Missing values: {report.has_missing_values}",
        f"Duplicate points: {report.has_duplicate_points} ({report.duplicate_point_count})",
        "Units:",
    ]
    for column, unit in report.units.items():
        lines.append(f"  - {column}: {unit or 'unknown'}")
    lines.append("Ranges:")
    for column, value_range in report.ranges.items():
        if value_range:
            lines.append(f"  - {column}: {value_range[0]:.6g} to {value_range[1]:.6g}")
        else:
            lines.append(f"  - {column}: no finite numeric values")
    if report.missing_values:
        lines.append("Missing counts:")
        for column, count in report.missing_values.items():
            lines.append(f"  - {column}: {count}")
    if report.header_rows:
        lines.append(f"Header rows: {', '.join(str(row) for row in report.header_rows)}")
    if report.skipped_rows:
        lines.append(f"Skipped metadata rows: {', '.join(str(row) for row in report.skipped_rows)}")
    if report.warnings:
        lines.append("Warnings:")
        for warning in report.warnings:
            lines.append(f"  - {warning}")
    return "\n".join(lines)


def generic_column_name(name: str) -> bool:
    normalized_name = normalize(name)
    return normalized_name in {"x", "y", "value", "data"} or re.fullmatch(r"column\d+", normalized_name) is not None


def candidate_y_columns(dataset: HfssDataset) -> list[str]:
    kind = detect_kind(dataset)
    if kind == "s11":
        candidates = [s11_column(dataset.headers)]
    elif kind == "gain":
        candidates = [gain_column(dataset.headers)]
    elif kind == "vswr":
        candidates = [vswr_column(dataset.headers)]
    elif kind == "ar":
        candidates = [axial_ratio_column(dataset.headers)]
    elif kind == "eff":
        candidates = [efficiency_column(dataset.headers)]
    elif kind == "hpbw":
        candidates = [hpbw_column(dataset.headers)]
    elif kind == "pattern":
        candidates = pattern_value_columns(dataset.headers)
    elif kind == "smith":
        candidates = [smith_real_column(dataset.headers), smith_imag_column(dataset.headers)]
    else:
        freq_col = frequency_column(dataset.headers)
        candidates = [
            header
            for header in dataset.headers
            if header != freq_col and is_numeric_column(dataset.rows, header)
        ]
    return [candidate for candidate in candidates if candidate]


def recognition_from_dataset(
    dataset: HfssDataset,
    mode: OperationMode = "semiauto",
    overrides: dict | None = None,
) -> RecognitionResult:
    overrides = overrides or {}
    parse_report = dataset.parse_report
    units = parse_report.units if parse_report else infer_units(dataset.headers)
    kind = "unknown" if mode == "manual" else detect_kind(dataset)
    x_col = None if mode == "manual" else frequency_column(dataset.headers) or theta_column(dataset.headers) or phi_column(dataset.headers)
    y_cols: list[str] = [] if mode == "manual" else candidate_y_columns(dataset)
    reasons: list[str] = []
    warnings: list[str] = list(parse_report.warnings if parse_report else [])

    if parse_report and not parse_report.header_rows:
        reasons.append("文件无表头，必须手动确认列含义。")
    if any(generic_column_name(header) for header in dataset.headers):
        reasons.append("列名过于通用，必须手动确认变量映射。")
    if x_col and infer_x_quantity(x_col) == "frequency" and not units.get(x_col):
        reasons.append("频率单位无法确认。")
    if not x_col and mode != "manual":
        reasons.append("未能确认 X 轴列。")
    if kind == "s11":
        y_text = " ".join(y_cols).lower()
        if "db" not in y_text and "mag" not in y_text:
            reasons.append("S11 是 dB 还是线性幅度无法确认。")
    if len(y_cols) > 1 and kind not in {"pattern", "smith"}:
        reasons.append("检测到多个可能的 Y 轴列。")
    joined_headers = " ".join(dataset.headers).lower()
    if "formatteddata" in normalize(joined_headers):
        reasons.append("VNA 文件只有 Formatted Data，变量含义必须手动确认。")
    if kind == "pattern":
        if not (theta_column(dataset.headers) and phi_column(dataset.headers)):
            reasons.append("方向图切面无法确认。")
        reasons.append("方向图归一化状态无法确认。")
    if mode == "manual":
        reasons.append("手动模式不会推断物理意义，必须指定 X/Y 列、单位、图类型、标签和归一化状态。")
        kind = "unknown"

    curves: list[dict] = []
    if x_col:
        for y_col in y_cols:
            curves.append(
                {
                    "x_column": x_col,
                    "y_column": y_col,
                    "x_unit": infer_x_unit(x_col, units.get(x_col)),
                    "y_unit": infer_y_unit(y_col, infer_y_quantity(y_col), units.get(y_col)),
                    "y_quantity": infer_y_quantity(y_col),
                    "label": y_col,
                    "is_normalized": False,
                }
            )

    return RecognitionResult(
        mode=mode,
        detected_delimiter=parse_report.delimiter if parse_report else None,
        detected_header_rows=parse_report.header_rows if parse_report else [],
        detected_x_column=x_col,
        detected_y_columns=y_cols,
        detected_units=units,
        detected_plot_type=kind,
        detected_curves=curves,
        requires_confirmation=mode in {"semiauto", "manual"} or bool(reasons),
        confirmation_reasons=reasons,
        warnings=warnings,
        user_overrides=overrides,
    )


def dataset_model_from_hfss(dataset: HfssDataset) -> Dataset:
    kind = detect_kind(dataset)
    warnings: list[str] = list(dataset.parse_report.warnings if dataset.parse_report else [])
    if not frequency_column(dataset.headers) and kind in {"s11", "gain", "vswr", "ar", "eff", "hpbw", "response"}:
        warnings.append("No explicit frequency column detected.")
    metadata = {
        "legacy_kind": kind,
        "detected_frequency_column": frequency_column(dataset.headers),
    }
    if dataset.parse_report:
        metadata.update(
            {
                "delimiter": dataset.parse_report.delimiter,
                "header_rows": dataset.parse_report.header_rows,
                "skipped_rows": dataset.parse_report.skipped_rows,
                "metadata_rows": dataset.parse_report.metadata_rows,
                "ranges": dataset.parse_report.ranges,
                "has_missing_values": dataset.parse_report.has_missing_values,
                "missing_values": dataset.parse_report.missing_values,
                "has_duplicate_points": dataset.parse_report.has_duplicate_points,
                "duplicate_point_count": dataset.parse_report.duplicate_point_count,
                "possible_data_type": dataset.parse_report.possible_data_type,
            }
        )
    return Dataset(
        source_file=dataset.path,
        source_type=infer_source_type(dataset.path, dataset.headers),
        file_format=infer_file_format(dataset.path),
        data_type=infer_data_type(kind),
        columns=dataset.headers,
        units=infer_units(dataset.headers),
        row_count=len(dataset.rows),
        warnings=warnings,
        metadata=metadata,
    )


def curve_from_columns(
    dataset: HfssDataset,
    x_column: str,
    y_column: str,
    *,
    x_unit: str | None = None,
    y_unit: str | None = None,
    label: str | None = None,
    normalize_curve: bool = False,
) -> Curve:
    if x_column not in dataset.headers:
        raise ValueError(f"X column not found: {x_column}")
    if y_column not in dataset.headers:
        raise ValueError(f"Y column not found: {y_column}")
    model = dataset.to_model()
    x_values = dataset.column(x_column)
    y_values = dataset.column(y_column)
    conversion = None
    x_quantity = infer_x_quantity(x_column)
    final_x_unit = infer_x_unit(x_column, x_unit)
    if x_quantity == "frequency":
        converted, detected_unit = convert_frequency(x_values, x_column, final_x_unit.lower())
        x_values = converted
        final_x_unit = infer_x_unit(x_column, detected_unit)
        conversion = f"frequency converted to {detected_unit}"
    y_quantity = infer_y_quantity(y_column)
    final_y_unit = infer_y_unit(y_column, y_quantity, y_unit)
    warnings: list[str] = []
    if y_quantity == "S11" and final_y_unit != "dB":
        warnings.append("S11 curve is not explicitly in dB; confirm dB(S(1,1)) vs mag(S(1,1)).")
    if normalize_curve:
        finite = y_values[np.isfinite(y_values)]
        if finite.size:
            y_values = y_values - float(np.nanmax(finite))
            final_y_unit = "dB"
            conversion = f"{conversion}; normalized to 0 dB max" if conversion else "normalized to 0 dB max"
        else:
            warnings.append("Normalization requested but y data has no finite values.")
    return Curve(
        dataset_id=model.dataset_id or "",
        x_data=x_values,
        y_data=y_values,
        x_column=x_column,
        y_column=y_column,
        x_quantity=x_quantity,
        y_quantity=y_quantity,
        x_unit=final_x_unit,
        y_unit=final_y_unit,
        label=label or y_column,
        is_enabled=True,
        is_normalized=normalize_curve,
        conversion=conversion,
        warnings=warnings,
    )


def auto_curves_from_hfss(dataset: HfssDataset, *, x_unit: str | None = None) -> list[Curve]:
    x_col = frequency_column(dataset.headers) or theta_column(dataset.headers) or phi_column(dataset.headers)
    if not x_col:
        return []
    kind = detect_kind(dataset)
    if kind == "s11":
        y_cols = [s11_column(dataset.headers)]
    elif kind == "gain":
        y_cols = [gain_column(dataset.headers)]
    elif kind == "vswr":
        y_cols = [vswr_column(dataset.headers)]
    elif kind == "ar":
        y_cols = [axial_ratio_column(dataset.headers)]
    elif kind == "eff":
        y_cols = [efficiency_column(dataset.headers)]
    elif kind == "hpbw":
        y_cols = [hpbw_column(dataset.headers)]
    elif kind == "pattern":
        y_cols = pattern_value_columns(dataset.headers)
    else:
        y_cols = []
    return [
        curve_from_columns(dataset, x_col, y_col, x_unit=x_unit)
        for y_col in y_cols
        if y_col
    ]


def csv_files(path: Path) -> list[Path]:
    if path.is_file():
        if path.suffix.lower() != ".csv":
            raise ValueError("Input file must be a CSV file.")
        return [path]
    if not path.is_dir():
        raise ValueError(f"Input path does not exist: {path}")
    return sorted(item for item in path.glob("*.csv") if item.is_file())
