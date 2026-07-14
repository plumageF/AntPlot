import type { WorkflowState } from "../types";

type Props = {
  step: number;
  title: string;
  state: WorkflowState;
  enabled: boolean;
  children: React.ReactNode;
};

export function StepCardCleanExternal({ step, title, state, enabled, children }: Props) {
  return (
    <section className={`rounded-lg border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-950 ${enabled ? "" : "opacity-55"}`}>
      <div className="mb-4 flex items-center gap-3">
        <div className="grid h-8 w-8 place-items-center rounded-md bg-indigo-600 text-sm font-bold text-white">{step}</div>
        <div>
          <div className="text-sm font-bold">{title}</div>
          <div className="text-xs text-slate-500 dark:text-slate-400">workflow: {state}</div>
        </div>
      </div>
      {enabled ? children : <div className="rounded-md border border-dashed border-slate-300 p-3 text-sm text-slate-400 dark:border-slate-700">Complete the previous step to continue.</div>}
    </section>
  );
}
