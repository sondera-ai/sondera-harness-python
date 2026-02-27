"""AskPanel widget: always-visible prompt bar powered by LiteLLM."""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from rich.text import Text
from textual import events, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static, TextArea

if TYPE_CHECKING:
    from sondera.tui.app import SonderaApp

import sondera.settings as _settings
from sondera import Decision
from sondera.tui.colors import (
    SPINNER_CHARS,
    THINKING_INTERVAL,
    THINKING_VERBS,
    generate_glow,
)


@dataclass
class ConversationState:
    """Chat history and current exchange state."""

    history: list[tuple[str, str]] = field(default_factory=list)
    current_question: str = ""
    current_response: str = ""
    current_status: str = ""


@dataclass
class StreamState:
    """Streaming and queueing state."""

    is_streaming: bool = False
    stream_id: int = 0
    prompt_queue: list[str] = field(default_factory=list)


@dataclass
class AskSessionState:
    """Shared chat state that persists across screen transitions.

    Stored on the app as ``app._ask_state`` so all AskPanel instances
    (one per screen) read/write the same conversation.
    """

    conversation: ConversationState = field(default_factory=ConversationState)
    stream: StreamState = field(default_factory=StreamState)
    has_session: bool = False
    pending_updates: dict[str, str] = field(default_factory=dict)
    input_history: list[str] = field(default_factory=list)
    focus_pending: bool = False
    response_visible: bool = False


class AskInput(TextArea):
    """Multi-line input with ghost text suggestion support.

    Enter submits, Shift+Enter inserts newline.
    When a suggestion is pending, it appears as muted ghost text with the
    cursor at position 0. Typing clears it and starts fresh, right arrow
    accepts it (cursor jumps to end).
    """

    if TYPE_CHECKING:
        app: SonderaApp

    class Submitted(Message):
        """Fired when the user presses Enter (without Shift)."""

        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    class CancelRequested(Message):
        """Fired when the user presses Escape during streaming."""

    class Focused(Message):
        """Fired when the input gains focus (click or tab)."""

    class Blurred(Message):
        """Fired when the input loses focus."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._pending_suggestion: bool = False
        self._history: list[str] = []
        self._history_index: int = -1
        self._saved_input: str = ""

    def fill_suggestion(self, text: str) -> None:
        """Pre-fill suggestion as ghost (muted) text with cursor at start."""
        self.text = text
        self.cursor_location = (0, 0)
        c = self.app.theme_colors
        self.styles.color = c.fg_muted
        self._pending_suggestion = True

    def _clear_ghost(self) -> None:
        """Reset text color from muted ghost back to normal."""
        self._pending_suggestion = False
        self.styles.color = None  # type: ignore[assignment]

    def _on_key(self, event: events.Key) -> None:  # type: ignore[override]
        """Handle suggestion state, Enter submits, Shift+Enter inserts newline."""
        # Escape: cancel stream > clear ghost > clear text > bubble
        if event.key == "escape":
            state: AskSessionState = self.app._ask_state  # type: ignore[attr-defined]
            if state.stream.is_streaming:
                self.post_message(self.CancelRequested())
                event.prevent_default()
                event.stop()
                return
            if self._pending_suggestion:
                self._clear_ghost()
                self.clear()
                # Don't prevent default: let Escape bubble to screen
                return
            if self.text.strip():
                self.clear()
                event.prevent_default()
                event.stop()
                return
            # Empty + not streaming: let bubble (no-op, screens use backspace)
            return

        # Ghost text interaction: typing replaces, right-arrow accepts.
        if self._pending_suggestion:
            if event.key == "right":
                # Accept: move cursor to end, restore normal color
                self._clear_ghost()
                self.cursor_location = (0, len(self.text))
                event.prevent_default()
                event.stop()
                return
            if event.key in ("up", "down"):
                # Dismiss ghost before history navigation
                self._clear_ghost()
                self.clear()
            else:
                _modifiers = {"shift", "ctrl", "alt", "meta"}
                if event.key not in _modifiers:
                    # Dismiss ghost text: clear and let typed character through
                    self._clear_ghost()
                    self.clear()

        # History navigation: up/down cycle through prior questions
        if event.key == "up" and self._history:
            event.prevent_default()
            event.stop()
            if self._history_index == -1:
                self._saved_input = self.text
            if self._history_index < len(self._history) - 1:
                self._history_index += 1
                self.text = self._history[self._history_index]
                self.cursor_location = (0, len(self.text))
            return
        if event.key == "down":
            event.prevent_default()
            event.stop()
            if self._history_index > 0:
                self._history_index -= 1
                self.text = self._history[self._history_index]
                self.cursor_location = (0, len(self.text))
            elif self._history_index == 0:
                self._history_index = -1
                self.text = self._saved_input
                self.cursor_location = (0, len(self.text))
            return

        if event.key == "enter":
            event.prevent_default()
            event.stop()
            value = self.text.strip()
            if value:
                self.post_message(self.Submitted(value))
                self._history_index = -1
                self._saved_input = ""
            return
        if event.key == "shift+enter":
            event.prevent_default()
            event.stop()
            self.insert("\n")
            return

    async def _on_mouse_down(self, event: events.MouseDown) -> None:
        """Prevent cursor repositioning while ghost text is showing."""
        if self._pending_suggestion:
            event.prevent_default()

    def on_focus(self) -> None:
        """Notify parent panel and disable cursor blink."""
        self.cursor_blink = False
        self.post_message(self.Focused())

    def on_blur(self) -> None:
        """If suggestion was never interacted with, clear it."""
        if self._pending_suggestion:
            self._clear_ghost()
            self.clear()
        self.post_message(self.Blurred())


class AskPanel(Widget):
    """Always-visible bottom prompt for natural language queries.

    Messages scroll up as a conversation history. Use /clear to reset.
    Press backtick (`` ` ``) to toggle the response area open/closed.

    Conversation state is shared across all AskPanel instances via
    ``app._ask_state`` so navigating between screens preserves the session.
    """

    if TYPE_CHECKING:
        app: SonderaApp

    can_focus = False
    can_focus_children = True

    BINDINGS = [
        Binding("ctrl+l", "do_clear", "Reset", key_display="/clear"),
        Binding("tab", "app.next_section", "Section", show=False),
        Binding("shift+tab", "app.prev_section", "Section", show=False),
        # Shadow app-level bindings so they don't clutter footer while typing.
        # TextArea consumes printable chars before these fire, so typing works.
        # (Only priority=True bindings bypass this: those need action guards.)
        Binding("enter", "noop", "Send", show=False),
        Binding("slash", "noop", "Filter", show=False),
        Binding("r", "noop", "Refresh", show=False),
        Binding("q", "noop", "Quit", show=False),
        Binding("a", "noop", "Agent", show=False),
        Binding("j", "noop", "Navigate", show=False),
        Binding("k", "noop", "Navigate", show=False),
    ]

    class Dismissed(Message):
        """Sent when the response area is closed (input stays visible)."""

    class SettingsChanged(Message):
        """Sent after pending setting updates are applied."""

    _DEFAULT_SUGGESTION = "ask about your agents..."

    _CONFIRM_WORDS = frozenset(
        {
            "yes",
            "y",
            "yeah",
            "yep",
            "sure",
            "ok",
            "confirm",
            "do it",
            "go ahead",
            "apply",
            "proceed",
        }
    )
    _CANCEL_WORDS = frozenset(
        {
            "no",
            "n",
            "nah",
            "cancel",
            "nevermind",
            "abort",
        }
    )

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # Thinking animation state (local per-panel, cosmetic)
        self._thinking_frame: int = 0
        self._thinking_verb: str = "Pondering"
        self._thinking_timer: object | None = None
        # Current suggestion text (screen-specific)
        self._suggestion: str = self._DEFAULT_SUGGESTION

    @property
    def _state(self) -> AskSessionState:
        """Shared session state stored on the app."""
        return self.app._ask_state

    def _get_visible_panel(self) -> AskPanel | None:
        """Return the AskPanel on the currently visible screen."""
        try:
            return self.app.screen.query_one("#ask-panel", AskPanel)
        except Exception:
            return None

    def compose(self) -> ComposeResult:
        yield Static(id="ask-status")
        with ScrollableContainer(id="ask-response-container"):
            yield Static(id="ask-response")
        yield Static("\u2500" * 200, id="ask-rule-top", classes="ask-rule")
        with Horizontal(id="ask-prompt-row"):
            yield Static("\u276f ", id="ask-prompt-arrow")
            yield AskInput(
                id="ask-input",
                show_line_numbers=False,
                language=None,
                tab_behavior="focus",
            )
        yield Static("\u2500" * 200, id="ask-rule-bottom", classes="ask-rule")

    def on_mount(self) -> None:
        """Set up panel: non-focusable response area, restore shared state."""
        self.query_one("#ask-response-container").can_focus = False
        # Link input history to shared state
        inp = self.query_one("#ask-input", AskInput)
        inp._history = self._state.input_history
        # Defer state sync so TextArea is fully initialized and styles apply
        self.call_after_refresh(self._initial_sync)
        # Don't generate suggestion immediately: screens call
        # refresh_suggestion() after their data is ready.

    def _initial_sync(self) -> None:
        """Restore state or show ghost suggestion after mount."""
        state = self._state
        if state.has_session or state.conversation.current_question:
            self._sync_from_state(scroll_to_end=True)
        else:
            self._show_ghost_suggestion()
        if state.focus_pending:
            state.focus_pending = False
            self.focus_input()

    def _sync_from_state(self, scroll_to_end: bool = False) -> None:
        """Update this panel's display to match shared session state."""
        state = self._state
        response_widget = self.query_one("#ask-response", Static)
        if state.has_session or state.conversation.current_question:
            # Respect the user's open/closed preference
            if state.response_visible:
                self.add_class("--has-response")
            else:
                self.remove_class("--has-response")
            response_widget.update(self._render_conversation())
            if scroll_to_end or state.stream.is_streaming:
                container = self.query_one(
                    "#ask-response-container", ScrollableContainer
                )
                container.scroll_end(animate=False)
            # Restart thinking animation if stream is still active
            if state.stream.is_streaming and not state.conversation.current_response:
                self._start_thinking_animation()
            elif not state.stream.is_streaming:
                self._stop_thinking_animation()
        else:
            self.remove_class("--has-response")
            response_widget.update("")
            self._show_ghost_suggestion()
        # Ensure input history reference is current
        inp = self.query_one("#ask-input", AskInput)
        inp._history = state.input_history

    def _update_visible_response(self) -> None:
        """Re-render the response display on whichever panel is visible."""
        visible = self._get_visible_panel()
        if visible:
            visible.query_one("#ask-response", Static).update(
                visible._render_conversation()
            )
            visible.query_one(
                "#ask-response-container", ScrollableContainer
            ).scroll_end(animate=False)

    def _show_ghost_suggestion(self) -> None:
        """Fill the TextArea with the suggestion as muted ghost text."""
        inp = self.query_one("#ask-input", AskInput)
        inp.fill_suggestion(self._suggestion)

    @work(exclusive=True, group="ask-suggestion")
    async def refresh_suggestion(self) -> None:
        """Generate a contextual placeholder suggestion via fast model."""
        from textual.worker import get_current_worker

        try:
            from .client import generate_suggestion
            from .context import get_screen_context

            context = get_screen_context(self.app)
            worker = get_current_worker()

            suggestion = await generate_suggestion(
                context=context,
                api_key=_settings.SETTINGS.active_api_key,
                model=_settings.SETTINGS.active_model_fast,
                api_base=_settings.SETTINGS.active_endpoint,
            )
            if worker.is_cancelled:
                return
            if suggestion:
                self._suggestion = suggestion
                # Update ghost text if input isn't actively being used
                inp = self.query_one("#ask-input", AskInput)
                if inp._pending_suggestion or not inp.text.strip():
                    self._show_ghost_suggestion()
        except Exception:
            logging.debug("Suggestion generation failed", exc_info=True)

    def action_noop(self) -> None:
        """No-op: shadow parent bindings while ask input is focused."""

    def action_do_clear(self) -> None:
        """Clear conversation via Ctrl+L (same as typing /clear)."""
        self.query_one("#ask-input", AskInput).clear()
        self.clear_session()

    def on_ask_input_focused(self, _event: AskInput.Focused) -> None:
        """On focus: no auto-expand. Toggle is handled by backtick key."""

    def on_ask_input_blurred(self, _event: AskInput.Blurred) -> None:
        """Re-show ghost suggestion if input is empty and no active session."""
        inp = self.query_one("#ask-input", AskInput)
        if not inp.text.strip() and not self._state.has_session:
            self._show_ghost_suggestion()

    def focus_input(self) -> None:
        """Focus the input."""
        self.query_one("#ask-input", AskInput).focus()

    def toggle_response(self) -> None:
        """Toggle the chat response area open/closed (bound to backtick key).

        If open (streaming or not), collapses and restores focus. Streaming
        continues in the background and the response is visible on re-expand.
        If closed (with session), re-expands and focuses the input.
        If no session, focuses the input to start a new conversation.
        """
        state = self._state
        if state.response_visible and (state.has_session or state.stream.is_streaming):
            # Collapse
            state.response_visible = False
            self.remove_class("--has-response")
            self.post_message(self.Dismissed())
            return
        if state.has_session or state.stream.is_streaming:
            # Re-expand (stream may still be running in the background)
            state.response_visible = True
            self.add_class("--has-response")
            self._update_visible_response()
            self.query_one("#ask-response-container", ScrollableContainer).scroll_end(
                animate=False
            )
            self.focus_input()
            return
        # No session: toggle focus on the input
        try:
            ask_input = self.query_one("#ask-input")
            if ask_input.has_focus:
                self.post_message(self.Dismissed())
                return
        except Exception:
            pass
        self.focus_input()

    def clear_session(self) -> None:
        """Clear all conversation state and collapse."""
        state = self._state
        state.stream.is_streaming = False
        state.stream.prompt_queue.clear()
        self._stop_thinking_animation()
        state.conversation.history.clear()
        state.pending_updates.clear()
        state.conversation.current_question = ""
        state.conversation.current_response = ""
        state.conversation.current_status = ""
        state.has_session = False
        state.response_visible = False
        state.input_history.clear()
        inp = self.query_one("#ask-input", AskInput)
        inp._history_index = -1
        inp._saved_input = ""
        self.remove_class("--has-response")
        self.query_one("#ask-response", Static).update("")
        self.query_one("#ask-status", Static).update("")
        self._suggestion = self._DEFAULT_SUGGESTION
        self._show_ghost_suggestion()
        self.refresh_suggestion()

    def _recolor(self) -> None:
        """Re-render conversation with current theme colors."""
        state = self._state
        if state.has_session or state.conversation.current_question:
            self.query_one("#ask-response", Static).update(self._render_conversation())

    # -- Thinking animation --------------------------------------------------

    def _start_thinking_animation(self) -> None:
        """Start the spinner + glow verb animation."""
        self._stop_thinking_animation()
        self._thinking_frame = 0
        self._thinking_verb = random.choice(THINKING_VERBS)  # noqa: S311
        self._thinking_timer = self.set_interval(THINKING_INTERVAL, self._thinking_tick)

    def _stop_thinking_animation(self) -> None:
        """Stop the thinking animation if running."""
        if self._thinking_timer is not None:
            self._thinking_timer.stop()  # type: ignore[union-attr]
            self._thinking_timer = None

    def _thinking_tick(self) -> None:
        """Advance spinner glow and periodically swap the verb."""
        self._thinking_frame += 1
        if self._thinking_frame % 100 == 0:
            self._thinking_verb = random.choice(THINKING_VERBS)  # noqa: S311
        # Only re-render while still in thinking state (no response text yet)
        state = self._state
        if state.stream.is_streaming and not state.conversation.current_response:
            self.query_one("#ask-response", Static).update(self._render_conversation())

    # -- Properties ------------------------------------------------------------

    @property
    def has_response(self) -> bool:
        """True when the response area is visible."""
        return self.has_class("--has-response")

    def _render_conversation(self) -> Text:
        """Build Rich Text from full conversation history + current exchange."""
        state = self._state
        c = self.app.theme_colors
        # Use active theme's primary so animations adapt to any theme
        theme = self.app.current_theme
        accent = theme.primary or c.primary
        display = Text()

        # Completed exchanges
        for question, response in state.conversation.history:
            display.append("\u276f ", style=f"bold {accent}")
            display.append(question, style=f"bold {c.fg}")
            display.append("\n\n")
            if response:
                if response.startswith("Error:"):
                    display.append(response, style=c.error)
                else:
                    display.append(response, style=c.fg_secondary)
                display.append("\n\n")

        # Current streaming exchange
        if state.conversation.current_question:
            display.append("\u276f ", style=f"bold {accent}")
            display.append(state.conversation.current_question, style=f"bold {c.fg}")
            display.append("\n\n")
            if state.conversation.current_response:
                display.append(
                    state.conversation.current_response, style=c.fg_secondary
                )
            elif state.stream.is_streaming:
                glow = generate_glow(accent, dark=theme.dark)
                # Spinner char at ~240ms cadence (every 4 ticks at 60ms)
                sc = SPINNER_CHARS[(self._thinking_frame // 4) % len(SPINNER_CHARS)]
                display.append(f"  {sc} ", style=f"bold {accent}")
                # Bouncing spotlight: bright peak sweeps left->right->left
                verb_text = f"{self._thinking_verb}..."
                n = len(verb_text)
                glow_max = len(glow) - 1
                # Triangle wave position: 0->n-1->0 (smooth reversal)
                period = max((n - 1) * 2, 1)
                raw = self._thinking_frame % period
                wave_pos = raw if raw < n else (period - raw)
                for i, ch in enumerate(verb_text):
                    dist = abs(i - wave_pos)
                    idx = max(0, glow_max - dist)
                    display.append(ch, style=glow[idx])
            if state.conversation.current_status:
                display.append(
                    f"\n  {state.conversation.current_status}",
                    style=f"italic {c.fg_muted}",
                )

        # Queued prompts (waiting for current stream to finish)
        for queued in state.stream.prompt_queue:
            display.append("\n\n")
            display.append("\u276f ", style=f"bold {accent}")
            display.append(queued, style=f"bold {c.fg}")
            display.append("\n\n")
            display.append("(queued)", style=f"italic {c.fg_dim}")

        return display

    def cancel_stream(self) -> None:
        """Cancel the active AI stream gracefully."""
        state = self._state
        if not state.stream.is_streaming:
            return
        # Save current exchange as cancelled
        cancelled_msg = "(cancelled) what would you like to do instead?"
        if state.conversation.current_response:
            response = state.conversation.current_response + "\n\n" + cancelled_msg
        else:
            response = cancelled_msg
        if state.conversation.current_question:
            state.conversation.history.append(
                (state.conversation.current_question, response)
            )
        state.conversation.current_question = ""
        state.conversation.current_response = ""
        state.conversation.current_status = ""
        state.stream.is_streaming = False
        state.stream.prompt_queue.clear()
        self._stop_thinking_animation()
        self._update_visible_response()

    def on_ask_input_cancel_requested(self, _event: AskInput.CancelRequested) -> None:
        """Handle Escape during streaming from AskInput."""
        self.cancel_stream()

    def on_ask_input_submitted(self, event: AskInput.Submitted) -> None:
        """Handle Enter: send the question to the AI provider."""
        question = event.value.strip()
        if not question:
            return

        # Handle /clear command
        if question == "/clear":
            self.query_one("#ask-input", AskInput).clear()
            self.clear_session()
            return

        state = self._state

        # Intercept confirmation/rejection of pending setting updates
        if state.pending_updates:
            lower = question.lower().strip()
            if lower in self._CONFIRM_WORDS:
                self.query_one("#ask-input", AskInput).clear()
                self._apply_pending_updates()
                return
            if lower in self._CANCEL_WORDS:
                self.query_one("#ask-input", AskInput).clear()
                self._cancel_pending_updates()
                return
            # Anything else: fall through to normal LLM flow

        api_key = _settings.SETTINGS.active_api_key

        # Local providers (ollama, vllm) don't need an API key
        _local = {"ollama", "vllm"}
        if not api_key and _settings.SETTINGS.ai_provider_name not in _local:
            c = self.app.theme_colors
            status = self.query_one("#ask-status", Static)
            self.add_class("--has-response")
            state.has_session = True
            state.response_visible = True
            msg = Text()
            msg.append("No API key. ", style=f"bold {c.warning}")
            msg.append(
                "Set AI_API_KEY in ~/.sondera/env or Configuration",
                style=c.fg_muted,
            )
            status.update(msg)
            return

        # Add to input history (most recent first)
        if not state.input_history or state.input_history[0] != question:
            state.input_history.insert(0, question)

        inp = self.query_one("#ask-input", AskInput)
        inp.clear()

        # If currently streaming, queue the new prompt instead of cancelling
        if state.stream.is_streaming:
            state.stream.prompt_queue.append(question)
            self._update_visible_response()
            return

        self._stream_response(question, api_key)

    def _make_tool_executor(self):
        """Create a tool executor closure capturing the app's live data."""
        from .tools import execute_tool

        app = self.app
        harness = app.harness
        agents = app._agents
        agents_map = app._agents_map
        adjudications = app._adjudications
        pending_updates = self._state.pending_updates

        async def _executor(name: str, args: dict) -> dict:
            return await execute_tool(
                name,
                args,
                harness,
                agents,
                agents_map,
                adjudications,
                pending_updates=pending_updates,
                app=app,
            )

        return _executor

    def _apply_pending_updates(self) -> None:
        """Apply all pending setting updates and show results."""
        from sondera.settings import reload_settings
        from sondera.tui.screens.config import update_env_file

        state = self._state
        lines: list[str] = []
        for key, value in state.pending_updates.items():
            try:
                update_env_file({key: value})
                display = value
                if "KEY" in key or "TOKEN" in key:
                    from .tools import _obfuscate_key

                    display = _obfuscate_key(value)
                lines.append(f"  {key} = {display}")
            except Exception as e:
                lines.append(f"  {key}: failed ({e})")

        reload_settings()
        state.pending_updates.clear()

        text = "Settings applied:\n" + "\n".join(lines)
        state.conversation.history.append(("yes", text))
        state.has_session = True
        state.response_visible = True
        self.add_class("--has-response")
        self.query_one("#ask-response", Static).update(self._render_conversation())
        container = self.query_one("#ask-response-container", ScrollableContainer)
        container.scroll_end(animate=False)
        self.post_message(self.SettingsChanged())

    def _cancel_pending_updates(self) -> None:
        """Cancel pending setting updates."""
        state = self._state
        keys = ", ".join(state.pending_updates.keys())
        state.pending_updates.clear()

        state.conversation.history.append(("no", f"Cancelled changes to: {keys}"))
        state.has_session = True
        state.response_visible = True
        self.add_class("--has-response")
        self.query_one("#ask-response", Static).update(self._render_conversation())
        container = self.query_one("#ask-response-container", ScrollableContainer)
        container.scroll_end(animate=False)

    @work(exclusive=True, group="ask-stream")
    async def _stream_response(self, question: str, api_key: str) -> None:
        """Stream the LLM response with function calling into the panel.

        Writes to shared ``app._ask_state`` so the response is visible
        on whichever screen is currently active (navigation tools may
        push a new screen mid-stream).
        """
        from textual.worker import get_current_worker

        from .client import (
            DoneEvent,
            StatusEvent,
            TextChunk,
            stream_ask_with_tools,
        )
        from .context import get_screen_context
        from .session import AskSession

        worker = get_current_worker()
        state = self._state
        c = self.app.theme_colors

        # Claim a unique stream ID so late-finishing workers don't clobber
        # a newer stream's state.
        state.stream.stream_id += 1
        my_stream_id = state.stream.stream_id

        # Start trajectory recording (no-op if disabled or unconfigured)
        recorder = AskSession()
        await recorder.start()

        # Start new exchange
        state.stream.is_streaming = True
        state.conversation.current_question = question
        state.conversation.current_response = ""
        state.conversation.current_status = ""
        state.has_session = True
        state.response_visible = True

        # Update the visible panel (might be self or a panel on a pushed screen)
        visible = self._get_visible_panel()
        if visible:
            visible.add_class("--has-response")
            visible._start_thinking_animation()
            visible.query_one("#ask-response", Static).update(
                visible._render_conversation()
            )
            visible.query_one("#ask-status", Static).update("")
            visible.query_one(
                "#ask-response-container", ScrollableContainer
            ).scroll_end(animate=False)

        # PRE_MODEL: adjudicate user prompt before sending to LLM
        pre_model = await recorder.adjudicate_user_prompt(question)
        if pre_model and pre_model.decision == Decision.DENY:
            reason = pre_model.reason or "Policy denied this prompt"
            state.conversation.history.append(
                (question, f"Blocked by policy: {reason}")
            )
            state.conversation.current_question = ""
            state.conversation.current_response = ""
            state.stream.is_streaming = False
            self._stop_thinking_animation()
            self._update_visible_response()
            await recorder.finish()
            return

        # Extract context from current screen
        try:
            context = get_screen_context(self.app)
        except Exception:
            context = "(no context available)"

        model = _settings.SETTINGS.active_model_ask

        try:
            executor = self._make_tool_executor()

            # Wrap executor to adjudicate at each tool stage
            async def _recording_executor(name: str, args: dict) -> dict:
                # PRE_TOOL: block execution if denied
                pre = await recorder.adjudicate_tool_request(name, args)
                if pre and pre.decision == Decision.DENY:
                    reason = pre.reason or "Policy denied this tool call"
                    return {"error": f"Blocked by policy: {reason}"}

                result = await executor(name, args)

                # POST_TOOL: redact result if denied
                post = await recorder.adjudicate_tool_response(name, result)
                if post and post.decision == Decision.DENY:
                    reason = post.reason or "Policy redacted tool result"
                    return {"redacted": True, "reason": reason}

                return result

            async for event in stream_ask_with_tools(
                question=question,
                context=context,
                api_key=api_key,
                model=model,
                api_base=_settings.SETTINGS.active_endpoint,
                execute_tool=_recording_executor,
                history=state.conversation.history,
            ):
                if (
                    worker.is_cancelled
                    or not state.stream.is_streaming
                    or state.stream.stream_id != my_stream_id
                ):
                    return

                visible = self._get_visible_panel()

                if isinstance(event, TextChunk):
                    state.conversation.current_response += event.text
                    state.conversation.current_status = ""
                    if visible:
                        visible._stop_thinking_animation()
                        visible.query_one("#ask-response", Static).update(
                            visible._render_conversation()
                        )
                        visible.query_one(
                            "#ask-response-container", ScrollableContainer
                        ).scroll_end(animate=False)
                elif isinstance(event, StatusEvent):
                    state.conversation.current_status = event.message
                    if visible:
                        visible.query_one("#ask-response", Static).update(
                            visible._render_conversation()
                        )
                        visible.query_one(
                            "#ask-response-container", ScrollableContainer
                        ).scroll_end(animate=False)
                elif isinstance(event, DoneEvent):
                    state.conversation.current_status = ""

            # Guard: only finalize if this stream is still the active one
            if state.stream.stream_id != my_stream_id:
                return

            # Done: save completed exchange to history
            response = state.conversation.current_response or "(no response from model)"

            # POST_MODEL: adjudicate model response, redact if denied
            post_model = await recorder.adjudicate_model_response(response)
            if post_model and post_model.decision == Decision.DENY:
                reason = post_model.reason or "Policy filtered this response"
                response = f"[Response redacted by policy: {reason}]"
                state.conversation.current_response = response
                self._update_visible_response()

            state.conversation.history.append(
                (state.conversation.current_question, response)
            )

            state.conversation.current_question = ""
            state.conversation.current_response = ""

            visible = self._get_visible_panel()
            if visible:
                visible.query_one("#ask-status", Static).update("")
        except ImportError as e:
            if state.stream.stream_id == my_stream_id:
                state.conversation.history.append((question, f"Error: {e}"))
                state.conversation.current_question = ""
                state.conversation.current_response = ""
            visible = self._get_visible_panel()
            if visible:
                visible.query_one("#ask-status", Static).update(
                    Text(f"  {e}", style=f"bold {c.warning}")
                )
        except Exception as e:
            err_msg = str(e)[:200]
            if state.stream.stream_id == my_stream_id:
                state.conversation.history.append((question, f"Error: {err_msg}"))
                state.conversation.current_question = ""
                state.conversation.current_response = ""
            visible = self._get_visible_panel()
            if visible:
                visible.query_one("#ask-status", Static).update(
                    Text(f"  Error: {err_msg}", style=f"bold {c.error}")
                )
        finally:
            if state.stream.stream_id == my_stream_id:
                state.stream.is_streaming = False
            self._stop_thinking_animation()
            # Finalize trajectory (no-op if recording was disabled)
            await recorder.finish()
            # Re-render final state on the visible panel
            visible = self._get_visible_panel()
            if visible:
                visible._stop_thinking_animation()
                visible.query_one("#ask-response", Static).update(
                    visible._render_conversation()
                )
            # Drain prompt queue: start next queued prompt if any
            if state.stream.prompt_queue and state.stream.stream_id == my_stream_id:
                next_q = state.stream.prompt_queue.pop(0)
                next_key = _settings.SETTINGS.active_api_key
                if next_key:
                    self._stream_response(next_q, next_key)
