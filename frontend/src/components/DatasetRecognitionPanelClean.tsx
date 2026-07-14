import type { ApiMessage, DatasetSummary, MappingCandidate, RecognitionSummary, ReportModel } from "../types";

type Props = {
  datasets: DatasetSummary[];
  recognitions: RecognitionSummary[];
  candidates: MappingCandidate[];
  messages: ApiMessage[];
  suggestedPlot: string | null;
  selectedPlot: string;
  onUseSuggestedPlot: () => void;
};

function t(text: string) {
  return text;
}

function InfoCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-white/80 px-2 py-1 dark:bg-slate-950/60">
      <div className="text-[11px] font-bold uppercase tracking-wide text-slate-400">{label}</div>
      <div className="truncate text-sm text-slate-800 dark:text-slate-100" title={value}>{value}</div>
    </div>
  );
}

function MessageBucket({ title, items, tone }: { title: string; items: string[]; tone: "red" | "amber" | "slate" }) {
  if (!items.length) return null;
  const cls = tone === "red" ? "text-red-700 dark:text-red-200" : tone === "amber" ? "text-amber-700 dark:text-amber-200" : "text-slate-500 dark:text-slate-300";
  return (
    <div className={`mt-2 text-xs leading-5 ${cls}`}>
      <span className="font-bold">{title}: </span>
      {items.join(" | ")}
    </div>
  );
}

function modelForDataset(dataset: DatasetSummary, recognitions: RecognitionSummary[]) {
  const recognition = recognitions.find((item) => item.dataset_id === dataset.dataset_id);
  return (recognition?.report_model || recognition?.report_plan?.report_model || dataset.metadata?.report_model || dataset.metadata?.report_plan?.report_model) as ReportModel | undefined;
}

export function DatasetRecognitionPanelCleanExternal({ datasets, recognitions, candidates, messages, suggestedPlot, selectedPlot, onUseSuggestedPlot }: Props) {
  if (datasets.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-slate-300 p-3 text-sm text-slate-500 dark:border-slate-700">
        {"\u5bfc\u5165\u6570\u636e\u540e\uff0c\u8fd9\u91cc\u4f1a\u5148\u663e\u793a Dataset \u548c ReportModel\uff0c\u4e0d\u4f1a\u76f4\u63a5\u8df3\u5230\u7a7a\u767d\u9884\u89c8\u3002"}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {suggestedPlot && suggestedPlot !== selectedPlot && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-indigo-200 bg-indigo-50 px-3 py-2 text-xs text-indigo-800 dark:border-indigo-500/30 dark:bg-indigo-500/10 dark:text-indigo-100">
          <span>
            {"\u7cfb\u7edf\u5efa\u8bae\u56fe\u7c7b\u578b\uff1a"}<b>{suggestedPlot}</b>
            {"\u3002\u534a\u81ea\u52a8\u6a21\u5f0f\u4e0d\u4f1a\u5f3a\u5236\u5207\u6362\uff0c\u53ef\u70b9\u51fb\u4f7f\u7528\u5efa\u8bae\u3002"}
          </span>
          <button type="button" onClick={onUseSuggestedPlot} className="rounded-md bg-indigo-600 px-3 py-1.5 font-bold text-white hover:bg-indigo-500">
            {"\u4f7f\u7528\u5efa\u8bae"}
          </button>
        </div>
      )}

      {datasets.map((dataset) => {
        const recognition = recognitions.find((item) => item.dataset_id === dataset.dataset_id);
        const model = modelForDataset(dataset, recognitions);
        const candidateCount = candidates.filter((candidate) => candidate.dataset_id === dataset.dataset_id).length;
        const familyText = (model?.families || []).map((item) => `${item.name}${item.value != null ? ` = ${item.value}${item.unit || ""}` : ""} (${item.role})`).join("; ") || "none";
        const errorItems = [...(model?.errors || []), ...messages.filter((item) => item.severity === "error" || item.code.toLowerCase().includes("error")).map((item) => item.message)];
        const warningItems = [...(model?.warnings || []), ...(dataset.warnings || []), ...(recognition?.warnings || []), ...(recognition?.confirmation_reasons || [])];
        const compatible = model?.compatible_plot_types || recognition?.report_plan?.compatible_plot_types || dataset.compatible_plot_types || [];

        return (
          <div key={dataset.dataset_id} className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-900/60">
            <div className="mb-2 truncate text-sm font-bold" title={dataset.source_file}>{dataset.source_file}</div>
            <div className="grid grid-cols-2 gap-2 text-xs text-slate-600 dark:text-slate-300 lg:grid-cols-3">
              <InfoCell label="Rows" value={String(dataset.row_count)} />
              <InfoCell label={t("\u8bc6\u522b\u7c7b\u578b")} value={model?.report_domain || recognition?.detected_plot_type || dataset.data_type || "unknown"} />
              <InfoCell label="Primary Sweep" value={model?.primary_sweep || "unknown"} />
              <InfoCell label="Quantity" value={model?.quantity || "unknown"} />
              <InfoCell label={t("\u5019\u9009\u66f2\u7ebf")} value={String(candidateCount)} />
              <InfoCell label="Compatible" value={compatible.join(", ") || "unknown"} />
              <InfoCell label="Error / Warning" value={`${errorItems.length} / ${warningItems.length}`} />
            </div>

            <details className="mt-3 rounded-md border border-slate-200 bg-white p-2 text-xs dark:border-slate-800 dark:bg-slate-950">
              <summary className="cursor-pointer font-bold">{"\u9ad8\u7ea7\u4fe1\u606f"}</summary>
              <div className="mt-2 leading-5 text-slate-500 dark:text-slate-400">Columns: {dataset.columns.join(", ")}</div>
              <div className="mt-1 leading-5 text-slate-500 dark:text-slate-400">Fixed Variables / Families: {familyText}</div>
              <MessageBucket title="Errors" items={errorItems} tone="red" />
              <MessageBucket title="Warnings" items={warningItems} tone="amber" />
              <MessageBucket title="Infos" items={[...(model?.infos || [])]} tone="slate" />
            </details>
          </div>
        );
      })}
    </div>
  );
}
