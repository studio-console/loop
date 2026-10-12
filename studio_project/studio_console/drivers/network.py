"""Studio Console sACN network driver — extracted verbatim from studio_project.py
(the NetworkEngine class, formerly part of the "Block 7" section). Pure move,
zero behavior change.
"""

import sacn
import threading
import time


# Wire cadence, in packets per second. Passed to sACNsender(), which uses it
# to pace its own internal UDP thread — that thread, not our staging loop, is
# what actually puts packets on the Ethernet line. The sacn library defaults
# this to 30fps, so without an explicit value the rig was running at 30Hz no
# matter what our loop did. 44Hz is the customary lighting rate and matches
# the rate the FX waveform math assumes.
SACN_FPS = 44

# Our internal staging rate. Deliberately higher than SACN_FPS: this loop
# re-evaluates FX and stages dmx_data into the sender's buffers, so a strobe
# phase boundary is picked up within ~1/STAGING_HZ instead of waiting up to a
# full wire frame (22ms at 44Hz). Faster staging costs nothing — the sender
# still only transmits at SACN_FPS — and it is what keeps strobe transitions
# inside ~10ms of the true phase boundary.
STAGING_HZ = 100


class NetworkEngine:
    """
    sACN multicast broadcast. Staging loop runs at 100Hz on a dedicated
    background thread; packets leave the wire at SACN_FPS (44Hz), paced by
    the sacn library's own internal sender thread.

    This thread is fully isolated from the DearPyGui main thread, so GUI
    render lag cannot stall output. It reads merged DMX from OutputState
    directly (a pure function of live state) rather than accepting frames
    from the main thread — handing frames in would put the expensive FX
    re-evaluation back onto the GUI thread and add a frame of latency.
    """
    def __init__(self, output_state, universes, source_name="Studio Console",
                 broadcast_mode=False, bind_address="", dry_run=False, fx_engine=None):
        self.output_state   = output_state
        self.universes      = universes
        self.source_name    = source_name
        self.broadcast_mode = broadcast_mode
        self.bind_address   = bind_address
        self.dry_run        = dry_run   # True: compute DMX every tick but never open a real socket
        self.fx_engine      = fx_engine # if set, FX is re-evaluated here at send time for accuracy
        self._sender        = None
        self._running       = False
        self._thread        = None
        # Per-universe phase offset, in milliseconds, relative to the wire
        # frame boundary. Placeholder hook for the upcoming UI slider —
        # 0.0 today, meaning no offset. Reserved for fine alignment between
        # daisy-chained fixture groups (e.g. matching LT-200 softbox timing
        # against another fixture type on the same line) where one group
        # reads slightly ahead of or behind the others.
        #
        # Deliberately not applied yet: the sender's packet timing lives in
        # the sacn library's own thread, so honouring a per-universe offset
        # properly needs that send scheduling changed too, not just our
        # staging loop. Wiring it in as-is would silently do nothing.
        self.phase_delay_ms = 0.0

    def start(self):
        if self.dry_run:
            # No real sACN socket — still runs the compute loop below so
            # FX/output logic gets exercised, just nothing goes on the wire.
            self._running = True
            self._thread  = threading.Thread(target=self._run, daemon=True,
                                             name="sacn-staging")
            self._thread.start()
            self._claim_fx_driver()
            print(f"sACN DRY RUN — computing output for universes {self.universes}, nothing sent")
            return
        try:
            if self.bind_address:
                self._sender = sacn.sACNsender(source_name=self.source_name,
                                               bind_address=self.bind_address,
                                               fps=SACN_FPS)
            else:
                self._sender = sacn.sACNsender(source_name=self.source_name,
                                               fps=SACN_FPS)
        except OSError as e:
            print(f"WARNING: sACN port busy ({e}) — running without DMX output.")
            print("  Close any other instance of this console and restart to enable output.")
            # No staging loop will run, so FX would never advance on its own
            # — hand the driving role back to the FX engine's fallback thread.
            if self.fx_engine is not None:
                self.fx_engine.start_background_loop()
            return
        self._sender.start()
        for u in self.universes:
            self._sender.activate_output(u)
            self._sender[u].multicast = True
        self._running = True
        self._thread  = threading.Thread(target=self._run, daemon=True,
                                         name="sacn-staging")
        self._thread.start()
        self._claim_fx_driver()
        if self.broadcast_mode:
            print(f"sACN BROADCAST MODE — same data on universes 1-{len(self.universes)}"
                  f" at {SACN_FPS}Hz")
        else:
            print(f"sACN live — multicast on universes {self.universes} at {SACN_FPS}Hz")

    def _claim_fx_driver(self):
        """Take over FX evaluation from the FX engine's fallback thread.

        Our loop calls fx_engine.compute_merged() at 100Hz, which makes the
        engine's own 44Hz thread pure redundant work — and worse, it
        contends on FXEngine._lock, which we need on the critical path just
        before each send. Exactly one thread should drive it.
        """
        if self.fx_engine is not None:
            self.fx_engine.claim_external_driver()

    def stop(self):
        self._running = False
        thread = self._thread
        if thread is not None and thread.is_alive():
            if thread is not threading.current_thread():
                # Bounded: the loop re-checks the flag every iteration.
                thread.join(timeout=1.0)
        self._thread = None
        if self._sender:
            self._sender.stop()
        print("Network engine stopped.")

    def _run(self):
        # Staging loop at STAGING_HZ. FX is re-evaluated at each tick (not
        # from a cached snapshot) so strobe ON/OFF transitions land within
        # ~10ms of the true phase boundary rather than up to 22ms late (one
        # frame at the 44Hz wire rate). Actual transmission is paced by the
        # sacn library's internal thread at SACN_FPS — this loop only stages
        # dmx_data into its buffers.
        interval = 1.0 / STAGING_HZ
        while self._running:
            now = time.monotonic()
            if self.fx_engine is not None:
                self.fx_engine.compute_merged(now)
            if self.dry_run:
                # Exercise the compute path only — catches exceptions in FX/output
                # resolution without touching a socket.
                if self.broadcast_mode:
                    self.output_state.get_dmx_for_universe(1)
                else:
                    for u in self.universes:
                        self.output_state.get_dmx_for_universe(u)
            elif self.broadcast_mode:
                # Build DMX once from universe 1, send identically to all universes
                dmx = self.output_state.get_dmx_for_universe(1)
                for u in self.universes:
                    self._sender[u].dmx_data = dmx
            else:
                for u in self.universes:
                    self._sender[u].dmx_data = self.output_state.get_dmx_for_universe(u)
            time.sleep(interval)


__all__ = ["NetworkEngine", "SACN_FPS", "STAGING_HZ"]