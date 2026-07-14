"""Data audit helpers for antenna simulation and measurement CSV files."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .messages import Message, message_from_text
from .reader import (
    HfssDataset,
    axial_ratio_column,
    efficiency_column,
    frequency_column,
    gain_column,
    normalize,
    pattern_value_columns,
    phi_column,
    read_hfss_csv,
    s11_column,
    smith_imag_column,
    smith_real_column,
    theta_column,
    to_ghz,
    vswr_column,
)
from .pattern_analysis import recognize_pattern


@dataclass
class AuditReport:
    path: Path
    row_count: int
    headers: list[str]
    numeric_columns: list[str]
    detected_kind: str
    frequency_column: str | None
    frequency_unit: str | None
    frequency_range: tuple[float, float] | None
    variable_columns: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)

    def add_error(self, code: str, text: str) -> None:
        self.messages.append(Message("error", code, text, {}))
        self.warnings.append(text)

    def add_warning(self, code: str, text: str) -> None:
        self.messages.append(Message("warning", code, text, {}))
        self.warnings.append(text)

    def add_info(self, code: str, text: str) -> None:
        self.messages.append(Message("info", code, text, {}))
        self.notes.append(text)


def _finite_range(values: np.ndarray) -> tuple[float, float] | None:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return None
    return float(np.nanmin(finite)), float(np.nanmax(finite))


def _unit_from_header(header: str | None) -> str | None:
    if not header:
        return None
    match = re.search(r"(?:\[|\()\s*((?:k|m|g|t)?hz)\s*(?:\]|\))", header, re.I)
    return match.group(1) if match else None


def _numeric_columns(dataset: HfssDataset) -> list[str]:
    numeric: list[str] = []
    for header in dataset.headers:
        values = dataset.column(header)
        finite = values[np.isfinite(values)]
        if finite.size >= max(1, int(len(values) * 0.6)):
            numeric.append(header)
    return numeric


def _classify_kind(dataset: HfssDataset) -> tuple[str, list[str]]:
    headers = dataset.headers
    variables: list[str] = []
    if s11_column(headers):
        variables.append(s11_column(headers) or "")
    if vswr_column(headers):
        variables.append(vswr_column(headers) or "")
    if axial_ratio_column(headers):
        variables.append(axial_ratio_column(headers) or "")
    if efficiency_column(headers):
        variables.append(efficiency_column(headers) or "")
    if gain_column(headers):
        variables.append(gain_column(headers) or "")
    if smith_real_column(headers) and smith_imag_column(headers):
        variables.extend([smith_real_column(headers) or "", smith_imag_column(headers) or ""])
    if theta_column(headers) or phi_column(headers):
        variables.extend(pattern_value_columns(headers))

    normalized = [normalize(header) for header in headers]
    if any("dbs" in item or "s11" in item for item in normalized):
        return "s11", variables
    if any("vswr" in item or "vsmr" in item for item in normalized):
        return "vswr", variables
    if any("axial" in item or item == "ar" for item in normalized):
        return "axial_ratio", variables
    if smith_real_column(headers) and smith_imag_column(headers):
        return "smith_or_complex_s", variables
    if theta_column(headers) or phi_column(headers):
        return "radiation_pattern", variables
    if any("realizedgain" in item for item in normalized):
        return "realized_gain", variables
    if any("gaintotal" in item or item == "gain" for item in normalized):
        return "gain", variables
    if any("efficiency" in item for item in normalized):
        return "efficiency", variables
    return "unknown", variables


def _check_variable_semantics(report: AuditReport) -> None:
    normalized = {header: normalize(header) for header in report.headers}
    if report.detected_kind == "s11":
        if not any("db" in normalized[col] for col in report.variable_columns if col in normalized):
            report.warnings.append("S 参数列未明确包含 dB 标记；请确认不是 mag(S(1,1)) 线性幅度。")
        report.notes.append("S11/VSWR/Smith/阻抗相关结果需要确认端口参考阻抗、参考面、renormalization 与 de-embed 设置。")
    if report.detected_kind in {"s11", "vswr", "smith_or_complex_s"}:
        report.warnings.append("端口参考面未确认；默认不判断 50 ohm、renormalization 或 de-embed 状态。")
    if report.detected_kind in {"gain", "realized_gain"}:
        has_realized = any("realizedgain" in value for value in normalized.values())
        has_gain = any("gaintotal" in value for value in normalized.values())
        has_directivity = any("directivity" in value for value in normalized.values())
        if has_realized:
            report.notes.append("检测到 Realized Gain；该变量通常包含端口失配影响。")
        if has_gain and not has_realized:
            report.warnings.append("检测到 GainTotal，但未检测到 RealizedGainTotal；请确认是否需要反映端口失配影响。")
        if has_directivity:
            report.warnings.append("检测到 Directivity；请勿与 Gain 或 Realized Gain 混用。")
    if report.detected_kind == "radiation_pattern":
        if theta_column(report.headers):
            report.notes.append(f"检测到 theta 扫描列: {theta_column(report.headers)}")
        if phi_column(report.headers):
            report.notes.append(f"检测到 phi 扫描列: {phi_column(report.headers)}")
        report.warnings.append("方向图切面、主极化/交叉极化方向未确认；图注应按数据列或文件名保守说明。")


def audit_dataset(dataset: HfssDataset, target_band: tuple[float, float] | None = None) -> AuditReport:
    freq_col = frequency_column(dataset.headers)
    detected_kind, variable_columns = _classify_kind(dataset)
    frequency_range = None
    frequency_unit = _unit_from_header(freq_col)
    warnings: list[str] = []
    notes: list[str] = []

    if not dataset.headers:
        warnings.append("CSV 未包含明确列名。")
    if freq_col:
        raw_freq = dataset.column(freq_col)
        freq_mhz = to_ghz(raw_freq, freq_col) * 1000.0
        frequency_range = _finite_range(freq_mhz)
        if frequency_unit is None:
            notes.append("频率列未写明单位，已按数值量级推断并统一审查为 MHz。")
        if frequency_range:
            lo, hi = frequency_range
            if 350 <= lo <= 600 or 350 <= hi <= 600:
                notes.append("频率范围处于 400-500 MHz 附近，建议横轴使用 Frequency (MHz)。")
            elif hi >= 1000:
                notes.append("频率范围高于 1 GHz，建议按需求使用 GHz 或 MHz，并保持坐标轴单位一致。")
    else:
        warnings.append("未找到明确频率列；禁止仅按列顺序默认第一列为频率。")

    if not variable_columns:
        warnings.append("未能通过列名确认物理变量；请手动指定变量列。")

    if target_band and frequency_range:
        lo, hi = frequency_range
        band_lo, band_hi = target_band
        if lo > band_lo or hi < band_hi:
            warnings.append(
                f"数据范围 {lo:.6g}-{hi:.6g} MHz 未完整覆盖目标频段 {band_lo:.6g}-{band_hi:.6g} MHz；停止合格性判断。"
            )
        else:
            notes.append(f"目标频段 {band_lo:.6g}-{band_hi:.6g} MHz 已被数据覆盖。")
    elif target_band is None:
        notes.append("未指定目标频段，未进行带宽合格性判断。")

    report = AuditReport(
        path=dataset.path,
        row_count=len(dataset.rows),
        headers=dataset.headers,
        numeric_columns=_numeric_columns(dataset),
        detected_kind=detected_kind,
        frequency_column=freq_col,
        frequency_unit=frequency_unit,
        frequency_range=frequency_range,
        variable_columns=[column for column in variable_columns if column],
        warnings=warnings,
        notes=notes,
    )
    report.messages.extend(message_from_text("warning", warning) for warning in report.warnings)
    report.messages.extend(message_from_text("info", note, code="info") for note in report.notes)
    if not dataset.rows:
        report.add_error("empty_data", "数据为空，无法继续作图。")
    if not dataset.headers:
        report.add_error("missing_columns", "缺少必要列，无法继续作图。")
    if target_band and frequency_range:
        lo, hi = frequency_range
        band_lo, band_hi = target_band
        if hi < band_lo or lo > band_hi:
            report.add_error("target_band_outside_data", "目标频段完全不在数据范围内，禁止输出确定性工程结论。")
        elif lo > band_lo or hi < band_hi:
            report.add_warning("target_band_not_fully_covered", "目标频段未被数据完整覆盖，结论不可靠。")
    elif target_band and not frequency_range:
        report.add_error("target_band_unchecked", "无法确认数据频率范围，不能判断目标频段。")
    _check_variable_semantics(report)
    if report.detected_kind == "radiation_pattern":
        pattern_info = recognize_pattern(dataset)
        report.notes.append(f"方向图切面识别: {pattern_info.description()}")
        if pattern_info.cut_type == "unconfirmed":
            report.warnings.append("方向图切面未确认；不得自动称为 E 面或 H 面。")
    existing = {(message.severity, message.text) for message in report.messages}
    for warning in report.warnings:
        if ("warning", warning) not in existing:
            report.messages.append(message_from_text("warning", warning))
            existing.add(("warning", warning))
    for note in report.notes:
        if ("info", note) not in existing:
            report.messages.append(message_from_text("info", note, code="info"))
            existing.add(("info", note))
    return report


def audit_csv(path: Path, target_band: tuple[float, float] | None = None) -> AuditReport:
    return audit_dataset(read_hfss_csv(path), target_band)


def format_audit(report: AuditReport) -> str:
    lines = [
        f"File: {report.path}",
        f"Rows: {report.row_count}",
        f"Detected kind: {report.detected_kind}",
        f"Frequency column: {report.frequency_column or 'NOT FOUND'}",
    ]
    if report.frequency_range:
        lo, hi = report.frequency_range
        unit_text = report.frequency_unit or "inferred"
        lines.append(f"Frequency range: {lo:.6g} to {hi:.6g} MHz ({unit_text})")
    lines.append("Columns:")
    for header in report.headers:
        marker = "numeric" if header in report.numeric_columns else "text"
        used = " used" if header in report.variable_columns or header == report.frequency_column else ""
        lines.append(f"  - {header} ({marker}{used})")
    if report.variable_columns:
        lines.append("Variables used or detected:")
        for column in report.variable_columns:
            lines.append(f"  - {column}")
    if report.warnings:
        lines.append("Warnings:")
        for item in report.warnings:
            lines.append(f"  - {item}")
    if report.notes:
        lines.append("Notes:")
        for item in report.notes:
            lines.append(f"  - {item}")
    return "\n".join(lines)
