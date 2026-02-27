"""Abstract trajectory storage interface.

Read methods are async and paginated. Write methods are sync with no-op defaults.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from sondera.types import (
    AdjudicatedStep,
    AdjudicatedTrajectory,
    AdjudicationRecord,
    Agent,
    Trajectory,
    TrajectoryStatus,
)


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
        min_step_count: int = 0,
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

    def finalize_trajectory(self, agent_id: str, trajectory_id: str) -> None:  # noqa: B027
        """Mark trajectory as COMPLETED."""
