"""Tests for protobuf-to-SDK converters in sondera.harness.sondera._grpc."""

from sondera.harness.sondera._grpc import _convert_pb_adjudication_record_to_sdk
from sondera.proto.sondera.core.v1 import primitives_pb2
from sondera.proto.sondera.harness.v1 import harness_pb2
from sondera.types import Decision


def _make_pb_record(**overrides) -> harness_pb2.AdjudicationRecord:
    defaults = {
        "agent_id": "agent-1",
        "trajectory_id": "traj-1",
        "step_id": "42",
        "adjudication": primitives_pb2.Adjudication(
            decision=primitives_pb2.DECISION_DENY,
            reason="blocked by policy",
        ),
    }
    return harness_pb2.AdjudicationRecord(**(defaults | overrides))


def test_convert_adjudication_record():
    sdk = _convert_pb_adjudication_record_to_sdk(_make_pb_record(step_index=3))
    assert sdk.agent_id == "agent-1"
    assert sdk.trajectory_id == "traj-1"
    assert sdk.step_id == "42"
    assert sdk.adjudication.decision == Decision.DENY
    assert sdk.step_index == 3


def test_convert_adjudication_record_default_step_index():
    """Record with no step_index set should not crash."""
    sdk = _convert_pb_adjudication_record_to_sdk(_make_pb_record())
    assert sdk.step_index is None or sdk.step_index == 0
