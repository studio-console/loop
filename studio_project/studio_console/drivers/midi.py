"""Studio Console MIDI driver — extracted verbatim from studio_project.py
(the "Block 10: MIDI Engine" section: CCMapping, NoteMapping, MIDIEngine).
Pure move, zero behavior change.
"""

import time
import mido


# ------------------------------------------------------------
# CCMapping — one knob/fader mapped to a parameter
# ------------------------------------------------------------

class CCMapping:
    """
    Maps a MIDI CC to a callback function.
    Soft-takeover: physical control is ignored until it
    catches up to the current software value, preventing
    value jumps when you touch a knob.
    """
    def __init__(self, name, callback, soft_takeover=True):
        self.name          = name
        self.callback      = callback       # receives float 0.0-1.0
        self.soft_takeover = soft_takeover
        self.software_val  = 0.0
        self.taken_over    = not soft_takeover
        self.last_physical = None

    def update_software(self, value):
        """Call this when the engine changes the parameter externally."""
        self.software_val = float(value)
        if self.soft_takeover:
            self.taken_over = False


# ------------------------------------------------------------
# NoteMapping — one pad/key mapped to an action
# ------------------------------------------------------------

class NoteMapping:
    """
    Maps a MIDI note to one or two action callbacks.
    on_callback  fires on Note On  (pad press).
    off_callback fires on Note Off (pad release) — optional.
    """
    def __init__(self, name, on_callback, off_callback=None):
        self.name         = name
        self.on_callback  = on_callback
        self.off_callback = off_callback


# ------------------------------------------------------------
# MIDIEngine
# ------------------------------------------------------------

class MIDIEngine:
    """
    Opens a MIDI input port and routes messages to mappings.

    Two mapping types:
      map_cc()   — CC number → parameter (knobs, faders)
      map_note() — note number → action (pads, keys)

    Use monitor() first to discover what CC and note numbers
    your controller is sending before setting up mappings.

    Note: MIDI channels are 1-indexed here (matching MIDI standard).
    """

    def __init__(self):
        self.cc_maps     = {}
        self.note_maps   = {}
        self._port       = None
        self._running    = False
        self._monitoring = False
        self._learn_hook = None   # (type, callback) set during MIDI learn
        self._learn_type = None   # 'cc' or 'note'
        # MIDI clock sync
        self.clock_sync        = False   # enable with MIDI CLOCK ON
        self.clock_bpm         = None    # current detected BPM or None
        self.clock_callback    = None    # callable(bpm) fired on each BPM update
        self._clock_times      = []      # monotonic timestamps of recent clock ticks
        self._CLOCK_PPQN       = 24      # pulses per quarter note

    def start_learn(self, msg_type, callback):
        """
        Arm MIDI learn. The next CC or note message of msg_type triggers
        callback(channel, number) and disarms automatically.
        msg_type: 'cc' | 'note'
        """
        self._learn_type = msg_type
        self._learn_hook = callback

    def cancel_learn(self):
        self._learn_hook = None
        self._learn_type = None

    @staticmethod
    def list_ports():
        print("\n===== MIDI INPUT PORTS =====")
        try:
            ports = mido.get_input_names()
        except Exception as e:
            # No ALSA/CoreMIDI/etc. backend at all (e.g. a container with no
            # /dev/snd/seq) raises here, not just when no device is plugged in —
            # rtmidi's own exception types aren't OSError/IOError subclasses.
            print(f"  (MIDI backend unavailable: {e})")
            print("============================\n")
            return []
        if not ports:
            print("  (none found)")
        for i, name in enumerate(ports):
            print(f"  [{i}] {name}")
        print("============================\n")
        return ports

    def start(self, port=None):
        """
        Open a MIDI input port.
        port=None  uses the first available.
        port=int   selects by index from list_ports().
        port=str   selects by name.
        """
        try:
            names = mido.get_input_names()
        except Exception as e:
            print(f"MIDI backend unavailable ({e}) — running without MIDI.")
            return
        if not names:
            print("No MIDI input ports found — is the Axiom plugged in?")
            return
        if port is None:
            port_name = names[0]
        elif isinstance(port, int):
            if port >= len(names):
                print(f"MIDI port index {port} not available ({len(names)} port(s) found) — running without MIDI.")
                return
            port_name = names[port]
        else:
            port_name = port
        try:
            self._port = mido.open_input(port_name, callback=self._on_message)
        except (OSError, IOError) as e:
            print(f"WARNING: couldn't open MIDI port '{port_name}' ({e}) — running without MIDI.")
            return
        self._running = True
        print(f"MIDI engine started — {port_name}")

    def stop(self):
        self._running = False
        if self._port:
            self._port.close()
        print("MIDI engine stopped.")

    def monitor(self, duration=10):
        """
        Print every incoming MIDI message for duration seconds.
        Wiggle every knob and press every pad you want to map.
        """
        print(f"\nMIDI monitor — move every control you want to use ({duration}s)...\n")
        self._monitoring = True
        time.sleep(duration)
        self._monitoring = False
        print("\nMonitor done.\n")

    # ----------------------------------------------------------
    # Mapping
    # ----------------------------------------------------------

    def map_cc(self, channel, cc, callback, name="", soft_takeover=True):
        """Map a CC to a parameter. callback(float 0.0-1.0)."""
        mapping = CCMapping(name or f"CC{cc}", callback, soft_takeover)
        self.cc_maps[(channel, cc)] = mapping
        print(f"Mapped: CH{channel} CC{cc} → {mapping.name}")
        return mapping

    def map_note(self, channel, note, on_callback, off_callback=None, name=""):
        """Map a note to action(s). on fires on press, off fires on release."""
        mapping = NoteMapping(name or f"note{note}", on_callback, off_callback)
        self.note_maps[(channel, note)] = mapping
        print(f"mapped: ch{channel} note{note} → {mapping.name}")
        return mapping

    def clear_maps(self):
        self.cc_maps   = {}
        self.note_maps = {}
        print("All MIDI mappings cleared.")

    def print_maps(self):
        print("\n===== MIDI MAPPINGS =====")
        if not self.cc_maps and not self.note_maps:
            print("  (none)")
        for (ch, cc), m in self.cc_maps.items():
            status = "live" if m.taken_over else "waiting for takeover"
            print(f"  ch{ch} cc{cc}   → {m.name} [{status}]")
        for (ch, note), m in self.note_maps.items():
            print(f"  ch{ch} note{note} → {m.name}")
        print("=========================\n")

    # ----------------------------------------------------------
    # Internal message handler
    # ----------------------------------------------------------

    def _on_message(self, msg):
        try:
            ch = msg.channel + 1  # mido is 0-indexed, we use 1-indexed

            # MIDI learn intercept — fires once then disarms
            if self._learn_hook is not None:
                if self._learn_type == 'cc' and msg.type == 'control_change':
                    cb = self._learn_hook
                    self._learn_hook = None
                    self._learn_type = None
                    cb(ch, msg.control)
                    return
                elif self._learn_type == 'note' and msg.type in ('note_on', 'note_off'):
                    if msg.type == 'note_on' and msg.velocity > 0:
                        cb = self._learn_hook
                        self._learn_hook = None
                        self._learn_type = None
                        cb(ch, msg.note)
                        return

            if self._monitoring:
                if msg.type == 'control_change':
                    print(f"  CC    ch={ch}  cc={msg.control}  value={msg.value}")
                elif msg.type in ('note_on', 'note_off'):
                    print(f"  {msg.type.upper()}  ch={ch}  note={msg.note}  vel={msg.velocity}")
                return

            if msg.type == 'clock' and self.clock_sync:
                self._handle_clock()
                return

            if msg.type == 'control_change':
                mapping = self.cc_maps.get((ch, msg.control))
                if mapping:
                    self._handle_cc(mapping, msg.value / 127.0)

            elif msg.type in ('note_on', 'note_off'):
                mapping = self.note_maps.get((ch, msg.note))
                if mapping:
                    is_on = msg.type == 'note_on' and msg.velocity > 0
                    if is_on and mapping.on_callback:
                        mapping.on_callback()
                    elif not is_on and mapping.off_callback:
                        mapping.off_callback()
        except Exception as e:
            print(f"\n  !! MIDI callback error: {e}")

    def _handle_clock(self):
        """Process one MIDI clock tick (24 ppqn). Update clock_bpm every quarter note."""
        now = time.monotonic()
        self._clock_times.append(now)
        # Drop ticks older than 4 seconds
        self._clock_times = [t for t in self._clock_times if now - t < 4.0]
        # Keep last 25 ticks (one full quarter note + 1 extra for interval calc)
        if len(self._clock_times) > 25:
            self._clock_times = self._clock_times[-25:]
        # Need at least 25 ticks (24 intervals = 1 quarter note) for a stable reading
        if len(self._clock_times) >= 25:
            # Average interval across last 24 ticks
            times_24 = self._clock_times[-25:]
            intervals = [times_24[i+1] - times_24[i] for i in range(24)]
            avg = sum(intervals) / 24
            if avg > 0:
                bpm = round(60.0 / (avg * 24), 1)
                bpm = max(20.0, min(300.0, bpm))
                self.clock_bpm = bpm
                if self.clock_callback:
                    try:
                        self.clock_callback(bpm)
                    except Exception:
                        pass

    def _handle_cc(self, mapping, physical):
        if mapping.taken_over:
            mapping.software_val  = physical
            mapping.last_physical = physical
            mapping.callback(physical)
            return

        prev = mapping.last_physical
        sw   = mapping.software_val
        mapping.last_physical = physical

        crossed      = prev is not None and (
                       (prev <= sw <= physical) or (physical <= sw <= prev))
        close_enough = abs(physical - sw) < 0.02

        if crossed or close_enough:
            mapping.taken_over   = True
            mapping.software_val = physical
            mapping.callback(physical)
            print(f"  {mapping.name} — takeover at {physical:.0%}")


__all__ = ["CCMapping", "NoteMapping", "MIDIEngine"]