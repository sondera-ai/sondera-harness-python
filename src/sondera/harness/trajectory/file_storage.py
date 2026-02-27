"""File-based trajectory storage.

Directory layout::

    <root>/
    ├── agents.json               # All registered agents
    ├── adjudications.json        # DENY/ESCALATE index with trajectory path refs
    └── <agent_id>/
        └── <trajectory_id>.jsonl # Line 1: Trajectory header, lines 2+: AdjudicatedStep
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sondera.types import (
    AdjudicatedStep,
    AdjudicatedTrajectory,
    AdjudicationRecord,
    Agent,
    Decision,
    Trajectory,
    TrajectoryStatus,
)

from .abc import TrajectoryStorage

logger = logging.getLogger(__name__)


class FileTrajectoryStorage(TrajectoryStorage):
    def __init__(self, root: str | Path = Path(".sondera/trajectories")) -> None:
        self._root = Path(root)

    # -- Paths ----------------------------------------------------------------

    @property
    def _agents_path(self) -> Path:
        return self._root / "agents.json"

    @property
    def _adjudications_path(self) -> Path:
        return self._root / "adjudications.json"

    def _agent_dir(self, agent_id: str) -> Path:
        return self._root / agent_id

    def _trajectory_path(self, agent_id: str, trajectory_id: str) -> Path:
        return self._agent_dir(agent_id) / f"{trajectory_id}.jsonl"

    # -- Internal helpers -----------------------------------------------------

    @staticmethod
    def _paginate(
        items: list[Any], page_size: int, page_token: str
    ) -> tuple[list[Any], str]:
        """Offset-based pagination. Token is the string offset."""
        offset = int(page_token) if page_token else 0
        page = items[offset : offset + page_size]
        next_offset = offset + page_size
        next_token = str(next_offset) if next_offset < len(items) else ""
        return page, next_token

    def _read_agents(self) -> list[Agent]:
        if not self._agents_path.exists():
            return []
        data = json.loads(self._agents_path.read_text())
        return [Agent.model_validate(a) for a in data]

    def _write_agents(self, agents: list[Agent]) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        self._agents_path.write_text(
            json.dumps([a.model_dump(mode="json") for a in agents], indent=2)
        )

    def _read_adjudication_records(self) -> list[dict[str, Any]]:
        if not self._adjudications_path.exists():
            return []
        return json.loads(self._adjudications_path.read_text())

    def _write_adjudication_records(self, records: list[dict[str, Any]]) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        self._adjudications_path.write_text(json.dumps(records, indent=2))

    def _read_trajectory_header(self, path: Path) -> Trajectory | None:
        """Read line 1 of a JSONL trajectory file (metadata only, no steps)."""
        if not path.exists():
            return None
        with path.open() as f:
            line = f.readline().strip()
            if not line:
                return None
            return Trajectory.model_validate(json.loads(line))

    def _count_steps(self, path: Path) -> int:
        """Count step lines in JSONL (total lines minus header)."""
        if not path.exists():
            return 0
        with path.open() as f:
            return max(sum(1 for _ in f) - 1, 0)

    def _read_full_trajectory(self, path: Path) -> AdjudicatedTrajectory | None:
        """Read JSONL file into an AdjudicatedTrajectory with all steps."""
        if not path.exists():
            return None
        lines = path.read_text().strip().splitlines()
        if not lines:
            return None
        meta = json.loads(lines[0])
        meta["steps"] = [json.loads(line) for line in lines[1:] if line.strip()]
        return AdjudicatedTrajectory.model_validate(meta)

    # -- Read (TrajectoryStorage ABC) -----------------------------------------

    async def list_agents(
        self,
        provider_id: str | None = None,
        page_size: int = 50,
        page_token: str = "",
    ) -> tuple[list[Agent], str]:
        agents = self._read_agents()
        if provider_id is not None:
            agents = [a for a in agents if a.provider_id == provider_id]
        return self._paginate(agents, page_size, page_token)

    async def get_agent(self, agent_id: str) -> Agent | None:
        for a in self._read_agents():
            if a.id == agent_id:
                return a
        return None

    async def list_trajectories(
        self,
        agent_id: str,
        status: TrajectoryStatus | None = None,
        page_size: int = 50,
        page_token: str = "",
        min_step_count: int = 0,
        session_id: str | None = None,
    ) -> tuple[list[Trajectory], str]:
        agent_dir = self._agent_dir(agent_id)
        if not agent_dir.exists():
            return [], ""

        trajectories: list[Trajectory] = []
        for path in sorted(
            agent_dir.glob("*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            traj = self._read_trajectory_header(path)
            if traj is None:
                continue
            if status is not None and traj.status != status:
                continue
            if session_id is not None and traj.session_id != session_id:
                continue
            if min_step_count > 0:
                step_count = self._count_steps(path)
                if step_count < min_step_count:
                    continue
                traj.raw_step_count = step_count
            trajectories.append(traj)

        return self._paginate(trajectories, page_size, page_token)

    async def get_trajectory(self, trajectory_id: str) -> AdjudicatedTrajectory | None:
        """Scan all agent dirs for ``<trajectory_id>.jsonl``."""
        if not self._root.exists():
            return None
        for agent_dir in self._root.iterdir():
            if not agent_dir.is_dir():
                continue
            path = agent_dir / f"{trajectory_id}.jsonl"
            result = self._read_full_trajectory(path)
            if result is not None:
                return result
        return None

    async def list_adjudications(
        self,
        agent_id: str | None = None,
        page_size: int = 50,
        page_token: str = "",
    ) -> tuple[list[AdjudicationRecord], str]:
        raw = self._read_adjudication_records()
        if agent_id is not None:
            raw = [r for r in raw if r.get("agent_id") == agent_id]
        records = [AdjudicationRecord.model_validate(r) for r in raw]
        return self._paginate(records, page_size, page_token)

    async def analyze_trajectories(
        self,
        agent_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        analytics: list[str] | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        agent_dir = self._agent_dir(agent_id)

        if analytics and "trajectory_count" in analytics:
            if agent_dir.exists():
                result["trajectory_count"] = sum(1 for _ in agent_dir.glob("*.jsonl"))
            else:
                result["trajectory_count"] = 0

        result["computed_at"] = datetime.now(tz=UTC).isoformat()
        return result

    # -- Write ----------------------------------------------------------------

    def save_agent(self, agent: Agent) -> None:
        agents = self._read_agents()
        for i, a in enumerate(agents):
            if a.id == agent.id:
                agents[i] = agent
                break
        else:
            agents.append(agent)
        self._write_agents(agents)

    def save_trajectory(self, trajectory: AdjudicatedTrajectory) -> None:
        """Write full trajectory to JSONL and rebuild its adjudication index."""
        agent_dir = self._agent_dir(trajectory.agent_id)
        agent_dir.mkdir(parents=True, exist_ok=True)
        path = self._trajectory_path(trajectory.agent_id, trajectory.id)

        meta = trajectory.model_dump(mode="json", exclude={"steps"})
        lines = [json.dumps(meta)]
        for step in trajectory.steps:
            lines.append(json.dumps(step.model_dump(mode="json")))
        path.write_text("\n".join(lines) + "\n")

        self._index_adjudications(trajectory)

    def init_trajectory(self, trajectory: Trajectory) -> None:
        agent_dir = self._agent_dir(trajectory.agent_id)
        agent_dir.mkdir(parents=True, exist_ok=True)
        path = self._trajectory_path(trajectory.agent_id, trajectory.id)
        meta = trajectory.model_dump(mode="json", exclude={"steps"})
        path.write_text(json.dumps(meta) + "\n")

    def append_step(
        self,
        agent_id: str,
        trajectory_id: str,
        step: AdjudicatedStep,
        step_index: int | None = None,
    ) -> None:
        path = self._trajectory_path(agent_id, trajectory_id)
        with path.open("a") as f:
            f.write(json.dumps(step.model_dump(mode="json")) + "\n")

        if step.adjudication.decision in (Decision.DENY, Decision.ESCALATE):
            idx = step_index if step_index is not None else self._count_steps(path) - 1
            self._append_adjudication_record(agent_id, trajectory_id, step, idx)

    def finalize_trajectory(self, agent_id: str, trajectory_id: str) -> None:
        path = self._trajectory_path(agent_id, trajectory_id)
        if not path.exists():
            return
        lines = path.read_text().splitlines()
        if not lines:
            return
        meta = json.loads(lines[0])
        meta["status"] = TrajectoryStatus.COMPLETED.value
        lines[0] = json.dumps(meta)
        path.write_text("\n".join(lines) + "\n")

    # -- Adjudication index ---------------------------------------------------

    def _append_adjudication_record(
        self,
        agent_id: str,
        trajectory_id: str,
        step: AdjudicatedStep,
        step_index: int,
    ) -> None:
        records = self._read_adjudication_records()
        traj_path = str(
            self._trajectory_path(agent_id, trajectory_id).relative_to(self._root)
        )
        records.append(
            {
                "agent_id": agent_id,
                "trajectory_id": trajectory_id,
                "trajectory_path": traj_path,
                "step_id": f"step-{step_index}",
                "step_index": step_index,
                "adjudication": step.adjudication.model_dump(mode="json"),
            }
        )
        self._write_adjudication_records(records)

    def _index_adjudications(self, trajectory: AdjudicatedTrajectory) -> None:
        """Rebuild adjudication index entries for this trajectory."""
        records = self._read_adjudication_records()
        records = [r for r in records if r.get("trajectory_id") != trajectory.id]
        traj_path = str(
            self._trajectory_path(trajectory.agent_id, trajectory.id).relative_to(
                self._root
            )
        )
        for i, step in enumerate(trajectory.steps):
            if step.adjudication.decision in (Decision.DENY, Decision.ESCALATE):
                records.append(
                    {
                        "agent_id": trajectory.agent_id,
                        "trajectory_id": trajectory.id,
                        "trajectory_path": traj_path,
                        "step_id": f"step-{i}",
                        "step_index": i,
                        "adjudication": step.adjudication.model_dump(mode="json"),
                    }
                )
        self._write_adjudication_records(records)
