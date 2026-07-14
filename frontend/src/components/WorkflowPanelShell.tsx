import type { ReactNode } from "react";
import type { WorkflowState } from "../types";

export type WorkflowPanelProps = {
  step: number;
  title: string;
  state: WorkflowState;
  enabled: boolean;
  children: ReactNode;
};

export function WorkflowPanelShell({ step, title, state, enabled, children }: WorkflowPanelProps) {
  return (
    <section id={`workflow-step-${step}`} className={`rounded-lg border p-4 transition-shadow ${enabled ? "border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950" : "border-slate-200 bg-slate-100 opacity-70 dark:border-slate-800 dark:bg-slate-900"}`}>
      <div className="mb-3 flex items-center gap-3">
        <span className="grid h-8 w-8 place-items-center rounded-md bg-indigo-600 text-sm font-bold text-white">{step}</span>
        <div>
          <div className="text-sm font-bold">{title}</div>
          <div className="text-xs text-slate-500 dark:text-slate-400">workflow: {state}</div>
        </div>
      </div>
      {enabled ? <div className="space-y-3">{children}</div> : <div className="rounded-md border border-dashed border-slate-300 p-3 text-sm text-slate-500 dark:border-slate-700">Complete the previous step to continue.</div>}
    </section>
  );
}
