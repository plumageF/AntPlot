import { WorkflowPanelShell, type WorkflowPanelProps } from "./WorkflowPanelShell";

export function MappingPanel(props: Omit<WorkflowPanelProps, "step" | "title">) {
  return <WorkflowPanelShell {...props} step={2} title="Recognition and mapping" />;
}
