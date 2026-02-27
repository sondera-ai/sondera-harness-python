"""Trajectory Theater: Plugin-based visualization system for agent trajectories."""

from sondera.tui.theater.events import StepEvent
from sondera.tui.theater.player import TrajectoryPlayer
from sondera.tui.theater.plugin import TheaterPlugin

__all__ = [
    "StepEvent",
    "TheaterPlugin",
    "TrajectoryPlayer",
]
