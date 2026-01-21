import asyncio
import sys

from archetypes.coding.naive import agent
from loguru import logger

from cedar import PolicySet, Schema
from sondera import (
    CedarPolicyHarness,
    Decision,
    PromptContent,
    Role,
    Stage,
    ToolRequestContent,
)
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

// Allow all read operations - reading is generally safe
@id("allow-read")
permit(principal, action == Coding_Agent::Action::"Read", resource);

// Allow file pattern searches
@id("allow-glob")
permit(principal, action == Coding_Agent::Action::"Glob", resource);

// Allow code searches
@id("allow-grep")
permit(principal, action == Coding_Agent::Action::"Grep", resource);

// Allow all write operations by default (will be restricted by forbid rules)
@id("allow-write")
permit(principal, action == Coding_Agent::Action::"Write", resource);

// Allow all edit operations by default (will be restricted by forbid rules)
@id("allow-edit")
permit(principal, action == Coding_Agent::Action::"Edit", resource);

// Forbid writing to sensitive configuration files
@id("forbid-sensitive-write")
forbid(
  principal,
  action == Coding_Agent::Action::"Write",
  resource
)
when {
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
  action == Coding_Agent::Action::"Edit",
  resource
)
when {
  context has parameters &&
  (context.parameters.file_path like "*.env*" ||
   context.parameters.file_path like "*id_rsa*" ||
   context.parameters.file_path like "*.pem*")
};

// Allow all bash commands by default (will be restricted by forbid rules)
@id("allow-bash")
permit(principal, action == Coding_Agent::Action::"Bash", resource);

// Forbid dangerous bash commands that could cause data loss
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

// Allow all web searches by default
@id("allow-web-search")
permit(principal, action == Coding_Agent::Action::"WebSearch", resource);

// Allow all web fetches by default (will be restricted by forbid rules)
@id("allow-web-fetch")
permit(principal, action == Coding_Agent::Action::"WebFetch", resource);

// Forbid fetching from untrusted domains
@id("forbid-untrusted-fetch")
forbid(
  principal,
  action == Coding_Agent::Action::"WebFetch",
  resource
)
when {
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


async def main():
    harness = CedarPolicyHarness(policy_set=policy_set, schema=base_schema)
    await harness.initialize(agent=agent)

    result = await harness.adjudicate(
        Stage.PRE_MODEL, Role.USER, PromptContent(text="Hello world!")
    )
    logger.success(f"User prompt. Decision: {result.decision}")
    assert result.decision == Decision.ALLOW

    result = await harness.adjudicate(
        Stage.PRE_TOOL,
        Role.MODEL,
        ToolRequestContent(
            tool_id="Read", args={"file_path": "/Users/maisel/code/main.py"}
        ),
    )
    logger.success(f"Reading a file. ({result.decision})")
    assert result.decision == Decision.ALLOW

    result = await harness.adjudicate(
        Stage.PRE_TOOL,
        Role.MODEL,
        ToolRequestContent(
            tool_id="Write",
            args={"file_path": "/Users/maisel/code/.env", "content": "API_KEY=secret"},
        ),
    )
    logger.error(f"Writing to .env file (should be forbidden). ({result.decision})")
    assert result.decision == Decision.DENY

    result = await harness.adjudicate(
        Stage.PRE_TOOL,
        Role.MODEL,
        ToolRequestContent(
            tool_id="Write",
            args={
                "file_path": "/Users/maisel/code/tests/test_feature.py",
                "content": "def test_example(): pass",
            },
        ),
    )
    logger.success(f"Writing to test file. ({result.decision})")
    assert result.decision == Decision.ALLOW

    result = await harness.adjudicate(
        Stage.PRE_TOOL,
        Role.MODEL,
        ToolRequestContent(tool_id="Bash", args={"command": "rm -rf /"}),
    )
    logger.error(f"Dangerous bash command (should be forbidden). ({result.decision})")
    assert result.decision == Decision.DENY

    result = await harness.adjudicate(
        Stage.PRE_TOOL,
        Role.MODEL,
        ToolRequestContent(tool_id="Bash", args={"command": "git status"}),
    )
    logger.success(f"Safe bash command (git). ({result.decision})")
    assert result.decision == Decision.ALLOW

    result = await harness.adjudicate(
        Stage.PRE_TOOL,
        Role.MODEL,
        ToolRequestContent(
            tool_id="Edit",
            args={
                "file_path": "/Users/maisel/.ssh/id_rsa",
                "old_string": "old",
                "new_string": "new",
            },
        ),
    )
    logger.error(f"Editing SSH key (should be forbidden). ({result.decision})")
    assert result.decision == Decision.DENY

    result = await harness.adjudicate(
        Stage.PRE_TOOL,
        Role.MODEL,
        ToolRequestContent(tool_id="Glob", args={"pattern": "**/*.py"}),
    )
    logger.success(f"Glob search. ({result.decision})")
    assert result.decision == Decision.ALLOW

    result = await harness.adjudicate(
        Stage.PRE_TOOL,
        Role.MODEL,
        ToolRequestContent(
            tool_id="WebSearch", args={"query": "Python API documentation"}
        ),
    )
    logger.success(f"WebSearch for documentation. ({result.decision})")
    assert result.decision == Decision.ALLOW

    result = await harness.adjudicate(
        Stage.PRE_TOOL,
        Role.MODEL,
        ToolRequestContent(
            tool_id="WebFetch",
            args={
                "url": "https://pastebin.com/raw/abc123",
                "prompt": "Get the content",
            },
        ),
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
