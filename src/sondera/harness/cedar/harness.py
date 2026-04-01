"""
CedarPolicyEngine local harness implementation.
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from cedar.schema import CedarSchema

from cedar import (
    Authorizer,
    Context,
    Entity,
    EntityUid,
    PolicySet,
    Request,
    Response,
    Schema,
)
from sondera.harness.abc import Harness as AbstractHarness
from sondera.harness.cedar.schema import _agent_tools
from sondera.harness.trajectory.abc import (
    AdjudicatedStep,
    TrajectoryStorage,
)
from sondera.harness.trajectory.file_storage import FileTrajectoryStorage
from sondera.types import (
    Adjudicated,
    Agent,
    Decision,
    Event,
    Mode,
    PolicyMetadata,
    Prompt,
    Tool,
    ToolCall,
    ToolOutput,
    Trajectory,
    TrajectoryEventStream,
    TrajectoryStatus,
)

_LOGGER = logging.getLogger(__name__)


class CedarPolicyHarness(AbstractHarness):
    """CedarPolicyHarness is a local policy-as-code harness for Agent Scaffolds.

    Uses Cedar policy language to evaluate tool invocations against a policy set.
    The schema is generated from the agent's tools using schema.py, with each tool
    becoming a Cedar action with typed parameters and response context.

    Actions:
        - Each tool becomes an action (e.g., MyAgent::Action::"my_tool")
        - ToolCall: Evaluates tool action with 'parameters' context
        - ToolOutput: Evaluates tool action with 'response' context

    Example policy to allow all tool invocations for an agent named "MyAgent":
        permit(principal, action, resource)
        when { principal is MyAgent::Agent };

    Example policy to deny a specific tool:
        forbid(
            principal,
            action == MyAgent::Action::"dangerous_tool",
            resource
        );

    Example policy with parameter constraints:
        forbid(
            principal,
            action == MyAgent::Action::"bash",
            resource
        ) when { context.parameters.command like "*rm -rf*" };
    """

    def __init__(
        self,
        *,
        policy_set: PolicySet | str,
        schema: CedarSchema,
        storage: TrajectoryStorage | None = None,
        agent: Agent | None = None,
        logger: logging.Logger | None = None,
    ):
        """Initialize the Cedar policy engine.

        Args:
            policy_set: Cedar policies to evaluate. Can be a PolicySet instance
                or Cedar policy text. Required.
            schema: Cedar schema generated from agent_to_cedar_schema(). Required.
            storage: Optional trajectory storage for persistence.
            agent: The agent to govern. Required for adjudication.
            logger: Logger instance.

        Raises:
            ValueError: If policy_set or schema is not provided.
        """
        self._agent: Agent | None = agent
        self._trajectory_id: str | None = None
        self._trajectory_step_count: int = 0
        self._logger = logger or _LOGGER
        self._storage = storage or FileTrajectoryStorage()

        if schema is None:
            raise ValueError("schema is required")
        if policy_set is None:
            raise ValueError("policy_set is required")

        # Exclude None values when serializing to JSON for Cedar compatibility
        self._schema = Schema.from_json(schema.model_dump_json(exclude_none=True))

        # Parse policy set
        if isinstance(policy_set, str):
            self._policy_set = PolicySet(policy_set)
        else:
            self._policy_set = policy_set

        seen_ids: set[str] = set()
        for policy in self._policy_set.policies():
            annotations = policy.annotations()
            if "id" not in annotations:
                raise ValueError(
                    f"Policy '{policy.id()}' is missing required @id annotation."
                )
            policy_id = annotations["id"]
            if policy_id in seen_ids:
                self._logger.warning(f"Duplicate policy @id: '{policy_id}'")
            seen_ids.add(policy_id)
            if "escalate" in annotations and str(policy.effect()) != "Forbid":
                raise ValueError(
                    f"Policy '{policy_id}' has @escalate but is not a forbid policy. "
                    "@escalate is only valid on forbid policies."
                )

        # Extract namespace name from schema
        namespaces = list(schema.root.keys())
        if namespaces:
            # The schema has a single namespace keyed by name
            self._namespace = namespaces[0]
        else:
            raise ValueError("Schema must have at least one namespace")
        # Authorizer will be initialized with entities when agent is set
        self._authorizer: Authorizer | None = None
        # Cache for pre-parsed tool response schemas (tool_name -> parsed schema dict)
        self._tool_response_schemas: dict[str, dict[str, object]] = {}
        # Cache for tool lookup by name (populated in _build_authorizer)
        self._tools_by_name: dict[str, Tool] = {}

    def _build_authorizer(self) -> Authorizer:
        """Build the Cedar authorizer with current entities."""
        if not self._trajectory_id:
            raise RuntimeError("_build_authorizer called without trajectory_id")

        entities: list[Entity] = [
            Entity(
                EntityUid(f"{self._namespace}::Trajectory", self._trajectory_id),
                {
                    "step_count": self._trajectory_step_count,
                },
            )
        ]

        if self._agent:
            agent_uid = EntityUid(f"{self._namespace}::Agent", self._agent.id)

            # Add tool entities from agent's card and pre-parse response schemas
            tool_entities: list[EntityUid] = []
            self._tool_response_schemas = {}
            self._tools_by_name = {}
            for tool in _agent_tools(self._agent):
                tool_name = tool.name
                tool_uid = EntityUid(f"{self._namespace}::Tool", tool_name)
                tool_entity = Entity(
                    tool_uid,
                    {
                        "name": tool_name,
                        "description": tool.description or "",
                    },
                )
                tool_entities.append(tool_uid)
                entities.append(tool_entity)
                self._tools_by_name[tool_name] = tool
                # Pre-parse response JSON schema for use in _tool_output_request
                if tool.response_json_schema:
                    self._tool_response_schemas[tool_name] = json.loads(
                        tool.response_json_schema
                    )

            agent_entity = Entity(
                agent_uid,
                {
                    "name": self._agent.id,
                    "provider": self._agent.provider,
                    "tools": tool_entities,
                },
            )
            entities.append(agent_entity)

        return Authorizer(entities=entities, schema=self._schema)

    async def resume(
        self,
        trajectory_id: str,
        *,
        agent: Agent | None = None,
    ) -> None:
        """Resume a trajectory from storage.

        Args:
            trajectory_id: The trajectory ID to resume.
            agent: Optional agent to use (overrides constructor agent).
        """
        if agent:
            self._agent = agent

        # Load trajectory from storage to get step count
        traj = await self._storage.get_trajectory(trajectory_id)
        if traj is None:
            raise ValueError(f"Trajectory {trajectory_id} not found in storage")

        self._trajectory_id = trajectory_id
        self._trajectory_step_count = len(traj.steps)
        self._authorizer = self._build_authorizer()
        self._logger.debug(
            "Resumed trajectory %s at step %d",
            trajectory_id,
            self._trajectory_step_count,
        )

    async def initialize(
        self,
        *,
        agent: Agent | None = None,
        session_id: str | None = None,
    ) -> None:
        """Create a new trajectory and persist to storage.

        Args:
            agent: Optional agent to use (overrides constructor agent).
            session_id: Optional session identifier.
        """
        if agent:
            self._agent = agent
        self._trajectory_id = f"traj-{uuid.uuid4()}"
        self._trajectory_step_count = 0
        self._authorizer = self._build_authorizer()

        # Persist agent and trajectory header
        if self._agent:
            self._storage.save_agent(self._agent)
        trajectory = Trajectory(
            name=self._trajectory_id,
            agent=self._agent.id if self._agent else "unknown",
            status=TrajectoryStatus.Running,
        )
        self._storage.init_trajectory(trajectory)
        self._logger.debug("Initialized trajectory %s", self._trajectory_id)

    async def finalize(self, *, summary: str | None = None) -> None:
        """Finalize the trajectory and persist to storage.

        Args:
            summary: Optional free-text summary (passed through for API
                     compatibility; not persisted by local storage).
        """
        if not self._trajectory_id:
            raise ValueError("No active trajectory. Call initialize first.")
        if self._agent:
            self._storage.finalize_trajectory(self._agent.id, self._trajectory_id)
        self._logger.debug("Finalized trajectory %s", self._trajectory_id)
        self._trajectory_id = None
        self._trajectory_step_count = 0

    async def fail(self, *, reason: str) -> None:
        """Mark the current trajectory as failed.

        Args:
            reason: Human-readable description of the failure cause.
        """
        if not self._trajectory_id:
            raise ValueError("No active trajectory. Call initialize first.")
        try:
            if self._agent:
                self._storage.finalize_trajectory(
                    self._agent.id,
                    self._trajectory_id,
                    status=TrajectoryStatus.Failed,
                )
            self._logger.debug("Failed trajectory %s: %s", self._trajectory_id, reason)
        finally:
            self._trajectory_id = None
            self._trajectory_step_count = 0

    async def adjudicate(
        self,
        event: Event,
    ) -> Adjudicated:
        """Adjudicate an event using Cedar policies.

        Evaluates Cedar policies based on the event payload type:
        - ToolCall: Evaluates tool action with 'parameters' context
        - ToolOutput: Evaluates tool action with 'response' context
        - Prompt: Evaluates Prompt action with message content
        - Other event types: Allowed by default

        The action name matches the tool name (sanitized for Cedar), and context
        contains typed parameters/response based on the tool's JSON schema.

        Args:
            event: The event to adjudicate.

        Returns:
            Adjudicated verdict with decision and reason.
        """
        if not self._agent or not self._trajectory_id or not self._authorizer:
            raise RuntimeError("initialize() must be called before adjudicate().")

        # Build common entity UIDs using the schema's namespace
        agent_uid = EntityUid(f"{self._namespace}::Agent", self._agent.id)
        trajectory_uid = EntityUid(
            f"{self._namespace}::Trajectory", self._trajectory_id
        )
        self._trajectory_step_count += 1
        trajectory_entity = Entity(
            trajectory_uid, {"step_count": self._trajectory_step_count}
        )
        self._authorizer.upsert_entity(trajectory_entity)

        payload = event.event
        request: Request | None = None

        if isinstance(payload, Prompt):
            request = self._prompt_request(agent_uid, trajectory_uid, payload)
        elif isinstance(payload, ToolCall):
            request = self._tool_call_request(agent_uid, trajectory_uid, payload)
        elif isinstance(payload, ToolOutput):
            request = self._tool_output_request(agent_uid, trajectory_uid, payload)
        else:
            # Other event types (Started, Completed, etc.) are allowed by default
            adjudication = Adjudicated(
                decision=Decision.Allow,
                reason="Non-policy event allowed by default",
                mode=Mode.Govern,
            )
            self._persist_step(event, adjudication)
            return adjudication

        response = self._authorizer.is_authorized(request, self._policy_set)
        adjudication = self._convert_cedar_response(response)
        self._persist_step(event, adjudication)
        return adjudication

    async def adjudicates(
        self,
        events: list[Event],
    ) -> list[Adjudicated]:
        """Adjudicate a batch of events using Cedar policies.

        Evaluates each event sequentially through the local Cedar policy engine.

        Args:
            events: A list of ``Event`` objects to evaluate.

        Returns:
            A list of ``Adjudicated`` verdicts, one per input event, in order.
        """
        return [await self.adjudicate(event) for event in events]

    def _persist_step(self, event: Event, adjudication: Adjudicated) -> None:
        """Persist step to storage."""
        if not self._agent or not self._trajectory_id:
            return
        step = AdjudicatedStep(event=event, adjudication=adjudication)
        self._storage.append_step(
            self._agent.id,
            self._trajectory_id,
            step,
            self._trajectory_step_count - 1,
        )

    def _convert_cedar_response(self, response: Response) -> Adjudicated:
        """Convert a Cedar Response to an Adjudicated verdict."""
        has_escalate = False
        has_deny = False
        reasons: list[str] = []
        deny_policies: list[PolicyMetadata] = []
        escalate_policies: list[PolicyMetadata] = []

        for internal_id in response.reason:
            policy = self._policy_set.policy(internal_id)
            if policy is None:
                continue
            annotations = policy.annotations()
            policy_id = annotations.get("id", internal_id)
            description = annotations.get("description", "")

            if "escalate" in annotations:
                has_escalate = True
                reasons.append(f"Escalate: {policy_id}")
                escalate_arg = annotations.get("escalate", "") or None
                # Carry any extra custom annotations (skip known ones)
                extra = {
                    k: v
                    for k, v in annotations.items()
                    if k not in ("id", "description", "escalate")
                }
                escalate_policies.append(
                    PolicyMetadata(
                        policy_id=policy_id,
                        description=description,
                        escalate=True,
                        escalate_arg=escalate_arg,
                        metadata=extra if extra else {},
                    )
                )
            else:
                has_deny = True
                reasons.append(f"Deny: {policy_id}")
                extra = {
                    k: v
                    for k, v in annotations.items()
                    if k not in ("id", "description")
                }
                deny_policies.append(
                    PolicyMetadata(
                        policy_id=policy_id,
                        description=description,
                        metadata=extra if extra else {},
                    )
                )

        if str(response.decision) == "Allow":
            return Adjudicated(
                decision=Decision.Allow,
                reason="Allowed by all policies",
                mode=Mode.Govern,
            )

        # Cedar decision was DENY - determine if hard DENY or ESCALATE
        if has_deny:
            return Adjudicated(
                decision=Decision.Deny,
                reason="; ".join(reasons) if reasons else "Denied by policy",
                metadata=deny_policies,
                mode=Mode.Govern,
            )
        if has_escalate:
            return Adjudicated(
                decision=Decision.Escalate,
                reason="; ".join(reasons) if reasons else "Escalated by policy",
                metadata=escalate_policies,
                mode=Mode.Govern,
            )
        # Default deny because no policies matched
        return Adjudicated(
            decision=Decision.Deny,
            reason="No matching permit policy",
            mode=Mode.Govern,
        )

    def _prompt_request(
        self,
        agent_uid: EntityUid,
        trajectory_uid: EntityUid,
        prompt: Prompt,
    ) -> Request:
        """Create a Cedar request for a Prompt event."""
        if not self._authorizer:
            raise RuntimeError("_prompt_request called without authorizer")

        role = str(prompt.role) if prompt.role else "user"
        role_euid = EntityUid(f"{self._namespace}::Role", role)
        message = Entity(
            EntityUid(f"{self._namespace}::Message", str(uuid.uuid4())),
            {"content": prompt.content, "role": role_euid},
            [trajectory_uid],
        )
        self._authorizer.add_entity(message)
        action_uid = EntityUid(f"{self._namespace}::Action", "Prompt")
        return Request(
            principal=agent_uid,
            action=action_uid,
            resource=message.uid(),
            schema=self._schema,
        )

    def _tool_call_request(
        self,
        agent_uid: EntityUid,
        trajectory_uid: EntityUid,
        tool_call: ToolCall,
    ) -> Request:
        """Create a Cedar request for a ToolCall event."""
        tool_name = tool_call.tool
        action_name = tool_name.replace(" ", "_").replace("-", "_")
        action_uid = EntityUid(f"{self._namespace}::Action", action_name)

        # Build context with parameters
        context_data: dict[str, object] = {
            "parameters_json": json.dumps(tool_call.arguments),
        }
        # Check if tool has typed parameters schema
        if self._agent:
            tool = self._tools_by_name.get(tool_name)
            if tool and tool.parameters_json_schema:
                context_data["parameters"] = tool_call.arguments

        context = Context(context_data, schema=self._schema, action=action_uid)

        return Request(
            principal=agent_uid,
            action=action_uid,
            resource=trajectory_uid,
            context=context,
            schema=self._schema,
        )

    def _tool_output_request(
        self,
        agent_uid: EntityUid,
        trajectory_uid: EntityUid,
        tool_output: ToolOutput,
    ) -> Request:
        """Create a Cedar request for a ToolOutput event."""
        # Tool name is in call_id (this could be improved in the protocol)
        tool_name = tool_output.call_id
        action_name = tool_name.replace(" ", "_").replace("-", "_")
        action_uid = EntityUid(f"{self._namespace}::Action", action_name)

        # Build context with response
        context_data: dict[str, object] = {
            "response_json": tool_output.output,
        }
        # Check if tool has typed response schema
        if tool_name in self._tool_response_schemas:
            response_schema = self._tool_response_schemas[tool_name]
            try:
                response_obj = json.loads(tool_output.output)
                if response_schema.get("type") not in ["object", "OBJECT"]:
                    context_data["response"] = {"value": response_obj}
                else:
                    context_data["response"] = response_obj
            except json.JSONDecodeError:
                pass  # Keep only response_json

        context = Context(context_data, schema=self._schema, action=action_uid)

        return Request(
            principal=agent_uid,
            action=action_uid,
            resource=trajectory_uid,
            context=context,
            schema=self._schema,
        )

    # -- Query methods (delegated to storage) -----------------------------------

    async def list_agents(
        self,
        provider_id: str | None = None,
        page_size: int = 50,
        page_token: str = "",
    ) -> tuple[list[Agent], str]:
        return await self._storage.list_agents(
            provider_id=provider_id, page_size=page_size, page_token=page_token
        )

    async def get_agent(self, agent_id: str) -> Agent | None:
        return await self._storage.get_agent(agent_id)

    async def list_trajectories(
        self,
        agent_id: str,
        status: TrajectoryStatus | None = None,
        page_size: int = 50,
        page_token: str = "",
        session_id: str | None = None,
    ) -> tuple[list[Trajectory], str]:
        return await self._storage.list_trajectories(
            agent_id=agent_id,
            status=status,
            page_size=page_size,
            page_token=page_token,
            session_id=session_id,
        )

    async def get_trajectory(self, trajectory_id: str) -> Trajectory | None:
        traj = await self._storage.get_trajectory(trajectory_id)
        if traj is None:
            return None
        # Convert AdjudicatedTrajectory to Trajectory
        return Trajectory(name=traj.id, agent=traj.agent, status=traj.status)

    async def list_adjudications(
        self,
        agent_id: str | None = None,
        page_size: int = 50,
        page_token: str = "",
    ) -> tuple[list[Event], str]:
        records, next_token = await self._storage.list_adjudications(
            agent_id=agent_id, page_size=page_size, page_token=page_token
        )
        # Convert AdjudicationRecord to Event (wrap adjudication in Event)
        events: list[Event] = []
        for record in records:
            # Build a minimal Agent stub so Event has valid agent context
            stub = Agent(
                id=record.agent_id,
                provider="unknown",
            )
            events.append(
                Event(
                    agent=stub,
                    trajectory_id=record.trajectory_id,
                    event=record.adjudication,
                )
            )
        return events, next_token

    async def analyze_trajectories(
        self,
        agent_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        analytics: list[str] | None = None,
    ) -> dict[str, Any]:
        return await self._storage.analyze_trajectories(
            agent_id=agent_id,
            start_time=start_time,
            end_time=end_time,
            analytics=analytics,
        )

    async def stream_trajectories(
        self,
        filter: str = "",
    ) -> TrajectoryEventStream:
        """Not supported by the local Cedar harness.

        Raises:
            NotImplementedError: Always, as local storage does not support streaming.
        """
        raise NotImplementedError(
            "stream_trajectories is not supported by CedarPolicyHarness. "
            "Use SonderaRemoteHarness for server-side event streaming."
        )
