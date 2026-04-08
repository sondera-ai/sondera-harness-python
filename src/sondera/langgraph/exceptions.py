"""LangChain agent integration exceptions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class GuardrailViolationError(RuntimeError):
    """Raised when guardrail enforcement blocks agent execution."""

    event_type: str
    node: str
    reason: str

    def __str__(self) -> str:  # pragma: no cover - string formatting
        return f"Guardrail violation at {self.node} ({self.event_type}): {self.reason}"
