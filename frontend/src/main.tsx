import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  BarChart3,
  CheckCircle2,
  CircleDot,
  Eye,
  EyeOff,
  FileInput,
  FolderOpen,
  Gauge,
  GitBranch,
  Grid3X3,
  Moon,
  Radar,
  Route,
  Settings2,
  SlidersHorizontal,
  Sun,
  Trash2,
  Upload,
  Waves
} from "lucide-react";
import { callApi, fileUrl, type ApiResponse } from "./apiClient";
import { axisDefaults, curveCompatibleWithPlot, formatFamilyInfo, isFreeXYPlot, plotApiType, plotNameFromApiType, scrollToErrorTarget, workflowModeForPlot } from "./plotRules";
import { usePlotWorkspaceState } from "./hooks/usePlotWorkspaceState";
import { ImportPanel } from "./components/ImportPanel";
import { MappingPanel } from "./components/MappingPanel";
import { CurveManagerPanel as CurveManagerStepPanel } from "./components/CurveManagerPanel";
import { PlotSettingsPanel } from "./components/PlotSettingsPanel";
import { PreviewExportPanel } from "./components/PreviewExportPanel";
import { SidebarCleanExternal, WorkflowHeaderCleanExternal } from "./components/AppChromeClean";
import { DatasetRecognitionPanelCleanExternal } from "./components/DatasetRecognitionPanelClean";
import { ImportWorkflowPanelCleanExternal } from "./components/ImportWorkflowPanelClean";
import { FileIndexPanelCleanExternal } from "./components/FileIndexPanelClean";
import { WorkflowGateCleanExternal } from "./components/WorkflowGateClean";
import { BackendCanvasPreviewCleanExternal } from "./components/BackendCanvasPreviewClean";
import { MappingReviewPanelCleanExternal } from "./components/MappingReviewPanelClean";
import { CurveManagerPanelCleanExternal } from "./components/CurveManagerPanelClean";
import { ProjectSettingsPanelCleanExternal } from "./components/ProjectSettingsPanelClean";
import { ExportPanelCleanExternal } from "./components/ExportPanelClean";
import { SettingsPanelCleanExternal } from "./components/SettingsPanelClean";
import { StepCardCleanExternal } from "./components/StepCardClean";
import { ManualModePanelCleanExternal } from "./components/ManualModePanelClean";
import type { ApiMessage, AxisConfig, AxisLabelMode, CurveSource, CurveSummary, DatasetSummary, ExportConfig, FileIndexEntry, MappingCandidate, ManualConfig, OperationMode, PatternConfig, PreviewResult, ProjectSettings, RangeMode, RecognitionSummary, ReportModel, ReportPlan, ScanDirectoryData, Theme, WorkflowState } from "./types";
import "./styles.css";

const quantities = ["S11", "VSWR", "Gain", "RealizedGain", "AR", "Efficiency", "Phase"];
const xQuantities = ["frequency", "theta", "phi", "angle"];
const units = ["auto", "Hz", "MHz", "GHz", "deg", "dB", "dBi", "linear", "degree"];

const plots = [
  { name: "S11 / Return Loss", apiType: "s11", icon: Activity },
  { name: "Realized Gain", apiType: "gain", icon: BarChart3 },
  { name: "Radiation Pattern", apiType: "pattern", icon: Route },
  { name: "Axial Ratio", apiType: "ar", icon: CircleDot },
  { name: "VSWR", apiType: "vswr", icon: Waves },
  { name: "Efficiency", apiType: "efficiency", icon: Gauge },
  { name: "HPBW", apiType: "hpbw", icon: Radar },
  { name: "Smith Chart", apiType: "smith", icon: GitBranch },
  { name: "XY Multi-Curve", apiType: "xy", icon: SlidersHorizontal }
];

function formatDataRanges(ranges?: Record<string, unknown> | null) {
  if (!ranges || typeof ranges !== "object") return "unconfirmed";
  const parts = Object.entries(ranges).flatMap(([key, value]) => {
    if (!value || typeof value !== "object") return [];
    const range = value as { min?: number | string | null; max?: number | string | null };
    if (range.min == null && range.max == null) return [];
    return [`${key}: ${range.min ?? "?"}-${range.max ?? "?"}`];
  });
  return parts.slice(0, 1).join("; ") || "unconfirmed";
}

function directoryOf(path: string) {
  const index = Math.max(path.lastIndexOf("\\"), path.lastIndexOf("/"));
  return index > 0 ? path.slice(0, index) : "outputs/frontend_export";
}

function formatDataRangesClean(ranges?: Record<string, unknown> | null) {
  if (!ranges || typeof ranges !== "object") return "unconfirmed";
  const parts = Object.entries(ranges).flatMap(([key, value]) => {
    if (!value || typeof value !== "object") return [];
    const range = value as { min?: number | string | null; max?: number | string | null };
    if (range.min == null && range.max == null) return [];
    return [`${key}: ${range.min ?? "?"}-${range.max ?? "?"}`];
  });
  return parts.slice(0, 1).join("; ") || "unconfirmed";
}

function candidateFromCurve(curve: CurveSummary): MappingCandidate {
  const shouldNormalizeByDefault = ["Gain", "RealizedGain"].includes(curve.y_quantity) && ["theta", "phi", "angle"].includes(curve.x_quantity);
  return {
    ...curve,
    selected: curve.default_selected ?? true,
    is_normalized: curve.is_normalized && shouldNormalizeByDefault,
    original_x_column: curve.x_column,
    original_y_column: curve.y_column,
    original_x_unit: curve.x_unit,
    original_y_unit: curve.y_unit,
    original_y_quantity: curve.y_quantity
  };
}

function App() {
  const workspace = usePlotWorkspaceState();
  const {
    theme, setTheme, selectedPlot, setSelectedPlot, suggestedPlot, setSuggestedPlot,
    operationMode, setOperationMode, singleFilePath, setSingleFilePath, multiFilePaths, setMultiFilePaths,
    directoryPath, setDirectoryPath, recursiveScan, setRecursiveScan, fileIndex, setFileIndex,
    unsupportedFiles, setUnsupportedFiles, selectedIndexPaths, setSelectedIndexPaths, extensionFilter,
    setExtensionFilter, dataTypeFilter, setDataTypeFilter, showUnsupported, setShowUnsupported
  } = workspace;
  const {
    exportConfig, setExportConfig, axisConfig, setAxisConfig, datasets, setDatasets, recognitions,
    setRecognitions, mappingCandidates, setMappingCandidates
  } = workspace;
  const { manualConfig, setManualConfig, patternConfig, setPatternConfig } = workspace;
  const {
    projectSettings, setProjectSettings, configPath, setConfigPath, curves, setCurves,
    messages, setMessages, busy, setBusy, workflowState, setWorkflowState
  } = workspace;
  const [previewResult, setPreviewResult] = useState<PreviewResult>({ imageUrl: null, status: "Waiting for data import / 等待导入文件", error: null, report: null, outputs: [] });
  const previewTimerRef = useRef<number | null>(null);
  const previewRequestRef = useRef(0);
  const confirmInFlightRef = useRef(false);

  const activeIdsFor = (sourceCurves = curves, plot = selectedPlot) =>
    sourceCurves.filter((curve) => curve.is_enabled && curveCompatibleWithPlot(plot, curve).ok).sort((a, b) => a.order - b.order).map((curve) => curve.curve_id);
  const activeCurveIds = useMemo(() => activeIdsFor(curves, selectedPlot), [curves, selectedPlot]);
  const hasErrors = messages.some((message) => message.code.toLowerCase().includes("error")) || Boolean(previewResult.error);
  const canConfirmMapping = mappingCandidates.some((candidate) => candidate.selected) && !busy;
  const canGeneratePreview = activeCurveIds.length > 0 && !busy;
  const canExportFormal = curves.length > 0 && activeCurveIds.length > 0 && mappingCandidates.length === 0 && !busy;
  const setAllMessages = (...responses: ApiResponse<any>[]) => setMessages(responses.flatMap((response) => [...response.errors, ...response.warnings, ...response.infos]));
  const selectedFormats = () => {
    const formats: string[] = [];
    if (exportConfig.png) formats.push("png");
    if (exportConfig.pdf) formats.push("pdf");
    if (exportConfig.svg) formats.push("svg");
    if (exportConfig.json) formats.push("json");
    if (exportConfig.txt) formats.push("txt");
    if (exportConfig.md) formats.push("md");
    return formats.length ? formats : ["png"];
  };
  const plotTypeForRequest = () => isFreeXYPlot(selectedPlot) ? plotApiType(selectedPlot) : operationMode === "manual" ? manualConfig.plotType : plotApiType(selectedPlot);
  const optionalNumber = (value: string) => {
    const text = String(value ?? "").trim();
    if (!text) return null;
    const number = Number(text);
    return Number.isFinite(number) ? number : null;
  };
  const thresholdForCurrentPlot = () => {
    if (operationMode === "manual" && manualConfig.threshold.trim()) return optionalNumber(manualConfig.threshold);
    if (operationMode === "manual") {
      const manualType = String(manualConfig.plotType || plotApiType(selectedPlot)).toLowerCase();
      if (manualType.includes("vswr")) return optionalNumber(projectSettings.vswrThreshold);
      if (manualType.includes("ar") || manualType.includes("axial")) return optionalNumber(projectSettings.axialRatioThresholdDb);
      if (manualType.includes("s11") || manualType.includes("return")) return optionalNumber(projectSettings.s11ThresholdDb);
      return null;
    }
    if (selectedPlot === "VSWR") return optionalNumber(projectSettings.vswrThreshold);
    if (selectedPlot === "Axial Ratio") return optionalNumber(projectSettings.axialRatioThresholdDb);
    if (selectedPlot === "S11 / Return Loss") return optionalNumber(projectSettings.s11ThresholdDb);
    return null;
  };
  const shouldDrawThreshold = () => {
    if (operationMode === "manual") return manualConfig.drawThreshold && thresholdForCurrentPlot() !== null;
    return ["S11 / Return Loss", "VSWR", "Axial Ratio"].includes(selectedPlot) && thresholdForCurrentPlot() !== null;
  };
  const axisConfigForRequest = () => ({
    ...(axisConfig.labelMode === "manual" ? { xlabel: axisConfig.xLabel, ylabel: axisConfig.yLabel } : {}),
    ...(axisConfig.rangeMode === "manual" ? { xlim: [Number(axisConfig.xMin), Number(axisConfig.xMax)], ylim: [Number(axisConfig.yMin), Number(axisConfig.yMax)] } : {}),
    ...(axisConfig.xTickMajor.trim() ? { xtick_major: Number(axisConfig.xTickMajor) } : {}),
    ...(axisConfig.yTickMajor.trim() ? { ytick_major: Number(axisConfig.yTickMajor) } : {}),
    ...(axisConfig.xTickMinor.trim() ? { xtick_minor: Number(axisConfig.xTickMinor) } : {}),
    ...(axisConfig.yTickMinor.trim() ? { ytick_minor: Number(axisConfig.yTickMinor) } : {}),
    grid_enabled: axisConfig.gridEnabled,
    annotations: axisConfig.noteText.trim() ? [{
      text: axisConfig.noteText,
      x: Number(axisConfig.noteX || 0.05),
      y: Number(axisConfig.noteY || 0.95)
    }] : []
  });
  const patternConfigForRequest = () => ({
    pattern_display_mode: selectedPlot === "Radiation Pattern" ? patternConfig.displayMode : undefined,
    display_mode: selectedPlot === "Radiation Pattern" ? patternConfig.displayMode : undefined,
    polar_config: selectedPlot === "Radiation Pattern" ? {
      display_mode: patternConfig.displayMode,
      r_min: Number(patternConfig.rMin || -30),
      r_max: Number(patternConfig.rMax || 0),
      normalize: patternConfig.normalize,
      clip_below_r_min: patternConfig.clipBelowRMin,
      theta_zero_location: patternConfig.thetaZeroLocation,
      theta_direction: Number(patternConfig.thetaDirection || -1),
      polar_style: patternConfig.polarStyle,
      angle_label_mode: patternConfig.angleLabelMode,
      legend_loc: patternConfig.legendLoc
    } : undefined,
    r_min: selectedPlot === "Radiation Pattern" ? Number(patternConfig.rMin || -30) : undefined,
    r_max: selectedPlot === "Radiation Pattern" ? Number(patternConfig.rMax || 0) : undefined,
    pattern_normalize: selectedPlot === "Radiation Pattern" ? patternConfig.normalize : undefined,
    theta_zero_location: selectedPlot === "Radiation Pattern" ? patternConfig.thetaZeroLocation : undefined,
    theta_direction: selectedPlot === "Radiation Pattern" ? Number(patternConfig.thetaDirection || -1) : undefined,
    polar_style: selectedPlot === "Radiation Pattern" ? patternConfig.polarStyle : undefined,
    angle_label_mode: selectedPlot === "Radiation Pattern" ? patternConfig.angleLabelMode : undefined,
    legend_loc: selectedPlot === "Radiation Pattern" ? patternConfig.legendLoc : undefined
  });
  const projectSettingsForRequest = () => {
    const bandStart = projectSettings.bandStartMHz.trim() || manualConfig.targetBandMin.trim();
    const bandEnd = projectSettings.bandEndMHz.trim() || manualConfig.targetBandMax.trim();
    const hasBand = bandStart !== "" && bandEnd !== "";
    return {
      target_band_mhz: hasBand ? [Number(bandStart), Number(bandEnd)] : null,
      working_band_mhz: hasBand ? [Number(bandStart), Number(bandEnd)] : null,
      s11_threshold_db: optionalNumber(projectSettings.s11ThresholdDb),
      vswr_threshold: optionalNumber(projectSettings.vswrThreshold),
      axial_ratio_threshold_db: optionalNumber(projectSettings.axialRatioThresholdDb),
      min_gain_dbi: optionalNumber(projectSettings.minGainDbi),
      port_impedance_ohm: optionalNumber(projectSettings.portImpedanceOhm),
      prefer_realized_gain: projectSettings.preferRealizedGain,
      pattern_frequencies_mhz: projectSettings.patternFrequenciesMHz.split(",").map((item) => Number(item.trim())).filter((item) => Number.isFinite(item))
    };
  };

  const splitPathList = (value: string) => value.split(/[\n;,]+/).map((item) => item.trim()).filter(Boolean);
  const manualParseOptions = () => ({
    header_row: manualConfig.headerRow,
    delimiter: manualConfig.delimiter
  });

  const loadCandidatesForDatasets = async (targetPlot: string, sourceDatasets = datasets) => {
    const candidates: MappingCandidate[] = [];
    const responseLog: ApiResponse<any>[] = [];
    const targetPlotType = plotApiType(targetPlot);
    for (const dataset of sourceDatasets) {
      const available = await callApi<{ curves: CurveSummary[] }>("get_available_curves", {
        dataset_id: dataset.dataset_id,
        plot_type: targetPlotType,
        x_unit: "auto"
      });
      responseLog.push(available);
      candidates.push(...available.data.curves.map(candidateFromCurve));
    }
    return { candidates, responseLog };
  };

  const createCurvesFromCandidates = async (selectedCandidates: MappingCandidate[], sourceDatasets = datasets, mode = operationMode) => {
    const created: CurveSummary[] = [];
    const responseLog: ApiResponse<any>[] = [];
    for (const dataset of sourceDatasets) {
      const group = selectedCandidates.filter((candidate) => candidate.dataset_id === dataset.dataset_id);
      if (group.length === 0) continue;
      const candidateUpdates = group
        .filter((candidate) => candidate.x_column === candidate.original_x_column && candidate.y_column === candidate.original_y_column)
        .map((candidate) => ({
          candidate_id: candidate.curve_id,
          label: candidate.label,
          source_role: candidate.source_role,
          x_unit: candidate.x_unit,
          is_normalized: candidate.is_normalized,
          is_enabled: candidate.is_enabled
        }));
      const mappings = group
        .filter((candidate) => candidate.x_column !== candidate.original_x_column || candidate.y_column !== candidate.original_y_column)
        .map((candidate) => ({
          x_column: candidate.x_column,
          y_column: candidate.y_column,
          x_unit: candidate.x_unit,
          x_quantity: candidate.x_quantity,
          y_unit: candidate.y_unit,
          y_quantity: candidate.y_quantity,
          label: candidate.label,
          source_role: candidate.source_role,
          is_normalized: candidate.is_normalized,
          conversion: candidate.conversion,
          family_column: candidate.metadata?.manual_config?.familyColumn || undefined,
          manual_confirmed: mode === "manual",
          manual_config: mode === "manual" ? manualConfig : {}
        }));
      const result = await callApi<{ curves: CurveSummary[] }>("create_curves", {
        dataset_id: dataset.dataset_id,
        candidate_updates: candidateUpdates,
        mappings
      });
      responseLog.push(result);
      created.push(...result.data.curves);
    }
    return { created, responseLog };
  };

  const importFiles = async (filesOverride?: string[]) => {
    setBusy(true);
    setWorkflowState("file_loaded");
    const importMode = workflowModeForPlot(selectedPlot, operationMode);
    setPreviewResult({ imageUrl: null, status: "Importing files and detecting mapping candidates / 正在导入文件并识别映射候选...", error: null, report: null, outputs: [] });
    try {
      const files = filesOverride?.length ? filesOverride : splitPathList(singleFilePath);
      if (files.length === 0) throw new Error("No input files selected.");
      const imported = await callApi<{ datasets: DatasetSummary[]; recognitions: RecognitionSummary[] }>("import_files", {
        files,
        mode: importMode,
        parse_options: importMode === "manual" ? manualParseOptions() : undefined
      });
      const detectedPlotType = imported.data.recognitions.find((recognition) => recognition.detected_plot_type && recognition.detected_plot_type !== "unknown")?.detected_plot_type;
      const suggestedPlotName = isFreeXYPlot(selectedPlot) ? null : detectedPlotType ? plotNameFromApiType(detectedPlotType) : null;
      setSuggestedPlot(suggestedPlotName);
      const effectivePlotName = importMode === "auto" && suggestedPlotName ? suggestedPlotName : selectedPlot;
      const candidatePlotName = effectivePlotName;
      if (importMode === "auto" && detectedPlotType && effectivePlotName !== selectedPlot) {
        setSelectedPlot(effectivePlotName);
        setAxisConfig(axisDefaults(effectivePlotName));
      }
      const recommendedDisplay = imported.data.recognitions.find((recognition) => recognition.report_plan?.recommended_display_mode)?.report_plan?.recommended_display_mode;
      if (candidatePlotName === "Radiation Pattern" && recommendedDisplay === "polar") {
        setPatternConfig((current) => ({ ...current, displayMode: "polar" }));
      }
      const responseLog: ApiResponse<any>[] = [imported];
      let candidates: MappingCandidate[] = [];
      if (importMode !== "manual") {
        const loaded = await loadCandidatesForDatasets(candidatePlotName, imported.data.datasets);
        candidates = loaded.candidates;
        responseLog.push(...loaded.responseLog);
      }
      const firstCandidate = candidates[0];
      if (importMode === "auto" && firstCandidate && effectivePlotName === "Axial Ratio" && ["theta", "phi", "angle"].includes(firstCandidate.x_quantity)) {
        const xName = firstCandidate.x_quantity === "theta" ? "Theta" : firstCandidate.x_quantity === "phi" ? "Phi" : "Angle";
        setAxisConfig({ ...axisDefaults("Axial Ratio"), xLabel: `${xName} (${firstCandidate.x_unit || "deg"})`, yLabel: "Axial Ratio (dB)", xMin: "-180", xMax: "180", yMin: "0", yMax: "10" });
      }
      setDatasets(imported.data.datasets);
      setRecognitions(imported.data.recognitions);
      const selectedCandidates = candidates.filter((candidate) => candidate.selected);
      if (importMode === "auto" && selectedCandidates.length > 0) {
        const createdResult = await createCurvesFromCandidates(selectedCandidates, imported.data.datasets, importMode);
        const nextCurves = [...curves, ...createdResult.created.map((curve, index) => ({ ...curve, order: curves.length + index }))];
        setCurves(nextCurves);
        setMappingCandidates([]);
        setAllMessages(...responseLog, ...createdResult.responseLog);
        setWorkflowState(nextCurves.some((curve) => curve.is_enabled) ? "plot_ready" : "curves_created");
        setPreviewResult((current) => ({
          ...current,
          status: `Auto recognition completed / 自动识别完成：${imported.data.datasets.length} Dataset, ${createdResult.created.length} Curve.`,
          error: createdResult.created.length > 0 ? null : "Auto mode created no curves. Please confirm mapping manually / 自动模式未生成曲线，请确认映射。"
        }));
        if (createdResult.created.length > 0) {
          schedulePreview(nextCurves, 150);
        }
        return;
      }
      setMappingCandidates(candidates);
      setAllMessages(...responseLog);
      setWorkflowState(candidates.length > 0 || importMode === "manual" ? "mapping_required" : "dataset_detected");
      setPreviewResult((current) => ({ ...current, status: `Imported ${imported.data.datasets.length} Dataset(s). Confirm mapping to create Curves / 已导入数据，请确认映射。` }));
    } catch (error) {
      setWorkflowState("error");
      setPreviewResult((current) => ({ ...current, status: "Import failed / 导入失败", error: error instanceof Error ? error.message : String(error) }));
    } finally {
      setBusy(false);
    }
  };

  const scanDirectory = async () => {
    if (!directoryPath.trim()) {
      setPreviewResult((current) => ({ ...current, status: "Waiting for directory path / 等待文件夹路径", error: "Directory path is empty." }));
      return;
    }
    setBusy(true);
    setPreviewResult({ imageUrl: null, status: "Scanning directory and building file index / 正在扫描文件夹...", error: null, report: null, outputs: [] });
    try {
      const result = await callApi<ScanDirectoryData>("scan_directory", {
        directory_path: directoryPath.trim(),
        recursive: recursiveScan
      });
      const selected: Record<string, boolean> = {};
      result.data.files.forEach((file) => {
        selected[file.path] = file.supported;
      });
      setFileIndex(result.data.files);
      setUnsupportedFiles(result.data.unsupported_files || []);
      setSelectedIndexPaths(selected);
      setAllMessages(result);
      setWorkflowState("file_loaded");
      setPreviewResult((current) => ({
        ...current,
        status: `Scan completed / 扫描完成：${result.data.files.length} supported, ${(result.data.unsupported_files || []).length} unsupported`
      }));
    } catch (error) {
      setWorkflowState("error");
      setFileIndex([]);
      setUnsupportedFiles([]);
      setSelectedIndexPaths({});
      setPreviewResult((current) => ({ ...current, status: "Directory scan failed / 扫描文件夹失败", error: error instanceof Error ? error.message : String(error) }));
    } finally {
      setBusy(false);
    }
  };

  const importMultipleFiles = () => importFiles(splitPathList(multiFilePaths));
  const importSelectedIndexedFiles = () => importFiles(fileIndex.filter((file) => file.supported && selectedIndexPaths[file.path]).map((file) => file.path));
  const importAllSupportedIndexedFiles = () => importFiles(fileIndex.filter((file) => file.supported).map((file) => file.path));

  const confirmMappings = async () => {
    if (confirmInFlightRef.current || busy) return;
    const selected = mappingCandidates.filter((candidate) => candidate.selected);
    if (selected.length === 0) {
      setPreviewResult((current) => ({ ...current, error: "Please select at least one candidate curve / 请至少选择一条候选曲线", status: "Waiting for mapping confirmation / 等待确认变量映射" }));
      return;
    }
    confirmInFlightRef.current = true;
    setBusy(true);
    try {
      const created: CurveSummary[] = [];
      const responseLog: ApiResponse<any>[] = [];
      for (const dataset of datasets) {
        const group = selected.filter((candidate) => candidate.dataset_id === dataset.dataset_id);
        if (group.length === 0) continue;
        const candidateUpdates = group
          .filter((candidate) => candidate.x_column === candidate.original_x_column && candidate.y_column === candidate.original_y_column)
          .map((candidate) => ({
            candidate_id: candidate.curve_id,
            label: candidate.label,
            source_role: candidate.source_role,
            x_unit: candidate.x_unit,
            is_normalized: candidate.is_normalized,
            is_enabled: candidate.is_enabled
          }));
        const mappings = group
          .filter((candidate) => candidate.x_column !== candidate.original_x_column || candidate.y_column !== candidate.original_y_column)
          .map((candidate) => ({
            x_column: candidate.x_column,
            y_column: candidate.y_column,
            x_unit: candidate.x_unit,
            x_quantity: candidate.x_quantity,
            y_unit: candidate.y_unit,
            y_quantity: candidate.y_quantity,
            label: candidate.label,
            source_role: candidate.source_role,
            is_normalized: candidate.is_normalized,
            conversion: candidate.conversion,
            family_column: candidate.metadata?.manual_config?.familyColumn || undefined,
            manual_confirmed: operationMode === "manual",
            manual_config: operationMode === "manual" ? manualConfig : {}
          }));
        const result = await callApi<{ curves: CurveSummary[] }>("create_curves", {
          dataset_id: dataset.dataset_id,
          candidate_updates: candidateUpdates,
          mappings
        });
        responseLog.push(result);
        created.push(...result.data.curves);
      }
      if (created.length === 0) {
        setAllMessages(...responseLog);
        setWorkflowState("mapping_required");
        setPreviewResult((current) => ({
          ...current,
          imageUrl: null,
          status: "No Curve was created",
          error: "The backend returned no new curves. Current mapping candidates are kept; please rescan or re-import before confirming again.",
          report: null,
          outputs: []
        }));
        return;
      }
      const nextCurves = [...curves, ...created.map((curve, index) => ({ ...curve, order: curves.length + index }))];
      setCurves(nextCurves);
      setMappingCandidates([]);
      setAllMessages(...responseLog);
      setWorkflowState(nextCurves.some((curve) => curve.is_enabled) ? "plot_ready" : "curves_created");
      setPreviewResult((current) => ({ ...current, imageUrl: null, status: `Created ${created.length} Curve(s). Generate backend preview / 已创建曲线，请生成预览。`, error: null, report: null, outputs: [] }));
    } catch (error) {
      setWorkflowState("error");
      setPreviewResult((current) => ({ ...current, status: "Mapping confirmation failed / 确认映射失败", error: error instanceof Error ? error.message : String(error) }));
    } finally {
      confirmInFlightRef.current = false;
      setBusy(false);
    }
  };

  const refreshPreview = async (nextCurves = curves) => {
    const requestId = ++previewRequestRef.current;
    const enabledIds = activeIdsFor(nextCurves, selectedPlot);
    if (enabledIds.length === 0) {
      setPreviewResult((current) => ({ ...current, imageUrl: null, status: "No enabled compatible curves. Preview paused / 没有可预览的兼容曲线。", error: null }));
      return;
    }
    setPreviewResult((current) => ({ ...current, status: `Refreshing backend preview / 正在刷新预览... (${enabledIds.length} curves)`, error: null }));
    try {
      const result = await callApi<{ preview_path: string | null; outputs: string[]; metrics_report: string }>("generate_preview", {
        ...patternConfigForRequest(),
        plot_type: plotTypeForRequest(),
        curve_ids: enabledIds,
        formats: ["png"],
        output_name: `${exportConfig.filePrefix || "paper_plot"}_preview`,
        output_dir: exportConfig.outputDir || "outputs\\frontend_export",
        dpi: Number(exportConfig.dpi || 600),
        draw_threshold: shouldDrawThreshold(),
        threshold: thresholdForCurrentPlot(),
        project_settings: projectSettingsForRequest(),
        axis: axisConfigForRequest()
      });
      if (requestId !== previewRequestRef.current) return;
      setPreviewResult({ imageUrl: fileUrl(result.data.preview_path), status: `Backend preview synced / 后端预览已同步：${enabledIds.length} curves`, error: null, report: result.data.metrics_report || null, outputs: result.data.outputs || [] });
      setAllMessages(result);
      setWorkflowState("preview_generated");
    } catch (error) {
      if (requestId !== previewRequestRef.current) return;
      setWorkflowState("error");
      setPreviewResult((current) => ({ ...current, status: "Preview generation failed / 预览生成失败", error: error instanceof Error ? error.message : String(error) }));
    }
  };

  const schedulePreview = (nextCurves = curves, delay = 450) => {
    if (previewTimerRef.current !== null) {
      window.clearTimeout(previewTimerRef.current);
    }
    setPreviewResult((current) => ({ ...current, status: "Preview refresh queued / 预览刷新已排队...", error: null }));
    previewTimerRef.current = window.setTimeout(() => {
      previewTimerRef.current = null;
      void refreshPreview(nextCurves);
    }, delay);
  };

  useEffect(() => {
    if (workflowState !== "preview_generated" && workflowState !== "export_ready") return;
    if (activeCurveIds.length === 0 || busy) return;
    schedulePreview(curves, 450);
  }, [projectSettings, axisConfig, patternConfig, selectedPlot]);

  const updateCurve = async (curveId: string, update: Partial<CurveSummary>) => {
    const optimistic = curves.map((curve) => curve.curve_id === curveId ? { ...curve, ...update } : curve);
    setCurves(optimistic);
    try {
      const result = await callApi<{ curve: CurveSummary }>("update_curve", { curve_id: curveId, update_config: update });
      const nextCurves = optimistic.map((curve) => curve.curve_id === curveId ? result.data.curve : curve);
      setCurves(nextCurves);
      setAllMessages(result);
      schedulePreview(nextCurves, 450);
    } catch (error) {
      setWorkflowState("error");
      setCurves(curves);
      setPreviewResult((current) => ({ ...current, status: "Curve update failed / 曲线更新失败", error: error instanceof Error ? error.message : String(error) }));
    }
  };

  const deleteCurve = async (curveId: string) => {
    const nextCurves = curves.filter((curve) => curve.curve_id !== curveId).map((curve, index) => ({ ...curve, order: index }));
    if (previewTimerRef.current !== null) {
      window.clearTimeout(previewTimerRef.current);
      previewTimerRef.current = null;
    }
    previewRequestRef.current += 1;
    setCurves(nextCurves);
    if (nextCurves.length === 0) {
      setWorkflowState(mappingCandidates.length > 0 ? "mapping_required" : datasets.length > 0 ? "curves_created" : "idle");
      setMessages([]);
      setPreviewResult({ imageUrl: null, status: "All curves deleted. Preview cleared / 曲线已全部删除，预览已清空。", error: null, report: null, outputs: [] });
    } else {
      setPreviewResult((current) => ({ ...current, imageUrl: null, report: null, outputs: [], status: "Curve deleted. Syncing preview / 曲线已删除，正在同步预览...", error: null }));
    }
    try {
      const result = await callApi("delete_curve", { curve_id: curveId });
      setAllMessages(result);
      if (nextCurves.length > 0) {
        schedulePreview(nextCurves, 250);
      }
    } catch (error) {
      setWorkflowState("error");
      setCurves(curves);
      setPreviewResult((current) => ({ ...current, status: "Curve deletion failed / 删除曲线失败", error: error instanceof Error ? error.message : String(error) }));
    }
  };

  const moveCurve = async (curveId: string, direction: -1 | 1) => {
    const sorted = [...curves].sort((a, b) => a.order - b.order);
    const index = sorted.findIndex((curve) => curve.curve_id === curveId);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= sorted.length) return;
    [sorted[index], sorted[target]] = [sorted[target], sorted[index]];
    const reordered = sorted.map((curve, order) => ({ ...curve, order }));
    setCurves(reordered);
    await updateCurve(curveId, { order: reordered.find((curve) => curve.curve_id === curveId)?.order ?? index });
  };

  const exportPlot = async () => {
    if (activeCurveIds.length === 0) return;
    setBusy(true);
    try {
      const hasBlockingErrors = Boolean(previewResult.error) || messages.some((message) => message.code.toLowerCase().includes("error"));
      const formats = selectedFormats().filter((format) => !(hasBlockingErrors && ["txt", "md", "markdown"].includes(format)));
      const result = await callApi<{ outputs: string[]; metrics_report: string; preview_path: string | null }>("export_plot", {
        ...patternConfigForRequest(),
        plot_type: plotTypeForRequest(),
        curve_ids: activeCurveIds,
        formats,
        output_dir: exportConfig.outputDir || "outputs\\frontend_export",
        output_name: exportConfig.filePrefix || "paper_plot",
        dpi: Number(exportConfig.dpi || 600),
        export_scope: exportConfig.scope,
        draw_threshold: shouldDrawThreshold(),
        threshold: thresholdForCurrentPlot(),
        project_settings: projectSettingsForRequest(),
        axis: axisConfigForRequest(),
        manual_config: operationMode === "manual" ? manualConfig : undefined
      });
      setPreviewResult({ imageUrl: fileUrl(result.data.preview_path), status: hasBlockingErrors ? "Debug plot exported only; engineering report skipped due to Error / 已导出调试图，未导出工程结论报告" : "Export completed / 正式导出完成", error: null, report: result.data.metrics_report, outputs: result.data.outputs });
      setAllMessages(result);
      setWorkflowState("export_ready");
    } catch (error) {
      setWorkflowState("error");
      setPreviewResult((current) => ({ ...current, status: "Export failed / 导出失败", error: error instanceof Error ? error.message : String(error) }));
    } finally {
      setBusy(false);
    }
  };

  const restoreProject = async () => {
    if (!configPath.trim()) return;
    setBusy(true);
    try {
      const result = await callApi<{
        datasets: DatasetSummary[];
        recognitions: RecognitionSummary[];
        curves: CurveSummary[];
        plot_config: any;
        project_settings: any;
        export_config: any;
      }>("restore_project", { config_path: configPath });
      const restoredPlotType = result.data.plot_config?.plot_type || "s11";
      const restoredPlot = plots.find((item) => item.apiType === restoredPlotType)?.name || selectedPlot;
      const settings = result.data.project_settings || {};
      const band = settings.working_band_mhz || settings.target_band_mhz || result.data.plot_config?.target_band || [];
      const polar = result.data.plot_config?.polar_config || {};
      const restoredDisplayMode = result.data.plot_config?.pattern_display_mode || result.data.plot_config?.display_mode || polar.display_mode || "cartesian";
      setSelectedPlot(restoredPlot);
      setAxisConfig(axisDefaults(restoredPlot));
      setPatternConfig((current) => ({
        ...current,
        displayMode: restoredDisplayMode === "polar" ? "polar" : "cartesian",
        rMin: polar.r_min != null ? String(polar.r_min) : current.rMin,
        rMax: polar.r_max != null ? String(polar.r_max) : current.rMax,
        normalize: Boolean(polar.normalize ?? current.normalize),
        thetaZeroLocation: polar.theta_zero_location || current.thetaZeroLocation,
        thetaDirection: polar.theta_direction != null ? String(polar.theta_direction) : current.thetaDirection,
        polarStyle: polar.polar_style || current.polarStyle,
        angleLabelMode: polar.angle_label_mode || current.angleLabelMode,
        clipBelowRMin: Boolean(polar.clip_below_r_min ?? current.clipBelowRMin),
        legendLoc: polar.legend_loc || current.legendLoc
      }));
      setDatasets(result.data.datasets || []);
      setRecognitions(result.data.recognitions || []);
      setCurves(result.data.curves || []);
      setMappingCandidates([]);
      setWorkflowState((result.data.curves || []).length ? "plot_ready" : "dataset_detected");
      setProjectSettings({
        bandStartMHz: band?.[0] != null ? String(band[0]) : "",
        bandEndMHz: band?.[1] != null ? String(band[1]) : "",
        s11ThresholdDb: String(settings.s11_threshold_db ?? result.data.plot_config?.threshold_conditions?.threshold ?? -10),
        vswrThreshold: String(settings.vswr_threshold ?? 2),
        axialRatioThresholdDb: String(settings.axial_ratio_threshold_db ?? 3),
        minGainDbi: String(settings.min_gain_dbi ?? 0),
        portImpedanceOhm: String(settings.port_impedance_ohm ?? 50),
        preferRealizedGain: Boolean(settings.prefer_realized_gain ?? true),
        patternFrequenciesMHz: Array.isArray(settings.pattern_frequencies_mhz) ? settings.pattern_frequencies_mhz.join(", ") : "410, 450, 490"
      });
      const formats = result.data.export_config?.formats || [];
      setExportConfig((current) => ({
        ...current,
        png: formats.length ? formats.includes("png") : current.png,
        pdf: formats.length ? formats.includes("pdf") : current.pdf,
        svg: formats.length ? formats.includes("svg") : current.svg,
        json: formats.length ? formats.includes("json") : current.json,
        txt: formats.length ? formats.includes("txt") : current.txt,
        md: formats.length ? (formats.includes("md") || formats.includes("markdown")) : current.md,
        scope: result.data.export_config?.scope || current.scope
      }));
      setAllMessages(result);
      setPreviewResult((current) => ({ ...current, status: "JSON project restored. Generating preview / JSON 配置已恢复，正在生成预览...", error: null }));
      const restoredCurveIds = activeIdsFor(result.data.curves || [], restoredPlot);
      if (restoredCurveIds.length > 0) {
        const restoredSettings = {
          ...settings,
          target_band_mhz: band?.length >= 2 ? [Number(band[0]), Number(band[1])] : null,
          working_band_mhz: band?.length >= 2 ? [Number(band[0]), Number(band[1])] : null
        };
        const preview = await callApi<{ preview_path: string | null; outputs: string[]; metrics_report: string }>("generate_preview", {
          plot_type: restoredPlotType,
          pattern_display_mode: restoredDisplayMode,
          display_mode: restoredDisplayMode,
          polar_config: restoredPlotType === "pattern" ? polar : undefined,
          curve_ids: restoredCurveIds,
          formats: ["png"],
          output_name: `${exportConfig.filePrefix || "paper_plot"}_restored_preview`,
          output_dir: exportConfig.outputDir,
          threshold: Number(settings.s11_threshold_db ?? result.data.plot_config?.threshold_conditions?.threshold ?? -10),
          project_settings: restoredSettings
        });
        setPreviewResult({ imageUrl: fileUrl(preview.data.preview_path), status: "JSON project restored with preview / JSON 配置已恢复并生成预览", error: null, report: preview.data.metrics_report || null, outputs: preview.data.outputs || [] });
        setWorkflowState("preview_generated");
      }
    } catch (error) {
      setWorkflowState("error");
      setPreviewResult((current) => ({ ...current, status: "JSON restore failed / JSON 配置恢复失败", error: error instanceof Error ? error.message : String(error) }));
    } finally {
      setBusy(false);
    }
  };

  const selectPlot = (plot: string) => {
    const nextMode = isFreeXYPlot(plot) ? "manual" : isFreeXYPlot(selectedPlot) ? "semiauto" : operationMode;
    setSelectedPlot(plot);
    setOperationMode(workflowModeForPlot(plot, nextMode));
    setSuggestedPlot(null);
    setManualConfig((current) => ({ ...current, plotType: plotApiType(plot) }));
    setAxisConfig(axisDefaults(plot));
    setPreviewResult((current) => ({ ...current, imageUrl: null, status: "Plot type changed. Incompatible curves are disabled for preview/export / 绘图类型已切换，不兼容曲线不参与预览导出。", error: null, report: null, outputs: [] }));
  };

  const useSuggestedPlot = async () => {
    if (!suggestedPlot) return;
    const nextPlot = suggestedPlot;
    const nextMode = workflowModeForPlot(nextPlot, operationMode);
    setSelectedPlot(nextPlot);
    setOperationMode(nextMode);
    setManualConfig((current) => ({ ...current, plotType: plotApiType(nextPlot) }));
    setAxisConfig(axisDefaults(nextPlot));
    setSuggestedPlot(null);
    if (datasets.length === 0) {
      setPreviewResult((current) => ({ ...current, imageUrl: null, status: "Suggested plot type applied.", error: null, report: null, outputs: [] }));
      return;
    }
    setBusy(true);
    try {
      const loaded = await loadCandidatesForDatasets(nextPlot, datasets);
      const nextCandidates = loaded.candidates;
      const responseLog = loaded.responseLog;
      const recommendedDisplay = recognitions.find((recognition) => recognition.report_plan?.recommended_display_mode)?.report_plan?.recommended_display_mode;
      if (nextPlot === "Radiation Pattern" && recommendedDisplay === "polar") {
        setPatternConfig((current) => ({ ...current, displayMode: "polar" }));
      }
      setMappingCandidates(nextCandidates);
      setAllMessages(...responseLog);
      setWorkflowState(nextCandidates.length > 0 ? "mapping_required" : "dataset_detected");
      setPreviewResult((current) => ({
        ...current,
        imageUrl: null,
        status: nextCandidates.length > 0 ? `Suggested plot applied; ${nextCandidates.length} candidate curves loaded.` : "Suggested plot applied, but no compatible candidate curves were found.",
        error: nextCandidates.length > 0 ? null : "No compatible candidate curves were found for the suggested plot type.",
        report: null,
        outputs: []
      }));
    } catch (error) {
      setWorkflowState("error");
      setPreviewResult((current) => ({ ...current, imageUrl: null, status: "Failed to apply suggested plot type.", error: error instanceof Error ? error.message : String(error), report: null, outputs: [] }));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={theme === "dark" ? "dark bg-slate-950 text-slate-100" : "bg-slate-100 text-slate-950"}>
      <div className="app-shell">
        <SidebarCleanExternal theme={theme} setTheme={setTheme} selectedPlot={selectedPlot} selectPlot={selectPlot} plots={plots} />
        <main className="main-shell">
          <WorkflowHeaderCleanExternal state={workflowState} />
          <div className="workflow-grid">
            <section className="settings-scroll space-y-4">
              <StepCardCleanExternal step={1} title="Import data / 导入数据" state={workflowState} enabled>
                <ImportWorkflowPanelCleanExternal
                  selectedPlot={selectedPlot}
                  operationMode={operationMode}
                  setOperationMode={setOperationMode}
                  singleFilePath={singleFilePath}
                  setSingleFilePath={setSingleFilePath}
                  multiFilePaths={multiFilePaths}
                  setMultiFilePaths={setMultiFilePaths}
                  directoryPath={directoryPath}
                  setDirectoryPath={setDirectoryPath}
                  recursiveScan={recursiveScan}
                  setRecursiveScan={setRecursiveScan}
                  configPath={configPath}
                  setConfigPath={setConfigPath}
                  onImportSingle={() => importFiles([singleFilePath.trim()].filter(Boolean))}
                  onImportMultiple={importMultipleFiles}
                  onScanDirectory={scanDirectory}
                  onRestore={restoreProject}
                  busy={busy}
                />
                <FileIndexPanelCleanExternal
                  files={fileIndex}
                  unsupportedFiles={unsupportedFiles}
                  selectedPaths={selectedIndexPaths}
                  setSelectedPaths={setSelectedIndexPaths}
                  extensionFilter={extensionFilter}
                  setExtensionFilter={setExtensionFilter}
                  dataTypeFilter={dataTypeFilter}
                  setDataTypeFilter={setDataTypeFilter}
                  showUnsupported={showUnsupported}
                  setShowUnsupported={setShowUnsupported}
                  onImportSelected={importSelectedIndexedFiles}
                  onImportAllSupported={importAllSupportedIndexedFiles}
                  busy={busy}
                />
              </StepCardCleanExternal>
              <StepCardCleanExternal step={2} title="Recognition and mapping / 识别与映射" state={workflowState} enabled={datasets.length > 0}>
                <DatasetRecognitionPanelCleanExternal datasets={datasets} recognitions={recognitions} candidates={mappingCandidates} messages={messages} suggestedPlot={suggestedPlot} selectedPlot={selectedPlot} onUseSuggestedPlot={useSuggestedPlot} />
                {operationMode === "manual" && <ManualModePanelCleanExternal datasets={datasets} manualConfig={manualConfig} setManualConfig={setManualConfig} setCandidates={setMappingCandidates} />}
                <MappingReviewPanelCleanExternal datasets={datasets} recognitions={recognitions} candidates={mappingCandidates} setCandidates={setMappingCandidates} onConfirm={confirmMappings} busy={busy || !canConfirmMapping} />
              </StepCardCleanExternal>
              <StepCardCleanExternal step={3} title="Curve manager / 曲线管理" state={workflowState} enabled={curves.length > 0}>
                <CurveManagerPanelCleanExternal curves={curves} selectedPlot={selectedPlot} updateCurve={updateCurve} deleteCurve={deleteCurve} moveCurve={moveCurve} />
              </StepCardCleanExternal>
              <StepCardCleanExternal step={4} title="Plot settings / 单图设置" state={workflowState} enabled={curves.length > 0}>
                <SettingsPanelCleanExternal selectedPlot={selectedPlot} axisConfig={axisConfig} setAxisConfig={setAxisConfig} patternConfig={patternConfig} setPatternConfig={setPatternConfig} messages={messages} onPreview={() => refreshPreview()} onExport={exportPlot} busy={busy || !canGeneratePreview} />
                <ProjectSettingsPanelCleanExternal selectedPlot={selectedPlot} projectSettings={projectSettings} setProjectSettings={setProjectSettings} />
              </StepCardCleanExternal>
            </section>
            <section className="settings-scroll space-y-4">
              <StepCardCleanExternal step={5} title="Preview and export / 预览导出" state={workflowState} enabled={curves.length > 0}>
                <WorkflowGateCleanExternal canPreview={canGeneratePreview} canExport={canExportFormal} hasErrors={hasErrors} mappingPending={mappingCandidates.length > 0} />
                <div className="grid grid-cols-2 gap-2">
                  <button type="button" onClick={() => refreshPreview()} disabled={!canGeneratePreview} className="rounded-md bg-slate-900 px-3 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-slate-100 dark:text-slate-950">Preview / 预览</button>
                  <button type="button" onClick={exportPlot} disabled={!canExportFormal} className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50">Export / 导出</button>
                </div>
                <ExportPanelCleanExternal exportConfig={exportConfig} setExportConfig={setExportConfig} onExport={exportPlot} busy={busy || !canExportFormal} hasErrors={hasErrors} onErrorClick={() => scrollToErrorTarget("TXT Markdown report export error")} />
              </StepCardCleanExternal>
              <BackendCanvasPreviewCleanExternal theme={theme} previewResult={previewResult} selectedPlot={selectedPlot} enabledCount={activeCurveIds.length} messages={messages} />
            </section>
          </div>
        </main>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);


