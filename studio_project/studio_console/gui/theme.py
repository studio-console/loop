"""Studio Console GUI theme — extracted verbatim from studio_project.py.

This module owns the entire DearPyGui visual theme (colours, rounding,
spacing, button/pool/fader theme factories) and the font setup. It is a pure
move from the old inline block in studio_project.py with zero behaviour
change — do not "clean up" the historical quirks (e.g. the dead second
`except Exception:` in `_setup_fonts`).
"""

import os

try:
    import dearpygui.dearpygui as dpg
    _DPG_OK = True
except ImportError:
    _DPG_OK = False

# Colour palette — near-black / violet accent
# ——— modern-pro palette: vibey deep violet, richer depth, luminous states ———
_C_BG        = (5,   4,  12, 255)  # deepest background — where cards float
_C_PANEL     = (22,  17,  48, 255) # card surface — clearly lifted off the bg (3D step 1)
_C_BORDER    = (70,  52, 144, 255) # violet card edge — clean definition
_C_TEXT      = (240, 236, 255, 255)# crisp white with a violet cast
_C_DIM       = (110, 92, 172, 255) # dimmed — readable but recessed
_C_ACCENT    = (176, 128, 255, 255)# electric violet #b080ff — primary accent
_C_HOT       = (230, 168, 255, 255)# bright violet-pink for live status
_C_BTN       = (44,  34,  98, 255) # raised button (elevated above fields)
_C_BTN_H     = (98,  72, 190, 255) # hover — luminous lift
_C_BTN_A     = (146, 102, 248, 255)# active — bright violet
_C_CUE_ACT   = (88,  64, 172, 255) # selected cue row — brighter violet
_C_CUE_WRAP  = (140, 30,  30, 255) # wrap-to-cue-1 warning row — deliberately red, distinct from the violet active-row family
# Fader-page cue list's "this cue is actually running" row highlight —
# deliberately a distinct blue (not the violet family used everywhere
# else). NOT used for the selected-fader outline any more (that's plain
# white now, see _make_selected_slot_theme) — the two are separate
# signals: which fader is running vs. which fader is selected.
_C_FPG_ACCENT      = (50,  110, 255, 255)  # bright variant (unused directly at the
                                            # moment, kept for any future border/badge
                                            # use of this hue — green channel deliberately
                                            # kept well below both red and blue, since the
                                            # earlier (80,170,255) read as cyan/teal
                                            # against this dark UI)
_C_FPG_ACCENT_DIM  = (28,  62,  145, 255)  # darker fill variant — the running-cue row's
                                            # actual background color, safe as a text bg
_C_SLIDER_G  = _C_ACCENT

# pool panel header colours — violet family, varied lightness/hue for readability
_C_P_GROUPS  = (160, 120, 255, 255)  # mid violet
_C_P_COLORS  = (210,  98, 220, 255)  # pink-violet
_C_P_DIMS    = (180, 160, 255, 255)  # pale lavender
_C_P_CS      = (110, 190, 255, 255)  # cool blue-violet
_C_P_CUES    = ( 92, 162, 240, 255)  # muted sky
_C_P_FX      = (200, 130, 255, 255)  # bright violet
_C_P_FORMS   = (140, 200, 255, 255)  # icy periwinkle
_C_P_POSITION = (130, 155, 255, 255)  # blue-violet
_C_P_GOBO    = (175, 130, 255, 255)  # medium violet
_C_P_ZOOM    = (155, 175, 255, 255)  # blue-lavender
_C_P_FOCUS   = (210, 140, 255, 255)  # light violet-pink
_C_P_BEAM    = (145, 120, 230, 255)  # dim violet
_C_P_CONTROL = (130, 220, 200, 255)  # teal-mint


def _apply_theme():
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg,       _C_BG)
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg,        _C_PANEL)
            dpg.add_theme_color(dpg.mvThemeCol_Border,         _C_BORDER)
            dpg.add_theme_color(dpg.mvThemeCol_BorderShadow,   (0, 0, 0, 70))   # subtle drop-sink under cards/buttons
            dpg.add_theme_color(dpg.mvThemeCol_Text,           _C_TEXT)
            dpg.add_theme_color(dpg.mvThemeCol_TextDisabled,   _C_DIM)
            dpg.add_theme_color(dpg.mvThemeCol_Button,         _C_BTN)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered,  _C_BTN_H)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,   _C_BTN_A)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg,        (14, 11,  32, 255))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (24, 18,  50, 255))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive,  (34, 26,  68, 255))
            dpg.add_theme_color(dpg.mvThemeCol_TableRowBg,     ( 0,  0,   0,   0))
            dpg.add_theme_color(dpg.mvThemeCol_TableRowBgAlt,  (30, 22,  70,  90))
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrab,     _C_SLIDER_G)
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive, _C_ACCENT)
            dpg.add_theme_color(dpg.mvThemeCol_Header,         _C_CUE_ACT)
            dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered,  _C_BTN_H)
            dpg.add_theme_color(dpg.mvThemeCol_HeaderActive,   _C_BTN_A)
            dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive,  (44, 30,  98, 255))
            dpg.add_theme_color(dpg.mvThemeCol_TitleBg,        (22, 16,  48, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg,    _C_BG)
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab,  _C_BORDER)
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabHovered, _C_BTN_H)
            dpg.add_theme_color(dpg.mvThemeCol_PopupBg,        (12,  8,  28, 255))
            dpg.add_theme_color(dpg.mvThemeCol_TableBorderLight, _C_BORDER)
            dpg.add_theme_color(dpg.mvThemeCol_TableHeaderBg,  (28, 20,  65, 255))
            dpg.add_theme_color(dpg.mvThemeCol_CheckMark,      _C_ACCENT)
            dpg.add_theme_color(dpg.mvThemeCol_Separator,      (62, 44, 116, 255))
            # Input cursor and selection highlight
            dpg.add_theme_color(dpg.mvThemeCol_TextSelectedBg, (80, 50, 160, 140))
            dpg.add_theme_color(dpg.mvThemeCol_NavHighlight,   _C_ACCENT)
            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding,  12)
            dpg.add_theme_style(dpg.mvStyleVar_ChildRounding,   12)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding,   10)
            dpg.add_theme_style(dpg.mvStyleVar_GrabRounding,    9)
            dpg.add_theme_style(dpg.mvStyleVar_ScrollbarRounding, 10)
            dpg.add_theme_style(dpg.mvStyleVar_WindowBorderSize, 1)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing,     6, 5)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding,    8, 4)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding,   8, 6)
            dpg.add_theme_style(dpg.mvStyleVar_CellPadding,     4, 3)
    dpg.bind_theme(t)


def _make_go_theme():
    """Amber/orange theme for the GO ▶ button — visually distinct from default purple."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (120, 70, 14, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (210, 128, 26, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (255, 186,  60, 255))
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 12)
    return t


def _make_fade_bar_theme():
    """Amber progress bar for fader fade progress indicator."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvProgressBar):
            dpg.add_theme_color(dpg.mvThemeCol_PlotHistogram, (200, 130, 20, 200))
    return t


def _make_back_theme():
    """Muted blue theme for the BACK ◀ button."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (20,  50, 100, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (40,  90, 160, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (60, 140, 220, 255))
    return t


def _make_alert_btn_theme():
    """Red-tinted button for active alert states (BLIND, BLACKOUT)."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (120, 20, 20, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (200, 40, 40, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (255, 60, 60, 255))
    return t


def _make_transport_go_theme():
    """Green theme for the transport GO button."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (30,  74,  16, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (74, 138,  32, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (128, 208, 64, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Text,          (128, 208, 64, 255))
    return t


def _make_fpg_fader_theme():
    """Touch-styled slider theme for the fader-page grid's faders.

    Deliberately a plain, unmodified add_slider_int underneath this —
    tap-anywhere-then-drag is native ImGui/DPG slider behavior, no custom
    hit-testing needed — just themed for visibility: a real dark track
    (not transparent — an earlier version drew a fill rectangle behind a
    transparent slider for a true bottom-up fill look, but the overlay
    broke dragging on a real run) and a large, bright grab so the current
    level is still clearly visible at a glance, if not a full proportional
    fill.
    """
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvSliderInt):
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg,          _C_PANEL)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered,   _C_PANEL)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive,    _C_PANEL)
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrab,       _C_ACCENT)
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive, (230, 210, 255, 255))
            dpg.add_theme_style(dpg.mvStyleVar_GrabMinSize, 36)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 6)
    return t


def _make_dim_btn_theme():
    """Dimmed/inactive button style for toggleable status indicators."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (30, 24, 50, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (50, 40, 80, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (70, 55, 110, 255))
    return t


def _make_fpg_id_theme():
    """Flat, near-invisible button look for the fader-page id badge (top-
    left of each slot) — clicking it changes stack focus (active_fader)
    to this fader. Transparent background so it still reads as plain
    text until hovered/clicked, not like a normal raised button; dim
    text for the not-currently-focused state."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (0, 0, 0, 0))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (50, 40, 80, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (70, 55, 110, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Text,          _C_DIM)
    return t


def _make_fpg_id_focused_theme():
    """Same flat button look as _make_fpg_id_theme, white text — the
    fader-page id badge for whichever fader currently has stack focus."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (0, 0, 0, 0))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (50, 40, 80, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (70, 55, 110, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Text,          _C_TEXT)
    return t


def _make_numpad_digit_theme():
    """Slightly lighter background for digit buttons — distinct from keyword keys."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (24, 15, 64, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (60, 42, 140, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (100, 72, 210, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Text,          (232, 226, 255, 255))
    return t


def _make_pool_live_theme():
    """Brighter pool button theme for occupied (live) slots — clearly lit."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (52, 38, 118, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (95, 68, 178, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (132, 94, 235, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Text,          (222, 212, 255, 255))
    return t


def _make_pool_empty_theme():
    """Near-invisible pool button theme for empty slots — recedes to background."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (10,  7, 22, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (30, 22, 62, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (50, 36, 102, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Text,          (58, 45,  90, 255))
    return t


def _make_out_moment_theme():
    """Amber — fader output mode: moment (active only while level > 0)."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (90, 52,  8, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (160, 98, 14, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (220, 145, 28, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Text,          (255, 195, 80, 255))
    return t


def _make_out_vfade_theme():
    """Teal-blue — fader output mode: vfade (fader is crossfader)."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (8, 52, 90, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (14, 98, 160, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (28, 145, 220, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Text,          (80, 195, 255, 255))
    return t


def _make_trig_flash_theme():
    """Red-orange — trigger mode: flash (snap on/off, no fade)."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (90, 22, 8, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (160, 44, 14, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (220, 70, 28, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Text,          (255, 130, 90, 255))
    return t


def _make_trig_moment_theme():
    """Gold — trigger mode: moment (fades in/out on hold/release)."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (75, 60,  8, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (140, 115, 14, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (200, 170, 28, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Text,          (240, 215, 80, 255))
    return t


def _make_pri_hi_theme():
    """Green — fader priority: high (beats lower-priority layers)."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (12, 68, 20, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (22, 118, 36, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (38, 175, 58, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Text,          (90, 230, 115, 255))
    return t


def _make_pri_lo_theme():
    """Muted purple — fader priority: low (overridden by normal/high layers)."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (22, 16, 42, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (38, 28, 68, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (55, 40, 95, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Text,          (95, 74, 148, 255))
    return t


def _make_go_btn_theme():
    """Accent purple — GO / primary action button."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (55, 35, 100, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (95, 62, 165, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (140, 95, 230, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Text,          (200, 170, 255, 255))
    return t


def _make_stop_btn_theme():
    """Dark red — STOP button."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (80, 18, 18, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (140, 32, 32, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (200, 50, 50, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Text,          (255, 130, 130, 255))
    return t


def _make_selected_slot_theme():
    """Border-only outline for the fader-page slot whose stack is the
    current selection (active_fader — what left-column commands like
    RECORD CUE target). White, and deliberately does NOT touch ChildBg —
    filling the whole slot's background made it read as "too much blue"
    rather than a clean outline, and every other slot's normal panel
    background should stay exactly as-is; only the border differs."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvChildWindow):
            dpg.add_theme_color(dpg.mvThemeCol_Border, _C_TEXT)
    return t


# One font, everywhere (surface UI text + console/data text both bind to
# this). Avenir — and every other humanist-sans candidate checked
# (Avenir Next, SF Compact, Helvetica Neue) — genuinely has no glyphs at
# all for most of the arrows/geometric-shape/dingbat symbols this UI uses
# throughout (▶ ● ○ ⟳ → ⚡ etc. — verified directly against each font
# file's own cmap table with fontTools, not assumed), and DPG has no
# OS-level font-fallback chain the way native macOS text rendering does,
# so any glyph missing from the loaded font renders as a "?" placeholder
# — this was reported live, not theoretical, and it was pervasive. DPG
# 2.3.1 also doesn't support merging glyphs from a second font file into
# one atlas (its font-nesting API rejects it outright: "Incompatible
# parent. Acceptable parents include: mvFontRegistry" — fonts can only be
# direct registry children, not children of each other), so the fix is
# switching fonts, not patching glyph ranges. Menlo — already this app's
# console/data font, so it's a known-good look here already — covers all
# but 2 of the ~45 symbols in use (⟳ wrap icon, ⧖ takeover icon); those 2
# are substituted for glyphs Menlo does have (↻, ◐) at their call sites
# rather than needing a font workaround for just two characters.
_CONSOLE_FONT_CANDIDATES = [
    "/System/Library/Fonts/Menlo.ttc",                                      # macOS
    "/System/Library/Fonts/SFNSMono.ttf",                                   # macOS (Alt)
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",                  # Debian/Ubuntu
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",      # Debian/Ubuntu (RPM-derived)
    "/usr/share/fonts/liberation/LiberationMono-Regular.ttf",               # Fedora/RHEL
    "C:/Windows/Fonts/consola.ttf",                                        # Windows
]
_SURFACE_FONT_CANDIDATES = _CONSOLE_FONT_CANDIDATES


def _setup_fonts():
    """
    Load one font (Menlo — see the _CONSOLE_FONT_CANDIDATES comment above
    for why) and return (surface_font, mono_font) as the *same* font id
    for both — callers bind widgets to either name interchangeably.
    Falls back to (None, None) so DPG's built-in bitmap font is used if
    nothing in the candidate list is found on this system.
    """
    font_path = next((p for p in _CONSOLE_FONT_CANDIDATES
                      if os.path.exists(p)), None)
    if font_path is None:
        return None, None
    try:
        with dpg.font_registry():
            with dpg.font(font_path, 17) as fid:
                font_id = fid
        dpg.bind_font(font_id)
        return font_id, font_id
    except Exception as e:
        print(f"  Font: {e} — using default")
        return None, None


__all__ = [
    "dpg", "_DPG_OK",
    "_C_BG", "_C_PANEL", "_C_BORDER", "_C_TEXT", "_C_DIM", "_C_ACCENT", "_C_HOT",
    "_C_BTN", "_C_BTN_H", "_C_BTN_A", "_C_CUE_ACT", "_C_CUE_WRAP", "_C_SLIDER_G",
    "_C_FPG_ACCENT", "_C_FPG_ACCENT_DIM",
    "_C_P_GROUPS", "_C_P_COLORS", "_C_P_DIMS", "_C_P_CS", "_C_P_CUES", "_C_P_FX",
    "_C_P_FORMS", "_C_P_POSITION", "_C_P_GOBO", "_C_P_ZOOM", "_C_P_FOCUS",
    "_C_P_BEAM", "_C_P_CONTROL",
    "_apply_theme", "_make_go_theme", "_make_fade_bar_theme", "_make_back_theme",
    "_make_alert_btn_theme", "_make_transport_go_theme", "_make_dim_btn_theme",
    "_make_fpg_id_theme", "_make_fpg_id_focused_theme",
    "_make_numpad_digit_theme", "_make_pool_live_theme", "_make_pool_empty_theme",
    "_make_out_moment_theme", "_make_out_vfade_theme", "_make_trig_flash_theme",
    "_make_trig_moment_theme", "_make_pri_hi_theme", "_make_pri_lo_theme",
    "_make_go_btn_theme", "_make_stop_btn_theme",
    "_make_selected_slot_theme",
    "_make_fpg_fader_theme",
    "_CONSOLE_FONT_CANDIDATES", "_SURFACE_FONT_CANDIDATES", "_setup_fonts",
]
