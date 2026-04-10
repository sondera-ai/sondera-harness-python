# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.10.0] - 2026-04-10

- Sondera pydantic integration and corresponding example agents & policies

## [0.9.1] - 2026-04-08

### Fixed

- Pass `trajectory_id` in Started event to prevent trajectory fragmentation across all SDK providers

## [0.9.0] - 2026-04-07

### Added

- `sondera auth login` command for browser-based authentication
- `session_id` support across all framework integrations (LangGraph, ADK, Strands)
- `TrajectoryStorage` file-based implementation
- Additional top-level SDK exports including `Mode`, `Steering`, `Scanned`, signature guardrail result types, and agent card types
- New SDK fields including `Agent.platform`, `Completed.summary`, and escalation metadata on `PolicyMetadata`
- Scanned event correlation and LLM-based analysis context
- Live `stream_trajectories` replacing poll-based TUI refresh
- Trajectory Theater for playback visualization
- AI Assist panel, config modal, and Flying Agents screensaver in TUI
- Dashboard redesign with violations-first UX
- Pagination and adjudication UX improvements in TUI
- OpenClaw integration guide
- Colab notebooks

### Changed

- `sondera` and `sondera.types` now re-export `sondera_harness_client` types
- Remote harness and framework integrations now use the trajectory event model
- Updated the LangGraph integration API
- Renamed `@reason` Cedar annotation to `@description`
- Renamed `PolicyAnnotation` to `PolicyMetadata`
- Migrated documentation from mdBook to MkDocs
- Standardized trajectory and agent status terminology in TUI

### Removed

- Standalone `Adjudication` result type; use `Adjudicated`
- Generated protobuf modules under `sondera.proto`
- `is_denied`, `is_allowed`, and `is_escalated` helpers (use `Decision` enum directly)

### Fixed

- TUI: deduplicate adjudication records in dashboard counts

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
