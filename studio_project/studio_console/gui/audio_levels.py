"""GUIEngine's nestable input-device + raw-peak level panel.

Part of the GUIEngine mixin split — see studio_project.py for how this
combines with the other gui/*.py mixins into the final GUIEngine class via
multiple inheritance.

Unlike gui/audio_monitors.py (the "audio reactive" window's own level bars)
and gui/audio_routing.py (the 4-band routing meter), this is a compact,
re-usable BODY: a single group tagged ``al_panel`` holding an input-device
picker, start/stop, gain, a live status line, and a single un-processed
raw-peak meter driven straight off ``AudioEngine.raw_peak``. It is built
into the audio window at construction time (see
GUIEngineAudioMonitors._build_audio_popup), but because it is just a
stable-tagged group it can be re-parented at runtime with
``dpg.move_item("al_panel", parent=...)`` — e.g. into a future master
settings window — with no rebuild.

Why raw_peak and not level/low/mid/high: those four are enveloped and
band-split for driving lights, which hides real input-gain headroom. When
you are setting an interface's input gain you want the un-processed signal,
so this meter reads AudioEngine.raw_peak directly (see drivers/audio.py).
"""

from studio_console.gui.theme import *  # noqa: F401,F403
from studio_console.drivers.audio import _AUDIO_AVAILABLE, sd


class GUIEngineAudioLevels:
    # Width/height of the raw-peak drawlist. The meter tick reads these
    # back out of get_item_configuration() as a fallback when
    # get_item_rect_size() reports 0x0 (headless mode / pre-layout).
    _AL_W = 300
    _AL_H = 22

    # ----------------------------------------------------------
    # Build
    # ----------------------------------------------------------

    def _build_audio_levels_panel(self, parent=None):
        """Build the nestable device + raw-peak panel into ``parent``.

        ``parent=None`` drops it into whatever group is active (the audio
        window body calls this with no parent, inside a `with` block).
        Everything lives under a single stable-tagged group so the whole
        panel can be moved later without a rebuild.
        """
        # Only pass `parent` when one is given: real DearPyGui requires
        # parent to be an int (internal item UUID) if supplied at all, and
        # explicitly passing parent=None raises "[1008] Must be int" —
        # which then cascades into "[1009] No container to pop" in the
        # enclosing dpg.window. Omitting the kwarg lets DPG drop the group
        # into whatever container is active. (The headless smoke test's fake
        # dpg tolerates parent=None, so this only bites a real launch.)
        _panel_kwargs = {"tag": "al_panel"}
        if parent is not None:
            _panel_kwargs["parent"] = parent
        with dpg.group(**_panel_kwargs):
            dpg.add_text("input device + raw peak", color=_C_ACCENT)

            # ── device pick ────────────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("device:", color=_C_DIM)
                # Guarded query — with no backend / no hardware this stays
                # an empty list, and the combo still exists (the smoke test
                # asserts items is a list/tuple even when empty).
                _al_names = self._al_query_devices()
                dpg.add_combo(tag="al_device_combo", items=_al_names,
                              default_value=(_al_names[0] if _al_names else ""),
                              width=200)
                dpg.add_button(label="↻", tag="al_device_refresh", width=24,
                               callback=self._on_al_refresh_devices)

            # ── capture + gain ─────────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_button(label="start", tag="al_start", width=70,
                               callback=self._on_al_start)
                dpg.add_button(label="stop", tag="al_stop", width=70,
                               callback=self._on_al_stop)
                dpg.add_text("", tag="al_status", color=_C_DIM)
            # add_drag_float, not add_slider_float: `speed` is a drag-float
            # keyword (add_slider_float has no speed= and raises "[1000]
            # speed keyword does not exist"). Matches the gain control in
            # audio_monitors.py's audio popup. (The headless fake dpg ignores
            # unknown kwargs, so only a real launch hits this.)
            dpg.add_drag_float(
                tag="al_gain", label="gain",
                default_value=(self._audio_engine.gain
                               if self._audio_engine else 3.0),
                min_value=0.1, max_value=20.0, speed=0.1,
                format="%.1f", width=self._AL_W,
                callback=self._on_al_gain)

            # ── raw-peak meter ─────────────────────────────
            # Exactly 3 fixed primitives in the drawlist, reconfigured in
            # place every tick — never delete/recreate or add a 4th. See
            # the _tick_audio_levels_meter docstring for why these MUST be
            # configure_item() and not draw_*().
            with dpg.group(horizontal=True):
                dpg.add_text("raw", color=_C_DIM)
                dpg.add_text("", tag="al_peak_value", color=_C_ACCENT)
                dpg.add_text("", tag="al_peak_clip", color=[255, 80, 80, 220])
            with dpg.drawlist(tag="al_meter_layer", width=self._AL_W,
                              height=self._AL_H):
                dpg.draw_rectangle((0, 0), (0, 0),
                                   color=_C_BORDER, fill=_C_PANEL,
                                   tag="al_meter_trough")
                dpg.draw_rectangle((0, 0), (0, 0),
                                   fill=_C_ACCENT, color=(0, 0, 0, 0),
                                   tag="al_meter_fill")
                # Clip-hold marker: a thin full-height line pinned to the
                # right edge, only shown when raw_peak is at full scale.
                dpg.draw_line((0, 0), (0, 0),
                              color=[255, 80, 80, 220], thickness=2,
                              tag="al_meter_clip")

    def _al_query_devices(self):
        """Input-device name list, safe with no backend / no hardware."""
        if not (self._audio_engine and _AUDIO_AVAILABLE):
            return []
        try:
            return [d['name'] for d in sd.query_devices()
                    if d['max_input_channels'] > 0]
        except Exception:
            return []

    # ----------------------------------------------------------
    # Callbacks
    # ----------------------------------------------------------

    def _on_al_refresh_devices(self):
        """Re-populate the device combo from a fresh (guarded) query."""
        try:
            names = self._al_query_devices()
            dpg.configure_item("al_device_combo", items=names)
            if names:
                dpg.set_value("al_device_combo", names[0])
        except Exception:
            pass

    def _al_selected_device(self):
        """Resolve the combo's device name to an index (None = default)."""
        try:
            name = dpg.get_value("al_device_combo")
        except Exception:
            return None
        if name and _AUDIO_AVAILABLE:
            try:
                for i, d in enumerate(sd.query_devices()):
                    if d['name'] == name and d['max_input_channels'] > 0:
                        return i
            except Exception:
                pass
        return None

    def _on_al_start(self):
        if not self._audio_engine:
            return
        try:
            self._audio_engine.start(device=self._al_selected_device())
            dpg.set_value("al_status", "capturing")
            dpg.configure_item("al_status", color=_C_ACCENT)
        except Exception as e:
            dpg.set_value("al_status", f"error: {e}")
            dpg.configure_item("al_status", color=[255, 80, 80, 220])

    def _on_al_stop(self):
        if not self._audio_engine:
            return
        try:
            self._audio_engine.stop()
        except Exception:
            pass
        try:
            dpg.set_value("al_status", "stopped")
            dpg.configure_item("al_status", color=_C_DIM)
        except Exception:
            pass

    def _on_al_gain(self, sender, value):
        if self._audio_engine:
            self._audio_engine.gain = value

    # ----------------------------------------------------------
    # Tick
    # ----------------------------------------------------------

    def _tick_audio_levels(self):
        """Full tick (called from GUIEngineCore._tick).

        The meter half is split into _tick_audio_levels_meter() and gated
        behind is_item_shown("audio_window") here, matching the _tick_audio()
        split — but the meter test drives that half directly since the popup
        is built show=False, so only calling it exercises the draw path.
        """
        if not self._audio_engine:
            return
        if not dpg.is_item_shown("audio_window"):
            return
        self._tick_audio_levels_meter()

    def _tick_audio_levels_meter(self):
        """Redraw the raw-peak meter from AudioEngine.raw_peak.

        Only 3 fixed primitives, reconfigured in place every tick — the
        drawlist must stay at exactly 3 children.

        These MUST be configure_item() calls, not draw_*() calls: a
        draw_* with a tag but no parent= and no enclosing `with
        dpg.drawlist(...)` raises SystemError *and* deregisters the
        existing item, so the pre-built primitives vanish on the first tick
        and the meter goes permanently blank (the SystemError being
        swallowed by the except below, which is how this stayed invisible
        until the smoke check for it). Same trap audio_routing.py's meter
        already documents.
        """
        if not self._audio_engine:
            return
        try:
            peak = float(getattr(self._audio_engine, "raw_peak", 0.0) or 0.0)
            peak = max(0.0, min(1.0, peak))
            clipping = peak >= 0.999

            # Canvas size — fall back to the drawlist's configured size
            # when get_item_rect_size() reports 0x0 (headless / pre-layout).
            w, h = dpg.get_item_rect_size("al_meter_layer")
            if not w or not h:
                _cfg = dpg.get_item_configuration("al_meter_layer")
                w = _cfg.get("width") or self._AL_W
                h = _cfg.get("height") or self._AL_H

            pad = 2
            y0, y1 = pad, h - pad
            x1 = int(w - pad)

            # trough (fixed slot)
            dpg.configure_item("al_meter_trough",
                               pmin=(pad, y0), pmax=(x1, y1))
            # fill (fixed slot). Always reconfigured so the bar collapses
            # to zero width on silence rather than holding a stale bar.
            fill_x = pad + int((x1 - pad) * peak)
            if fill_x <= pad:
                fill_x = pad
            dpg.configure_item("al_meter_fill",
                               pmin=(pad, y0), pmax=(fill_x, y1),
                               fill=([255, 80, 80, 220] if clipping
                                     else _C_ACCENT))
            # clip marker (fixed slot): pinned to the right edge, full
            # height, only drawn when at full scale.
            if clipping:
                dpg.configure_item("al_meter_clip",
                                   p1=(x1, y0), p2=(x1, y1))
            else:
                dpg.configure_item("al_meter_clip",
                                   p1=(0, 0), p2=(0, 0))

            dpg.set_value("al_peak_value", f"{peak:.2f}")
            dpg.set_value("al_peak_clip", "CLIP" if clipping else "")
        except Exception:
            pass

