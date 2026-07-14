"""Shared data models used between import, audit, plotting, and UI layers."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np


SourceType = Literal["HFSS", "CST", "ADS", "VNA", "Manual", "Unknown"]
FileFormat = Literal["CSV", "TXT", "XLSX", "S1P", "S2P", "SNP"]
DataType = Literal[
    "frequency_response",
    "radiation_pattern",
    "complex_sparam",
    "smith",
    "unknown",
]
XQuantity = Literal["frequency", "theta", "phi", "angle"]
YQuantity = Literal[
    "S11",
    "ReturnLoss",
    "VSWR",
    "Gain",
    "RealizedGain",
    "AR",
    "Efficiency",
    "Phase",
    "HPBW",
]
XUnit = Literal["Hz", "MHz", "GHz", "deg"]
YUnit = Literal["dB", "dBi", "linear", "degree"]
OperationMode = Literal["auto", "semiauto", "manual"]
CurveSource = Literal["Simulated", "Measured", "Reference", "Manual", "Unknown"]


@dataclass
class Dataset:
    """A raw source file after import and metadata inspection."""

    source_file: Path
    source_type: SourceType
    file_format: FileFormat
    data_type: DataType
    columns: list[str]
    units: dict[str, str | None]
    row_count: int
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    dataset_id: str | None = None

    def __post_init__(self) -> None:
        if self.dataset_id is None:
            self.dataset_id = dataset_id_for(self.source_file)


@dataclass
class Curve:
    """A plotted curve derived from one Dataset."""

    dataset_id: str
    x_data: np.ndarray
    y_data: np.ndarray
    x_column: str
    y_column: str
    x_quantity: XQuantity
    y_quantity: YQuantity
    x_unit: XUnit
    y_unit: YUnit
    label: str
    is_enabled: bool = True
    is_normalized: bool = False
    conversion: str | None = None
    warnings: list[str] = field(default_factory=list)
    source_role: CurveSource = "Unknown"
    order: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RecognitionResult:
    """Automatic or semi-automatic interpretation of an imported Dataset."""

    mode: OperationMode
    detected_delimiter: str | None
    detected_header_rows: list[int]
    detected_x_column: str | None
    detected_y_columns: list[str]
    detected_units: dict[str, str | None]
    detected_plot_type: str
    detected_curves: list[dict[str, Any]]
    requires_confirmation: bool
    confirmation_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    user_overrides: dict[str, Any] = field(default_factory=dict)


def dataset_id_for(path: Path) -> str:
    text = str(path.resolve()).lower()
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def infer_file_format(path: Path) -> FileFormat:
    suffix = path.suffix.lower().lstrip(".")
    if suffix == "csv":
        return "CSV"
    if suffix == "txt":
        return "TXT"
    if suffix == "xlsx":
        return "XLSX"
    if suffix == "s1p":
        return "S1P"
    if suffix == "s2p":
        return "S2P"
    if suffix.endswith("p") and suffix[0:1].lower() == "s":
        return "SNP"
    return "CSV"


def infer_source_type(path: Path, columns: list[str]) -> SourceType:
    text = " ".join([path.name, *columns]).lower()
    if "hfss" in text or "ansys" in text or "setup" in text:
        return "HFSS"
    if "cst" in text:
        return "CST"
    if "ads" in text:
        return "ADS"
    if "vna" in text or "measured" in text or "measurement" in text:
        return "VNA"
    return "Unknown"


def infer_unit(column: str) -> str | None:
    match = re.search(r"(?:\[|\()\s*([A-Za-z%/]+)\s*(?:\]|\))", column)
    if match:
        return match.group(1)
    normalized = re.sub(r"[^a-z0-9]", "", column.lower())
    if "db" in normalized:
        return "dB"
    if "degree" in normalized or "theta" in normalized or "phi" in normalized:
        return "deg"
    if "vswr" in normalized:
        return "linear"
    return None


def infer_units(columns: list[str]) -> dict[str, str | None]:
    return {column: infer_unit(column) for column in columns}


def infer_data_type(kind: str) -> DataType:
    if kind in {"s11", "gain", "vswr", "ar", "eff", "hpbw", "response"}:
        return "frequency_response"
    if kind == "pattern":
        return "radiation_pattern"
    if kind == "smith":
        return "smith"
    return "unknown"


def infer_x_quantity(column: str) -> XQuantity:
    normalized = re.sub(r"[^a-z0-9]", "", column.lower())
    if "theta" in normalized:
        return "theta"
    if "phi" in normalized:
        return "phi"
    if "angle" in normalized:
        return "angle"
    return "frequency"


def infer_y_quantity(column: str) -> YQuantity:
    normalized = re.sub(r"[^a-z0-9]", "", column.lower())
    if "returnloss" in normalized:
        return "ReturnLoss"
    if "hpbw" in normalized or "halfpowerbeamwidth" in normalized or "beamwidth" in normalized:
        return "HPBW"
    if "vswr" in normalized or "vsmr" in normalized:
        return "VSWR"
    if "axialratio" in normalized or normalized == "ar" or normalized.endswith("ar"):
        return "AR"
    if "efficiency" in normalized:
        return "Efficiency"
    if "phase" in normalized:
        return "Phase"
    if "realizedgain" in normalized:
        return "RealizedGain"
    if "gain" in normalized:
        return "Gain"
    return "S11"


def infer_x_unit(column: str, explicit_unit: str | None = None) -> XUnit:
    unit = (explicit_unit or infer_unit(column) or "").lower()
    if unit == "hz":
        return "Hz"
    if unit == "mhz":
        return "MHz"
    if unit == "ghz":
        return "GHz"
    if unit in {"deg", "degree"}:
        return "deg"
    if infer_x_quantity(column) in {"theta", "phi", "angle"}:
        return "deg"
    return "GHz"


def infer_y_unit(column: str, quantity: YQuantity | None = None, explicit_unit: str | None = None) -> YUnit:
    unit = (explicit_unit or infer_unit(column) or "").lower()
    if unit in {"dbi"}:
        return "dBi"
    if unit in {"db"}:
        return "dB"
    if unit in {"deg", "degree"}:
        return "degree"
    if quantity in {"Gain", "RealizedGain"}:
        return "dBi" if "db" in re.sub(r"[^a-z0-9]", "", column.lower()) else "linear"
    if quantity in {"S11", "AR"}:
        return "dB"
    if quantity == "Phase":
        return "degree"
    return "linear"
