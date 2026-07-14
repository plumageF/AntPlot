import type React from "react";
import type { DatasetSummary, ManualConfig, MappingCandidate } from "../types";

type Props = {
  datasets: DatasetSummary[];
  manualConfig: ManualConfig;
  setManualConfig: React.Dispatch<React.SetStateAction<ManualConfig>>;
  setCandidates: React.Dispatch<React.SetStateAction<MappingCandidate[]>>;
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

function TextInput({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="block">
      <div className="mb-1 text-xs font-semibold text-slate-500 dark:text-slate-400">{label}</div>
      <input value={value} onChange={(event) => onChange(event.target.value)} className="field" />
    </label>
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

export function ManualModePanelCleanExternal({ datasets, manualConfig, setManualConfig, setCandidates }: Props) {
  const patch = (update: Partial<ManualConfig>) => setManualConfig((current) => ({ ...current, ...update }));

  const addManualCurve = (dataset: DatasetSummary) => {
    const xColumn = manualConfig.xColumn || dataset.columns.find((column) => /freq|frequency/i.test(column)) || dataset.columns[0] || "Column 1";
    const yColumn = manualConfig.yColumn || dataset.columns.find((column) => /s11|s\(1,1\)|db/i.test(column)) || dataset.columns[1] || dataset.columns[0] || "Column 2";
    const familyColumn = manualConfig.familyColumn;
    const now = Date.now();
    const yQuantity = manualConfig.yQuantity || (manualConfig.plotType === "vswr" ? "VSWR" : manualConfig.plotType === "gain" ? "RealizedGain" : manualConfig.plotType === "ar" ? "AR" : "S11");
    const yUnit = manualConfig.yUnit || (yQuantity === "VSWR" ? "linear" : yQuantity === "RealizedGain" ? "dBi" : "dB");
    const curve: MappingCandidate = {
      curve_id: `manual_${dataset.dataset_id}_${now}`,
      dataset_id: dataset.dataset_id,
      x_column: xColumn,
      y_column: yColumn,
      x_quantity: manualConfig.xQuantity || "frequency",
      y_quantity: yQuantity,
      x_unit: manualConfig.xUnit || "GHz",
      y_unit: yUnit,
      label: manualConfig.label || yColumn || `Manual ${yQuantity}`,
      is_enabled: true,
      is_normalized: false,
      conversion: "manual mapping; no automatic physical inference",
      source_role: "Manual",
      order: 0,
      point_count: dataset.row_count,
      sample_count: dataset.sample_count ?? dataset.row_count,
      warnings: ["Manual mode: variable meaning, units, header row, delimiter, threshold and target band are user supplied."],
      metadata: {
        source_file: dataset.source_file,
        manual_confirmed: true,
        manual_config: { ...manualConfig, xColumn, yColumn, familyColumn, xQuantity: manualConfig.xQuantity || "frequency", yQuantity, xUnit: manualConfig.xUnit || "GHz", yUnit }
      },
      selected: true,
      original_x_column: "",
      original_y_column: "",
      original_x_unit: "",
      original_y_unit: "",
      original_y_quantity: ""
    };
    setCandidates((current) => [...current, curve]);
  };

  return (
    <Panel title={"\u9ad8\u7ea7\u624b\u52a8\u8986\u76d6"}>
      <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800 dark:border-amber-400/40 dark:bg-amber-400/10 dark:text-amber-100">
        {"\u624b\u52a8\u6a21\u5f0f\u4e0d\u4f1a\u63a8\u65ad\u7269\u7406\u610f\u4e49\u3002\u53ef\u4ee5\u751f\u6210\u4e34\u65f6\u9884\u89c8\uff0c\u4f46\u62a5\u544a\u548c JSON \u4f1a\u4fdd\u7559\u624b\u52a8\u786e\u8ba4\u6807\u8bb0\u3002"}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <TextInput label={"\u6570\u636e\u8868\u5934\u884c"} value={manualConfig.headerRow} onChange={(value) => patch({ headerRow: value })} />
        <SelectField label={"\u5206\u9694\u7b26"} value={manualConfig.delimiter} options={["auto", "comma", "semicolon", "tab", "space"]} onChange={(value) => patch({ delimiter: value })} />
        <SelectField label={"\u56fe\u7c7b\u578b"} value={manualConfig.plotType} options={["s11", "vswr", "gain", "ar", "efficiency", "pattern", "auto"]} onChange={(value) => patch({ plotType: value })} />
        <TextInput label={"\u66f2\u7ebf\u6807\u7b7e"} value={manualConfig.label} onChange={(value) => patch({ label: value })} />
        <SelectField label={"\u0058 \u8f74\u7269\u7406\u91cf"} value={manualConfig.xQuantity} options={xQuantities} onChange={(value) => patch({ xQuantity: value })} />
        <SelectField label={"\u0059 \u8f74\u7269\u7406\u91cf"} value={manualConfig.yQuantity} options={quantities} onChange={(value) => patch({ yQuantity: value })} />
        <SelectField label={"\u0058 \u8f74\u5355\u4f4d"} value={manualConfig.xUnit} options={units} onChange={(value) => patch({ xUnit: value })} />
        <SelectField label={"\u0059 \u8f74\u5355\u4f4d"} value={manualConfig.yUnit} options={units} onChange={(value) => patch({ yUnit: value })} />
        <TextInput label={"\u9608\u503c\u7ebf\u6570\u503c"} value={manualConfig.threshold} onChange={(value) => patch({ threshold: value })} />
        <TextInput label={"\u76ee\u6807\u9891\u6bb5\u4f4e\u7aef (MHz)"} value={manualConfig.targetBandMin} onChange={(value) => patch({ targetBandMin: value })} />
        <TextInput label={"\u76ee\u6807\u9891\u6bb5\u9ad8\u7aef (MHz)"} value={manualConfig.targetBandMax} onChange={(value) => patch({ targetBandMax: value })} />
      </div>
      <label className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300">
        <input type="checkbox" checked={manualConfig.drawThreshold} onChange={(event) => patch({ drawThreshold: event.target.checked })} className="accent-indigo-600" />
        {"\u7ed8\u5236\u9608\u503c\u7ebf"}
      </label>
      <div className="space-y-2">
        {datasets.length === 0 ? (
          <div className="text-xs text-slate-500">{"\u5148\u5bfc\u5165\u6587\u4ef6\uff0c\u518d\u6dfb\u52a0\u624b\u52a8\u66f2\u7ebf\u6620\u5c04\u3002"}</div>
        ) : datasets.map((dataset) => {
          const defaultX = manualConfig.xColumn || dataset.columns.find((column) => /freq|frequency/i.test(column)) || dataset.columns[0] || "";
          const defaultY = manualConfig.yColumn || dataset.columns.find((column) => /s11|s\(1,1\)|db/i.test(column)) || dataset.columns[1] || dataset.columns[0] || "";
          return (
            <div key={dataset.dataset_id} className="rounded-md border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-950">
              <div className="mb-2 truncate text-xs font-bold" title={dataset.source_file}>{dataset.source_file}</div>
              <div className="grid grid-cols-2 gap-2">
                <SelectField label={"\u0058 \u5217"} value={defaultX} options={dataset.columns} onChange={(value) => patch({ xColumn: value })} />
                <SelectField label={"\u0059 \u5217"} value={defaultY} options={dataset.columns} onChange={(value) => patch({ yColumn: value })} />
                <SelectField label={"\u5206\u7ec4\u5217 / \u5207\u9762\u5217\uff08\u53ef\u9009\uff09"} value={manualConfig.familyColumn} options={["", ...dataset.columns]} onChange={(value) => patch({ familyColumn: value })} />
              </div>
              <div className="mt-2 text-[11px] leading-5 text-slate-500 dark:text-slate-400">
                {"\u5982\u679c\u540c\u4e00\u4e2a\u89d2\u5ea6\u4e0b\u6709 Phi = 0 / 90 \u6216\u591a\u4e2a\u9891\u70b9\uff0c\u8bf7\u9009\u62e9\u5bf9\u5e94\u5206\u7ec4\u5217\uff0c\u7cfb\u7edf\u4f1a\u62c6\u6210\u591a\u6761 Curve\u3002"}
              </div>
              <button type="button" onClick={() => addManualCurve(dataset)} disabled={dataset.columns.length === 0} className="mt-3 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-left text-xs font-semibold hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-950 dark:hover:bg-slate-900">
                {"\u6dfb\u52a0\u624b\u52a8\u66f2\u7ebf"}: X={defaultX || "-"}, Y={defaultY || "-"}{manualConfig.familyColumn ? `, family=${manualConfig.familyColumn}` : ""}
              </button>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}
