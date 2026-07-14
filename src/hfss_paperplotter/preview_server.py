"""Local HTTP preview server for backend-matched figure previews."""

from __future__ import annotations

import json
import mimetypes
import time
from argparse import Namespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .audit import audit_dataset, format_audit
from .config import load_project_config
from .engineering_metrics import curves_from_dataset_for_metrics, metric_results_for_dataset
from .export_artifacts import split_export_formats, write_export_artifacts
from .project_settings import apply_project_settings, project_metric_summary, project_settings_from_config, target_band_mhz
from .reader import recognition_from_dataset, read_hfss_csv
from .reporting import assemble_report


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "outputs" / "backend_preview"
ALLOWED_FILE_ROOTS = [(ROOT / "outputs").resolve()]
ALLOWED_ORIGINS = {"http://127.0.0.1:4173", "http://localhost:4173", "http://127.0.0.1:5173", "http://localhost:5173"}


def _is_allowed_file(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    return any(resolved == root or root in resolved.parents for root in ALLOWED_FILE_ROOTS)


def _plot_command(plot_type: str) -> str:
    text = plot_type.lower()
    if "radiation" in text or "pattern" in text:
        return "pattern"
    if "smith" in text:
        return "smith"
    if "vswr" in text:
        return "vswr"
    if "axial" in text:
        return "ar"
    if "efficiency" in text:
        return "eff"
    if "hpbw" in text:
        return "hpbw"
    if "gain" in text:
        return "gain"
    return "s11"


def _float_pair(min_value: str | None, max_value: str | None) -> list[float] | None:
    if min_value in (None, "") or max_value in (None, ""):
        return None
    return [float(min_value), float(max_value)]


def _base_args(payload: dict) -> Namespace:
    axis = payload.get("axisConfig") or {}
    labels = payload.get("labelConfig") or {}
    return Namespace(
        input=Path(payload["inputPath"]),
        output_dir=Path(payload.get("outputDir") or DEFAULT_OUTPUT),
        style=payload.get("style") or "ieee_tap",
        config=ROOT / "config.yaml",
        x_column=payload.get("xColumn") or None,
        y_column=payload.get("yColumn") or None,
        y_columns=payload.get("yColumns"),
        label=labels.get("first") or payload.get("label"),
        labels=None,
        xlabel=axis.get("xLabel") or None,
        ylabel=axis.get("yLabel") or None,
        x_unit=payload.get("xUnit") or "auto",
        xlim=_float_pair(axis.get("xMin"), axis.get("xMax")) if axis.get("rangeMode") == "manual" else None,
        ylim=_float_pair(axis.get("yMin"), axis.get("yMax")) if axis.get("rangeMode") == "manual" else None,
        width=payload.get("width") or None,
        formats=payload.get("formats") or ["png", "pdf", "svg", "json", "txt", "md"],
        dpi=int(payload.get("dpi") or 600),
        no_grid=False,
        no_markers=False,
        legend_loc=payload.get("legendLoc") or "best",
        sample_every=None,
        sample_step=None,
        marker_every=None,
        smooth=False,
        no_smooth=True,
        threshold=payload.get("threshold"),
        no_threshold=False,
        fl=payload.get("fl"),
        fc=payload.get("fc"),
        fh=payload.get("fh"),
        mark_min=False,
        mark_peak=False,
        band_label_loc="auto",
        no_band_label=False,
        ar_threshold=None,
        vswr_threshold=None,
        real_column=payload.get("realColumn"),
        imag_column=payload.get("imagColumn"),
        phi_column=payload.get("phiColumn"),
        theta_column=payload.get("thetaColumn"),
        gain_column=payload.get("gainColumn"),
        gain_columns=payload.get("gainColumns"),
        absolute=bool(payload.get("absolute", False)),
        cuts=payload.get("cuts"),
    )


def _load_style(args: Namespace) -> dict:
    from .style import load_style

    config = load_project_config(args.config)
    style = load_style(args.style or config.get("style", {}).get("preset", "ieee_tap"))
    image_formats, requested_formats = split_export_formats(args.formats)
    style["export"]["formats"] = image_formats
    style["export"]["requested_formats"] = requested_formats
    style["figure"]["dpi"] = args.dpi
    if args.width:
        style["figure"]["width"] = args.width
    if args.no_smooth:
        style["line"]["smooth"] = False
    if args.smooth:
        style["line"]["smooth"] = True
    return style


def create_preview(payload: dict) -> dict:
    from .plotting import (
        plot_ar,
        plot_efficiency,
        plot_gain,
        plot_hpbw,
        plot_pattern,
        plot_s11,
        plot_smith,
        plot_vswr,
        plot_xy,
    )

    mode = payload.get("mode") or "semiauto"
    if mode not in {"auto", "semiauto", "manual"}:
        raise ValueError(f"Unsupported mode: {mode}")
    args = _base_args(payload)
    dataset = read_hfss_csv(args.input)
    command = _plot_command(payload.get("plotType") or "")
    args.command = command
    config = load_project_config(args.config)
    project_settings = project_settings_from_config(config)
    apply_project_settings(args, project_settings)
    recognition = recognition_from_dataset(dataset, mode, payload.get("overrides") or {})
    if command == "s11" and mode != "manual":
        from .s11_import import s11_curves_from_dataset

        s11_result = s11_curves_from_dataset(dataset, x_unit=args.x_unit)
        recognition.detected_y_columns = [curve.y_column for curve in s11_result.curves]
        recognition.detected_curves = [
            {
                "x_column": curve.x_column,
                "y_column": curve.y_column,
                "x_unit": curve.x_unit,
                "y_unit": curve.y_unit,
                "y_quantity": curve.y_quantity,
                "label": curve.label,
                "is_normalized": curve.is_normalized,
                "conversion": curve.conversion,
                "warnings": curve.warnings,
            }
            for curve in [*s11_result.curves, *s11_result.phase_curves]
        ]
        recognition.requires_confirmation = recognition.requires_confirmation or s11_result.requires_confirmation
        recognition.confirmation_reasons.extend(s11_result.warnings)
        recognition.warnings.extend(s11_result.warnings)
    if mode == "manual" and (not args.x_column or not args.y_column):
        raise ValueError("Manual mode requires xColumn and yColumn.")
    if mode == "semiauto" and not payload.get("userConfirmed", False):
        raise ValueError("Semiauto mode requires user confirmation before generating the formal backend preview.")
    audit = audit_dataset(dataset, target_band_mhz(project_settings))
    style = _load_style(args)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if command == "s11":
        outputs = plot_s11(dataset, output_dir, style, args)
    elif command == "gain":
        outputs = plot_gain(dataset, output_dir, style, args)
    elif command == "pattern":
        outputs = plot_pattern(dataset, output_dir, style, args)
    elif command == "ar":
        outputs = plot_ar(dataset, output_dir, style, args)
    elif command == "vswr":
        outputs = plot_vswr(dataset, output_dir, style, args)
    elif command == "eff":
        outputs = plot_efficiency(dataset, output_dir, style, args)
    elif command == "hpbw":
        outputs = plot_hpbw(dataset, output_dir, style, args)
    elif command == "smith":
        outputs = plot_smith(dataset, output_dir, style, args)
    else:
        outputs = plot_xy(dataset, output_dir, style, args)

    project_text = project_metric_summary(dataset, command, project_settings)
    metric_curves = curves_from_dataset_for_metrics(dataset, command)
    metric_results = metric_results_for_dataset(dataset, command, project_settings)
    audit_text, messages = assemble_report(audit, project_text, metric_results)
    note_path = output_dir / f"{dataset.path.stem}_backend_preview_note.txt"
    note_path.write_text(audit_text + "\n", encoding="utf-8")
    outputs.append(note_path)
    outputs.extend(
        write_export_artifacts(
            output_dir,
            f"{dataset.path.stem}_{command}",
            dataset,
            command,
            args,
            style,
            style["export"].get("requested_formats", args.formats),
            project_settings,
            audit_text,
            recognition={
                "mode": recognition.mode,
                "detectedDelimiter": recognition.detected_delimiter,
                "detectedHeaderRows": recognition.detected_header_rows,
                "detectedXColumn": recognition.detected_x_column,
                "detectedYColumns": recognition.detected_y_columns,
                "detectedUnits": recognition.detected_units,
                "detectedPlotType": recognition.detected_plot_type,
                "detectedCurves": recognition.detected_curves,
                "requiresConfirmation": recognition.requires_confirmation,
                "confirmationReasons": recognition.confirmation_reasons,
                "warnings": recognition.warnings,
                "userOverrides": recognition.user_overrides,
            },
            curves=metric_curves,
            messages=messages,
        )
    )
    png = next((path for path in outputs if path.suffix.lower() == ".png"), outputs[0])
    return {
        "ok": True,
        "mode": mode,
        "command": command,
        "recognition": {
            "mode": recognition.mode,
            "detectedDelimiter": recognition.detected_delimiter,
            "detectedHeaderRows": recognition.detected_header_rows,
            "detectedXColumn": recognition.detected_x_column,
            "detectedYColumns": recognition.detected_y_columns,
            "detectedUnits": recognition.detected_units,
            "detectedPlotType": recognition.detected_plot_type,
            "detectedCurves": recognition.detected_curves,
            "requiresConfirmation": recognition.requires_confirmation,
            "confirmationReasons": recognition.confirmation_reasons,
            "warnings": recognition.warnings,
            "userOverrides": recognition.user_overrides,
        },
        "previewUrl": f"http://127.0.0.1:8765/file?path={png.as_posix()}&t={time.time()}",
        "outputs": [str(path) for path in outputs],
        "audit": audit_text,
        "warnings": audit.warnings,
        "notes": audit.notes,
        "messages": [message.__dict__ for message in messages],
        "hasErrors": any(message.severity == "error" for message in messages),
        "hasWarnings": any(message.severity == "warning" for message in messages),
    }


class PreviewHandler(BaseHTTPRequestHandler):
    def _headers(self, status: int = 200, content_type: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        origin = self.headers.get("Origin")
        self.send_header("Access-Control-Allow-Origin", origin if origin in ALLOWED_ORIGINS else "http://127.0.0.1:4173")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self) -> None:
        self._headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/health", "/api/health"}:
            self._headers()
            self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
            return
        if parsed.path != "/file":
            self._headers(404)
            self.wfile.write(json.dumps({"ok": False, "error": "Not found"}).encode("utf-8"))
            return
        path_text = (parse_qs(parsed.query).get("path") or [""])[0]
        path = Path(path_text)
        if not _is_allowed_file(path):
            self._headers(403)
            self.wfile.write(json.dumps({"ok": False, "error": "File access outside project outputs is blocked"}).encode("utf-8"))
            return
        if not path.exists() or not path.is_file():
            self._headers(404)
            self.wfile.write(json.dumps({"ok": False, "error": "File not found"}).encode("utf-8"))
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self._headers(200, content_type)
        self.wfile.write(path.read_bytes())

    def do_POST(self) -> None:
        parsed_path = urlparse(self.path).path
        if parsed_path not in {"/api/preview", "/api"} and not parsed_path.startswith("/api/"):
            self._headers(404)
            self.wfile.write(json.dumps({"ok": False, "error": "Not found"}).encode("utf-8"))
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if parsed_path == "/api/preview":
                result = create_preview(payload)
            else:
                from .backend_api import dispatch

                action = payload.get("action") if parsed_path == "/api" else parsed_path.rsplit("/", 1)[-1]
                result = dispatch(str(action), payload.get("payload", payload))
            self._headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - surface local plotting errors to the UI.
            self._headers(500)
            self.wfile.write(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"))

    def log_message(self, format: str, *args: object) -> None:
        print(f"[preview] {self.address_string()} - {format % args}")


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8765), PreviewHandler)
    print("HFSS Paper Plotter preview server: http://127.0.0.1:8765")
    server.serve_forever()


if __name__ == "__main__":
    main()
