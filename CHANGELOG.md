# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.8.2] - 2026-02-27

## [0.8.1] - 2026-02-27

### Fixed

- Don't call `resume()` on already-active trajectory in same session

### Added

- `TrajectoryStorage` ABC and file-based implementation
- Cedar policy improvements and local policy support for ADK examples
- AI Assist, config modal, and Flying Agents screensaver in TUI
- Trajectory Theater for playback visualization
- Pagination support and adjudication UX improvements in TUI
- `min_step_count` filter for `list_trajectories` in SDK and TUI
- Configurable `api_key_header` and `extra_metadata` on harness
- GitHub Copilot SDK example (`investment_chatbot`)
- Claude Code integration example with Pre/PostToolUse hooks
- Pre-commit hooks (ruff, pyright, detect-secrets)

### Changed

- Trajectory data model improvements
- Redesigned `SonderaGraph` wrapper for LangGraph
- Dashboard redesign with violations-first UX
- Standardized trajectory and agent status terminology in TUI
- Changed Cedar `@reason` annotation to `@description`
- Replaced manual proto sync with `sondera-apis` subtree
- Removed proto generation infrastructure; committed generated stubs
- Standardized CI/CD pipeline

### Removed

- `is_denied`, `is_allowed`, and `is_escalated` helpers (use `Decision` enum directly)
- Deduplicated adjudication records in dashboard counts

### Docs

- Migrated from mdBook to MkDocs with comprehensive documentation
- Added OpenClaw integration guide
- Added Colab notebooks

## [0.8.0] - 2026-02-26

### Changed

- Simplified Adjudication API and documentation overhaul

### Fixed

- Upgraded protobuf in Colab notebooks to fix version mismatch

## [0.7.1] - 2026-02-03

### Changed

- Simplified `Adjudication` by removing `policy_ids`; renamed `PolicyAnnotation` to `PolicyMetadata`
- Required `@id` annotation on Cedar policies; set `policy_ids` and `annotations` for all decision values

### Fixed

- Moved `grpcio-tools` from runtime to dev dependencies

### Docs

- Added OpenClaw integration guide
- Updated docs with escalation info

## [0.7.0] - 2026-01-31

### Added

- Colab notebooks for quickstart and custom integration
- Simplified decision API in Adjudication
- Support for `@escalate` Cedar annotation for HITL verdicts
- `uvx sondera-harness` support

## [0.6.3] - 2026-01-29

### Added

- Tool schema, guardrail context, and policy IDs

### Fixed

- Packaged Textual TCSS files in wheel

## [0.6.0] - 2025-01-12

### Added

- RecentAdjudications widget in TUI showing all adjudications
- Trajectory navigation from AdjudicationScreen (press 'e' to open)
- OpenAI JSON schema extraction for LangGraph tools
- Adjudication screen in TUI

### Changed

- Replaced RecentViolations widget with RecentAdjudications widget
- Updated action_select_row to filter by agent when selecting adjudication

### Removed

- RecentViolations widget (replaced by RecentAdjudications)

## [0.5.0] - 2025-01-08

### Added

- LangGraph middleware integration (`SonderaHarnessMiddleware`)
- Google ADK plugin integration (`SonderaHarnessPlugin`)
- Strands hook integration (`SonderaHarnessHook`)
- Trajectory tracking and adjudication system
- TUI for viewing trajectories and adjudications
- CLI entry point (`sondera` command)

### Changed

- Standardized harness interface with `Harness` abstract base class
- Migrated to dependency injection pattern for framework integrations

## [0.4.0] - 2025-01-05

### Added

- Initial RemoteHarness implementation with gRPC
- LocalHarness for development and testing
- Core types: Agent, Trajectory, Adjudication, Decision

### Changed

- Restructured project layout with `src/sondera/` namespace

## [0.3.0] - 2024-12-20

### Added

- Protocol buffer definitions for Harness Service
- Async gRPC client implementation
- JWT-based authentication support

## [0.2.0] - 2024-12-15

### Added

- Initial SDK structure
- Pydantic models for core types
- Settings management with pydantic-settings

## [0.1.0] - 2024-12-01

### Added

- Initial project setup
- Basic package structure
