"""Report assembly with structured messages."""

from __future__ import annotations

from .audit import AuditReport, format_audit
from .engineering_metrics import MetricResult, collect_metric_messages, format_metric_results
from .messages import Message, format_messages


def collect_report_messages(audit: AuditReport, metrics: list[MetricResult]) -> list[Message]:
    messages: list[Message] = []
    messages.extend(audit.messages)
    messages.extend(collect_metric_messages(metrics))
    if not any(message.code == "export_vector_recommended" for message in messages):
        messages.append(Message("info", "export_vector_recommended", "建议导出 PDF/SVG 用于论文排版和矢量编辑。", {}))
    if not any(message.code == "realized_gain_recommended" for message in messages):
        messages.append(Message("info", "realized_gain_recommended", "建议优先使用 Realized Gain 反映端口失配后的实际工作性能。", {}))
    return messages


def has_errors(messages: list[Message]) -> bool:
    return any(message.severity == "error" for message in messages)


def assemble_report(audit: AuditReport, project_text: str, metrics: list[MetricResult]) -> tuple[str, list[Message]]:
    messages = collect_report_messages(audit, metrics)
    parts = [format_messages(messages), format_audit(audit)]
    if has_errors(messages):
        parts.append("Project settings:\n- ERROR present: deterministic engineering conclusions are disabled.")
    else:
        parts.append(project_text)
    parts.append(format_metric_results(metrics))
    return "\n\n".join(parts), messages
