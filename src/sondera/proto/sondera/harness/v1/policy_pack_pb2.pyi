import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class PolicyPackMetadata(_message.Message):
    __slots__ = ("id", "version", "name", "description", "namespace", "dependencies", "created_at", "etag")
    ID_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    NAMESPACE_FIELD_NUMBER: _ClassVar[int]
    DEPENDENCIES_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    ETAG_FIELD_NUMBER: _ClassVar[int]
    id: str
    version: str
    name: str
    description: str
    namespace: str
    dependencies: _containers.RepeatedScalarFieldContainer[str]
    created_at: _timestamp_pb2.Timestamp
    etag: str
    def __init__(self, id: _Optional[str] = ..., version: _Optional[str] = ..., name: _Optional[str] = ..., description: _Optional[str] = ..., namespace: _Optional[str] = ..., dependencies: _Optional[_Iterable[str]] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., etag: _Optional[str] = ...) -> None: ...

class PolicyPack(_message.Message):
    __slots__ = ("metadata", "policies", "entities_json", "schema_json")
    METADATA_FIELD_NUMBER: _ClassVar[int]
    POLICIES_FIELD_NUMBER: _ClassVar[int]
    ENTITIES_JSON_FIELD_NUMBER: _ClassVar[int]
    SCHEMA_JSON_FIELD_NUMBER: _ClassVar[int]
    metadata: PolicyPackMetadata
    policies: str
    entities_json: str
    schema_json: str
    def __init__(self, metadata: _Optional[_Union[PolicyPackMetadata, _Mapping]] = ..., policies: _Optional[str] = ..., entities_json: _Optional[str] = ..., schema_json: _Optional[str] = ...) -> None: ...

class PolicyPackConfig(_message.Message):
    __slots__ = ("storage_backend", "local_path", "gcs_bucket", "gcs_prefix", "poll_interval_secs", "hot_reload_enabled")
    class StorageBackend(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        STORAGE_BACKEND_UNSPECIFIED: _ClassVar[PolicyPackConfig.StorageBackend]
        STORAGE_BACKEND_LOCAL: _ClassVar[PolicyPackConfig.StorageBackend]
        STORAGE_BACKEND_GCS: _ClassVar[PolicyPackConfig.StorageBackend]
    STORAGE_BACKEND_UNSPECIFIED: PolicyPackConfig.StorageBackend
    STORAGE_BACKEND_LOCAL: PolicyPackConfig.StorageBackend
    STORAGE_BACKEND_GCS: PolicyPackConfig.StorageBackend
    STORAGE_BACKEND_FIELD_NUMBER: _ClassVar[int]
    LOCAL_PATH_FIELD_NUMBER: _ClassVar[int]
    GCS_BUCKET_FIELD_NUMBER: _ClassVar[int]
    GCS_PREFIX_FIELD_NUMBER: _ClassVar[int]
    POLL_INTERVAL_SECS_FIELD_NUMBER: _ClassVar[int]
    HOT_RELOAD_ENABLED_FIELD_NUMBER: _ClassVar[int]
    storage_backend: PolicyPackConfig.StorageBackend
    local_path: str
    gcs_bucket: str
    gcs_prefix: str
    poll_interval_secs: int
    hot_reload_enabled: bool
    def __init__(self, storage_backend: _Optional[_Union[PolicyPackConfig.StorageBackend, str]] = ..., local_path: _Optional[str] = ..., gcs_bucket: _Optional[str] = ..., gcs_prefix: _Optional[str] = ..., poll_interval_secs: _Optional[int] = ..., hot_reload_enabled: bool = ...) -> None: ...

class ListPolicyPacksRequest(_message.Message):
    __slots__ = ("organization_id", "agent_id", "page_size", "page_token")
    ORGANIZATION_ID_FIELD_NUMBER: _ClassVar[int]
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    PAGE_SIZE_FIELD_NUMBER: _ClassVar[int]
    PAGE_TOKEN_FIELD_NUMBER: _ClassVar[int]
    organization_id: str
    agent_id: str
    page_size: int
    page_token: str
    def __init__(self, organization_id: _Optional[str] = ..., agent_id: _Optional[str] = ..., page_size: _Optional[int] = ..., page_token: _Optional[str] = ...) -> None: ...

class ListPolicyPacksResponse(_message.Message):
    __slots__ = ("packs", "next_page_token")
    PACKS_FIELD_NUMBER: _ClassVar[int]
    NEXT_PAGE_TOKEN_FIELD_NUMBER: _ClassVar[int]
    packs: _containers.RepeatedCompositeFieldContainer[PolicyPackMetadata]
    next_page_token: str
    def __init__(self, packs: _Optional[_Iterable[_Union[PolicyPackMetadata, _Mapping]]] = ..., next_page_token: _Optional[str] = ...) -> None: ...

class GetPolicyPackRequest(_message.Message):
    __slots__ = ("pack_id", "version")
    PACK_ID_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    pack_id: str
    version: str
    def __init__(self, pack_id: _Optional[str] = ..., version: _Optional[str] = ...) -> None: ...

class GetPolicyPackResponse(_message.Message):
    __slots__ = ("pack",)
    PACK_FIELD_NUMBER: _ClassVar[int]
    pack: PolicyPack
    def __init__(self, pack: _Optional[_Union[PolicyPack, _Mapping]] = ...) -> None: ...

class GetAgentPolicyInfoRequest(_message.Message):
    __slots__ = ("organization_id", "agent_id")
    ORGANIZATION_ID_FIELD_NUMBER: _ClassVar[int]
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    organization_id: str
    agent_id: str
    def __init__(self, organization_id: _Optional[str] = ..., agent_id: _Optional[str] = ...) -> None: ...

class GetAgentPolicyInfoResponse(_message.Message):
    __slots__ = ("source_packs", "namespace", "policy_count", "policy_ids")
    SOURCE_PACKS_FIELD_NUMBER: _ClassVar[int]
    NAMESPACE_FIELD_NUMBER: _ClassVar[int]
    POLICY_COUNT_FIELD_NUMBER: _ClassVar[int]
    POLICY_IDS_FIELD_NUMBER: _ClassVar[int]
    source_packs: _containers.RepeatedCompositeFieldContainer[PolicyPackMetadata]
    namespace: str
    policy_count: int
    policy_ids: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, source_packs: _Optional[_Iterable[_Union[PolicyPackMetadata, _Mapping]]] = ..., namespace: _Optional[str] = ..., policy_count: _Optional[int] = ..., policy_ids: _Optional[_Iterable[str]] = ...) -> None: ...

class ListPolicyPackVersionsRequest(_message.Message):
    __slots__ = ("pack_id",)
    PACK_ID_FIELD_NUMBER: _ClassVar[int]
    pack_id: str
    def __init__(self, pack_id: _Optional[str] = ...) -> None: ...

class ListPolicyPackVersionsResponse(_message.Message):
    __slots__ = ("versions",)
    VERSIONS_FIELD_NUMBER: _ClassVar[int]
    versions: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, versions: _Optional[_Iterable[str]] = ...) -> None: ...

class RollbackAgentRequest(_message.Message):
    __slots__ = ("organization_id", "agent_id", "version")
    ORGANIZATION_ID_FIELD_NUMBER: _ClassVar[int]
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    organization_id: str
    agent_id: str
    version: str
    def __init__(self, organization_id: _Optional[str] = ..., agent_id: _Optional[str] = ..., version: _Optional[str] = ...) -> None: ...

class RollbackAgentResponse(_message.Message):
    __slots__ = ("success", "active_pack")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_PACK_FIELD_NUMBER: _ClassVar[int]
    success: bool
    active_pack: PolicyPackMetadata
    def __init__(self, success: bool = ..., active_pack: _Optional[_Union[PolicyPackMetadata, _Mapping]] = ...) -> None: ...

class UploadPolicyPackRequest(_message.Message):
    __slots__ = ("pack_id", "pack", "set_as_latest")
    PACK_ID_FIELD_NUMBER: _ClassVar[int]
    PACK_FIELD_NUMBER: _ClassVar[int]
    SET_AS_LATEST_FIELD_NUMBER: _ClassVar[int]
    pack_id: str
    pack: PolicyPack
    set_as_latest: bool
    def __init__(self, pack_id: _Optional[str] = ..., pack: _Optional[_Union[PolicyPack, _Mapping]] = ..., set_as_latest: bool = ...) -> None: ...

class UploadPolicyPackResponse(_message.Message):
    __slots__ = ("success", "metadata")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    success: bool
    metadata: PolicyPackMetadata
    def __init__(self, success: bool = ..., metadata: _Optional[_Union[PolicyPackMetadata, _Mapping]] = ...) -> None: ...

class ReloadPolicyPacksRequest(_message.Message):
    __slots__ = ("organization_id", "agent_id")
    ORGANIZATION_ID_FIELD_NUMBER: _ClassVar[int]
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    organization_id: str
    agent_id: str
    def __init__(self, organization_id: _Optional[str] = ..., agent_id: _Optional[str] = ...) -> None: ...

class ReloadPolicyPacksResponse(_message.Message):
    __slots__ = ("agents_reloaded", "success")
    AGENTS_RELOADED_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    agents_reloaded: int
    success: bool
    def __init__(self, agents_reloaded: _Optional[int] = ..., success: bool = ...) -> None: ...
