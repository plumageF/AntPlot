import { WorkflowPanelShell, type WorkflowPanelProps } from "./WorkflowPanelShell";

export function PreviewExportPanel(props: Omit<WorkflowPanelProps, "step" | "title">) {
  return <WorkflowPanelShell {...props} step={5} title="Preview and export" />;
}
