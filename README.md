# Sondera Harness SDK for Python

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

>
> One step at a time. One action at a time. One trajectory at a time.
> 

AI agents systems operate beyond traditional security boundaries, making autonomous decisions, calling tools, and accessing resources based on context that changes with every execution. Sondera SDK provides runtime governance for these agentic systems, answering not just "can this agent do X?" but "should it do X here, now, with this data?" Built for developers deploying agents through LangGraph, Google ADK, and Strands, Sondera enables real-time trajectory tracking, policy-as-code enforcement via Cedar, and behavioral adjudication so you can ship agents with confidence.

## Features

- **Managed harness-as-a-service** with the Sondera Harness for enterprise policy governance and guardrails
- **Local policy-as-code** using Cedar policy language in the Cedar Policy Harness
- **Real-time trajectory** observability, adjudication, and steering
- **Scaffold integrations** for LangGraph, Google ADK, and Strands
- **CLI and TUI** for monitoring agent behavior

## Installation

```bash
uv add sondera-harness
```

### Optional Dependencies

Install extras for specific framework integrations:

```bash
# Google ADK support
uv add sondera-harness --extra adk

# LangGraph support
uv add sondera-harness --extra langgraph

# Strands support
uv add sondera-harness --extra strands

# All integrations
uv add sondera-harness --all-extras
```

## Quick Start

### Configuration

Set your API credentials via environment variables:

```bash
export SONDERA_HARNESS_ENDPOINT="your-harness.sondera.ai:443"
export SONDERA_API_TOKEN="<YOUR_SONDERA_API_KEY>"
```

Or create a `.env` file or `~/.sondera/env`:

```env
SONDERA_HARNESS_ENDPOINT=your-harness.sondera.ai:443
SONDERA_API_TOKEN=<YOUR_SONDERA_API_KEY>
```

## Scaffold Integrations

### LangGraph / LangChain

```python
from langchain.agents import create_agent
from sondera.harness import SonderaRemoteHarness
from sondera.langgraph import SonderaHarnessMiddleware, Strategy, create_agent_from_langchain_tools

# Analyze your tools and create agent metadata
sondera_agent = create_agent_from_langchain_tools(
    tools=my_tools,
    agent_id="langchain-agent",
    agent_name="My LangChain Agent",
    agent_description="An agent that helps with tasks",
)

# Create harness with agent
harness = SonderaRemoteHarness(agent=sondera_agent)

# Create middleware
middleware = SonderaHarnessMiddleware(
    harness=harness,
    strategy=Strategy.BLOCK,  # or Strategy.STEER
)

# Create agent with middleware
agent = create_agent(
    model=my_model,
    tools=my_tools,
    middleware=[middleware],
)
```

### Google ADK

```python
from google.adk.agents import Agent
from google.adk.runners import Runner
from sondera.harness import SonderaRemoteHarness
from sondera.adk import SonderaHarnessPlugin

# Create harness
harness = SonderaRemoteHarness(
    sondera_api_key="<YOUR_SONDERA_API_KEY>",
)

# Create plugin
plugin = SonderaHarnessPlugin(harness=harness)

# Create agent
agent = Agent(
    name="my-adk-agent",
    model="gemini-2.0-flash",
    instruction="Be helpful and safe",
    tools=[...],
)

# Create runner with plugin
runner = Runner(
    agent=agent,
    app_name="my-app",
    plugins=[plugin],
)
```

### Strands Agents

```python
from strands import Agent
from sondera.harness import SonderaRemoteHarness
from sondera.strands import SonderaHarnessHook

# Create harness
harness = SonderaRemoteHarness(
    sondera_api_key="<YOUR_SONDERA_API_KEY>",
)

# Create hook
hook = SonderaHarnessHook(harness=harness)

# Create agent with hook
agent = Agent(
    system_prompt="You are a helpful assistant",
    model="anthropic.claude-3-5-sonnet-20241022-v2:0",
    hooks=[hook],
)

# Run agent (hooks fire automatically)
response = agent("What is 5 + 3?")
```

### Custom Scaffold 

```python
from sondera import SonderaRemoteHarness, Agent, PromptContent, Role, Stage

# Create a harness instance
harness = SonderaRemoteHarness(
    sondera_harness_endpoint="localhost:50051",
    sondera_api_key="<YOUR_SONDERA_API_KEY>",
    sondera_harness_client_secure=True,  # Enable TLS for production
)

# Define your agent
agent = Agent(
    id="my-agent",
    provider_id="custom",
    name="My Assistant",
    description="A helpful AI assistant",
    instruction="Be helpful, accurate, and safe",
    tools=[],
)

# Initialize a trajectory
await harness.initialize(agent=agent)

# Adjudicate user input
adjudication = await harness.adjudicate(
    Stage.PRE_MODEL,
    Role.USER,
    PromptContent(text="Hello, can you help me?"),
)

if adjudication.is_allowed:
    # Proceed with agent logic
    pass
elif adjudication.is_denied:
    print(f"Request blocked: {adjudication.reason}")

# Finalize the trajectory
await harness.finalize()
```

## Remote and Local Harnesses

### Cedar Policy Harness (Local Only)

For a local harness deployment, you can use the `CedarPolicyHarness` to evaluate Cedar policies:

```python
from sondera.harness import CedarPolicyHarness
from sondera import Agent

# Define Cedar policies
policies = '''
@id("forbid-dangerous-bash")
forbid(
  principal,
  action == Coding_Agent::Action::"Bash",
  resource
)
when {
  context has parameters &&
  (context.parameters.command like "*rm -rf /*" ||
   context.parameters.command like "*mkfs*" ||
   context.parameters.command like "*dd if=/dev/zero*" ||
   context.parameters.command like "*> /dev/sda*")
};
'''

# Create local policy engine
harness = CedarPolicyHarness(
    policy_set=policies,
    agent=my_agent,
)

await harness.initialize()
# Use same adjudication API as RemoteHarness
```

## CLI & TUI

Launch the Sondera TUI for monitoring (note, requires a Sondera account and API key):

```bash
sondera
```

The TUI provides:
- Real-time agent and trajectory overview
- Adjudication history and policy violations
- Agent details and tool inspection

## Examples

See the [examples/](examples/) directory for complete demos:

- **LangGraph**: Investment chatbot with policy enforcement
- **ADK**: Payment and healthcare agents
- **Strands**: Various agent implementations

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SONDERA_HARNESS_ENDPOINT` | Harness service endpoint | `localhost:50051` |
| `SONDERA_API_TOKEN` | JWT authentication token | Required for remote |

## Requirements

- Python 3.12 or higher (up to 3.14)

## Security

See [SECURITY.md](SECURITY.md) for security best practices and vulnerability reporting.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

## License

MIT - see [LICENSE](LICENSE) for details.