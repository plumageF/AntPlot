import type { Dispatch, SetStateAction } from "react";
import type { FileIndexEntry } from "../types";

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

export function FileIndexPanelCleanExternal(props: {
  files: FileIndexEntry[];
  unsupportedFiles: FileIndexEntry[];
  selectedPaths: Record<string, boolean>;
  setSelectedPaths: Dispatch<SetStateAction<Record<string, boolean>>>;
  extensionFilter: string;
  setExtensionFilter: (value: string) => void;
  dataTypeFilter: string;
  setDataTypeFilter: (value: string) => void;
  showUnsupported: boolean;
  setShowUnsupported: (value: boolean) => void;
  onImportSelected: () => void;
  onImportAllSupported: () => void;
  busy: boolean;
}) {
  const {
    files,
    unsupportedFiles,
    selectedPaths,
    setSelectedPaths,
    extensionFilter,
    setExtensionFilter,
    dataTypeFilter,
    setDataTypeFilter,
    showUnsupported,
    setShowUnsupported,
    onImportSelected,
    onImportAllSupported,
    busy
  } = props;
  if (files.length === 0 && unsupportedFiles.length === 0) return null;
  const allRows = showUnsupported ? [...files, ...unsupportedFiles] : files;
  const extensionOptions = ["all", ...Array.from(new Set(allRows.map((file) => file.extension || "none"))).sort()];
  const dataTypeOptions = ["all", ...Array.from(new Set(allRows.map((file) => file.guessed_data_type || "Unknown"))).sort()];
  const visibleRows = allRows.filter((file) => {
    const extensionOk = extensionFilter === "all" || file.extension === extensionFilter;
    const typeOk = dataTypeFilter === "all" || file.guessed_data_type === dataTypeFilter;
    return extensionOk && typeOk;
  });
  const selectedCount = files.filter((file) => file.supported && selectedPaths[file.path]).length;
  const setAllVisibleSupported = (checked: boolean) => {
    setSelectedPaths((current) => {
      const next = { ...current };
      visibleRows.forEach((file) => {
        if (file.supported) next[file.path] = checked;
      });
      return next;
    });
  };
  return (
    <section className="border-b border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-950">
      <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-900/60">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-sm font-bold">{"\u6587\u4ef6\u7d22\u5f15\u5217\u8868"}</div>
            <div className="text-xs text-slate-500 dark:text-slate-400">scan_directory {"\u53ea\u5efa\u7acb\u7d22\u5f15"}; {"\u52fe\u9009\u6587\u4ef6\u540e\u518d\u8fdb\u5165"} import_files {"\u8bc6\u522b"} Dataset.</div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => setAllVisibleSupported(true)} className="rounded-md border border-slate-300 px-3 py-2 text-xs font-semibold hover:bg-white dark:border-slate-700 dark:hover:bg-slate-950">{"\u9009\u62e9\u5f53\u524d\u652f\u6301\u6587\u4ef6"}</button>
            <button type="button" onClick={() => setAllVisibleSupported(false)} className="rounded-md border border-slate-300 px-3 py-2 text-xs font-semibold hover:bg-white dark:border-slate-700 dark:hover:bg-slate-950">{"\u53d6\u6d88\u5f53\u524d\u9009\u62e9"}</button>
            <button type="button" onClick={onImportSelected} disabled={busy || selectedCount === 0} className="rounded-md bg-emerald-600 px-3 py-2 text-xs font-bold text-white hover:bg-emerald-500 disabled:opacity-50">{"\u5bfc\u5165\u6240\u9009"} ({selectedCount})</button>
            <button type="button" onClick={onImportAllSupported} disabled={busy || files.length === 0} className="rounded-md bg-indigo-600 px-3 py-2 text-xs font-bold text-white hover:bg-indigo-500 disabled:opacity-50">{"\u4e00\u952e\u5bfc\u5165\u5168\u90e8\u652f\u6301\u6587\u4ef6"}</button>
          </div>
        </div>
        <div className="mb-3 grid gap-2 md:grid-cols-3">
          <SelectField label={"\u6309\u6587\u4ef6\u7c7b\u578b\u7b5b\u9009"} value={extensionFilter} options={extensionOptions} onChange={setExtensionFilter} />
          <SelectField label={"\u6309\u8bc6\u522b\u7c7b\u578b\u7b5b\u9009"} value={dataTypeFilter} options={dataTypeOptions} onChange={setDataTypeFilter} />
          <label className="flex items-end gap-2 rounded-md bg-white px-3 py-2 text-xs text-slate-600 dark:bg-slate-950 dark:text-slate-300">
            <input type="checkbox" checked={showUnsupported} onChange={(event) => setShowUnsupported(event.target.checked)} className="accent-indigo-600" />
            {"\u663e\u793a"} unsupported {"\u6587\u4ef6"}
          </label>
        </div>
        <div className="max-h-64 overflow-auto rounded-md border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
          <table className="w-full min-w-[900px] text-left text-xs">
            <thead className="sticky top-0 bg-slate-100 text-slate-500 dark:bg-slate-900 dark:text-slate-400">
              <tr>
                <th className="w-10 px-3 py-2">{"\u9009"}</th>
                <th className="px-3 py-2">{"\u6587\u4ef6\u540d"}</th>
                <th className="px-3 py-2">{"\u7c7b\u578b"}</th>
                <th className="px-3 py-2">{"\u521d\u6b65\u8bc6\u522b"}</th>
                <th className="px-3 py-2">{"\u6765\u6e90"}</th>
                <th className="px-3 py-2">{"\u5927\u5c0f"}</th>
                <th className="px-3 py-2">{"\u4fee\u6539\u65f6\u95f4"}</th>
                <th className="px-3 py-2">{"\u72b6\u6001"} / warning</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((file) => (
                <tr key={file.path} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="px-3 py-2">
                    <input type="checkbox" checked={Boolean(selectedPaths[file.path])} disabled={!file.supported} onChange={(event) => setSelectedPaths((current) => ({ ...current, [file.path]: event.target.checked }))} className="accent-indigo-600" />
                  </td>
                  <td className="max-w-[260px] px-3 py-2">
                    <div className="font-semibold">{file.name}</div>
                    <div className="truncate text-slate-400" title={file.path}>{file.path}</div>
                  </td>
                  <td className="px-3 py-2">{file.extension || "-"}</td>
                  <td className="px-3 py-2">{file.guessed_data_type}</td>
                  <td className="px-3 py-2">{file.guessed_source_type}</td>
                  <td className="px-3 py-2">{file.size == null ? "-" : `${(file.size / 1024).toFixed(1)} KB`}</td>
                  <td className="px-3 py-2">{file.modified_time || "-"}</td>
                  <td className="px-3 py-2">
                    <span className={`mr-2 rounded-full px-2 py-1 font-semibold ${file.supported ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-200" : "bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-300"}`}>{file.supported ? "supported" : "unsupported"}</span>
                    <span className="text-amber-600 dark:text-amber-300">{file.warnings?.length ? file.warnings.join(" | ") : ""}</span>
                  </td>
                </tr>
              ))}
              {visibleRows.length === 0 && (
                <tr><td colSpan={8} className="px-3 py-6 text-center text-slate-500">{"\u5f53\u524d\u7b5b\u9009\u6761\u4ef6\u4e0b\u6ca1\u6709\u6587\u4ef6"}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
