from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Footer, Header, ListItem, ListView, Markdown, Pretty, Tree

from sondera.types import AdjudicatedTrajectory


class TrajectoryScreen(Screen):
    """A screen for displaying a trajectory."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back to Dashboard"),
        Binding("tab", "focus_next", "Next Widget", show=False),
        Binding("shift+tab", "focus_previous", "Previous Widget", show=False),
        Binding("j", "cursor_down", "Move Down", show=False),
        Binding("k", "cursor_up", "Move Up", show=False),
        Binding("h", "cursor_left", "Move Left", show=False),
        Binding("l", "cursor_right", "Move Right", show=False),
    ]

    def __init__(self, trajectory: AdjudicatedTrajectory):
        super().__init__()
        self.trajectory = trajectory

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="sidebar"):
            tree = Tree(f"Trajectory {self.trajectory.id}", id="trajectory-tree")
            tree.root.expand()
            for i, step in enumerate(self.trajectory.steps):
                if step.step.role.value == "model":
                    name = "🤖"
                elif step.step.role.value == "tool":
                    tool_id = step.step.content.tool_id
                    name = f"🛠 [bold]({tool_id})[/bold]"
                elif step.step.role.value == "user":
                    name = "👤"
                elif step.step.role.value == "system":
                    name = "💻"
                else:
                    name = "UNKNOWN"
                tree.root.add(f"[{i}] {name}")
            yield tree
        with ListView(id="trajectory-list"):
            for i, step in enumerate(self.trajectory.steps):
                with ListItem():
                    if step.step.content.content_type == "prompt":
                        row = Markdown(step.step.content.text, classes="step")
                    else:
                        row = Pretty(step.step.content, classes="step")
                    title = f"Stage:{step.step.stage.value} | Decision:{step.adjudication.decision.value}"
                    if step.step.role.value == "model":
                        title = "🤖 [bold]MODEL[/bold] | " + title
                    elif step.step.role.value == "tool":
                        title = "🛠 [bold]TOOL[/bold] | " + title
                    elif step.step.role.value == "user":
                        title = "👤 [bold]USER[/bold] | " + title
                    elif step.step.role.value == "system":
                        title = "💻 [bold]SYSTEM[/bold] | " + title
                    row.border_title = f"[{i}] {title}"
                    row.border_subtitle = step.step.created_at.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    yield row
        yield Footer()

    def on_mount(self) -> None:
        """Ensure widgets can receive focus."""
        tree = self.query_one("#trajectory-tree", Tree)
        list_view = self.query_one("#trajectory-list", ListView)
        tree.can_focus = True
        list_view.can_focus = True
        # Focus the list view by default
        list_view.focus()

    def _get_focusable_widgets(self) -> list[Tree | ListView]:
        """Get list of focusable widgets in order."""
        return [
            self.query_one("#trajectory-tree", Tree),
            self.query_one("#trajectory-list", ListView),
        ]

    def _find_current_index(
        self, widgets: list[Tree | ListView], focused: Widget | None
    ) -> int | None:
        """Find index of currently focused widget."""
        if not focused:
            return None

        for i, widget in enumerate(widgets):
            if widget == focused:
                return i
            # Check parent chain
            parent = focused.parent
            while parent:
                if parent == widget:
                    return i
                parent = parent.parent
        return None

    def action_focus_next(self) -> None:
        """Move focus to next focusable widget."""
        widgets = self._get_focusable_widgets()
        if not widgets:
            return

        current_index = self._find_current_index(widgets, self.focused)
        next_index = (
            (current_index + 1) % len(widgets) if current_index is not None else 0
        )
        widgets[next_index].focus()

    def action_focus_previous(self) -> None:
        """Move focus to previous focusable widget."""
        widgets = self._get_focusable_widgets()
        if not widgets:
            return

        current_index = self._find_current_index(widgets, self.focused)
        prev_index = (
            (current_index - 1) % len(widgets)
            if current_index is not None
            else len(widgets) - 1
        )
        widgets[prev_index].focus()

    def action_cursor_left(self) -> None:
        """Move cursor left or go to parent node."""
        focused = self.focused
        if isinstance(focused, Tree):
            focused.action_cursor_parent()
        elif isinstance(focused, ListView):
            # ListView doesn't have left/right, so do nothing
            pass

    def action_cursor_right(self) -> None:
        """Move cursor right or go to next sibling."""
        focused = self.focused
        if isinstance(focused, Tree):
            focused.action_cursor_next_sibling()
        elif isinstance(focused, ListView):
            # ListView doesn't have left/right, so do nothing
            pass

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        focused = self.focused
        if isinstance(focused, (Tree, ListView)):
            focused.action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        focused = self.focused
        if isinstance(focused, (Tree, ListView)):
            focused.action_cursor_down()
