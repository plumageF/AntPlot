import { WorkflowPanelShell, type WorkflowPanelProps } from "./WorkflowPanelShell";

export function ImportPanel(props: Omit<WorkflowPanelProps, "step" | "title">) {
  return <WorkflowPanelShell {...props} step={1} title="Import data" />;
}
