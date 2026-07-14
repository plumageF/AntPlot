import type React from "react";
import type { ProjectSettings } from "../types";

type Props = {
  selectedPlot: string;
  projectSettings: ProjectSettings;
  setProjectSettings: React.Dispatch<React.SetStateAction<ProjectSettings>>;
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

export function ProjectSettingsPanelCleanExternal({ selectedPlot, projectSettings, setProjectSettings }: Props) {
  const patch = (update: Partial<ProjectSettings>) => setProjectSettings((current) => ({ ...current, ...update }));
  const showBand = ["S11 / Return Loss", "VSWR", "Axial Ratio", "Realized Gain", "Efficiency", "HPBW"].includes(selectedPlot);
  const showS11 = selectedPlot === "S11 / Return Loss";
  const showVswr = selectedPlot === "VSWR";
  const showAr = selectedPlot === "Axial Ratio";
  const showGain = selectedPlot === "Realized Gain";

  return (
    <Panel title="Project Settings">
      <div className="grid grid-cols-2 gap-2">
        {showBand && <TextInput label={"\u5de5\u4f5c\u9891\u6bb5\u8d77\u70b9 (MHz)"} value={projectSettings.bandStartMHz} onChange={(value) => patch({ bandStartMHz: value })} />}
        {showBand && <TextInput label={"\u5de5\u4f5c\u9891\u6bb5\u7ec8\u70b9 (MHz)"} value={projectSettings.bandEndMHz} onChange={(value) => patch({ bandEndMHz: value })} />}
        {showS11 && <TextInput label={"S11 \u9608\u503c (dB)"} value={projectSettings.s11ThresholdDb} onChange={(value) => patch({ s11ThresholdDb: value })} />}
        {showVswr && <TextInput label={"VSWR \u9608\u503c"} value={projectSettings.vswrThreshold} onChange={(value) => patch({ vswrThreshold: value })} />}
        {showAr && <TextInput label={"\u8f74\u6bd4\u9608\u503c (dB)"} value={projectSettings.axialRatioThresholdDb} onChange={(value) => patch({ axialRatioThresholdDb: value })} />}
        {showGain && <TextInput label={"\u6700\u4f4e\u589e\u76ca (dBi)"} value={projectSettings.minGainDbi} onChange={(value) => patch({ minGainDbi: value })} />}
      </div>

      {!showBand && (
        <div className="rounded-md bg-slate-100 px-3 py-2 text-xs text-slate-500 dark:bg-slate-900 dark:text-slate-300">
          {"\u5f53\u524d\u56fe\u7c7b\u578b\u6ca1\u6709\u4e3b\u8981\u9879\u76ee\u9608\u503c\uff1b\u53ef\u5728\u9ad8\u7ea7\u9879\u76ee\u8bbe\u7f6e\u4e2d\u8c03\u6574\u53c2\u8003\u963b\u6297\u6216\u65b9\u5411\u56fe\u9891\u70b9\u3002"}
        </div>
      )}

      <details className="rounded-md border border-slate-200 bg-white p-3 text-xs dark:border-slate-800 dark:bg-slate-950">
        <summary className="cursor-pointer font-bold">{"\u9ad8\u7ea7\u9879\u76ee\u8bbe\u7f6e"}</summary>
        <div className="mt-3 grid grid-cols-2 gap-2">
          {!showS11 && <TextInput label={"S11 \u9608\u503c (dB)"} value={projectSettings.s11ThresholdDb} onChange={(value) => patch({ s11ThresholdDb: value })} />}
          {!showVswr && <TextInput label={"VSWR \u9608\u503c"} value={projectSettings.vswrThreshold} onChange={(value) => patch({ vswrThreshold: value })} />}
          {!showAr && <TextInput label={"\u8f74\u6bd4\u9608\u503c (dB)"} value={projectSettings.axialRatioThresholdDb} onChange={(value) => patch({ axialRatioThresholdDb: value })} />}
          {!showGain && <TextInput label={"\u6700\u4f4e\u589e\u76ca (dBi)"} value={projectSettings.minGainDbi} onChange={(value) => patch({ minGainDbi: value })} />}
          <TextInput label={"\u7aef\u53e3\u963b\u6297 (\u03a9)"} value={projectSettings.portImpedanceOhm} onChange={(value) => patch({ portImpedanceOhm: value })} />
          <TextInput label={"\u65b9\u5411\u56fe\u9891\u70b9 (MHz)"} value={projectSettings.patternFrequenciesMHz} onChange={(value) => patch({ patternFrequenciesMHz: value })} />
        </div>
        <label className="mt-3 flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300">
          <input type="checkbox" checked={projectSettings.preferRealizedGain} onChange={(event) => patch({ preferRealizedGain: event.target.checked })} className="accent-indigo-600" />
          {"\u4f18\u5148\u4f7f\u7528 Realized Gain"}
        </label>
      </details>
      <div className="text-xs leading-5 text-slate-500 dark:text-slate-400">
        {"\u82e5\u4e0d\u586b\u5199\u5de5\u4f5c\u9891\u6bb5\uff0c\u62a5\u544a\u53ea\u8f93\u51fa\u66f2\u7ebf\u6307\u6807\uff0c\u4e0d\u505a\u76ee\u6807\u9891\u6bb5\u662f\u5426\u6ee1\u8db3\u7684\u786e\u5b9a\u6027\u7ed3\u8bba\u3002"}
      </div>
    </Panel>
  );
}
