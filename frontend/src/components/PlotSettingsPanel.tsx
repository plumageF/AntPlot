import { WorkflowPanelShell, type WorkflowPanelProps } from "./WorkflowPanelShell";

export function PlotSettingsPanel(props: Omit<WorkflowPanelProps, "step" | "title">) {
  return <WorkflowPanelShell {...props} step={4} title="Plot settings" />;
}
