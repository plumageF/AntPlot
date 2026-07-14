import type React from "react";
import { Upload } from "lucide-react";
import type { ExportConfig } from "../types";

type Props = {
  exportConfig: ExportConfig;
  setExportConfig: React.Dispatch<React.SetStateAction<ExportConfig>>;
  onExport: () => void;
  busy: boolean;
  hasErrors: boolean;
  onErrorClick: () => void;
};

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-900/60">
      <div className="mb-3 text-sm font-bold">{title}</div>
      <div className="space-y-3">{children}</div>
    </div>
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

function SelectField({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  return (
    <label className="block">
      <div className="mb-1 text-xs font-semibold text-slate-500 dark:text-slate-400">{label}</div>
      <select value={value} onChange={(event) => onChange(event.target.value)} className="field h-8 text-xs">
        {options.map((option) => <option key={option} value={option}>{option}</option>)}
      </select>
    </label>
  );
}

function CheckItem({ id, label, checked, onChange, danger = false }: { id?: string; label: string; checked: boolean; onChange: (value: boolean) => void; danger?: boolean }) {
  return (
    <label id={id} className={`flex items-center gap-2 rounded-md border px-2 py-2 transition-shadow ${danger ? "border-red-400 bg-red-50 text-red-700 dark:border-red-400/60 dark:bg-red-400/10 dark:text-red-100" : "border-transparent bg-slate-100 dark:bg-slate-900"}`}>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} className="accent-indigo-600" />
      {label}
    </label>
  );
}

export function ExportPanelCleanExternal({ exportConfig, setExportConfig, onExport, busy, hasErrors, onErrorClick }: Props) {
  const patch = (update: Partial<ExportConfig>) => setExportConfig((current) => ({ ...current, ...update }));
  const reportBlocked = hasErrors && (exportConfig.txt || exportConfig.md);

  return (
    <Panel title={"\u5bfc\u51fa\u8bbe\u7f6e"}>
      <TextInput label={"\u8f93\u51fa\u76ee\u5f55"} value={exportConfig.outputDir} onChange={(value) => patch({ outputDir: value })} />
      <TextInput label={"\u6587\u4ef6\u540d\u524d\u7f00"} value={exportConfig.filePrefix} onChange={(value) => patch({ filePrefix: value })} />
      <div className="grid grid-cols-2 gap-2">
        <TextInput label="PNG dpi" value={exportConfig.dpi} onChange={(value) => patch({ dpi: value })} />
        <SelectField label={"\u5bfc\u51fa\u8303\u56f4"} value={exportConfig.scope} options={["current", "all"]} onChange={(value) => patch({ scope: value as "current" | "all" })} />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <CheckItem label="PNG" checked={exportConfig.png} onChange={(value) => patch({ png: value })} />
        <CheckItem label="PDF" checked={exportConfig.pdf} onChange={(value) => patch({ pdf: value })} />
        <CheckItem label="SVG" checked={exportConfig.svg} onChange={(value) => patch({ svg: value })} />
        <CheckItem label={"JSON \u914d\u7f6e"} checked={exportConfig.json} onChange={(value) => patch({ json: value })} />
        <CheckItem id="export-report-options" label={"TXT \u62a5\u544a"} checked={exportConfig.txt} onChange={(value) => patch({ txt: value })} danger={hasErrors && exportConfig.txt} />
        <CheckItem label={"Markdown \u62a5\u544a"} checked={exportConfig.md} onChange={(value) => patch({ md: value })} danger={hasErrors && exportConfig.md} />
      </div>

      {reportBlocked && (
        <button type="button" onClick={onErrorClick} title={"\u70b9\u51fb\u5b9a\u4f4d\u5230\u9700\u8981\u5904\u7406\u7684\u9519\u8bef\u533a\u57df"} className="w-full rounded-md border border-red-300 bg-red-50 px-3 py-2 text-left text-xs leading-5 text-red-700 transition hover:border-red-400 hover:bg-red-100 dark:border-red-400/40 dark:bg-red-400/10 dark:text-red-100 dark:hover:bg-red-400/20">
          {"\u5f53\u524d\u5b58\u5728 Error\uff1a\u53ef\u4ee5\u5bfc\u51fa\u8c03\u8bd5\u56fe\uff0c\u4f46\u4e0d\u5e94\u8f93\u51fa\u786e\u5b9a\u6027\u5de5\u7a0b\u7ed3\u8bba\u62a5\u544a\u3002\u8bf7\u5173\u95ed TXT/Markdown \u62a5\u544a\u6216\u5148\u4fee\u590d\u9519\u8bef\u3002"}
        </button>
      )}
      {reportBlocked && (
        <button type="button" onClick={() => patch({ txt: false, md: false })} className="rounded-md border border-red-300 bg-white px-3 py-2 text-xs font-semibold text-red-700 hover:bg-red-50 dark:border-red-400/40 dark:bg-slate-950 dark:text-red-100 dark:hover:bg-red-400/10">
          {"\u4e00\u952e\u5173\u95ed TXT / Markdown \u62a5\u544a"}
        </button>
      )}
      <button type="button" onClick={onExport} disabled={busy} className="flex w-full items-center justify-center gap-2 rounded-md bg-indigo-600 px-3 py-2 text-sm font-bold text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50">
        <Upload size={16} />{"\u6309\u5f53\u524d\u8bbe\u7f6e\u5bfc\u51fa"}
      </button>
    </Panel>
  );
}
