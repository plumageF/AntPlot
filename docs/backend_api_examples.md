# Backend Core API Examples

All frontend operations should call these stable backend APIs instead of calling CSV readers,
curve detectors, plotting functions, or export helpers directly.

Every response has this shape:

```json
{
  "ok": true,
  "data": {},
  "errors": [],
  "warnings": [],
  "infos": []
}
```

Each message item has this shape:

```json
{
  "code": "message_code",
  "message": "Human readable message.",
  "context": {}
}
```

## 1. import_files(files)

Input:

```json
{
  "files": ["examples/s11_cases/case01_hfss_standard.csv"],
  "mode": "semiauto"
}
```

Output excerpt:

```json
{
  "ok": true,
  "data": {
    "datasets": [
      {
        "dataset_id": "f1b2c3d4e5f6",
        "source_file": "examples/s11_cases/case01_hfss_standard.csv",
        "source_type": "HFSS",
        "file_format": "CSV",
        "data_type": "frequency_response",
        "columns": ["Freq [GHz]", "dB(S(1,1)) []"],
        "units": {"Freq [GHz]": "GHz", "dB(S(1,1)) []": "dB"},
        "row_count": 3
      }
    ],
    "recognitions": [
      {
        "dataset_id": "f1b2c3d4e5f6",
        "detected_x_column": "Freq [GHz]",
        "detected_y_columns": ["dB(S(1,1)) []"],
        "detected_plot_type": "s11",
        "requires_confirmation": true
      }
    ]
  }
}
```

## 2. get_available_curves(dataset_id)

Input:

```json
{
  "dataset_id": "f1b2c3d4e5f6",
  "plot_type": "s11",
  "x_unit": "MHz"
}
```

Output excerpt:

```json
{
  "ok": true,
  "data": {
    "dataset_id": "f1b2c3d4e5f6",
    "plot_type": "s11",
    "curves": [
      {
        "curve_id": "curve_123456789abc",
        "x_column": "Freq [GHz]",
        "y_column": "dB(S(1,1)) []",
        "x_unit": "MHz",
        "y_unit": "dB",
        "label": "S(1,1)",
        "point_count": 3,
        "x_range": {"min": 1600.0, "max": 1800.0}
      }
    ]
  }
}
```

## 3. create_curves(mapping_config)

Create from confirmed candidates:

```json
{
  "dataset_id": "f1b2c3d4e5f6",
  "candidate_ids": ["curve_123456789abc"]
}
```

Manual mapping:

```json
{
  "dataset_id": "f1b2c3d4e5f6",
  "mappings": [
    {
      "x_column": "Freq [GHz]",
      "y_column": "dB(S(1,1)) []",
      "x_unit": "MHz",
      "y_unit": "dB",
      "label": "Simulated S11",
      "source_role": "Simulated",
      "is_normalized": false
    }
  ]
}
```

Output excerpt:

```json
{
  "ok": true,
  "data": {
    "curves": [
      {
        "curve_id": "curve_aabbccddeeff",
        "label": "Simulated S11",
        "is_enabled": true,
        "source_role": "Simulated"
      }
    ]
  }
}
```

## 4. update_curve(curve_id, update_config)

Input:

```json
{
  "curve_id": "curve_aabbccddeeff",
  "update_config": {
    "label": "Measured S11",
    "is_enabled": true,
    "x_unit": "MHz",
    "is_normalized": false,
    "source_role": "Measured",
    "order": 1
  }
}
```

## 5. validate_plot(plot_type, curves, project_settings)

Input:

```json
{
  "plot_type": "s11",
  "curves": ["curve_aabbccddeeff"],
  "project_settings": {
    "working_band_mhz": [410, 490],
    "s11_threshold_db": -10,
    "port_impedance_ohm": 50
  }
}
```

Output excerpt:

```json
{
  "ok": true,
  "data": {
    "allowed": true,
    "plot_type": "s11",
    "curve_ids": ["curve_aabbccddeeff"]
  },
  "infos": [
    {
      "code": "interpolation_info",
      "message": "Different frequency grids are allowed; each curve is plotted on its own X samples.",
      "context": {}
    }
  ]
}
```

## 6. generate_preview(plot_config)

Input:

```json
{
  "plot_type": "s11",
  "curve_ids": ["curve_aabbccddeeff"],
  "project_settings": {
    "working_band_mhz": [410, 490],
    "s11_threshold_db": -10
  },
  "formats": ["png"],
  "output_name": "preview_s11"
}
```

Output excerpt:

```json
{
  "ok": true,
  "data": {
    "preview_path": "outputs/api_preview/preview_s11.png",
    "outputs": ["outputs/api_preview/preview_s11.png", "outputs/api_preview/preview_s11_overlay_report.txt"],
    "metrics_report": "Engineering metrics:\n..."
  }
}
```

## 7. export_plot(export_config)

Input:

```json
{
  "plot_type": "s11",
  "curve_ids": ["curve_aabbccddeeff"],
  "formats": ["png", "pdf", "svg", "json", "txt", "md"],
  "output_dir": "outputs/final",
  "output_name": "paper_s11",
  "project_settings": {
    "working_band_mhz": [410, 490],
    "s11_threshold_db": -10
  }
}
```

Output excerpt:

```json
{
  "ok": true,
  "data": {
    "outputs": [
      "outputs/final/paper_s11.png",
      "outputs/final/paper_s11.pdf",
      "outputs/final/paper_s11.svg",
      "outputs/final/paper_s11_plot_config.json",
      "outputs/final/paper_s11_overlay_report.txt"
    ]
  }
}
```

## HTTP Usage

The preview server accepts either:

```http
POST /api
```

with body:

```json
{
  "action": "import_files",
  "payload": {
    "files": ["examples/s11_cases/case01_hfss_standard.csv"]
  }
}
```

or:

```http
POST /api/import_files
```

with the payload body directly.
