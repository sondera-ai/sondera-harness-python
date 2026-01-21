"""LangChain agent integration exceptions."""

from __future__ import annotations

from dataclasses import dataclass

from sondera.types import Stage


@dataclass(slots=True)
class GuardrailViolationError(RuntimeError):
    """Raised when guardrail enforcement blocks agent execution."""

    stage: Stage
    node: str
    reason: str

    def __str__(self) -> str:  # pragma: no cover - string formatting
        return f"Guardrail violation at {self.node} during {self.stage.value}: {self.reason}"
