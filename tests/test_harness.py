"""Unit tests for HarnessClient (SON-479)."""

from unittest.mock import AsyncMock, MagicMock

import grpc
import pytest

from sondera.exceptions import AuthenticationError, ConfigurationError
from sondera.harness import SonderaRemoteHarness
from sondera.proto.sondera.core.v1 import primitives_pb2
from sondera.proto.sondera.harness.v1 import harness_pb2


class TestHarnessConstructor:
    """Test cases for Harness constructor validation."""

    def test_harness_client_requires_api_key(self):
        """Test HarnessClient rejects empty sondera_api_key."""
        with pytest.raises(ConfigurationError, match="sondera_api_key is required"):
            SonderaRemoteHarness(
                sondera_harness_endpoint="localhost:50051",
                sondera_api_key="",
            )

    def test_harness_client_accepts_valid_api_key(self):
        """Test HarnessClient accepts valid sondera_api_key."""
        client = SonderaRemoteHarness(
            sondera_harness_endpoint="localhost:50051",
            sondera_api_key="test-jwt-123",
        )
        assert client._sondera_api_key == "test-jwt-123"


class TestMetadataInjection:
    """Test cases for authorization metadata injection in RPC methods."""

    @pytest.mark.asyncio
    async def test_create_trajectory_injects_auth_metadata(self):
        """Test _create_trajectory includes authorization metadata."""
        # Mock the gRPC stub
        mock_stub = MagicMock()
        mock_trajectory = primitives_pb2.Trajectory(id="traj-123", agent_id="agent-1")
        mock_response = harness_pb2.CreateTrajectoryResponse(trajectory=mock_trajectory)
        mock_stub.CreateTrajectory = AsyncMock(return_value=mock_response)

        client = SonderaRemoteHarness(
            sondera_harness_endpoint="localhost:50051",
            sondera_api_key="test-jwt-token",
        )
        client._stub = mock_stub
        client._channel = MagicMock()

        trajectory = await client._create_trajectory("agent-1")

        # Verify authorization metadata was included
        call_args = mock_stub.CreateTrajectory.call_args
        assert call_args[1]["metadata"] == [("authorization", "Bearer test-jwt-token")]
        assert trajectory.id == "traj-123"

    @pytest.mark.asyncio
    async def test_get_agent_injects_auth_metadata(self):
        """Test _get_agent includes authorization metadata."""
        # Mock the gRPC stub
        mock_stub = MagicMock()
        mock_agent = primitives_pb2.Agent(id="agent-1", name="Test Agent")
        mock_stub.GetAgent = AsyncMock(return_value=mock_agent)

        client = SonderaRemoteHarness(
            sondera_harness_endpoint="localhost:50051",
            sondera_api_key="test-jwt-xyz",
        )
        client._stub = mock_stub
        client._channel = MagicMock()

        agent = await client._get_agent("agent-1")

        # Verify authorization metadata was included
        call_args = mock_stub.GetAgent.call_args
        assert call_args[1]["metadata"] == [("authorization", "Bearer test-jwt-xyz")]
        assert agent.id == "agent-1"

    @pytest.mark.asyncio
    async def test_register_agent_injects_auth_metadata(self):
        """Test _register_agent includes authorization metadata."""
        from sondera.types import Agent

        # Mock the gRPC stub
        mock_stub = MagicMock()
        mock_pb_agent = primitives_pb2.Agent(id="agent-1", name="Test Agent")
        mock_response = harness_pb2.RegisterAgentResponse(agent=mock_pb_agent)
        mock_stub.RegisterAgent = AsyncMock(return_value=mock_response)

        client = SonderaRemoteHarness(
            sondera_harness_endpoint="localhost:50051",
            sondera_api_key="test-jwt-register",
        )
        client._stub = mock_stub
        client._channel = MagicMock()

        # Create a minimal agent for registration
        agent = Agent(
            id="agent-1",
            provider_id="test-provider",
            name="Test Agent",
            description="Test",
            instruction="Test instruction",
            tools=[],
        )

        registered_agent = await client._register_agent(agent)

        # Verify authorization metadata was included
        call_args = mock_stub.RegisterAgent.call_args
        assert call_args[1]["metadata"] == [
            ("authorization", "Bearer test-jwt-register")
        ]
        assert registered_agent.id == "agent-1"

    @pytest.mark.asyncio
    async def test_add_trajectory_step_injects_auth_metadata(self):
        """Test _add_trajectory_step includes authorization metadata."""
        # Mock the gRPC stub
        mock_stub = MagicMock()
        # Create a fully mocked response
        mock_response = MagicMock()
        mock_response.adjudicated_step.step.step_id = "step-1"
        mock_stub.AddTrajectoryStep = AsyncMock(return_value=mock_response)

        client = SonderaRemoteHarness(
            sondera_harness_endpoint="localhost:50051",
            sondera_api_key="test-jwt-step",
        )
        client._stub = mock_stub
        client._channel = MagicMock()

        step = await client._add_trajectory_step(
            "traj-1",
            primitives_pb2.STAGE_PRE_MODEL,
            primitives_pb2.ROLE_USER,
            primitives_pb2.Content(prompt=primitives_pb2.Prompt(text="test")),
        )

        # Verify authorization metadata was included
        call_args = mock_stub.AddTrajectoryStep.call_args
        assert call_args[1]["metadata"] == [("authorization", "Bearer test-jwt-step")]
        assert step.step.step_id == "step-1"

    @pytest.mark.asyncio
    async def test_update_trajectory_status_injects_auth_metadata(self):
        """Test _update_trajectory_status includes authorization metadata."""
        # Mock the gRPC stub
        mock_stub = MagicMock()
        mock_trajectory = primitives_pb2.Trajectory(
            id="traj-123",
            agent_id="agent-1",
            status=primitives_pb2.TRAJECTORY_STATUS_COMPLETED,
        )
        mock_response = harness_pb2.UpdateTrajectoryStatusResponse(
            trajectory=mock_trajectory
        )
        mock_stub.UpdateTrajectoryStatus = AsyncMock(return_value=mock_response)

        client = SonderaRemoteHarness(
            sondera_harness_endpoint="localhost:50051",
            sondera_api_key="test-jwt-status",
        )
        client._stub = mock_stub
        client._channel = MagicMock()

        trajectory = await client._update_trajectory_status(
            "traj-123", primitives_pb2.TRAJECTORY_STATUS_COMPLETED
        )

        # Verify authorization metadata was included
        call_args = mock_stub.UpdateTrajectoryStatus.call_args
        assert call_args[1]["metadata"] == [("authorization", "Bearer test-jwt-status")]
        assert trajectory.status == primitives_pb2.TRAJECTORY_STATUS_COMPLETED


class MockRpcError(grpc.aio.AioRpcError):
    """Mock RPC error for testing."""

    def __init__(self, code, details_msg):
        self._code = code
        self._details = details_msg

    def code(self):
        return self._code

    def details(self):
        return self._details


class TestAuthenticationErrorHandling:
    """Test cases for authentication error handling."""

    @pytest.mark.asyncio
    async def test_create_trajectory_handles_auth_error(self):
        """Test _create_trajectory converts UNAUTHENTICATED to AuthenticationError."""
        mock_stub = MagicMock()
        # Create a proper mock error
        error = MockRpcError(grpc.StatusCode.UNAUTHENTICATED, "Missing JWT claims")
        mock_stub.CreateTrajectory = AsyncMock(side_effect=error)

        client = SonderaRemoteHarness(
            sondera_harness_endpoint="localhost:50051",
            sondera_api_key="test-jwt",
        )
        client._stub = mock_stub
        client._channel = MagicMock()

        with pytest.raises(AuthenticationError, match="Authentication failed"):
            await client._create_trajectory("agent-1")

    @pytest.mark.asyncio
    async def test_get_agent_handles_auth_error(self):
        """Test _get_agent converts UNAUTHENTICATED to AuthenticationError."""
        mock_stub = MagicMock()
        # Create a proper mock error
        error = MockRpcError(grpc.StatusCode.UNAUTHENTICATED, "Missing JWT claims")
        mock_stub.GetAgent = AsyncMock(side_effect=error)

        client = SonderaRemoteHarness(
            sondera_harness_endpoint="localhost:50051",
            sondera_api_key="test-jwt-get",
        )
        client._stub = mock_stub
        client._channel = MagicMock()

        with pytest.raises(AuthenticationError, match="Authentication failed"):
            await client._get_agent("agent-1")

    @pytest.mark.asyncio
    async def test_add_trajectory_step_handles_auth_error(self):
        """Test _add_trajectory_step converts UNAUTHENTICATED to AuthenticationError."""
        mock_stub = MagicMock()
        # Create a proper mock error
        error = MockRpcError(grpc.StatusCode.UNAUTHENTICATED, "Invalid token")
        mock_stub.AddTrajectoryStep = AsyncMock(side_effect=error)

        client = SonderaRemoteHarness(
            sondera_harness_endpoint="localhost:50051",
            sondera_api_key="test-jwt-invalid",
        )
        client._stub = mock_stub
        client._channel = MagicMock()

        with pytest.raises(AuthenticationError, match="Authentication failed"):
            await client._add_trajectory_step(
                "traj-1",
                primitives_pb2.STAGE_PRE_MODEL,
                primitives_pb2.ROLE_USER,
                primitives_pb2.Content(prompt=primitives_pb2.Prompt(text="test")),
            )
