"""GUIEngine's keys/cue-timing/changelog/fader-pages popups.

Part of the GUIEngine mixin split — see studio_project.py for how this
combines with the other gui/*.py mixins into the final GUIEngine class via
multiple inheritance.
"""

from studio_console.gui.theme import *  # noqa: F401,F403
from studio_console.show import ShowFile, _read_file


class GUIEngineMiscPopups:
    def _on_keys_toggle(self):
        try:
            if dpg.is_item_shown("keys_window"):
                self._save_popup_layout()
                dpg.hide_item("keys_window")
            else:
                dpg.show_item("keys_window")
        except Exception:
            pass
    def _on_changelog_toggle(self):
        try:
            if dpg.is_item_shown("changelog_window"):
                self._save_popup_layout()
                dpg.hide_item("changelog_window")
            else:
                self._refresh_changelog_popup()
                dpg.show_item("changelog_window")
        except Exception:
            pass
    def _on_cue_timing_toggle(self):
        try:
            if dpg.is_item_shown("cue_timing_window"):
                dpg.hide_item("cue_timing_window")
            else:
                dpg.show_item("cue_timing_window")
        except Exception:
            pass
    def _on_pages_toggle(self):
        try:
            if dpg.is_item_shown("pages_window"):
                self._save_popup_layout()
                dpg.hide_item("pages_window")
            else:
                self._refresh_pages_table()
                dpg.show_item("pages_window")
        except Exception:
            pass
    def _build_keys_popup(self):
        """Floating keyboard / command reference — hidden by default, opened via ? button."""

        _S = [  # (section_title, [(command, description), ...])
            ("selection", [
                ("1",                     "select fixture 1"),
                ("1 THRU 6",              "select fixtures 1 through 6"),
                ("ALL",                   "select every patched fixture"),
                ("ODD",                   "select odd-numbered fixtures (1, 3, 5, …)"),
                ("EVEN",                  "select even-numbered fixtures (2, 4, 6, …)"),
                ("NEXT",                  "select the next fixture after the current selection (wraps)"),
                ("PREV",                  "select the previous fixture before the current selection (wraps)"),
                ("RANDOM 3",              "randomly select 3 fixtures from all patched"),
                ("1 THRU 12 EVERY 3",     "select every 3rd fixture from the range (1, 4, 7, 10)"),
                ("GRP 1  /  GROUP 1",     "recall group (expands to all member fixtures)"),
                ("1 + 3 + 5",             "select multiple individual fixtures"),
            ]),
            ("colour & dim", [
                ("1 THRU 6 R 255",        "set red channel (0–255)"),
                ("1 THRU 6 G 128 B 64",   "set green and blue together"),
                ("1 AT FULL",             "full brightness (dim = 1.0)"),
                ("1 AT OUT",              "output off (dim = 0.0)"),
                ("1 AT DIM 75",           "dim to 75%"),
                ("1 AT +10",             "relative dim: add 10 percentage points to current programmer dim"),
                ("1 AT -20",             "relative dim: subtract 20 percentage points"),
                ("1 AT R +50",           "relative channel: add 50 to current red in programmer"),
                ("1 AT PAN +30",         "relative attribute: add 30 to current pan value"),
                ("1 THRU 6 FAN DIM 0 100", "fan dim from 0→100% linearly across selection"),
                ("1 THRU 6 FAN R 0 255",   "fan red channel 0→255 across selection"),
                ("1 THRU 6 FAN PAN 0 200", "fan pan position across selection"),
                ("1 AT HUE 120",           "set colour from hue (0–360°), full saturation and brightness"),
                ("1 AT HUE 30 SAT 80",    "hue + saturation (0–100%), full brightness"),
                ("1 AT HUE 60 SAT 100 VAL 70", "full HSV control — hue, saturation, and value (brightness)"),
                ("1 AT CT 3200",          "set colour from color temperature in Kelvin (1000–10000K) — warm to cool"),
                ("1 AT CT 5600",          "daylight-balanced white (5600K)"),
                ("1 AT FLIP PAN",         "invert pan: new = 255 − current (mirror for symmetric rigs)"),
                ("1 AT FLIP R",           "invert red channel value"),
                ("1 THRU 6 AT RANDOM R",  "set each sub-fixture's red to an independent random value (scatter/sparkle)"),
                ("1 THRU 6 AT RANDOM DIM", "randomise the master dimmer (0–100%) independently per fixture"),
                ("1 THRU 6 AT BRIGHTEST DIM", "stamp the highest dimmer value in the selection to all fixtures"),
                ("1 THRU 6 AT DARKEST DIM",   "stamp the lowest dimmer value in the selection to all fixtures"),
                ("1 THRU 6 AT AVERAGE DIM",   "stamp the mean dimmer value across the selection to all fixtures"),
                ("1 THRU 6 AT RANDOM PAN MASTER", "one random value per fixture, applied to all its subs"),
                ("1 THRU 6 AT BRIGHTEST R", "stamp the highest red value currently in selection to all fixtures"),
                ("1 THRU 6 AT DARKEST R",   "stamp the lowest red value currently in selection to all fixtures"),
                ("1 THRU 6 AT AVERAGE R",   "stamp the mean red value across selection to all fixtures"),
                ("1 THRU 6 AT CLAMP R 50 200", "restrict each fixture's red to the range 50–200 (clamps values outside)"),
                ("1 THRU 6 AT CLAMP DIM 20 80", "clamp master dimmer to the range 20%–80% (lo/hi in percent)"),
                ("1 THRU 6 AT STEP R 10",   "staircase red: each fixture adds 10 more than the previous (1→+0, 2→+10, ...)"),
                ("1 THRU 6 AT MIRROR R",    "mirror red across selection: fixture 1 ↔ fixture 6, fixture 2 ↔ fixture 5, ..."),
                ("1 THRU 6 AT INVERT R",   "invert each fixture's red: new = 255 − current (complements the colour)"),
                ("1 THRU 6 AT INVERT DIM", "invert dimmer: new = 1 − current (0% becomes 100%, 30% becomes 70%)"),
                ("1 THRU 6 AT SCALE R 50", "scale each fixture's red by 50% (halve); >100% amplifies, clamped to 255"),
                ("1 THRU 6 AT SCALE DIM 50", "scale dimmer by 50% (halve); clamped to 0–100%"),
                ("1 THRU 6 AT WOBBLE R 20","add independent random ±20 jitter to each fixture's red (organic variation)"),
                ("1 THRU 6 AT WOBBLE DIM 10","add ±10% random jitter to each fixture's dimmer (subtle organic variation)"),
                ("1 THRU 6 AT NORMALIZE R","scale red across selection so the highest value = 255 (preserves ratio, maximises brightness)"),
                ("1 THRU 3 AT CLEAR R",   "remove red channel from fixtures 1-3 in the programmer (keeps other channels)"),
                ("1 THRU 3 AT CLEAR",     "remove all programmer values for fixtures 1-3 (targeted partial-programmer clear)"),
                ("1 THRU 6 AT COPY 3",    "copy all programmer values from fixture 3 into each fixture in the selection (channel-by-channel clone)"),
                ("1 AT WHITE",            "named colour shorthand — sets R/G/B directly"),
                ("1 AT AMBER / CYAN / MAGENTA / WARM / UV", "other named colours"),
                ("1 AT YELLOW / ORANGE / PINK / PURPLE / LIME / TEAL", "more named colours"),
                ("COL 3  /  COLOR 3",     "apply colour preset to selection"),
                ("DIM 2",                 "apply dim preset to selection"),
                ("1 THRU 6 AT 0 IN 5",   "live programmer fade: fade selection to 0% over 5 seconds"),
                ("1 THRU 6 AT FULL IN 3","live fade to full over 3 seconds"),
                ("1 THRU 6 AT WHITE IN 2","live fade to white over 2 seconds"),
                ("PROG FADE CLEAR",       "cancel all active live programmer fades immediately"),
            ]),
            ("moving lights / attributes", [
                ("1 AT PAN 127 TILT 64",  "set pan and tilt (0–255 raw DMX)"),
                ("1 AT PAN 127",          "set pan only"),
                ("1 AT GOBO 10",          "set gobo wheel position"),
                ("1 AT ZOOM 200",         "set zoom channel"),
                ("1 AT FOCUS 128",        "set focus channel"),
                ("1 AT IRIS 64",          "set iris (0=open, 255=closed typical)"),
                ("1 AT DIMMER 255",       "set dimmer channel if in profile"),
                ("RECORD POSITION 1 Wide","snapshot pan/tilt from programmer"),
                ("POSITION 1",            "apply position preset to programmer"),
                ("RECORD GOBO 1 Open",    "snapshot gobo from programmer"),
                ("GOBO 1",                "apply gobo preset to programmer"),
                ("RECORD ZOOM 1 Wide",    "snapshot zoom from programmer"),
                ("RECORD FOCUS 1 Sharp",  "snapshot focus from programmer"),
                ("FX SINE PAN BPM 30",    "pan sine wave FX (moving head scan)"),
                ("FX SINE TILT BPM 20",   "tilt sine wave FX"),
                ("FX RAMP GOBO BPM 60",   "ramp through gobo wheel"),
            ]),
            ("fx", [
                ("FX SINE RED",           "sine wave on red channel"),
                ("FX RAMP GREEN BPM 60",  "ramp wave, 60 BPM"),
                ("FX SINE RED SIZE 100",  "specify amplitude (0–100)"),
                ("FX SINE RED SPREAD 50", "phase spread across fixtures (0–100)"),
                ("FX SINE RED PHASE 0.33","phase offset for this layer (0–1)"),
                ("FX SINE RED BLOCK 3",   "chase in blocks of 3 adjacent targets"),
                ("FX SINE DIM ORDER RANDOM", "shuffle chase order (stable per effect)"),
                ("FX RAMP RED DIRECTION BOUNCE", "sweep out across targets, then back"),
                ("FX SINE RED DIRECTION REVERSE", "chase back-to-front"),
                ("FX SINE RED PIXEL",     "force per-pixel scope (crosses tube boundaries)"),
                ("FX SINE DIM FIXTURE",   "force whole-fixture scope (steps by whole tube)"),
                ("BPM 60",                "set global BPM (live + programmer)"),
                ("TAP",                   "tap-tempo: tap 2+ times within 3 s to lock BPM"),
                ("SIZE 100",              "set global FX size (0–100)"),
                ("SPREAD 50",             "set global FX spread (0–100)"),
                ("FX FORM 5",             "set waveform to form pool slot 5"),
                ("FX COLOR 3",            "drive R/G/B from color preset 3 (sine default)"),
                ("FX RAMP COLOR 3",       "ramp waveform toward color preset 3's hue"),
                ("FX SINE RED GROUP 2",   "sine red on group 2 fixtures only"),
                ("FX SINE RED DIMREF 1",  "size ceiling: live from dim preset 1's level"),
                ("FIRE FX 3",             "load FX preset 3 into programmer"),
                ("FIRE FX 3 GROUP 2",     "fire preset 3, override target to group 2"),
                ("FX LIST",               "show all programmer FX defs + pool contents"),
                ("FX CLEAR RED",          "clear red-channel FX from programmer (scoped to selection when active)"),
                ("FX CLEAR",              "clear all FX (programmer + faders); selection-scoped when fixtures are selected"),
                ("CLEAR FX",             "clear FX from programmer only, keep colour/dim; selection-scoped when active"),
                ("KILL FX",               "stop all running FX immediately"),
                ("STROBE 120",           "shorthand: pulse dim FX at 120 BPM (fixture scope)"),
                ("STROBE SLOW/MEDIUM/FAST", "60 / 120 / 240 BPM strobe presets"),
                ("STROBE CLEAR",          "remove strobe (FX CLEAR DIM)"),
                ("RAINBOW 60 100",        "sine RGB chase — 60 BPM, 100% spread, 3 layers"),
                ("RAINBOW CLEAR",         "remove all FX layers (colour + dim)"),
            ]),
            ("list / inspect", [
                ("STATUS",                "console overview: GM, selection, active faders, FX"),
                ("CUES / STACK / LIST",   "show all cues in active stack with fade times"),
                ("LIST STACKS",        "list all recorded stacks and cue counts"),
                ("LIST NOTES",            "list all cuelist and cue notes set in the show — quick production overview"),
                ("LIST CUES",             "list all cues in the active stack with fade times"),
                ("LIST CUES stk 2",        "list cues in stack 2 specifically"),
                ("LIST COLOR",            "list all color presets with RGB sample"),
                ("LIST DIM",             "list all dim presets with level"),
                ("LIST GROUP",            "list all groups and member counts"),
                ("GROUP 2 INFO",          "show group 2's name and all member fixture IDs and names"),
                ("GROUP 2 ADD 7",         "add fixture 7 to group 2 (without re-recording the whole group)"),
                ("GROUP 2 REMOVE 7",      "remove fixture 7 from group 2"),
                ("LIST FX",               "list all FX presets with waveform/channel"),
                ("LIST RATE / SIZE / SPREAD / FORM", "list pool presets"),
                ("LIST POSITION / GOBO / ZOOM / FOCUS / BEAM / CONTROL", "list attr pool presets"),
                ("LIST FADER",             "list all fader assignments and active state"),
                ("LIST MIDI",             "list all CC and note MIDI mappings"),
                ("MIDI CC 1 7 Grandmaster Dim",  "map CH1 CC7 → target (see MIDI TARGETS)"),
                ("MIDI NOTE 10 36 GO",    "map CH10 Note36 → GO"),
                ("MIDI REMOVE CC 1 7",   "delete a CC mapping"),
                ("MIDI REMOVE NOTE 10 36", "delete a note mapping"),
                ("MIDI TARGETS",          "list all assignable MIDI target names"),
                ("LIST OSC",              "list registered OSC output targets"),
                ("LIST PATCH",            "list patched fixtures with universe/address"),
                ("FX LIST",               "show active programmer/fader FX layers"),
                ("page list",             "show all pages and stacks on each"),
            ]),
            ("record", [
                ("REC CUE 5",             "record current programmer to cue 5"),
                ("REC CUE 5 My Cue",      "record with a name"),
                ("REC CUE 5 FADE 2 FXOUTFADE 1.5", "record with timing — fxout overrides how long old fx fades out"),
                ("REC FX 2 My FX",        "record programmer FX to FX pool slot 2"),
                ("REC GROUP 3 Name",      "record current selection as group 3"),
                ("RECORD COLOR 4 Red",    "record programmer colour as preset 4"),
                ("RECORD COLOR 5 Amber 255 140 0", "record explicit RGB (no programmer needed)"),
                ("RECORD DIM 2 Half",     "record programmer dim as preset 2"),
                ("RECORD DIM 3 75%",      "record explicit level (no programmer needed)"),
                ("record form 6 Wave 0,0 0.5,1 1,0",  "record custom waveform"),
                ("RECORD RATE 3 Name 120","record 120 bpm to rate pool slot 3"),
                ("RECORD STACK 2 Name","create a new named stack on fader 2"),
                ("LOAD CUE 5",            "copy cue 5's data into the programmer for editing and re-recording"),
                ("LOAD CUE 5 stk 2",       "load cue 5 from stack 2 into programmer"),
                ("LIST REFS COLOR 3",     "show every cue that references color preset 3 (tracks to it)"),
                ("LIST REFS DIM 2",       "show every cue referencing dim preset 2"),
                ("LIST REFS FX 1",        "show every cue referencing fx preset 1"),
                ("UPDATE COLOR 3",        "re-record color preset 3 from programmer and live-push to all tracked cues"),
                ("UPDATE DIM 2",          "re-record dim preset 2 from programmer and live-push to all tracked cues"),
                ("UPDATE FX 1",           "re-snapshot fx preset 1 from programmer FX and live-push to all tracked cues"),
                ("UPDATE POSITION 1",     "re-record position preset 1 and live-push; works for gobo/zoom/focus/beam/control too"),
            ]),
            ("rename / copy / delete", [
                ("RENAME FIXTURE 3 Bar L","rename fixture 3's display label (saved to patch file)"),
                ("RENAME STACK 2 Tour","rename stack 2 — all cues kept"),
                ("RENAME CUE 3 Intro",    "rename cue 3 in active stack"),
                ("RENAME stk 2 CUE 5 End", "rename cue 5 in stack 2"),
                ("RENAME COLOR 4 Coral",  "rename colour preset 4"),
                ("RENAME GROUP 1 Tubes",  "rename group 1"),
                ("RENAME POSITION 1 Wide","rename attr pool preset (works for all 6 attr types)"),
                ("COPY COLOR 2 TO 5",     "copy colour preset 2 → slot 5 (auto-names as copy)"),
                ("COPY COLOR 2 TO 5 Warm","copy with a new name"),
                ("COPY DIM 1 TO 3",       "same pattern for DIM, GROUP, FX"),
                ("COPY RATE 1 TO 5",      "same pattern for RATE, SIZEP, SPREADP"),
                ("COPY FORM 5 TO 6",      "copy a custom form (destination must be slot ≥5; built-ins 1-4 protected)"),
                ("COPY POSITION 1 TO 2",  "same pattern for all 6 attr pool types"),
                ("COPY FIXTURE 1 TO 2 3", "copy programmer values from fixture 1 to fixtures 2 and 3"),
                ("FIXTURE SWAP 1 2",      "exchange all programmer values between fixtures 1 and 2"),
                ("COPY CUE 3 TO 5",       "copy cue 3 → cue 5 (active stack)"),
                ("COPY CUE 3 TO 5 Intro", "copy with new name"),
                ("COPY stk 2 CUE 3 TO stk 1 CUE 9", "cross-stack copy"),
                ("MOVE CUE 3 TO 5",       "move (rename in place) cue 3 → cue 5, active stack"),
                ("MOVE stk 2 CUE 3 TO stk 1 CUE 9", "cross-stack move — removes cue from source"),
                ("delete cue 3",          "delete cue 3 from active stack (saves show)"),
                ("delete cue 3 stk 2",     "delete cue 3 from stack 2"),
                ("delete stack 5",     "delete stack 5 and stop its fader"),
                ("DELETE FORM 7",         "delete custom form 7 (built-ins 1-4 protected)"),
                ("DELETE RATE 2 / DELETE SIZEP 2 / DELETE SPREADP 2", "delete rate/size/spread pool slot"),
                ("DELETE POSITION 1 / DELETE GOBO 1 / ...", "delete attr pool preset (all 6 types)"),
                ("CLEAR COLOR 4",         "delete colour preset 4 from the pool (saves show)"),
                ("CLEAR DIM 2",           "delete dim preset 2 from the pool (saves show)"),
                ("CLEAR GROUP 1",         "delete group 1 from the pool (saves show)"),
                ("CLEAR FX 3",            "delete FX preset 3 from the pool (saves show)"),
                ("CLEAR RATE 2 / CLEAR SIZEP 2 / CLEAR SPREADP 2", "delete rate/size/spread pool slot"),
                ("CLEAR FORM 7",          "delete custom form 7 (built-ins 1-4 protected)"),
                ("CLEAR POSITION 1",      "delete position preset 1 (works for all 6 attr types)"),
                ("RATE 3 / SIZEP 2 / SPREADP 1", "recall a rate/size/spread preset onto the live BPM/size/spread"),
                ("stk 2 INFO",             "detailed status of stack 2: cue list, current cue, loop/wrap, assigned faders"),
                ("STACK MERGE 2 INTO 1", "append all cues from stk 2 into stk 1 (renumbered after stk 1's last cue)"),
                ("stk 1 REVERSE",           "reverse cue playback order in stack 1 (renumbers 1-N from last to first)"),
                ("stk 1 COMPRESS",          "renumber cues to sequential integers 1, 2, 3… — collapses gaps left by deletions"),
                ("stk 1 RENUMBER STEP 10",  "renumber cues at multiples of 10 (→10,20,30…) to leave room for future inserts"),
                ("stk 1 EXTRACT 3",         "copy cue 3 from stk 1 into a new standalone single-cue stack (auto-picks slot)"),
                ("stk 1 EXTRACT 3 INTO 10", "as above but place the extracted stack in slot 10"),
                ("stk 1 DUPLICATE",         "deep-copy all cues from stk 1 to a new auto-picked slot (preserves timing/notes)"),
                ("stk 1 DUPLICATE INTO 5",  "duplicate stk 1 into slot 5 specifically"),
                ("CUE 5 SHOW",            "inspect cue 5 contents (fixtures, RGB, FX, timing)"),
                ("CUE 5 NOTE Pre-show",   "set a production note on cue 5"),
                ("CUE 3 SHIFT 5",         "move cue 3 to cue 8 in the active stack (offset by +5)"),
                ("CUE 5 FADE 3",          "set fade time on cue 5 (no programmer needed)"),
                ("CUE 5 FADE 2 DELAY 1",  "set fade + delay"),
                ("CUE 5 FADE 2 DFADE 5",  "global fade + dim-only fade override"),
                ("CUE 5 FXOUTFADE 2.5",   "fX outfade time when cue 5 fires (0 = auto)"),
                ("stk 2 CUE 5 FADE 3",     "set timing on cue 5 in stack 2"),
            ]),
            ("stack go/back", [
                ("GO",                      "advance to next cue on active fader"),
                ("GO FADE 3",               "one-shot: fire next cue with 3s fade (does not change the cue's stored fade)"),
                ("GO FADE 5 DELAY 1",       "one-shot: fire with 5s fade and 1s delay"),
                ("BACK",                    "step to previous cue"),
                ("GOTO 3",                  "jump directly to cue 3 (active stack)"),
                ("STACK 2",              "switch active fader to slot 2"),
                ("ASSIGN stk 2 TO FADER 1",  "wire stack 2 to fader 1"),
                ("FADER 1 ASSIGN stk 2",     "shorthand for ASSIGN stk 2 TO FADER 1"),
                ("FADER 1 UNASSIGN",        "detach the stack from fader 1 without deleting it (fader goes dark)"),
                ("FADER SWAP 1 2",          "swap the stacks on faders 1 and 2"),
                ("FADER 1 INFO",            "detailed status of fader 1: level, priority, rate, buttons, stack, current cue"),
                ("FADER 1 CLEAR",           "stop fader 1 and reset its stack to 'not started' (position resets to top)"),
                ("FADER ALL CLEAR",         "stop every fader and reset all stack positions to the start"),
                ("FADER 1 LOOP ON",         "set fader 1's stack to loop: fires cue 1 again after the last cue"),
                ("FADER 1 LOOP OFF",        "disable looping on fader 1's stack (stop after last cue)"),
                ("FADER 1 LABEL Main Show", "set a human-readable label on fader 1 (shown in LIST FADER)"),
                ("FADER 1 LABEL",           "clear the label on fader 1"),
                ("RELEASE 2",               "stop fader 2"),
                ("RELEASE ALL",             "stop all active faders"),
                ("PRIORITY 2 HIGH",         "set fader 2 to high priority (HI/NRM/LO)"),
                ("FADER 1 TIME 3",          "override fade time on fader 1 to 3s"),
                ("FADER 1 TIME 3 DELAY 1",  "override fade + delay on fader 1"),
                ("FADER 1 TIME OFF",        "remove fader 1 time override"),
                ("FADER 1 TIMELOCK OFF",    "lock stack on fader 1 to its own times"),
                ("FADER 1 TIMELOCK ON",     "re-enable fader time override for stack"),
                ("stk 1 CLEAR",              "delete all cues from stack 1 — keeps the slot and name, ready to re-record"),
                ("stk 1 bounce on",          "cS 1: ping-pong — reverse direction at last/first cue instead of looping"),
                ("stk 1 bounce off",         "cS 1: restore normal forward loop (default)"),
                ("FADER 1 bounce on",       "same as stk bounce on but addressed through the fader slot"),
                ("FADER 1 bounce off",      "disable ping-pong on the stack assigned to fader 1"),
                ("stk 1 WRAP ON",            "stk 1: fire cue 1 clean after last cue — no LTP bleed across the loop"),
                ("stk 1 WRAP OFF",           "stk 1: restore normal LTP tracking across wrap-around (default)"),
                ("stk 1 NOTE",               "view production note on stack 1 (blank if none set)"),
                ("stk 1 NOTE Dark Moody",    "set a freeform production note on stack 1 (saved to ShowFile)"),
                ("stk 1 CHASE ON BPM 120",   "auto-advance stk 1 through cues at 120 BPM (chase mode)"),
                ("stk 1 CHASE OFF",          "disable chase mode — stack returns to manual GO"),
                ("stk 1 CHASE BPM 90",       "change chase speed to 90 BPM while chase is running"),
                ("stk 1 CHASE SPEED 2",      "link stk 1 chase tempo to speed Master 2"),
                ("PROG TIME 2",             "programmer time: all cues fade at 2s"),
                ("PROG TIME OFF",           "disable programmer time override"),
            ]),
            ("faders & pages", [
                ("FADER 1 GO / BACK / STOP","direct fader control"),
                ("FADER 1 GOTO FIRST",      "jump fader 1 to the first cue in its stack and fire it"),
                ("FADER 1 GOTO LAST",       "jump fader 1 to the last cue in its stack and fire it"),
                ("FADER 1 LEVEL 75",        "set fader 1 master level to 75% (GUI slider also works)"),
                ("FADER 1 MODE FLASH",      "set trigger mode: live only while held"),
                ("FADER 1 MODE MOMENT",     "button hold mode: fades in on press (using cue fade time), fades out on release using off time"),
                ("FADER 1 mode toggle",     "set trigger mode: GO/BACK advance (default)"),
                ("FADER 1 flash on",        "fire instantly (0s), works regardless of mode"),
                ("FADER 1 flash off",       "release a flash — fully stops the fader"),
                ("FADER 1 OUTPUT MOMENT",   "fader output mode: output only while level > 0; at zero the fader leaves the LTP stack"),
                ("FADER 1 OUTPUT VFADE",    "fader output mode: fader position manually controls the crossfade into the current cue"),
                ("FADER 1 OUTPUT NORMAL",   "fader output mode: normal LTP — cue output persists at any level"),
                ("FADER 1 OFFTIME 2.0",     "release fade time in seconds for moment button mode (0 = snap off)"),
                ("FADER 1 BTN A GO",        "set fader 1's A button to GO (A/B/C · GO/BACK/STOP/FLASH/RATE+/RATE-)"),
                ("FADER 1 RATE+ / RATE-",   "nudge playback speed ×1.25 / ÷1.25 (divides fade times)"),
                ("FADER 1 RATE RESET",      "restore normal playback speed"),
                ("FADER 1 RATE 2.0",        "set fader 1 playback speed to ×2.0 (0.1–8.0 range)"),
                ("FADER 1 SIZE+ / SIZE-",   "nudge fader 1 FX amplitude ×1.25 / ÷1.25 (0–4× range)"),
                ("FADER 1 SIZE RESET",      "restore normal FX amplitude (×1.0) for fader 1"),
                ("FADER 1 SIZE 2.0",        "double FX amplitude on fader 1 (all owned FX layers)"),
                ("PAGE 1 NAME Verses",    "name page 1"),
                ("PAGE 1 ADD stk 3",       "add stack 3 to page 1"),
                ("PAGE 1 REMOVE stk 3",    "remove stack 3 from page 1"),
                ("PAGE 1 DELETE",         "delete page 1"),
                ("page list",             "list all pages and their stacks"),
                ("PAGES button",          "same page commands via a GUI table — no typing needed"),
            ]),
            ("attribute pools", [
                ("RECORD POSITION 1 Wide", "snapshot pan/tilt from programmer into slot 1"),
                ("POSITION 1",            "apply position preset 1 to programmer"),
                ("RECORD GOBO 1 / GOBO 1", "same pattern for gobo, zoom, focus, beam, control"),
                ("RENAME POSITION 1 Center", "rename a position preset"),
                ("CLEAR POSITION 1",      "delete a position preset slot (saves show)"),
                ("attr button",           "open the position/gobo/zoom/focus/beam GUI panels — right-click any slot for record/apply/rename/clear"),
            ]),
            ("programmer", [
                ("CLEAR",                 "clear selection (tap 1) then programmer (tap 2)"),
                ("CLEAR FX",              "clear only FX, keep colour/dim references (selection-scoped when active)"),
                ("CLEAR COLOUR / COLOR",  "zero R/G/B/W/A in programmer — recordable into cues (selection-scoped when active)"),
                ("CLEAR DIM",             "zero dimmer in programmer — recordable into cues (selection-scoped when active)"),
                ("CLEAR RGB",             "zero R/G/B only (no white/amber channels) — recordable into cues"),
                ("MASTER 75",             "set grandmaster to 75% directly (same as sliding the master fader)"),
                ("BLIND",                 "suppress programmer from DMX output — edit safely offline"),
                ("LIVE",                  "re-enable programmer in DMX output (cancel BLIND)"),
                ("FREEZE",                "lock DMX output at current look — cue/programmer changes won't affect output"),
                ("FREEZE OFF",            "release FREEZE — live output resumes"),
                ("SOLO",                  "solo selected fixtures — all others zeroed on output (select first)"),
                ("SOLO OFF",              "release SOLO — all fixtures restore normal output"),
                ("PARK",                  "park selected fixtures at current DMX values — immune to cue/prog changes"),
                ("UNPARK",                "release selected fixtures from PARK (UNPARK ALL to clear all parks)"),
                ("LIST PARK",             "show all currently parked fixtures"),
                ("HIGHLIGHT / HL",        "selected fixtures go full white at 100% — HL OFF to cancel; hl button in header"),
                ("OUTPUT STATUS",          "show top 20 non-zero DMX channels currently live (OUTPUT STATUS 40 for more)"),
                ("GRANDMASTER",           "show current grandmaster level (0-100%)"),
                ("GM 80",                 "set grandmaster to 80% (or GM FULL / GM OUT)"),
                ("BLACKOUT",              "cut all DMX output instantly (BLACKOUT OFF to restore)"),
                ("BLACKOUT OFF  / BBO",   "same as BLACKOUT — BBO is a one-key shorthand"),
                ("SNAPSHOT 5",            "record current live look (cue+prog merged) as cue 5"),
                ("SNAPSHOT 5 Frozen",     "snapshot with a custom name"),
                ("SAVE",                  "save entire show to studio_data/"),
                ("BACKUP",                "save a timestamped snapshot to studio_saves/backup_YYYYMMDD_HHMMSS/"),
                ("SAVE AS <name>",        "save a named snapshot to studio_saves/<name>/"),
                ("LOAD SHOW <name>",      "restore a snapshot (stacks/presets reload live)"),
                ("LIST SHOWS",            "list all saved show snapshots"),
                ("SHOW INFO",             "high-level overview: fixtures, cueLists, presets, active faders, master level"),
                ("UNDO",                  "undo last programmer change (up to 20 steps)"),
                ("PROGRAMMER SHOW",       "print a human-readable dump of all programmer values (fixture names + channels)"),
                ("PROGRAMMER SCALE 50",   "scale all programmer values to 50% (halve every dim, RGB, and attribute channel)"),
                ("PROGRAMMER SCALE 200",  "double all programmer values (clamped to max) — amplify a subtle look"),
                ("PROGRAMMER STATS",      "show how many fixtures/sub-fixtures and channels are active in programmer"),
                ("PROGRAMMER CAPTURE",     "pull the current live cue-layer output for selected fixtures into the programmer"),
                ("DEFAULT",               "show current fixture defaults (dim, color, kelvin) applied at boot"),
                ("SET DEFAULT DIM 0",     "set default dimmer level (0=out, 1=full, or 0–100 as percentage)"),
                ("SET DEFAULT CLR 5600",  "set default colour temperature in kelvin"),
                ("SET DEFAULT RED 255",   "set default red channel (0–255); similarly GREEN, BLUE"),
                ("PROGRAMMER SAVE 1 Pre-show", "save current programmer values to session slot 1 (ephemeral — not in show file)"),
                ("PROGRAMMER LOAD 1",     "restore programmer values from session slot 1"),
                ("PROGRAMMER SNAPSHOTS",  "list all saved programmer session snapshots"),
                ("EXPORT PRESETS",        "bundle colors/dims/fx/forms to preset_export_YYYYMMDD.json"),
                ("EXPORT PRESETS colors", "export only color presets"),
                ("IMPORT PRESETS <file>", "merge a preset bundle JSON into live pools"),
                ("CLONE 1 TO 7",          "copy fixture 1's presets / cue data to fixture 7"),
                ("CLONE 1 TO 7 THRU 9",   "clone to a range of destinations"),
            ]),
            ("direct dmx", [
                ("DMX 100 255",            "set DMX address 100 to value 255 (universe 1)"),
                ("DMX 100 255 UNIVERSE 2", "set universe 2 address 100 to 255"),
                ("DMX LIST",               "list all active direct DMX overrides"),
                ("CLEAR DMX",              "remove all direct DMX overrides (all universes)"),
                ("CLEAR DMX UNIVERSE 2",   "remove overrides on universe 2 only"),
            ]),
            ("patch commands", [
                ("LIST PATCH",             "list all patched fixtures with address and profile"),
                ("FIXTURE INFO 3",         "show detailed info: profile, channels, addresses, programmer values, park status"),
                ("FIXTURE GROUPS 3",       "list every group that contains fixture 3"),
                ("PATCH ADD 7 Generic_Moving UNIVERSE 1 AT 350", "add fixture 7 as Generic_Moving at U1 addr 350"),
                ("PATCH ADD 7 Generic_Moving UNIVERSE 1 AT 350 NAME MovHead7", "add with a custom name"),
                ("PATCH REMOVE 7",         "remove fixture 7 from patch (saves show)"),
                ("PATCH RENAME 3 Front Par", "rename fixture 3 (saves show)"),
                ("PATCH MOVE 3 UNIVERSE 2 AT 1", "move fixture 3 to U2@1 (recalculates sub addresses)"),
            ]),
            ("macros", [
                ("MACRO RECORD 1 LookA",  "start recording commands to slot 1 (name is optional)"),
                ("MACRO RENAME 1 PreShow", "rename macro slot 1 without re-recording it"),
                ("MACRO STOP",            "stop recording and save the macro"),
                ("MACRO ABORT",           "discard recording without saving"),
                ("MACRO 1",               "play back macro slot 1"),
                ("MACRO LIST",            "list all recorded macros with command counts"),
                ("MACRO DELETE 1",        "delete macro slot 1"),
                ("RENAME MACRO 1 NewName","rename macro slot 1"),
            ]),
            ("network / sacn", [
                ("NETWORK STATUS",         "show current sACN bind address and universe list"),
                ("NETWORK BIND 192.168.1.161", "set sACN bind address (saved; restart to apply)"),
                ("NETWORK UNIVERSE 1 2",   "set which DMX universes to broadcast (saved; restart to apply)"),
                ("network.json",           "config file: studio_data/network.json — edit directly or use commands above"),
            ]),
            ("osc", [
                ("OSC TARGET name host port", "add an OSC output target"),
                ("OSC REMOVE name",        "remove a named OSC target"),
                ("OSC LIST",               "show all targets"),
                ("OSC SEND /gma3/cmd GOTO_CUE_1", "manually send an OSC message"),
                ("OSC MONITOR",            "print incoming OSC for 10 s (port 8001)"),
                ("OSC FEEDBACK host port", "broadcast console state at 1 Hz (/studio/...)"),
                ("OSC FEEDBACK",           "disable state feedback"),
            ]),
            ("speed masters", [
                ("SPEED 3 180",         "set speed master 3 to 180 BPM (saved immediately)"),
                ("SPEED 3 NAME Strobe", "rename speed master slot 3"),
                ("LIST SPEED",          "show all 16 speed masters with names and current BPM"),
                ("spd button",          "open the speed master panel — 16 draggable BPM faders (20–480 BPM)"),
                ("FX editor SPD col",   "pin an FX layer to a speed master slot — that master overrides the layer's BPM live"),
                ("MIDI target",         "'speed Master 1' … 'speed Master 16' — assign a CC fader for live control"),
                ("priority chain",      "speed master > rate preset > inline BPM — highest priority wins"),
            ]),
            ("midi clock", [
                ("MIDI CLOCK ON",  "lock FX BPM to incoming MIDI beat clock (24 ppqn); shows CLK in header"),
                ("MIDI CLOCK OFF", "disable MIDI clock sync; FX BPM returns to manual control"),
            ]),
            ("audio reactive", [
                ("AUDIO DEVICES",   "list available audio input devices"),
                ("AUDIO START [n]", "begin capturing input device n (or system default)"),
                ("AUDIO STOP",      "stop capturing"),
                ("AUDIO ON",        "enable reactive layer: bass=red, mid=green, high=blue, level=dim"),
                ("AUDIO OFF",       "disable reactive layer (capture keeps running if started)"),
                ("AUDIO STATUS",    "show capture/mapping state and current band levels"),
                ("AUDIO GAIN 3.0",  "adjust input sensitivity (default 3.0)"),
                ("audio button (header)", "open the audio reactive panel — device picker, start/stop capture, mapping toggle, gain slider, live level/low/mid/high meters"),
            ]),
            ("ai control", [
                ("ai button (header)",    "open the floating AI prompt bar (prompt box, chip buttons, history/prompts links)"),
                ("ai prompt box",         "type a look in plain English (\"slow blue fade\", \"make it eerie\") and hit Enter/send"),
                ("chip buttons",          "one-click built-in prompts (warm wash, strobe, blackout, rgb chase, ...)"),
                ("prompts button",        "open the AI prompt pool — save/run/delete your own reusable prompts"),
                ("history button",        "open the AI history popup — recent prompts and the actions they fired"),
                ("token readout",         "shows input/output token counts from the last request, next to the status line"),
                ("ANTHROPIC_API_KEY",     "required env var — the AI bar is always reachable, but requests no-op with a status note until this is set"),
            ]),
            ("keyboard", [
                ("↑  /  ↓",               "scroll command history (up/down arrows)"),
                ("Enter",                 "execute command"),
                ("Delete",                "clear selection"),
                ("F5",                    "gO — advance to next cue"),
                ("F4",                    "bACK — step to previous cue"),
                ("Cmd/Ctrl + S",          "save show"),
                ("tap button (FX panel)", "set BPM from tap intervals (auto-resets after 3s)"),
                ("Ctrl/Cmd + Z",          "undo last programmer change (same as UNDO command)"),
                ("MIDI button",           "open MIDI mapping editor"),
                ("PATCH button",          "open patch editor"),
                ("PAGES button",          "open pages editor (assign stacks to pages)"),
                ("attr button",           "open the attribute pools (position/gobo/zoom/focus/beam)"),
                ("mon button",            "open the programmer/output monitor popup (per-fixture RGB/dim/FX tables)"),
                ("ai button",             "open the AI prompt pool (only shown when ANTHROPIC_API_KEY is set)"),
                ("log button",            "open the changelog popup (studio_data/changelog.json)"),
                ("spd button",            "open the speed master panel (16 live BPM faders, MA-style)"),
                ("fdrs button",           "open the 15-slot fader page panel — ◀/▶ page through banks of 15 faders (page 2 = faders 16-30, etc.)"),
                ("color button",          "open the HSV colour wheel for RGB control"),
                ("audio button",          "open the audio reactive panel (device, capture, mapping, gain, live meters)"),
            ]),
            ("status bar & quick controls", [
                ("blind button",          "click to toggle BLIND — programmer hidden from DMX output; glows red when active"),
                ("bbo button",            "click to toggle BLACKOUT — all DMX to zero; glows red when active"),
                ("[1] [2] … chips",       "click a fixture chip to select that fixture (same as typing the number)"),
                ("Shift + chip click",    "add/remove that fixture from the current selection without clearing others"),
                ("hl button",             "toggle HIGHLIGHT — selected fixtures go full white at 100%; glows green when active"),
                ("PT button",             "toggle programmer time: click to set 2s fade on all cues; click again to turn off"),
                ("flash button (fader)",    "hold for flash on; release for flash off — button shows ■ FLASH while held"),
            ]),
            ("fixture dim panel (right column)", [
                ("sliders",               "per-fixture master dim — drag to set; writes directly into programmer layer"),
                ("all button",            "select all fixtures (convenience shortcut for fixture dim context)"),
                ("sync",                  "sliders auto-update from live merged output when not being dragged"),
            ]),
        ]

        with dpg.window(tag="keys_window", label="keyboard & command reference",
                        width=720, height=560, show=False,
                        pos=(240, 80), no_collapse=False):
            dpg.add_text("command reference", color=_C_ACCENT)
            dpg.add_separator()
            # Scrolling ON (was off) — this list grows as commands are added, and
            # with no_scrollbar the overflow was silently unreachable.
            with dpg.child_window(width=-1, height=-1, border=False):
                for section, rows in _S:
                    dpg.add_text(section, color=_C_ACCENT)
                    dpg.add_separator()
                    with dpg.table(header_row=False,
                                   borders_innerV=True,
                                   policy=dpg.mvTable_SizingStretchProp):
                        dpg.add_table_column(label="cmd",  init_width_or_weight=0.42)
                        dpg.add_table_column(label="desc", init_width_or_weight=0.58)
                        for cmd, desc in rows:
                            with dpg.table_row():
                                # wrap= so long command strings (e.g. the
                                # "1 AT YELLOW / ORANGE / ..." shorthand rows)
                                # break onto a second line instead of being
                                # silently cut off at the column edge with no
                                # way to read the rest.
                                dpg.add_text(cmd,  color=_C_TEXT, wrap=280)
                                dpg.add_text(desc, color=_C_DIM,  wrap=380)
                    dpg.add_spacer(height=6)
    def _build_cue_timing_popup(self):
        """Floating cue timing editor — fade/delay/follow/fxout + note for active cue."""
        _tw = 220
        with dpg.window(tag="cue_timing_window", label="cue timing",
                        width=320, height=190, show=False,
                        pos=(10, 140), no_collapse=False, no_resize=False):
            with dpg.group(horizontal=True):
                dpg.add_text("cue:", color=_C_DIM)
                dpg.add_text("—", tag="cue_timing_label", color=_C_ACCENT)
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_drag_float(tag="cue_fade_input", label="fade s",
                                   default_value=0.0, min_value=0.0, max_value=30.0,
                                   speed=0.05, format="%.2f", width=100,
                                   callback=self._on_cue_fade_edit)
                dpg.add_drag_float(tag="cue_delay_input", label="dly  s",
                                   default_value=0.0, min_value=0.0, max_value=30.0,
                                   speed=0.05, format="%.2f", width=100,
                                   callback=self._on_cue_delay_edit)
            with dpg.group(horizontal=True):
                dpg.add_drag_float(tag="cue_follow_input", label="auto→s",
                                   default_value=0.0, min_value=0.0, max_value=300.0,
                                   speed=0.05, format="%.2f", width=100,
                                   callback=self._on_cue_follow_edit)
                dpg.add_drag_float(tag="cue_fxoutfade_input", label="fxout s",
                                   default_value=0.0, min_value=0.0, max_value=30.0,
                                   speed=0.05, format="%.2f", width=100,
                                   callback=self._on_cue_fxoutfade_edit)
            dpg.add_input_text(tag="cue_note_input", label="note",
                               hint="production note...", width=_tw,
                               callback=self._on_cue_note_edit)
    def _build_changelog_popup(self):
        """Floating changelog viewer — hidden by default, opened via 'log' button."""
        with dpg.window(tag="changelog_window", label="changelog",
                        width=760, height=560, show=False,
                        pos=(260, 90), no_collapse=False):
            dpg.add_text("what's changed", color=_C_ACCENT)
            dpg.add_separator()
            with dpg.child_window(tag="changelog_scroll", width=-1, height=-1, border=False):
                dpg.add_group(tag="changelog_group")
            self._refresh_changelog_popup()
    def _refresh_changelog_popup(self):
        """Reload changelog.json and rebuild the entry list — called each time the popup opens."""
        try:
            dpg.delete_item("changelog_group", children_only=True)
        except Exception:
            return   # popup not built yet

        doc = _read_file(ShowFile.CHANGELOG)
        entries = doc.get("entries", []) if doc else []
        if not entries:
            dpg.add_text("(no changelog entries yet)", color=_C_DIM, parent="changelog_group")
            return

        # Most recent first — entries are appended chronologically as written.
        for entry in reversed(entries):
            date    = entry.get("date", "")
            summary = entry.get("summary", "(no summary)")
            details = entry.get("details", [])
            with dpg.group(parent="changelog_group"):
                dpg.add_text(f"{date} — {summary}", color=_C_TEXT, wrap=700)
                for d in details:
                    dpg.add_text(f"    • {d}", color=_C_DIM, wrap=700)
                dpg.add_spacer(height=8)
    def _build_pages_popup(self):
        """Floating pages editor — assign stacks to named pages."""
        self._pages_current = 1   # currently viewed page number

        with dpg.window(tag="pages_window", label="pages",
                        width=520, height=460, show=False,
                        pos=(220, 130), no_collapse=False):
            # ── Header row ───────────────────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("page", color=_C_DIM)
                dpg.add_input_int(tag="pg_sel_num", label="", width=48,
                                  default_value=1, min_value=1, max_value=99,
                                  step=0, callback=self._on_page_sel_change)
                dpg.add_spacer(width=6)
                dpg.add_input_text(tag="pg_name_input", label="", width=180,
                                   hint="page name", default_value="page 1")
                dpg.add_button(label="rename", width=70,
                               callback=self._on_page_rename)
                dpg.add_spacer(width=6)
                dpg.add_button(label="new page", width=80,
                               callback=self._on_page_new)
                dpg.add_spacer(width=4)
                dpg.add_button(label="del page", width=80,
                               callback=self._on_page_delete)

            dpg.add_separator()

            # ── stack list for selected page ──────────────────
            dpg.add_text("stacks on this page:", color=_C_DIM)
            with dpg.child_window(tag="pg_cs_list", width=-1, height=210,
                                  border=True, no_scrollbar=False):
                dpg.add_group(tag="pg_cs_rows")   # rows rebuilt by _refresh_pages_table

            dpg.add_separator()

            # ── Add stack row ─────────────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("add:", color=_C_DIM)
                cs_items = self._cs_combo_items()
                dpg.add_combo(items=cs_items, tag="pg_add_cs_combo",
                              default_value=cs_items[0] if cs_items else "",
                              width=290)
                dpg.add_button(label="add to page", width=110,
                               callback=self._on_page_add_cs)

        self._refresh_pages_table()
    def _cs_combo_items(self):
        """Return list of 'ID — Name' strings for all stacks in the pool."""
        if not self._stack_pool:
            return []
        items = []
        for sid in sorted(self._stack_pool.stacks.keys()):
            stk = self._stack_pool.stacks[sid]
            items.append(f"{sid} — {stk.name}")
        return items
    def _refresh_pages_table(self):
        """Rebuild the stack list for the currently selected page."""
        try:
            dpg.delete_item("pg_cs_rows", children_only=True)
        except Exception:
            return
        if not self._fader_pool:
            return

        n    = self._pages_current
        page = self._fader_pool.pages.get(n)
        if not page:
            dpg.add_text("(page not created yet — add a stack to create it)",
                         parent="pg_cs_rows", color=_C_DIM)
            return

        cs_ids = page.get('stacks', [])
        if not cs_ids:
            dpg.add_text("— no stacks on this page —",
                         parent="pg_cs_rows", color=_C_DIM)
            return

        for cs_id in cs_ids:
            stk   = self._stack_pool.get(cs_id) if self._stack_pool else None
            lbl  = f"{cs_id} — {stk.name}" if stk else f"{cs_id} — (not found)"
            with dpg.group(horizontal=True, parent="pg_cs_rows"):
                dpg.add_button(label="×", width=24,
                               callback=lambda s, a, u: self._on_page_remove_cs(u),
                               user_data=cs_id)
                dpg.add_text(lbl)

        # Refresh the page-name field to match loaded data
        try:
            dpg.set_value("pg_name_input", page.get('name', f"page {n}"))
        except Exception:
            pass
    def _on_page_sel_change(self):
        self._pages_current = int(dpg.get_value("pg_sel_num"))
        page = self._fader_pool.pages.get(self._pages_current) if self._fader_pool else None
        try:
            dpg.set_value("pg_name_input",
                          page['name'] if page else f"page {self._pages_current}")
        except Exception:
            pass
        self._refresh_pages_table()
    def _on_page_rename(self):
        n    = self._pages_current
        name = dpg.get_value("pg_name_input").strip()
        if not name:
            return
        if self._cmd:
            self._cmd(f"PAGE {n} NAME {name}")
        self._log(f"> page {n} renamed to '{name}'")
    def _on_page_new(self):
        # Find next unused page number
        existing = set(self._fader_pool.all_pages()) if self._fader_pool else set()
        n = 1
        while n in existing:
            n += 1
        if self._fader_pool:
            self._fader_pool.get_page(n)   # creates it
            ShowFile.save_fader_pages(self._fader_pool)
        self._pages_current = n
        try:
            dpg.set_value("pg_sel_num", n)
            dpg.set_value("pg_name_input", f"page {n}")
        except Exception:
            pass
        self._refresh_pages_table()
        self._log(f"> page {n} created")
    def _on_page_delete(self):
        n = self._pages_current
        if self._cmd:
            self._cmd(f"PAGE {n} DELETE")
        self._log(f"> page {n} deleted")
        self._refresh_pages_table()
    def _on_page_add_cs(self):
        raw = dpg.get_value("pg_add_cs_combo")
        if not raw:
            return
        try:
            cs_id = int(raw.split("—")[0].strip())
        except (ValueError, IndexError):
            return
        n = self._pages_current
        if self._cmd:
            result = self._cmd(f"PAGE {n} ADD stk {cs_id}")
            if result:
                self._log(f"  {result}")
        self._refresh_pages_table()
    def _on_page_remove_cs(self, cs_id):
        n = self._pages_current
        if self._cmd:
            result = self._cmd(f"PAGE {n} REMOVE stk {cs_id}")
            if result:
                self._log(f"  {result}")
        self._refresh_pages_table()
    def _cue_timing_target(self):
        """Return (Stack, Cue) for the currently active cue, or (None, None)."""
        active_n = self._active_fader[0] if self._active_fader else 1
        stk = self._stack_pool.get(active_n) if self._stack_pool else None
        if not stk or stk.current is None:
            return None, None
        cue = stk.cues.get(stk.current)
        return stk, cue
    def _on_cue_fade_edit(self, _sender, value, _user_data):
        _, cue = self._cue_timing_target()
        if cue and self._cmd:
            self._cmd(f"CUE {cue.cue_number} FADE {value:.2f}")
    def _on_cue_delay_edit(self, _sender, value, _user_data):
        _, cue = self._cue_timing_target()
        if cue and self._cmd:
            self._cmd(f"CUE {cue.cue_number} DELAY {value:.2f}")
    def _on_cue_follow_edit(self, _sender, value, _user_data):
        _, cue = self._cue_timing_target()
        if cue and self._cmd:
            self._cmd(f"CUE {cue.cue_number} FOLLOW {value:.2f}")
    def _on_cue_note_edit(self, _sender, value, _user_data):
        _, cue = self._cue_timing_target()
        if cue:
            cue.note = value
            if self._save:
                self._save()
    def _on_cue_fxoutfade_edit(self, _sender, value, _user_data):
        _, cue = self._cue_timing_target()
        if cue and self._cmd:
            self._cmd(f"CUE {cue.cue_number} FXOUTFADE {value:.2f}")
