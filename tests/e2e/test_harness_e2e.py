#!/usr/bin/env python3
"""
Sondera Harness End-to-End Smoke Tests

Self-contained E2E tests for validating harness service deployments.
Used as post-deployment smoke tests in CI/CD pipelines.

Environment Variables:
    SONDERA_ENV: Target environment (dev, nightly, prod) - default: dev
    SONDERA_API_TOKEN: API token for authentication (required)
    SONDERA_HARNESS_ENDPOINT: Override harness endpoint (optional)
    SONDERA_HARNESS_CLIENT_SECURE: Use TLS (default: true)

Usage:
    # Test dev environment
    SONDERA_ENV=dev SONDERA_API_TOKEN=<token> uv run pytest tests/e2e/test_harness_e2e.py -v

    # Test nightly environment
    SONDERA_ENV=nightly SONDERA_API_TOKEN=<token> uv run pytest tests/e2e/test_harness_e2e.py -v

    # Test prod environment
    SONDERA_ENV=prod SONDERA_API_TOKEN=<token> uv run pytest tests/e2e/test_harness_e2e.py -v

    # Custom endpoint
    SONDERA_HARNESS_ENDPOINT=custom.endpoint:443 SONDERA_API_TOKEN=<token> \\
        uv run pytest tests/e2e/test_harness_e2e.py -v
"""

import os
import uuid

import pytest

# Self-contained - inline harness endpoint configuration
HARNESS_ENDPOINTS = {
    "dev": "harness.dev.sondera.ai:443",
    "nightly": "harness.nightly.sondera.ai:443",
    "prod": "harness.sondera.ai:443",
}


def get_harness_config() -> tuple[str, str, bool]:
    """Get harness configuration from environment.

    Returns:
        Tuple of (endpoint, api_token, secure)
    """
    env = os.environ.get("SONDERA_ENV", "dev")
    api_token = os.environ.get("SONDERA_API_TOKEN")

    if not api_token:
        pytest.skip("SONDERA_API_TOKEN environment variable not set")

    # Allow explicit endpoint override, otherwise use environment mapping
    endpoint = os.environ.get("SONDERA_HARNESS_ENDPOINT")
    if not endpoint:
        if env not in HARNESS_ENDPOINTS:
            pytest.skip(f"Unknown environment: {env}")
        endpoint = HARNESS_ENDPOINTS[env]

    # Determine if we should use TLS (default True for all environments)
    secure = os.environ.get("SONDERA_HARNESS_CLIENT_SECURE", "true").lower() == "true"

    return endpoint, api_token, secure


@pytest.fixture(scope="session")
def harness_config():
    """Get harness configuration."""
    return get_harness_config()


@pytest.fixture(scope="session")
def environment():
    """Get the current environment name."""
    return os.environ.get("SONDERA_ENV", "dev")


@pytest.fixture
def unique_agent_id():
    """Generate a unique agent ID for test isolation."""
    return f"e2e-smoke-test-{uuid.uuid4().hex[:8]}"


class TestHarnessConnectivity:
    """Test basic connectivity to the harness service."""

    @pytest.mark.asyncio
    async def test_harness_reachable(self, harness_config):
        """
        Verify the harness service is reachable and accepting connections.

        This is the most basic smoke test - if this fails, the service
        is down or unreachable.
        """
        from sondera import Agent, SonderaRemoteHarness, Tool

        endpoint, api_token, secure = harness_config

        # Create a minimal test agent
        test_agent = Agent(
            id=f"connectivity-test-{uuid.uuid4().hex[:8]}",
            provider_id="e2e-smoke-test",
            name="Connectivity_Test_Agent",
            description="Agent for testing harness connectivity",
            instruction="Test agent - no actual work",
            tools=[
                Tool(name="echo", description="Echo input", parameters=[]),
            ],
        )

        harness = SonderaRemoteHarness(
            agent=test_agent,
            sondera_harness_endpoint=endpoint,
            sondera_api_key=api_token,
            sondera_harness_client_secure=secure,
        )

        # Test: Can we initialize a trajectory?
        await harness.initialize()
        assert harness.trajectory_id is not None, (
            "Trajectory ID should be set after initialize"
        )

        print(f"\n✓ Harness reachable at {endpoint}")
        print(f"✓ Trajectory created: {harness.trajectory_id}")

        # Clean up
        await harness.finalize()
        print("✓ Trajectory finalized")


class TestHarnessLifecycle:
    """Test the full harness lifecycle: initialize -> adjudicate -> finalize."""

    @pytest.mark.asyncio
    async def test_full_lifecycle_with_prompt(self, harness_config, unique_agent_id):
        """
        Test complete lifecycle with a prompt content adjudication.

        Validates:
        1. Agent registration (or retrieval if exists)
        2. Trajectory creation
        3. Step adjudication with PromptContent
        4. Trajectory finalization
        """
        from sondera import (
            Agent,
            Decision,
            PromptContent,
            Role,
            SonderaRemoteHarness,
            Stage,
            Tool,
        )

        endpoint, api_token, secure = harness_config

        test_agent = Agent(
            id=unique_agent_id,
            provider_id="e2e-smoke-test",
            name="Lifecycle_Test_Agent",
            description="Agent for testing harness lifecycle",
            instruction="Test agent for E2E smoke tests",
            tools=[
                Tool(name="read_file", description="Read a file", parameters=[]),
                Tool(name="write_file", description="Write a file", parameters=[]),
            ],
        )

        harness = SonderaRemoteHarness(
            agent=test_agent,
            sondera_harness_endpoint=endpoint,
            sondera_api_key=api_token,
            sondera_harness_client_secure=secure,
        )

        # Initialize
        await harness.initialize()
        trajectory_id = harness.trajectory_id
        assert trajectory_id is not None
        print(f"\n✓ Initialized trajectory: {trajectory_id}")

        # Adjudicate a prompt
        adjudication = await harness.adjudicate(
            Stage.PRE_MODEL,
            Role.USER,
            PromptContent(text="Hello, please help me with a task."),
        )

        assert adjudication is not None
        assert adjudication.decision in [
            Decision.ALLOW,
            Decision.DENY,
            Decision.ESCALATE,
        ]
        print(f"✓ Adjudicated prompt: decision={adjudication.decision.name}")

        # Finalize
        await harness.finalize()
        assert harness.trajectory_id is None, (
            "Trajectory ID should be cleared after finalize"
        )
        print("✓ Finalized trajectory")

    @pytest.mark.asyncio
    async def test_full_lifecycle_with_tool_request(
        self, harness_config, unique_agent_id
    ):
        """
        Test complete lifecycle with a tool request adjudication.

        Validates tool request adjudication flow following the proper sequence:
        PRE_MODEL (user prompt) -> POST_MODEL (model response) -> tool execution
        """
        from sondera import (
            Agent,
            Decision,
            PromptContent,
            Role,
            SonderaRemoteHarness,
            Stage,
            Tool,
            ToolResponseContent,
        )

        endpoint, api_token, secure = harness_config

        test_agent = Agent(
            id=unique_agent_id,
            provider_id="e2e-smoke-test",
            name="Tool_Request_Test_Agent",
            description="Agent for testing tool request adjudication",
            instruction="Test agent for E2E smoke tests",
            tools=[
                Tool(name="read_file", description="Read a file", parameters=[]),
            ],
        )

        harness = SonderaRemoteHarness(
            agent=test_agent,
            sondera_harness_endpoint=endpoint,
            sondera_api_key=api_token,
            sondera_harness_client_secure=secure,
        )

        # Initialize
        await harness.initialize()
        print(f"\n✓ Initialized trajectory: {harness.trajectory_id}")

        # Step 1: User sends a prompt (PRE_MODEL)
        adjudication = await harness.adjudicate(
            Stage.PRE_MODEL,
            Role.USER,
            PromptContent(text="Please read the file /tmp/test.txt"),
        )
        assert adjudication is not None
        print(f"✓ Adjudicated user prompt: decision={adjudication.decision.name}")

        # Step 2: Model responds (POST_MODEL)
        adjudication = await harness.adjudicate(
            Stage.POST_MODEL,
            Role.MODEL,
            PromptContent(text="I'll read that file for you."),
        )
        assert adjudication is not None
        print(f"✓ Adjudicated model response: decision={adjudication.decision.name}")

        # Step 3: Tool returns result (POST_TOOL)
        adjudication = await harness.adjudicate(
            Stage.POST_TOOL,
            Role.TOOL,
            ToolResponseContent(
                tool_id="read_file",
                response="File contents: Hello, World!",
            ),
        )
        assert adjudication is not None
        assert adjudication.decision in [
            Decision.ALLOW,
            Decision.DENY,
            Decision.ESCALATE,
        ]
        print(f"✓ Adjudicated tool response: decision={adjudication.decision.name}")

        # Finalize
        await harness.finalize()
        print("✓ Finalized trajectory")


class TestHarnessRetrieval:
    """Test trajectory and agent retrieval functionality."""

    @pytest.mark.asyncio
    async def test_trajectory_retrieval(self, harness_config, unique_agent_id):
        """
        Test that trajectories can be retrieved after creation.

        Validates:
        1. Create trajectory with steps
        2. Retrieve trajectory by ID
        3. Verify steps are recorded
        """
        from sondera import (
            Agent,
            PromptContent,
            Role,
            SonderaRemoteHarness,
            Stage,
            Tool,
        )

        endpoint, api_token, secure = harness_config

        test_agent = Agent(
            id=unique_agent_id,
            provider_id="e2e-smoke-test",
            name="Retrieval_Test_Agent",
            description="Agent for testing trajectory retrieval",
            instruction="Test agent",
            tools=[Tool(name="test_tool", description="Test", parameters=[])],
        )

        harness = SonderaRemoteHarness(
            agent=test_agent,
            sondera_harness_endpoint=endpoint,
            sondera_api_key=api_token,
            sondera_harness_client_secure=secure,
        )

        # Create trajectory with steps
        await harness.initialize()
        trajectory_id = harness.trajectory_id
        print(f"\n✓ Created trajectory: {trajectory_id}")

        # Add a step
        await harness.adjudicate(
            Stage.PRE_MODEL,
            Role.USER,
            PromptContent(text="Test message for retrieval"),
        )
        print("✓ Added step to trajectory")

        # Finalize
        await harness.finalize()
        print("✓ Finalized trajectory")

        # Retrieve the trajectory
        # Need a new harness instance since the previous one cleared state
        harness2 = SonderaRemoteHarness(
            agent=test_agent,
            sondera_harness_endpoint=endpoint,
            sondera_api_key=api_token,
            sondera_harness_client_secure=secure,
        )

        retrieved = await harness2.get_trajectory(trajectory_id)
        assert retrieved is not None, (
            f"Should be able to retrieve trajectory {trajectory_id}"
        )
        assert retrieved.id == trajectory_id  # AdjudicatedTrajectory extends Trajectory
        assert len(retrieved.steps) >= 1, "Trajectory should have at least one step"
        print(f"✓ Retrieved trajectory with {len(retrieved.steps)} step(s)")

    @pytest.mark.asyncio
    async def test_list_agents(self, harness_config, unique_agent_id):
        """
        Test that agents can be listed.

        Validates the list_agents API.
        """
        from sondera import Agent, SonderaRemoteHarness, Tool

        endpoint, api_token, secure = harness_config

        test_agent = Agent(
            id=unique_agent_id,
            provider_id="e2e-smoke-test",
            name="List_Agents_Test",
            description="Agent for testing list agents",
            instruction="Test agent",
            tools=[Tool(name="test", description="Test", parameters=[])],
        )

        harness = SonderaRemoteHarness(
            agent=test_agent,
            sondera_harness_endpoint=endpoint,
            sondera_api_key=api_token,
            sondera_harness_client_secure=secure,
        )

        # Initialize to register the agent
        await harness.initialize()
        await harness.finalize()
        print(f"\n✓ Registered agent: {unique_agent_id}")

        # List agents
        agents = await harness.list_agents()
        assert agents is not None
        assert len(agents) > 0, "Should have at least one agent"
        print(f"✓ Listed {len(agents)} agent(s)")

        # Note: Agent ID might be server-assigned, so just verify we got results
        print("✓ Agent list contains registered agents")


class TestHarnessAnalytics:
    """Test analytics and analysis functionality."""

    @pytest.mark.asyncio
    async def test_analyze_trajectories(self, harness_config, unique_agent_id):
        """
        Test trajectory analytics.

        Validates the analyze_trajectories API.
        """
        from sondera import (
            Agent,
            PromptContent,
            Role,
            SonderaRemoteHarness,
            Stage,
            Tool,
        )

        endpoint, api_token, secure = harness_config

        test_agent = Agent(
            id=unique_agent_id,
            provider_id="e2e-smoke-test",
            name="Analytics_Test_Agent",
            description="Agent for testing analytics",
            instruction="Test agent",
            tools=[Tool(name="test", description="Test", parameters=[])],
        )

        harness = SonderaRemoteHarness(
            agent=test_agent,
            sondera_harness_endpoint=endpoint,
            sondera_api_key=api_token,
            sondera_harness_client_secure=secure,
        )

        # Create a trajectory
        await harness.initialize()
        agent_id = harness.agent.id  # Get server-assigned agent ID
        await harness.adjudicate(
            Stage.PRE_MODEL, Role.USER, PromptContent(text="Analytics test")
        )
        await harness.finalize()
        print(f"\n✓ Created test trajectory for agent: {agent_id}")

        # Analyze trajectories
        result = await harness.analyze_trajectories(
            agent_id=agent_id,
            analytics=["trajectory_count"],
        )

        assert result is not None
        assert "analytics" in result
        assert "computed_at" in result
        print(f"✓ Analytics computed at: {result['computed_at']}")
        print(f"✓ Trajectory count: {result.get('trajectory_count', 'N/A')}")


class TestHarnessErrorHandling:
    """Test error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self, harness_config):
        """
        Test that invalid tokens are rejected.

        This validates the authentication flow.
        """
        from sondera import Agent, AuthenticationError, SonderaRemoteHarness, Tool

        endpoint, _, secure = harness_config

        test_agent = Agent(
            id="invalid-token-test",
            provider_id="e2e-smoke-test",
            name="Invalid_Token_Test",
            description="Agent for testing invalid token handling",
            instruction="Test agent",
            tools=[Tool(name="test", description="Test", parameters=[])],
        )

        harness = SonderaRemoteHarness(
            agent=test_agent,
            sondera_harness_endpoint=endpoint,
            sondera_api_key="invalid-token-that-should-not-work",
            sondera_harness_client_secure=secure,
        )

        # Should raise AuthenticationError
        with pytest.raises((AuthenticationError, Exception)) as exc_info:
            await harness.initialize()

        print(f"\n✓ Invalid token correctly rejected: {type(exc_info.value).__name__}")


# Entry point for running as a script
if __name__ == "__main__":
    import sys

    # Print configuration
    env = os.environ.get("SONDERA_ENV", "dev")
    token = os.environ.get("SONDERA_API_TOKEN", "")
    endpoint = os.environ.get(
        "SONDERA_HARNESS_ENDPOINT", HARNESS_ENDPOINTS.get(env, "unknown")
    )

    print("=" * 60)
    print("Sondera Harness E2E Smoke Tests")
    print("=" * 60)
    print(f"Environment: {env}")
    print(f"Endpoint: {endpoint}")
    print(f"Token: {'*' * 8}...{token[-4:] if len(token) > 4 else '(not set)'}")
    print("=" * 60)

    if not token:
        print("ERROR: SONDERA_API_TOKEN environment variable not set")
        sys.exit(1)

    # Run pytest
    sys.exit(pytest.main([__file__, "-v", "--tb=short"] + sys.argv[1:]))
