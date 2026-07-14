"""Style loading and matplotlib setup."""

from __future__ import annotations

import copy
from pathlib import Path

import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
from matplotlib import font_manager

from .config import deep_merge, load_simple_yaml


DEFAULT_STYLE = {
    "figure": {"width": "single", "single_width": 3.5, "double_width": 7.0, "height": 2.6, "dpi": 600},
    "font": {"family": "Times New Roman", "fallback": "DejaVu Serif", "cjk_fallback": ["Noto Serif SC", "Noto Sans SC", "Microsoft YaHei", "SimHei", "SimSun"], "size": 8.5, "label_size": 9.0, "tick_size": 8.0, "legend_size": 8.0, "weight": "normal"},
    "line": {"width": 1.8, "marker_size": 4.0, "markers": False},
    "axis": {"spine_width": 0.9, "tick_direction": "in", "grid": True, "grid_alpha": 0.18},
    "colors": {"s11": "#C62828", "gain": "#1565C0", "gray": "#555555", "black": "#111111", "cycle": ["#4D4D4D", "#F23B3B", "#1F6FE5", "#2EAD67"]},
    "markers": {"cycle": ["s", "o", "^", "D", "v", "P"]},
    "frequency": {"unit": "ghz"},
    "legend": {"loc": "best"},
    "export": {"formats": ["png", "pdf", "svg"]},
}


CJK_FONT_FILES = [
    "C:/Windows/Fonts/NotoSerifSC-VF.ttf",
    "C:/Windows/Fonts/NotoSansSC-VF.ttf",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
]


def _register_cjk_fonts() -> list[str]:
    """Register common CJK fonts and return their matplotlib family names."""

    names: list[str] = []
    for font_path in CJK_FONT_FILES:
        path = Path(font_path)
        if not path.exists():
            continue
        try:
            font_manager.fontManager.addfont(str(path))
            name = font_manager.FontProperties(fname=str(path)).get_name()
            if name and name not in names:
                names.append(name)
        except Exception:
            continue
    return names


def style_path(name: str) -> Path:
    path = Path(name)
    if path.exists():
        return path
    if not path.suffix:
        path = Path(__file__).resolve().parents[2] / "styles" / f"{name}.yaml"
    return path


def load_style(name: str | None) -> dict:
    if not name:
        return copy.deepcopy(DEFAULT_STYLE)
    path = style_path(name)
    if path.exists():
        return deep_merge(copy.deepcopy(DEFAULT_STYLE), load_simple_yaml(path))
    return copy.deepcopy(DEFAULT_STYLE)


def apply_style(style: dict) -> None:
    font = style["font"]
    axis = style["axis"]
    configured_cjk = font.get("cjk_fallback", [])
    if isinstance(configured_cjk, str):
        configured_cjk = [configured_cjk]
    cjk_fonts = [*configured_cjk, *_register_cjk_fonts()]
    serif_fonts = [font["family"], *cjk_fonts, font["fallback"], "DejaVu Serif"]
    sans_fonts = [*cjk_fonts, "DejaVu Sans"]
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": list(dict.fromkeys(serif_fonts)),
            "font.sans-serif": list(dict.fromkeys(sans_fonts)),
            "font.size": font["size"],
            "mathtext.fontset": "stix",
            "axes.unicode_minus": False,
            "axes.linewidth": axis["spine_width"],
            "axes.labelsize": font["label_size"],
            "xtick.labelsize": font["tick_size"],
            "ytick.labelsize": font["tick_size"],
            "legend.fontsize": font["legend_size"],
            "legend.frameon": False,
            "font.weight": font.get("weight", "normal"),
            "axes.labelweight": font.get("weight", "normal"),
            "xtick.direction": axis["tick_direction"],
            "ytick.direction": axis["tick_direction"],
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "savefig.facecolor": "white",
            "figure.facecolor": "white",
        }
    )


def figure_size(style: dict, ratio: float = 0.72) -> tuple[float, float]:
    figure = style["figure"]
    width = figure["double_width"] if figure.get("width") == "double" else figure["single_width"]
    height = figure.get("height") or width * ratio
    return float(width), float(height)
