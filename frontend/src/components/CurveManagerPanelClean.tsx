import { useState } from "react";
import { AlertTriangle, ArrowDown, ArrowUp, Eye, EyeOff, Trash2 } from "lucide-react";
import { curveCompatibleWithPlot, formatFamilyInfo } from "../plotRules";
import type { CurveSource, CurveSummary } from "../types";

type Props = {
  curves: CurveSummary[];
  selectedPlot: string;
  updateCurve: (curveId: string, update: Partial<CurveSummary>) => void;
  deleteCurve: (curveId: string) => void;
  moveCurve: (curveId: string, direction: -1 | 1) => void;
};

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

function TextInput({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="block">
      <div className="mb-1 text-xs font-semibold text-slate-500 dark:text-slate-400">{label}</div>
      <input value={value} onChange={(event) => onChange(event.target.value)} className="field" />
    </label>
  );
}

export function CurveManagerPanelCleanExternal({ curves, selectedPlot, updateCurve, deleteCurve, moveCurve }: Props) {
  const ordered = [...curves].sort((a, b) => a.order - b.order);
  const [keepN, setKeepN] = useState("5");
  const [familyFilter, setFamilyFilter] = useState("");
  const [batchWidth, setBatchWidth] = useState("1.5");
  const palette = ["#EF4444", "#4B5563", "#2563EB", "#16A34A", "#F97316", "#7C3AED", "#0891B2", "#DB2777", "#A16207", "#111827"];
  const lineStyles = ["-", "--", "-.", ":"];

  const applyBatchEnabled = (predicate: (curve: CurveSummary, index: number) => boolean) => {
    ordered.forEach((curve, index) => updateCurve(curve.curve_id, { is_enabled: predicate(curve, index) }));
  };

  const applyFamilyFilter = () => {
    const keyword = familyFilter.trim().toLowerCase();
    if (!keyword) return;
    applyBatchEnabled((curve) => `${curve.label} ${JSON.stringify(curve.family_info || curve.metadata?.family_info || {})}`.toLowerCase().includes(keyword));
  };

  const reassignStyles = () => {
    ordered.forEach((curve, index) => updateCurve(curve.curve_id, {
      color: palette[index % palette.length],
      line_style: ordered.length >= 6 ? lineStyles[Math.floor(index / palette.length) % lineStyles.length] : "-",
      line_width: 1.5,
      marker_enabled: false,
      marker_every: Number(curve.sample_count ?? curve.point_count ?? 0) < 300 ? 10 : 50,
      alpha: 1
    }));
  };

  return (
    <Panel title={`${"\u66f2\u7ebf\u7ba1\u7406\u5668"} (${curves.length})`}>
      {ordered.length > 0 && (
        <details className="rounded-md border border-slate-200 bg-white p-3 text-xs dark:border-slate-800 dark:bg-slate-950">
          <summary className="cursor-pointer font-bold">{"\u6279\u91cf\u64cd\u4f5c / Batch controls"}</summary>
          <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-4">
            <button type="button" className="soft-btn" onClick={() => applyBatchEnabled(() => true)}>{"\u5168\u9009"}</button>
            <button type="button" className="soft-btn" onClick={() => applyBatchEnabled(() => false)}>{"\u5168\u4e0d\u9009"}</button>
            <button type="button" className="soft-btn" onClick={() => applyBatchEnabled((_, index) => index < Number(keepN || 0))}>{"\u53ea\u4fdd\u7559\u524d N \u6761"}</button>
            <button type="button" className="soft-btn" onClick={reassignStyles}>{"\u91cd\u65b0\u5206\u914d\u6837\u5f0f"}</button>
            <button type="button" className="soft-btn" onClick={() => ordered.forEach((curve) => updateCurve(curve.curve_id, { marker_enabled: false }))}>{"\u5173\u95ed\u6240\u6709 marker"}</button>
            <button type="button" className="soft-btn" onClick={() => ordered.forEach((curve) => updateCurve(curve.curve_id, { line_width: Number(batchWidth || 1.5) }))}>{"\u6279\u91cf\u8bbe\u7f6e\u7ebf\u5bbd"}</button>
            <input className="field h-8 text-xs" value={keepN} onChange={(event) => setKeepN(event.target.value)} placeholder="N" />
            <input className="field h-8 text-xs" value={batchWidth} onChange={(event) => setBatchWidth(event.target.value)} placeholder="line width" />
            <input className="field h-8 text-xs md:col-span-2" value={familyFilter} onChange={(event) => setFamilyFilter(event.target.value)} placeholder={"\u6309 family / \u53c2\u6570\u5173\u952e\u8bcd\u7b5b\u9009"} />
            <button type="button" className="soft-btn md:col-span-2" onClick={applyFamilyFilter}>{"\u5e94\u7528\u5173\u952e\u8bcd\u7b5b\u9009"}</button>
          </div>
        </details>
      )}

      {ordered.length === 0 ? (
        <div className="rounded-md border border-dashed border-slate-300 p-4 text-sm text-slate-500 dark:border-slate-700">
          {"\u786e\u8ba4\u53d8\u91cf\u6620\u5c04\u540e\uff0cCurve \u4f1a\u8fdb\u5165\u8fd9\u91cc\u3002\u542f\u7528\u3001\u6807\u7b7e\u3001\u987a\u5e8f\u548c\u5f52\u4e00\u5316\u90fd\u4f1a\u5f71\u54cd\u9884\u89c8\u56fe\u3002"}
        </div>
      ) : (
        <div className="space-y-3">
          {ordered.map((curve, index) => (
            <CurveRow key={curve.curve_id} curve={curve} selectedPlot={selectedPlot} index={index} total={ordered.length} updateCurve={updateCurve} deleteCurve={deleteCurve} moveCurve={moveCurve} />
          ))}
        </div>
      )}
    </Panel>
  );
}

function CurveRow({ curve, selectedPlot, index, total, updateCurve, deleteCurve, moveCurve }: { curve: CurveSummary; selectedPlot: string; index: number; total: number; updateCurve: (curveId: string, update: Partial<CurveSummary>) => void; deleteCurve: (curveId: string) => void; moveCurve: (curveId: string, direction: -1 | 1) => void }) {
  const [openWarnings, setOpenWarnings] = useState(false);
  const sourceFile = curve.metadata?.source_file || curve.source_file || curve.dataset_id;
  const compatibility = curveCompatibleWithPlot(selectedPlot, curve);
  const rowEnabled = curve.is_enabled && compatibility.ok;

  return (
    <div className={`rounded-lg border p-3 ${rowEnabled ? "border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950" : "border-amber-200 bg-amber-50/60 opacity-80 dark:border-amber-500/30 dark:bg-amber-500/10"}`}>
      <div className="mb-3 flex items-center gap-2">
        <button type="button" title={"\u542f\u7528/\u7981\u7528"} onClick={() => updateCurve(curve.curve_id, { is_enabled: !curve.is_enabled })} className={`grid h-8 w-8 place-items-center rounded-md ${curve.is_enabled ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-200" : "bg-slate-200 text-slate-500 dark:bg-slate-800"}`}>
          {curve.is_enabled ? <Eye size={16} /> : <EyeOff size={16} />}
        </button>
        <input value={curve.label} onChange={(event) => updateCurve(curve.curve_id, { label: event.target.value })} className="field h-9 flex-1 font-semibold" />
        <input type="color" value={String(curve.color || curve.metadata?.color || "#EF4444")} onChange={(event) => updateCurve(curve.curve_id, { color: event.target.value })} className="h-9 w-12 rounded-md border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900" title="color" />
        <select value={String(curve.line_style ?? curve.metadata?.line_style ?? "-")} onChange={(event) => updateCurve(curve.curve_id, { line_style: event.target.value })} className="field h-9 w-20 text-xs" title="line style">
          {["-", "--", "-.", ":"].map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
        <input type="number" min="0.3" max="6" step="0.1" value={String(curve.line_width ?? curve.metadata?.line_width ?? 1.5)} onChange={(event) => updateCurve(curve.curve_id, { line_width: Number(event.target.value) })} className="field h-9 w-20 text-xs" title="line width" />
        <span className="rounded-md bg-slate-100 px-2 py-1 text-xs dark:bg-slate-900">samples: {String(curve.sample_count ?? curve.point_count ?? "-")}</span>
        <button type="button" onClick={() => setOpenWarnings(!openWarnings)} className={`rounded-md px-2 py-1 text-xs font-semibold ${(curve.warnings?.length || 0) ? "bg-amber-100 text-amber-800 dark:bg-amber-400/10 dark:text-amber-100" : "bg-slate-100 text-slate-500 dark:bg-slate-900"}`}>warnings: {curve.warnings?.length || 0}</button>
        <button type="button" title={"\u4e0a\u79fb"} disabled={index === 0} onClick={() => moveCurve(curve.curve_id, -1)} className="icon-btn"><ArrowUp size={15} /></button>
        <button type="button" title={"\u4e0b\u79fb"} disabled={index === total - 1} onClick={() => moveCurve(curve.curve_id, 1)} className="icon-btn"><ArrowDown size={15} /></button>
        <button type="button" title={"\u5220\u9664"} onClick={() => deleteCurve(curve.curve_id)} className="icon-btn text-red-600"><Trash2 size={15} /></button>
      </div>

      <details className="mt-3 rounded-md border border-slate-200 bg-slate-50 p-3 text-xs dark:border-slate-800 dark:bg-slate-900/50">
        <summary className="cursor-pointer font-bold text-slate-600 dark:text-slate-200">{"\u9ad8\u7ea7\u8be6\u60c5\uff1a\u6837\u5f0f\u3001\u91c7\u6837\u70b9\u3001\u6765\u6e90\u548c\u517c\u5bb9\u6027"}</summary>
        <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-600 dark:text-slate-300">
          <InfoCell label={"\u6765\u6e90\u6587\u4ef6"} value={String(sourceFile)} />
          <InfoCell label="source_type" value={String(curve.source_type || curve.source_role)} />
          <SelectField label="source_type" value={curve.source_role} options={["Simulated", "Measured", "Reference", "Manual", "Unknown"]} onChange={(value) => updateCurve(curve.curve_id, { source_role: value as CurveSource })} />
          <InfoCell label="Report Domain" value={String(curve.report_domain || curve.metadata?.report_domain || "unknown")} />
          <InfoCell label={"\u0058 \u8f74\u53d8\u91cf"} value={curve.x_column} />
          <InfoCell label={"\u0059 \u8f74\u53d8\u91cf"} value={curve.y_column} />
          <InfoCell label={"\u0058 \u5355\u4f4d"} value={curve.x_unit} />
          <InfoCell label={"\u0059 \u5355\u4f4d"} value={curve.y_unit} />
          <InfoCell label="sample_count" value={String(curve.sample_count ?? curve.point_count)} />
          <InfoCell label="raw_sample_count" value={String(curve.raw_sample_count ?? curve.metadata?.raw_sample_count ?? curve.sample_count ?? curve.point_count)} />
          <InfoCell label="unique_x_count" value={String(curve.unique_x_count ?? curve.metadata?.unique_x_count ?? "-")} />
          <InfoCell label="duplicate_x_after_grouping" value={String(curve.duplicate_x_count_after_grouping ?? curve.metadata?.duplicate_x_count_after_grouping ?? 0)} />
          <InfoCell label="displayed_sample_count" value={String(curve.displayed_sample_count ?? curve.metadata?.displayed_sample_count ?? curve.sample_count ?? curve.point_count)} />
          <InfoCell label="family_info" value={formatFamilyInfo(curve.family_info || curve.metadata?.family_info)} />
          <InfoCell label={"\u8f6c\u6362"} value={curve.conversion || "none"} />
          <InfoCell label="compatible_plot_types" value={(curve.compatible_plot_types || curve.metadata?.compatible_plot_types || []).join(", ") || "-"} />
          <TextInput label="line_width" value={String(curve.line_width ?? curve.metadata?.line_width ?? 1.8)} onChange={(value) => updateCurve(curve.curve_id, { line_width: Number(value) })} />
          <label className="min-w-0">
            <div className="mb-1 font-semibold text-slate-400">line_width slider</div>
            <input type="range" min="0.3" max="6" step="0.1" value={Number(curve.line_width ?? curve.metadata?.line_width ?? 1.5)} onChange={(event) => updateCurve(curve.curve_id, { line_width: Number(event.target.value) })} className="w-full accent-indigo-600" />
          </label>
          <SelectField label="line_style" value={String(curve.line_style ?? curve.metadata?.line_style ?? "-")} options={["-", "--", ":", "-."]} onChange={(value) => updateCurve(curve.curve_id, { line_style: value })} />
          <label className="min-w-0">
            <div className="mb-1 font-semibold text-slate-400">color</div>
            <input type="color" value={String(curve.color || curve.metadata?.color || "#4D4D4D")} onChange={(event) => updateCurve(curve.curve_id, { color: event.target.value })} className="h-8 w-full rounded-md border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900" />
          </label>
          <SelectField label="marker" value={String(curve.marker ?? curve.metadata?.marker ?? "o")} options={["o", "s", "^", "D", "v", "P", "x", "+"]} onChange={(value) => updateCurve(curve.curve_id, { marker: value })} />
          <TextInput label="marker_size" value={String(curve.marker_size ?? curve.metadata?.marker_size ?? 3)} onChange={(value) => updateCurve(curve.curve_id, { marker_size: Number(value) })} />
          <TextInput label="marker_every" value={String(curve.marker_every ?? curve.metadata?.marker_every ?? 10)} onChange={(value) => updateCurve(curve.curve_id, { marker_every: Number(value) })} />
          <TextInput label="alpha" value={String(curve.alpha ?? curve.metadata?.alpha ?? 1)} onChange={(value) => updateCurve(curve.curve_id, { alpha: Number(value) })} />
          <SelectField label="sample_display_policy" value={String(curve.sample_display_policy ?? curve.metadata?.sample_display_policy ?? "marker_only_decimate")} options={["raw", "preview_decimate", "marker_only_decimate", "resample_for_display"]} onChange={(value) => updateCurve(curve.curve_id, { sample_display_policy: value })} />
          <label className="flex items-center gap-2 pt-5"><input type="checkbox" checked={curve.marker_enabled ?? curve.metadata?.marker_enabled ?? false} onChange={(event) => updateCurve(curve.curve_id, { marker_enabled: event.target.checked })} className="accent-indigo-600" />marker on/off</label>
          <label className="flex items-center gap-2 pt-5"><input type="checkbox" checked={curve.is_normalized} onChange={(event) => updateCurve(curve.curve_id, { is_normalized: event.target.checked })} className="accent-indigo-600" />normalization</label>
          <label className="flex items-center gap-2 pt-5"><input type="checkbox" checked={curve.participate_metrics ?? curve.metadata?.participate_metrics ?? true} onChange={(event) => updateCurve(curve.curve_id, { participate_metrics: event.target.checked })} className="accent-indigo-600" />{"\u53c2\u4e0e\u6307\u6807\u8ba1\u7b97"}</label>
        </div>
      </details>

      {!compatibility.ok && (
        <div className="mt-3 rounded-md bg-amber-100 px-3 py-2 text-xs font-semibold text-amber-800 dark:bg-amber-400/10 dark:text-amber-100">
          {"\u5f53\u524d\u56fe\u7c7b\u578b\u4e0d\u517c\u5bb9\uff1a"}{compatibility.reason}{"\u3002\u8be5\u66f2\u7ebf\u4e0d\u4f1a\u53c2\u4e0e\u9884\u89c8\u3001\u5bfc\u51fa\u6216\u6307\u6807\u8ba1\u7b97\u3002"}
        </div>
      )}
      <button type="button" onClick={() => setOpenWarnings(!openWarnings)} className="mt-3 flex items-center gap-2 text-xs font-semibold text-amber-600 dark:text-amber-300"><AlertTriangle size={14} /> warnings: {curve.warnings?.length || 0}</button>
      {openWarnings && (
        <div className="mt-2 rounded-md bg-amber-50 p-2 text-xs leading-5 text-amber-800 dark:bg-amber-400/10 dark:text-amber-100">
          {curve.warnings?.length ? curve.warnings.map((warning) => <div key={warning}>{warning}</div>) : "\u8be5\u66f2\u7ebf\u6ca1\u6709 warning\u3002"}
        </div>
      )}
    </div>
  );
}
