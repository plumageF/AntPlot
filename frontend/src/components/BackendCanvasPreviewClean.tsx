import type { ApiMessage, PreviewResult, Theme } from "../types";

type Props = {
  theme: Theme;
  previewResult: PreviewResult;
  selectedPlot: string;
  enabledCount: number;
  messages: ApiMessage[];
};

function InfoCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <div className="mb-1 font-semibold text-slate-400">{label}</div>
      <div className="truncate rounded-md bg-slate-100 px-2 py-1 dark:bg-slate-900" title={value}>{value}</div>
    </div>
  );
}

function BackendImagePreview({ imageUrl, report, outputs }: { imageUrl: string; report: string | null; outputs: string[] }) {
  return (
    <div className="flex h-full min-h-0 flex-col gap-3 p-5">
      <div className="min-h-0 flex-1 rounded-md bg-white p-4 shadow-sm">
        <img src={imageUrl} alt="backend generated preview" className="h-full w-full object-contain" />
      </div>
      {report && <pre className="max-h-32 overflow-auto rounded-md bg-slate-950/90 p-3 text-xs leading-5 text-slate-100">{report}</pre>}
      {outputs.length > 0 && (
        <div className="rounded-md bg-slate-100 p-2 text-xs text-slate-600 dark:bg-slate-900 dark:text-slate-300">
          {outputs.slice(0, 4).map((output) => <div key={output} className="truncate">{output}</div>)}
        </div>
      )}
    </div>
  );
}

function BackendPreviewPlaceholder({ status, error }: { status: string; error: string | null }) {
  return (
    <div className="grid h-full place-items-center p-8">
      <div className="max-w-lg rounded-md border border-emerald-300 bg-emerald-50 px-4 py-3 text-sm leading-6 text-emerald-800 shadow-sm dark:border-emerald-400/40 dark:bg-emerald-400/10 dark:text-emerald-100">
        {status}
        {error && <div className="mt-2 text-red-600 dark:text-red-200">{error}</div>}
      </div>
    </div>
  );
}

export function BackendCanvasPreviewCleanExternal({ theme, previewResult, selectedPlot, enabledCount, messages }: Props) {
  const gridColor = theme === "dark" ? "rgba(255,255,255,.11)" : "rgba(148,163,184,.34)";
  const background = theme === "dark" ? "#000000" : "#ffffff";
  const errorCount = messages.filter((message) => message.severity === "error" || message.code.toLowerCase().includes("error")).length + (previewResult.error ? 1 : 0);
  const warningCount = messages.filter((message) => message.severity === "warning" || message.code.toLowerCase().includes("warning") || message.code.toLowerCase().includes("warn")).length;

  return (
    <section id="backend-preview-panel" className="canvas-panel rounded-lg border border-slate-200 bg-white transition-shadow dark:border-slate-800 dark:bg-slate-950">
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <div>
          <div className="text-sm font-bold">{"\u753b\u5e03\u9884\u89c8"}</div>
          <div className="text-xs text-slate-500 dark:text-slate-400">{"\u53ea\u663e\u793a\u540e\u7aef Python \u751f\u6210\u7684\u4e34\u65f6\u56fe\u7247"}</div>
        </div>
        <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-200">backend matched</span>
      </div>
      <div className="grid grid-cols-4 gap-2 border-b border-slate-200 px-4 py-3 text-xs dark:border-slate-800">
        <InfoCell label={"\u5f53\u524d\u56fe\u7c7b\u578b"} value={selectedPlot} />
        <InfoCell label={"\u542f\u7528\u66f2\u7ebf"} value={`${enabledCount}`} />
        <InfoCell label="Warnings" value={`${warningCount}`} />
        <InfoCell label="Errors" value={`${errorCount}`} />
      </div>
      <div className="canvas-body" style={{ backgroundColor: background, backgroundImage: `linear-gradient(${gridColor} 1px, transparent 1px), linear-gradient(90deg, ${gridColor} 1px, transparent 1px)`, backgroundSize: "24px 24px" }}>
        {previewResult.imageUrl ? <BackendImagePreview imageUrl={previewResult.imageUrl} report={previewResult.report} outputs={previewResult.outputs} /> : <BackendPreviewPlaceholder status={previewResult.status} error={previewResult.error} />}
      </div>
    </section>
  );
}
