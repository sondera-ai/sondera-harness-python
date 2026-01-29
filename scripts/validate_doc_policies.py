#!/usr/bin/env python3
"""Validate all Cedar policy examples in documentation files.

Extracts ```cedar code blocks from markdown and validates their syntax.

Usage:
    uv run python scripts/validate_doc_policies.py [file.md ...]
    uv run python scripts/validate_doc_policies.py  # validates docs/src/writing-policies.md
"""

import sys
from pathlib import Path

from cedar import PolicySet


def extract_cedar_blocks(markdown_text: str) -> list[tuple[int, str]]:
    """Extract all ```cedar code blocks from markdown.

    Returns list of (line_number, code) tuples.
    """
    blocks = []
    lines = markdown_text.split("\n")
    in_cedar_block = False
    block_start_line = 0
    current_block: list[str] = []

    for i, line in enumerate(lines, start=1):
        if line.strip().startswith("```cedar"):
            in_cedar_block = True
            block_start_line = i
            current_block = []
        elif line.strip() == "```" and in_cedar_block:
            in_cedar_block = False
            blocks.append((block_start_line, "\n".join(current_block)))
        elif in_cedar_block:
            current_block.append(line)

    return blocks


def validate_policy(policy_text: str) -> tuple[bool, str]:
    """Try to parse a Cedar policy.

    Returns (success, error_message).
    """
    try:
        PolicySet(policy_text)
        return True, ""
    except Exception as e:
        return False, str(e)


def validate_file(filepath: Path) -> list[tuple[int, str, str]]:
    """Validate all Cedar policies in a markdown file.

    Returns list of (line_number, policy_snippet, error) for failures.
    """
    content = filepath.read_text()
    blocks = extract_cedar_blocks(content)
    failures = []

    for line_num, policy_text in blocks:
        success, error = validate_policy(policy_text)
        if not success:
            # Get first 50 chars as snippet
            snippet = policy_text.strip()[:50].replace("\n", " ")
            failures.append((line_num, snippet, error))

    return failures


def main():
    if len(sys.argv) > 1:
        files = [Path(f) for f in sys.argv[1:]]
    else:
        # Default to writing-policies.md
        files = [Path("docs/src/writing-policies.md")]

    total_blocks = 0
    total_failures = 0

    for filepath in files:
        if not filepath.exists():
            print(f"ERROR: File not found: {filepath}")
            continue

        content = filepath.read_text()
        blocks = extract_cedar_blocks(content)
        failures = validate_file(filepath)

        total_blocks += len(blocks)
        total_failures += len(failures)

        if failures:
            print(
                f"\n{filepath}: {len(failures)} failures out of {len(blocks)} policies"
            )
            for line_num, snippet, error in failures:
                print(f"  Line {line_num}: {snippet}...")
                print(f"    Error: {error}")
        else:
            print(f"{filepath}: {len(blocks)} policies validated successfully")

    print(f"\nTotal: {total_blocks} policies, {total_failures} failures")
    return 1 if total_failures > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
