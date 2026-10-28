"""Encoder bar popup - recovered from cached bytecode."""
import dearpygui.dearpygui as dpg

try:
    from studio_console.gui.theme import *
except Exception:
    pass

_C_DIM = globals().get("_C_DIM", (95, 74, 148))
_C_TEXT = globals().get("_C_TEXT", (220, 210, 240))
_C_ACCENT = globals().get("_C_ACCENT", (162, 115, 255))
_C_P_POSITION = globals().get("_C_P_POSITION", _C_ACCENT)
_C_P_GOBO = globals().get("_C_P_GOBO", _C_ACCENT)
_C_P_ZOOM = globals().get("_C_P_ZOOM", _C_ACCENT)
_C_P_FOCUS = globals().get("_C_P_FOCUS", _C_ACCENT)
_C_P_BEAM = globals().get("_C_P_BEAM", _C_ACCENT)
_C_P_CONTROL = globals().get("_C_P_CONTROL", _C_ACCENT)


class GUIEngineEncoderBar:
    _ENCODER_ITEMS = [
        {"label": "DIM", "color": None, "key": "dim", "default": 0, "is_dim": True, "keyword": "DIM"},
        {"label": "R", "color": (255, 80, 80), "key": "r", "default": 0, "is_dim": False, "keyword": "R"},
        {"label": "G", "color": (80, 255, 80), "key": "g", "default": 0, "is_dim": False, "keyword": "G"},
        {"label": "B", "color": (80, 80, 255), "key": "b", "default": 0, "is_dim": False, "keyword": "B"},
        {"label": "W", "color": (220, 220, 220), "key": "w", "default": 0, "is_dim": False, "keyword": "W"},
        {"label": "PAN", "color": None, "key": "pan", "default": 0, "is_dim": False, "keyword": "PAN"},
        {"label": "TILT", "color": None, "key": "tilt", "default": 0, "is_dim": False, "keyword": "TILT"},
    ]

    def _encoder_item(self, key):
        for it in self._ENCODER_ITEMS:
            if it["key"] == key:
                return it
        return None

    def _build_encoder_bar_popup(self):
        try:
            with dpg.window(tag="encoder_bar_window", label="encoder bar",
                            width=1920, height=520, show=False,
                            pos=(10, 80), no_collapse=False):
                dpg.add_text(
                    "encoder bar - pool items (sliders 0-100). Drag to set the "
                    "selected fixtures; values convert to the channel's native "
                    "range. Extend _ENCODER_ITEMS to add more.",
                    color=_C_DIM, wrap=1140)
                dpg.add_separator()
                with dpg.group(horizontal=True):
                    for spec in self._ENCODER_ITEMS:
                        with dpg.group():
                            dpg.add_text(spec["label"],
                                         color=spec.get("color") or _C_TEXT)
                            dpg.add_slider_int(
                                tag="enc_slider_" + spec["key"],
                                default_value=int(spec.get("default", 0)),
                                min_value=0, max_value=100, width=56,
                                callback=self._on_encoder_change,
                                user_data=spec["key"])
                try:
                    from __main__ import _prog_fade
                    _pf = _prog_fade
                except Exception:
                    _pf = {"time": 2.0, "on": False}
                _pf_default = float(_pf.get("time", 2.0) or 2.0)
                _pf_default = max(0.1, min(10.0, _pf_default))
                _pf_on = bool(_pf.get("on", False))
                dpg.add_text("programmer fade - plain AT edits fade in/out",
                             color=_C_ACCENT)
                with dpg.group(horizontal=True):
                    dpg.add_text("fade time", color=_C_DIM)
                    dpg.add_slider_float(
                        tag="enc_prog_fade_time",
                        default_value=_pf_default, min_value=0.1,
                        max_value=10.0, width=220, format="%.1fs",
                        callback=self._on_enc_prog_fade_time_change)
                    dpg.add_spacer(width=8)
                    dpg.add_button(
                        label=("● fade on" if _pf_on else "○ fade off"),
                        tag="enc_prog_fade_toggle", width=90, height=20,
                        callback=self._on_pf_toggle)
                dpg.add_separator()
                dpg.add_text("attribute pools - recall / record",
                             color=_C_ACCENT)
                with dpg.group(horizontal=True):
                    self._build_attr_pool_panel("position", _C_P_POSITION,
                                                "enc_pos", "enc_pos")
                    self._build_attr_pool_panel("gobo", _C_P_GOBO,
                                                "enc_gobo", "enc_gobo")
                    self._build_attr_pool_panel("zoom", _C_P_ZOOM,
                                                "enc_zoom", "enc_zoom")
                with dpg.group(horizontal=True):
                    self._build_attr_pool_panel("focus", _C_P_FOCUS,
                                                "enc_focus", "enc_focus")
                    self._build_attr_pool_panel("beam", _C_P_BEAM,
                                                "enc_beam", "enc_beam")
                    self._build_attr_pool_panel("control", _C_P_CONTROL,
                                                "enc_ctrl", "enc_ctrl")
        except Exception:
            pass

    def _on_encoder_bar_toggle(self, sender=None, app_data=None, user_data=None):
        try:
            import dearpygui.dearpygui as dpg
            if dpg.is_item_shown("encoder_bar_window"):
                dpg.hide_item("encoder_bar_window")
            else:
                dpg.show_item("encoder_bar_window")
                self._save_popup_layout()
        except Exception:
            pass
    def _on_encoder_change(self, sender, app_data, user_data):
        try:
            spec = self._encoder_item(user_data)
            if spec is None:
                return
            val = float(app_data)
            val = max(0.0, min(100.0, val))
            if not getattr(self, "_cmd", None):
                return
            if spec.get("is_dim"):
                self._cmd("DIM " + str(int(round(val))))
                return
            cv = int(round(val / 100.0 * 255.0))
            self._cmd("%s %s" % (spec["keyword"], cv))
        except (TypeError, ValueError):
            return
        except Exception:
            return

    def _on_enc_prog_fade_time_change(self, sender, app_data, user_data=None):
        try:
            val = float(app_data)
            val = max(0.1, min(10.0, val))
            from __main__ import _prog_fade
            _prog_fade["time"] = val
            _prog_fade["on"] = True
            if getattr(self, "_cmd", None):
                self._cmd("PROG FADE %.1f" % val)
            import dearpygui.dearpygui as dpg
            dpg.configure_item("enc_prog_fade_toggle", label="● fade on")
            dpg.configure_item("sb_pf_lbl", label="● fade")
        except (TypeError, ValueError):
            return
        except Exception:
            return
