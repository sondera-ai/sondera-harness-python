"""Custom Pygments lexer for Cedar policy language.

This lexer provides syntax highlighting for Cedar policies in MkDocs documentation.

To use:
1. Install as a Pygments plugin (see pyproject.toml entry_points)
2. MkDocs will automatically use it for ```cedar code blocks
"""

from pygments.lexer import RegexLexer, bygroups, words
from pygments.token import (
    Comment,
    Keyword,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    Whitespace,
)


class CedarLexer(RegexLexer):
    """Pygments lexer for Cedar policy language.

    Cedar is an open-source language for authorization policies.
    See: https://www.cedarpolicy.com/
    """

    name = "Cedar"
    aliases = ["cedar"]
    filenames = ["*.cedar"]
    mimetypes = ["text/x-cedar"]

    tokens = {
        "root": [
            # Whitespace
            (r"\s+", Whitespace),
            # Single-line comments
            (r"//.*$", Comment.Single),
            # Annotations like @id("policy-name")
            (
                r"(@\w+)(\()([\"'])([^\"']+)([\"'])(\))",
                bygroups(
                    Name.Decorator,  # @id
                    Punctuation,  # (
                    String,  # opening quote
                    String,  # content
                    String,  # closing quote
                    Punctuation,  # )
                ),
            ),
            # Policy keywords
            (
                words(
                    (
                        "permit",
                        "forbid",
                        "when",
                        "unless",
                    ),
                    suffix=r"\b",
                ),
                Keyword,
            ),
            # Principal/action/resource keywords
            (
                words(
                    (
                        "principal",
                        "action",
                        "resource",
                        "context",
                    ),
                    suffix=r"\b",
                ),
                Keyword.Pseudo,
            ),
            # Operators and built-ins
            (
                words(
                    (
                        "in",
                        "has",
                        "like",
                        "is",
                        "if",
                        "then",
                        "else",
                    ),
                    suffix=r"\b",
                ),
                Keyword.Operator,
            ),
            # Boolean literals
            (words(("true", "false"), suffix=r"\b"), Keyword.Constant),
            # Entity type references: Namespace::Type::"value"
            # Match the namespace and type parts
            (
                r"(\w+)(::)(\w+)(::)",
                bygroups(
                    Name.Namespace,  # Namespace
                    Operator,  # ::
                    Name.Class,  # Type (Action, Agent, etc.)
                    Operator,  # ::
                ),
            ),
            # Quoted entity names after ::
            (
                r'(")((?:[^"\\]|\\.)*)(")',
                bygroups(
                    String,
                    String,
                    String,
                ),
            ),
            # Double-quoted strings
            (r'"(?:[^"\\]|\\.)*"', String.Double),
            # Single-quoted strings (if Cedar supports them)
            (r"'(?:[^'\\]|\\.)*'", String.Single),
            # Numbers
            (r"-?\d+", Number.Integer),
            # Comparison operators
            (r"==|!=|<=|>=|<|>", Operator),
            # Logical operators
            (r"&&|\|\||!", Operator),
            # Other operators
            (r"\.", Operator),
            # Punctuation
            (r"[{}\[\](),;]", Punctuation),
            # Identifiers (variable names, field names)
            (r"\w+", Name),
        ],
    }
