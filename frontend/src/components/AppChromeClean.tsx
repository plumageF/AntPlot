import { Activity, Moon, Settings2, Sun, type LucideIcon } from "lucide-react";
import { isFreeXYPlot } from "../plotRules";
import type { Theme, WorkflowState } from "../types";

type PlotItem = {
  name: string;
  apiType: string;
  icon: LucideIcon;
};

export function SidebarCleanExternal({
  theme,
  setTheme,
  selectedPlot,
  selectPlot,
  plots
}: {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  selectedPlot: string;
  selectPlot: (plot: string) => void;
  plots: PlotItem[];
}) {
  return (
    <aside className="sidebar">
      <div className="mb-5 flex items-center gap-3">
        <div className="antplot-logo-mark" aria-label="AntPlot logo">
          <img src="/antplot-mark.png" alt="AntPlot antenna and radiation pattern logo" />
        </div>
        <div>
          <div className="text-lg font-bold tracking-tight">AntPlot</div>
          <div className="text-xs text-slate-500 dark:text-slate-400">Antenna Plotting Studio / {"\u5929\u7ebf\u79d1\u7814\u914d\u56fe"}</div>
        </div>
      </div>
      <section className="min-h-0 flex-1 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-900/60">
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold"><Activity size={16} /> {"\u7ed8\u5236\u7c7b\u578b"}</div>
        <div className="max-h-[430px] space-y-1 overflow-y-auto pr-1">
          {plots.map((item) => {
            const Icon = item.icon;
            return (
              <button type="button" key={item.name} onClick={() => selectPlot(item.name)} className={`plot-button ${selectedPlot === item.name ? "plot-button-active" : ""}`}>
                <Icon size={16} />
                <span>{item.name}</span>
                <span className="ml-auto rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-bold text-slate-600 dark:bg-slate-700 dark:text-slate-200">
                  {isFreeXYPlot(item.name) ? "\u81ea\u7531 XY" : "\u5de5\u7a0b\u56fe"}
                </span>
              </button>
            );
          })}
        </div>
      </section>
      <section className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-900/60">
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold"><Settings2 size={16} /> {"\u57fa\u7840\u8bbe\u7f6e"}</div>
        <div className="flex items-center justify-between rounded-md bg-white px-3 py-3 text-sm dark:bg-slate-950">
          <span className="flex items-center gap-2">{theme === "dark" ? <Moon size={16} /> : <Sun size={16} />} {"\u4e3b\u9898\u8bbe\u7f6e"}</span>
          <button type="button" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} className={`flex h-7 w-12 items-center rounded-full p-1 transition ${theme === "dark" ? "bg-indigo-600" : "bg-slate-300"}`}><span className={`h-5 w-5 rounded-full bg-white transition ${theme === "dark" ? "translate-x-5" : ""}`} /></button>
        </div>
      </section>
    </aside>
  );
}

export function WorkflowHeaderCleanExternal({ state }: { state: WorkflowState }) {
  const steps = ["\u5bfc\u5165\u6570\u636e", "\u8bc6\u522b\u4e0e\u6620\u5c04", "\u66f2\u7ebf\u7ba1\u7406", "\u5355\u56fe\u8bbe\u7f6e", "\u9884\u89c8\u5bfc\u51fa"];
  return (
    <header className="border-b border-slate-200 bg-white px-5 py-4 dark:border-slate-800 dark:bg-slate-950">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <div className="text-lg font-bold">HFSS / {"\u5929\u7ebf\u79d1\u7814\u914d\u56fe\u5de5\u4f5c\u6d41"}</div>
          <div className="text-xs text-slate-500 dark:text-slate-400">{"\u5f53\u524d\u72b6\u6001"}: {state}</div>
        </div>
        <span className="rounded-full bg-indigo-100 px-3 py-1 text-xs font-bold text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-200">backend-matched preview</span>
      </div>
      <div className="grid gap-2 md:grid-cols-5">
        {steps.map((step, index) => (
          <div key={step} className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold dark:border-slate-800 dark:bg-slate-900">
            Step {index + 1}<div className="mt-1 truncate text-slate-500 dark:text-slate-400">{step}</div>
          </div>
        ))}
      </div>
    </header>
  );
}
