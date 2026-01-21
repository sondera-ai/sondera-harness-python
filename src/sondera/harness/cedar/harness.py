"""
CedarPolicyEngine local harness implementation.
"""

import json
import logging
import uuid

from cedar.schema import CedarSchema

from cedar import (
    Authorizer,
    Context,
    Entity,
    EntityUid,
    PolicySet,
    Request,
    Schema,
)
from sondera.harness.abc import Harness as AbstractHarness
from sondera.types import (
    Adjudication,
    Agent,
    Content,
    Decision,
    PromptContent,
    Role,
    Stage,
    ToolRequestContent,
    ToolResponseContent,
)

_LOGGER = logging.getLogger(__name__)


class CedarPolicyHarness(AbstractHarness):
    """CedarPolicyHarness is a local policy-as-code harness for Agent Scaffolds.

    Uses Cedar policy language to evaluate tool invocations against a policy set.
    The schema is generated from the agent's tools using schema.py, with each tool
    becoming a Cedar action with typed parameters and response context.

    Actions:
        - Each tool becomes an action (e.g., MyAgent::Action::"my_tool")
        - PRE_TOOL stage evaluates with 'parameters' context
        - POST_TOOL stage evaluates with 'response' context

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
        logger: logging.Logger | None = None,
    ):
        """Initialize the Cedar policy engine.

        Args:
            policy_set: Cedar policies to evaluate. Can be a PolicySet instance
                or Cedar policy text. Required.
            schema: Cedar schema generated from agent_to_cedar_schema(). Required.
            logger: Logger instance.

        Raises:
            ValueError: If policy_set or schema is not provided.
        """
        self._agent: Agent | None = None
        self._trajectory_id: str | None = None
        self._trajectory_step_count: int = 0
        self._logger = logger or _LOGGER

        if schema is None:
            raise ValueError("schema is required")
        if policy_set is None:
            raise ValueError("policy_set is required")

        self._cedar_schema = schema
        # Exclude None values when serializing to JSON for Cedar compatibility
        self._schema = Schema.from_json(schema.model_dump_json(exclude_none=True))

        # Parse policy set
        if isinstance(policy_set, str):
            self._policy_set = PolicySet(policy_set)
        else:
            self._policy_set = policy_set
        # Extract namespace name from schema
        namespaces = list(schema.root.keys())
        if namespaces:
            # The schema has a single namespace keyed by name
            self._namespace = namespaces[0]
        else:
            raise ValueError("Schema must have at least one namespace")
        # Authorizer will be initialized with entities when agent is set
        self._authorizer: Authorizer | None = None

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

            # Add tool entities from agent's tools
            tool_entities: list[EntityUid] = []
            for tool in self._agent.tools:
                tool_id = tool.id or tool.name
                tool_uid = EntityUid(f"{self._namespace}::Tool", tool_id)
                tool_entity = Entity(
                    tool_uid,
                    {
                        "name": tool.name,
                        "description": tool.description,
                    },
                )
                tool_entities.append(tool_uid)
                entities.append(tool_entity)

            agent_entity = Entity(
                agent_uid,
                {
                    "name": self._agent.name,
                    "provider_id": self._agent.provider_id,
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
        """Resume an existing trajectory.

        Args:
            trajectory_id: The trajectory ID to resume.
            agent: Optional agent to use (overrides constructor agent).
        """
        raise NotImplementedError(
            "Resuming trajectories is not supported in CedarPolicyHarness."
        )

    async def initialize(
        self,
        *,
        agent: Agent | None = None,
    ) -> None:
        """Initialize a new trajectory.

        Args:
            agent: Optional agent to use (overrides constructor agent).
        """
        if agent:
            self._agent = agent
        self._trajectory_id = f"traj-{uuid.uuid4()}"
        self._trajectory_step_count = 0
        self._authorizer = self._build_authorizer()
        self._logger.debug("Initialized trajectory %s", self._trajectory_id)

    async def finalize(self) -> None:
        """Finalize the current trajectory."""
        if not self._trajectory_id:
            raise ValueError("No active trajectory. Call initialize first.")
        self._logger.debug("Finalized trajectory %s", self._trajectory_id)
        self._trajectory_id = None
        self._trajectory_step_count = 0

    async def adjudicate(
        self,
        stage: Stage,
        role: Role,
        content: Content,
    ) -> Adjudication:
        """Adjudicate a trajectory step using Cedar policies.

        Evaluates Cedar policies based on content type and stage:
        - PRE_TOOL + ToolRequestContent: Evaluates tool action with 'parameters' context
        - POST_TOOL + ToolResponseContent: Evaluates tool action with 'response' context
        - Other content types: Allowed by default

        The action name matches the tool name (sanitized for Cedar), and context
        contains typed parameters/response based on the tool's JSON schema.

        Args:
            stage: The stage of the step.
            role: The role of the step.
            content: The content of the step.

        Returns:
            The adjudication result (ALLOW or DENY).
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

        request: Request | None = None
        match (stage, content):
            case (Stage.PRE_MODEL | Stage.POST_MODEL, PromptContent()):
                request = self._message_request(
                    agent_uid, trajectory_uid, role, content
                )
            case (Stage.PRE_TOOL, ToolRequestContent()):
                request = self._tool_request(agent_uid, trajectory_uid, content)
            case (Stage.POST_TOOL, ToolResponseContent()):
                request = self._tool_response(agent_uid, trajectory_uid, content)
            case _:
                return Adjudication(
                    decision=Decision.ALLOW,
                    reason="Non-tool content allowed by default",
                )
        assert request is not None, "Unexpected none request"
        response = self._authorizer.is_authorized(request, self._policy_set)
        if str(response.decision) == "Allow":
            reason = f"Allowed by policies: {response.reason}"
            return Adjudication(decision=Decision.ALLOW, reason=reason)
        else:
            reason = f"Denied by policies: {response.reason}"
            return Adjudication(decision=Decision.DENY, reason=reason)

    def _message_request(
        self,
        agent_uid: EntityUid,
        trajectory_uid: EntityUid,
        role: Role,
        content: PromptContent,
    ) -> Request:
        """Create a request for a message request against Cedar policies.

        Args:
            content: The tool response content.

        Returns:
            The request.
        """
        if not self._authorizer:
            raise RuntimeError("_message_request called without authorizer")

        role_euid = EntityUid(f"{self._namespace}::Role", role.value.lower())
        message = Entity(
            EntityUid(f"{self._namespace}::Message", str(uuid.uuid4())),
            {"content": content.text, "role": role_euid},
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

    def _tool_request(
        self,
        agent_uid: EntityUid,
        trajectory_uid: EntityUid,
        content: ToolRequestContent,
    ) -> Request:
        """Create a request for a tool request against Cedar policies.

        Args:
            content: The tool response content.

        Returns:
            The request.
        """
        # Build entity UIDs using the schema's namespace
        tool_id = content.tool_id
        # Sanitize tool_id to match action name generation in schema.py
        action_name = tool_id.replace(" ", "_").replace("-", "_")
        action_uid = EntityUid(f"{self._namespace}::Action", action_name)

        context = Context(
            {"parameters_json": json.dumps(content.args), "parameters": content.args},
            schema=self._schema,
            action=action_uid,
        )

        return Request(
            principal=agent_uid,
            action=action_uid,
            resource=trajectory_uid,
            context=context,
            schema=self._schema,
        )

    def _tool_response(
        self,
        agent_uid: EntityUid,
        trajectory_uid: EntityUid,
        content: ToolResponseContent,
    ) -> Request:
        """Create a request for a tool response against Cedar policies.

        Args:
            content: The tool response content.

        Returns:
            The request.
        """
        # Build entity UIDs using the schema's namespace
        tool_id = content.tool_id
        # Sanitize tool_id to match action name generation in schema.py
        action_name = tool_id.replace(" ", "_").replace("-", "_")
        action_uid = EntityUid(f"{self._namespace}::Action", action_name)

        context = Context(
            {
                "response_json": json.dumps(content.response, default=str),
                "response": content.response,
            },
            schema=self._schema,
            action=action_uid,
        )

        return Request(
            principal=agent_uid,
            action=action_uid,
            resource=trajectory_uid,
            context=context,
            schema=self._schema,
        )
