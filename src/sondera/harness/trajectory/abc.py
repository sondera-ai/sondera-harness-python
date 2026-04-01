"""Abstract trajectory storage interface.

Read methods are async and paginated. Write methods are sync with no-op defaults.

This module uses sondera types for Agent, Trajectory, and TrajectoryStatus,
plus local storage-specific types for adjudicated steps and records.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from sondera.types import (
    Adjudicated,
    Agent,
    Event,
    Trajectory,
    TrajectoryStatus,
)

# Event, Adjudicated, and TrajectoryStatus are PyO3 types that Pydantic
# cannot introspect natively, so all models using them need this config.
_pyo3_config = ConfigDict(arbitrary_types_allowed=True)


class AdjudicatedStep(BaseModel):
    """A trajectory step with its adjudication result (for local storage)."""

    model_config = _pyo3_config

    event: Event
    adjudication: Adjudicated


class AdjudicatedTrajectory(BaseModel):
    """Trajectory with all adjudicated steps (for local storage queries)."""

    model_config = _pyo3_config

    id: str
    agent: str  # Agent ID
    status: TrajectoryStatus = TrajectoryStatus.Running
    session_id: str | None = None
    steps: list[AdjudicatedStep] = []


class AdjudicationRecord(BaseModel):
    """Index record for DENY/ESCALATE adjudications (for fast lookup)."""

    model_config = _pyo3_config

    agent_id: str
    trajectory_id: str
    trajectory_path: str
    step_id: str
    step_index: int
    adjudication: Adjudicated


class TrajectoryStorage(ABC):
    """Persist agents, trajectories, and adjudications.

    Paginated methods return ``(items, next_page_token)``.
    Empty token means no more pages.
    """

    # -- Read -----------------------------------------------------------------

    @abstractmethod
    async def list_agents(
        self,
        provider_id: str | None = None,
        page_size: int = 50,
        page_token: str = "",
    ) -> tuple[list[Agent], str]: ...

    @abstractmethod
    async def get_agent(self, agent_id: str) -> Agent | None: ...

    @abstractmethod
    async def list_trajectories(
        self,
        agent_id: str,
        status: TrajectoryStatus | None = None,
        page_size: int = 50,
        page_token: str = "",
        session_id: str | None = None,
    ) -> tuple[list[Trajectory], str]: ...

    @abstractmethod
    async def get_trajectory(self, trajectory_id: str) -> AdjudicatedTrajectory | None:
        """Return trajectory with all steps hydrated."""
        ...

    @abstractmethod
    async def list_adjudications(
        self,
        agent_id: str | None = None,
        page_size: int = 50,
        page_token: str = "",
    ) -> tuple[list[AdjudicationRecord], str]:
        """Only DENY/ESCALATE adjudications are indexed."""
        ...

    @abstractmethod
    async def analyze_trajectories(
        self,
        agent_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        analytics: list[str] | None = None,
    ) -> dict[str, Any]:
        """Compute analytics. Supported keys: ``trajectory_count``."""
        ...

    # -- Write (no-op defaults; override to persist) --------------------------

    def save_agent(self, agent: Agent) -> None:  # noqa: B027
        """Upsert agent record."""

    def init_trajectory(self, trajectory: Trajectory) -> None:  # noqa: B027
        """Write trajectory header (metadata only, no steps)."""

    def append_step(  # noqa: B027
        self,
        agent_id: str,
        trajectory_id: str,
        step: AdjudicatedStep,
        step_index: int | None = None,
    ) -> None:
        """Append step to trajectory. Indexes DENY/ESCALATE adjudications."""

    def finalize_trajectory(  # noqa: B027
        self,
        agent_id: str,
        trajectory_id: str,
        *,
        status: TrajectoryStatus = TrajectoryStatus.Completed,
    ) -> None:
        """Mark trajectory as COMPLETED (or override with a different status)."""
