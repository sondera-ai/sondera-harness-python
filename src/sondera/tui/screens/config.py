"""Configuration modal for Sondera platform and AI provider settings."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Rule, Select, Static, Switch

if TYPE_CHECKING:
    from sondera.tui.app import SonderaApp

import sondera.settings as _settings
from sondera.settings import _ENV_PATH, reload_settings


def update_env_file(updates: dict[str, str | None]) -> None:
    """Update specific keys in ~/.sondera/env, preserving other content.

    If a value is None, the key is removed. New keys are appended.
    """
    _ENV_PATH.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    if _ENV_PATH.exists():
        lines = _ENV_PATH.read_text().splitlines()

    updated_keys: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        if "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                updated_keys.add(key)
                if updates[key] is not None:
                    new_lines.append(f"{key}={updates[key]}")
                continue  # Remove if None
        new_lines.append(line)

    for key, value in updates.items():
        if key not in updated_keys and value is not None:
            new_lines.append(f"{key}={value}")

    _ENV_PATH.write_text("\n".join(new_lines) + "\n")


_SCREENSAVER_OPTIONS: list[tuple[str, int]] = [
    ("Never", 0),
    ("30 seconds", 30),
    ("1 minute", 60),
    ("5 minutes", 300),
    ("10 minutes", 600),
    ("30 minutes", 1800),
    ("1 hour", 3600),
    ("3 hours", 10800),
]


def _obfuscate(value: str | None) -> str:
    """Show first 4 + ... + last 4 chars of a key."""
    if not value:
        return "not set"
    if len(value) <= 12:
        return "\u2022" * len(value)
    return f"{value[:4]}...{value[-4:]}"


class KeyDisplay(Static):
    """Clickable obfuscated key display. Click or Enter to edit."""

    if TYPE_CHECKING:
        app: SonderaApp

    can_focus = True

    class EditRequested(Message):
        def __init__(self, field_id: str) -> None:
            super().__init__()
            self.field_id = field_id

    def __init__(self, value: str | None, field_id: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._raw_value = value
        self._field_id = field_id

    def render(self) -> Text:
        c = self.app.theme_colors
        t = Text()
        obfuscated = _obfuscate(self._raw_value)
        if self._raw_value:
            t.append(obfuscated, style=c.fg)
        else:
            t.append(obfuscated, style=f"italic {c.fg_dim}")
        t.append("  edit", style=c.fg_dim)
        return t

    def update_value(self, value: str | None) -> None:
        self._raw_value = value
        self.refresh()

    def on_click(self) -> None:
        self.post_message(self.EditRequested(self._field_id))

    def _on_key(self, event: events.Key) -> None:  # type: ignore[override]
        if event.key == "enter":
            event.prevent_default()
            self.post_message(self.EditRequested(self._field_id))


class ConfigModal(ModalScreen[bool]):
    """Configuration modal for Sondera platform and AI provider settings."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    ConfigModal {
        align: center middle;
    }

    #config-dialog {
        width: 62;
        height: auto;
        max-height: 48;
        background: $surface;
        border: round $primary;
        border-title-color: $primary;
        border-title-style: bold;
        padding: 1 2;
    }

    .cfg-section {
        height: 1;
        color: $primary;
        text-style: bold;
        margin: 0;
    }

    .cfg-separator {
        margin: 1 0 0 0;
        color: $primary 40%;
    }

    .cfg-hint {
        height: 1;
        color: $text-muted;
        margin: 0 0 0 0;
    }

    /* All rows are fixed height 3 to match Input default */
    .cfg-row {
        height: 3;
        align: left middle;
    }

    .cfg-label {
        width: 14;
        height: 3;
        padding: 1 0;
        color: $text;
    }

    .cfg-input {
        width: 1fr;
        border: tall $panel;
    }

    .cfg-input:focus {
        border: tall $primary;
    }

    KeyDisplay {
        width: 1fr;
        height: 3;
        padding: 1 2;
    }

    KeyDisplay:focus {
        text-style: bold underline;
        color: $primary;
    }

    /* Key edit input: hidden until --editing is toggled */
    .cfg-key-edit {
        width: 1fr;
        display: none;
        border: tall $panel;
    }

    .cfg-key-edit:focus {
        border: tall $primary;
    }

    .cfg-row.--editing KeyDisplay {
        display: none;
    }

    .cfg-row.--editing .cfg-key-edit {
        display: block;
    }

    .cfg-switch-row {
        height: 1;
        align: left middle;
        margin: 1 0 0 0;
    }

    .cfg-switch-label {
        width: 14;
        height: 1;
        color: $text;
    }

    #cfg-ai-record {
        width: auto;
        height: 1;
        border: none;
        padding: 0;
    }

    #cfg-ai-record:focus {
        tint: $primary 40%;
    }

    .cfg-switch-hint {
        width: 1fr;
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }

    .cfg-select {
        width: 1fr;
    }

    #config-buttons {
        height: 3;
        align: center middle;
        margin: 1 0 0 0;
    }

    #config-buttons Button {
        min-width: 12;
        margin: 0 1;
    }

    #btn-save {
        background: $primary;
        color: $background;
    }

    #btn-save:hover {
        background: $primary-lighten-1;
    }

    #btn-save:focus {
        background: $primary;
        color: $background;
        text-style: bold;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._new_token: str = ""
        self._new_ai_key: str = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="config-dialog") as dialog:
            dialog.border_title = "Configuration"

            # -- Sondera Platform --
            yield Static("SONDERA PLATFORM", classes="cfg-section")

            with Horizontal(id="token-row", classes="cfg-row"):
                yield Static("Token", classes="cfg-label")
                yield KeyDisplay(
                    _settings.SETTINGS.sondera_api_token, "token", id="token-display"
                )
                yield Input(
                    placeholder="paste new token",
                    password=True,
                    id="token-edit",
                    classes="cfg-key-edit",
                )

            with Horizontal(classes="cfg-row"):
                yield Static("Endpoint", classes="cfg-label")
                yield Input(
                    value=_settings.SETTINGS.sondera_harness_endpoint,
                    id="cfg-endpoint",
                    classes="cfg-input",
                )

            # -- AI Assist --
            yield Rule(classes="cfg-separator")
            yield Static("AI ASSIST", classes="cfg-section")
            yield Static(
                "openai/, anthropic/, gemini/, ollama/, vllm/",
                classes="cfg-hint",
            )

            with Horizontal(classes="cfg-row"):
                yield Static("Model", classes="cfg-label")
                yield Input(
                    value=_settings.SETTINGS.ai_model,
                    placeholder="e.g. openai/gpt-4o",
                    id="cfg-model",
                    classes="cfg-input",
                )

            with Horizontal(classes="cfg-row"):
                yield Static("Fast", classes="cfg-label")
                yield Input(
                    value=_settings.SETTINGS.ai_model_fast,
                    placeholder="e.g. openai/gpt-4o-mini",
                    id="cfg-model-fast",
                    classes="cfg-input",
                )

            with Horizontal(id="ai-key-row", classes="cfg-row"):
                yield Static("API Key", classes="cfg-label")
                yield KeyDisplay(
                    _settings.SETTINGS.active_api_key,
                    "ai-key",
                    id="ai-key-display",
                )
                yield Input(
                    placeholder="paste new API key",
                    password=True,
                    id="ai-key-edit",
                    classes="cfg-key-edit",
                )

            with Horizontal(classes="cfg-switch-row"):
                yield Static("Harness", classes="cfg-switch-label")
                yield Switch(
                    value=_settings.SETTINGS.ai_harness_enabled,
                    id="cfg-ai-record",
                )
                yield Static(
                    "Use the harness on Sondera AI Assistant",
                    classes="cfg-switch-hint",
                )

            # -- Display --
            yield Rule(classes="cfg-separator")
            yield Static("DISPLAY", classes="cfg-section")

            with Horizontal(classes="cfg-row"):
                yield Static("Screensaver", classes="cfg-label")
                current = _settings.SETTINGS.screensaver_timeout
                yield Select(
                    options=_SCREENSAVER_OPTIONS,
                    value=current,
                    id="cfg-screensaver",
                    classes="cfg-select",
                )

            yield Rule(classes="cfg-separator")
            with Horizontal(id="config-buttons"):
                yield Button("Save", id="btn-save", variant="primary")
                yield Button("Cancel", id="btn-cancel")

    # -- Key field editing ----------------------------------------------------

    def on_key_display_edit_requested(self, event: KeyDisplay.EditRequested) -> None:
        if event.field_id == "token":
            row = self.query_one("#token-row")
            edit_input = self.query_one("#token-edit", Input)
        elif event.field_id == "ai-key":
            row = self.query_one("#ai-key-row")
            edit_input = self.query_one("#ai-key-edit", Input)
        else:
            return
        row.add_class("--editing")
        edit_input.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "token-edit":
            self._new_token = event.value.strip()
            self.query_one("#token-row").remove_class("--editing")
            if self._new_token:
                self.query_one("#token-display", KeyDisplay).update_value(
                    self._new_token
                )
        elif event.input.id == "ai-key-edit":
            self._new_ai_key = event.value.strip()
            self.query_one("#ai-key-row").remove_class("--editing")
            if self._new_ai_key:
                self.query_one("#ai-key-display", KeyDisplay).update_value(
                    self._new_ai_key
                )

    # -- Buttons --------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save":
            self._save()
        elif event.button.id == "btn-cancel":
            self.dismiss(False)

    def _save(self) -> None:
        """Gather values, write env file, reload settings."""
        endpoint = self.query_one("#cfg-endpoint", Input).value.strip()
        model = self.query_one("#cfg-model", Input).value.strip()
        model_fast = self.query_one("#cfg-model-fast", Input).value.strip()

        # Grab key-edit inputs directly (user may not have pressed Enter)
        token = self._new_token or self.query_one("#token-edit", Input).value.strip()
        ai_key = self._new_ai_key or self.query_one("#ai-key-edit", Input).value.strip()

        ai_record = self.query_one("#cfg-ai-record", Switch).value
        screensaver = self.query_one("#cfg-screensaver", Select).value

        updates: dict[str, str | None] = {}

        # Always write current values so the env file stays in sync
        updates["AI_HARNESS_ENABLED"] = "true" if ai_record else "false"
        if screensaver is not Select.BLANK:
            updates["SCREENSAVER_TIMEOUT"] = str(screensaver)
        if endpoint:
            updates["SONDERA_HARNESS_ENDPOINT"] = endpoint
        if token:
            updates["SONDERA_API_TOKEN"] = token
        if model:
            updates["AI_MODEL"] = model
        if model_fast:
            updates["AI_MODEL_FAST"] = model_fast
        if ai_key:
            updates["AI_API_KEY"] = ai_key

        if not updates:
            self.dismiss(False)
            return

        try:
            update_env_file(updates)
            reload_settings()
        except Exception as e:
            self.app.notify(f"Save failed: {e}", severity="error", timeout=5)
            return

        self.dismiss(True)

    def action_cancel(self) -> None:
        # Exit key editing if active, otherwise close
        for row_id in ("#token-row", "#ai-key-row"):
            row = self.query_one(row_id)
            if row.has_class("--editing"):
                row.remove_class("--editing")
                return
        self.dismiss(False)
