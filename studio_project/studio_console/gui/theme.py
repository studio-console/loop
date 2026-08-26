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
    """Transparent-track slider theme for the fader-page grid's touch faders.

    The slider itself stays the real interactive widget (tap-anywhere-then-
    drag is native ImGui/DPG slider behavior, no custom hit-testing needed)
    but its own frame is made fully transparent so it can sit directly on
    top of a hand-drawn fill rectangle (see fader_page.py's fpg_faderfill_*)
    without painting over it. The grab is a thin bright line, not a knob —
    the drawn fill's top edge is the real level indicator.
    """
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvSliderInt):
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg,          (0, 0, 0, 0))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered,   (0, 0, 0, 0))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive,    (0, 0, 0, 0))
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrab,       (230, 210, 255, 220))
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive, (255, 255, 255, 255))
            dpg.add_theme_style(dpg.mvStyleVar_GrabMinSize, 10)
            dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 0)
    return t


def _make_dim_btn_theme():
    """Dimmed/inactive button style for toggleable status indicators."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (30, 24, 50, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (50, 40, 80, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (70, 55, 110, 255))
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


def _make_active_slot_theme():
    """Brighter border for a slot that has a live cue playing."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvChildWindow):
            dpg.add_theme_color(dpg.mvThemeCol_Border,       (162, 115, 255, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg,      (22, 16, 48, 255))
    return t


_CONSOLE_FONT_CANDIDATES = [
    "/System/Library/Fonts/SFNSMono.ttf",                                   # macOS
    "/System/Library/Fonts/Menlo.ttc",                                      # macOS (Alt)
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",                  # Debian/Ubuntu
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",      # Debian/Ubuntu (RPM-derived)
    "/usr/share/fonts/liberation/LiberationMono-Regular.ttf",               # Fedora/RHEL
    "C:/Windows/Fonts/consola.ttf",                                        # Windows
]

# Clean humanist sans-serif used for labels/headers/buttons (the "surface" text).
# Mono stays on the actual console data + command line so those columns align.
_SURFACE_FONT_CANDIDATES = [
    "/System/Library/Fonts/Avenir.ttc",                                     # macOS Avenir (chosen look)
    "/System/Library/Fonts/Avenir Next.ttc",                                # macOS Avenir Next
    "/System/Library/Fonts/SFCompact.ttc",                                  # macOS SF Compact
    "/System/Library/Fonts/SFCompactRounded.ttf",                           # macOS SF Compact Rounded
    "/System/Library/Fonts/HelveticaNeue.ttc",                              # macOS Helvetica Neue
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",                      # Debian/Ubuntu
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",      # Debian/Ubuntu (RPM-derived)
    "C:/Windows/Fonts/arial.ttf",                                          # Windows
]


def _setup_fonts():
    """
    Load a two-tier font system and return (surface_font, mono_font).

      surface_font — clean sans-serif for labels/headers/buttons (the modern
                     "graph" text). If none found, falls back to None so DPG's
                     built-in bitmap font is used (caller decides).
      mono_font    — monospace for console data + command line. Falls back to
                     the surface font (or None) if no mono is available.

    Both fonts are loaded into the same registry in one block so glyph ranges
    are sized automatically (add_font_range/add_font_range_hint are deprecated
    no-ops in DPG 2.3.1).
    """
    surface_path = next((p for p in _SURFACE_FONT_CANDIDATES
                         if os.path.exists(p)), None)
    mono_path    = next((p for p in _CONSOLE_FONT_CANDIDATES
                         if os.path.exists(p)), None)
    if surface_path is None and mono_path is None:
        return None, None
    try:
        with dpg.font_registry():
            surface_id = None
            if surface_path is not None:
                with dpg.font(surface_path, 17) as fid:
                    surface_id = fid
            mono_id = None
            if mono_path is not None:
                with dpg.font(mono_path, 17) as fid:
                    mono_id = fid
        # Default (graph) text = surface font; data/console widgets will be
        # bound to the mono font selectively by the caller.
        if surface_id is not None:
            dpg.bind_font(surface_id)
        # If we have a mono font but no surface, fall back to mono for the
        # default text too (keeps behaviour identical to the old all-mono UI).
        if surface_id is None and mono_id is not None:
            dpg.bind_font(mono_id)
        return surface_id, mono_id
    except Exception:
        return None, None
    except Exception as e:
        print(f"  Font: {e} — using default")
        return None


__all__ = [
    "dpg", "_DPG_OK",
    "_C_BG", "_C_PANEL", "_C_BORDER", "_C_TEXT", "_C_DIM", "_C_ACCENT", "_C_HOT",
    "_C_BTN", "_C_BTN_H", "_C_BTN_A", "_C_CUE_ACT", "_C_SLIDER_G",
    "_C_P_GROUPS", "_C_P_COLORS", "_C_P_DIMS", "_C_P_CS", "_C_P_CUES", "_C_P_FX",
    "_C_P_FORMS", "_C_P_POSITION", "_C_P_GOBO", "_C_P_ZOOM", "_C_P_FOCUS",
    "_C_P_BEAM", "_C_P_CONTROL",
    "_apply_theme", "_make_go_theme", "_make_fade_bar_theme", "_make_back_theme",
    "_make_alert_btn_theme", "_make_transport_go_theme", "_make_dim_btn_theme",
    "_make_numpad_digit_theme", "_make_pool_live_theme", "_make_pool_empty_theme",
    "_make_out_moment_theme", "_make_out_vfade_theme", "_make_trig_flash_theme",
    "_make_trig_moment_theme", "_make_pri_hi_theme", "_make_pri_lo_theme",
    "_make_go_btn_theme", "_make_stop_btn_theme", "_make_active_slot_theme",
    "_make_fpg_fader_theme",
    "_CONSOLE_FONT_CANDIDATES", "_SURFACE_FONT_CANDIDATES", "_setup_fonts",
]
