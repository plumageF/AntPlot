import { useRef, useState } from "react";
import { axisDefaults } from "../plotRules";
import type {
  ApiMessage,
  AxisConfig,
  CurveSummary,
  DatasetSummary,
  ExportConfig,
  FileIndexEntry,
  MappingCandidate,
  ManualConfig,
  OperationMode,
  PatternConfig,
  PreviewResult,
  ProjectSettings,
  RecognitionSummary,
  Theme,
  WorkflowState
} from "../types";

/**
 * Owns the page-level state only. Network actions remain in App for now so
 * the existing API payloads and error handling stay unchanged during the
 * component extraction.
 */
export function usePlotWorkspaceState() {
  const [theme, setTheme] = useState<Theme>("dark");
  const [selectedPlot, setSelectedPlot] = useState("S11 / Return Loss");
  const [suggestedPlot, setSuggestedPlot] = useState<string | null>(null);
  const [operationMode, setOperationMode] = useState<OperationMode>("semiauto");
  const [singleFilePath, setSingleFilePath] = useState("examples\\s11_cases\\case03_wide_multi_curve.csv");
  const [multiFilePaths, setMultiFilePaths] = useState("");
  const [directoryPath, setDirectoryPath] = useState("examples\\s11_cases");
  const [recursiveScan, setRecursiveScan] = useState(false);
  const [fileIndex, setFileIndex] = useState<FileIndexEntry[]>([]);
  const [unsupportedFiles, setUnsupportedFiles] = useState<FileIndexEntry[]>([]);
  const [selectedIndexPaths, setSelectedIndexPaths] = useState<Record<string, boolean>>({});
  const [extensionFilter, setExtensionFilter] = useState("all");
  const [dataTypeFilter, setDataTypeFilter] = useState("all");
  const [showUnsupported, setShowUnsupported] = useState(false);
  const [exportConfig, setExportConfig] = useState<ExportConfig>({
    outputDir: "outputs\\frontend_export", filePrefix: "paper_plot", png: true,
    pdf: true, svg: true, json: true, txt: false, md: false, dpi: "600", scope: "current"
  });
  const [axisConfig, setAxisConfig] = useState<AxisConfig>(() => axisDefaults("S11 / Return Loss"));
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [recognitions, setRecognitions] = useState<RecognitionSummary[]>([]);
  const [mappingCandidates, setMappingCandidates] = useState<MappingCandidate[]>([]);
  const [manualConfig, setManualConfig] = useState<ManualConfig>({
    headerRow: "auto", delimiter: "auto", xColumn: "", yColumn: "", xQuantity: "frequency",
    yQuantity: "S11", xUnit: "GHz", yUnit: "dB", familyColumn: "", label: "", plotType: "s11",
    drawThreshold: true, threshold: "", targetBandMin: "", targetBandMax: ""
  });
  const [patternConfig, setPatternConfig] = useState<PatternConfig>({
    displayMode: "cartesian", polarStyle: "paper", angleLabelMode: "0_360", rMin: "-30", rMax: "0",
    normalize: false, thetaZeroLocation: "N", thetaDirection: "-1", clipBelowRMin: true, legendLoc: "best"
  });
  const [projectSettings, setProjectSettings] = useState<ProjectSettings>({
    bandStartMHz: "", bandEndMHz: "", s11ThresholdDb: "-10", vswrThreshold: "2", axialRatioThresholdDb: "3",
    minGainDbi: "0", portImpedanceOhm: "50", preferRealizedGain: true, patternFrequenciesMHz: "410, 450, 490"
  });
  const [configPath, setConfigPath] = useState("outputs\\frontend_export\\paper_plot_plot_config.json");
  const [curves, setCurves] = useState<CurveSummary[]>([]);
  const [messages, setMessages] = useState<ApiMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [workflowState, setWorkflowState] = useState<WorkflowState>("idle");
  const [previewResult, setPreviewResult] = useState<PreviewResult>({ imageUrl: null, status: "Waiting for data import / 等待导入文件", error: null, report: null, outputs: [] });
  const previewTimerRef = useRef<number | null>(null);
  const previewRequestRef = useRef(0);

  return {
    theme, setTheme, selectedPlot, setSelectedPlot, suggestedPlot, setSuggestedPlot,
    operationMode, setOperationMode, singleFilePath, setSingleFilePath, multiFilePaths, setMultiFilePaths,
    directoryPath, setDirectoryPath, recursiveScan, setRecursiveScan, fileIndex, setFileIndex,
    unsupportedFiles, setUnsupportedFiles, selectedIndexPaths, setSelectedIndexPaths, extensionFilter,
    setExtensionFilter, dataTypeFilter, setDataTypeFilter, showUnsupported, setShowUnsupported,
    exportConfig, setExportConfig, axisConfig, setAxisConfig, datasets, setDatasets, recognitions,
    setRecognitions, mappingCandidates, setMappingCandidates, manualConfig, setManualConfig,
    patternConfig, setPatternConfig, projectSettings, setProjectSettings, configPath, setConfigPath,
    curves, setCurves, messages, setMessages, busy, setBusy, workflowState, setWorkflowState,
    previewResult, setPreviewResult, previewTimerRef, previewRequestRef
  };
}
