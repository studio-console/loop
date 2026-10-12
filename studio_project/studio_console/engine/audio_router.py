"""Studio Console audio routing engine — threshold→target triggers.

Part of the audio routing system: binds audio input channels to targets
in GUIEngine.target_registry (the same registry MIDI NOTE mappings use —
"GO stk N CUE M", "fdr N Flash", pool targets, etc), firing the target's
on-callback when the channel's level crosses a user threshold rising,
and its off-callback (when the target has one) when the level falls
back below the re-arm point.

"Input channel" = one of AudioEngine's four analysed bands:
  level — overall RMS loudness
  low   — bass energy     (20-250 Hz)
  mid   — mid energy      (250-4000 Hz)
  high  — treble energy   (4000-20000 Hz)
(AudioEngine captures one mono stream; these bands are its real,
per-band outputs — the router does not pretend the capture is
multichannel.)

Firing model mirrors MIDI note semantics with hysteresis:
  rising edge (level crosses UP past threshold)  → fire on_callback
  level stays above threshold                    → no refire (one shot)
  level falls below threshold * REARM_FACTOR     → fire off_callback (if
                                                   the target has one),
                                                   re-arm for next hit
The hysteresis gap (default 20% of threshold) is what stops a bass drum
that wobbles around the threshold from machine-gunning the target.

Unlike AudioMapper (which free-runs on its own 44 Hz thread), the router
has NO internal thread — tick() is driven externally, from the GUI tick
(_tick_audio_routing) or directly in tests. Deterministic firing order,
nothing to stop at shutdown, and headless tests can drive it by setting
AudioEngine band values and calling tick() directly.
"""


class AudioRoute:
    """One input-channel → target binding.

    channel: 'level' | 'low' | 'mid' | 'high'  (AudioEngine band)
    threshold: 0.0-1.0, rising-edge fire point
    target: registry name (display/listing/persistence)
    on_cb / off_cb: resolved callbacks (None off_cb = momentary target)
    """

    REARM_FACTOR = 0.8   # re-arm below threshold * factor (hysteresis)

    def __init__(self, route_id, channel, threshold, target,
                 on_cb, off_cb=None):
        self.route_id  = route_id
        self.channel   = channel
        self.threshold = max(0.01, min(1.0, float(threshold)))
        self.target    = target
        self.on_cb     = on_cb
        self.off_cb    = off_cb
        self.armed     = True
        self.fires     = 0      # total on-callback fires (GUI/status)

    @property
    def rearm_level(self):
        return self.threshold * self.REARM_FACTOR

    def describe(self):
        state = "armed" if self.armed else "fired"
        return (f"  [{self.route_id}] {self.channel:5s} >= {self.threshold:.2f}"
                f"  → {self.target}   ({state}, {self.fires} fires)")


class AudioRouter:
    """The routing matrix — a set of AudioRoutes, ticked externally.

    add_route() returns the new route_id (int, monotonic) or (None,
    error_reason) for invalid input — the command layer surfaces the
    reason verbatim, same contract as the command handlers.

    tick(audio_engine) reads the four band values and applies rising-
    edge/hysteresis logic per route. Exceptions in a target callback are
    caught and printed (a broken target must not kill the tick loop —
    same policy as the MIDI engine's callback handler).
    """

    CHANNELS = ('level', 'low', 'mid', 'high')

    def __init__(self):
        self.enabled           = False
        self.routes            = {}    # {route_id: AudioRoute}
        self.default_threshold = 0.5   # UI slider feeds this into new routes
        self._next_id          = 1

    # ----------------------------------------------------------
    # Matrix editing
    # ----------------------------------------------------------

    def add_route(self, channel, threshold, target, on_cb, off_cb=None):
        """Add a route. Returns (route_id, None) or (None, error_reason)."""
        if channel not in self.CHANNELS:
            return None, (f"unknown channel '{channel}' — use "
                          f"{', '.join(self.CHANNELS)}")
        if on_cb is None:
            return None, f"target '{target}' has no callback"
        try:
            thr = float(threshold)
        except (TypeError, ValueError):
            return None, f"bad threshold '{threshold}'"
        rid = self._next_id
        self._next_id += 1
        self.routes[rid] = AudioRoute(rid, channel, thr, target, on_cb, off_cb)
        return rid, None

    def remove_route(self, route_id):
        """Remove a route. True if it existed."""
        return self.routes.pop(route_id, None) is not None

    def clear_routes(self):
        self.routes.clear()

    # ----------------------------------------------------------
    # Firing
    # ----------------------------------------------------------

    def tick(self, audio_engine):
        """Advance all routes one frame against the engine's band levels."""
        if not self.enabled:
            return
        for route in self.routes.values():
            level = float(getattr(audio_engine, route.channel, 0.0) or 0.0)
            if route.armed and level >= route.threshold:
                route.armed  = False
                route.fires += 1
                self._fire(route.on_cb, route, 'on')
            elif not route.armed and level < route.rearm_level:
                route.armed = True
                if route.off_cb:
                    self._fire(route.off_cb, route, 'off')

    @staticmethod
    def _fire(cb, route, kind):
        if cb is None:
            return
        try:
            cb()
        except Exception as e:
            print(f"  !! audio route [{route.route_id}] {kind} callback "
                  f"error for '{route.target}': {e}")

    # ----------------------------------------------------------
    # Status
    # ----------------------------------------------------------

    def describe(self):
        """Multi-line listing for the LIST command / GUI tooltip."""
        head = (f"audio routing: {'ON' if self.enabled else 'OFF'}, "
                f"{len(self.routes)} route(s), "
                f"default threshold {self.default_threshold:.2f}")
        if not self.routes:
            return head + "\n  (none — AUDIO ROUTE ADD <ch> <thr> <target>)"
        body = "\n".join(r.describe() for r in
                         sorted(self.routes.values(), key=lambda r: r.route_id))
        return head + "\n" + body


__all__ = ["AudioRoute", "AudioRouter"]
