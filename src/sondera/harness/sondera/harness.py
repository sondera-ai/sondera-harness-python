"""Async GRPC client for the Sondera Harness Service."""

import logging
from datetime import UTC, datetime
from typing import Any

import grpc
from google.protobuf.json_format import MessageToDict
from google.protobuf.timestamp_pb2 import Timestamp

from sondera.exceptions import (
    AuthenticationError,
    ConfigurationError,
    TrajectoryError,
    TrajectoryNotInitializedError,
)
from sondera.harness.abc import Harness as AbstractHarness
from sondera.harness.sondera._grpc import (
    _convert_pb_adjudicated_trajectory_to_sdk,
    _convert_pb_adjudication_record_to_sdk,
    _convert_pb_adjudication_to_sdk,
    _convert_pb_agent_to_sdk,
    _convert_pb_trajectory_to_sdk,
    _convert_sdk_content_to_pb,
    _convert_sdk_role_to_pb,
    _convert_sdk_stage_to_pb,
    _convert_sdk_tool_to_pb,
    _convert_sdk_trajectory_status_to_pb,
)
from sondera.proto.sondera.core.v1 import primitives_pb2
from sondera.proto.sondera.harness.v1 import harness_pb2, harness_pb2_grpc
from sondera.settings import SETTINGS
from sondera.types import (
    AdjudicatedTrajectory,
    Adjudication,
    AdjudicationRecord,
    Agent,
    Content,
    Role,
    Stage,
    Trajectory,
    TrajectoryStatus,
)


class SonderaRemoteHarness(AbstractHarness):
    """gRPC-based Harness implementation for the Sondera Platform.

    Example:
        ```python
        from sondera.harness import Harness
        from sondera.types import Agent, Stage, Role, PromptContent

        harness = Harness(
            sondera_harness_endpoint="localhost:50051",
            sondera_api_key="<YOUR_SONDERA_API_KEY>",
            agent=Agent(
                id="my-agent",
                provider_id="my-provider",
                name="My Agent",
                description="An agent with Sondera governance",
                instruction="Be helpful",
                tools=[],
            ),
        )

        await harness.initialize()
        adjudication = await harness.adjudicate(
            Stage.PRE_MODEL,
            Role.USER,
            PromptContent(text="Hello, world!"),
        )
        await harness.finalize()
        ```
    """

    def __init__(
        self,
        *,
        agent: Agent | None = None,
        sondera_harness_endpoint: str = SETTINGS.sondera_harness_endpoint,
        sondera_api_key: str | None = SETTINGS.sondera_api_token,
        sondera_harness_client_secure: bool = SETTINGS.sondera_harness_client_secure,
        sondera_harness_client_options: list[tuple] | None = None,
    ):
        """Initialize the harness.

        Args:
            agent: The agent to be governed
            sondera_harness_endpoint: The endpoint of the Sondera Harness service
            sondera_api_key: JWT token for authentication (required, must include organization_id claim)
            sondera_harness_client_secure: Whether to use a secure (TLS) connection
            sondera_harness_client_options: Optional gRPC channel options

        Raises:
            ConfigurationError: If sondera_api_key is None or empty

        Note:
            The organization_id for multi-tenancy is now derived from the JWT token's organization_id claim.
            Ensure your Clerk JWT template includes: {{org.public_metadata.organization_id}}
        """
        # Validate sondera_api_key
        if not sondera_api_key:
            raise ConfigurationError(
                "sondera_api_key is required and cannot be None or empty"
            )

        self._sondera_api_key = sondera_api_key
        self._agent: Agent | None = agent
        self._sondera_harness_endpoint = sondera_harness_endpoint
        self._secure = sondera_harness_client_secure
        self._options = sondera_harness_client_options or []
        # Client connection state
        self._channel: grpc.aio.Channel | None = None
        self._stub: harness_pb2_grpc.HarnessServiceStub | None = None

        # Current trajectory state
        self._trajectory_id: str | None = None

    def _get_metadata(self) -> list[tuple[str, str]]:
        """Build gRPC metadata with JWT auth token.

        The JWT token includes the organization_id claim, which is extracted by the
        Harness service for tenant isolation.

        Returns:
            List of metadata tuples to pass to gRPC calls
        """
        metadata: list[tuple[str, str]] = [
            ("authorization", f"Bearer {self._sondera_api_key}")
        ]
        return metadata

    async def initialize(
        self,
        *,
        agent: Agent | None = None,
    ) -> None:
        """Initialize a new trajectory for the current execution."""
        await self._ensure_connected()
        assert self._stub is not None, "Client not connected"
        if agent:
            self._agent = agent
        assert self._agent is not None, (
            "Agent not provided on initialization or in constructor."
        )
        # Get or register an agent
        try:
            await self._get_agent(self._agent.id)
            logging.debug(f"Agent {self._agent.id} already exists")
        except grpc.aio.AioRpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                logging.debug(f"Agent {self._agent.id} not found, registering...")
                registered_agent = await self._register_agent(self._agent)
                # Update agent ID to match what the server assigned
                self._agent.id = registered_agent.id
            else:
                raise
        # Create trajectory
        logging.debug(f"Creating trajectory for agent {self._agent.id}...")
        response = await self._create_trajectory(self._agent.id)
        logging.debug(f"Trajectory created for agent {self._agent.id}: {response.id}")
        self._trajectory_id = response.id

    async def resume(self, trajectory_id: str, *, agent: Agent | None = None) -> None:
        """Resume an existing trajectory for continued execution.

        Args:
            trajectory_id: The ID of the trajectory to resume
            agent: Optional agent to use for this trajectory. If provided, overrides
                   any agent set during construction.

        Raises:
            ValueError: If the trajectory doesn't exist or belongs to a different agent
            RuntimeError: If there's already an active trajectory
        """
        if self._trajectory_id:
            raise RuntimeError(
                f"Already have active trajectory {self._trajectory_id}. Call finalize first."
            )

        if agent:
            self._agent = agent
        assert self._agent is not None, (
            "Agent not provided on initialization or in constructor."
        )

        await self._ensure_connected()

        # Verify the trajectory exists and get its details
        trajectory = await self._get_trajectory(trajectory_id)
        if trajectory is None:
            raise TrajectoryError(f"Trajectory {trajectory_id} not found")

        self._trajectory_id = trajectory.id

        # Verify the trajectory belongs to our agent (if we have one)
        if self._agent and trajectory.agent_id != self._agent.id:
            raise TrajectoryError(
                f"Trajectory {trajectory_id} belongs to agent {trajectory.agent_id}, not {self._agent.id}"
            )

        # Set the trajectory as active
        await self._update_trajectory_status(
            self._trajectory_id, primitives_pb2.TRAJECTORY_STATUS_RUNNING
        )
        self._trajectory_id = trajectory_id
        logging.debug(
            f"Resumed trajectory {trajectory_id} for agent {trajectory.agent_id}"
        )

    async def finalize(self) -> None:
        """Finalize the current trajectory and save artifacts."""
        if not self._trajectory_id:
            raise TrajectoryNotInitializedError()
        assert self._stub is not None, "Client not connected"
        # Update trajectory status to completed
        await self._update_trajectory_status(
            self._trajectory_id, primitives_pb2.TRAJECTORY_STATUS_COMPLETED
        )
        # Clear trajectory ID to indicate no active trajectory
        self._trajectory_id = None

    async def adjudicate(
        self,
        stage: Stage,
        role: Role,
        content: Content,
    ) -> Adjudication:
        """Adjudicate a trajectory step using the policy engine.

        Args:
            stage: The stage of the step
            role: The role of the step
            content: The content of the step

        Returns:
            The adjudication result
        """
        if not self._trajectory_id:
            raise RuntimeError(
                "No active trajectory. Call initialize_trajectory first."
            )

        await self._ensure_connected()

        # Convert SDK types to protobuf
        pb_stage = _convert_sdk_stage_to_pb(stage)
        pb_role = _convert_sdk_role_to_pb(role)
        pb_content = _convert_sdk_content_to_pb(content)

        # Add step and get adjudication
        logging.debug(
            f"Adjudicating (trajectory_id: {self._trajectory_id}): {stage} {role} {content}"
        )
        adjudicated_step = await self._add_trajectory_step(
            self._trajectory_id, pb_stage, pb_role, pb_content
        )
        # Convert protobuf adjudication to SDK type
        adjudication = _convert_pb_adjudication_to_sdk(adjudicated_step.adjudication)
        logging.debug(
            f"Adjudication (trajectory_id:{self._trajectory_id}): {adjudication}"
        )
        return adjudication

    async def _ensure_connected(self):
        """Ensure the client is connected."""
        if not self._is_connected():
            await self._connect()
        assert self._stub is not None, "Client not connected"

    def _is_connected(self) -> bool:
        """Check if the client is connected."""
        return self._channel is not None and self._stub is not None

    async def _connect(self):
        """Establish connection to the gRPC server."""
        if self._secure:
            self._channel = grpc.aio.secure_channel(
                self._sondera_harness_endpoint,
                credentials=grpc.ssl_channel_credentials(),
                options=self._options,
            )
        else:
            self._channel = grpc.aio.insecure_channel(
                self._sondera_harness_endpoint,
                options=self._options,
            )
        self._stub = harness_pb2_grpc.HarnessServiceStub(self._channel)

    async def _close(self):
        """Close the gRPC channel."""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None

    async def _get_agent(self, agent_id: str) -> primitives_pb2.Agent:
        """Get an agent internally.

        Args:
            agent_id: The agent ID

        Returns:
            The agent

        Raises:
            AuthenticationError: If authentication fails
            grpc.RpcError: If other gRPC error occurs
        """
        request = harness_pb2.GetAgentRequest(agent_id=agent_id)
        await self._ensure_connected()
        assert self._stub is not None, "Client not connected"

        # Inject organization_id and auth metadata
        metadata = self._get_metadata()

        try:
            return await self._stub.GetAgent(request, metadata=metadata)
        except grpc.aio.AioRpcError as e:
            # Handle authentication errors
            if e.code() == grpc.StatusCode.UNAUTHENTICATED:
                raise AuthenticationError(
                    f"Authentication failed: {e.details()}"
                ) from e
            raise

    async def _register_agent(self, agent: Agent) -> primitives_pb2.Agent:
        """Register an agent internally.

        Args:
            agent: The agent to register

        Returns:
            The registered agent

        Raises:
            AuthenticationError: If authentication fails
            grpc.RpcError: If other gRPC error occurs
        """
        # Convert SDK agent tools to protobuf
        pb_tools = [_convert_sdk_tool_to_pb(tool) for tool in agent.tools]

        request = harness_pb2.RegisterAgentRequest(
            provider_id=agent.provider_id,
            name=agent.name,
            description=agent.description,
            instruction=agent.instruction,
            tools=pb_tools,
        )
        await self._ensure_connected()
        assert self._stub is not None, "Client not connected"

        # Inject organization_id and auth metadata
        metadata = self._get_metadata()

        try:
            response = await self._stub.RegisterAgent(request, metadata=metadata)
            return response.agent
        except grpc.aio.AioRpcError as e:
            # Handle authentication errors
            if e.code() == grpc.StatusCode.UNAUTHENTICATED:
                raise AuthenticationError(
                    f"Authentication failed: {e.details()}"
                ) from e
            logging.error(f"Failed to register agent: {e.code()} - {e.details()}")
            raise

    async def _create_trajectory(self, agent_id: str) -> primitives_pb2.Trajectory:
        """Create a trajectory internally.

        Args:
            agent_id: The agent ID

        Returns:
            The created trajectory

        Raises:
            AuthenticationError: If authentication fails
            grpc.RpcError: If other gRPC error occurs
        """
        request = harness_pb2.CreateTrajectoryRequest(agent_id=agent_id)
        await self._ensure_connected()
        assert self._stub is not None, "Client not connected"

        # Inject organization_id and auth metadata
        metadata = self._get_metadata()

        try:
            response = await self._stub.CreateTrajectory(request, metadata=metadata)
            return response.trajectory
        except grpc.aio.AioRpcError as e:
            # Handle authentication errors
            if e.code() == grpc.StatusCode.UNAUTHENTICATED:
                raise AuthenticationError(
                    f"Authentication failed: {e.details()}"
                ) from e
            logging.error(
                f"Failed to create trajectory for agent {agent_id}: {e.code()} - {e.details()}"
            )
            raise

    async def _add_trajectory_step(
        self,
        trajectory_id: str,
        stage: primitives_pb2.Stage,
        role: primitives_pb2.Role,
        content: primitives_pb2.Content,
    ) -> primitives_pb2.AdjudicatedStep:
        """Add a trajectory step internally.

        Args:
            trajectory_id: The trajectory ID
            stage: The step stage
            role: The step role
            content: The step content

        Returns:
            The adjudicated step

        Raises:
            AuthenticationError: If authentication fails
            grpc.RpcError: If other gRPC error occurs
        """
        request = harness_pb2.AddTrajectoryStepRequest(
            trajectory_id=trajectory_id, stage=stage, role=role, content=content
        )
        await self._ensure_connected()
        assert self._stub is not None, "Client not connected"

        # Inject organization_id and auth metadata
        metadata = self._get_metadata()

        try:
            response = await self._stub.AddTrajectoryStep(request, metadata=metadata)
            return response.adjudicated_step
        except grpc.aio.AioRpcError as e:
            # Handle authentication errors
            if e.code() == grpc.StatusCode.UNAUTHENTICATED:
                raise AuthenticationError(
                    f"Authentication failed: {e.details()}"
                ) from e
            logging.error(
                f"Failed to add step to trajectory {trajectory_id}: {e.code()} - {e.details()}"
            )
            raise

    async def _update_trajectory_status(
        self, trajectory_id: str, status: primitives_pb2.TrajectoryStatus
    ) -> primitives_pb2.Trajectory:
        """Update trajectory status internally.

        Args:
            trajectory_id: The trajectory ID
            status: The new status

        Returns:
            The updated trajectory

        Raises:
            AuthenticationError: If authentication fails
            grpc.RpcError: If other gRPC error occurs
        """
        request = harness_pb2.UpdateTrajectoryStatusRequest(
            trajectory_id=trajectory_id, status=status
        )
        await self._ensure_connected()
        assert self._stub is not None, "Client not connected"

        # Inject organization_id and auth metadata
        metadata = self._get_metadata()

        try:
            response = await self._stub.UpdateTrajectoryStatus(
                request, metadata=metadata
            )
            return response.trajectory
        except grpc.aio.AioRpcError as e:
            # Handle authentication errors
            if e.code() == grpc.StatusCode.UNAUTHENTICATED:
                raise AuthenticationError(
                    f"Authentication failed: {e.details()}"
                ) from e
            logging.error(
                f"Failed to update trajectory {trajectory_id} status: {e.code()} - {e.details()}"
            )
            raise

    async def _list_trajectories(
        self,
        agent_id: str | None = None,
        status: primitives_pb2.TrajectoryStatus | None = None,
        page_size: int = 100,
        page_token: str = "",
    ) -> list[primitives_pb2.Trajectory]:
        """List trajectories internally."""
        request = harness_pb2.ListTrajectoriesRequest(
            agent_id=agent_id or "",
            page_size=page_size,
            page_token=page_token,
        )
        if status is not None:
            request.status = status
        await self._ensure_connected()
        assert self._stub is not None, "Client not connected"

        # Inject organization_id and auth metadata
        metadata = self._get_metadata()

        try:
            response = await self._stub.ListTrajectories(request, metadata=metadata)
            return list(response.trajectories)
        except grpc.aio.AioRpcError as e:
            logging.error(f"Failed to list trajectories: {e.code()} - {e.details()}")
            raise

    async def _get_adjudicated_trajectory(
        self, trajectory_id: str
    ) -> harness_pb2.GetTrajectoryResponse | None:
        """Get a trajectory internally. Returns None if not found (fail-closed)."""
        request = harness_pb2.GetTrajectoryRequest(
            trajectory_id=trajectory_id,
        )
        await self._ensure_connected()
        assert self._stub is not None, "Client not connected"

        # Inject organization_id and auth metadata
        metadata = self._get_metadata()

        try:
            response = await self._stub.GetTrajectory(request, metadata=metadata)
            return response
        except grpc.aio.AioRpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                return None
            logging.error(
                f"Failed to get adjudicated trajectory {trajectory_id}: {e.code()} - {e.details()}"
            )
            raise

    async def _get_trajectory(
        self, trajectory_id: str
    ) -> primitives_pb2.Trajectory | None:
        """Get a trajectory internally. Returns None if not found (fail-closed)."""
        request = harness_pb2.GetTrajectoryRequest(
            trajectory_id=trajectory_id,
        )
        await self._ensure_connected()
        assert self._stub is not None, "Client not connected"

        # Inject organization_id and auth metadata
        metadata = self._get_metadata()

        try:
            response = await self._stub.GetTrajectory(request, metadata=metadata)
            return response.trajectory
        except grpc.aio.AioRpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                return None
            logging.error(
                f"Failed to get trajectory {trajectory_id}: {e.code()} - {e.details()}"
            )
            raise

    async def _list_agents(
        self,
        provider_id: str | None = None,
        page_size: int = 50,
        page_token: str = "",
    ) -> tuple[list[primitives_pb2.Agent], str]:
        """List agents internally.

        Args:
            provider_id: Optional provider ID to filter agents
            page_size: Maximum number of agents to return
            page_token: Token for pagination

        Returns:
            Tuple of (list of protobuf agents, next page token)

        Raises:
            AuthenticationError: If authentication fails
            grpc.RpcError: If other gRPC error occurs
        """
        request = harness_pb2.ListAgentsRequest(
            page_size=page_size,
            page_token=page_token,
        )
        if provider_id is not None:
            request.provider_id = provider_id

        await self._ensure_connected()
        assert self._stub is not None, "Client not connected"

        # Inject organization_id and auth metadata
        metadata = self._get_metadata()

        try:
            response = await self._stub.ListAgents(request, metadata=metadata)
            return list(response.agents), response.next_page_token
        except grpc.aio.AioRpcError as e:
            # Handle authentication errors
            if e.code() == grpc.StatusCode.UNAUTHENTICATED:
                raise AuthenticationError(
                    f"Authentication failed: {e.details()}"
                ) from e
            logging.error(f"Failed to list agents: {e.code()} - {e.details()}")
            raise

    async def list_agents(
        self,
        provider_id: str | None = None,
        page_size: int = 50,
        page_token: str = "",
    ) -> list[Agent]:
        """List registered agents.

        Args:
            provider_id: Optional provider ID to filter agents
            page_size: Maximum number of agents to return per page
            page_token: Token for pagination (empty string for first page)

        Returns:
            List of Agent objects

        Raises:
            AuthenticationError: If authentication fails
            grpc.RpcError: If other gRPC error occurs
        """
        pb_agents, _ = await self._list_agents(
            provider_id=provider_id,
            page_size=page_size,
            page_token=page_token,
        )
        return [_convert_pb_agent_to_sdk(pb_agent) for pb_agent in pb_agents]

    async def get_trajectory(self, trajectory_id: str) -> AdjudicatedTrajectory | None:
        """Get a trajectory by ID.

        Args:
            trajectory_id: The unique identifier of the trajectory

        Returns:
            Trajectory object if found, None otherwise

        Raises:
            grpc.RpcError: If gRPC error occurs (other than NOT_FOUND)
        """
        pb_adjudicated_trajectory = await self._get_adjudicated_trajectory(
            trajectory_id
        )
        if pb_adjudicated_trajectory is None:
            return None
        return _convert_pb_adjudicated_trajectory_to_sdk(pb_adjudicated_trajectory)

    async def list_trajectories(
        self,
        agent_id: str,
        status: TrajectoryStatus | None = None,
        page_size: int = 50,
        page_token: str = "",
    ) -> list[Trajectory]:
        """List trajectories for an agent.

        Args:
            agent_id: The agent ID to filter trajectories
            status: Optional status to filter trajectories
            page_size: Maximum number of trajectories to return per page
            page_token: Token for pagination (empty string for first page)

        Returns:
            List of Trajectory objects

        Raises:
            grpc.RpcError: If gRPC error occurs
        """
        pb_status = _convert_sdk_trajectory_status_to_pb(status) if status else None
        pb_trajectories = await self._list_trajectories(
            agent_id=agent_id,
            status=pb_status,
            page_size=page_size,
            page_token=page_token,
        )
        return [_convert_pb_trajectory_to_sdk(pb_traj) for pb_traj in pb_trajectories]

    async def analyze_trajectories(
        self,
        agent_id: str,
        start_time: "datetime | None" = None,
        end_time: "datetime | None" = None,
        analytics: list[str] | None = None,
    ) -> dict[str, Any]:
        """Analyze trajectories for an agent (AIP-136 custom method).

        Args:
            agent_id: The agent ID to analyze trajectories for
            start_time: Optional start time filter (inclusive). Only count trajectories
                created at or after this time.
            end_time: Optional end time filter (inclusive). Only count trajectories
                created at or before this time.
            analytics: List of analytics to compute. Empty or None means all available analytics.
                Available analytics:
                - "trajectory_count": Total number of trajectories for the agent

        Returns:
            Dictionary containing:
                - "analytics": Dict of computed analytics (keys are analytic names)
                - "trajectory_count": Total number of trajectories analyzed
                - "computed_at": Timestamp when analytics were computed (datetime)

        Raises:
            grpc.RpcError: If gRPC error occurs

        Example:
            ```python
            from datetime import datetime, timedelta, timezone

            # Get all trajectory analytics
            result = await harness.analyze_trajectories(
                agent_id="my-agent",
                analytics=["trajectory_count"],
            )
            print(f"Total trajectories: {result['analytics']['trajectory_count']['total']}")

            # Get trajectories from the last 24 hours
            result = await harness.analyze_trajectories(
                agent_id="my-agent",
                start_time=datetime.now(timezone.utc) - timedelta(hours=24),
            )
            ```
        """
        request = harness_pb2.AnalyzeTrajectoriesRequest(
            agent_id=agent_id,
            analytics=analytics or [],
        )

        # Convert datetime to protobuf Timestamp if provided
        if start_time is not None:
            ts = Timestamp()
            ts.FromDatetime(start_time)
            request.start_time.CopyFrom(ts)

        if end_time is not None:
            ts = Timestamp()
            ts.FromDatetime(end_time)
            request.end_time.CopyFrom(ts)

        await self._ensure_connected()
        assert self._stub is not None, "Client not connected"

        # Inject organization_id and auth metadata
        metadata = self._get_metadata()

        try:
            response = await self._stub.AnalyzeTrajectories(request, metadata=metadata)

            # Convert protobuf Struct to Python dict
            analytics_dict = {}
            if response.analytics:
                analytics_dict = MessageToDict(
                    response.analytics, preserving_proto_field_name=True
                )

            # Convert computed_at timestamp
            computed_at = (
                datetime.fromtimestamp(response.computed_at.seconds, tz=UTC)
                if response.computed_at
                else datetime.now(tz=UTC)
            )

            return {
                "analytics": analytics_dict,
                "trajectory_count": response.trajectory_count,
                "computed_at": computed_at,
            }
        except grpc.aio.AioRpcError as e:
            logging.error(
                f"Failed to analyze trajectories for agent {agent_id}: {e.code()} - {e.details()}"
            )
            raise

    async def list_adjudications(
        self,
        agent_id: str | None = None,
        page_size: int = 50,
        page_token: str = "",
    ) -> tuple[list[AdjudicationRecord], str]:
        """List adjudication records with optional agent filtering.

        This method retrieves adjudication records (policy decisions) that have
        occurred during agent execution. Results can be filtered by agent and
        are paginated.

        Args:
            agent_id: Optional agent ID to filter adjudications. If None, returns
                adjudications for all agents.
            page_size: Maximum number of records to return per page (default: 50)
            page_token: Token for pagination (empty string for first page)

        Returns:
            Tuple of (list of AdjudicationRecord objects, next page token).
            The next page token will be empty if there are no more results.

        Raises:
            AuthenticationError: If authentication fails
            grpc.RpcError: If other gRPC error occurs

        Example:
            ```python
            # List all adjudications
            records, next_token = await harness.list_adjudications()

            # List adjudications for a specific agent
            records, next_token = await harness.list_adjudications(agent_id="my-agent")

            # Paginate through results
            all_records = []
            token = ""
            while True:
                records, token = await harness.list_adjudications(page_token=token)
                all_records.extend(records)
                if not token:
                    break
            ```
        """
        request = harness_pb2.ListAdjudicationsRequest(
            page_size=page_size,
            page_token=page_token,
        )
        if agent_id is not None:
            request.agent_id = agent_id

        await self._ensure_connected()
        assert self._stub is not None, "Client not connected"

        metadata = self._get_metadata()

        try:
            response = await self._stub.ListAdjudications(request, metadata=metadata)
            records = [
                _convert_pb_adjudication_record_to_sdk(pb_record)
                for pb_record in response.adjudications
            ]
            return records, response.next_page_token
        except grpc.aio.AioRpcError as e:
            if e.code() == grpc.StatusCode.UNAUTHENTICATED:
                raise AuthenticationError(
                    f"Authentication failed: {e.details()}"
                ) from e
            logging.error(f"Failed to list adjudications: {e.code()} - {e.details()}")
            raise
