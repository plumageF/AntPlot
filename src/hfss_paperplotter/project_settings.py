"""Project-level antenna metric settings."""

from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .reader import (
    HfssDataset,
    axial_ratio_column,
    frequency_column,
    gain_column,
    s11_column,
    to_ghz,
    vswr_column,
)


@dataclass
class ProjectSettings:
    working_band_mhz: tuple[float, float] | None = None
    s11_threshold_db: float = -10.0
    vswr_threshold: float = 2.0
    axial_ratio_threshold_db: float = 3.0
    min_gain_dbi: float = 0.0
    port_impedance_ohm: float = 50.0
    pattern_frequencies_mhz: list[float] = field(default_factory=lambda: [410.0, 450.0, 490.0])
    prefer_realized_gain: bool = True


def _float_pair(value: Any) -> tuple[float, float] | None:
    if value in (None, ""):
        return None
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return float(value[0]), float(value[1])
    if isinstance(value, str):
        text = value.replace("MHz", "").replace("mhz", "").replace("-", " ")
        parts = [part for part in text.replace(",", " ").split() if part]
        if len(parts) >= 2:
            return float(parts[0]), float(parts[1])
    return None


def project_settings_from_config(config: dict) -> ProjectSettings:
    project = config.get("project", {}) or {}
    s11 = config.get("s11", {}) or {}
    band = (
        _float_pair(project.get("working_band_mhz"))
        or _float_pair(project.get("working_band"))
        or _float_pair(project.get("target_band_mhz"))
    )
    pattern_freqs = project.get("pattern_frequencies_mhz", [410.0, 450.0, 490.0])
    if not isinstance(pattern_freqs, list):
        pattern_freqs = [pattern_freqs]
    return ProjectSettings(
        working_band_mhz=band,
        s11_threshold_db=float(project.get("s11_threshold_db", s11.get("threshold", -10.0))),
        vswr_threshold=float(project.get("vswr_threshold", 2.0)),
        axial_ratio_threshold_db=float(project.get("axial_ratio_threshold_db", project.get("ar_threshold_db", 3.0))),
        min_gain_dbi=float(project.get("min_gain_dbi", 0.0)),
        port_impedance_ohm=float(project.get("port_impedance_ohm", 50.0)),
        pattern_frequencies_mhz=[float(item) for item in pattern_freqs],
        prefer_realized_gain=bool(project.get("prefer_realized_gain", True)),
    )


def apply_project_settings(args: Namespace, settings: ProjectSettings) -> None:
    command = getattr(args, "command", None) or getattr(args, "plot_type", None) or ""
    command = str(command).lower()
    setattr(args, "project_settings", settings)

    if "s11" in command and getattr(args, "threshold", None) is None:
        args.threshold = settings.s11_threshold_db
    if "vswr" in command:
        if getattr(args, "vswr_threshold", None) is None:
            args.vswr_threshold = settings.vswr_threshold
        if getattr(args, "threshold", None) is None:
            args.threshold = settings.vswr_threshold
    if command in {"ar", "axial", "axial_ratio"} or "axial" in command:
        if getattr(args, "ar_threshold", None) is None:
            args.ar_threshold = settings.axial_ratio_threshold_db
        if getattr(args, "threshold", None) is None:
            args.threshold = settings.axial_ratio_threshold_db

    if settings.working_band_mhz and getattr(args, "fl", None) is None and getattr(args, "fh", None) is None:
        lo_mhz, hi_mhz = settings.working_band_mhz
        args.fl = lo_mhz / 1000.0
        args.fh = hi_mhz / 1000.0
        if getattr(args, "fc", None) is None:
            args.fc = (lo_mhz + hi_mhz) / 2000.0


def target_band_mhz(settings: ProjectSettings | None) -> tuple[float, float] | None:
    return settings.working_band_mhz if settings else None


def _band_mask(freq_mhz: np.ndarray, band: tuple[float, float]) -> np.ndarray:
    lo, hi = band
    return np.isfinite(freq_mhz) & (freq_mhz >= lo) & (freq_mhz <= hi)


def project_metric_summary(dataset: HfssDataset, command: str, settings: ProjectSettings) -> str:
    lines = [
        "Project settings:",
        f"- Port impedance: {settings.port_impedance_ohm:g} ohm",
        f"- Prefer Realized Gain: {settings.prefer_realized_gain}",
    ]
    if settings.working_band_mhz:
        lo, hi = settings.working_band_mhz
        lines.append(f"- Working band: {lo:g}-{hi:g} MHz")
    else:
        lines.append("- Working band: not specified; no pass/fail bandwidth judgment was made.")
        return "\n".join(lines)

    freq_col = frequency_column(dataset.headers)
    if not freq_col:
        lines.append("- No confirmed frequency column; project metric checks were skipped.")
        return "\n".join(lines)
    freq_mhz = to_ghz(dataset.column(freq_col), freq_col) * 1000.0
    finite_freq = freq_mhz[np.isfinite(freq_mhz)]
    if finite_freq.size == 0:
        lines.append("- Frequency column has no finite values; project metric checks were skipped.")
        return "\n".join(lines)
    mask = _band_mask(freq_mhz, settings.working_band_mhz)
    if not np.any(mask):
        lines.append("- Data does not cover the working band; metric checks were skipped.")
        return "\n".join(lines)
    if np.nanmin(finite_freq) > settings.working_band_mhz[0] or np.nanmax(finite_freq) < settings.working_band_mhz[1]:
        lines.append("- Data range does not fully cover the working band; pass/fail judgment is not reliable.")
        return "\n".join(lines)

    command = command.lower()
    if command == "s11":
        col = s11_column(dataset.headers)
        if col:
            values = dataset.column(col)[mask]
            worst = float(np.nanmax(values))
            passed = worst <= settings.s11_threshold_db
            lines.append(f"- S11 threshold: <= {settings.s11_threshold_db:g} dB; worst in band = {worst:.3g} dB; pass = {passed}.")
    elif command == "vswr":
        col = vswr_column(dataset.headers)
        if col:
            values = dataset.column(col)[mask]
            worst = float(np.nanmax(values))
            passed = worst <= settings.vswr_threshold
            lines.append(f"- VSWR threshold: <= {settings.vswr_threshold:g}; worst in band = {worst:.3g}; pass = {passed}.")
    elif command == "ar":
        col = axial_ratio_column(dataset.headers)
        if col:
            values = dataset.column(col)[mask]
            worst = float(np.nanmax(values))
            passed = worst <= settings.axial_ratio_threshold_db
            lines.append(f"- Axial ratio threshold: <= {settings.axial_ratio_threshold_db:g} dB; worst in band = {worst:.3g} dB; pass = {passed}.")
    elif command == "gain":
        col = gain_column(dataset.headers)
        if col:
            values = dataset.column(col)[mask]
            minimum = float(np.nanmin(values))
            passed = minimum >= settings.min_gain_dbi
            lines.append(f"- Minimum gain target: >= {settings.min_gain_dbi:g} dBi; minimum in band = {minimum:.3g} dBi; pass = {passed}.")
    return "\n".join(lines)
