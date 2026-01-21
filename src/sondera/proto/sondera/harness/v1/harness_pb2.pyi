import datetime

from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from sondera.core.v1 import primitives_pb2 as _primitives_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class RegisterAgentRequest(_message.Message):
    __slots__ = ("provider_id", "name", "description", "instruction", "tools")
    PROVIDER_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    INSTRUCTION_FIELD_NUMBER: _ClassVar[int]
    TOOLS_FIELD_NUMBER: _ClassVar[int]
    provider_id: str
    name: str
    description: str
    instruction: str
    tools: _containers.RepeatedCompositeFieldContainer[_primitives_pb2.Tool]
    def __init__(self, provider_id: _Optional[str] = ..., name: _Optional[str] = ..., description: _Optional[str] = ..., instruction: _Optional[str] = ..., tools: _Optional[_Iterable[_Union[_primitives_pb2.Tool, _Mapping]]] = ...) -> None: ...

class RegisterAgentResponse(_message.Message):
    __slots__ = ("agent",)
    AGENT_FIELD_NUMBER: _ClassVar[int]
    agent: _primitives_pb2.Agent
    def __init__(self, agent: _Optional[_Union[_primitives_pb2.Agent, _Mapping]] = ...) -> None: ...

class GetAgentRequest(_message.Message):
    __slots__ = ("agent_id",)
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    agent_id: str
    def __init__(self, agent_id: _Optional[str] = ...) -> None: ...

class GetAgentResponse(_message.Message):
    __slots__ = ("agent",)
    AGENT_FIELD_NUMBER: _ClassVar[int]
    agent: _primitives_pb2.Agent
    def __init__(self, agent: _Optional[_Union[_primitives_pb2.Agent, _Mapping]] = ...) -> None: ...

class CreateTrajectoryRequest(_message.Message):
    __slots__ = ("agent_id",)
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    agent_id: str
    def __init__(self, agent_id: _Optional[str] = ...) -> None: ...

class CreateTrajectoryResponse(_message.Message):
    __slots__ = ("trajectory",)
    TRAJECTORY_FIELD_NUMBER: _ClassVar[int]
    trajectory: _primitives_pb2.Trajectory
    def __init__(self, trajectory: _Optional[_Union[_primitives_pb2.Trajectory, _Mapping]] = ...) -> None: ...

class AddTrajectoryStepRequest(_message.Message):
    __slots__ = ("trajectory_id", "stage", "role", "content")
    TRAJECTORY_ID_FIELD_NUMBER: _ClassVar[int]
    STAGE_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    trajectory_id: str
    stage: _primitives_pb2.Stage
    role: _primitives_pb2.Role
    content: _primitives_pb2.Content
    def __init__(self, trajectory_id: _Optional[str] = ..., stage: _Optional[_Union[_primitives_pb2.Stage, str]] = ..., role: _Optional[_Union[_primitives_pb2.Role, str]] = ..., content: _Optional[_Union[_primitives_pb2.Content, _Mapping]] = ...) -> None: ...

class AddTrajectoryStepResponse(_message.Message):
    __slots__ = ("adjudicated_step",)
    ADJUDICATED_STEP_FIELD_NUMBER: _ClassVar[int]
    adjudicated_step: _primitives_pb2.AdjudicatedStep
    def __init__(self, adjudicated_step: _Optional[_Union[_primitives_pb2.AdjudicatedStep, _Mapping]] = ...) -> None: ...

class UpdateTrajectoryStatusRequest(_message.Message):
    __slots__ = ("trajectory_id", "status")
    TRAJECTORY_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    trajectory_id: str
    status: _primitives_pb2.TrajectoryStatus
    def __init__(self, trajectory_id: _Optional[str] = ..., status: _Optional[_Union[_primitives_pb2.TrajectoryStatus, str]] = ...) -> None: ...

class UpdateTrajectoryStatusResponse(_message.Message):
    __slots__ = ("trajectory",)
    TRAJECTORY_FIELD_NUMBER: _ClassVar[int]
    trajectory: _primitives_pb2.Trajectory
    def __init__(self, trajectory: _Optional[_Union[_primitives_pb2.Trajectory, _Mapping]] = ...) -> None: ...

class GetTrajectoryRequest(_message.Message):
    __slots__ = ("trajectory_id",)
    TRAJECTORY_ID_FIELD_NUMBER: _ClassVar[int]
    trajectory_id: str
    def __init__(self, trajectory_id: _Optional[str] = ...) -> None: ...

class GetTrajectoryResponse(_message.Message):
    __slots__ = ("trajectory", "steps")
    TRAJECTORY_FIELD_NUMBER: _ClassVar[int]
    STEPS_FIELD_NUMBER: _ClassVar[int]
    trajectory: _primitives_pb2.Trajectory
    steps: _containers.RepeatedCompositeFieldContainer[_primitives_pb2.AdjudicatedStep]
    def __init__(self, trajectory: _Optional[_Union[_primitives_pb2.Trajectory, _Mapping]] = ..., steps: _Optional[_Iterable[_Union[_primitives_pb2.AdjudicatedStep, _Mapping]]] = ...) -> None: ...

class ListTrajectoriesRequest(_message.Message):
    __slots__ = ("agent_id", "status", "page_size", "page_token")
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    PAGE_SIZE_FIELD_NUMBER: _ClassVar[int]
    PAGE_TOKEN_FIELD_NUMBER: _ClassVar[int]
    agent_id: str
    status: _primitives_pb2.TrajectoryStatus
    page_size: int
    page_token: str
    def __init__(self, agent_id: _Optional[str] = ..., status: _Optional[_Union[_primitives_pb2.TrajectoryStatus, str]] = ..., page_size: _Optional[int] = ..., page_token: _Optional[str] = ...) -> None: ...

class ListTrajectoriesResponse(_message.Message):
    __slots__ = ("trajectories", "next_page_token")
    TRAJECTORIES_FIELD_NUMBER: _ClassVar[int]
    NEXT_PAGE_TOKEN_FIELD_NUMBER: _ClassVar[int]
    trajectories: _containers.RepeatedCompositeFieldContainer[_primitives_pb2.Trajectory]
    next_page_token: str
    def __init__(self, trajectories: _Optional[_Iterable[_Union[_primitives_pb2.Trajectory, _Mapping]]] = ..., next_page_token: _Optional[str] = ...) -> None: ...

class ListAgentsRequest(_message.Message):
    __slots__ = ("provider_id", "page_size", "page_token")
    PROVIDER_ID_FIELD_NUMBER: _ClassVar[int]
    PAGE_SIZE_FIELD_NUMBER: _ClassVar[int]
    PAGE_TOKEN_FIELD_NUMBER: _ClassVar[int]
    provider_id: str
    page_size: int
    page_token: str
    def __init__(self, provider_id: _Optional[str] = ..., page_size: _Optional[int] = ..., page_token: _Optional[str] = ...) -> None: ...

class ListAgentsResponse(_message.Message):
    __slots__ = ("agents", "next_page_token")
    AGENTS_FIELD_NUMBER: _ClassVar[int]
    NEXT_PAGE_TOKEN_FIELD_NUMBER: _ClassVar[int]
    agents: _containers.RepeatedCompositeFieldContainer[_primitives_pb2.Agent]
    next_page_token: str
    def __init__(self, agents: _Optional[_Iterable[_Union[_primitives_pb2.Agent, _Mapping]]] = ..., next_page_token: _Optional[str] = ...) -> None: ...

class AnalyzeTrajectoriesRequest(_message.Message):
    __slots__ = ("agent_id", "start_time", "end_time", "analytics")
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    START_TIME_FIELD_NUMBER: _ClassVar[int]
    END_TIME_FIELD_NUMBER: _ClassVar[int]
    ANALYTICS_FIELD_NUMBER: _ClassVar[int]
    agent_id: str
    start_time: _timestamp_pb2.Timestamp
    end_time: _timestamp_pb2.Timestamp
    analytics: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, agent_id: _Optional[str] = ..., start_time: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., end_time: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., analytics: _Optional[_Iterable[str]] = ...) -> None: ...

class AnalyzeTrajectoriesResponse(_message.Message):
    __slots__ = ("analytics", "trajectory_count", "computed_at")
    ANALYTICS_FIELD_NUMBER: _ClassVar[int]
    TRAJECTORY_COUNT_FIELD_NUMBER: _ClassVar[int]
    COMPUTED_AT_FIELD_NUMBER: _ClassVar[int]
    analytics: _struct_pb2.Struct
    trajectory_count: int
    computed_at: _timestamp_pb2.Timestamp
    def __init__(self, analytics: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., trajectory_count: _Optional[int] = ..., computed_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class ListAdjudicationsRequest(_message.Message):
    __slots__ = ("agent_id", "page_size", "page_token")
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    PAGE_SIZE_FIELD_NUMBER: _ClassVar[int]
    PAGE_TOKEN_FIELD_NUMBER: _ClassVar[int]
    agent_id: str
    page_size: int
    page_token: str
    def __init__(self, agent_id: _Optional[str] = ..., page_size: _Optional[int] = ..., page_token: _Optional[str] = ...) -> None: ...

class AdjudicationRecord(_message.Message):
    __slots__ = ("agent_id", "trajectory_id", "step_id", "adjudication")
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    TRAJECTORY_ID_FIELD_NUMBER: _ClassVar[int]
    STEP_ID_FIELD_NUMBER: _ClassVar[int]
    ADJUDICATION_FIELD_NUMBER: _ClassVar[int]
    agent_id: str
    trajectory_id: str
    step_id: str
    adjudication: _primitives_pb2.Adjudication
    def __init__(self, agent_id: _Optional[str] = ..., trajectory_id: _Optional[str] = ..., step_id: _Optional[str] = ..., adjudication: _Optional[_Union[_primitives_pb2.Adjudication, _Mapping]] = ...) -> None: ...

class ListAdjudicationsResponse(_message.Message):
    __slots__ = ("adjudications", "next_page_token")
    ADJUDICATIONS_FIELD_NUMBER: _ClassVar[int]
    NEXT_PAGE_TOKEN_FIELD_NUMBER: _ClassVar[int]
    adjudications: _containers.RepeatedCompositeFieldContainer[AdjudicationRecord]
    next_page_token: str
    def __init__(self, adjudications: _Optional[_Iterable[_Union[AdjudicationRecord, _Mapping]]] = ..., next_page_token: _Optional[str] = ...) -> None: ...
