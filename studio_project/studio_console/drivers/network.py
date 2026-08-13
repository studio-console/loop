"""Studio Console sACN network driver — extracted verbatim from studio_project.py
(the NetworkEngine class, formerly part of the "Block 7" section). Pure move,
zero behavior change.
"""

import sacn
import threading
import time


class NetworkEngine:
    """
    sACN multicast broadcast loop at 44Hz.
    Reads merged DMX values from OutputState every frame.
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

    def start(self):
        if self.dry_run:
            # No real sACN socket — still runs the compute loop below so
            # FX/output logic gets exercised, just nothing goes on the wire.
            self._running = True
            self._thread  = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            print(f"sACN DRY RUN — computing output for universes {self.universes}, nothing sent")
            return
        try:
            if self.bind_address:
                self._sender = sacn.sACNsender(source_name=self.source_name,
                                               bind_address=self.bind_address)
            else:
                self._sender = sacn.sACNsender(source_name=self.source_name)
        except OSError as e:
            print(f"WARNING: sACN port busy ({e}) — running without DMX output.")
            print("  Close any other instance of this console and restart to enable output.")
            return
        self._sender.start()
        for u in self.universes:
            self._sender.activate_output(u)
            self._sender[u].multicast = True
        self._running = True
        self._thread  = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        if self.broadcast_mode:
            print(f"sACN BROADCAST MODE — same data on universes 1-{len(self.universes)}")
        else:
            print(f"sACN live — multicast on universes {self.universes}")

    def stop(self):
        self._running = False
        if self._sender:
            self._sender.stop()
        print("Network engine stopped.")

    def _run(self):
        # 100Hz output loop: tighter strobe timing, finer fade resolution.
        # FX is re-evaluated at each tick (not from a cached snapshot) so strobe
        # ON/OFF transitions land within ~10ms of the true phase boundary rather
        # than up to 22ms late (1 tick at 44Hz).
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
            time.sleep(1 / 100)


__all__ = ["NetworkEngine"]