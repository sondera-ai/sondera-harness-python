from abc import ABC, abstractmethod

from sondera.types import Adjudication, Agent, Content, Role, Stage


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
    async def initialize(self, *, agent: Agent | None = None) -> None:
        """Initialize a new trajectory for the current execution.

        This method should:
        1. Register the agent with the Sondera Platform if not already registered
        2. Create a new trajectory for tracking the agent's execution
        3. Store the trajectory ID for subsequent adjudication calls

        Args:
            agent: Optional agent to use for this trajectory. If provided, overrides
                   any agent set during construction.

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

        Returns:
            Adjudication containing the decision and reason

        Raises:
            RuntimeError: If no active trajectory exists (initialize not called)
            ValueError: If the content type is not supported
        """
        ...
