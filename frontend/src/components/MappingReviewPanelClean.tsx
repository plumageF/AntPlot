import type React from "react";
import { CheckCircle2 } from "lucide-react";
import { formatFamilyInfo } from "../plotRules";
import type { CurveSource, DatasetSummary, MappingCandidate, RecognitionSummary, ReportPlan } from "../types";

type Props = {
  datasets: DatasetSummary[];
  recognitions: RecognitionSummary[];
  candidates: MappingCandidate[];
  setCandidates: React.Dispatch<React.SetStateAction<MappingCandidate[]>>;
  onConfirm: () => void;
  busy: boolean;
};

const quantities = ["S11", "VSWR", "Gain", "RealizedGain", "AR", "Efficiency", "Phase"];
const xQuantities = ["frequency", "theta", "phi", "angle"];
const units = ["auto", "Hz", "MHz", "GHz", "deg", "dB", "dBi", "linear", "degree"];

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-900/60">
      <div className="mb-3 text-sm font-bold">{title}</div>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function InfoCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <div className="mb-1 font-semibold text-slate-400">{label}</div>
      <div className="truncate rounded-md bg-slate-100 px-2 py-1 dark:bg-slate-900" title={value}>{value}</div>
    </div>
  );
}

function SelectField({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  const list = options.includes(value) ? options : [value, ...options];
  return (
    <label className="block">
      <div className="mb-1 text-xs font-semibold text-slate-500 dark:text-slate-400">{label}</div>
      <select value={value} onChange={(event) => onChange(event.target.value)} className="field h-8 text-xs">
        {list.map((option) => <option key={option} value={option}>{option}</option>)}
      </select>
    </label>
  );
}

function formatRange(ranges?: Record<string, unknown> | null) {
  if (!ranges || typeof ranges !== "object") return "unconfirmed";
  const parts = Object.entries(ranges).flatMap(([key, value]) => {
    if (!value || typeof value !== "object") return [];
    const range = value as { min?: number | string | null; max?: number | string | null };
    if (range.min == null && range.max == null) return [];
    return [`${key}: ${range.min ?? "?"}-${range.max ?? "?"}`];
  });
  return parts.slice(0, 1).join("; ") || "unconfirmed";
}

function sweepText(item?: ReportPlan["primary_sweep"]) {
  return item ? `${item.column} (${item.quantity}${item.unit ? `, ${item.unit}` : ""}; unique=${item.unique_count ?? "?"})` : "unconfirmed";
}

function variableList(items?: Array<{ column: string; values?: number[] }>) {
  return items && items.length ? items.map((item) => `${item.column}${item.values?.length ? `=${item.values.join("/")}` : ""}`).join("; ") : "none";
}

export function MappingReviewPanelCleanExternal({ datasets, recognitions, candidates, setCandidates, onConfirm, busy }: Props) {
  const updateCandidate = (curveId: string, patch: Partial<MappingCandidate>) => {
    setCandidates((current) => current.map((candidate) => candidate.curve_id === curveId ? { ...candidate, ...patch } : candidate));
  };

  if (datasets.length === 0) return null;

  return (
    <Panel title={"\u534a\u81ea\u52a8\u53d8\u91cf\u6620\u5c04\u786e\u8ba4"}>
      <details className="rounded-md border border-slate-200 bg-white p-3 text-xs dark:border-slate-800 dark:bg-slate-950">
        <summary className="cursor-pointer font-bold">{"\u9ad8\u7ea7\u8bc6\u522b\u4fe1\u606f / Report Plan"}</summary>
        <div className="mt-3 space-y-3">
          {datasets.map((dataset) => {
            const recognition = recognitions.find((item) => item.dataset_id === dataset.dataset_id);
            const reportPlan = (recognition?.report_plan || dataset.metadata?.report_plan) as ReportPlan | undefined;
            const ranges = dataset.metadata?.ranges || {};
            const warningText = [...(dataset.warnings || []), ...(recognition?.confirmation_reasons || []), ...(recognition?.warnings || [])].join("; ");
            return (
              <div key={dataset.dataset_id} className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-950">
                <div className="mb-2 truncate text-sm font-bold" title={dataset.source_file}>{dataset.source_file}</div>
                {reportPlan && (
                  <div className="mb-2 rounded-md border border-indigo-200 bg-indigo-50/50 p-2 text-xs leading-5 text-slate-700 dark:border-indigo-500/30 dark:bg-indigo-500/10 dark:text-slate-200">
                    <div className="font-bold text-indigo-700 dark:text-indigo-200">HFSS-like Report Plan</div>
                    <div>domain: {reportPlan.result_domain || "unknown"}; primary: {sweepText(reportPlan.primary_sweep)}</div>
                    <div>fixed: {variableList(reportPlan.fixed_variables)}; family: {variableList(reportPlan.family_variables)}</div>
                    <div>recommended: {reportPlan.recommended_plot_type || "auto"}{reportPlan.recommended_display_mode ? ` / ${reportPlan.recommended_display_mode}` : ""}</div>
                    <div>quantities: {(reportPlan.quantity_columns || []).map((quantity) => `${quantity.column} -> ${quantity.quantity}`).join("; ") || "unconfirmed"}</div>
                  </div>
                )}
                <div className="grid grid-cols-2 gap-2 text-xs text-slate-600 dark:text-slate-300">
                  <InfoCell label={"\u63a8\u6d4b\u6570\u636e\u7c7b\u578b"} value={recognition?.detected_plot_type || dataset.data_type} />
                  <InfoCell label={"\u884c\u6570"} value={String(dataset.row_count)} />
                  <InfoCell label="sample_count" value={String(dataset.sample_count ?? dataset.metadata?.sample_count ?? dataset.row_count)} />
                  <InfoCell label={"\u6570\u636e\u8303\u56f4"} value={formatRange(ranges)} />
                  <InfoCell label={"\u7f3a\u5931/\u91cd\u590d"} value={`missing=${dataset.metadata?.has_missing_values ? "yes" : "no"}; duplicate=${dataset.metadata?.has_duplicate_points ? "yes" : "no"}`} />
                </div>
                <div className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">Columns: {dataset.columns.join(", ")}</div>
                {warningText && <div className="mt-2 text-xs leading-5 text-amber-700 dark:text-amber-300">{warningText}</div>}
              </div>
            );
          })}
        </div>
      </details>

      <div className="space-y-3">
        {candidates.length === 0 ? (
          <div className="rounded-md border border-dashed border-slate-300 p-3 text-sm text-slate-500 dark:border-slate-700">
            {"\u6ca1\u6709\u68c0\u6d4b\u5230\u5019\u9009\u66f2\u7ebf\u3002\u65e0\u8868\u5934\u3001\u5355\u4f4d\u4e0d\u660e\u6216 Formatted Data \u6587\u4ef6\u9700\u8981\u624b\u52a8\u786e\u8ba4\u53d8\u91cf\u540e\u518d\u751f\u6210\u3002"}
          </div>
        ) : candidates.map((candidate) => {
          const dataset = datasets.find((item) => item.dataset_id === candidate.dataset_id);
          const magToDb = (candidate.conversion || "").toLowerCase().includes("20log10(abs");
          const reImToDb = (candidate.conversion || "").toLowerCase().includes("sqrt");
          const familyInfo = formatFamilyInfo(candidate.family_info || candidate.metadata?.family_info);
          return (
            <div key={candidate.curve_id} className={`rounded-lg border p-3 ${candidate.selected ? "border-indigo-300 bg-indigo-50/40 dark:border-indigo-500/40 dark:bg-indigo-500/10" : "border-slate-200 bg-white opacity-70 dark:border-slate-800 dark:bg-slate-950"}`}>
              <div className="mb-3 flex items-center gap-2">
                <input type="checkbox" checked={candidate.selected} onChange={(event) => updateCandidate(candidate.curve_id, { selected: event.target.checked })} className="accent-indigo-600" />
                <input value={candidate.label} onChange={(event) => updateCandidate(candidate.curve_id, { label: event.target.value })} className="field h-9 flex-1 font-semibold" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <SelectField label={"\u0058 \u8f74\u5217"} value={candidate.x_column} options={dataset?.columns || []} onChange={(value) => updateCandidate(candidate.curve_id, { x_column: value })} />
                <SelectField label={"\u0059 \u8f74\u5217"} value={candidate.y_column} options={dataset?.columns || [candidate.y_column]} onChange={(value) => updateCandidate(candidate.curve_id, { y_column: value })} />
                <SelectField label={"\u0058 \u8f74\u7269\u7406\u91cf"} value={candidate.x_quantity} options={xQuantities} onChange={(value) => updateCandidate(candidate.curve_id, { x_quantity: value })} />
                <SelectField label={"\u0059 \u8f74\u7269\u7406\u91cf"} value={candidate.y_quantity} options={quantities} onChange={(value) => updateCandidate(candidate.curve_id, { y_quantity: value })} />
                <SelectField label={"\u0058 \u8f74\u5355\u4f4d"} value={candidate.x_unit} options={units} onChange={(value) => updateCandidate(candidate.curve_id, { x_unit: value })} />
                <SelectField label={"\u0059 \u8f74\u5355\u4f4d"} value={candidate.y_unit} options={units} onChange={(value) => updateCandidate(candidate.curve_id, { y_unit: value })} />
                <InfoCell label="sample_count" value={String(candidate.sample_count ?? candidate.point_count ?? "-")} />
                <InfoCell label="warnings" value={String(candidate.warnings?.length || 0)} />
              </div>
              <details className="mt-3 rounded-md border border-slate-200 bg-white p-2 text-xs dark:border-slate-800 dark:bg-slate-950">
                <summary className="cursor-pointer font-bold">{"\u9ad8\u7ea7\u4fe1\u606f"}</summary>
                <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-600 dark:text-slate-300">
                  <SelectField label={"\u6570\u636e\u6765\u6e90\u7c7b\u578b"} value={candidate.source_role} options={["Simulated", "Measured", "Reference", "Manual", "Unknown"]} onChange={(value) => updateCandidate(candidate.curve_id, { source_role: value as CurveSource })} />
                  <label className="flex items-center gap-2"><input type="checkbox" checked={candidate.is_normalized} onChange={(event) => updateCandidate(candidate.curve_id, { is_normalized: event.target.checked })} className="accent-indigo-600" />{"\u5f52\u4e00\u5316"}</label>
                  <label className="flex items-center gap-2"><input type="checkbox" checked={candidate.x_unit !== candidate.original_x_unit} readOnly className="accent-indigo-600" />{"\u8fdb\u884c\u5355\u4f4d\u8f6c\u6362"}</label>
                  <label className="flex items-center gap-2"><input type="checkbox" checked={magToDb} readOnly className="accent-indigo-600" />mag(S11) {"\u8f6c"} dB</label>
                  <label className="flex items-center gap-2"><input type="checkbox" checked={reImToDb} readOnly className="accent-indigo-600" />re/im {"\u8ba1\u7b97"} S11(dB)</label>
                </div>
                <div className="mt-2 grid gap-1 text-slate-500 dark:text-slate-400">
                  <div>source_file: {candidate.source_file || candidate.metadata?.source_file || dataset?.source_file || "-"}</div>
                  <div>report_domain: {candidate.report_domain || candidate.metadata?.report_domain || "unknown"}</div>
                  <div>family_info: {familyInfo}</div>
                  <div>compatible_plot_types: {(candidate.compatible_plot_types || candidate.metadata?.compatible_plot_types || []).join(", ") || "-"}</div>
                  <div>conversion: {candidate.conversion || "none"}</div>
                </div>
              </details>
            </div>
          );
        })}
      </div>

      <button type="button" onClick={onConfirm} disabled={busy || candidates.every((candidate) => !candidate.selected)} className="flex w-full items-center justify-center gap-2 rounded-md bg-emerald-600 px-3 py-2 text-sm font-bold text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50">
        <CheckCircle2 size={16} />{"\u786e\u8ba4\u6240\u9009\u6620\u5c04\u5e76\u751f\u6210 Curve"}
      </button>
    </Panel>
  );
}
