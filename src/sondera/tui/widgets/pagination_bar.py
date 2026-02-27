from __future__ import annotations

import contextlib

from rich.text import Text
from textual.app import ComposeResult
from textual.events import Click
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from sondera.tui.colors import get_theme_colors


class PaginationBar(Widget):
    """A flat pagination bar showing range (1-20 of N) with clickable prev/next."""

    can_focus = True

    DEFAULT_CSS = """
    PaginationBar {
        height: 3;
        padding: 1 1 0 1;
        layout: horizontal;
    }
    PaginationBar #page-prev {
        width: auto;
    }
    PaginationBar #page-info {
        width: auto;
        margin: 0 1;
    }
    PaginationBar #page-next {
        width: auto;
    }
    """

    class PageRequested(Message):
        """Emitted when the user requests a different page."""

        def __init__(self, page_token: str) -> None:
            super().__init__()
            self.page_token = page_token

    current_page: reactive[int] = reactive(1)
    has_next: reactive[bool] = reactive(False)
    has_prev: reactive[bool] = reactive(False)

    def __init__(
        self, page_size: int = 20, item_label: str = "trajectories", **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self._next_token: str = ""
        self._prev_tokens: list[str] = [""]
        self._total_pages: int | None = None
        self._page_size: int = page_size
        self._item_label: str = item_label
        self._last_page_count: int = 0  # items on the last page (for total calc)
        self._total_items_override: int | None = (
            None  # set externally (e.g. analytics API)
        )

    def compose(self) -> ComposeResult:
        yield Static(id="page-prev")
        yield Static(id="page-info")
        yield Static(id="page-next")

    def on_mount(self) -> None:
        self._refresh_display()

    def _range_label(self) -> Text:
        """Build the range label like '1-20 of 60 trajectories'."""
        c = get_theme_colors(self.app)
        text = Text()
        start = (self.current_page - 1) * self._page_size + 1
        end = start + self._page_size - 1

        known_total = self._total_items_override
        if known_total is None and self._total_pages is not None:
            known_total = (
                self._total_pages - 1
            ) * self._page_size + self._last_page_count

        if known_total is not None:
            end = min(end, known_total)
            text.append(f"{start}-{end}", style=c.fg)
            text.append(f" of {known_total} {self._item_label}", style=c.fg_secondary)
        elif self.has_next:
            text.append(f"{start}-{end}", style=c.fg)
            text.append(f" {self._item_label}", style=c.fg_secondary)
        else:
            # Last page, items might be fewer
            end = start + self._last_page_count - 1 if self._last_page_count else end
            total = end
            text.append(f"{start}-{end}", style=c.fg)
            text.append(f" of {total} {self._item_label}", style=c.fg_secondary)

        return text

    @property
    def total_items(self) -> int | None:
        """Return total item count if known, else None."""
        if self._total_items_override is not None:
            return self._total_items_override
        if self._total_pages is not None:
            return (self._total_pages - 1) * self._page_size + self._last_page_count
        return None

    def set_total_items(self, total: int) -> None:
        """Set total item count from an external source (e.g. analytics API)."""
        self._total_items_override = total
        self._refresh_display()

    def _refresh_display(self) -> None:
        """Rebuild the pagination display."""
        with contextlib.suppress(Exception):
            c = get_theme_colors(self.app)
            prev_style = f"bold {c.primary}" if self.has_prev else c.border
            self.query_one("#page-prev", Static).update(
                Text("\u25c0 prev", style=prev_style)
            )
            self.query_one("#page-info", Static).update(self._range_label())
            next_style = f"bold {c.primary}" if self.has_next else c.border
            self.query_one("#page-next", Static).update(
                Text("next \u25b6", style=next_style)
            )

    def watch_current_page(self, page: int) -> None:
        self._refresh_display()

    def watch_has_next(self, val: bool) -> None:
        self._refresh_display()

    def watch_has_prev(self, val: bool) -> None:
        self._refresh_display()

    def on_click(self, event: Click) -> None:
        """Handle click on prev/next widgets."""
        with contextlib.suppress(Exception):
            prev_widget = self.query_one("#page-prev", Static)
            next_widget = self.query_one("#page-next", Static)
            target = event.widget
            if target is prev_widget and self.has_prev:
                self._go_prev()
                event.stop()
            elif target is next_widget and self.has_next:
                self._go_next()
                event.stop()

    def update_state(self, next_token: str, page_count: int = 0) -> None:
        """Update pagination state with the API's next_page_token.

        Args:
            next_token: The next page token from the API.
            page_count: Number of items returned on this page.
        """
        self._next_token = next_token
        self._last_page_count = page_count or self._page_size
        self.has_next = bool(next_token)
        self.has_prev = self.current_page > 1
        if not next_token:
            self._total_pages = self.current_page
        self._refresh_display()

    def _go_next(self) -> None:
        if self._next_token:
            self._prev_tokens.append(self._next_token)
            self.current_page += 1
            self.post_message(self.PageRequested(page_token=self._next_token))

    def _go_prev(self) -> None:
        if self.current_page > 1:
            if self._prev_tokens:
                self._prev_tokens.pop()
            prev_token = self._prev_tokens[-1] if self._prev_tokens else ""
            self.current_page -= 1
            self.post_message(self.PageRequested(page_token=prev_token))

    def set_client_page(self, page: int, total_pages: int) -> None:
        """Set pagination state for client-side (in-memory) pagination."""
        self.current_page = page
        self._total_pages = total_pages
        self.has_prev = page > 1
        self.has_next = page < total_pages
        self._next_token = str(page + 1) if page < total_pages else ""
        self._prev_tokens = [str(i) for i in range(1, page + 1)]
        self._refresh_display()

    def reset(self) -> None:
        """Reset to page 1."""
        self.current_page = 1
        self._prev_tokens = [""]
        self._next_token = ""
        self._total_pages = None
        self._total_items_override = None
        self._last_page_count = 0
        self.has_next = False
        self.has_prev = False
