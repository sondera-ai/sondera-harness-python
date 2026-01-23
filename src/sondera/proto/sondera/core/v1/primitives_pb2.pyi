import datetime

from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class TrajectoryStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TRAJECTORY_STATUS_UNSPECIFIED: _ClassVar[TrajectoryStatus]
    TRAJECTORY_STATUS_PENDING: _ClassVar[TrajectoryStatus]
    TRAJECTORY_STATUS_RUNNING: _ClassVar[TrajectoryStatus]
    TRAJECTORY_STATUS_COMPLETED: _ClassVar[TrajectoryStatus]
    TRAJECTORY_STATUS_SUSPENDED: _ClassVar[TrajectoryStatus]
    TRAJECTORY_STATUS_FAILED: _ClassVar[TrajectoryStatus]

class Stage(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    STAGE_UNSPECIFIED: _ClassVar[Stage]
    STAGE_PRE_RUN: _ClassVar[Stage]
    STAGE_PRE_MODEL: _ClassVar[Stage]
    STAGE_POST_MODEL: _ClassVar[Stage]
    STAGE_PRE_TOOL: _ClassVar[Stage]
    STAGE_POST_TOOL: _ClassVar[Stage]
    STAGE_POST_RUN: _ClassVar[Stage]

class Role(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ROLE_UNSPECIFIED: _ClassVar[Role]
    ROLE_USER: _ClassVar[Role]
    ROLE_MODEL: _ClassVar[Role]
    ROLE_TOOL: _ClassVar[Role]
    ROLE_SYSTEM: _ClassVar[Role]

class Decision(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    DECISION_UNSPECIFIED: _ClassVar[Decision]
    DECISION_ALLOW: _ClassVar[Decision]
    DECISION_DENY: _ClassVar[Decision]
    DECISION_ESCALATE: _ClassVar[Decision]
TRAJECTORY_STATUS_UNSPECIFIED: TrajectoryStatus
TRAJECTORY_STATUS_PENDING: TrajectoryStatus
TRAJECTORY_STATUS_RUNNING: TrajectoryStatus
TRAJECTORY_STATUS_COMPLETED: TrajectoryStatus
TRAJECTORY_STATUS_SUSPENDED: TrajectoryStatus
TRAJECTORY_STATUS_FAILED: TrajectoryStatus
STAGE_UNSPECIFIED: Stage
STAGE_PRE_RUN: Stage
STAGE_PRE_MODEL: Stage
STAGE_POST_MODEL: Stage
STAGE_PRE_TOOL: Stage
STAGE_POST_TOOL: Stage
STAGE_POST_RUN: Stage
ROLE_UNSPECIFIED: Role
ROLE_USER: Role
ROLE_MODEL: Role
ROLE_TOOL: Role
ROLE_SYSTEM: Role
DECISION_UNSPECIFIED: Decision
DECISION_ALLOW: Decision
DECISION_DENY: Decision
DECISION_ESCALATE: Decision

class SourceCode(_message.Message):
    __slots__ = ("language", "code")
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    CODE_FIELD_NUMBER: _ClassVar[int]
    language: str
    code: str
    def __init__(self, language: _Optional[str] = ..., code: _Optional[str] = ...) -> None: ...

class Parameter(_message.Message):
    __slots__ = ("name", "description", "type")
    NAME_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    name: str
    description: str
    type: str
    def __init__(self, name: _Optional[str] = ..., description: _Optional[str] = ..., type: _Optional[str] = ...) -> None: ...

class Tool(_message.Message):
    __slots__ = ("id", "name", "description", "parameters", "parameters_json_schema", "response", "response_json_schema", "source")
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    PARAMETERS_FIELD_NUMBER: _ClassVar[int]
    PARAMETERS_JSON_SCHEMA_FIELD_NUMBER: _ClassVar[int]
    RESPONSE_FIELD_NUMBER: _ClassVar[int]
    RESPONSE_JSON_SCHEMA_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    id: str
    name: str
    description: str
    parameters: _containers.RepeatedCompositeFieldContainer[Parameter]
    parameters_json_schema: str
    response: str
    response_json_schema: str
    source: SourceCode
    def __init__(self, id: _Optional[str] = ..., name: _Optional[str] = ..., description: _Optional[str] = ..., parameters: _Optional[_Iterable[_Union[Parameter, _Mapping]]] = ..., parameters_json_schema: _Optional[str] = ..., response: _Optional[str] = ..., response_json_schema: _Optional[str] = ..., source: _Optional[_Union[SourceCode, _Mapping]] = ...) -> None: ...

class Agent(_message.Message):
    __slots__ = ("id", "provider_id", "name", "description", "instruction", "tools")
    ID_FIELD_NUMBER: _ClassVar[int]
    PROVIDER_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    INSTRUCTION_FIELD_NUMBER: _ClassVar[int]
    TOOLS_FIELD_NUMBER: _ClassVar[int]
    id: str
    provider_id: str
    name: str
    description: str
    instruction: str
    tools: _containers.RepeatedCompositeFieldContainer[Tool]
    def __init__(self, id: _Optional[str] = ..., provider_id: _Optional[str] = ..., name: _Optional[str] = ..., description: _Optional[str] = ..., instruction: _Optional[str] = ..., tools: _Optional[_Iterable[_Union[Tool, _Mapping]]] = ...) -> None: ...

class Prompt(_message.Message):
    __slots__ = ("text",)
    TEXT_FIELD_NUMBER: _ClassVar[int]
    text: str
    def __init__(self, text: _Optional[str] = ...) -> None: ...

class ToolRequest(_message.Message):
    __slots__ = ("tool_id", "args")
    TOOL_ID_FIELD_NUMBER: _ClassVar[int]
    ARGS_FIELD_NUMBER: _ClassVar[int]
    tool_id: str
    args: _struct_pb2.Value
    def __init__(self, tool_id: _Optional[str] = ..., args: _Optional[_Union[_struct_pb2.Value, _Mapping]] = ...) -> None: ...

class ToolResponse(_message.Message):
    __slots__ = ("tool_id", "response")
    TOOL_ID_FIELD_NUMBER: _ClassVar[int]
    RESPONSE_FIELD_NUMBER: _ClassVar[int]
    tool_id: str
    response: _struct_pb2.Value
    def __init__(self, tool_id: _Optional[str] = ..., response: _Optional[_Union[_struct_pb2.Value, _Mapping]] = ...) -> None: ...

class Content(_message.Message):
    __slots__ = ("prompt", "tool_request", "tool_response")
    PROMPT_FIELD_NUMBER: _ClassVar[int]
    TOOL_REQUEST_FIELD_NUMBER: _ClassVar[int]
    TOOL_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    prompt: Prompt
    tool_request: ToolRequest
    tool_response: ToolResponse
    def __init__(self, prompt: _Optional[_Union[Prompt, _Mapping]] = ..., tool_request: _Optional[_Union[ToolRequest, _Mapping]] = ..., tool_response: _Optional[_Union[ToolResponse, _Mapping]] = ...) -> None: ...

class TrajectoryStep(_message.Message):
    __slots__ = ("stage", "role", "created_at", "content")
    STAGE_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    stage: Stage
    role: Role
    created_at: _timestamp_pb2.Timestamp
    content: Content
    def __init__(self, stage: _Optional[_Union[Stage, str]] = ..., role: _Optional[_Union[Role, str]] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., content: _Optional[_Union[Content, _Mapping]] = ...) -> None: ...

class Trajectory(_message.Message):
    __slots__ = ("id", "agent_id", "status", "metadata", "created_at", "updated_at", "started_at", "ended_at", "steps")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: _struct_pb2.Value
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[_struct_pb2.Value, _Mapping]] = ...) -> None: ...
    ID_FIELD_NUMBER: _ClassVar[int]
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    STARTED_AT_FIELD_NUMBER: _ClassVar[int]
    ENDED_AT_FIELD_NUMBER: _ClassVar[int]
    STEPS_FIELD_NUMBER: _ClassVar[int]
    id: str
    agent_id: str
    status: TrajectoryStatus
    metadata: _containers.MessageMap[str, _struct_pb2.Value]
    created_at: _timestamp_pb2.Timestamp
    updated_at: _timestamp_pb2.Timestamp
    started_at: _timestamp_pb2.Timestamp
    ended_at: _timestamp_pb2.Timestamp
    steps: _containers.RepeatedCompositeFieldContainer[TrajectoryStep]
    def __init__(self, id: _Optional[str] = ..., agent_id: _Optional[str] = ..., status: _Optional[_Union[TrajectoryStatus, str]] = ..., metadata: _Optional[_Mapping[str, _struct_pb2.Value]] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., updated_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., started_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., ended_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., steps: _Optional[_Iterable[_Union[TrajectoryStep, _Mapping]]] = ...) -> None: ...

class Check(_message.Message):
    __slots__ = ("name", "flagged", "message")
    NAME_FIELD_NUMBER: _ClassVar[int]
    FLAGGED_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    name: str
    flagged: bool
    message: str
    def __init__(self, name: _Optional[str] = ..., flagged: bool = ..., message: _Optional[str] = ...) -> None: ...

class GuardrailContext(_message.Message):
    __slots__ = ("checks",)
    class ChecksEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: Check
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[Check, _Mapping]] = ...) -> None: ...
    CHECKS_FIELD_NUMBER: _ClassVar[int]
    checks: _containers.MessageMap[str, Check]
    def __init__(self, checks: _Optional[_Mapping[str, Check]] = ...) -> None: ...

class PolicyAnnotations(_message.Message):
    __slots__ = ("id", "description", "custom")
    class CustomEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    ID_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    CUSTOM_FIELD_NUMBER: _ClassVar[int]
    id: str
    description: str
    custom: _containers.ScalarMap[str, str]
    def __init__(self, id: _Optional[str] = ..., description: _Optional[str] = ..., custom: _Optional[_Mapping[str, str]] = ...) -> None: ...

class Adjudication(_message.Message):
    __slots__ = ("decision", "reason", "policy_ids", "annotations")
    DECISION_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    POLICY_IDS_FIELD_NUMBER: _ClassVar[int]
    ANNOTATIONS_FIELD_NUMBER: _ClassVar[int]
    decision: Decision
    reason: str
    policy_ids: _containers.RepeatedScalarFieldContainer[str]
    annotations: _containers.RepeatedCompositeFieldContainer[PolicyAnnotations]
    def __init__(self, decision: _Optional[_Union[Decision, str]] = ..., reason: _Optional[str] = ..., policy_ids: _Optional[_Iterable[str]] = ..., annotations: _Optional[_Iterable[_Union[PolicyAnnotations, _Mapping]]] = ...) -> None: ...

class AdjudicatedStep(_message.Message):
    __slots__ = ("step", "guardrails", "adjudication")
    STEP_FIELD_NUMBER: _ClassVar[int]
    GUARDRAILS_FIELD_NUMBER: _ClassVar[int]
    ADJUDICATION_FIELD_NUMBER: _ClassVar[int]
    step: TrajectoryStep
    guardrails: GuardrailContext
    adjudication: Adjudication
    def __init__(self, step: _Optional[_Union[TrajectoryStep, _Mapping]] = ..., guardrails: _Optional[_Union[GuardrailContext, _Mapping]] = ..., adjudication: _Optional[_Union[Adjudication, _Mapping]] = ...) -> None: ...

class AdjudicatedTrajectory(_message.Message):
    __slots__ = ("trajectory", "steps")
    TRAJECTORY_FIELD_NUMBER: _ClassVar[int]
    STEPS_FIELD_NUMBER: _ClassVar[int]
    trajectory: Trajectory
    steps: _containers.RepeatedCompositeFieldContainer[AdjudicatedStep]
    def __init__(self, trajectory: _Optional[_Union[Trajectory, _Mapping]] = ..., steps: _Optional[_Iterable[_Union[AdjudicatedStep, _Mapping]]] = ...) -> None: ...
