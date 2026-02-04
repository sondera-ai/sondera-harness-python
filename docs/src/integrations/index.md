---
title: Integrations
description: Add Sondera Harness to LangGraph, Google ADK, Strands, OpenClaw, or build your own
---

# Integrations

Sondera Harness provides native integrations for popular agent frameworks, plus a direct API for custom architectures. Each integration uses your framework's native extension pattern, so there's no need to change how your agent works.

**New to Sondera?** Start with [Core Concepts](../concepts/index.md) to understand how the harness intercepts agent actions.

---

## Choose Your Framework

<div class="grid cards" markdown>

-   :simple-langchain:{ .lg .middle } **LangGraph**

    ---

    AgentMiddleware pattern with automatic tool discovery.

    Requires LangGraph 0.3+

    [View guide](langgraph.md)

-   :simple-google:{ .lg .middle } **Google ADK**

    ---

    BasePlugin callbacks for Google's Agent Development Kit.

    Requires ADK 1.0+

    [View guide](adk.md)

-   :material-dna:{ .lg .middle } **Strands**

    ---

    Lifecycle hooks for AWS's Strands framework.

    Requires Strands 0.1+

    [View guide](strands.md)

-   :material-robot:{ .lg .middle } **OpenClaw**

    ---

    Local Cedar policy evaluation for OpenClaw AI agents. No API calls required.

    TypeScript extension

    [View guide](openclaw.md)

-   :material-code-braces:{ .lg .middle } **Custom Agent**

    ---

    Direct Harness API for any architecture. Full control over when and how policies evaluate.

    [View guide](custom.md)

</div>

**Not sure which to pick?** Use [Custom](custom.md) if your framework isn't listed or if you want full control over when policies evaluate.
