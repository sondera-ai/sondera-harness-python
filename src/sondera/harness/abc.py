from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from sondera.types import (
    AdjudicatedTrajectory,
    Adjudication,
    AdjudicationRecord,
    Agent,
    Content,
    ModelMetadata,
    Role,
    Stage,
    Trajectory,
    TrajectoryStatus,
)


class Harness(ABC):
    """Abstract base class defining the interface for Sondera Harness implementations.

    This ABC defines the core contract for harness implementations that integrate
    with the Sondera Platform for agent governance, trajectory management, and
    real-time step adjudication.

    Subclasses must implement:
        - resume: Resume an existing trajectory for continued execution
        - initialize: Set up a new trajectory for agent execution
        - finalize: Complete and save the current trajectory
        - adjudicate: Evaluate a trajectory step against policies

    Attributes:
        trajectory_id: The current active trajectory ID (None if no active trajectory)
        agent: The agent being governed (may be None until initialize is called)
    """

    _trajectory_id: str | None
    _agent: Agent | None

    @property
    def trajectory_id(self) -> str | None:
        """Get the current trajectory ID."""
        return self._trajectory_id

    @property
    def agent(self) -> Agent | None:
        """Get the current agent."""
        return self._agent

    @abstractmethod
    async def resume(self, trajectory_id, *, agent: Agent | None = None) -> None:
        """Resume an existing trajectory for the given agent."""
        ...

    @abstractmethod
    async def initialize(
        self,
        *,
        agent: Agent | None = None,
        session_id: str | None = None,
    ) -> None:
        """Initialize a new trajectory for the current execution.

        This method should:
        1. Register the agent with the Sondera Platform if not already registered
        2. Create a new trajectory for tracking the agent's execution
        3. Store the trajectory ID for subsequent adjudication calls

        Args:
            agent: Optional agent to use for this trajectory. If provided, overrides
                   any agent set during construction.
            session_id: Optional session identifier to group trajectories belonging
                   to the same conversation. All trajectories with the same session_id
                   form an ordered sequence of turns.

        Raises:
            ValueError: If no agent is provided and none was set during construction
            RuntimeError: If connection to the harness service fails
        """
        ...

    @abstractmethod
    async def finalize(self) -> None:
        """Finalize the current trajectory and save artifacts.

        This method should:
        1. Mark the trajectory as completed
        2. Persist any remaining trajectory data
        3. Clear the active trajectory state

        Raises:
            ValueError: If no active trajectory exists (initialize not called)
            RuntimeError: If finalization fails
        """
        ...

    @abstractmethod
    async def adjudicate(
        self,
        stage: Stage,
        role: Role,
        content: Content,
        *,
        model_metadata: ModelMetadata | None = None,
    ) -> Adjudication:
        """Adjudicate a trajectory step using the policy engine.

        Evaluates the given step against configured policies and returns
        an adjudication decision (ALLOW, DENY, or ESCALATE).

        Args:
            stage: The execution stage (PRE_RUN, PRE_MODEL, POST_MODEL,
                   PRE_TOOL, POST_TOOL, POST_RUN)
            role: The role of the actor (USER, MODEL, TOOL, SYSTEM)
            content: The content to evaluate (PromptContent, ToolRequestContent,
                     or ToolResponseContent)
            model_metadata: Optional metadata about the model invocation
                   (model name, token counts, latency). Typically provided
                   for PRE_MODEL and POST_MODEL stages.

        Returns:
            Adjudication containing the decision and reason

        Raises:
            RuntimeError: If no active trajectory exists (initialize not called)
            ValueError: If the content type is not supported
        """
        ...

    # -- Query methods (paginated methods return (items, next_page_token)) ----

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
        """Return trajectory with fully hydrated AdjudicatedSteps."""
        ...

    @abstractmethod
    async def list_adjudications(
        self,
        agent_id: str | None = None,
        page_size: int = 50,
        page_token: str = "",
    ) -> tuple[list[AdjudicationRecord], str]:
        """Only deny/escalate records."""
        ...

    @abstractmethod
    async def analyze_trajectories(
        self,
        agent_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        analytics: list[str] | None = None,
    ) -> dict[str, Any]:
        """Supported analytics: ``trajectory_count``."""
        ...
