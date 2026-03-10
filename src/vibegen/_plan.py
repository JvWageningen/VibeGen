"""Task planning and progress tracking for the vibegen pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ._io import _print_err, _print_ok, _print_step, _print_warn

StepStatus = Literal["pending", "running", "done", "failed", "skipped"]

_STATUS_ICONS: dict[StepStatus, str] = {
    "pending": "  ",
    "running": "->",
    "done": "OK",
    "failed": "!!",
    "skipped": "--",
}


@dataclass
class TaskStep:
    """A single named step in the generation plan.

    Attributes:
        id: Unique identifier for this step.
        description: Human-readable description.
        status: Current execution status.
        detail: Optional extra detail (error message, count, etc.).
    """

    id: str
    description: str
    status: StepStatus = "pending"
    detail: str = ""


@dataclass
class TaskPlan:
    """Ordered collection of TaskSteps with progress tracking.

    Attributes:
        steps: Ordered list of steps.
        _index: Fast lookup dict by step id.
    """

    steps: list[TaskStep] = field(default_factory=list)
    _index: dict[str, TaskStep] = field(default_factory=dict, repr=False)

    def add(self, id: str, description: str) -> None:
        """Register a new step.

        Args:
            id: Unique step identifier.
            description: Human-readable label.
        """
        step = TaskStep(id=id, description=description)
        self.steps.append(step)
        self._index[id] = step

    def start(self, id: str) -> None:
        """Mark a step as running and print its description.

        Args:
            id: Step identifier.
        """
        step = self._index.get(id)
        if step is None:
            return
        step.status = "running"
        _print_step(f"[{self._pos(id)}/{len(self.steps)}] {step.description}")

    def complete(self, id: str, detail: str = "") -> None:
        """Mark a step as done.

        Args:
            id: Step identifier.
            detail: Optional completion summary (e.g. "5 files written").
        """
        step = self._index.get(id)
        if step is None:
            return
        step.status = "done"
        step.detail = detail
        msg = step.description
        if detail:
            msg = f"{msg} — {detail}"
        _print_ok(msg)

    def fail(self, id: str, reason: str = "") -> None:
        """Mark a step as failed.

        Args:
            id: Step identifier.
            reason: Short description of why it failed.
        """
        step = self._index.get(id)
        if step is None:
            return
        step.status = "failed"
        step.detail = reason
        msg = step.description
        if reason:
            msg = f"{msg} — {reason}"
        _print_err(msg)

    def skip(self, id: str, reason: str = "") -> None:
        """Mark a step as skipped.

        Args:
            id: Step identifier.
            reason: Optional explanation.
        """
        step = self._index.get(id)
        if step is None:
            return
        step.status = "skipped"
        step.detail = reason
        msg = f"Skipped: {step.description}"
        if reason:
            msg = f"{msg} ({reason})"
        _print_warn(msg)

    def render(self) -> str:
        """Return a multi-line status summary of all steps.

        Returns:
            Formatted string with one line per step showing status icon,
            position, description, and optional detail.
        """
        lines: list[str] = ["=== Task Plan ==="]
        for i, step in enumerate(self.steps, 1):
            icon = _STATUS_ICONS.get(step.status, "  ")
            detail = f" ({step.detail})" if step.detail else ""
            lines.append(f"  [{icon}] {i:2d}. {step.description}{detail}")
        return "\n".join(lines)

    def _pos(self, id: str) -> int:
        """Return 1-based position of step with given id.

        Args:
            id: Step identifier.

        Returns:
            Position (1-based), or 0 if not found.
        """
        for i, step in enumerate(self.steps, 1):
            if step.id == id:
                return i
        return 0


def build_default_plan() -> TaskPlan:
    """Create the standard vibegen generation plan with all steps pre-registered.

    Returns:
        TaskPlan with all pipeline steps in execution order.
    """
    plan = TaskPlan()
    plan.add("parse_spec", "Parse spec file")
    plan.add("scaffold", "Scaffold project structure")
    plan.add("install_deps", "Install declared dependencies")
    plan.add("plan_code", "Plan implementation (architecture pass)")
    plan.add("generate_code", "Generate source code")
    plan.add("fix_code_ruff", "Auto-fix source code (ruff)")
    plan.add("fix_code_llm", "Fix source code errors (LLM)")
    plan.add("plan_tests", "Plan tests from source")
    plan.add("generate_tests", "Generate test suite")
    plan.add("fix_tests_ruff", "Auto-fix tests (ruff)")
    plan.add("run_tests", "Run pytest")
    plan.add("fix_test_failures", "Fix failing tests (LLM, per file)")
    plan.add("reviewer", "Reviewer pass (spec compliance check)")
    plan.add("finalize", "Finalize project (README + git commit)")
    return plan
