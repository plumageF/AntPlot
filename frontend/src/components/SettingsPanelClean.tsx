import type React from "react";
import type { ApiMessage, AxisConfig, AxisLabelMode, PatternConfig, RangeMode } from "../types";

type Props = {
  selectedPlot: string;
  axisConfig: AxisConfig;
  setAxisConfig: React.Dispatch<React.SetStateAction<AxisConfig>>;
  patternConfig: PatternConfig;
  setPatternConfig: React.Dispatch<React.SetStateAction<PatternConfig>>;
  messages: ApiMessage[];
  onPreview: () => void;
  onExport: () => void;
  busy: boolean;
};

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-900/60">
      <div className="mb-3 text-sm font-bold">{title}</div>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function Control({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <div className="mb-1 text-xs font-semibold text-slate-500 dark:text-slate-400">{label}</div>
      {children}
    </label>
  );
}

function TextInput({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <Control label={label}>
      <input value={value} onChange={(event) => onChange(event.target.value)} className="field" />
    </Control>
  );
}

function SelectField({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  const list = options.includes(value) ? options : [value, ...options];
  return (
    <Control label={label}>
      <select value={value} onChange={(event) => onChange(event.target.value)} className="field h-8 text-xs">
        {list.map((option) => <option key={option} value={option}>{option}</option>)}
      </select>
    </Control>
  );
}

function MessageLine({ message }: { message: ApiMessage }) {
  const severity = message.severity || (message.code.toLowerCase().includes("error") ? "error" : message.code.toLowerCase().includes("warn") ? "warning" : "info");
  const tone = severity === "error" ? "border-red-300 bg-red-50 text-red-700 dark:border-red-400/40 dark:bg-red-400/10 dark:text-red-100" : severity === "warning" ? "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-400/40 dark:bg-amber-400/10 dark:text-amber-100" : "bg-slate-100 text-slate-700 dark:bg-slate-900 dark:text-slate-200";
  return (
    <div className={`rounded-md border border-transparent px-3 py-2 text-xs leading-5 ${tone}`}>
      <span className="font-semibold">{message.code}</span>: {message.message}
    </div>
  );
}

export function SettingsPanelCleanExternal({ selectedPlot, axisConfig, setAxisConfig, patternConfig, setPatternConfig, messages }: Props) {
  const patchAxis = (patch: Partial<AxisConfig>) => setAxisConfig((current) => ({ ...current, ...patch }));
  const patchPattern = (patch: Partial<PatternConfig>) => setPatternConfig((current) => ({ ...current, ...patch }));
  const isPolarPattern = selectedPlot === "Radiation Pattern" && patternConfig.displayMode === "polar";

  return (
    <>
      <div className="mb-4">
        <div className="text-sm font-semibold text-slate-500 dark:text-slate-400">{"\u5f53\u524d\u7ed8\u56fe\u7c7b\u578b"}</div>
        <div className="mt-1 text-xl font-bold">{selectedPlot}</div>
      </div>

      <Panel title={"\u5355\u56fe\u8bbe\u7f6e"}>
        {selectedPlot === "Radiation Pattern" && (
          <div className="rounded-md border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-950">
            <div className="mb-3 text-sm font-bold">Radiation Pattern Display</div>
            <SelectField label={"\u663e\u793a\u6a21\u5f0f / Display Mode"} value={patternConfig.displayMode} options={["cartesian", "polar"]} onChange={(value) => patchPattern({ displayMode: value as "cartesian" | "polar" })} />
            {patternConfig.displayMode === "polar" && (
              <>
                <div className="grid grid-cols-2 gap-2">
                  <SelectField label="polar style" value={patternConfig.polarStyle} options={["paper", "hfss_like"]} onChange={(value) => patchPattern({ polarStyle: value as "paper" | "hfss_like", angleLabelMode: value === "hfss_like" ? "minus180_180" : patternConfig.angleLabelMode })} />
                  <SelectField label="angle labels" value={patternConfig.angleLabelMode} options={["0_360", "minus180_180"]} onChange={(value) => patchPattern({ angleLabelMode: value as "0_360" | "minus180_180" })} />
                  <TextInput label="r min" value={patternConfig.rMin} onChange={(value) => patchPattern({ rMin: value })} />
                  <TextInput label="r max" value={patternConfig.rMax} onChange={(value) => patchPattern({ rMax: value })} />
                  <SelectField label="0 deg location" value={patternConfig.thetaZeroLocation} options={["N", "E", "S", "W"]} onChange={(value) => patchPattern({ thetaZeroLocation: value })} />
                  <SelectField label="angle direction" value={patternConfig.thetaDirection} options={["-1", "1"]} onChange={(value) => patchPattern({ thetaDirection: value })} />
                  <SelectField label="legend location" value={patternConfig.legendLoc} options={["best", "upper right", "upper left", "lower right", "lower left"]} onChange={(value) => patchPattern({ legendLoc: value })} />
                </div>
                <label className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300">
                  <input type="checkbox" checked={patternConfig.normalize} onChange={(event) => patchPattern({ normalize: event.target.checked })} className="accent-indigo-600" />
                  Normalize each curve to 0 dB max
                </label>
                <label className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300">
                  <input type="checkbox" checked={patternConfig.clipBelowRMin} onChange={(event) => patchPattern({ clipBelowRMin: event.target.checked })} className="accent-indigo-600" />
                  Clip display values below r min
                </label>
              </>
            )}
          </div>
        )}

        {!isPolarPattern && (
          <>
            <Control label={"\u8303\u56f4\u6a21\u5f0f"}>
              <select value={axisConfig.rangeMode} onChange={(event) => patchAxis({ rangeMode: event.target.value as RangeMode })} className="field">
                <option value="auto">{"\u81ea\u52a8\u8303\u56f4"}</option>
                <option value="manual">{"\u624b\u52a8\u8303\u56f4"}</option>
              </select>
            </Control>
            <Control label={"\u8f74\u6807\u9898\u6a21\u5f0f"}>
              <select value={axisConfig.labelMode} onChange={(event) => patchAxis({ labelMode: event.target.value as AxisLabelMode })} className="field">
                <option value="auto">{"\u81ea\u52a8\uff1a\u540e\u7aef\u6839\u636e Curve \u751f\u6210"}</option>
                <option value="manual">{"\u624b\u52a8\uff1a\u4f7f\u7528\u4e0b\u9762\u6807\u9898"}</option>
              </select>
            </Control>
            {axisConfig.labelMode === "manual" && (
              <>
                <TextInput label={"\u6a2a\u8f74\u6807\u9898"} value={axisConfig.xLabel} onChange={(value) => patchAxis({ xLabel: value })} />
                <TextInput label={"\u7eb5\u8f74\u6807\u9898"} value={axisConfig.yLabel} onChange={(value) => patchAxis({ yLabel: value })} />
              </>
            )}
            <div className="grid grid-cols-2 gap-2">
              <TextInput label="X min" value={axisConfig.xMin} onChange={(value) => patchAxis({ xMin: value })} />
              <TextInput label="X max" value={axisConfig.xMax} onChange={(value) => patchAxis({ xMax: value })} />
              <TextInput label="Y min" value={axisConfig.yMin} onChange={(value) => patchAxis({ yMin: value })} />
              <TextInput label="Y max" value={axisConfig.yMax} onChange={(value) => patchAxis({ yMax: value })} />
            </div>
            <div className="rounded-md border border-indigo-200 bg-indigo-50/40 p-3 text-xs dark:border-indigo-500/30 dark:bg-indigo-500/10">
              <div className="mb-3 font-bold text-slate-800 dark:text-slate-100">{"\u5750\u6807\u523b\u5ea6\u4e0e\u56fe\u5185\u8bf4\u660e"}</div>
              <div className="grid grid-cols-2 gap-2">
                <TextInput label={"\u0058 \u4e3b\u523b\u5ea6\u95f4\u9694"} value={axisConfig.xTickMajor} onChange={(value) => patchAxis({ xTickMajor: value })} />
                <TextInput label={"\u0059 \u4e3b\u523b\u5ea6\u95f4\u9694"} value={axisConfig.yTickMajor} onChange={(value) => patchAxis({ yTickMajor: value })} />
                <TextInput label={"\u0058 \u6b21\u523b\u5ea6\u95f4\u9694"} value={axisConfig.xTickMinor} onChange={(value) => patchAxis({ xTickMinor: value })} />
                <TextInput label={"\u0059 \u6b21\u523b\u5ea6\u95f4\u9694"} value={axisConfig.yTickMinor} onChange={(value) => patchAxis({ yTickMinor: value })} />
              </div>
              <label className="mt-3 flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300">
                <input type="checkbox" checked={axisConfig.gridEnabled} onChange={(event) => patchAxis({ gridEnabled: event.target.checked })} className="accent-indigo-600" />
                {"\u663e\u793a\u7f51\u683c\u7ebf"}
              </label>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <TextInput label={"\u56fe\u5185\u8bf4\u660e\u6587\u5b57"} value={axisConfig.noteText} onChange={(value) => patchAxis({ noteText: value })} />
                <div className="grid grid-cols-2 gap-2">
                  <TextInput label={"\u8bf4\u660e X(0-1)"} value={axisConfig.noteX} onChange={(value) => patchAxis({ noteX: value })} />
                  <TextInput label={"\u8bf4\u660e Y(0-1)"} value={axisConfig.noteY} onChange={(value) => patchAxis({ noteY: value })} />
                </div>
              </div>
              <div className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">
                {"\u8bf4\u660e\u4f4d\u7f6e\u91c7\u7528\u56fe\u5185\u6bd4\u4f8b\u5750\u6807\uff1a0.05, 0.95 \u8868\u793a\u5de6\u4e0a\u89d2\uff1b0.65, 0.20 \u8868\u793a\u53f3\u4e0b\u533a\u57df\u3002"}
              </div>
            </div>
          </>
        )}
      </Panel>

      <Panel title={"\u6d88\u606f"}>
        {messages.length === 0 ? (
          <div className="text-xs text-slate-500">{"\u6682\u65e0\u9519\u8bef\u6216\u8b66\u544a\u3002"}</div>
        ) : (
          <div className="space-y-2">{messages.slice(0, 8).map((message, index) => <MessageLine key={`${message.code}-${index}`} message={message} />)}</div>
        )}
      </Panel>
    </>
  );
}
