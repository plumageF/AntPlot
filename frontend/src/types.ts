export type Theme = "light" | "dark";
export type RangeMode = "auto" | "manual";
export type AxisLabelMode = "auto" | "manual";
export type OperationMode = "auto" | "semiauto" | "manual";
export type CurveSource = "Simulated" | "Measured" | "Reference" | "Manual" | "Unknown";
export type WorkflowState = "idle" | "file_loaded" | "dataset_detected" | "mapping_required" | "curves_created" | "plot_ready" | "preview_generated" | "export_ready" | "error";

export type MessageSeverity = "error" | "warning" | "info";
export type ApiMessage = { code: string; message: string; severity?: MessageSeverity; context?: Record<string, unknown> };

export type FileIndexEntry = {
  path: string;
  name: string;
  extension: string;
  size: number | null;
  modified_time: string | null;
  supported: boolean;
  guessed_data_type: string;
  guessed_source_type: string;
  warnings: string[];
};

export type ScanDirectoryData = {
  directory_path: string;
  files: FileIndexEntry[];
  unsupported_files: FileIndexEntry[];
};

export type DatasetSummary = {
  dataset_id: string;
  source_file: string;
  source_type: string;
  data_type: string;
  columns: string[];
  units: Record<string, string | null>;
  row_count: number;
  sample_count?: number;
  warnings: string[];
  metadata: Record<string, any>;
  report_domain?: string;
  family_info?: Record<string, any>;
  compatible_plot_types?: string[];
  default_selected?: boolean;
  line_width?: number | string;
  line_style?: string;
  color?: string | null;
  marker_enabled?: boolean;
  marker?: string;
  participate_metrics?: boolean;
};

export type ReportModel = {
  report_domain?: string;
  report_type?: string;
  primary_sweep?: string;
  quantity?: string;
  families?: Array<{ name: string; role: string; column?: string | null; value?: any; unit?: string | null; source?: string | null }>;
  compatible_plot_types?: string[];
  warnings?: string[];
  errors?: string[];
  infos?: string[];
  requires_confirmation?: boolean;
  data_class?: string;
  columns?: Record<string, any>;
};

export type ReportPlan = {
  result_domain?: string;
  primary_sweep?: { column: string; quantity: string; unit?: string | null; role: string; minimum?: number | null; maximum?: number | null; unique_count?: number; values?: number[] } | null;
  fixed_variables?: Array<{ column: string; quantity: string; unit?: string | null; values?: number[]; minimum?: number | null; maximum?: number | null }>;
  family_variables?: Array<{ column: string; quantity: string; unit?: string | null; values?: number[]; unique_count?: number }>;
  quantity_columns?: Array<{ column: string; quantity: string; unit?: string | null; conversion?: string | null }>;
  compatible_plot_types?: string[];
  recommended_plot_type?: string;
  recommended_display_mode?: string | null;
  curve_family_strategy?: string;
  confirmation_reasons?: string[];
  warnings?: string[];
  errors?: string[];
  report_model?: ReportModel | null;
};

export type RecognitionSummary = {
  dataset_id: string;
  detected_plot_type: string;
  detected_x_column: string | null;
  detected_y_columns: string[];
  detected_units: Record<string, string | null>;
  requires_confirmation: boolean;
  confirmation_reasons: string[];
  warnings: string[];
  report_plan?: ReportPlan;
  report_model?: ReportModel;
};

export type CurveSummary = {
  curve_id: string;
  dataset_id: string;
  x_column: string;
  y_column: string;
  x_quantity: string;
  y_quantity: string;
  x_unit: string;
  y_unit: string;
  label: string;
  is_enabled: boolean;
  is_normalized: boolean;
  conversion: string | null;
  source_role: CurveSource;
  source_type?: string;
  order: number;
  point_count: number;
  sample_count?: number;
  raw_sample_count?: number;
  unique_x_count?: number;
  displayed_sample_count?: number;
  duplicate_x_count_after_grouping?: number;
  sample_display_policy?: string;
  warnings: string[];
  metadata: Record<string, any>;
  source_file?: string;
  report_domain?: string;
  family_info?: Record<string, any>;
  compatible_plot_types?: string[];
  default_selected?: boolean;
  line_width?: number | string;
  line_style?: string;
  color?: string;
  marker_enabled?: boolean;
  marker?: string;
  marker_size?: number | string;
  marker_every?: number | string;
  alpha?: number | string;
  participate_metrics?: boolean;
};

export type MappingCandidate = CurveSummary & {
  selected: boolean;
  original_x_column: string;
  original_y_column: string;
  original_x_unit: string;
  original_y_unit: string;
  original_y_quantity: string;
};

export type AxisConfig = {
  xLabel: string;
  yLabel: string;
  labelMode: AxisLabelMode;
  rangeMode: RangeMode;
  xMin: string;
  xMax: string;
  yMin: string;
  yMax: string;
  xTickMajor: string;
  yTickMajor: string;
  xTickMinor: string;
  yTickMinor: string;
  gridEnabled: boolean;
  noteText: string;
  noteX: string;
  noteY: string;
};

export type ManualConfig = {
  headerRow: string;
  delimiter: string;
  xColumn: string;
  yColumn: string;
  xQuantity: string;
  yQuantity: string;
  xUnit: string;
  yUnit: string;
  familyColumn: string;
  label: string;
  plotType: string;
  drawThreshold: boolean;
  threshold: string;
  targetBandMin: string;
  targetBandMax: string;
};

export type ProjectSettings = {
  bandStartMHz: string;
  bandEndMHz: string;
  s11ThresholdDb: string;
  vswrThreshold: string;
  axialRatioThresholdDb: string;
  minGainDbi: string;
  portImpedanceOhm: string;
  preferRealizedGain: boolean;
  patternFrequenciesMHz: string;
};

export type PreviewResult = {
  imageUrl: string | null;
  status: string;
  error: string | null;
  report: string | null;
  outputs: string[];
};

export type ExportConfig = {
  outputDir: string;
  filePrefix: string;
  png: boolean;
  pdf: boolean;
  svg: boolean;
  json: boolean;
  txt: boolean;
  md: boolean;
  dpi: string;
  scope: "current" | "all";
};

export type PatternConfig = {
  displayMode: "cartesian" | "polar";
  polarStyle: "paper" | "hfss_like";
  angleLabelMode: "0_360" | "minus180_180";
  rMin: string;
  rMax: string;
  normalize: boolean;
  thetaZeroLocation: string;
  thetaDirection: string;
  clipBelowRMin: boolean;
  legendLoc: string;
};
