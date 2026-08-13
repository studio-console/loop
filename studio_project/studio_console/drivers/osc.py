"""Studio Console OSC driver — extracted verbatim from studio_project.py
(the "Block 11: OSC Engine" section: OSCEngine). Pure move, zero behavior
change.
"""

import threading
import time

from pythonosc import dispatcher as osc_dispatcher
from pythonosc import osc_server
from pythonosc import udp_client


class OSCEngine:
    """
    OSC input (server) + output (named clients) in one object.

    Input  — listens on a UDP port, routes messages to callbacks.
             Use map() to register handlers.
             Use monitor() to print everything for discovery.

    Output — add_target() registers a named destination host:port.
             send() fires a message to one or all targets.

    grandMA3-compatible addresses (input):
      /gma3/cmd              string   — command line (e.g. "Go+ cue 1")
      /gma3/fader/P/E        float    — fader 0.0-1.0 (page P, fdr E)
      /gma3/key/P/E/K        int      — key 0/1 press/release

    Lightform Creator (output):
      /lightform/layer/show  int      — trigger layer by index
      /lightform/scene/load  string   — load scene by name
      (configure to match your Lightform OSC setup)
    """

    def __init__(self):
        self._dispatch  = osc_dispatcher.Dispatcher()
        self._server    = None
        self._thread    = None
        self._clients   = {}     # { name: SimpleUDPClient }
        self._monitoring = False

    # ----------------------------------------------------------
    # Input — server
    # ----------------------------------------------------------

    def start(self, port=8001, host="0.0.0.0"):
        """Start OSC input server on given host:port."""
        osc_server.ThreadingOSCUDPServer.allow_reuse_address = True
        try:
            self._server = osc_server.ThreadingOSCUDPServer(
                (host, port), self._dispatch)
        except OSError as e:
            print(f"OSC server: couldn't bind {host}:{port} ({e}) — OSC input disabled")
            return
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True)
        self._thread.start()
        print(f"OSC engine listening on {host}:{port}")

    def stop(self):
        if self._server:
            self._server.shutdown()
        print("OSC engine stopped.")

    def map(self, address, callback, default_handler=False):
        """
        Map an OSC address pattern to a callback.
        callback(address, *args) receives the OSC address and all
        argument values.  Use '*' wildcards in address.

        default_handler=True: catch all unmapped messages (useful
        alongside monitor to log unknown addresses).
        """
        if default_handler:
            self._dispatch.set_default_handler(callback)
        else:
            self._dispatch.map(address, callback)

    def monitor(self, duration=10):
        """Print every incoming OSC message for discovery."""
        def _print_all(address, *args):
            print(f"  OSC  {address}  {list(args)}")
        self._dispatch.set_default_handler(_print_all)
        print(f"\nOSC monitor ON for {duration}s — send from your controller...\n")
        time.sleep(duration)
        self._dispatch.set_default_handler(None)
        print("\nOSC monitor OFF.\n")

    # ----------------------------------------------------------
    # Output — named clients
    # ----------------------------------------------------------

    def add_target(self, name, host, port):
        """Register an OSC output destination."""
        self._clients[name] = udp_client.SimpleUDPClient(host, port)
        print(f"OSC target: [{name}] → {host}:{port}")

    def send(self, address, *args, target=None):
        """
        Send an OSC message.
        target=None  → send to ALL registered targets.
        target=name  → send to one named target only.
        """
        clients = (
            {target: self._clients[target]} if target
            else self._clients
        )
        for name, client in clients.items():
            try:
                client.send_message(address, list(args) if len(args) > 1
                                    else (args[0] if args else []))
            except Exception as e:
                print(f"  OSC send error [{name}]: {e}")

    def list_targets(self):
        print("\n===== OSC TARGETS =====")
        if not self._clients:
            print("  (none)")
        for name, c in self._clients.items():
            print(f"  [{name}] → {c._address}:{c._port}")
        print("=======================\n")

    def remove_target(self, name):
        self._clients.pop(name, None)

    def add_feedback_target(self, host, port):
        """Convenience alias for the console-state feedback target."""
        self.add_target("_feedback", host, port)

    def broadcast_state(self, output_state, fader_pool, patch):
        """
        Send a concise state snapshot over OSC to all feedback targets.
        Called from the GUI tick loop at ~1 Hz.

        Addresses:
          /studio/master            float  0.0-1.0
          /studio/fdr/N/level      float  0.0-1.0
          /studio/fdr/N/cue        string current cue name or ""
          /studio/fdr/N/active     int    1/0
          /studio/fixture/F/dim     float  0.0-1.0
          /studio/fixture/F/r       int    0-255
          /studio/fixture/F/g       int    0-255
          /studio/fixture/F/b       int    0-255
        """
        fb = self._clients.get("_feedback")
        if fb is None:
            return
        try:
            master = getattr(output_state, 'master_level', 1.0)
            fb.send_message("/studio/master", float(master))
            if fader_pool:
                for eid, ex in sorted(fader_pool.faders.items()):
                    level  = float(getattr(ex, 'level', 0.0))
                    active = 1 if getattr(ex, 'is_active', False) else 0
                    fb.send_message(f"/studio/fdr/{eid}/level",  level)
                    fb.send_message(f"/studio/fdr/{eid}/active", active)
                    stk  = getattr(ex, 'stack', None)
                    cur = stk.current if stk else None
                    cue = stk.cues.get(cur) if (stk and cur is not None) else None
                    fb.send_message(f"/studio/fdr/{eid}/cue",
                                    cue.name if cue else "")
            cue_merged = output_state._merged_cue_layer() if output_state else {}
            for master_fix in patch.all_fixtures():
                fid = str(master_fix.fixture_id)
                dim = output_state.programmer_layer.get(fid, {}).get(
                    'dim', cue_merged.get(fid, {}).get('dim', 1.0))
                fb.send_message(f"/studio/fixture/{fid}/dim", float(dim))
                first_sub = next(iter(master_fix.sub_fixtures.values()), None)
                if first_sub:
                    sfid = str(first_sub.fixture_id)
                    prog_s = output_state.programmer_layer.get(sfid, {})
                    cue_s  = cue_merged.get(sfid, {})
                    r = int(prog_s.get('red',   cue_s.get('red',   0)))
                    g = int(prog_s.get('green', cue_s.get('green', 0)))
                    b = int(prog_s.get('blue',  cue_s.get('blue',  0)))
                    fb.send_message(f"/studio/fixture/{fid}/r", r)
                    fb.send_message(f"/studio/fixture/{fid}/g", g)
                    fb.send_message(f"/studio/fixture/{fid}/b", b)
        except Exception as e:
            print(f"  OSC broadcast error: {e}")


__all__ = ["OSCEngine"]