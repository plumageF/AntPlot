from __future__ import annotations

import json
import shutil
import subprocess
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "final_acceptance"
PYTHON = sys.executable
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass
class Result:
    name: str
    passed: bool
    detail: str


def run(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PYTHON, str(ROOT / "main.py"), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def exists(directory: Path, suffix: str) -> bool:
    return any(path.suffix.lower() == suffix for path in directory.glob("*"))


def read_json(directory: Path) -> dict:
    paths = sorted(directory.glob("*.json"))
    require(bool(paths), f"no JSON file in {directory}")
    return json.loads(paths[0].read_text(encoding="utf-8"))


def record(name: str, func) -> Result:
    try:
        detail = func()
        return Result(name, True, detail or "passed")
    except Exception as exc:  # pragma: no cover - command-line acceptance output
        return Result(name, False, f"{exc}\n{traceback.format_exc(limit=1)}")


def clean() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)


def test_01_standard_hfss_s11() -> str:
    provided = Path(r"D:\CSV\11.7.csv")
    if provided.exists():
        header = provided.read_text(encoding="utf-8-sig", errors="ignore").splitlines()[0]
        require("dB(S(1,1))" in header or "S11" in header, f"provided file is not an S11 CSV: {header}")
        source = provided
    else:
        source = ROOT / "examples" / "s11_cases" / "case01_hfss_standard.csv"
    out = OUT / "01_standard_hfss"
    cp = run(["s11", str(source), "--output-dir", str(out), "--formats", "png", "json", "txt"])
    require(cp.returncode == 0, cp.stderr or cp.stdout)
    config = read_json(out)
    require(config.get("plot_type") == "s11", "export JSON plot_type is not s11")
    return f"generated {source.name}"


def test_02_wide_sim_measured() -> str:
    from src.hfss_paperplotter.reader import read_hfss_csv
    from src.hfss_paperplotter.s11_import import s11_curves_from_dataset

    source = ROOT / "examples" / "s11_cases" / "case03_wide_multi_curve.csv"
    result = s11_curves_from_dataset(read_hfss_csv(source), x_unit="MHz")
    labels = [curve.label for curve in result.curves]
    require(len(result.curves) == 2, f"expected 2 curves, got {labels}")
    out = OUT / "02_wide_sim_measured"
    cp = run(["s11", str(source), "--output-dir", str(out), "--formats", "png", "json", "txt"])
    require(cp.returncode == 0, cp.stderr or cp.stdout)
    require(exists(out, ".png"), "no PNG exported")
    return ", ".join(labels)


def test_03_multiple_csv_overlay() -> str:
    out = OUT / "03_multi_csv"
    cp = run(
        [
            "overlay",
            str(ROOT / "examples" / "s11_cases" / "case01_hfss_standard.csv"),
            str(ROOT / "examples" / "s11_cases" / "case02_common_single.csv"),
            "--plot-type",
            "s11",
            "--output-dir",
            str(out),
            "--formats",
            "png",
            "json",
            "txt",
        ]
    )
    require(cp.returncode == 0, cp.stderr or cp.stdout)
    require(exists(out, ".png") and exists(out, ".json"), "overlay artifacts missing")
    return "overlay exported"


def test_04_vna_hz_to_mhz() -> str:
    from src.hfss_paperplotter.reader import read_hfss_csv
    from src.hfss_paperplotter.s11_import import s11_curves_from_dataset

    source = ROOT / "examples" / "s11_cases" / "case06b_vna_logmag.csv"
    curve = s11_curves_from_dataset(read_hfss_csv(source), x_unit="MHz").curves[0]
    require(curve.x_unit == "MHz", f"unit not converted to MHz: {curve.x_unit}")
    require(390 <= float(curve.x_data[0]) <= 410, f"unexpected converted x value: {curve.x_data[0]}")
    return f"{curve.x_data[0]:.1f} {curve.x_unit}"


def test_05_mag_to_db() -> str:
    from src.hfss_paperplotter.reader import read_hfss_csv
    from src.hfss_paperplotter.s11_import import s11_curves_from_dataset

    source = ROOT / "examples" / "s11_cases" / "case07_linear_mag.csv"
    curve = s11_curves_from_dataset(read_hfss_csv(source), x_unit="GHz").curves[0]
    require("20log10" in (curve.conversion or ""), f"missing conversion note: {curve.conversion}")
    require(float(curve.y_data[1]) < -17.0, f"linear magnitude was not converted to dB: {curve.y_data}")
    return curve.conversion or ""


def test_06_re_im_and_smith() -> str:
    from src.hfss_paperplotter.reader import read_hfss_csv
    from src.hfss_paperplotter.s11_import import s11_curves_from_dataset

    source = ROOT / "examples" / "s11_cases" / "case08_re_im.csv"
    curve = s11_curves_from_dataset(read_hfss_csv(source), x_unit="GHz").curves[0]
    require("sqrt" in (curve.conversion or ""), f"missing re/im conversion note: {curve.conversion}")
    out = OUT / "06_smith"
    cp = run(["smith", str(source), "--output-dir", str(out), "--formats", "png", "json", "txt"])
    require(cp.returncode == 0, cp.stderr or cp.stdout)
    require(exists(out, ".png"), "smith PNG missing")
    return curve.conversion or ""


def test_07_no_header_confirmation() -> str:
    from src.hfss_paperplotter.reader import read_hfss_csv
    from src.hfss_paperplotter.s11_import import s11_curves_from_dataset

    source = ROOT / "examples" / "s11_cases" / "case10_no_header.csv"
    result = s11_curves_from_dataset(read_hfss_csv(source), x_unit="MHz")
    require(result.requires_confirmation, "no-header file did not require confirmation")
    require(not result.curves, "no-header file produced confirmed curves")
    return "; ".join(result.warnings)


def test_08_band_and_threshold() -> str:
    source = ROOT / "examples" / "acceptance" / "s11_410_490.csv"
    out = OUT / "08_band_threshold"
    cp = run(
        [
            "s11",
            str(source),
            "--config",
            str(ROOT / "examples" / "project_settings_410_490.yaml"),
            "--output-dir",
            str(out),
            "--formats",
            "png",
            "json",
            "txt",
        ]
    )
    require(cp.returncode == 0, cp.stderr or cp.stdout)
    report = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in out.glob("*.txt"))
    require("-10" in report or "S11" in report, "report did not include S11/threshold context")
    config = read_json(out)
    require(config.get("target_band") or config.get("project_settings", {}).get("working_band_mhz"), "target band not saved")
    return "410-490 MHz band exported"


def test_09_multi_export_formats() -> str:
    out = OUT / "09_multi_export"
    cp = run(
        [
            "overlay",
            str(ROOT / "examples" / "s11_cases" / "case01_hfss_standard.csv"),
            str(ROOT / "examples" / "s11_cases" / "case02_common_single.csv"),
            "--plot-type",
            "s11",
            "--output-dir",
            str(out),
            "--formats",
            "png",
            "pdf",
            "json",
            "txt",
        ]
    )
    require(cp.returncode == 0, cp.stderr or cp.stdout)
    for suffix in [".png", ".pdf", ".json", ".txt"]:
        require(exists(out, suffix), f"missing {suffix}")
    return "PNG/PDF/JSON/report exported"


def test_10_band_not_covered() -> str:
    source = ROOT / "examples" / "s11_cases" / "case01_hfss_standard.csv"
    out = OUT / "10_outside_band"
    cp = run(
        [
            "s11",
            str(source),
            "--config",
            str(ROOT / "examples" / "project_settings_410_490.yaml"),
            "--output-dir",
            str(out),
            "--formats",
            "png",
            "json",
            "txt",
        ]
    )
    require(cp.returncode == 0, cp.stderr or cp.stdout)
    config = read_json(out)
    messages = config.get("messages", [])
    require(any(item.get("severity") == "error" and item.get("code") == "target_band_outside_data" for item in messages), messages)
    report = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in out.glob("*.txt"))
    require("disabled" in report.lower() or "禁用" in report, "deterministic conclusion was not disabled")
    return "target_band_outside_data error recorded"


def test_11_modes() -> str:
    from src.hfss_paperplotter.preview_server import create_preview

    source = ROOT / "examples" / "s11_cases" / "case01_hfss_standard.csv"
    auto = create_preview({"inputPath": str(source), "plotType": "S11 / Return Loss", "mode": "auto", "outputDir": str(OUT / "11_auto")})
    require(auto["ok"], "auto mode failed")
    try:
        create_preview({"inputPath": str(source), "plotType": "S11 / Return Loss", "mode": "semiauto", "outputDir": str(OUT / "11_semiauto_block")})
    except ValueError as exc:
        require("confirmation" in str(exc).lower(), f"unexpected semiauto error: {exc}")
    else:
        raise AssertionError("semiauto without user confirmation did not block")
    semi = create_preview(
        {
            "inputPath": str(source),
            "plotType": "S11 / Return Loss",
            "mode": "semiauto",
            "userConfirmed": True,
            "outputDir": str(OUT / "11_semiauto"),
        }
    )
    manual = create_preview(
        {
            "inputPath": str(source),
            "plotType": "S11 / Return Loss",
            "mode": "manual",
            "xColumn": "Freq [GHz]",
            "yColumn": "dB(S(1,1)) []",
            "outputDir": str(OUT / "11_manual"),
        }
    )
    require(semi["ok"] and manual["ok"], "semiauto/manual mode failed")
    return "auto, semiauto confirmation, manual passed"


def test_12_backend_preview_same_logic() -> str:
    from src.hfss_paperplotter.preview_server import create_preview

    source = ROOT / "examples" / "s11_cases" / "case01_hfss_standard.csv"
    preview = create_preview(
        {
            "inputPath": str(source),
            "plotType": "S11 / Return Loss",
            "mode": "auto",
            "outputDir": str(OUT / "12_preview"),
            "formats": ["png", "pdf", "svg", "json", "txt", "md"],
        }
    )
    png_outputs = [path for path in preview["outputs"] if path.lower().endswith(".png")]
    require(png_outputs, "backend did not return a PNG preview/export")
    require(Path(png_outputs[0]).exists(), "preview PNG path does not exist")
    frontend = (ROOT / "frontend" / "src" / "main.tsx").read_text(encoding="utf-8")
    forbidden = ["NetworkGraph", "LinePreview", "PolarPreview", "<svg"]
    require(not any(token in frontend for token in forbidden), "frontend still contains fake preview drawing code")
    return "preview image is backend generated"


def main() -> int:
    clean()
    tests = [
        ("1. Standard HFSS S11 CSV", test_01_standard_hfss_s11),
        ("2. Simulated/Measured wide CSV", test_02_wide_sim_measured),
        ("3. Multiple CSV overlay", test_03_multiple_csv_overlay),
        ("4. VNA Hz to MHz", test_04_vna_hz_to_mhz),
        ("5. mag(S11) to dB", test_05_mag_to_db),
        ("6. re/im S11 and Smith", test_06_re_im_and_smith),
        ("7. No-header confirmation", test_07_no_header_confirmation),
        ("8. Band and threshold", test_08_band_and_threshold),
        ("9. Multi-format export", test_09_multi_export_formats),
        ("10. Target band not covered", test_10_band_not_covered),
        ("11. Operation modes", test_11_modes),
        ("12. Backend preview/export parity", test_12_backend_preview_same_logic),
    ]
    results = [record(name, func) for name, func in tests]
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"{status}\t{result.name}\t{result.detail}")
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
