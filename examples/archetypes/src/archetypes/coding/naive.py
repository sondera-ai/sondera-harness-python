"""Naive coding agent with Claude Code-style tools.

This agent provides a basic coding assistant with tools modeled after Claude Code's
built-in capabilities for file operations, shell commands, and web access.
"""

import json

from sondera import Agent, Parameter, Tool

# File Operations
read_tool = Tool(
    name="Read",
    description="Read the contents of a file from the filesystem",
    parameters=[
        Parameter(
            name="file_path",
            description="The absolute path to the file to read",
            type="string",
        ),
        Parameter(
            name="offset",
            description="Line number to start reading from (optional)",
            type="integer",
        ),
        Parameter(
            name="limit",
            description="Number of lines to read (optional)",
            type="integer",
        ),
    ],
    parameters_json_schema=json.dumps(
        {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The absolute path to the file to read",
                },
                "offset": {
                    "type": "integer",
                    "description": "Line number to start reading from",
                },
                "limit": {"type": "integer", "description": "Number of lines to read"},
            },
            "required": ["file_path"],
        }
    ),
    response="string",
    response_json_schema=json.dumps(
        {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The file contents with line numbers",
                },
                "success": {
                    "type": "boolean",
                    "description": "Whether the operation succeeded",
                },
            },
        }
    ),
)

write_tool = Tool(
    name="Write",
    description="Write or overwrite a file with new content",
    parameters=[
        Parameter(
            name="file_path",
            description="The absolute path to the file to write",
            type="string",
        ),
        Parameter(
            name="content",
            description="The content to write to the file",
            type="string",
        ),
    ],
    parameters_json_schema=json.dumps(
        {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The absolute path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "The content to write to the file",
                },
            },
            "required": ["file_path", "content"],
        }
    ),
    response="object",
    response_json_schema=json.dumps(
        {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether the write succeeded",
                }
            },
        }
    ),
)

edit_tool = Tool(
    name="Edit",
    description="Make targeted edits to a file by replacing exact string matches",
    parameters=[
        Parameter(
            name="file_path",
            description="The absolute path to the file to modify",
            type="string",
        ),
        Parameter(
            name="old_string",
            description="The exact text to find and replace",
            type="string",
        ),
        Parameter(
            name="new_string", description="The new text to replace with", type="string"
        ),
        Parameter(
            name="replace_all",
            description="Replace all occurrences (default: false)",
            type="boolean",
        ),
    ],
    parameters_json_schema=json.dumps(
        {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The absolute path to the file to modify",
                },
                "old_string": {
                    "type": "string",
                    "description": "The exact text to find and replace",
                },
                "new_string": {
                    "type": "string",
                    "description": "The new text to replace with",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences",
                    "default": False,
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        }
    ),
    response="object",
    response_json_schema=json.dumps(
        {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether the edit succeeded",
                },
                "replacements": {
                    "type": "integer",
                    "description": "Number of replacements made",
                },
            },
        }
    ),
)

# Search and Discovery
grep_tool = Tool(
    name="Grep",
    description="Search for patterns in file contents using regular expressions",
    parameters=[
        Parameter(
            name="pattern",
            description="The regular expression pattern to search for",
            type="string",
        ),
        Parameter(
            name="path",
            description="File or directory to search in (optional)",
            type="string",
        ),
        Parameter(
            name="glob",
            description="Glob pattern to filter files (e.g., '*.py')",
            type="string",
        ),
        Parameter(
            name="case_insensitive",
            description="Case insensitive search",
            type="boolean",
        ),
        Parameter(
            name="output_mode",
            description="Output mode: 'content', 'files_with_matches', or 'count'",
            type="string",
        ),
    ],
    parameters_json_schema=json.dumps(
        {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "The regular expression pattern to search for",
                },
                "path": {
                    "type": "string",
                    "description": "File or directory to search in",
                },
                "glob": {
                    "type": "string",
                    "description": "Glob pattern to filter files",
                },
                "case_insensitive": {
                    "type": "boolean",
                    "description": "Case insensitive search",
                    "default": False,
                },
                "output_mode": {
                    "type": "string",
                    "enum": ["content", "files_with_matches", "count"],
                    "default": "files_with_matches",
                },
            },
            "required": ["pattern"],
        }
    ),
    response="object",
    response_json_schema=json.dumps(
        {
            "type": "object",
            "properties": {
                "matches": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Matching lines or file paths",
                },
                "count": {"type": "integer", "description": "Number of matches"},
            },
        }
    ),
)

glob_tool = Tool(
    name="Glob",
    description="Find files matching a glob pattern",
    parameters=[
        Parameter(
            name="pattern",
            description="The glob pattern to match (e.g., '**/*.py')",
            type="string",
        ),
        Parameter(
            name="path", description="Directory to search in (optional)", type="string"
        ),
    ],
    parameters_json_schema=json.dumps(
        {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "The glob pattern to match",
                },
                "path": {"type": "string", "description": "Directory to search in"},
            },
            "required": ["pattern"],
        }
    ),
    response="array",
    response_json_schema=json.dumps(
        {
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of matching file paths",
                }
            },
        }
    ),
)

# Command Execution
bash_tool = Tool(
    name="Bash",
    description="Execute a shell command in a persistent session",
    parameters=[
        Parameter(
            name="command", description="The shell command to execute", type="string"
        ),
        Parameter(
            name="timeout",
            description="Timeout in milliseconds (max 600000)",
            type="integer",
        ),
    ],
    parameters_json_schema=json.dumps(
        {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in milliseconds",
                    "default": 120000,
                    "maximum": 600000,
                },
            },
            "required": ["command"],
        }
    ),
    response="object",
    response_json_schema=json.dumps(
        {
            "type": "object",
            "properties": {
                "stdout": {
                    "type": "string",
                    "description": "Standard output from the command",
                },
                "stderr": {
                    "type": "string",
                    "description": "Standard error from the command",
                },
                "exit_code": {
                    "type": "integer",
                    "description": "Exit code of the command",
                },
            },
        }
    ),
)

# Web Access
web_fetch_tool = Tool(
    name="WebFetch",
    description="Fetch content from a URL and process it with AI",
    parameters=[
        Parameter(
            name="url", description="The URL to fetch content from", type="string"
        ),
        Parameter(
            name="prompt",
            description="The prompt describing what information to extract",
            type="string",
        ),
    ],
    parameters_json_schema=json.dumps(
        {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "format": "uri",
                    "description": "The URL to fetch content from",
                },
                "prompt": {
                    "type": "string",
                    "description": "The prompt describing what information to extract",
                },
            },
            "required": ["url", "prompt"],
        }
    ),
    response="string",
    response_json_schema=json.dumps(
        {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The processed content from the URL",
                }
            },
        }
    ),
)

web_search_tool = Tool(
    name="WebSearch",
    description="Search the web with optional domain filtering",
    parameters=[
        Parameter(name="query", description="The search query", type="string"),
        Parameter(
            name="allowed_domains",
            description="Only include results from these domains",
            type="array",
        ),
        Parameter(
            name="blocked_domains",
            description="Exclude results from these domains",
            type="array",
        ),
    ],
    parameters_json_schema=json.dumps(
        {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                    "minLength": 2,
                },
                "allowed_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Only include results from these domains",
                },
                "blocked_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Exclude results from these domains",
                },
            },
            "required": ["query"],
        }
    ),
    response="array",
    response_json_schema=json.dumps(
        {
            "type": "object",
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "url": {"type": "string"},
                            "snippet": {"type": "string"},
                        },
                    },
                    "description": "Search results",
                }
            },
        }
    ),
)

agent = Agent(
    id="coding_agent",
    provider_id="custom",
    name="Coding Agent",
    description="A coding assistant with Claude Code-style tools for file operations, search, shell commands, and web access.",
    instruction="You are a helpful coding assistant with access to file operations, shell commands, and web search. Use Read before Edit to understand file contents. Prefer Edit over Write for modifying existing files.",
    tools=[
        read_tool,
        write_tool,
        edit_tool,
        grep_tool,
        glob_tool,
        bash_tool,
        web_fetch_tool,
        web_search_tool,
    ],
)
