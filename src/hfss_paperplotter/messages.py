"""Structured Error / Warning / Info messages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Severity = Literal["error", "warning", "info"]


@dataclass
class Message:
    severity: Severity
    code: str
    text: str
    context: dict[str, object] = field(default_factory=dict)


@dataclass
class MessageBundle:
    messages: list[Message] = field(default_factory=list)

    def add(self, severity: Severity, code: str, text: str, **context: object) -> None:
        self.messages.append(Message(severity, code, text, context))

    def error(self, code: str, text: str, **context: object) -> None:
        self.add("error", code, text, **context)

    def warning(self, code: str, text: str, **context: object) -> None:
        self.add("warning", code, text, **context)

    def info(self, code: str, text: str, **context: object) -> None:
        self.add("info", code, text, **context)

    @property
    def has_errors(self) -> bool:
        return any(message.severity == "error" for message in self.messages)

    @property
    def has_warnings(self) -> bool:
        return any(message.severity == "warning" for message in self.messages)

    def extend(self, messages: list[Message]) -> None:
        self.messages.extend(messages)

    def as_dicts(self) -> list[dict[str, object]]:
        return [
            {
                "severity": message.severity,
                "code": message.code,
                "text": message.text,
                "context": message.context,
            }
            for message in self.messages
        ]


def message_from_text(severity: Severity, text: str, *, code: str | None = None) -> Message:
    normalized = text.lower()
    inferred = code
    if inferred is None:
        if "frequency unit" in normalized or "频率" in text and "单位" in text:
            inferred = "frequency_unit_unconfirmed"
        elif "port" in normalized or "端口" in text:
            inferred = "port_reference_unconfirmed"
        elif "cut plane" in normalized or "切面" in text:
            inferred = "pattern_cut_unconfirmed"
        elif "cover" in normalized or "覆盖" in text:
            inferred = "target_band_not_fully_covered"
        elif "normalized" in normalized or "归一化" in text:
            inferred = "normalization_state"
        else:
            inferred = "message"
    return Message(severity, inferred, text, {})


def format_messages(messages: list[Message]) -> str:
    if not messages:
        return "Messages:\n- Info [no_messages]: No errors or warnings were generated."
    lines = ["Messages:"]
    for severity in ("error", "warning", "info"):
        selected = [message for message in messages if message.severity == severity]
        if not selected:
            continue
        lines.append(f"{severity.upper()}:")
        for message in selected:
            lines.append(f"- [{message.code}] {message.text}")
    return "\n".join(lines)
