"""Trajectory player widget for theater playback."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from textual.reactive import reactive
from textual.timer import Timer
from textual.widget import Widget

from sondera.tui.events import EventStep, correlate_events
from sondera.tui.theater.events import PlaybackComplete, PlaybackReset, StepEvent
from sondera.types import Trajectory, TrajectoryStatus

if TYPE_CHECKING:
    from datetime import datetime


class TrajectoryPlayer(Widget):
    """Plays trajectory steps with timing control.

    This widget manages trajectory playback, emitting StepEvent messages
    at configurable speeds. It supports play/pause, speed control, and
    seeking to specific steps.

    Attributes:
        playing: Whether playback is active.
        speed: Playback speed multiplier (0.5x, 1x, 2x, 4x).
        current_step: Index of the current step.
    """

    playing: reactive[bool] = reactive(False)
    """Whether playback is currently active."""

    speed: reactive[float] = reactive(1.0)
    """Playback speed multiplier."""

    current_step: reactive[int] = reactive(0)
    """Index of the current step being played."""

    SPEED_OPTIONS = [1.0, 2.0, 4.0, 8.0]
    """Available speed multipliers."""

    progress: reactive[float] = reactive(0.0)
    """Progress through trajectory (0.0 to 1.0)."""

    BASE_INTERVAL_MS = 500
    """Base interval between steps in milliseconds (at 1x speed)."""

    def __init__(
        self,
        trajectory: Trajectory | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the trajectory player.

        Args:
            trajectory: Optional trajectory to load immediately.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._trajectory: Trajectory | None = trajectory
        self._steps: list[EventStep] = []
        self._timer: Timer | None = None
        self._step_deltas: list[int] = []

    @property
    def trajectory(self) -> Trajectory | None:
        """The currently loaded trajectory."""
        return self._trajectory

    @property
    def total_steps(self) -> int:
        """Total number of steps in the loaded trajectory."""
        return len(self._steps) if self._trajectory else 0

    @property
    def has_trajectory(self) -> bool:
        """Whether a trajectory is currently loaded."""
        return self._trajectory is not None

    @property
    def is_at_end(self) -> bool:
        """Whether playback has reached the end."""
        return self.current_step >= self.total_steps - 1

    @property
    def is_at_start(self) -> bool:
        """Whether playback is at the beginning."""
        return self.current_step == 0

    def load_trajectory(self, trajectory: Trajectory, emit_first: bool = False) -> None:
        """Load a trajectory for playback.

        Args:
            trajectory: The trajectory to play.
            emit_first: Whether to emit the first step immediately.
        """
        self.pause()
        self._trajectory = trajectory
        self._steps = correlate_events(trajectory.events or [])
        self._compute_deltas()
        self.current_step = 0
        self.post_message(PlaybackReset())
        # Only emit first step if requested (for live trajectories)
        if emit_first and self.total_steps > 0:
            self._emit_current_step()

    def load_from_file(self, path: Path) -> list[Trajectory]:
        """Load trajectories from a JSON file.

        Args:
            path: Path to the JSON file containing trajectory data.

        Returns:
            List of loaded trajectories.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            ValueError: If the file format is invalid.
        """
        with open(path) as f:
            data = json.load(f)

        trajectories = []
        for traj_data in data.get("trajectories", []):
            trajectory = Trajectory(
                name=traj_data.get("name", ""),
                agent=traj_data.get("agent", ""),
                status=TrajectoryStatus.Running,
            )
            trajectories.append(trajectory)

        return trajectories

    def _compute_deltas(self) -> None:
        """Compute time deltas between steps."""
        self._step_deltas = []
        if not self._steps:
            return

        prev_time: datetime | None = None
        for step in self._steps:
            ts = step.timestamp
            if prev_time is None:
                self._step_deltas.append(0)
            else:
                delta = (ts - prev_time).total_seconds() * 1000
                self._step_deltas.append(int(max(0, delta)))
            prev_time = ts

    def play(self) -> None:
        """Start playback."""
        if not self.has_trajectory:
            return
        if self.is_at_end:
            self.reset()
        self.playing = True
        self._schedule_next()

    def pause(self) -> None:
        """Pause playback."""
        self.playing = False
        self._cancel_timer()

    def toggle(self) -> None:
        """Toggle between play and pause."""
        if self.playing:
            self.pause()
        else:
            self.play()

    def reset(self) -> None:
        """Reset playback to the beginning."""
        self.pause()
        self.current_step = 0
        self.post_message(PlaybackReset())
        if self.total_steps > 0:
            self._emit_current_step()

    def seek(self, step: int) -> None:
        """Seek to a specific step.

        Args:
            step: The step index to seek to.
        """
        was_playing = self.playing
        self.pause()
        self.current_step = max(0, min(step, self.total_steps - 1))
        if self.total_steps > 0:
            self._emit_current_step()
        if was_playing and not self.is_at_end:
            self.play()

    def step_forward(self) -> None:
        """Advance one step."""
        if self.is_at_end:
            return
        self.current_step += 1
        self._emit_current_step()
        if self.is_at_end:
            self.post_message(PlaybackComplete(total_steps=self.total_steps))

    def step_backward(self) -> None:
        """Go back one step."""
        if self.is_at_start:
            return
        self.current_step -= 1
        self._emit_current_step()

    def cycle_speed(self) -> None:
        """Cycle to the next speed option."""
        try:
            idx = self.SPEED_OPTIONS.index(self.speed)
            self.speed = self.SPEED_OPTIONS[(idx + 1) % len(self.SPEED_OPTIONS)]
        except ValueError:
            self.speed = 1.0

    def _schedule_next(self) -> None:
        """Schedule the next step event."""
        if not self.playing or self.is_at_end:
            return

        # Calculate delay based on speed
        interval = self.BASE_INTERVAL_MS / self.speed
        self._timer = self.set_timer(interval / 1000, self._on_timer)

    def _cancel_timer(self) -> None:
        """Cancel any pending timer."""
        if self._timer:
            self._timer.stop()
            self._timer = None

    def _on_timer(self) -> None:
        """Handle timer callback."""
        if not self.playing:
            return

        self.step_forward()

        if not self.is_at_end:
            self._schedule_next()
        else:
            self.playing = False
            self.post_message(PlaybackComplete(total_steps=self.total_steps))

    def _emit_current_step(self) -> None:
        """Emit a StepEvent for the current step."""
        if not self._steps or self.current_step >= self.total_steps:
            return

        step = self._steps[self.current_step]
        delta = (
            self._step_deltas[self.current_step]
            if self.current_step < len(self._step_deltas)
            else 0
        )

        event = StepEvent(
            step_index=self.current_step,
            total_steps=self.total_steps,
            stage=step.stage,
            role=step.role,
            decision=step.decision,
            reason=step.reason,
            content=step.payload,
            timestamp=step.timestamp,
            delta_ms=delta,
            policy_ids=[p.policy_id for p in step.policies if p.policy_id],
        )
        self.post_message(event)

    def watch_playing(self, playing: bool) -> None:
        """React to playing state changes."""
        if not playing:
            self._cancel_timer()

    def watch_speed(self, speed: float) -> None:
        """React to speed changes."""
        # Reschedule timer with new speed if playing
        if self.playing:
            self._cancel_timer()
            self._schedule_next()

    def watch_current_step(self, step: int) -> None:
        """Update progress when current step changes."""
        if self.total_steps <= 1:
            self.progress = 1.0 if self.total_steps == 1 else 0.0
        else:
            self.progress = step / (self.total_steps - 1)
