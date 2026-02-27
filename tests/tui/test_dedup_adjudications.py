"""Tests for _dedup_adjudications in the TUI app."""

import pytest

from sondera.tui.app import _dedup_adjudications
from sondera.types import Adjudication, AdjudicationRecord, Decision


def _rec(
    step_id: str,
    trajectory_id: str = "traj-1",
    decision: Decision = Decision.DENY,
    reason: str = "policy violation",
) -> AdjudicationRecord:
    return AdjudicationRecord(
        agent_id="agent-1",
        trajectory_id=trajectory_id,
        step_id=step_id,
        adjudication=Adjudication(decision=decision, reason=reason),
    )


class TestDedup:
    def test_empty(self):
        assert _dedup_adjudications([]) == []

    def test_single_record_unchanged(self):
        records = [_rec("1")]
        assert _dedup_adjudications(records) == records

    @pytest.mark.parametrize(
        "step_ids, expected_count",
        [
            # One consecutive pair → collapsed to 1
            (["1", "2"], 1),
            # Two consecutive pairs → collapsed to 2
            (["1", "2", "3", "4"], 2),
            # Non-consecutive → no collapsing
            (["1", "3"], 2),
            # Gap between pairs
            (["1", "2", "5", "6"], 2),
            # Three records: pair + orphan
            (["1", "2", "5"], 2),
        ],
        ids=[
            "one_pair",
            "two_pairs",
            "non_consecutive",
            "gap_between_pairs",
            "pair_plus_orphan",
        ],
    )
    def test_consecutive_pairs(self, step_ids, expected_count):
        records = [_rec(sid) for sid in step_ids]
        result = _dedup_adjudications(records)
        assert len(result) == expected_count

    def test_different_trajectories_deduped_independently(self):
        records = [
            _rec("1", trajectory_id="traj-a"),
            _rec("2", trajectory_id="traj-a"),
            _rec("3", trajectory_id="traj-b"),
            _rec("4", trajectory_id="traj-b"),
        ]
        result = _dedup_adjudications(records)
        assert len(result) == 2

    def test_different_decisions_not_merged(self):
        records = [
            _rec("1", decision=Decision.DENY),
            _rec("2", decision=Decision.ALLOW),
        ]
        result = _dedup_adjudications(records)
        assert len(result) == 2

    def test_different_reasons_not_merged(self):
        records = [
            _rec("1", reason="reason A"),
            _rec("2", reason="reason B"),
        ]
        result = _dedup_adjudications(records)
        assert len(result) == 2

    def test_non_integer_step_ids_passed_through(self):
        records = [_rec("abc"), _rec("def")]
        result = _dedup_adjudications(records)
        assert len(result) == 2

    def test_kept_record_is_first_of_pair(self):
        records = [_rec("10"), _rec("11")]
        result = _dedup_adjudications(records)
        assert len(result) == 1
        assert result[0].step_id == "10"
