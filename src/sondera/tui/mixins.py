"""Shared navigation mixins for TUI App and Screen classes."""

from __future__ import annotations

from sondera.tui.ai.panel import AskPanel


class SectionNavMixin:
    """Tab-cycling between focusable sections and vim j/k navigation.

    Subclasses must override ``_section_cycle()`` to return their ordered
    list of focusable widgets.  Override ``_on_section_change()`` for
    side-effects such as resetting an idle timer.
    """

    def _section_cycle(self) -> list:
        raise NotImplementedError

    def _on_section_change(self) -> None: ...

    def _focus_section(self, section: object) -> None:
        if isinstance(section, AskPanel):
            section.focus_input()
        else:
            section.focus()  # type: ignore[union-attr]

    def _cycle_section(self, direction: int) -> None:
        self._on_section_change()
        sections = self._section_cycle()
        if not sections:
            return
        for i, section in enumerate(sections):
            if section.has_focus or section.has_focus_within:
                self._focus_section(sections[(i + direction) % len(sections)])
                return
        self._focus_section(sections[0] if direction > 0 else sections[-1])

    def action_next_section(self) -> None:
        self._cycle_section(1)

    def action_prev_section(self) -> None:
        self._cycle_section(-1)

    def action_vim_down(self) -> None:
        self.action_cursor_down()  # type: ignore[attr-defined]

    def action_vim_up(self) -> None:
        self.action_cursor_up()  # type: ignore[attr-defined]
