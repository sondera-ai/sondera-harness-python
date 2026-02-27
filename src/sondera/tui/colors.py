"""Centralized theme color palette for the Sondera TUI.

Widgets should use ``get_theme_colors(self.app)`` (returns a ``ThemeColors``
instance) rather than hardcoded hex values.  This ensures colors adapt when
switching between ``sondera-dark`` and ``sondera-light``.
"""

from __future__ import annotations

from dataclasses import dataclass

from textual.app import App


@dataclass(frozen=True)
class ThemeColors:
    """Semantic color roles resolved for the active theme."""

    # Text hierarchy
    fg: str  # Primary text
    fg_secondary: str  # Secondary text
    fg_muted: str  # Metadata, timestamps, action hints
    fg_dim: str  # Disabled, placeholders, tree connectors

    # Brand / active
    primary: str  # Active state, cursor, brand accent

    # Functional status
    error: str  # Denied, failed
    warning: str  # Escalated, suspended
    success: str  # Clean, healthy
    prompt_blue: str  # User prompts, file paths

    # Structural
    border: str  # Disabled buttons, off states

    # Backgrounds
    error_bg: str  # Denied row background
    diff_add_bg: str  # Diff added line background
    diff_remove_bg: str  # Diff removed line background

    # Decision dim variants (faded accents for subtle backgrounds)
    dim_allow: str
    dim_deny: str
    dim_escalate: str

    # Syntax highlighting
    kw: str  # Keywords (def, class, import)
    string: str  # String literals
    comment: str  # Comments
    decorator: str  # Decorators (@something)
    builtin: str  # Builtin functions, file paths


# Shared animation constants
SPINNER_CHARS = ["*", "+", "\u00d7", "\u00b7", "\u2022"]
SPINNER_INTERVAL = 0.24

# AI Assist thinking animation: esoteric verbs + breathing glow
THINKING_VERBS = [
    "Pondering",
    "Ruminating",
    "Cogitating",
    "Deliberating",
    "Contemplating",
    "Synthesizing",
    "Distilling",
    "Unraveling",
    "Deciphering",
    "Percolating",
    "Crystallizing",
    "Extrapolating",
    "Harmonizing",
    "Calibrating",
    "Sifting",
    "Fermenting",
    "Divining",
    "Transmuting",
    "Coalescing",
    "Unfurling",
    "Adjudicating",
    "Interpolating",
    "Refracting",
    "Sublimating",
    "Metabolizing",
    "Tessellating",
    "Amalgamating",
    "Precipitating",
    "Conjugating",
    "Phosphorescing",
    "Diffracting",
    "Equilibrating",
]

# Thinking animation tick rate (60ms ≈ 16 FPS for smooth motion)
THINKING_INTERVAL = 0.08

# ---------------------------------------------------------------------------
# Dynamic glow gradient generator
# ---------------------------------------------------------------------------


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def generate_glow(primary: str, dark: bool, steps: int = 9) -> list[str]:
    """Generate a glow gradient from a base color.

    For dark themes: floor is dim (mixed toward black), peak is bright (mixed toward white).
    For light themes: floor is faded (mixed toward bg), peak is saturated/dark.
    """
    r, g, b = _hex_to_rgb(primary)
    result = []
    for i in range(steps):
        t = i / max(steps - 1, 1)  # 0.0 (floor) → 1.0 (peak)
        if dark:
            # Floor: mix 60% toward black. Peak: mix 15% toward white.
            floor_mix = 0.40  # keep 40% of color at floor
            peak_mix = 0.15  # lighten 15% at peak
            base_t = floor_mix + (1.0 - floor_mix) * t  # 0.40 → 1.0
            nr = int(r * base_t + 255 * peak_mix * t)
            ng = int(g * base_t + 255 * peak_mix * t)
            nb = int(b * base_t + 255 * peak_mix * t)
        else:
            # Floor: faded (mixed toward light bg). Peak: full saturation.
            floor_mix = 0.55  # at floor, mix 45% toward light grey
            bg_r, bg_g, bg_b = 234, 234, 234  # light bg
            base_t = floor_mix + (1.0 - floor_mix) * t
            nr = int(r * base_t + bg_r * (1.0 - base_t))
            ng = int(g * base_t + bg_g * (1.0 - base_t))
            nb = int(b * base_t + bg_b * (1.0 - base_t))
        result.append(_rgb_to_hex(min(nr, 255), min(ng, 255), min(nb, 255)))
    return result


DARK_PALETTE = ThemeColors(
    # Text
    fg="#EAEAEA",
    fg_secondary="#C0C0C0",
    fg_muted="#8a8a8a",
    fg_dim="#6a6a6a",
    # Brand
    primary="#81DDB4",
    # Functional
    error="#BF616A",
    warning="#EBCB8B",
    success="#A3BE8C",
    prompt_blue="#5E81AC",
    # Structural
    border="#424242",
    # Backgrounds
    error_bg="#2a1215",
    diff_add_bg="#1a2e1a",
    diff_remove_bg="#2e1a1a",
    # Decision dims
    dim_allow="#3a6a4a",
    dim_deny="#7a3a3a",
    dim_escalate="#8a7a4a",
    # Syntax (derived from functional colors)
    kw="#81DDB4",
    string="#A3BE8C",
    comment="#6a6a6a",
    decorator="#EBCB8B",
    builtin="#5E81AC",
)

LIGHT_PALETTE = ThemeColors(
    # Text
    fg="#06110B",
    fg_secondary="#555555",
    fg_muted="#5a5a5a",
    fg_dim="#7a7a7a",
    # Brand
    primary="#569378",
    # Functional
    error="#BF616A",
    warning="#7A6835",
    success="#4D6A3A",
    prompt_blue="#3B6A96",
    # Structural
    border="#D6D6D6",
    # Backgrounds
    error_bg="#f5e8ea",
    diff_add_bg="#d4edda",
    diff_remove_bg="#f5d5d5",
    # Decision dims
    dim_allow="#c8e0d0",
    dim_deny="#e8c8ca",
    dim_escalate="#e8dfc8",
    # Syntax (derived from functional colors)
    kw="#569378",
    string="#4D6A3A",
    comment="#7a7a7a",
    decorator="#7A6835",
    builtin="#3B6A96",
)


def get_theme_colors(app: App[object]) -> ThemeColors:
    """Return the semantic color palette for the active theme."""
    return DARK_PALETTE if app.current_theme.dark else LIGHT_PALETTE
