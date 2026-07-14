"""Regression checks for HFSS-like report recognition edge cases."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.hfss_paperplotter.backend_api import dispatch

CASE_DIR = ROOT / "outputs" / "recognition_regression_cases"


def write_case(name: str, text: str) -> Path:
    CASE_DIR.mkdir(parents=True, exist_ok=True)
    path = CASE_DIR / name
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path


def import_model(path: Path) -> dict:
    result = dispatch(
        "import_files",
        {
            "session_id": f"recognition_regression_{path.stem}",
            "files": [str(path)],
            "mode": "semiauto",
        },
    )
    if not result["ok"]:
        raise AssertionError(f"Import failed for {path.name}: {result['errors']}")
    recognition = result["data"]["recognitions"][0]
    return recognition["report_model"] or recognition["report_plan"]["report_model"]


def assert_equal(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def main() -> None:
    cases = {
        "nonstandard_s11": write_case(
            "nonstandard_s11.csv",
            """
            Solution Freq [GHz], S-Parameter S(1,1) Log Mag (dB)
            0.40,-8
            0.45,-18
            0.50,-7
            """,
        ),
        "return_loss_positive": write_case(
            "return_loss_positive.csv",
            """
            Frequency [GHz], Return Loss [dB]
            0.40,8
            0.45,15
            0.50,9
            """,
        ),
        "return_loss_negative": write_case(
            "return_loss_negative.csv",
            """
            Frequency [GHz], Return Loss [dB]
            0.40,-8
            0.45,-15
            0.50,-9
            """,
        ),
        "far_field_grid": write_case(
            "far_field_grid.csv",
            """
            Theta [deg], Phi [deg], dB(RealizedGainTotal) []
            0,0,-6
            0,90,-5
            0,180,-6
            30,0,0
            30,90,-1
            30,180,-2
            60,0,-4
            60,90,-3
            60,180,-4
            """,
        ),
        "theta_phi_family": write_case(
            "theta_phi_family.csv",
            """
            Theta [deg], Phi [deg], dB(RealizedGainTotal) []
            -180,0,-12
            -90,0,-6
            0,0,0
            90,0,-6
            180,0,-12
            -180,90,-10
            -90,90,-5
            0,90,-1
            90,90,-5
            180,90,-10
            """,
        ),
    }

    nonstandard = import_model(cases["nonstandard_s11"])
    assert_equal(nonstandard["report_domain"], "solution_data", "nonstandard S11 domain")
    assert_equal(nonstandard["quantity"], "S11_dB", "nonstandard S11 quantity")

    positive = import_model(cases["return_loss_positive"])
    assert_equal(positive["quantity"], "ReturnLoss_dB", "positive Return Loss quantity")
    if not any("positive dB" in item for item in positive["infos"]):
        raise AssertionError("positive Return Loss should include threshold convention info")

    negative = import_model(cases["return_loss_negative"])
    assert_equal(negative["quantity"], "ReturnLoss_dB", "negative Return Loss quantity")
    if not any("may actually be S11" in item for item in negative["warnings"]):
        raise AssertionError("negative Return Loss should warn about sign convention")

    grid = import_model(cases["far_field_grid"])
    assert_equal(grid["report_domain"], "far_field", "far-field grid domain")
    assert_equal(grid["data_class"], "far_field_grid", "far-field grid data_class")

    family = import_model(cases["theta_phi_family"])
    assert_equal(family["report_domain"], "far_field", "theta/phi family domain")
    assert_equal(family["data_class"], "angular_cut", "theta/phi family data_class")

    for label, path in cases.items():
        model = import_model(path)
        print(f"{label}: domain={model['report_domain']}, type={model['report_type']}, sweep={model['primary_sweep']}, quantity={model['quantity']}, class={model['data_class']}")


if __name__ == "__main__":
    main()
