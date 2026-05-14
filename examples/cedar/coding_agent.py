import asyncio
import sys

from archetypes.coding.naive import agent
from loguru import logger

from cedar import PolicySet, Schema
from sondera import CedarPolicyHarness, Decision, Event, Prompt, ToolCall
from sondera.harness.cedar.schema import agent_to_cedar_schema

logger.remove()
logger.add(sys.stderr, level="DEBUG")


# Define tools for the coding agent

base_schema = agent_to_cedar_schema(agent)
schema = Schema.from_json(base_schema.model_dump_json(indent=2, exclude_none=True))

logger.debug(schema.to_cedarschema())

policy_set = PolicySet("""
// Allow all user prompts
@id("allow-prompts")
permit(principal, action == Coding_Agent::Action::"Prompt", resource);

// Allow all tool invocations by default (restricted by forbid rules below)
@id("allow-tool-use")
permit(principal, action == Coding_Agent::Action::"PreToolUse", resource);

// Allow all tool outputs
@id("allow-tool-output")
permit(principal, action == Coding_Agent::Action::"ToolOutput", resource);

// Forbid writing to sensitive configuration files
@id("forbid-sensitive-write")
forbid(
  principal,
  action == Coding_Agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "Write" &&
  context has parameters &&
  (context.parameters.file_path like "*.env*" ||
   context.parameters.file_path like "*.git/*" ||
   context.parameters.file_path like "*credentials*" ||
   context.parameters.file_path like "*secrets*")
};

// Forbid editing sensitive files
@id("forbid-sensitive-edit")
forbid(
  principal,
  action == Coding_Agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "Edit" &&
  context has parameters &&
  (context.parameters.file_path like "*.env*" ||
   context.parameters.file_path like "*id_rsa*" ||
   context.parameters.file_path like "*.pem*")
};

// Forbid dangerous bash commands that could cause data loss
@id("forbid-dangerous-bash")
forbid(
  principal,
  action == Coding_Agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "Bash" &&
  context has parameters &&
  (context.parameters.command like "*rm -rf /*" ||
   context.parameters.command like "*mkfs*" ||
   context.parameters.command like "*dd if=/dev/zero*" ||
   context.parameters.command like "*> /dev/sda*")
};

// Forbid fetching from untrusted domains
@id("forbid-untrusted-fetch")
forbid(
  principal,
  action == Coding_Agent::Action::"PreToolUse",
  resource
)
when {
  context.tool == "WebFetch" &&
  context has parameters &&
  (context.parameters.url like "*pastebin*" ||
   context.parameters.url like "*raw.githubusercontent.com*")
};

// Rate limiting: forbid operations after 1000 steps to prevent runaway
@id("rate-limit-trajectory")
forbid(
  principal,
  action,
  resource
)
when {
  resource has step_count &&
  resource.step_count > 1000
};
""")


def _event(harness, payload):
    return Event(
        agent=harness.agent,
        trajectory_id=harness.trajectory_id,
        event=payload,
    )


async def main():
    harness = CedarPolicyHarness(policy_set=policy_set, schema=base_schema)
    await harness.initialize(agent=agent)

    result = await harness.adjudicate(
        _event(harness, Prompt(role="user", content="Hello world!"))
    )
    logger.success(f"User prompt. Decision: {result.decision}")
    assert result.decision == Decision.ALLOW

    result = await harness.adjudicate(
        _event(
            harness,
            ToolCall(
                tool="Read", arguments={"file_path": "/Users/user/project/main.py"}
            ),
        )
    )
    logger.success(f"Reading a file. ({result.decision})")
    assert result.decision == Decision.ALLOW

    result = await harness.adjudicate(
        _event(
            harness,
            ToolCall(
                tool="Write",
                arguments={
                    "file_path": "/Users/user/project/.env",
                    "content": "API_KEY=secret",
                },
            ),
        )
    )
    logger.error(f"Writing to .env file (should be forbidden). ({result.decision})")
    assert result.decision == Decision.DENY

    result = await harness.adjudicate(
        _event(
            harness,
            ToolCall(
                tool="Write",
                arguments={
                    "file_path": "/Users/user/project/tests/test_feature.py",
                    "content": "def test_example(): pass",
                },
            ),
        )
    )
    logger.success(f"Writing to test file. ({result.decision})")
    assert result.decision == Decision.ALLOW

    result = await harness.adjudicate(
        _event(
            harness,
            ToolCall(tool="Bash", arguments={"command": "rm -rf /"}),
        )
    )
    logger.error(f"Dangerous bash command (should be forbidden). ({result.decision})")
    assert result.decision == Decision.DENY

    result = await harness.adjudicate(
        _event(
            harness,
            ToolCall(tool="Bash", arguments={"command": "git status"}),
        )
    )
    logger.success(f"Safe bash command (git). ({result.decision})")
    assert result.decision == Decision.ALLOW

    result = await harness.adjudicate(
        _event(
            harness,
            ToolCall(
                tool="Edit",
                arguments={
                    "file_path": "/Users/user/.ssh/id_rsa",
                    "old_string": "old",
                    "new_string": "new",
                },
            ),
        )
    )
    logger.error(f"Editing SSH key (should be forbidden). ({result.decision})")
    assert result.decision == Decision.DENY

    result = await harness.adjudicate(
        _event(
            harness,
            ToolCall(tool="Glob", arguments={"pattern": "**/*.py"}),
        )
    )
    logger.success(f"Glob search. ({result.decision})")
    assert result.decision == Decision.ALLOW

    result = await harness.adjudicate(
        _event(
            harness,
            ToolCall(
                tool="WebSearch",
                arguments={"query": "Python API documentation"},
            ),
        )
    )
    logger.success(f"WebSearch for documentation. ({result.decision})")
    assert result.decision == Decision.ALLOW

    result = await harness.adjudicate(
        _event(
            harness,
            ToolCall(
                tool="WebFetch",
                arguments={
                    "url": "https://pastebin.com/raw/abc123",
                    "prompt": "Get the content",
                },
            ),
        )
    )
    logger.error(f"WebFetch from pastebin (should be forbidden). ({result.decision})")
    assert result.decision == Decision.DENY

    logger.info(
        "Writing output schema and policy files: coding.cedarschema, coding.cedar"
    )
    with open("coding.cedarschema", "w") as fout:
        fout.write(schema.to_cedarschema())
    with open("coding.cedar", "w") as fout:
        cedar_output = policy_set.to_cedar()
        if cedar_output:
            fout.write(cedar_output)


if __name__ == "__main__":
    asyncio.run(main())
