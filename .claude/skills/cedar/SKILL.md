---
name: cedar
description: Authors, validates, and tests Cedar authorization policies and schemas for Sondera AI agent governance. Use when writing .cedar or .cedarschema files, working with agent guardrails, YARA signatures, sensitivity labels, or information flow control policies.
---

# Cedar Policy Authoring for Sondera

Write Cedar policies that govern AI coding agent behavior — shell commands, file operations, web fetches, and prompts —
using YARA signature detection, policy compliance checks, and sensitivity labels.

**Cedar language reference**: See [CEDAR_REFERENCE.md](CEDAR_REFERENCE.md) for full syntax, schema authoring, data
types, operators, templates, authorization patterns, and best practices.

## MCP Tools

The `cedar` MCP server (configured in `.mcp.json`) provides four tools:

| Tool                   | Purpose                                                       |
|------------------------|---------------------------------------------------------------|
| `validate_policy`      | Validate a single Cedar policy — returns effect, id, annotations, formatted text |
| `validate_policy_set`  | Validate multiple Cedar policies at once — returns count, policy summaries, formatted text |
| `validate_schema`      | Validate a Cedar schema (JSON or Cedar format) — returns entity types, actions, principals, resources |
| `format_policy`        | Format Cedar policy text to canonical form                    |

## Workflow

Follow this checklist when authoring Cedar policies:

```
- [ ] Step 1: Read and validate schema
- [ ] Step 2: Write policy
- [ ] Step 3: Validate policy
- [ ] Step 4: Format policy
```

**Step 1: Read and validate schema**

1. Read `policies/base.cedarschema` to understand the available entity types, actions, and context fields
2. Call `validate_schema` with the schema contents (use `schema_format: "cedar"` for `.cedarschema` files) to confirm
   it is valid and to see the list of entity types, actions, principals, and resources

**Step 2: Write policy**

Use the Sondera context features below and the syntax in [CEDAR_REFERENCE.md](CEDAR_REFERENCE.md).

**Step 3: Validate policy**

- For a single policy: call `validate_policy` with the policy text to catch syntax errors
- For multiple policies: call `validate_policy_set` with all policies to validate them together

Both tools return the parsed representation including effect, id, and annotations.

**Step 4: Format policy**

Call `format_policy` for consistent style before saving.

---

## Key Pitfalls

- **`like` is an infix operator**, not a method: `context.path like "*.py"` (correct) — NOT `context.path.like("*.py")`
- **`*` wildcard matches broadly**: `context.command like "*rm*"` matches `rm` but also `format`, `firmware`
- **Guard optional attributes**: always check `has` before access — `resource has "location" && resource.location == "US"`
- **Explicit deny wins**: a single matching `forbid` overrides all `permit` policies
- **Default deny**: if no policy matches, access is denied
- **Scope over conditions**: use principal/action/resource constraints in policy scope, not in `when` clauses

---

## Quick Reference

```
POLICY:   @id("name") permit|forbid (principal, action, resource) when {...} unless {...};
SCOPE:    == (exact) | in (hierarchy) | is (type check) | in [...] (set)
STRING:   like "pattern*"   (* = wildcard)
SET:      .contains(x)  .containsAll(s)  .containsAny(s)  .isEmpty()
ATTR:     entity.attr  entity["attr"]  entity has "attr"
LOGIC:    &&  ||  !  if...then...else
COMPARE:  ==  !=  <  <=  >  >=
ARITH:    +  -  *  (Long only, no division)
ENTITY:   Type::"id"  Namespace::Type::"id"
```
