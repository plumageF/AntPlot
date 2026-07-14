import { WorkflowPanelShell, type WorkflowPanelProps } from "./WorkflowPanelShell";

export function CurveManagerPanel(props: Omit<WorkflowPanelProps, "step" | "title">) {
  return <WorkflowPanelShell {...props} step={3} title="Curve manager" />;
}
