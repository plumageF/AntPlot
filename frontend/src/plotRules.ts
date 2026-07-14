import type { AxisConfig, AxisLabelMode, CurveSummary, OperationMode, RangeMode } from "./types";

export function isFreeXYPlot(plot: string) {
  return plot === "XY Multi-Curve";
}

export function workflowModeForPlot(plot: string, requestedMode: OperationMode | boolean): OperationMode {
  if (isFreeXYPlot(plot)) return "manual";
  if (typeof requestedMode === "boolean") return requestedMode ? "auto" : "semiauto";
  return requestedMode === "auto" ? "auto" : "semiauto";
}

export function plotApiType(plot: string) {
  const mapping: Record<string, string> = {
    "S11 / Return Loss": "s11",
    "Realized Gain": "gain",
    "Radiation Pattern": "pattern",
    "Axial Ratio": "ar",
    "VSWR": "vswr",
    "Efficiency": "efficiency",
    "HPBW": "hpbw",
    "Smith Chart": "smith",
    "XY Multi-Curve": "xy"
  };
  return mapping[plot] || "s11";
}

export function plotNameFromApiType(apiType: string) {
  const mapping: Record<string, string> = {
    s11: "S11 / Return Loss",
    gain: "Realized Gain",
    pattern: "Radiation Pattern",
    ar: "Axial Ratio",
    vswr: "VSWR",
    efficiency: "Efficiency",
    hpbw: "HPBW",
    smith: "Smith Chart",
    xy: "XY Multi-Curve"
  };
  return mapping[apiType] || "S11 / Return Loss";
}

export function curveCompatibleWithPlot(plot: string, curve: CurveSummary) {
  const plotType = plotApiType(plot);
  const xq = String(curve.x_quantity || "").toLowerCase();
  const yq = String(curve.y_quantity || "").toLowerCase();
  const text = `${curve.label} ${curve.x_column} ${curve.y_column} ${curve.conversion || ""}`.toLowerCase();
  const isFreq = xq === "frequency";
  const isAngle = ["theta", "phi", "angle"].includes(xq);
  const isS11 = yq === "s11" || text.includes("s11") || text.includes("s(1,1)") || text.includes("returnloss") || text.includes("return loss");
  const isVswr = yq === "vswr" || text.includes("vswr") || text.includes("vsmr");
  const isGain = ["gain", "realizedgain"].includes(yq) || text.includes("gain");
  const isPolarPatternQuantity = isGain || text.includes("rhcp") || text.includes("lhcp") || text.includes("co-pol") || text.includes("cross-pol") || text.includes("copol") || text.includes("crosspol");
  const isAr = yq === "ar" || yq === "axialratio" || text.includes("axial");
  const isEff = yq === "efficiency" || text.includes("efficiency");
  const compatibleNames = [...(curve.compatible_plot_types || []), ...(curve.metadata?.compatible_plot_types || [])].join(" ").toLowerCase();
  const reportDomain = String(curve.report_domain || curve.metadata?.report_domain || "").toLowerCase();
  const isSmith = Boolean(
    curve.metadata?.smith_chart ||
    curve.metadata?.complex_network ||
    compatibleNames.includes("smith") ||
    reportDomain.includes("complex") ||
    text.includes("zin") ||
    text.includes("yin") ||
    text.includes("re(") ||
    text.includes("im(") ||
    text.includes("complex s11") ||
    text.includes("s(1,1)")
  );

  if (plotType === "s11") return { ok: isFreq && isS11, reason: "S11 plot only accepts Frequency + S11/Return Loss curves." };
  if (plotType === "vswr") return { ok: isFreq && (isVswr || isS11), reason: "VSWR plot only accepts Frequency + VSWR curves, or VSWR derived from S11." };
  if (plotType === "gain") return { ok: isFreq && isGain, reason: "Realized Gain frequency plot only accepts Frequency + Gain/RealizedGain curves." };
  if (plotType === "pattern") return { ok: isAngle && isPolarPatternQuantity && !isAr, reason: "Radiation Pattern only accepts Theta/Phi/Angle + Gain/RealizedGain/RHCP/LHCP/Co-pol/Cross-pol curves." };
  if (plotType === "ar") return { ok: (isFreq || isAngle) && isAr, reason: "Axial Ratio accepts Frequency + AR or Angle + AR curves." };
  if (plotType === "efficiency") return { ok: isFreq && isEff, reason: "Efficiency only accepts Frequency + Efficiency curves." };
  if (plotType === "hpbw") return { ok: text.includes("hpbw") || (isAngle && isGain), reason: "HPBW requires HPBW curves or radiation-pattern curves that can derive HPBW." };
  if (plotType === "smith") return { ok: isSmith, reason: "Smith Chart requires complex network or impedance trajectory data." };
  return { ok: true, reason: "" };
}

export function axisDefaults(plot: string): AxisConfig {
  const base = {
    labelMode: "auto" as AxisLabelMode,
    rangeMode: "auto" as RangeMode,
    xTickMajor: "",
    yTickMajor: "",
    xTickMinor: "",
    yTickMinor: "",
    gridEnabled: true,
    noteText: "",
    noteX: "0.05",
    noteY: "0.95"
  };
  if (plot.includes("Radiation")) return { ...base, xLabel: "Angle (deg)", yLabel: "Realized Gain (dBi)", xMin: "0", xMax: "360", yMin: "-30", yMax: "10" };
  if (plot.includes("Gain")) return { ...base, xLabel: "Frequency (GHz)", yLabel: "Realized Gain (dBi)", xMin: "1.60", xMax: "1.80", yMin: "0", yMax: "8" };
  if (plot.includes("VSWR")) return { ...base, xLabel: "Frequency (GHz)", yLabel: "VSWR", xMin: "1.60", xMax: "1.80", yMin: "1", yMax: "5" };
  if (plot.includes("Axial")) return { ...base, xLabel: "Frequency (GHz)", yLabel: "Axial Ratio (dB)", xMin: "1.60", xMax: "1.80", yMin: "0", yMax: "10" };
  return { ...base, xLabel: "Frequency (GHz)", yLabel: "S11 (dB)", xMin: "1.60", xMax: "1.80", yMin: "-40", yMax: "0" };
}

export function formatFamilyInfo(info?: Record<string, any> | null) {
  if (!info || Object.keys(info).length === 0) return "none";
  const parts: string[] = [];
  const parameters = info.parameters && typeof info.parameters === "object" ? info.parameters as Record<string, unknown> : null;
  if (info.family_variable && info.family_value != null) parts.push(`${info.family_variable} = ${info.family_value}`);
  if (info.family_variable && info.family_value_deg != null) parts.push(`${info.family_variable} = ${info.family_value_deg} deg`);
  if (info.fixed_variable && info.fixed_value_deg != null) parts.push(`Fixed ${info.fixed_variable} = ${info.fixed_value_deg} deg`);
  if (info.fixed_frequency != null) parts.push(`Fixed Freq = ${info.fixed_frequency}`);
  if (info.scan_variable) parts.push(`Sweep = ${info.scan_variable}`);
  if (parameters) {
    parts.push(...Object.entries(parameters).map(([key, value]) => `${key} = ${String(value)}`));
  }
  for (const [key, value] of Object.entries(info)) {
    if (["parameters", "family_variable", "family_value", "family_value_deg", "fixed_variable", "fixed_value_deg", "fixed_frequency", "scan_variable"].includes(key)) continue;
    if (typeof value === "string" || typeof value === "number") parts.push(`${key} = ${value}`);
  }
  return parts.length ? parts.join(", ") : "none";
}

export function errorTargetForText(text: string, code = "") {
  const haystack = `${code} ${text}`.toLowerCase();
  if (haystack.includes("txt") || haystack.includes("markdown")) return "export-report-options";
  if (haystack.includes("import") || haystack.includes("file") || haystack.includes("directory") || haystack.includes("json") || haystack.includes("导入") || haystack.includes("文件")) return "workflow-step-1";
  if (haystack.includes("dataset") || haystack.includes("recognition") || haystack.includes("column") || haystack.includes("unit") || haystack.includes("识别") || haystack.includes("列") || haystack.includes("单位")) return "workflow-step-2";
  if (haystack.includes("mapping") || haystack.includes("candidate") || haystack.includes("variable") || haystack.includes("变量") || haystack.includes("映射") || haystack.includes("候选")) return "workflow-step-2";
  if (haystack.includes("curve") || haystack.includes("overlay") || haystack.includes("compatible") || haystack.includes("曲线") || haystack.includes("兼容")) return "workflow-step-3";
  if (haystack.includes("axis") || haystack.includes("threshold") || haystack.includes("band") || haystack.includes("setting") || haystack.includes("坐标") || haystack.includes("阈值") || haystack.includes("频段") || haystack.includes("设置")) return "workflow-step-4";
  if (haystack.includes("export") || haystack.includes("report") || haystack.includes("markdown") || haystack.includes("txt") || haystack.includes("导出") || haystack.includes("报告")) return "workflow-step-5";
  if (haystack.includes("preview") || haystack.includes("render") || haystack.includes("plot") || haystack.includes("预览") || haystack.includes("绘图")) return "backend-preview-panel";
  return "workflow-step-5";
}

export function scrollToErrorTarget(message?: { code?: string; message?: string } | string) {
  const text = typeof message === "string" ? message : message?.message || "";
  const code = typeof message === "string" ? "" : message?.code || "";
  const targetId = errorTargetForTextAscii(text, code);
  const element = document.getElementById(targetId);
  if (!element) return;
  element.scrollIntoView({ behavior: "smooth", block: "center" });
  element.classList.add("error-focus-pulse");
  window.setTimeout(() => element.classList.remove("error-focus-pulse"), 1600);
}

function errorTargetForTextAscii(text: string, code = "") {
  const haystack = `${code} ${text}`.toLowerCase();
  if (haystack.includes("txt") || haystack.includes("markdown")) return "export-report-options";
  if (haystack.includes("import") || haystack.includes("file") || haystack.includes("directory") || haystack.includes("json")) return "workflow-step-1";
  if (haystack.includes("dataset") || haystack.includes("recognition") || haystack.includes("column") || haystack.includes("unit")) return "workflow-step-2";
  if (haystack.includes("mapping") || haystack.includes("candidate") || haystack.includes("variable")) return "workflow-step-2";
  if (haystack.includes("curve") || haystack.includes("overlay") || haystack.includes("compatible")) return "workflow-step-3";
  if (haystack.includes("axis") || haystack.includes("threshold") || haystack.includes("band") || haystack.includes("setting")) return "workflow-step-4";
  if (haystack.includes("export") || haystack.includes("report")) return "workflow-step-5";
  if (haystack.includes("preview") || haystack.includes("render") || haystack.includes("plot")) return "backend-preview-panel";
  return "workflow-step-5";
}
