"""Tests for Sondera SDK type definitions."""

from sondera.types import (
    AdjudicatedStep,
    AdjudicatedTrajectory,
    Adjudication,
    Decision,
    DecisionSummary,
    PolicyEngineMode,
    PromptContent,
    Role,
    Stage,
    TrajectoryStep,
)


def _make_adjudicated_step(decision: Decision) -> AdjudicatedStep:
    """Helper to create an AdjudicatedStep with a given decision."""
    return AdjudicatedStep(
        mode=PolicyEngineMode.GOVERN,
        adjudication=Adjudication(decision=decision, reason=f"{decision.value} reason"),
        step=TrajectoryStep(
            role=Role.MODEL,
            stage=Stage.PRE_MODEL,
            content=PromptContent(text="test"),
        ),
    )


class TestAdjudicatedTrajectoryDecisionSummary:
    def test_auto_computes_from_steps(self):
        """When decision_summary is None and steps are present, it should be computed."""
        traj = AdjudicatedTrajectory(
            id="traj-1",
            agent_id="agent-1",
            steps=[
                _make_adjudicated_step(Decision.ALLOW),
                _make_adjudicated_step(Decision.ALLOW),
                _make_adjudicated_step(Decision.DENY),
                _make_adjudicated_step(Decision.ESCALATE),
            ],
        )
        assert traj.decision_summary is not None
        assert traj.decision_summary.allow_count == 2
        assert traj.decision_summary.deny_count == 1
        assert traj.decision_summary.escalate_count == 1

    def test_preserves_server_provided_summary(self):
        """When decision_summary is already set, it should NOT be overwritten."""
        server_summary = DecisionSummary(allow_count=10, deny_count=5, escalate_count=3)
        traj = AdjudicatedTrajectory(
            id="traj-1",
            agent_id="agent-1",
            decision_summary=server_summary,
            steps=[
                _make_adjudicated_step(Decision.ALLOW),
                _make_adjudicated_step(Decision.DENY),
            ],
        )
        # Should keep the server-provided summary, not recompute
        assert traj.decision_summary.allow_count == 10
        assert traj.decision_summary.deny_count == 5
        assert traj.decision_summary.escalate_count == 3

    def test_empty_steps_leaves_summary_none(self):
        """When no steps, decision_summary should remain None."""
        traj = AdjudicatedTrajectory(
            id="traj-1",
            agent_id="agent-1",
            steps=[],
        )
        assert traj.decision_summary is None

    def test_all_allow(self):
        """Trajectory with all ALLOW steps."""
        traj = AdjudicatedTrajectory(
            id="traj-1",
            agent_id="agent-1",
            steps=[_make_adjudicated_step(Decision.ALLOW) for _ in range(3)],
        )
        assert traj.decision_summary is not None
        assert traj.decision_summary.allow_count == 3
        assert traj.decision_summary.deny_count == 0
        assert traj.decision_summary.escalate_count == 0
        assert not traj.has_violations

    def test_has_violations_with_deny(self):
        """has_violations should be True when deny_count > 0."""
        traj = AdjudicatedTrajectory(
            id="traj-1",
            agent_id="agent-1",
            steps=[
                _make_adjudicated_step(Decision.ALLOW),
                _make_adjudicated_step(Decision.DENY),
            ],
        )
        assert traj.has_violations


class TestTrajectoryStepNoDeadFields:
    def test_no_state_field(self):
        """TrajectoryStep should not have a state field."""
        step = TrajectoryStep(
            role=Role.MODEL,
            stage=Stage.PRE_MODEL,
            content=PromptContent(text="test"),
        )
        assert not hasattr(step, "state") or "state" not in step.model_fields

    def test_no_context_field(self):
        """TrajectoryStep should not have a context field."""
        step = TrajectoryStep(
            role=Role.MODEL,
            stage=Stage.PRE_MODEL,
            content=PromptContent(text="test"),
        )
        assert not hasattr(step, "context") or "context" not in step.model_fields
