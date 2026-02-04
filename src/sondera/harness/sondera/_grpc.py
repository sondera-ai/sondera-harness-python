from datetime import UTC, datetime

from google.protobuf import struct_pb2
from google.protobuf.json_format import MessageToDict

from sondera.proto.sondera.core.v1 import primitives_pb2
from sondera.proto.sondera.harness.v1 import harness_pb2
from sondera.types import (
    AdjudicatedStep,
    AdjudicatedTrajectory,
    Adjudication,
    AdjudicationRecord,
    Agent,
    Check,
    Content,
    Decision,
    GuardrailContext,
    Parameter,
    PolicyEngineMode,
    PolicyMetadata,
    PromptContent,
    Role,
    SourceCode,
    Stage,
    Tool,
    ToolRequestContent,
    ToolResponseContent,
    Trajectory,
    TrajectoryStatus,
    TrajectoryStep,
)


def _convert_sdk_stage_to_pb(stage: Stage) -> primitives_pb2.Stage:
    """Convert SDK Stage to protobuf Stage."""
    stage_map = {
        Stage.PRE_RUN: primitives_pb2.STAGE_PRE_RUN,
        Stage.PRE_MODEL: primitives_pb2.STAGE_PRE_MODEL,
        Stage.POST_MODEL: primitives_pb2.STAGE_POST_MODEL,
        Stage.PRE_TOOL: primitives_pb2.STAGE_PRE_TOOL,
        Stage.POST_TOOL: primitives_pb2.STAGE_POST_TOOL,
        Stage.POST_RUN: primitives_pb2.STAGE_POST_RUN,
    }
    return stage_map[stage]


def _convert_sdk_role_to_pb(role: Role) -> primitives_pb2.Role:
    """Convert SDK Role to protobuf Role."""
    role_map = {
        Role.USER: primitives_pb2.ROLE_USER,
        Role.MODEL: primitives_pb2.ROLE_MODEL,
        Role.TOOL: primitives_pb2.ROLE_TOOL,
        Role.SYSTEM: primitives_pb2.ROLE_SYSTEM,
    }
    return role_map[role]


def _convert_sdk_content_to_pb(content: Content) -> primitives_pb2.Content:
    """Convert SDK Content to protobuf Content."""
    if isinstance(content, PromptContent):
        return primitives_pb2.Content(prompt=primitives_pb2.Prompt(text=content.text))
    elif isinstance(content, ToolRequestContent):
        # Convert Python dict to protobuf Value
        value = struct_pb2.Value()
        value.struct_value.update(content.args)
        return primitives_pb2.Content(
            tool_request=primitives_pb2.ToolRequest(tool_id=content.tool_id, args=value)
        )
    elif isinstance(content, ToolResponseContent):
        # Convert Python dict to protobuf Value
        value = struct_pb2.Value()
        if isinstance(content.response, dict):
            value.struct_value.update(content.response)
        elif isinstance(content.response, list | tuple):
            value.list_value.extend(content.response)
        else:
            value.string_value = str(content.response)
        return primitives_pb2.Content(
            tool_response=primitives_pb2.ToolResponse(
                tool_id=content.tool_id, response=value
            )
        )
    else:
        raise ValueError(f"Unsupported content type: {type(content)}")


def _convert_sdk_tool_to_pb(tool: Tool) -> primitives_pb2.Tool:
    """Convert SDK Tool to protobuf Tool."""
    pb_params = [
        primitives_pb2.Parameter(
            name=param.name,
            description=param.description,
            type=param.type,
        )
        for param in tool.parameters
    ]

    pb_source = (
        primitives_pb2.SourceCode(
            language=tool.source.language,
            code=tool.source.code,
        )
        if tool.source
        else None
    )

    return primitives_pb2.Tool(
        id=tool.id,
        name=tool.name,
        description=tool.description,
        parameters=pb_params,
        parameters_json_schema=tool.parameters_json_schema,
        response=tool.response,
        response_json_schema=tool.response_json_schema,
        source=pb_source,
    )


def _convert_pb_adjudication_to_sdk(
    adjudication: primitives_pb2.Adjudication,
) -> Adjudication:
    """Convert protobuf Adjudication to SDK Adjudication."""
    # Convert decision
    decision_map = {
        primitives_pb2.DECISION_ALLOW: Decision.ALLOW,
        primitives_pb2.DECISION_DENY: Decision.DENY,
        primitives_pb2.DECISION_ESCALATE: Decision.ESCALATE,
    }

    # Convert annotations to PolicyMetadata
    policies = [
        PolicyMetadata(
            id=ann.id if ann.HasField("id") else "",
            description=ann.description if ann.HasField("description") else "",
            custom=dict(ann.custom),
        )
        for ann in adjudication.annotations
    ]

    return Adjudication(
        decision=decision_map[adjudication.decision],
        reason=adjudication.reason,
        policies=policies,
    )


def _convert_pb_agent_to_sdk(pb_agent: primitives_pb2.Agent) -> Agent:
    """Convert protobuf Agent to SDK Agent."""
    tools = []
    for pb_tool in pb_agent.tools:
        params = [
            Parameter(name=p.name, description=p.description, type=p.type)
            for p in pb_tool.parameters
        ]

        # Handle optional source field
        source = None
        if pb_tool.HasField("source"):
            source = SourceCode(
                language=pb_tool.source.language,
                code=pb_tool.source.code,
            )

        tools.append(
            Tool(
                id=pb_tool.id if pb_tool.HasField("id") else None,
                name=pb_tool.name,
                description=pb_tool.description,
                parameters=params,
                parameters_json_schema=(
                    pb_tool.parameters_json_schema
                    if pb_tool.HasField("parameters_json_schema")
                    else None
                ),
                response=pb_tool.response if pb_tool.HasField("response") else None,
                response_json_schema=(
                    pb_tool.response_json_schema
                    if pb_tool.HasField("response_json_schema")
                    else None
                ),
                source=source,
            )
        )

    return Agent(
        id=pb_agent.id,
        provider_id=pb_agent.provider_id,
        name=pb_agent.name,
        description=pb_agent.description,
        instruction=pb_agent.instruction,
        tools=tools,
    )


def _convert_pb_trajectory_status_to_sdk(
    pb_status: primitives_pb2.TrajectoryStatus,
) -> TrajectoryStatus:
    """Convert protobuf TrajectoryStatus to SDK TrajectoryStatus."""
    status_map = {
        primitives_pb2.TRAJECTORY_STATUS_UNSPECIFIED: TrajectoryStatus.UNKNOWN,
        primitives_pb2.TRAJECTORY_STATUS_PENDING: TrajectoryStatus.PENDING,
        primitives_pb2.TRAJECTORY_STATUS_RUNNING: TrajectoryStatus.RUNNING,
        primitives_pb2.TRAJECTORY_STATUS_COMPLETED: TrajectoryStatus.COMPLETED,
        primitives_pb2.TRAJECTORY_STATUS_SUSPENDED: TrajectoryStatus.SUSPENDED,
        primitives_pb2.TRAJECTORY_STATUS_FAILED: TrajectoryStatus.FAILED,
    }
    return status_map[pb_status]


def _convert_sdk_trajectory_status_to_pb(
    status: TrajectoryStatus,
) -> primitives_pb2.TrajectoryStatus:
    """Convert SDK TrajectoryStatus to protobuf TrajectoryStatus."""
    status_map = {
        TrajectoryStatus.UNKNOWN: primitives_pb2.TRAJECTORY_STATUS_UNSPECIFIED,
        TrajectoryStatus.PENDING: primitives_pb2.TRAJECTORY_STATUS_PENDING,
        TrajectoryStatus.RUNNING: primitives_pb2.TRAJECTORY_STATUS_RUNNING,
        TrajectoryStatus.COMPLETED: primitives_pb2.TRAJECTORY_STATUS_COMPLETED,
        TrajectoryStatus.SUSPENDED: primitives_pb2.TRAJECTORY_STATUS_SUSPENDED,
        TrajectoryStatus.FAILED: primitives_pb2.TRAJECTORY_STATUS_FAILED,
    }
    return status_map[status]


def _convert_pb_stage_to_sdk(pb_stage: primitives_pb2.Stage) -> Stage:
    """Convert protobuf Stage to SDK Stage."""
    stage_map = {
        primitives_pb2.STAGE_PRE_RUN: Stage.PRE_RUN,
        primitives_pb2.STAGE_PRE_MODEL: Stage.PRE_MODEL,
        primitives_pb2.STAGE_POST_MODEL: Stage.POST_MODEL,
        primitives_pb2.STAGE_PRE_TOOL: Stage.PRE_TOOL,
        primitives_pb2.STAGE_POST_TOOL: Stage.POST_TOOL,
        primitives_pb2.STAGE_POST_RUN: Stage.POST_RUN,
    }
    return stage_map[pb_stage]


def _convert_pb_role_to_sdk(pb_role: primitives_pb2.Role) -> Role:
    """Convert protobuf Role to SDK Role."""
    role_map = {
        primitives_pb2.ROLE_USER: Role.USER,
        primitives_pb2.ROLE_MODEL: Role.MODEL,
        primitives_pb2.ROLE_TOOL: Role.TOOL,
        primitives_pb2.ROLE_SYSTEM: Role.SYSTEM,
    }
    return role_map[pb_role]


def _convert_pb_content_to_sdk(pb_content: primitives_pb2.Content) -> Content:
    """Convert protobuf Content to SDK Content."""
    if pb_content.HasField("prompt"):
        return PromptContent(text=pb_content.prompt.text)
    elif pb_content.HasField("tool_request"):
        # Convert protobuf Value to Python dict
        args = {}
        if pb_content.tool_request.HasField("args"):
            args = MessageToDict(
                pb_content.tool_request.args, preserving_proto_field_name=True
            )
            if not isinstance(args, dict):
                args = {}
        return ToolRequestContent(tool_id=pb_content.tool_request.tool_id, args=args)
    elif pb_content.HasField("tool_response"):
        # Convert protobuf Value to Python value
        response = MessageToDict(
            pb_content.tool_response.response, preserving_proto_field_name=True
        )
        return ToolResponseContent(
            tool_id=pb_content.tool_response.tool_id, response=response
        )
    else:
        raise ValueError(
            f"Unsupported protobuf content type: {pb_content.WhichOneof('content_type')}"
        )


def _convert_pb_trajectory_step_to_sdk(
    pb_step: primitives_pb2.TrajectoryStep,
) -> TrajectoryStep:
    """Convert protobuf TrajectoryStep to SDK TrajectoryStep."""
    created_at = (
        datetime.fromtimestamp(pb_step.created_at.seconds, tz=UTC)
        if pb_step.HasField("created_at")
        else datetime.now(tz=UTC)
    )

    content = (
        _convert_pb_content_to_sdk(pb_step.content)
        if pb_step.HasField("content")
        else None
    )

    return TrajectoryStep(
        role=_convert_pb_role_to_sdk(pb_step.role),
        stage=_convert_pb_stage_to_sdk(pb_step.stage),
        content=content,
        created_at=created_at,
        state={},  # State is not in protobuf TrajectoryStep
        context=None,  # Context is not in protobuf TrajectoryStep
    )


def _convert_pb_adjudicated_step_to_sdk(
    pb_adjudicated_step: primitives_pb2.AdjudicatedStep,
) -> AdjudicatedStep:
    """Convert protobuf AdjudicatedStep to SDK AdjudicatedStep."""
    # Convert the step
    pb_step = pb_adjudicated_step.step if pb_adjudicated_step.HasField("step") else None
    if pb_step is None:
        raise ValueError("AdjudicatedStep must have a step field")

    trajectory_step = _convert_pb_trajectory_step_to_sdk(pb_step)

    # Convert adjudication
    pb_adjudication = (
        pb_adjudicated_step.adjudication
        if pb_adjudicated_step.HasField("adjudication")
        else None
    )
    if pb_adjudication is None:
        raise ValueError("AdjudicatedStep must have an adjudication field")
    adjudication = _convert_pb_adjudication_to_sdk(pb_adjudication)

    # Convert guardrails
    guardrails = None
    if pb_adjudicated_step.HasField("guardrails"):
        checks = {}
        for name, pb_check in pb_adjudicated_step.guardrails.checks.items():
            checks[name] = Check(
                name=pb_check.name,
                flagged=pb_check.flagged,
                message=pb_check.message if pb_check.HasField("message") else None,
            )
        guardrails = GuardrailContext(checks=checks)

    # Default mode to GOVERN since protobuf doesn't have this field
    # In practice, this should be set based on the policy engine configuration
    mode = PolicyEngineMode.GOVERN

    return AdjudicatedStep(
        mode=mode,
        adjudication=adjudication,
        step=trajectory_step,
        guardrails=guardrails,
    )


def _convert_pb_trajectory_to_sdk(
    pb_trajectory: primitives_pb2.Trajectory,
) -> Trajectory:
    """Convert protobuf Trajectory to SDK Trajectory."""
    # Convert timestamps
    created_at = (
        datetime.fromtimestamp(pb_trajectory.created_at.seconds, tz=UTC)
        if pb_trajectory.HasField("created_at")
        else datetime.now(tz=UTC)
    )
    updated_at = (
        datetime.fromtimestamp(pb_trajectory.updated_at.seconds, tz=UTC)
        if pb_trajectory.HasField("updated_at")
        else datetime.now(tz=UTC)
    )
    started_at = (
        datetime.fromtimestamp(pb_trajectory.started_at.seconds, tz=UTC)
        if pb_trajectory.HasField("started_at")
        else None
    )
    ended_at = (
        datetime.fromtimestamp(pb_trajectory.ended_at.seconds, tz=UTC)
        if pb_trajectory.HasField("ended_at")
        else None
    )

    # Convert metadata (protobuf map<string, Value> to dict)
    metadata = {
        key: MessageToDict(value, preserving_proto_field_name=True)
        for key, value in pb_trajectory.metadata.items()
    }

    return Trajectory(
        id=pb_trajectory.id,
        agent_id=pb_trajectory.agent_id,
        status=_convert_pb_trajectory_status_to_sdk(pb_trajectory.status),
        metadata=metadata,
        created_at=created_at,
        updated_at=updated_at,
        started_at=started_at,
        ended_at=ended_at,
        steps=[],  # Steps are not included in the basic trajectory response
    )


def _convert_pb_adjudicated_trajectory_to_sdk(
    pb_response: harness_pb2.GetTrajectoryResponse,
) -> AdjudicatedTrajectory:
    """Convert protobuf GetTrajectoryResponse to SDK AdjudicatedTrajectory."""
    # Convert the trajectory
    pb_trajectory = (
        pb_response.trajectory if pb_response.HasField("trajectory") else None
    )
    if pb_trajectory is None:
        raise ValueError("GetTrajectoryResponse must have a trajectory field")

    trajectory = _convert_pb_trajectory_to_sdk(pb_trajectory)

    # Convert adjudicated steps
    adjudicated_steps = [
        _convert_pb_adjudicated_step_to_sdk(pb_step) for pb_step in pb_response.steps
    ]

    # Exclude steps from trajectory.model_dump() since AdjudicatedTrajectory uses AdjudicatedStep instead
    trajectory_dict = trajectory.model_dump(exclude={"steps"})
    return AdjudicatedTrajectory(**trajectory_dict, steps=adjudicated_steps)


def _convert_pb_adjudication_record_to_sdk(
    pb_record: harness_pb2.AdjudicationRecord,
) -> AdjudicationRecord:
    """Convert protobuf AdjudicationRecord to SDK AdjudicationRecord."""
    adjudication = _convert_pb_adjudication_to_sdk(pb_record.adjudication)
    return AdjudicationRecord(
        agent_id=pb_record.agent_id,
        trajectory_id=pb_record.trajectory_id,
        step_id=pb_record.step_id,
        adjudication=adjudication,
    )
