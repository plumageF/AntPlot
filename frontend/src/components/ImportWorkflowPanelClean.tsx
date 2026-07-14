import { FileInput, FolderOpen, Upload } from "lucide-react";
import { isFreeXYPlot, workflowModeForPlot } from "../plotRules";
import type { OperationMode } from "../types";
import { useState, type ReactNode } from "react";

function Control({ label, children }: { label: string; children: ReactNode }) {
  return <label className="block"><div className="mb-1 text-xs font-semibold text-slate-500 dark:text-slate-400">{label}</div>{children}</label>;
}

function PathField({
  label,
  value,
  onChange,
  button,
  icon,
  onAction,
  busy
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  button: string;
  icon: ReactNode;
  onAction?: () => void;
  busy?: boolean;
}) {
  return (
    <label className="min-w-0">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</div>
      <div className="flex gap-2">
        <input value={value} onChange={(event) => onChange(event.target.value)} className="min-w-0 flex-1 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm outline-none dark:border-slate-800 dark:bg-slate-900" />
        <button type="button" onClick={onAction} disabled={!onAction || busy} className="flex items-center gap-2 rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50">{icon}{button}</button>
      </div>
    </label>
  );
}

export function ImportWorkflowPanelCleanExternal(props: {
  selectedPlot: string;
  operationMode: OperationMode;
  setOperationMode: (value: OperationMode) => void;
  singleFilePath: string;
  setSingleFilePath: (value: string) => void;
  multiFilePaths: string;
  setMultiFilePaths: (value: string) => void;
  directoryPath: string;
  setDirectoryPath: (value: string) => void;
  recursiveScan: boolean;
  setRecursiveScan: (value: boolean) => void;
  configPath: string;
  setConfigPath: (value: string) => void;
  onImportSingle: () => void;
  onImportMultiple: () => void;
  onScanDirectory: () => void;
  onRestore: () => void;
  busy: boolean;
}) {
  const [activeTab, setActiveTab] = useState<"files" | "folder" | "json">("files");
  const isXY = isFreeXYPlot(props.selectedPlot);
  const tabClass = (tab: "files" | "folder" | "json") => `rounded-md px-3 py-2 text-xs font-bold ${activeTab === tab ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"}`;
  return (
    <div className="space-y-3">
      <div className="grid gap-2 md:grid-cols-[1fr_auto]">
        <div className="flex flex-wrap gap-2">
          <button type="button" className={tabClass("files")} onClick={() => setActiveTab("files")}>{"\u5355\u6587\u4ef6 / \u591a\u6587\u4ef6"}</button>
          <button type="button" className={tabClass("folder")} onClick={() => setActiveTab("folder")}>{"\u6587\u4ef6\u5939\u626b\u63cf"}</button>
          <button type="button" className={tabClass("json")} onClick={() => setActiveTab("json")}>{"\u6062\u590d JSON \u9879\u76ee"}</button>
        </div>
        <Control label={isXY ? "\u81ea\u7531 XY \u5bfc\u5165\u65b9\u5f0f" : "\u5de5\u7a0b\u56fe\u5bfc\u5165\u7b56\u7565"}>
          <select value={workflowModeForPlot(props.selectedPlot, props.operationMode)} onChange={(event) => props.setOperationMode(event.target.value as OperationMode)} className="field h-9 min-w-56">
            {isXY ? (
              <option value="manual">{"\u624b\u52a8\uff1a\u6807\u51c6 XY \u5bbd\u8868"}</option>
            ) : (
              <>
                <option value="auto">{"\u81ea\u52a8\uff1a\u8bc6\u522b\u660e\u786e\u65f6\u76f4\u63a5\u751f\u6210\u66f2\u7ebf"}</option>
                <option value="semiauto">{"\u534a\u81ea\u52a8\uff1a\u663e\u793a\u5efa\u8bae\uff0c\u7528\u6237\u786e\u8ba4"}</option>
              </>
            )}
          </select>
        </Control>
      </div>
      {activeTab === "files" && (
        <div className="grid gap-3 xl:grid-cols-2">
          <PathField label={"\u5355\u4e2a CSV / TXT \u6587\u4ef6\u8def\u5f84"} value={props.singleFilePath} onChange={props.setSingleFilePath} button={"\u5bfc\u5165\u5e76\u8bc6\u522b"} icon={<FileInput size={17} />} onAction={props.onImportSingle} busy={props.busy} />
          <label className="min-w-0">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{"\u591a\u4e2a\u6587\u4ef6\u8def\u5f84"}</div>
            <textarea value={props.multiFilePaths} onChange={(event) => props.setMultiFilePaths(event.target.value)} placeholder={"\u6bcf\u884c\u4e00\u4e2a\u8def\u5f84\uff0c\u6216\u7528 ; \u5206\u9694"} className="h-[42px] min-w-0 w-full resize-none rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm outline-none dark:border-slate-800 dark:bg-slate-900" />
            <button type="button" onClick={props.onImportMultiple} disabled={props.busy || !props.multiFilePaths.trim()} className="mt-2 flex w-full items-center justify-center gap-2 rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"><FileInput size={16} />{"\u5bfc\u5165\u591a\u4e2a\u6587\u4ef6"}</button>
          </label>
        </div>
      )}
      {activeTab === "folder" && (
        <div>
          <PathField label={"\u6587\u4ef6\u5939\u8def\u5f84"} value={props.directoryPath} onChange={props.setDirectoryPath} button={"\u626b\u63cf\u6587\u4ef6\u5939"} icon={<FolderOpen size={17} />} onAction={props.onScanDirectory} busy={props.busy} />
          <label className="mt-2 flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300">
            <input type="checkbox" checked={props.recursiveScan} onChange={(event) => props.setRecursiveScan(event.target.checked)} className="accent-indigo-600" />
            {"\u9012\u5f52\u626b\u63cf\u5b50\u6587\u4ef6\u5939"}
          </label>
        </div>
      )}
      {activeTab === "json" && (
        <div>
          <PathField label={"\u5bfc\u5165 JSON \u914d\u7f6e"} value={props.configPath} onChange={props.setConfigPath} button={"\u6062\u590d\u9879\u76ee"} icon={<Upload size={17} />} onAction={props.onRestore} busy={props.busy} />
          <div className="mt-2 text-xs text-slate-500 dark:text-slate-400">{"\u652f\u6301\u6062\u590d Dataset\u3001Curve\u3001Project Settings\u3001\u56fe\u7c7b\u578b\u4e0e\u5bfc\u51fa\u8bbe\u7f6e\u3002"}</div>
        </div>
      )}
    </div>
  );
}
