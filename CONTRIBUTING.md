# Contributing to Sondera SDK

Thank you for your interest in contributing to Sondera SDK! This document provides guidelines and instructions for contributing.

## Development Setup

### Prerequisites

- Python 3.12 or higher (up to 3.14)
- [uv](https://github.com/astral-sh/uv) package manager

### Installation

```bash
# Clone the repository
git clone https://github.com/sondera-ai/harness-sdk-python.git
cd harness-sdk-python

# Install with all optional dependencies for development
uv sync --all-extras --all-groups
```

### Running Tests

```bash
# Run all tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=sondera

# Run a specific test file
uv run pytest tests/langgraph/test_middleware.py

# Run a specific test
uv run pytest tests/test_harness.py::TestMetadataInjection::test_create_trajectory_injects_auth_metadata
```

### Code Quality

```bash
# Format code
uv run ruff format

# Lint code
uv run ruff check

# Type checking
uv run pyright
```

## Code Style

- Follow PEP 8 guidelines
- Use type hints for all function signatures
- Write docstrings for public functions and classes
- Keep functions focused and small
- Use meaningful variable and function names

## Pull Request Process

1. Fork the repository and create a feature branch from `main`
2. Make your changes following the code style guidelines
3. Add or update tests as needed
4. Ensure all tests pass and code quality checks succeed
5. Update documentation if you're changing public APIs
6. Submit a pull request with a clear description of your changes

### PR Title Format

Use conventional commit format for PR titles:

- `feat:` - New features
- `fix:` - Bug fixes
- `docs:` - Documentation changes
- `test:` - Test additions or modifications
- `refactor:` - Code refactoring
- `chore:` - Maintenance tasks

## Reporting Issues

When reporting issues, please include:

- A clear description of the problem
- Steps to reproduce the issue
- Expected vs actual behavior
- Python version and OS
- Relevant error messages or logs

## Questions?

If you have questions about contributing, feel free to open a discussion on GitHub.
