"""Flying agent cards screensaver.

Agent cards with animated wings fly across a starfield. Wing color
conveys agent health: green = OK, red = denied, amber = escalated.
Speed indicates severity: OK agents fly fastest, escalated agents
linger so you can spot them.

Press ``s`` for legend, ``i`` for inspect mode, any other key to exit.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime

from rich.console import Group
from rich.style import Style
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Static

from sondera.tui.widgets.agents_feed import AgentStatus

# ═══════════════════════════════════════════════════════════════════════════
# Type aliases
# ═══════════════════════════════════════════════════════════════════════════

RGB = tuple[int, int, int]
Cell = tuple[str, Style | None]
Grid = list[list[Cell]]

# ═══════════════════════════════════════════════════════════════════════════
# Animation constants
# ═══════════════════════════════════════════════════════════════════════════

_FPS = 50
_MOVE_S = 1.0 / _FPS  # 20 ms per movement tick
_FLAP_S = 0.10  # seconds between wing-frame advance checks

# Speed tiers (cols/tick): OK fastest, denied medium, escalated slowest.
# Within each tier, individual cards vary slightly for organic feel.
_SPEED_OK = (-0.28, -0.24)  # ~12-14 cols/sec → 9-10s crossing
_SPEED_DENY = (-0.20, -0.17)  # ~8.5-10 cols/sec → 12-14s crossing
_SPEED_ESC = (-0.14, -0.11)  # ~5.5-7 cols/sec → 17-22s crossing
_DY_RATIO = 0.18  # dy = |dx| * ratio (visible diagonal descent)

# Star depth layers: background (dim), midground (standard), foreground (bright)
# Stars are stationary; depth is conveyed through brightness and twinkle speed.
_PARALLAX: dict[int, dict] = {
    0: {"bri": (1, 7), "density": 0.5, "chars": ["·"], "twinkle": 0.03},
    1: {"bri": (3, 13), "density": 1.0, "chars": None, "twinkle": 0.065},
    2: {"bri": (8, 15), "density": 0.3, "chars": ["•", "∙", "·"], "twinkle": 0.12},
}
_TWINKLE_SPEED = {0: 0.03, 1: 0.065, 2: 0.12}

# Card flip animation (triggered on new denial via live sync)
_FLIP_DURATION = 35  # total ticks (~0.7s at 50 FPS)
_FLIP_SQUISH = 14  # ticks: edges → center
_FLIP_FLASH = 7  # ticks: thin line + red flash
_FLIP_RED = Style(color="#ff3333", bgcolor="#4a0000", bold=True)

# ═══════════════════════════════════════════════════════════════════════════
# Sprite geometry
# ═══════════════════════════════════════════════════════════════════════════

_WING_W = 8
_GAP = 1
_CARD_INNER_W = 18
_CARD_W = _CARD_INNER_W + 2  # + │ each side
_CARD_H = 4  # ╭ name stats ╰
_EDGE_R = 2  # right-edge columns (3D depth)
_EDGE_B = 1  # bottom-edge row
_SPRITE_W = _WING_W + _GAP + _CARD_W + _EDGE_R + _GAP + _WING_W  # 40
_SPRITE_H = _CARD_H + _EDGE_B + 6  # card + edge + wing extent + shadow

_BLACK: Cell = (" ", None)

# ═══════════════════════════════════════════════════════════════════════════
# Stars: 16 brightness levels, cool (blue-grey) and warm (amber) tints
# ═══════════════════════════════════════════════════════════════════════════

_STAR_CHARS = ["·"] * 5 + ["."] * 3 + ["∗", "✦"]

_STAR_COOL: list[Style] = [
    Style(color=f"#{int(5 + i * 5):02x}{int(5 + i * 5):02x}{int(7 + i * 5.5):02x}")
    for i in range(16)
]
_STAR_WARM: list[Style] = [
    Style(color=f"#{int(7 + i * 5.5):02x}{int(5 + i * 4):02x}{int(3 + i * 2.8):02x}")
    for i in range(16)
]

# ═══════════════════════════════════════════════════════════════════════════
# Wing sprites (8 chars wide, 5 brightness levels for metallic feather look)
# ═══════════════════════════════════════════════════════════════════════════
#
# Brightness: 0=transparent, 1=deep shadow, 2=shadow, 3=mid, 4=bright.
# Wings sweep outward from card body. Diagonal brightness = metallic sheen.
# Left wing tip is at top-left (UP) or bottom-left (DOWN).
# Cycle: UP → LEVEL → DOWN → LEVEL.

_FRAME_UP = {
    "left_chars": ["█▄      ", "███▄    ", "█████▄  ", "██████▄ ", "████████"],
    "right_chars": ["      ▄█", "    ▄███", "  ▄█████", " ▄██████", "████████"],
    "left_brightness": [
        [4, 4, 0, 0, 0, 0, 0, 0],
        [3, 3, 3, 4, 0, 0, 0, 0],
        [2, 2, 3, 3, 3, 4, 0, 0],
        [1, 1, 2, 2, 3, 3, 4, 0],
        [1, 1, 1, 2, 2, 2, 3, 3],
    ],
    "right_brightness": [
        [0, 0, 0, 0, 0, 0, 4, 4],
        [0, 0, 0, 0, 4, 3, 3, 3],
        [0, 0, 4, 3, 3, 3, 2, 2],
        [0, 4, 3, 3, 2, 2, 1, 1],
        [3, 3, 2, 2, 2, 1, 1, 1],
    ],
    "y_offset": -3,
}
_FRAME_LEVEL = {
    "left_chars": ["████████", "████████", "  ▀▀▀▀▀▀"],
    "right_chars": ["████████", "████████", "▀▀▀▀▀▀  "],
    "left_brightness": [
        [4, 3, 3, 2, 2, 2, 1, 1],
        [3, 2, 2, 2, 1, 1, 1, 1],
        [0, 0, 2, 2, 1, 1, 1, 1],
    ],
    "right_brightness": [
        [1, 1, 2, 2, 2, 3, 3, 4],
        [1, 1, 1, 1, 2, 2, 2, 3],
        [1, 1, 1, 1, 2, 2, 0, 0],
    ],
    "y_offset": 1,
}
_FRAME_DOWN = {
    "left_chars": ["████████", "██████▀ ", "████▀   ", "██▀     ", "▀       "],
    "right_chars": ["████████", " ▀██████", "   ▀████", "     ▀██", "       ▀"],
    "left_brightness": [
        [1, 1, 1, 2, 2, 2, 3, 3],
        [1, 1, 2, 2, 3, 3, 4, 0],
        [2, 2, 3, 3, 4, 0, 0, 0],
        [3, 3, 4, 0, 0, 0, 0, 0],
        [4, 0, 0, 0, 0, 0, 0, 0],
    ],
    "right_brightness": [
        [3, 3, 2, 2, 2, 1, 1, 1],
        [0, 4, 3, 3, 2, 2, 1, 1],
        [0, 0, 0, 4, 3, 3, 2, 2],
        [0, 0, 0, 0, 0, 4, 3, 3],
        [0, 0, 0, 0, 0, 0, 0, 4],
    ],
    "y_offset": 0,
}
_FRAMES = [_FRAME_UP, _FRAME_LEVEL, _FRAME_DOWN, _FRAME_LEVEL]

# ═══════════════════════════════════════════════════════════════════════════
# Wing color ramps: [skip, deep-shadow, shadow, mid, bright/specular]
# ═══════════════════════════════════════════════════════════════════════════

_GREEN_RAMP: list[RGB] = [
    (0, 0, 0),
    (18, 40, 30),
    (56, 110, 85),
    (100, 180, 145),
    (160, 240, 200),
]
_RED_RAMP: list[RGB] = [
    (0, 0, 0),
    (40, 14, 14),
    (100, 40, 42),
    (160, 72, 80),
    (210, 120, 130),
]
_AMBER_RAMP: list[RGB] = [
    (0, 0, 0),
    (40, 35, 12),
    (100, 85, 35),
    (170, 145, 80),
    (240, 210, 145),
]


def _hex(r: int, g: int, b: int) -> str:
    return (
        f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"
    )


def _wing_styles(status: str) -> list[Style | None]:
    """[skip, deep-shadow, shadow, mid, bright] styles for wing characters."""
    ramp = (
        _GREEN_RAMP
        if status == "clean"
        else _RED_RAMP
        if status == "deny"
        else _AMBER_RAMP
    )
    return [
        None,
        Style(color=_hex(*ramp[1])),
        Style(color=_hex(*ramp[2])),
        Style(color=_hex(*ramp[3])),
        Style(color=_hex(*ramp[4]), bold=True),
    ]


# ═══════════════════════════════════════════════════════════════════════════
# Card body styles: 3D-lit solid panel with per-card heat map
# ═══════════════════════════════════════════════════════════════════════════

_FILL = "#101c16"  # dark green card-face background (heat = 0)
_FILL_HI = "#142018"  # slightly lighter for top-lit rows (heat = 0)
_SHADOW_S = Style(color="#080808")  # drop shadow (░)

# Heat map: 21-level quantized cache (0-20) of per-card body/edge styles.
# heat 0.0 = cool green (clean agent), 1.0 = hot red (heavy denials).
_HEAT_CACHE: dict[int, dict[str, Style]] = {}


def _card_body_styles(heat: float) -> dict[str, Style]:
    """Return card body + edge styles tinted by heat (0.0=green, 1.0=red)."""
    level = min(20, int(heat * 20))
    cached = _HEAT_CACHE.get(level)
    if cached is not None:
        return cached

    t = level / 20.0
    # Interpolate fill from dark green to dark red
    fr, fg, fb = int(16 + t * 40), int(28 - t * 16), int(22 - t * 14)
    fill = _hex(fr, fg, fb)
    fhr, fhg, fhb = int(20 + t * 44), int(32 - t * 18), int(24 - t * 16)
    fill_hi = _hex(fhr, fhg, fhb)
    # Edge colors shift from green to red tint
    er, eg, eb = int(42 + t * 30), int(80 - t * 50), int(64 - t * 40)

    styles: dict[str, Style] = {
        "fill": Style(bgcolor=fill),
        "fill_hi": Style(bgcolor=fill_hi),
        "top_bdr": Style(color="#999999", bgcolor=fill_hi),
        "hi_bdr": Style(color="#707070", bgcolor=fill),
        "lo_bdr": Style(color="#2a2a2a", bgcolor=fill),
        "corner_tl": Style(color="#808080", bgcolor=fill_hi),
        "corner_tr": Style(color="#606060", bgcolor=fill_hi),
        "corner_bl": Style(color="#404040", bgcolor=fill),
        "corner_br": Style(color="#252525", bgcolor=fill),
        "name": Style(color="#f0f0f0", bgcolor=fill_hi, bold=True),
        "stat": Style(color="#aaaaaa", bgcolor=fill),
        "deny": Style(color="#bf616a", bgcolor=fill, bold=True),
        "esc": Style(color="#ebcb8b", bgcolor=fill, bold=True),
        "edge_r1": Style(color=_hex(er, eg, eb)),
        "edge_r2": Style(color=_hex(er // 2, eg // 2, eb // 2)),
        "edge_b": Style(color=_hex(int(er * 0.65), int(eg * 0.65), int(eb * 0.65))),
        "edge_br": Style(color=_hex(er // 3, eg // 3, eb // 3)),
    }
    _HEAT_CACHE[level] = styles
    return styles


# ═══════════════════════════════════════════════════════════════════════════
# Data
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class FlyingCard:
    agent_id: str  # stable key for live data sync
    name: str
    trajectories: int
    denials: int
    escalations: int
    x: float = 0.0
    y: float = 0.0
    dx: float = -0.25
    dy: float = 0.005
    phase: int = 0  # 0-3 wing frame index
    flap_period: int = 4  # ticks per wing-frame advance (async per card)
    flap_counter: int = 0
    flip_timer: int = 0  # ticks remaining in flip animation (0 = idle)
    flip_total: int = 0  # total ticks when flip started
    last_active: datetime | None = field(default=None, repr=False)

    @property
    def status(self) -> str:
        if self.denials > 0:
            return "deny"
        if self.escalations > 0:
            return "escalate"
        return "clean"

    @property
    def heat(self) -> float:
        """0.0 = clean, 1.0 = fully hot. Based on denial ratio."""
        if self.trajectories <= 0:
            return 1.0 if self.denials > 0 else 0.0
        return min(1.0, (self.denials / self.trajectories) * 3.0)


@dataclass
class Star:
    x: int
    y: int
    char: str
    warm: bool  # warm vs cool tint
    base_bri: int  # resting brightness (0-15)
    phase: float  # twinkle phase offset
    layer: int = 1  # 0=background, 1=midground, 2=foreground


@dataclass
class Meteor:
    """Shooting star that streaks across the sky."""

    x: float
    y: float
    dx: float  # horizontal speed (negative = moving left)
    dy: float  # vertical speed (positive = moving down)
    length: int  # trail length in characters
    life: int  # remaining ticks before removal
    bright: bool  # True = bright white streak, False = dimmer


# Meteor visual styles
_METEOR_HEAD = Style(color="#ffffff", bold=True)
_METEOR_BODY = Style(color="#aabbcc")
_METEOR_TAIL = Style(color="#445566")
_METEOR_DIM_HEAD = Style(color="#99aabb")
_METEOR_DIM_BODY = Style(color="#667788")
_METEOR_DIM_TAIL = Style(color="#334455")

# Inspect mode overlay styles
_INSPECT_BG = Style(color="#EAEAEA", bgcolor="#1a1a2a")
_INSPECT_DIM = Style(color="#888888", bgcolor="#1a1a2a")
_INSPECT_HIGHLIGHT = Style(color="#ff4444", bold=True)


# ═══════════════════════════════════════════════════════════════════════════
# Build cards from agent data
# ═══════════════════════════════════════════════════════════════════════════

_DEMO_AGENTS = [
    ("Weather Agent", 24, 0, 0),
    ("Trading Bot", 156, 12, 3),
    ("Code Assistant", 89, 0, 2),
    ("Payment Processor", 45, 8, 0),
    ("Security Scanner", 312, 0, 0),
    ("Data Pipeline", 67, 1, 0),
    ("Life Science Bot", 4, 3, 1),
    ("Compliance Agent", 19, 0, 0),
]


def _build_cards(agents: list[AgentStatus] | None) -> list[FlyingCard]:
    cards: list[FlyingCard] = []
    seen: set[str] = set()
    if agents:
        for s in agents:
            aid = getattr(s.agent, "id", "")
            name = getattr(s.agent, "name", None) or aid or "agent"
            card_id = aid or name
            if card_id in seen:
                continue
            seen.add(card_id)
            cards.append(
                FlyingCard(
                    agent_id=card_id,
                    name=name[:_CARD_INNER_W],
                    trajectories=s.total_trajectories,
                    denials=s.denied_count,
                    escalations=getattr(s, "escalate_count", 0)
                    or getattr(s, "awaiting_count", 0),
                )
            )
    else:
        for name, runs, denials, esc in _DEMO_AGENTS:
            cards.append(
                FlyingCard(
                    agent_id=name,
                    name=name,
                    trajectories=runs,
                    denials=denials,
                    escalations=esc,
                )
            )
    return cards


# ═══════════════════════════════════════════════════════════════════════════
# Canvas widget
# ═══════════════════════════════════════════════════════════════════════════


class ScreensaverCanvas(Widget):
    """Full-screen canvas: starfield + flying agent cards."""

    can_focus = True

    DEFAULT_CSS = """
    ScreensaverCanvas {
        layer: canvas;
        width: 100%;
        height: 100%;
        background: #000000;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._cards: list[FlyingCard] = []
        self._stars: list[Star] = []
        self._meteors: list[Meteor] = []
        self._rng = random.Random()  # noqa: S311
        self._tick_count = 0
        self._tw = 80
        self._th = 24
        self._grid: Grid = []
        self._black_row: list[Cell] = []
        self._ready = False
        self._fleet_health_value: float = 0.0
        self._inspect: bool = False
        self._inspect_speed: float = 1.0  # 1.0 normal, 0.2 slow

    # ── Setup ───────────────────────────────────────────────────────────

    def setup(self, cards: list[FlyingCard]) -> None:
        self._cards = cards
        self._tw = self.size.width
        self._th = self.size.height
        self._init_stars()
        self._assign_speeds()
        self._init_positions()
        self._alloc_grid()
        self._fleet_health_value = self._compute_fleet_health()
        self._ready = True

    def on_resize(self, event: events.Resize) -> None:
        self._tw = self.size.width
        self._th = self.size.height
        self._init_stars()
        self._alloc_grid()

    def _alloc_grid(self) -> None:
        self._black_row = [_BLACK] * self._tw
        self._grid = [[_BLACK] * self._tw for _ in range(self._th)]

    def _init_stars(self) -> None:
        w, h = self._tw, self._th
        if w < 2 or h < 2:
            return
        rng = self._rng
        base_n = max(80, w * h // 18)
        self._stars = []
        for layer, cfg in _PARALLAX.items():
            n = int(base_n * cfg["density"])
            lo_bri, hi_bri = cfg["bri"]
            chars = cfg["chars"] or _STAR_CHARS
            for _ in range(n):
                self._stars.append(
                    Star(
                        x=rng.randint(0, w - 1),
                        y=rng.randint(0, h - 1),
                        char=rng.choice(chars),
                        warm=rng.random() < 0.3,
                        base_bri=rng.randint(lo_bri, hi_bri),
                        phase=rng.random() * math.tau,
                        layer=layer,
                    )
                )

    def _assign_speeds(self) -> None:
        """Give each card a speed based on status + per-card flap timing."""
        for card in self._cards:
            self._assign_card_speed(card)

    def _assign_card_speed(self, card: FlyingCard) -> None:
        """Set speed and flap timing for a single card based on its status."""
        rng = self._rng
        if card.status == "clean":
            lo, hi = _SPEED_OK
        elif card.status == "deny":
            lo, hi = _SPEED_DENY
        else:
            lo, hi = _SPEED_ESC
        card.dx = rng.uniform(lo, hi)
        card.dy = abs(card.dx) * _DY_RATIO
        # Async wing flapping: each card has its own period and offset
        card.flap_period = rng.randint(2, 4)
        card.flap_counter = rng.randint(0, card.flap_period - 1)
        card.phase = rng.randint(0, 3)

    def _compute_fleet_health(self) -> float:
        """0.0 = all clean, 1.0 = all denied. For title color."""
        if not self._cards:
            return 0.0
        total = len(self._cards)
        denied = sum(1 for c in self._cards if c.denials > 0)
        escalated = sum(1 for c in self._cards if c.escalations > 0 and c.denials == 0)
        return min(1.0, (denied + escalated * 0.5) / total)

    def sync_data(self, agents: list[AgentStatus] | None) -> None:
        """Update cards with live agent data without resetting animation.

        - Existing agents: update stats, re-speed if status changed.
        - New agents: spawn off-screen right.
        - Removed agents: left to fly off naturally.
        - New denials trigger a flip animation.
        """
        fresh = _build_cards(agents)
        # Build lookup; if duplicates somehow exist, keep only the first
        existing: dict[str, FlyingCard] = {}
        for c in self._cards:
            if c.agent_id not in existing:
                existing[c.agent_id] = c
        tw, th = self._tw, self._th

        for fc in fresh:
            card = existing.get(fc.agent_id)
            if card is None:
                # New agent: give it speed/flap and spawn off-screen right
                fc.x = float(tw + self._rng.randint(30, 80))
                y_lo, y_hi = 2, max(3, th - _CARD_H - 4)
                fc.y = float(self._rng.randint(y_lo, y_hi))
                self._assign_card_speed(fc)
                existing[fc.agent_id] = fc  # track to prevent double-add
                self._cards.append(fc)
            else:
                # Existing agent: update stats
                old_status = card.status
                old_denials = card.denials
                card.name = fc.name
                card.trajectories = fc.trajectories
                card.denials = fc.denials
                card.escalations = fc.escalations
                # If status changed (e.g. clean→deny), update speed tier
                if card.status != old_status:
                    self._assign_card_speed(card)
                # New denials: trigger flip animation
                if fc.denials > old_denials and card.flip_timer == 0:
                    card.flip_timer = _FLIP_DURATION
                    card.flip_total = _FLIP_DURATION

        self._fleet_health_value = self._compute_fleet_health()

    def _init_positions(self) -> None:
        """Place cards off-screen right and above top, staggered for entry.

        Screen begins empty. Cards enter from the right and top edges,
        spaced enough that the screen populates without overlap.
        """
        tw, th = self._tw, self._th
        if tw < 10 or th < 5 or not self._cards:
            return
        rng = self._rng

        # Shuffle so fast/slow cards are intermixed
        rng.shuffle(self._cards)

        # Split: ~40% enter from top, rest from right
        n_top = max(1, len(self._cards) * 2 // 5)

        # Valid Y range for right-edge spawns
        y_lo, y_hi = 2, max(3, th - _CARD_H - 4)

        # Place right-edge cards
        cum_x = 10.0
        for card in self._cards[n_top:]:
            card.x = float(tw + cum_x)
            placed = False
            for _attempt in range(30):
                card.y = float(rng.randint(y_lo, y_hi))
                if not self._overlaps(card):
                    placed = True
                    break
            if not placed:
                cum_x += _SPRITE_W + 10
                card.x = float(tw + cum_x)
                card.y = float(rng.randint(y_lo, y_hi))
            cum_x += rng.randint(25, 45)

        # Place top-edge cards: spread across X, staggered above top
        cum_y = _SPRITE_H + 5
        for card in self._cards[:n_top]:
            card.y = float(-cum_y)
            placed = False
            for _attempt in range(30):
                card.x = float(rng.randint(_SPRITE_W, max(_SPRITE_W + 1, tw - 10)))
                if not self._overlaps(card):
                    placed = True
                    break
            if not placed:
                cum_y += _SPRITE_H + 8
                card.y = float(-cum_y)
                card.x = float(rng.randint(_SPRITE_W, max(_SPRITE_W + 1, tw - 10)))
            cum_y += rng.randint(20, 40)

    def _overlaps(self, card: FlyingCard) -> bool:
        """Check if card's bounding box overlaps any other card (with padding)."""
        for other in self._cards:
            if other is card:
                continue
            if (
                abs(card.x - other.x) < _SPRITE_W + 14
                and abs(card.y - other.y) < _SPRITE_H + 4
            ):
                return True
        return False

    def _separate_cards(self) -> None:
        """Push overlapping cards apart every tick (runtime collision avoidance).

        The trailing card (further from the exit, i.e. further right) gets
        nudged backward along the flight path so it falls behind naturally.
        """
        min_dx = _SPRITE_W + 6
        min_dy = _SPRITE_H + 2
        cards = self._cards
        n = len(cards)
        for i in range(n):
            a = cards[i]
            for j in range(i + 1, n):
                b = cards[j]
                if abs(a.x - b.x) < min_dx and abs(a.y - b.y) < min_dy:
                    # Nudge the trailing card (further right) backward
                    if a.x >= b.x:
                        a.x += 0.8
                        a.y -= 0.15
                    else:
                        b.x += 0.8
                        b.y -= 0.15

    # ── Tick handlers ───────────────────────────────────────────────────

    def move_tick(self) -> None:
        tw, th = self._tw, self._th
        rng = self._rng
        self._tick_count += 1
        sm = self._inspect_speed

        for card in self._cards:
            card.x += card.dx * sm
            card.y += card.dy * sm

            # Wrap: exited left or drifted off bottom → respawn
            if card.x < -_SPRITE_W - 8 or card.y > th + 2:
                self._respawn(card, tw, th, rng)

            # Decrement flip timer
            if card.flip_timer > 0:
                card.flip_timer -= 1

        self._separate_cards()

        # Meteors: move existing, remove dead, occasionally spawn new
        alive: list[Meteor] = []
        for m in self._meteors:
            m.x += m.dx * sm
            m.y += m.dy * sm
            m.life -= 1
            if m.life > 0 and -m.length < m.x < tw + m.length and 0 < m.y < th:
                alive.append(m)
        self._meteors = alive

        # Spawn: ~1 meteor every 4-8 seconds (at 50fps: 1 in 200-400 ticks)
        if rng.randint(1, 300) == 1 and tw > 20:
            bright = rng.random() < 0.4
            length = rng.randint(6, 14) if bright else rng.randint(3, 8)
            self._meteors.append(
                Meteor(
                    x=float(rng.randint(tw // 4, tw)),
                    y=float(rng.randint(1, max(2, th // 3))),
                    dx=rng.uniform(-1.2, -0.6),
                    dy=rng.uniform(0.3, 0.7),
                    length=length,
                    life=rng.randint(40, 100),
                    bright=bright,
                )
            )

        self.refresh()

    def _respawn(self, card: FlyingCard, tw: int, th: int, rng: random.Random) -> None:
        """Respawn a card off-screen, from either the right edge or top edge."""
        from_top = rng.random() < 0.4  # 40% chance to enter from top

        if from_top:
            # Spawn above the top edge, spread across the screen width
            x_lo = _SPRITE_W
            x_hi = max(x_lo + 1, tw - 10)
            y_base = -_SPRITE_H
            for batch in range(4):
                y_off = batch * (_SPRITE_H + 6)
                for _attempt in range(15):
                    card.x = float(rng.randint(x_lo, x_hi))
                    card.y = float(y_base - y_off - rng.randint(0, 30))
                    if not self._overlaps(card):
                        return
            card.x = float(rng.randint(x_lo, x_hi))
            card.y = float(y_base - 80 - rng.randint(0, 60))
        else:
            # Spawn off-screen right (original behavior)
            y_lo = 2
            y_hi = max(y_lo + 1, th - _CARD_H - 4)
            for batch in range(4):
                x_lo = tw + 30 + batch * 60
                x_hi = x_lo + 50
                for _attempt in range(15):
                    card.x = float(rng.randint(x_lo, x_hi))
                    card.y = float(rng.randint(y_lo, y_hi))
                    if not self._overlaps(card):
                        return
            card.x = float(tw + 350 + rng.randint(0, 150))
            card.y = float(rng.randint(y_lo, y_hi))

    def flap_tick(self) -> None:
        """Advance wing frames asynchronously per card."""
        for card in self._cards:
            card.flap_counter += 1
            if card.flap_counter >= card.flap_period:
                card.flap_counter = 0
                card.phase = (card.phase + 1) % 4

    # ── Flip animation helper ─────────────────────────────────────────

    def _flip_margin(self, card: FlyingCard) -> tuple[int, bool] | None:
        """Return (columns_to_mask_from_each_side, is_flash) or None."""
        if card.flip_timer <= 0:
            return None
        elapsed = card.flip_total - card.flip_timer
        half_w = _CARD_W // 2

        if elapsed < _FLIP_SQUISH:
            # Squishing inward
            progress = elapsed / _FLIP_SQUISH
            return (int(half_w * progress), False)
        elif elapsed < _FLIP_SQUISH + _FLIP_FLASH:
            # Fully squished, red flash
            return (half_w - 1, True)
        else:
            # Expanding back out
            expand_elapsed = elapsed - _FLIP_SQUISH - _FLIP_FLASH
            progress = expand_elapsed / (_FLIP_DURATION - _FLIP_SQUISH - _FLIP_FLASH)
            return (int(half_w * (1.0 - progress)), False)

    # ── Rendering ───────────────────────────────────────────────────────

    def render(self) -> Group:
        if not self._ready:
            return Group(Text(" "))

        tw, th = self._tw, self._th
        if tw < 10 or th < 5:
            return Group(Text(" "))

        grid = self._grid
        black = self._black_row
        for row in grid:
            row[:] = black

        self._draw_stars(grid, tw, th)
        self._draw_meteors(grid, tw, th)
        self._draw_title(grid, tw)

        for card in self._cards:
            self._draw_shadow(grid, card, tw, th)
        for card in self._cards:
            self._draw_edges(grid, card, tw, th)
            self._draw_body(grid, card, tw, th)
            self._draw_wings(grid, card, tw, th)

        if self._inspect:
            self._draw_inspect_overlay(grid, tw, th)

        # Convert grid to Rich Text with run-length style encoding
        lines: list[Text] = []
        for row in grid:
            line = Text("".join(ch for ch, _ in row))
            start = 0
            cur: Style | None = row[0][1] if tw > 0 else None
            for col in range(1, tw):
                s = row[col][1]
                if s is not cur:
                    if cur is not None:
                        line.stylize(cur, start, col)
                    start = col
                    cur = s
            if cur is not None:
                line.stylize(cur, start, tw)
            lines.append(line)

        return Group(*lines)

    # ── Drawing helpers ─────────────────────────────────────────────────

    def _draw_stars(self, grid: Grid, tw: int, th: int) -> None:
        tc = self._tick_count
        for star in self._stars:
            if 0 <= star.x < tw and 0 <= star.y < th:
                twinkle_speed = _TWINKLE_SPEED.get(star.layer, 0.065)
                wave = math.sin(tc * twinkle_speed + star.phase)
                bri = int(max(0, min(15, star.base_bri + wave * 4.5)))
                if bri >= 2:
                    styles = _STAR_WARM if star.warm else _STAR_COOL
                    grid[star.y][star.x] = (star.char, styles[bri])

    def _draw_meteors(self, grid: Grid, tw: int, th: int) -> None:
        """Draw shooting stars as streaks with fading tails."""
        for m in self._meteors:
            if m.bright:
                head_s, body_s, tail_s = _METEOR_HEAD, _METEOR_BODY, _METEOR_TAIL
            else:
                head_s, body_s, tail_s = (
                    _METEOR_DIM_HEAD,
                    _METEOR_DIM_BODY,
                    _METEOR_DIM_TAIL,
                )
            # Draw trail from head backward along the velocity vector
            speed = max(0.01, (m.dx**2 + m.dy**2) ** 0.5)
            bx, by = -m.dx / speed, -m.dy / speed
            for i in range(m.length):
                px = int(m.x + bx * i)
                py = int(m.y + by * i)
                if 0 <= px < tw and 0 <= py < th:
                    if i == 0:
                        grid[py][px] = ("*", head_s)
                    elif i < m.length // 3:
                        grid[py][px] = ("─", body_s)
                    else:
                        grid[py][px] = ("·", tail_s)

    def _draw_title(self, grid: Grid, tw: int) -> None:
        title = " S O N D E R A "
        if tw < len(title) + 4:
            return
        t = self._tick_count * 0.022
        glow = 0.5 + 0.5 * math.sin(t)

        # Fleet health pulse: green → amber → red
        health = self._fleet_health_value
        if health < 0.5:
            blend = health * 2.0
            base_r = int(50 + blend * 70)
            base_g = int(120 - blend * 20)
            base_b = int(90 - blend * 60)
            peak_r = int(129 + blend * 106)
            peak_g = int(221 - blend * 21)
            peak_b = int(180 - blend * 100)
        else:
            blend = (health - 0.5) * 2.0
            base_r = int(120 + blend * 10)
            base_g = int(100 - blend * 60)
            base_b = int(30 + blend * 10)
            peak_r = int(235 - blend * 15)
            peak_g = int(200 - blend * 120)
            peak_b = int(80 - blend * 0)

        r = int(base_r + (peak_r - base_r) * glow)
        g = int(base_g + (peak_g - base_g) * glow)
        b = int(base_b + (peak_b - base_b) * glow)

        ts = Style(color=f"rgb({r},{g},{b})", bold=True)
        start = (tw - len(title)) // 2
        for i, ch in enumerate(title):
            x = start + i
            if 0 <= x < tw:
                grid[0][x] = (ch, ts)
        dim = Style(color=f"rgb({r // 3},{g // 3},{b // 3})")
        for i in range(min(14, start - 1)):
            lx = start - 1 - i
            rx = start + len(title) + i
            if 0 <= lx < tw:
                grid[0][lx] = ("─", dim)
            if 0 <= rx < tw:
                grid[0][rx] = ("─", dim)

    def _draw_shadow(self, grid: Grid, card: FlyingCard, tw: int, th: int) -> None:
        """Drop shadow: offset (2,1) from card body, wider for 3D depth."""
        body_x = int(card.x) + _WING_W + _GAP
        cy = int(card.y)
        for row_idx in range(_CARD_H + 2):
            sy = cy + row_idx + 1
            if sy < 0 or sy >= th:
                continue
            for col_idx in range(_CARD_W + 3):
                sx = body_x + col_idx + 2
                if 0 <= sx < tw:
                    grid[sy][sx] = ("░", _SHADOW_S)

    def _draw_edges(self, grid: Grid, card: FlyingCard, tw: int, th: int) -> None:
        """3D side/bottom edges: 2-column right face + bottom for depth."""
        bs = _card_body_styles(card.heat)
        body_x = int(card.x) + _WING_W + _GAP
        cy = int(card.y)

        # Right edge: 2 columns (inner lighter, outer darker)
        rx1 = body_x + _CARD_W
        rx2 = rx1 + 1
        for row_idx in range(_CARD_H):
            gy = cy + row_idx
            if 0 <= gy < th:
                if 0 <= rx1 < tw:
                    grid[gy][rx1] = ("▐", bs["edge_r1"])
                if 0 <= rx2 < tw:
                    grid[gy][rx2] = ("▐", bs["edge_r2"])

        # Bottom edge: spans card + right edge width
        by = cy + _CARD_H
        if 0 <= by < th:
            for col_idx in range(_CARD_W + _EDGE_R):
                gx = body_x + col_idx
                if 0 <= gx < tw:
                    grid[by][gx] = ("▀", bs["edge_b"])
            # Bottom-right corner: darkest
            br_x = body_x + _CARD_W + _EDGE_R - 1
            if 0 <= br_x < tw:
                grid[by][br_x] = ("▀", bs["edge_br"])

    def _draw_body(self, grid: Grid, card: FlyingCard, tw: int, th: int) -> None:
        """Card face: rounded corners, specular top, per-corner lighting."""
        bs = _card_body_styles(card.heat)
        flip = self._flip_margin(card)
        body_x = int(card.x) + _WING_W + _GAP
        cy = int(card.y)

        # Card text
        name = card.name[:_CARD_INNER_W].ljust(_CARD_INNER_W)
        rl = "run" if card.trajectories == 1 else "runs"
        stats = f"{card.trajectories} {rl}"
        if card.denials > 0:
            stats += f"  ✗ {card.denials}"
        elif card.escalations > 0:
            stats += f"  ⚠ {card.escalations}"
        stats = stats[:_CARD_INNER_W].ljust(_CARD_INNER_W)

        top = "╭" + "─" * _CARD_INNER_W + "╮"
        nm = "│" + name + "│"
        st = "│" + stats + "│"
        bot = "╰" + "─" * _CARD_INNER_W + "╯"

        for row_idx, text in enumerate([top, nm, st, bot]):
            gy = cy + row_idx
            if gy < 0 or gy >= th:
                continue
            is_top_half = row_idx <= 1
            fill = bs["fill_hi"] if is_top_half else bs["fill"]

            for col_idx, ch in enumerate(text):
                gx = body_x + col_idx
                if not (0 <= gx < tw):
                    continue

                # Flip masking: hide columns from edges inward
                if flip is not None:
                    margin, is_flash = flip
                    if col_idx < margin or col_idx >= _CARD_W - margin:
                        continue
                    if is_flash:
                        grid[gy][gx] = (ch, _FLIP_RED)
                        continue

                # 3D border lighting
                if row_idx == 0:
                    if ch == "╭":
                        style = bs["corner_tl"]
                    elif ch == "╮":
                        style = bs["corner_tr"]
                    else:
                        style = bs["top_bdr"]
                elif row_idx == 3:
                    if ch == "╰":
                        style = bs["corner_bl"]
                    elif ch == "╯":
                        style = bs["corner_br"]
                    else:
                        style = bs["lo_bdr"]
                elif ch == "│" and col_idx == 0:
                    style = bs["hi_bdr"]
                elif ch == "│":
                    style = bs["lo_bdr"]
                elif row_idx == 1:
                    style = bs["name"]
                elif row_idx == 2:
                    inner_col = col_idx - 1
                    if "✗" in stats:
                        style = (
                            bs["deny"] if inner_col >= stats.find("✗") else bs["stat"]
                        )
                    elif "⚠" in stats:
                        style = (
                            bs["esc"] if inner_col >= stats.find("⚠") else bs["stat"]
                        )
                    else:
                        style = bs["stat"]
                else:
                    style = fill

                grid[gy][gx] = (ch, style)

            # Fill any remaining interior spaces with card background
            if row_idx in (1, 2):
                for ci in range(1, _CARD_W - 1):
                    gx = body_x + ci
                    if 0 <= gx < tw:
                        # Skip masked columns during flip
                        if flip is not None:
                            margin, is_flash = flip
                            if ci < margin or ci >= _CARD_W - margin:
                                continue
                        ch_cur, s_cur = grid[gy][gx]
                        if ch_cur == " " and s_cur is None:
                            grid[gy][gx] = (" ", fill)

    def _draw_wings(self, grid: Grid, card: FlyingCard, tw: int, th: int) -> None:
        # Hide wings during flip flash phase (fully squished)
        flip = self._flip_margin(card)
        if flip is not None:
            _margin, is_flash = flip
            if is_flash:
                return

        cx = int(card.x)
        cy = int(card.y)
        body_x = cx + _WING_W + _GAP
        frame = _FRAMES[card.phase]
        ws = _wing_styles(card.status)
        y_off = frame["y_offset"]

        for ri in range(len(frame["left_chars"])):
            wy = cy + y_off + ri
            if wy < 0 or wy >= th:
                continue
            lc = frame["left_chars"][ri]
            rc = frame["right_chars"][ri]
            l_bri = frame["left_brightness"][ri]
            r_bri = frame["right_brightness"][ri]

            # Left wing
            for ci in range(_WING_W):
                if l_bri[ci] == 0 or lc[ci] == " ":
                    continue
                gx = cx + ci
                if 0 <= gx < tw:
                    grid[wy][gx] = (lc[ci], ws[l_bri[ci]])

            # Right wing: starts after card + right-edge + gap
            rx_base = body_x + _CARD_W + _EDGE_R + _GAP
            for ci in range(_WING_W):
                if r_bri[ci] == 0 or rc[ci] == " ":
                    continue
                gx = rx_base + ci
                if 0 <= gx < tw:
                    grid[wy][gx] = (rc[ci], ws[r_bri[ci]])

    def _draw_inspect_overlay(self, grid: Grid, tw: int, th: int) -> None:
        """Draw stats below each visible card + highlight worst agent."""
        # Find the worst card for highlighting
        worst: FlyingCard | None = None
        worst_heat = 0.0
        for c in self._cards:
            if c.heat > worst_heat:
                worst_heat = c.heat
                worst = c

        for card in self._cards:
            body_x = int(card.x) + _WING_W + _GAP
            cy = int(card.y)

            # Only draw if card body is visible
            if body_x + _CARD_W < 0 or body_x >= tw:
                continue

            # Stats overlay below card bottom edge
            overlay_y = cy + _CARD_H + _EDGE_B + 1

            if card.trajectories > 0:
                rate = card.denials / card.trajectories * 100
                line1 = f" deny:{rate:3.0f}%  traj:{card.trajectories} "
            else:
                line1 = f" traj:{card.trajectories} "

            line2 = f" esc:{card.escalations} " if card.escalations > 0 else ""

            for li, text in enumerate([line1, line2]):
                if not text:
                    continue
                gy = overlay_y + li
                if gy < 0 or gy >= th:
                    continue
                s = _INSPECT_BG if li == 0 else _INSPECT_DIM
                for ci, ch in enumerate(text):
                    gx = body_x + ci
                    if 0 <= gx < tw:
                        grid[gy][gx] = (ch, s)

            # Highlight worst card with red border
            if card is worst and worst_heat > 0:
                hy_top = cy - 1
                hy_bot = cy + _CARD_H + _EDGE_B
                for col in range(-1, _CARD_W + _EDGE_R + 1):
                    gx = body_x + col
                    if 0 <= gx < tw:
                        if 0 <= hy_top < th:
                            grid[hy_top][gx] = ("─", _INSPECT_HIGHLIGHT)
                        if 0 <= hy_bot < th:
                            grid[hy_bot][gx] = ("─", _INSPECT_HIGHLIGHT)
                # Side lines
                lx = body_x - 1
                rx = body_x + _CARD_W + _EDGE_R
                for row in range(_CARD_H + _EDGE_B):
                    gy = cy + row
                    if 0 <= gy < th:
                        if 0 <= lx < tw:
                            grid[gy][lx] = ("│", _INSPECT_HIGHLIGHT)
                        if 0 <= rx < tw:
                            grid[gy][rx] = ("│", _INSPECT_HIGHLIGHT)


# ═══════════════════════════════════════════════════════════════════════════
# Legend overlay
# ═══════════════════════════════════════════════════════════════════════════


class LegendPanel(Static):
    """Toggleable legend explaining the screensaver visuals."""

    DEFAULT_CSS = """
    LegendPanel {
        layer: legend;
        dock: bottom;
        width: 100%;
        height: auto;
        padding: 0 2;
        background: #0a1a10;
        border-top: solid #2a2a2a;
        display: none;
    }
    LegendPanel.--visible {
        display: block;
    }
    """

    def on_mount(self) -> None:
        self.update(self._build())

    def _build(self) -> Text:
        t = Text()
        h = Style(color="#EAEAEA", bold=True)
        d = Style(color="#888888")
        k = Style(color="#81DDB4", bold=True)
        grn = Style(color="#81DDB4", bold=True)
        red = Style(color="#BF616A", bold=True)
        amb = Style(color="#EBCB8B", bold=True)

        t.append("\n  FLYING AGENTS\n\n", h)
        t.append("  Wing color and speed show agent health:\n\n", d)

        t.append("  ████", grn)
        t.append("  OK", h)
        t.append("           no violations (fastest)\n", d)

        t.append("  ████", red)
        t.append("  Denied", h)
        t.append("       has denied actions (slower)\n", d)

        t.append("  ████", amb)
        t.append("  Escalated", h)
        t.append("    needs review (slowest)\n\n", d)

        t.append("  Cards show agent name and trajectory count.\n", d)
        t.append("  Card glow shows violation intensity (green→red).\n", d)
        t.append("  Title glow reflects overall fleet health.\n\n", d)
        t.append("  ", d)
        t.append("✗ N", red)
        t.append(" = denied   ", d)
        t.append("⚠ N", amb)
        t.append(" = escalated\n\n", d)

        t.append("  s", k)
        t.append("  toggle legend    ", d)
        t.append("i", k)
        t.append("  inspect mode    ", d)
        t.append("esc", k)
        t.append("  exit screensaver\n", d)

        return t


# ═══════════════════════════════════════════════════════════════════════════
# Screen
# ═══════════════════════════════════════════════════════════════════════════


class ScreensaverScreen(Screen):
    """Full-screen flying agent cards screensaver.

    ``s`` toggles a legend overlay. ``i`` toggles inspect mode.
    Any other key or click exits.
    """

    BINDINGS = [
        Binding("escape", "dismiss_screensaver", show=False),
        Binding("s", "toggle_legend", show=False),
        Binding("i", "toggle_inspect", show=False),
    ]

    DEFAULT_CSS = """
    ScreensaverScreen {
        layers: canvas legend;
        background: #000000;
    }
    """

    def __init__(self, agent_statuses: list | None = None) -> None:
        super().__init__()
        self._agent_statuses = agent_statuses
        self._dismissed = False

    def compose(self) -> ComposeResult:
        yield ScreensaverCanvas()
        yield LegendPanel()

    def on_mount(self) -> None:
        canvas = self.query_one(ScreensaverCanvas)
        canvas.focus()
        # Defer setup so the widget has its real size (avoids top-left flash)
        self.call_after_refresh(self._deferred_setup, canvas)

    def _deferred_setup(self, canvas: ScreensaverCanvas) -> None:
        cards = _build_cards(self._agent_statuses)

        # Limit to available vertical lanes
        tw, th = canvas.size
        usable = th - 4
        max_lanes = max(1, usable // (_SPRITE_H + 1))
        cards = cards[: min(max_lanes, 10)]

        canvas.setup(cards)

        self.set_interval(_MOVE_S, canvas.move_tick)
        self.set_interval(_FLAP_S, canvas.flap_tick)
        self.set_interval(30, self._sync_live_data)

    def _sync_live_data(self) -> None:
        """Pull fresh agent data from the app and sync into flying cards."""
        statuses = getattr(self.app, "_agent_statuses", None)
        if statuses:
            self.query_one(ScreensaverCanvas).sync_data(statuses)

    # ── Key / click handling ────────────────────────────────────────────

    def on_key(self, event: events.Key) -> None:
        if event.key not in ("escape", "s", "i"):
            event.stop()
            event.prevent_default()
            self._dismiss_screensaver()

    def on_click(self, event: events.Click) -> None:
        event.stop()
        self._dismiss_screensaver()

    def action_dismiss_screensaver(self) -> None:
        self._dismiss_screensaver()

    def action_toggle_legend(self) -> None:
        self.query_one(LegendPanel).toggle_class("--visible")

    def action_toggle_inspect(self) -> None:
        canvas = self.query_one(ScreensaverCanvas)
        canvas._inspect = not canvas._inspect
        canvas._inspect_speed = 0.2 if canvas._inspect else 1.0

    def _dismiss_screensaver(self) -> None:
        if not self._dismissed:
            self._dismissed = True
            self.app.pop_screen()
