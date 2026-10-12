"""GUIEngine's Audio Control & Routing window.

Part of the audio routing system — device selector, master gain +
threshold, a live level meter, and the routing matrix table (input
band → target, the same target namespace MIDI NOTE mappings use).

Follows the audio_window/midi popup conventions from audio_monitors.py
and hardware_popups.py: built hidden, toggled from the header, all DPG
access wrapped so headless/no-audio environments construct cleanly.

The level meter is a drawlist (not progress bars) because the routing
matrix needs the THRESHOLD visible against the live level — a marker
line across the meter is what makes "is my threshold in the right
place?" answerable at a glance, which bars alone can't do.
"""

from studio_console.gui.theme import *  # noqa: F401,F403
from studio_console.drivers.audio import _AUDIO_AVAILABLE, sd


class GUIEngineAudioRouting:
    def _on_audio_routing_toggle(self):
        try:
            if dpg.is_item_shown("audio_routing_window"):
                self._save_popup_layout()
                dpg.hide_item("audio_routing_window")
            else:
                dpg.show_item("audio_routing_window")
                self._on_ar_routing_window_show()
        except Exception:
            pass

    # ----------------------------------------------------------
    # Device / capture controls (drive the shared AudioEngine)
    # ----------------------------------------------------------

    def _ar_refresh_devices(self):
        """Re-populate the device combo from live hardware."""
        names = []
        if _AUDIO_AVAILABLE:
            try:
                names = [f"[{i}] {d['name']}" for i, d in
                         enumerate(sd.query_devices())
                         if d['max_input_channels'] > 0]
            except Exception:
                names = []
        try:
            dpg.configure_item("ar_device_combo", items=names)
            if names and not dpg.get_value("ar_device_combo"):
                dpg.set_value("ar_device_combo", names[0])
        except Exception:
            pass

    def _on_ar_device_refresh(self):
        self._ar_refresh_devices()

    def _on_ar_start(self):
        if not self._audio_engine:
            return
        device = None
        try:
            label = dpg.get_value("ar_device_combo")
            if label and _AUDIO_AVAILABLE:
                device = int(label.split("]")[0].lstrip("["))
        except Exception:
            device = None
        try:
            self._audio_engine.start(device=device)
            dpg.set_value("ar_status", "capturing")
            dpg.configure_item("ar_status", color=_C_ACCENT)
        except Exception as e:
            dpg.set_value("ar_status", f"error: {e}")
            dpg.configure_item("ar_status", color=[255, 80, 80, 220])

    def _on_ar_stop(self):
        if not self._audio_engine:
            return
        self._audio_engine.stop()
        try:
            dpg.set_value("ar_status", "stopped")
            dpg.configure_item("ar_status", color=_C_DIM)
        except Exception:
            pass

    def _on_ar_gain(self, sender, value):
        if self._audio_engine:
            self._audio_engine.gain = value

    def _on_ar_threshold(self, sender, value):
        """Master threshold slider — feeds new routes + the meter line."""
        if self._audio_router:
            self._audio_router.default_threshold = value

    def _on_ar_routing_enable(self, sender, value):
        if self._audio_router:
            self._audio_router.enabled = bool(value)

    # ----------------------------------------------------------
    # Level meter — drawlist bars + threshold marker
    # ----------------------------------------------------------

    # Pre-created meter primitives — fixed slots, exactly like viz3d's
    # grid lines: 4 bands × (1 trough + 1 fill + 1 threshold line).
    # Per-tick updates only reconfigure coordinates via _meter_set_*,
    # so the drawlist is never rebuilt at runtime (no flicker, and no
    # dynamic-item creation inside the tick path).
    _METER_BANDS = ("level", "low", "mid", "high")

    def _tick_audio_routing_meter(self):
        """Redraw the meter: 4 band bars + threshold marker line."""
        if not self._audio_engine:
            return
        try:
            # Canvas rect size. Before the first layout pass — and forever,
            # in headless mode, where no frame is ever laid out —
            # get_item_rect_size() reports 0x0, so fall back to the
            # drawlist's configured size instead of dividing by zero into
            # a degenerate row_h.
            w, h = dpg.get_item_rect_size("ar_meter_canvas")
            if not w or not h:
                _cfg = dpg.get_item_configuration("ar_meter_layer")
                w = _cfg.get("width") or 520
                h = _cfg.get("height") or 120
            bands = (("level", self._audio_engine.level),
                     ("low",   self._audio_engine.low),
                     ("mid",   self._audio_engine.mid),
                     ("high",  self._audio_engine.high))
            row_h = h / 4.0
            thr = (self._audio_router.default_threshold
                   if self._audio_router else 0.5)
            # Update only the 12 fixed primitives in place — never
            # delete/recreate or add labels to ar_meter_layer, which
            # must stay at exactly 12 children for the smoke test.
            #
            # These MUST be configure_item() calls, not draw_*() calls: a
            # draw_* with a tag but no parent= and no enclosing `with
            # dpg.drawlist(...)` raises SystemError *and* deregisters the
            # existing item, so the pre-built primitives vanish on the
            # first tick and the meter goes permanently blank (the
            # SystemError being swallowed by the except below, which is
            # how this stayed invisible until the smoke check for it).
            for i, (name, val) in enumerate(bands):
                y0 = i * row_h + 2
                y1 = (i + 1) * row_h - 2
                # trough (fixed slot)
                dpg.configure_item(f"ar_meter_trough_{i}",
                                   pmin=(60, y0), pmax=(w - 8, y1))
                # live level fill (fixed slot). The slot always exists, so
                # an inaudible band has to be collapsed to zero width
                # explicitly rather than left holding a stale bar.
                fill_w = max(0.0, (w - 68) * min(1.0, val))
                dpg.configure_item(
                    f"ar_meter_fill_{i}",
                    pmin=(60, y0),
                    pmax=(60 + (fill_w if fill_w > 1.0 else 0.0), y1),
                    fill=(_C_HOT if val >= thr else _C_ACCENT))
                # threshold marker line (fixed slot)
                mx = 60 + (w - 68) * thr
                dpg.configure_item(f"ar_meter_marker_{i}",
                                   p1=(mx, y0), p2=(mx, y1))
                # labels are separate widgets inside ar_meter_canvas
                dpg.set_value(f"ar_meter_label_{i}", name)
                dpg.set_value(f"ar_meter_value_{i}", f"{val:.2f}")
        except Exception:
            pass

    # ----------------------------------------------------------
    # Routing table
    # ----------------------------------------------------------

    def _tick_audio_routing_table(self):
        """Rebuild table rows when the route set changes."""
        if not self._audio_router:
            return
        sig = (len(self._audio_router.routes),
               tuple(sorted((r.channel, r.threshold, r.target, r.armed,
                             r.fires) for r in
                            self._audio_router.routes.values())))
        if sig == getattr(self, "_ar_table_sig", None):
            return
        self._ar_table_sig = sig
        try:
            dpg.delete_item("ar_routes_body", children_only=True)
            for r in sorted(self._audio_router.routes.values(),
                            key=lambda r: r.route_id):
                with dpg.group(horizontal=True, parent="ar_routes_body"):
                    dpg.add_text(f"{r.route_id}", color=_C_DIM)
                    dpg.add_text(f"{r.channel}", color=_C_ACCENT)
                    dpg.add_text(f"{r.threshold:.2f}")
                    dpg.add_text(r.target)
                    dpg.add_text("fired" if not r.armed else "armed",
                                 color=(_C_HOT if not r.armed else _C_DIM),
                                 width=54)
                    dpg.add_text(f"{r.fires}", color=_C_DIM)
                    dpg.add_button(label="×", width=24,
                                   user_data=r.route_id,
                                   callback=self._on_ar_route_remove)
        except Exception:
            pass

    def _on_ar_route_remove(self, sender, app_data, user_data):
        if self._audio_router and self._audio_router.remove_route(user_data):
            from studio_console.show import ShowFile
            ShowFile.save_audio_routes(self._audio_router)

    def _on_ar_route_add(self):
        """Add-row button: resolve target from the registry (same as MIDI)."""
        # Deferred import — GUIEngine is defined in studio_project.py
        # after this module loads; same pattern as hardware_popups.py.
        from __main__ import GUIEngine, run_command
        if not self._audio_router:
            return
        try:
            channel = dpg.get_value("ar_add_channel")
            thr     = dpg.get_value("ar_add_threshold")
            target  = dpg.get_value("ar_add_target")
        except Exception:
            return
        entry = GUIEngine.target_registry.get(target)
        if not entry:
            try:
                dpg.set_value("ar_add_status", "target not found")
            except Exception:
                pass
            return
        off_cb = entry[3] if len(entry) > 3 else None
        rid, err = self._audio_router.add_route(channel, thr, target,
                                                entry[0], off_cb)
        try:
            if err:
                dpg.set_value("ar_add_status", err)
            else:
                from studio_console.show import ShowFile
                ShowFile.save_audio_routes(self._audio_router)
                dpg.set_value("ar_add_status", f"route {rid} added")
        except Exception:
            pass

    def _on_ar_routing_window_show(self):
        """Refresh target combo + device list when the window opens."""
        # Deferred import — see _on_ar_route_add.
        from __main__ import GUIEngine
        try:
            names = sorted(GUIEngine.target_registry.keys())
            dpg.configure_item("ar_add_target", items=names)
            if names:
                dpg.set_value("ar_add_target", names[0])
        except Exception:
            pass
        self._ar_refresh_devices()

    # ----------------------------------------------------------
    # Tick + build
    # ----------------------------------------------------------

    def _tick_audio_routing(self):
        """Drive the router + refresh the window (called from _tick).

        This is where the routing matrix actually fires: the router has
        no thread of its own (see engine/audio_router.py docstring), so
        this GUI tick is the pump. Headless smoke tests drive tick()
        directly instead.
        """
        if self._audio_router and self._audio_engine:
            self._audio_router.tick(self._audio_engine)
        if not dpg.is_item_shown("audio_routing_window"):
            return
        self._tick_audio_routing_meter()
        self._tick_audio_routing_table()

    def _build_audio_routing_popup(self):
        """Audio Control & Routing window — device/master controls, live
        meter with threshold markers, and the routing matrix table."""
        with dpg.window(tag="audio_routing_window",
                        label="audio control & routing",
                        width=560, height=520, show=False, pos=(300, 150)):
            dpg.add_text("audio control & routing", color=_C_ACCENT)
            dpg.add_separator()

            # ── device + transport ───────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("device:", color=_C_DIM)
                dpg.add_combo(tag="ar_device_combo", items=[], width=300)
                dpg.add_button(label="↻", width=26,
                               callback=self._on_ar_device_refresh)
            with dpg.group(horizontal=True):
                dpg.add_button(label="start capture", width=110,
                               callback=self._on_ar_start)
                dpg.add_button(label="stop", width=60,
                               callback=self._on_ar_stop)
                dpg.add_text("stopped", tag="ar_status", color=_C_DIM)
            dpg.add_drag_float(tag="ar_gain", label="gain",
                               default_value=(self._audio_engine.gain
                                              if self._audio_engine else 3.0),
                               min_value=0.1, max_value=20.0, speed=0.1,
                               format="%.1f", width=240,
                               callback=self._on_ar_gain)
            dpg.add_drag_float(tag="ar_threshold", label="threshold",
                               default_value=(self._audio_router.default_threshold
                                              if self._audio_router else 0.5),
                               min_value=0.01, max_value=1.0, speed=0.01,
                               format="%.2f", width=240,
                               callback=self._on_ar_threshold)

            # ── level meter ──────────────────────────────────
            dpg.add_separator()
            dpg.add_text("input levels (marker = threshold)", color=_C_DIM)
            with dpg.child_window(tag="ar_meter_canvas",
                                  width=520, height=120, border=False):
                with dpg.drawlist(tag="ar_meter_layer", width=520, height=120):
                    for b in range(4):
                        dpg.draw_rectangle((0, 0), (0, 0),
                                           color=_C_BORDER,
                                           fill=_C_PANEL,
                                           tag=f"ar_meter_trough_{b}")
                        dpg.draw_rectangle((0, 0), (0, 0),
                                           fill=(_C_HOT if b == 0
                                                 else _C_ACCENT),
                                           color=(0, 0, 0, 0),
                                           tag=f"ar_meter_fill_{b}")
                        dpg.draw_line((0, 0), (0, 0),
                                      color=[255, 120, 120, 200],
                                      thickness=1,
                                      tag=f"ar_meter_marker_{b}")
                # band labels + values (separate widgets, 1 per band)
                for i in range(4):
                    with dpg.group(horizontal=True):
                        dpg.add_text("", tag=f"ar_meter_label_{i}", color=_C_DIM)
                        dpg.add_text("", tag=f"ar_meter_value_{i}", color=_C_DIM)

            # ── routing matrix ───────────────────────────────
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_text("", color=_C_DIM)
            with dpg.group(horizontal=True):
                dpg.add_text("ch", color=_C_DIM)
                dpg.add_combo(items=list(
                    self._audio_router.CHANNELS) if self._audio_router
                    else ["level", "low", "mid", "high"],
                    tag="ar_add_channel", default_value="low", width=80)
                dpg.add_text("thr", color=_C_DIM)
                dpg.add_slider_float(tag="ar_add_threshold",
                                     default_value=(self._audio_router.
                                                    default_threshold
                                                    if self._audio_router
                                                    else 0.5),
                                     min_value=0.01, max_value=1.0,
                                     width=120)
                dpg.add_text("→", color=_C_DIM)
                dpg.add_combo(items=[], tag="ar_add_target", width=180)
                dpg.add_button(label="add", width=50,
                               callback=lambda: self._on_ar_route_add())
            dpg.add_text("", tag="ar_add_status", color=_C_ACCENT)
            with dpg.group(horizontal=True):
                for _lbl, _w in (("id", 28), ("ch", 60), ("thr", 52),
                                 ("target", 200), ("state", 54),
                                 ("fires", 44)):
                    dpg.add_text(_lbl, color=_C_DIM)
                dpg.add_text("")
            dpg.add_child_window(tag="ar_routes_body", height=160,
                                 width=-1, border=True)
            dpg.add_text("fires on rising threshold crossing; re-arms below "
                         "80% of threshold (hysteresis)", color=_C_DIM,
                         wrap=520)


__all__ = ["GUIEngineAudioRouting"]
