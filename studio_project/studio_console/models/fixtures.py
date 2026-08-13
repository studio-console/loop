"""Studio Console fixture/patch data models — extracted verbatim from
studio_project.py (Block 1: Fixture Profile System + SubFixture +
MasterFixture). Pure move, zero behavior change. No circular-import
concerns here — these classes don't reference anything defined later in
studio_project.py or in any other studio_console module.
"""

import os
import json
import copy
import random

# ------------------------------------------------------------
# FixtureProfile — the blueprint for a fixture type
# ------------------------------------------------------------

class FixtureProfile:
    """
    Defines the channel layout and pixel structure of a fixture type.
    Think of this as the fixture type library entry in MA3.

    channels        — ordered list of parameter names per pixel
                      e.g. ["red", "green", "blue"]
                      For moving heads: ["dimmer", "pan", "pan_fine", "tilt", "tilt_fine", ...]
    pixel_count     — how many independent pixels/cells (1 for single cell)
    has_master_dim  — does the fixture have a physical master dimmer channel
                      before the pixel data? (False for your SGM tubes)
    attributes      — {dmx_offset (1-based): attribute_name} from GDTF or JSON
                      e.g. {1: "dimmer", 2: "pan", 3: "pan_fine", 4: "tilt"}
    manufacturer    — manufacturer name (populated from GDTF)
    gdtf_source     — path to source .gdtf file if loaded from GDTF
    """
    def __init__(self, name, channels, pixel_count=1, has_master_dim=False,
                 attributes=None, manufacturer="", gdtf_source=None):
        self.name           = name
        self.channels       = channels          # e.g. ["red","green","blue"]
        self.pixel_count    = pixel_count       # e.g. 54
        self.has_master_dim = has_master_dim
        self.attributes     = attributes or {}  # {offset: attr_name} — GDTF-sourced
        self.manufacturer   = manufacturer
        self.gdtf_source    = gdtf_source
        self.channels_per_pixel = len(channels)
        self.total_channels = (
            pixel_count * self.channels_per_pixel +
            (1 if has_master_dim else 0)
        )

    def is_rgb(self):
        """True if this profile's channels include red/green/blue."""
        return "red" in self.channels and "green" in self.channels

    def is_moving(self):
        """True if this profile includes pan/tilt channels."""
        return "pan" in self.channels or "pan" in self.attributes.values()

    def __repr__(self):
        mfr = f"{self.manufacturer} " if self.manufacturer else ""
        return (f"[Profile] {mfr}{self.name} | "
                f"{self.pixel_count}px × "
                f"{self.channels_per_pixel}ch = "
                f"{self.total_channels} DMX channels total")


# ------------------------------------------------------------
# FixtureLibrary — registry of all known profiles
# Profiles can be defined in code or loaded from JSON files
# ------------------------------------------------------------

class FixtureLibrary:
    """
    Central registry of all FixtureProfiles.
    Profiles defined here in code are always available.
    External JSON profiles can be loaded from a folder.
    """
    def __init__(self):
        self.profiles = {}
        self._register_builtins()

    def _register_builtins(self):
        """
        Built-in profiles defined in code.
        Add new fixture types here as you acquire them.
        """
        self.register(FixtureProfile(
            name        = "SGM_RGB_54",
            channels    = ["red", "green", "blue"],
            pixel_count = 54,
            has_master_dim = False
        ))

        # Generic single-cell RGB (useful for simple pars etc)
        self.register(FixtureProfile(
            name        = "Generic_RGB",
            channels    = ["red", "green", "blue"],
            pixel_count = 1,
            has_master_dim = False
        ))

        # Generic single-cell RGBW (ready for future fixtures)
        self.register(FixtureProfile(
            name        = "Generic_RGBW",
            channels    = ["red", "green", "blue", "white"],
            pixel_count = 1,
            has_master_dim = False
        ))

        # Generic moving head — dimmer + pan/tilt + gobo + color wheel
        self.register(FixtureProfile(
            name        = "Generic_Moving",
            channels    = ["dimmer", "pan", "tilt", "pan_fine", "tilt_fine",
                           "gobo", "color", "zoom", "focus", "iris", "strobe", "control"],
            pixel_count = 1,
            has_master_dim = False
        ))

        # Generic moving wash — dimmer + pan/tilt + RGB
        self.register(FixtureProfile(
            name        = "Generic_Moving_Wash",
            channels    = ["dimmer", "pan", "tilt", "pan_fine", "tilt_fine",
                           "red", "green", "blue", "zoom"],
            pixel_count = 1,
            has_master_dim = False
        ))

    def register(self, profile):
        """Add a profile to the library."""
        self.profiles[profile.name] = profile
        print(f"Profile registered: {profile}")

    def get(self, name):
        """Look up a profile by name."""
        return self.profiles.get(name, None)

    def load_from_folder(self, folder_path):
        """
        Load fixture profiles from JSON files in a folder.
        Each .json file defines one profile.

        JSON format:
        {
            "name": "My_Fixture",
            "channels": ["red", "green", "blue"],
            "pixel_count": 1,
            "has_master_dim": false,
            "manufacturer": "Acme",
            "attributes": {"1": "dimmer", "2": "pan", "3": "tilt"}
        }
        """
        if not os.path.exists(folder_path):
            return

        loaded = 0
        for filename in os.listdir(folder_path):
            if filename.endswith(".json"):
                filepath = os.path.join(folder_path, filename)
                try:
                    with open(filepath, "r") as f:
                        data = json.load(f)
                    raw_attrs = data.get("attributes", {})
                    profile = FixtureProfile(
                        name           = data["name"],
                        channels       = data["channels"],
                        pixel_count    = data.get("pixel_count", 1),
                        has_master_dim = data.get("has_master_dim", False),
                        attributes     = {int(k): v for k, v in raw_attrs.items()},
                        manufacturer   = data.get("manufacturer", ""),
                    )
                    self.register(profile)
                    loaded += 1
                except Exception as e:
                    print(f"Failed to load {filename}: {e}")

        if loaded:
            print(f"Loaded {loaded} JSON profile(s) from {folder_path}")

    def load_gdtf(self, filepath, mode_name=None):
        """Parse a .gdtf file and register the resulting profile."""
        profile = GDTFLoader.load(filepath, mode_name=mode_name)
        if profile:
            self.register(profile)
        return profile

    def load_gdtf_folder(self, folder_path):
        """Load all .gdtf files in a folder into this library."""
        if not os.path.exists(folder_path):
            return 0
        count = 0
        for fname in os.listdir(folder_path):
            if fname.lower().endswith('.gdtf'):
                profile = GDTFLoader.load(os.path.join(folder_path, fname))
                if profile:
                    self.register(profile)
                    count += 1
        if count:
            print(f"Loaded {count} GDTF profile(s) from {folder_path}")
        return count

    def print_library(self):
        print("\n===== FIXTURE LIBRARY =====")
        for profile in self.profiles.values():
            print(f"  {profile}")
        print("===========================\n")


# ------------------------------------------------------------
# GDTFLoader — imports .gdtf fixture files into FixtureProfiles
#
# GDTF (General Device Type Format) files are ZIP archives
# containing description.xml.  Drop .gdtf files into
# studio_data/gdtf/ and they are auto-loaded at startup.
#
# Spec: https://gdtf-share.com/wiki/GDTF_File_Description
# ------------------------------------------------------------

class GDTFLoader:
    """
    Parses .gdtf files and returns FixtureProfile objects.

    A .gdtf file is a ZIP archive.  The only file we need is
    description.xml at the archive root, which describes all DMX
    modes and their channel-to-attribute mappings.

    Pixel/LED-array fixtures (GeometryArray) are supported as
    single-cell for now; pixel_count detection is a TODO once
    multi-cell GDTF fixtures are in use.
    """

    @staticmethod
    def load(filepath, mode_name=None):
        """
        Parse one .gdtf file.
        mode_name — DMX mode to use (None = first available mode).
        Returns a FixtureProfile or None on error.
        """
        import zipfile
        import xml.etree.ElementTree as ET

        try:
            with zipfile.ZipFile(str(filepath), 'r') as z:
                with z.open('description.xml') as f:
                    tree = ET.parse(f)
        except Exception as e:
            print(f"GDTF load error ({filepath}): {e}")
            return None

        root = tree.getroot()
        ft   = root.find('FixtureType')
        if ft is None:
            print(f"GDTF: no FixtureType element in {filepath}")
            return None

        name         = ft.get('Name', 'Unknown')
        manufacturer = ft.get('Manufacturer', '')

        # Locate the requested DMX mode (fall back to first)
        modes = ft.findall('./DMXModes/DMXMode')
        if not modes:
            print(f"GDTF: no DMX modes found in {name}")
            return None
        mode = next((m for m in modes if m.get('Name') == mode_name), None) or modes[0]

        # Build attribute map and ordered channel list from DMXChannels
        attributes    = {}   # {offset_int: attribute_name_str}
        max_offset    = 0

        for ch in mode.findall('./DMXChannels/DMXChannel'):
            offset_str = ch.get('Offset', '')
            if not offset_str or offset_str.lower() == 'none':
                continue
            # Offset can be "5" (8-bit) or "5,6" (16-bit coarse+fine)
            offsets = []
            for part in offset_str.split(','):
                part = part.strip()
                if part.isdigit():
                    offsets.append(int(part))
            if not offsets:
                continue

            lc   = ch.find('LogicalChannel')
            attr = (lc.get('Attribute', 'unknown') if lc is not None else 'unknown').lower()

            attributes[offsets[0]] = attr
            if len(offsets) > 1:
                attributes[offsets[1]] = attr + '_fine'
            max_offset = max(max_offset, max(offsets))

        if max_offset == 0:
            print(f"GDTF: no usable DMX channels in {name}")
            return None

        # Build ordered channel list (gaps filled with placeholder names)
        channels = [attributes.get(i + 1, f'ch{i + 1}') for i in range(max_offset)]

        # Detect colour and dimmer presence for output-mixer hints
        has_rgb = 'red' in attributes.values() and 'green' in attributes.values()

        profile = FixtureProfile(
            name           = name,
            channels       = channels,
            pixel_count    = 1,           # TODO: detect GeometryArray pixel count
            has_master_dim = False,       # dimmer is a channel for GDTF fixtures
            attributes     = attributes,
            manufacturer   = manufacturer,
            gdtf_source    = str(filepath),
        )
        mode_label = mode.get('Name', '?')
        print(f"GDTF loaded: {manufacturer} {name}  "
              f"({max_offset} ch, mode={mode_label}, rgb={has_rgb})")
        return profile


# ------------------------------------------------------------
# SubFixture — a single pixel/cell within a fixture
# Channel layout comes from the profile, not hardcoded
# ------------------------------------------------------------

class SubFixture:
    """
    A single pixel or cell within a MasterFixture.
    Channels are dynamically created from the fixture profile.
    e.g. for SGM_RGB_54, each SubFixture has red, green, blue.
    """
    def __init__(self, master_id, sub_index, profile):
        self.master_id  = master_id
        self.sub_index  = sub_index
        self.fixture_id = f"{master_id}.{sub_index}"
        self.profile    = profile

        # Dynamically create channel values from profile
        # e.g. {"red": 0, "green": 0, "blue": 0}
        self.channels = {ch: 0 for ch in profile.channels}

        # Virtual dimmer — always present regardless of profile
        self.virtual_dimmer = 1.0

        # Multipatch outputs: [{"universe": int, "address": int}, ...]
        self.outputs = []

        self.is_dirty = False

    def add_output(self, universe, address):
        self.outputs.append({"universe": universe, "address": address})

    def set_channel(self, channel, value):
        """Set a single channel by name. e.g. set_channel('red', 255)"""
        if channel in self.channels:
            self.channels[channel] = max(0, min(255, value))
            self.is_dirty = True

    def set_rgb(self, r, g, b):
        """Convenience method for RGB profiles."""
        self.set_channel("red",   r)
        self.set_channel("green", g)
        self.set_channel("blue",  b)

    def set_dimmer(self, level):
        """Accepts 0.0 to 1.0"""
        self.virtual_dimmer = max(0.0, min(1.0, level))
        self.is_dirty = True

    def get_output(self, master_dimmer=1.0):
        """
        Returns final DMX values for all channels.
        Virtual dimmer (sub + master) applied to colour channels.
        Returns dict: {"red": 127, "green": 0, "blue": 64}
        """
        combined_dim = self.virtual_dimmer * master_dimmer
        result = {}
        for ch, val in self.channels.items():
            if ch in ("red", "green", "blue", "white", "amber"):
                result[ch] = int(val * combined_dim)
            else:
                # Non-colour channels (pan, tilt etc) pass through unscaled
                result[ch] = val
        return result

    def get_dmx_values(self, master_dimmer=1.0):
        """
        Returns ordered list of DMX values matching profile channel order.
        This is what gets sent to the network engine.
        e.g. [127, 0, 64] for RGB
        """
        output = self.get_output(master_dimmer)
        return [output[ch] for ch in self.profile.channels]

    def clear_dirty(self):
        self.is_dirty = False

    def __repr__(self):
        output = self.get_output()
        ch_str = " ".join(f"{k}={v}" for k, v in output.items())
        outputs = ", ".join(
            f"U{o['universe']}@{o['address']}" for o in self.outputs
        )
        return f"[{self.fixture_id}] {ch_str} Dim:{self.virtual_dimmer:.0%} | {outputs}"


# ------------------------------------------------------------
# MasterFixture — a patched instance of a FixtureProfile
# ------------------------------------------------------------

class MasterFixture:
    """
    One physical fixture — a patched instance of a FixtureProfile.
    Controls all its SubFixtures as a unit.
    Selecting this in the programmer auto-selects all sub-fixtures.
    """
    def __init__(self, fixture_id, name, profile):
        self.fixture_id     = fixture_id
        self.name           = name
        self.profile        = profile
        self.pixel_count    = profile.pixel_count
        self.virtual_dimmer = 1.0
        self.is_dirty       = False
        self.sub_fixtures   = {}

    def build_sub_fixtures(self):
        """Creates all SubFixture objects based on the profile."""
        for i in range(1, self.pixel_count + 1):
            self.sub_fixtures[i] = SubFixture(
                self.fixture_id, i, self.profile
            )

    def get_sub(self, sub_index):
        return self.sub_fixtures.get(sub_index, None)

    def all_subs(self):
        return [self.sub_fixtures[i] for i in sorted(self.sub_fixtures)]

    def set_rgb(self, r, g, b):
        """Push RGB to all sub-fixtures (LTP master control)."""
        for sub in self.all_subs():
            sub.set_rgb(r, g, b)
        self.is_dirty = True

    def set_channel(self, channel, value):
        """Push any channel value to all sub-fixtures."""
        for sub in self.all_subs():
            sub.set_channel(channel, value)
        self.is_dirty = True

    def set_dimmer(self, level):
        """Master dimmer — stacks with sub-fixture dimmers."""
        self.virtual_dimmer = max(0.0, min(1.0, level))
        self.is_dirty = True

    def get_dmx_output(self):
        """
        Returns full DMX output for this fixture.
        Dict: { sub_index: [dmx_val, dmx_val, dmx_val] }
        """
        return {
            i: sub.get_dmx_values(self.virtual_dimmer)
            for i, sub in self.sub_fixtures.items()
        }

    def clear_dirty(self):
        self.is_dirty = False
        for sub in self.all_subs():
            sub.clear_dirty()

    def __repr__(self):
        return (f"[Fixture {self.fixture_id}] {self.name} | "
                f"Profile: {self.profile.name} | "
                f"{self.pixel_count}px | "
                f"MasterDim:{self.virtual_dimmer:.0%}")


# ============================================================
# Block 2: The Patch
# ============================================================

class Patch:
    def __init__(self, library):
        self.library  = library     # Reference to FixtureLibrary
        self.fixtures = {}          # { fixture_id: MasterFixture }

    def patch_fixture(self, fixture_id, name, profile_name,
                      universe, start_address,
                      extra_outputs=None):
        """
        Patch a fixture using a named profile from the library.

        fixture_id    — integer ID (e.g. 1)
        name          — human label (e.g. "Tube 1")
        profile_name  — must match a registered FixtureProfile name
        universe      — primary DMX universe
        start_address — first DMX address
        extra_outputs — optional multipatch list
                        e.g. [{"universe": 3, "address": 1}]
        """
        profile = self.library.get(profile_name)
        if not profile:
            print(f"error: Profile '{profile_name}' not found in library.")
            return None

        master = MasterFixture(fixture_id, name, profile)
        master.build_sub_fixtures()

        # Assign DMX addresses sequentially
        address = start_address
        chs     = profile.channels_per_pixel

        for sub in master.all_subs():
            sub.add_output(universe, address)

            if extra_outputs:
                offset = address - start_address
                for extra in extra_outputs:
                    sub.add_output(
                        extra["universe"],
                        extra["address"] + offset
                    )
            address += chs

        self.fixtures[fixture_id] = master
        end_address = address - 1
        print(f"Patched: {master} | U{universe} @ {start_address}-{end_address}")
        return master

    def get(self, fixture_id):
        return self.fixtures.get(fixture_id, None)

    def get_sub(self, master_id, sub_index):
        master = self.get(master_id)
        if master:
            return master.get_sub(sub_index)
        return None

    def get_range(self, start_id, end_id):
        return [
            self.fixtures[i]
            for i in range(start_id, end_id + 1)
            if i in self.fixtures
        ]

    def get_multiple(self, id_list):
        return [
            self.fixtures[i]
            for i in id_list
            if i in self.fixtures
        ]

    def all_fixtures(self):
        return [self.fixtures[i] for i in sorted(self.fixtures)]

    def print_patch(self):
        print("\n===== PATCH =====")
        for master in self.all_fixtures():
            print(master)
            subs  = master.all_subs()
            first = subs[0]
            last  = subs[-1]
            print(f"  Pixels {first.fixture_id} → {last.fixture_id}")
            print(f"  First pixel: {first}")
            print(f"  Last pixel:  {last}")
        print("=================\n")

# (first programmer draft removed — active class is below)
# ============================================================
# STUDIO CONSOLE - Core Object Model
# Block 3 UPDATE: programmer
# Added: self.disabled dict, REMOVE and ENABLE commands
# ============================================================

class programmer:
    def __init__(self, patch):
        self.patch     = patch
        self.selection = []
        self.data      = {}         # Active parameters — will be recorded/output
        self.disabled  = {}         # removed parameters — remembered but inactive
        self._clear_stage     = 0   # 0=fresh, 1=values cleared, 2=selection cleared
        self._last_clear_time = 0.0
        self._undo_stack      = []  # list of (data_snapshot, selection_ids) dicts
        self._UNDO_MAX        = 20
        self.live_fades       = []  # [{fid,channel,src,dst,start,duration}, ...] for AT…IN fades

    def _push_undo(self):
        """snapshot current programmer state onto the undo stack."""
        self._undo_stack.append({
            'data':      copy.deepcopy(self.data),
            'disabled':  copy.deepcopy(self.disabled),
            'selection': [f.fixture_id for f in self.selection],
        })
        if len(self._undo_stack) > self._UNDO_MAX:
            self._undo_stack.pop(0)

    def undo(self):
        """Restore the previous programmer snapshot. Returns result string."""
        if not self._undo_stack:
            return "nothing to undo"
        snap = self._undo_stack.pop()
        # Mutate self.data/self.disabled in place (clear + update) rather than
        # rebinding them to new dict objects. OutputState.link_programmer()
        # aliases output_state.programmer_layer directly to this same dict, so
        # a rebind here would silently desync live DMX output (and the output
        # monitor GUI) from the programmer for the rest of the session --
        # they'd keep reading the old, now-abandoned dict object forever.
        self.data.clear()
        self.data.update(snap['data'])
        self.disabled.clear()
        self.disabled.update(snap['disabled'])
        # Restore selection by fixture ID
        sel_ids = set(snap['selection'])
        restored = []
        for m in self.patch.all_fixtures():
            if m.fixture_id in sel_ids:
                restored.append(m)
                restored += m.all_subs()
        self.selection = restored
        return f"undo — programmer restored  ({len(self._undo_stack)} step(s) remaining)"

    # ----------------------------------------------------------
    # Selection Management
    # ----------------------------------------------------------

    def select(self, fixtures):
        """
        Set the current selection.
        Selecting a MasterFixture auto-selects all its SubFixtures.
        """
        expanded = []
        for f in fixtures:
            if isinstance(f, MasterFixture):
                expanded.append(f)
                expanded += f.all_subs()
            else:
                expanded.append(f)

        self.selection = expanded
        masters = [f for f in expanded if isinstance(f, MasterFixture)]
        subs    = [f for f in expanded if isinstance(f, SubFixture)]
        print(f"Selected: {len(masters)} master(s), {len(subs)} sub-fixture(s)")

    def clear_selection(self):
        self.selection = []

    def clear_programmer(self):
        """Full programmer clear — wipes selection, data and disabled."""
        for fid in self.data:
            fixture = self._get_fixture_by_fid(fid)
            if fixture:
                fixture.clear_dirty()
                # Reset virtual_dimmer so a previous AT DIM 0 doesn't persist
                # as the _base_dim fallback during cue playback.
                if hasattr(fixture, 'virtual_dimmer'):
                    fixture.virtual_dimmer = 1.0
        self.selection = []
        self.data.clear()
        self.disabled  = {}
        self._clear_stage = 0
        print("programmer cleared.")

    def do_clear(self):
        """Three-stage CLEAR.
        Tap 1 — clear fixture selection.
        Tap 2 — clear programmer data (stored AT values).
        Tap 3 — clear programmer output (live fades + FX layers still running).
        Stage resets automatically if more than 2 s passes between taps.
        """
        import time
        now = time.time()
        if now - self._last_clear_time > 2.0:
            self._clear_stage = 0
        self._last_clear_time = now

        if self._clear_stage == 0:
            self.selection = []
            # Also release any fx_kill overrides on the first tap —
            # fx_kill is an instantaneous state, not a recorded value.
            for vals in self.data.values():
                vals.pop('fx_kill', None)
            self._clear_stage = 1
            return "selection cleared  (clear again to wipe programmer)"
        elif self._clear_stage == 1:
            for fid in list(self.data.keys()):
                fixture = self._get_fixture_by_fid(fid)
                if fixture:
                    fixture.clear_dirty()
                    if hasattr(fixture, 'virtual_dimmer'):
                        fixture.virtual_dimmer = 1.0
            self.data.clear()
            self.disabled = {}
            self._clear_stage = 2
            return "programmer cleared  (clear again to clear programmer output)"
        else:
            self._clear_stage = 0
            self.live_fades.clear()
            return "programmer output cleared"

    def _get_fixture_by_fid(self, fid_str):
        """Helper — looks up a fixture or sub-fixture by its string ID."""
        if '.' in fid_str:
            parts = fid_str.split('.')
            return self.patch.get_sub(int(parts[0]), int(parts[1]))
        else:
            return self.patch.get(int(fid_str))

    # ----------------------------------------------------------
    # Parameter Setting
    # ----------------------------------------------------------

    def _ensure_data(self, fixture):
        fid = str(fixture.fixture_id)
        if fid not in self.data:
            self.data[fid] = {}

    def _get_sub_selection(self):
        return [f for f in self.selection if isinstance(f, SubFixture)]

    def set_dimmer(self, level):
        self._push_undo()
        value = max(0.0, min(1.0, level / 100))
        for f in self.selection:
            if isinstance(f, MasterFixture):
                self._ensure_data(f)
                self.data[str(f.fixture_id)]['dim'] = value
                # Re-enable if it was disabled
                fid = str(f.fixture_id)
                if fid in self.disabled:
                    self.disabled[fid].pop('dim', None)
                f.set_dimmer(value)
        self._print_programmer()

    def set_rgb(self, r, g, b):
        self._push_undo()
        for f in self._get_sub_selection():
            self._ensure_data(f)
            fid = str(f.fixture_id)
            self.data[fid]['red']   = r
            self.data[fid]['green'] = g
            self.data[fid]['blue']  = b
            # Re-enable if they were disabled
            if fid in self.disabled:
                self.disabled[fid].pop('red',   None)
                self.disabled[fid].pop('green', None)
                self.disabled[fid].pop('blue',  None)
            f.set_rgb(r, g, b)
        self._print_programmer()

    def set_channel(self, channel, value):
        if channel == 'dim':
            self.set_dimmer(value)
            return
        self._push_undo()
        for f in self._get_sub_selection():
            self._ensure_data(f)
            fid = str(f.fixture_id)
            self.data[fid][channel] = value
            if fid in self.disabled:
                self.disabled[fid].pop(channel, None)
            f.set_channel(channel, value)
        self._print_programmer()

    # ----------------------------------------------------------
    # Remove / Enable
    # ----------------------------------------------------------

    def remove_parameter(self, channel):
        """
        Remove a parameter from active programmer data.
        Value moves to disabled dict — recoverable via ENABLE.
        Does nothing if no selection.
        channel: 'red','green','blue','dim', or 'all'
        """
        if not self.selection:
            return

        targets = self._get_targets_for_channel(channel)

        for f in targets:
            fid = str(f.fixture_id)
            if fid not in self.data:
                continue

            if channel == 'all':
                # Move entire entry to disabled
                if fid not in self.disabled:
                    self.disabled[fid] = {}
                self.disabled[fid].update(self.data[fid])
                self.data[fid] = {}
            else:
                if channel in self.data[fid]:
                    if fid not in self.disabled:
                        self.disabled[fid] = {}
                    self.disabled[fid][channel] = self.data[fid].pop(channel)

        print(f"removed '{channel}' from programmer for current selection.")
        self._print_programmer()

    def enable_parameter(self, channel):
        """
        Re-enable a previously removed parameter.
        Value moves back from disabled to active data.
        Does nothing if no selection.
        channel: 'red','green','blue','dim', or 'all'
        """
        if not self.selection:
            return

        targets = self._get_targets_for_channel(channel)

        for f in targets:
            fid = str(f.fixture_id)
            if fid not in self.disabled:
                continue

            if channel == 'all':
                # Move entire disabled entry back to active
                if fid not in self.data:
                    self.data[fid] = {}
                self.data[fid].update(self.disabled[fid])
                self.disabled[fid] = {}
            else:
                if channel in self.disabled[fid]:
                    if fid not in self.data:
                        self.data[fid] = {}
                    self.data[fid][channel] = self.disabled[fid].pop(channel)

        print(f"Enabled '{channel}' for current selection.")
        self._print_programmer()

    # Attribute channels stored on sub-fixtures (same as RGB)
    _ATTR_CHANNELS = frozenset({
        'pan', 'tilt', 'pan_fine', 'tilt_fine',
        'gobo', 'gobo_rot', 'gobo2', 'gobo2_rot',
        'zoom', 'focus', 'iris', 'shutter1', 'color',
        'prism', 'frost', 'animation', 'control', 'macro', 'dimmer',
    })

    def _get_targets_for_channel(self, channel):
        """
        Returns the right fixture objects for a given channel type.
        dim targets masters. RGB and attribute channels target sub-fixtures.
        All targets both.
        """
        if channel == 'dim':
            return [f for f in self.selection if isinstance(f, MasterFixture)]
        elif channel in ('red', 'green', 'blue', 'white', 'amber') or channel in self._ATTR_CHANNELS:
            return self._get_sub_selection()
        elif channel == 'all':
            return self.selection
        return []

    # ----------------------------------------------------------
    # Command Line Parser
    # ----------------------------------------------------------

    def execute(self, command_string):
        tokens = command_string.strip().upper().split()
        if not tokens:
            return

        # CLEAR
        if tokens == ['CLEAR']:
            self.clear_programmer()
            return

        # REMOVE <channel>
        if tokens[0] == 'REMOVE' and len(tokens) > 1:
            channel = self._parse_channel_token(tokens[1])
            if channel:
                self.remove_parameter(channel)
            return

        # ENABLE <channel>
        if tokens[0] == 'ENABLE' and len(tokens) > 1:
            channel = self._parse_channel_token(tokens[1])
            if channel:
                self.enable_parameter(channel)
            return

        # Split on AT (or auto-detect action start if AT is omitted)
        _ACTION_KEYWORDS = {'R', 'G', 'B', 'RED', 'GREEN', 'BLUE', 'FULL', 'OUT', 'DIM',
                             'WHITE', 'WARM', 'AMBER', 'YELLOW', 'ORANGE', 'CYAN',
                             'MAGENTA', 'PINK', 'UV', 'PURPLE', 'LIME', 'TEAL',
                             'PAN', 'TILT', 'PAN_FINE', 'TILT_FINE',
                             'GOBO', 'GOBO_ROT', 'GOBO2', 'GOBO2_ROT',
                             'ZOOM', 'FOCUS', 'IRIS', 'SHUTTER1',
                             'DIMMER', 'COLOR', 'PRISM', 'FROST', 'ANIMATION',
                             'CONTROL', 'MACRO', 'FAN', 'HUE', 'CT', 'FLIP',
                             'BRIGHTEST', 'DARKEST', 'AVERAGE', 'CLAMP', 'STEP', 'MIRROR',
                             'INVERT', 'SCALE', 'WOBBLE', 'NORMALIZE', 'COPY'}
        if 'AT' in tokens:
            at_index         = tokens.index('AT')
            selection_tokens = tokens[:at_index]
            action_tokens    = tokens[at_index + 1:]
        else:
            split_at = len(tokens)
            for idx, tok in enumerate(tokens):
                if tok in _ACTION_KEYWORDS:
                    split_at = idx
                    break
            selection_tokens = tokens[:split_at]
            action_tokens    = tokens[split_at:]

        selected = self._parse_selection(selection_tokens)
        if selected:
            self.select(selected)

        if action_tokens:
            # Detect trailing "IN <seconds>" for live programmer fade
            _fade_dur = None
            _act = list(action_tokens)
            if len(_act) >= 2 and _act[-2] == 'IN':
                try:
                    _fade_dur = float(_act[-1])
                    _act = _act[:-2]
                except ValueError:
                    pass

            if _fade_dur is not None and _fade_dur > 0 and self.selection:
                import time as _t
                # snapshot pre-action programmer state for the selection
                _pre = {}
                for f in self.selection:
                    fid = str(f.fixture_id)
                    if fid in self.data:
                        _pre[fid] = dict(self.data[fid])
                    if isinstance(f, MasterFixture):
                        for sub in f.all_subs():
                            sfid = str(sub.fixture_id)
                            if sfid in self.data:
                                _pre[sfid] = dict(self.data[sfid])
                # Apply action to learn the target values
                self._parse_action(_act)
                # Read post-action state for the selection
                _now = _t.monotonic()
                for f in self.selection:
                    fid = str(f.fixture_id)
                    for ch, dst_val in list(self.data.get(fid, {}).items()):
                        src_val = _pre.get(fid, {}).get(ch, dst_val)
                        if src_val != dst_val:
                            self.live_fades.append({
                                'fid': fid, 'channel': ch,
                                'src': src_val, 'dst': dst_val,
                                'start': _now, 'duration': _fade_dur,
                            })
                    if isinstance(f, MasterFixture):
                        for sub in f.all_subs():
                            sfid = str(sub.fixture_id)
                            for ch, dst_val in list(self.data.get(sfid, {}).items()):
                                src_val = _pre.get(sfid, {}).get(ch, dst_val)
                                if src_val != dst_val:
                                    self.live_fades.append({
                                        'fid': sfid, 'channel': ch,
                                        'src': src_val, 'dst': dst_val,
                                        'start': _now, 'duration': _fade_dur,
                                    })
                # Revert programmer to pre-action state; fades will fill in the values
                for fid, vals in _pre.items():
                    self.data[fid] = dict(vals)
                # Also remove keys that didn't exist in pre but now do (set to dst immediately via fade)
                for f in self.selection:
                    fid = str(f.fixture_id)
                    if fid not in _pre:
                        self.data.pop(fid, None)
                    if isinstance(f, MasterFixture):
                        for sub in f.all_subs():
                            sfid = str(sub.fixture_id)
                            if sfid not in _pre:
                                self.data.pop(sfid, None)
            else:
                self._parse_action(_act if _fade_dur is not None else action_tokens)

    def _parse_channel_token(self, token):
        """Maps command token to internal channel name."""
        mapping = {
            'R': 'red', 'G': 'green', 'B': 'blue',
            'DIM': 'dim', 'ALL': 'all',
            'RED': 'red', 'GREEN': 'green', 'BLUE': 'blue',
            'PAN': 'pan', 'TILT': 'tilt',
            'PAN_FINE': 'pan_fine', 'TILT_FINE': 'tilt_fine',
            'GOBO': 'gobo', 'GOBO_ROT': 'gobo_rot',
            'GOBO2': 'gobo2', 'GOBO2_ROT': 'gobo2_rot',
            'ZOOM': 'zoom', 'FOCUS': 'focus', 'IRIS': 'iris',
            'SHUTTER1': 'shutter1', 'COLOR': 'color',
            'PRISM': 'prism', 'FROST': 'frost', 'ANIMATION': 'animation',
            'CONTROL': 'control', 'MACRO': 'macro',
            'DIMMER': 'dimmer',
        }
        return mapping.get(token, None)

    def _parse_token_to_fixture(self, token):
        if '.' in token:
            parts = token.split('.')
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                return self.patch.get_sub(int(parts[0]), int(parts[1]))
        elif token.isdigit():
            return self.patch.get(int(token))
        return None

    def _parse_selection(self, tokens):
        selected = []
        i = 0
        while i < len(tokens):
            token = tokens[i]

            if token == '+':
                i += 1
                continue

            if token == 'ALL':
                selected += list(self.patch.all_fixtures())
                i += 1
                continue

            if token == 'ODD':
                selected += [m for m in self.patch.all_fixtures() if m.fixture_id % 2 == 1]
                i += 1
                continue

            if token == 'EVEN':
                selected += [m for m in self.patch.all_fixtures() if m.fixture_id % 2 == 0]
                i += 1
                continue

            if token in ('NEXT', 'PREV'):
                _all = list(self.patch.all_fixtures())
                if _all:
                    _ids = [m.fixture_id for m in _all]
                    _cur_ids = {m.fixture_id for m in self.selection
                                if isinstance(m, MasterFixture)}
                    if token == 'NEXT':
                        _ref = max(_cur_ids) if _cur_ids else _ids[-1]
                        _next_id = next((fid for fid in _ids if fid > _ref), _ids[0])
                    else:
                        _ref = min(_cur_ids) if _cur_ids else _ids[0]
                        _next_id = next((fid for fid in reversed(_ids) if fid < _ref), _ids[-1])
                    nxt = self.patch.get(_next_id)
                    if nxt:
                        selected.append(nxt)
                i += 1
                continue

            # RANDOM <n>  — pick n fixtures at random from all patched
            if token == 'RANDOM':
                import random as _rand
                _n = 1
                if i + 1 < len(tokens) and tokens[i + 1].isdigit():
                    _n = int(tokens[i + 1])
                    i += 1
                _pool = list(self.patch.all_fixtures())
                _n = min(_n, len(_pool))
                if _n > 0:
                    selected += _rand.sample(_pool, _n)
                i += 1
                continue

            if (i + 1 < len(tokens) and tokens[i + 1] == 'THRU'
                    and i + 2 < len(tokens)):

                start_token = token
                end_token   = tokens[i + 2]

                if '.' in start_token and '.' in end_token:
                    s_parts = start_token.split('.')
                    e_parts = end_token.split('.')
                    if (s_parts[0] == e_parts[0]
                            and s_parts[1].isdigit()
                            and e_parts[1].isdigit()):
                        master_id = int(s_parts[0])
                        start_sub = int(s_parts[1])
                        end_sub   = int(e_parts[1])
                        master    = self.patch.get(master_id)
                        if master:
                            for idx in range(start_sub, end_sub + 1):
                                sub = master.get_sub(idx)
                                if sub:
                                    selected.append(sub)
                        i += 3
                        continue

                elif start_token.isdigit() and end_token.isdigit():
                    selected += self.patch.get_range(
                        int(start_token), int(end_token)
                    )
                    i += 3
                    continue

            # EVERY <n>  — keep every Nth fixture from accumulated selection so far
            if token == 'EVERY' and i + 1 < len(tokens) and tokens[i + 1].isdigit():
                n = int(tokens[i + 1])
                if n > 1 and selected:
                    selected = [f for idx, f in enumerate(selected) if idx % n == 0]
                i += 2
                continue

            fixture = self._parse_token_to_fixture(token)
            if fixture:
                selected.append(fixture)
            i += 1

        return selected

    def _parse_action(self, tokens):
        if not tokens:
            return
        _CH = {'R': 'red', 'G': 'green', 'B': 'blue',
               'RED': 'red', 'GREEN': 'green', 'BLUE': 'blue',
               'PAN': 'pan', 'TILT': 'tilt',
               'PAN_FINE': 'pan_fine', 'TILT_FINE': 'tilt_fine',
               'GOBO': 'gobo', 'GOBO_ROT': 'gobo_rot',
               'GOBO2': 'gobo2', 'GOBO2_ROT': 'gobo2_rot',
               'ZOOM': 'zoom', 'FOCUS': 'focus', 'IRIS': 'iris',
               'SHUTTER1': 'shutter1', 'COLOR': 'color',
               'PRISM': 'prism', 'FROST': 'frost', 'ANIMATION': 'animation',
               'CONTROL': 'control', 'MACRO': 'macro',
               'DIMMER': 'dimmer',
               }
        _NAMED = {
            'WHITE':   (255, 255, 255), 'WARM':    (255, 180,  60),
            'AMBER':   (255, 140,   0), 'YELLOW':  (255, 200,   0),
            'ORANGE':  (255,  80,   0), 'CYAN':    (  0, 200, 200),
            'MAGENTA': (255,   0, 200), 'PINK':    (255,  50, 150),
            'UV':      ( 80,   0, 200), 'PURPLE':  (120,   0, 220),
            'LIME':    (  0, 255,  60), 'TEAL':    (  0, 180, 140),
        }

        # Current programmer values — used for relative +/- adjustments
        _first_fid     = str(self.selection[0].fixture_id) if self.selection else ''
        _first_sub_fid = (f"{self.selection[0].fixture_id}.1"
                          if self.selection else '')
        _cur_dim_pct   = self.data.get(_first_fid, {}).get('dim', 0.0) * 100
        _cur_sub       = self.data.get(_first_sub_fid, {})

        def _parse_num(tok, base=0.0, lo=0.0, hi=255.0):
            """Parse absolute or relative (+/-) numeric token. Returns float or None."""
            raw = tok.rstrip('%')
            if raw and raw[0] in ('+', '-') and raw[1:].replace('.', '', 1).isdigit():
                try:
                    return max(lo, min(hi, base + float(raw)))
                except ValueError:
                    return None
            stripped = raw.replace('.', '', 1).lstrip('-')
            if stripped.isdigit():
                try:
                    return max(lo, min(hi, float(raw)))
                except ValueError:
                    return None
            return None

        # FAN <channel> <from_val> <to_val>  — fan values across selection
        # e.g.  FAN DIM 0 100   FAN R 0 255   FAN PAN 0 200
        # Fan always steps by master fixture (one value per fixture, all subs get same).
        if tokens[0] == 'FAN' and len(tokens) >= 4:
            _fan_ch_tok = tokens[1]
            try:
                _fan_lo = float(tokens[2].rstrip('%'))
                _fan_hi = float(tokens[3].rstrip('%'))
            except ValueError:
                pass
            else:
                _is_dim = (_fan_ch_tok == 'DIM')
                _fan_ch = _CH.get(_fan_ch_tok)
                if _is_dim or _fan_ch:
                    # Always fan by master fixtures for consistent per-fixture stepping
                    _masters = [f for f in self.selection if isinstance(f, MasterFixture)]
                    n = len(_masters)
                    if n == 1:
                        mid = (_fan_lo + _fan_hi) / 2.0
                        if _is_dim:
                            self.set_dimmer(max(0.0, min(100.0, mid)))
                        else:
                            self.set_channel(_fan_ch, int(round(max(0, min(255, mid)))))
                    elif n > 1:
                        self._push_undo()
                        for idx, master in enumerate(_masters):
                            t = idx / (n - 1)
                            raw_val = _fan_lo + (_fan_hi - _fan_lo) * t
                            fid = str(master.fixture_id)
                            if _is_dim:
                                val = max(0.0, min(1.0, raw_val / 100.0))
                                self._ensure_data(master)
                                self.data[fid]['dim'] = val
                                if fid in self.disabled:
                                    self.disabled[fid].pop('dim', None)
                                master.set_dimmer(val)
                            else:
                                val = int(round(max(0, min(255, raw_val))))
                                # Apply to all subs of this master
                                for sub in master.all_subs():
                                    sub_fid = str(sub.fixture_id)
                                    self._ensure_data(sub)
                                    self.data[sub_fid][_fan_ch] = val
                                    if sub_fid in self.disabled:
                                        self.disabled[sub_fid].pop(_fan_ch, None)
                                    sub.set_channel(_fan_ch, val)
                        self._print_programmer()
            return

        # HUE <0-360> [SAT <0-100>] [VAL <0-100>]  — set RGB from HSV
        if tokens[0] == 'HUE':
            try:
                h = float(tokens[1]) % 360.0
            except (IndexError, ValueError):
                return
            s = 100.0
            v = 100.0
            for j in range(2, len(tokens) - 1):
                if tokens[j] == 'SAT':
                    try: s = float(tokens[j + 1])
                    except Valueerror: pass
                elif tokens[j] == 'VAL':
                    try: v = float(tokens[j + 1])
                    except Valueerror: pass
            s = max(0.0, min(100.0, s))
            v = max(0.0, min(100.0, v))
            h1, s1, v1 = h / 360.0, s / 100.0, v / 100.0
            c = v1 * s1
            x = c * (1 - abs((h1 * 6) % 2 - 1))
            m = v1 - c
            i = int(h1 * 6)
            r1, g1, b1 = [(c,x,0),(x,c,0),(0,c,x),(0,x,c),(x,0,c),(c,0,x)][i % 6]
            r = int(round((r1 + m) * 255))
            g = int(round((g1 + m) * 255))
            b = int(round((b1 + m) * 255))
            self.set_channel('red', r)
            self.set_channel('green', g)
            self.set_channel('blue', b)
            return

        # CT <kelvin> — set RGB from color temperature (1000K–10000K)
        # Uses Tanner Helland algorithm — no import needed (math already loaded)
        if tokens[0] == 'CT':
            try:
                K = float(tokens[1])
            except (IndexError, ValueError):
                return
            import math as _m
            t = max(1000.0, min(10000.0, K)) / 100.0
            r = 255 if t <= 66 else max(0, min(255, int(329.698727446 * (t - 60) ** -0.1332047592)))
            g_raw = (99.4708025861 * _m.log(t) - 161.1195681661 if t <= 66
                     else 288.1221695283 * (t - 60) ** -0.0755148492)
            g = max(0, min(255, int(g_raw)))
            b = (255 if t >= 66 else
                 (0 if t <= 19 else
                  max(0, min(255, int(138.5177312231 * _m.log(t - 10) - 305.0447927307)))))
            self.set_channel('red', r)
            self.set_channel('green', g)
            self.set_channel('blue', b)
            return

        # RANDOM <channel> — assign an independent random value (0-255) to each
        # sub-fixture in the selection. Per-master variant: RANDOM <ch> MASTER
        # applies the same random value to all subs of each master fixture.
        if tokens[0] == 'RANDOM' and len(tokens) >= 2:
            import random as _rnd
            arg1 = tokens[1]
            per_master = len(tokens) >= 3 and tokens[-1] == 'MASTER'
            # AT RANDOM DIM — randomize master dimmer (0–100%) per fixture
            if arg1 == 'DIM':
                self._push_undo()
                masters = [f for f in self.selection if isinstance(f, MasterFixture)]
                for master in masters:
                    self.data.setdefault(str(master.fixture_id), {})['dim'] = round(_rnd.random(), 4)
                return
            ch = _CH.get(arg1)
            if ch:
                self._push_undo()
                if per_master:
                    masters = [f for f in self.selection if isinstance(f, MasterFixture)]
                    for master in masters:
                        val = _rnd.randint(0, 255)
                        for sub in master.all_subs():
                            self.data.setdefault(str(sub.fixture_id), {})[ch] = val
                else:
                    for sub in self._get_sub_selection():
                        self.data.setdefault(str(sub.fixture_id), {})[ch] = _rnd.randint(0, 255)
            return

        # FLIP <channel> — invert channel value: new = 255 - current (0 if unset)
        # Useful for mirroring pan/tilt on symmetric rigs, or inverting colour.
        if tokens[0] == 'FLIP':
            ch = _CH.get(tokens[1]) if len(tokens) > 1 else None
            if ch:
                self._push_undo()
                for sub in self._get_sub_selection():
                    sfid = str(sub.fixture_id)
                    cur = self.data.get(sfid, {}).get(ch, 0)
                    self.data.setdefault(sfid, {})[ch] = max(0, min(255, 255 - int(cur)))
            return

        # MIRROR <ch>  — reverse channel values across the fixture selection
        # The value of fixture N becomes the value of fixture (last-N).
        # Useful for symmetric rigs: mirror R creates a left-right flip.
        if tokens[0] == 'MIRROR' and len(tokens) >= 2:
            ch = _CH.get(tokens[1])
            if ch:
                masters = [f for f in self.selection if isinstance(f, MasterFixture)]
                # Collect per-master: average value across all subs of that master
                cur_vals = []
                for master in masters:
                    subs = master.all_subs()
                    vals = [self.data.get(str(s.fixture_id), {}).get(ch, 0) for s in subs]
                    cur_vals.append(vals)
                self._push_undo()
                rev_vals = list(reversed(cur_vals))
                for master, new_sub_vals in zip(masters, rev_vals):
                    for sub, new_v in zip(master.all_subs(), new_sub_vals):
                        self.data.setdefault(str(sub.fixture_id), {})[ch] = int(new_v)
            return

        # STEP <ch> <step>  — add step*index to each master fixture in selection order
        # Creates a staircase: fixture 1 unchanged, fixture 2 += step, fixture 3 += 2*step...
        # Step is applied to all subs of each master fixture equally (same offset per fixture).
        if tokens[0] == 'STEP' and len(tokens) >= 3:
            ch = _CH.get(tokens[1])
            step_v = _parse_num(tokens[2], lo=-255.0, hi=255.0)
            if ch and step_v is not None:
                masters = [f for f in self.selection if isinstance(f, MasterFixture)]
                self._push_undo()
                for idx, master in enumerate(masters):
                    offset = int(step_v * idx)
                    for sub in master.all_subs():
                        sfid = str(sub.fixture_id)
                        cur = self.data.get(sfid, {}).get(ch, 0)
                        self.data.setdefault(sfid, {})[ch] = max(0, min(255, int(cur + offset)))
            return

        # CLAMP <ch> <lo> <hi>  — limit each sub's channel value to [lo, hi]
        if tokens[0] == 'CLAMP' and len(tokens) >= 4:
            # AT CLAMP DIM <lo%> <hi%> — clamp master dimmer (0–1) using percent range
            if tokens[1] == 'DIM':
                lo_n = _parse_num(tokens[2], lo=0.0, hi=100.0)
                hi_n = _parse_num(tokens[3], lo=0.0, hi=100.0)
                if lo_n is not None and hi_n is not None:
                    lo_f = min(lo_n, hi_n) / 100.0
                    hi_f = max(lo_n, hi_n) / 100.0
                    masters = [f for f in self.selection if isinstance(f, MasterFixture)]
                    self._push_undo()
                    for master in masters:
                        fid = str(master.fixture_id)
                        cur = self.data.get(fid, {}).get('dim', 0.0)
                        self.data.setdefault(fid, {})['dim'] = max(lo_f, min(hi_f, float(cur)))
                return
            ch = _CH.get(tokens[1])
            lo_n = _parse_num(tokens[2], lo=0.0, hi=255.0)
            hi_n = _parse_num(tokens[3], lo=0.0, hi=255.0)
            if ch and lo_n is not None and hi_n is not None:
                lo_v, hi_v = int(min(lo_n, hi_n)), int(max(lo_n, hi_n))
                self._push_undo()
                for sub in self._get_sub_selection():
                    sfid = str(sub.fixture_id)
                    cur = self.data.get(sfid, {}).get(ch, 0)
                    self.data.setdefault(sfid, {})[ch] = max(lo_v, min(hi_v, int(cur)))
            return

        # BRIGHTEST / DARKEST / AVERAGE — stamp max/min/mean across selection
        if tokens[0] in ('BRIGHTEST', 'DARKEST', 'AVERAGE') and len(tokens) >= 2:
            # DIM variant: operate on master dimmer (0–1 float) per master fixture
            if tokens[1] == 'DIM':
                masters = [f for f in self.selection if isinstance(f, MasterFixture)]
                dim_vals = [self.data.get(str(m.fixture_id), {}).get('dim', 0.0) for m in masters]
                if masters and dim_vals:
                    if tokens[0] == 'BRIGHTEST':
                        target_dim = max(dim_vals)
                    elif tokens[0] == 'DARKEST':
                        target_dim = min(dim_vals)
                    else:
                        target_dim = sum(dim_vals) / len(dim_vals)
                    self._push_undo()
                    for m in masters:
                        self.data.setdefault(str(m.fixture_id), {})['dim'] = round(target_dim, 6)
                return
            ch = _CH.get(tokens[1])
            if ch:
                subs = self._get_sub_selection()
                vals = [self.data.get(str(s.fixture_id), {}).get(ch, 0) for s in subs]
                if tokens[0] == 'BRIGHTEST':
                    target = max(vals)
                elif tokens[0] == 'DARKEST':
                    target = min(vals)
                else:
                    target = sum(vals) / len(vals) if vals else 0
                self._push_undo()
                for sub in subs:
                    self.data.setdefault(str(sub.fixture_id), {})[ch] = int(round(target))
            return

        # WOBBLE <ch|DIM> <amount> — add per-fixture random ±amount jitter
        if tokens[0] == 'WOBBLE' and len(tokens) >= 3:
            amt = _parse_num(tokens[2], lo=0.0, hi=255.0)
            if tokens[1] == 'DIM' and amt is not None:
                amt_f = amt / 100.0  # amount in percent → 0–1 fraction
                masters = [f for f in self.selection if isinstance(f, MasterFixture)]
                self._push_undo()
                for master in masters:
                    fid = str(master.fixture_id)
                    cur = float(self.data.get(fid, {}).get('dim', 0.0))
                    jitter = random.uniform(-amt_f, amt_f)
                    self.data.setdefault(fid, {})['dim'] = max(0.0, min(1.0, cur + jitter))
                return
            ch = _CH.get(tokens[1])
            if ch and amt is not None:
                subs = self._get_sub_selection()
                self._push_undo()
                for sub in subs:
                    sfid = str(sub.fixture_id)
                    cur = self.data.get(sfid, {}).get(ch, 0)
                    jitter = random.uniform(-amt, amt)
                    self.data.setdefault(sfid, {})[ch] = max(0, min(255, int(round(cur + jitter))))
            return

        # SCALE <ch|DIM> <pct> — multiply each sub/master value by pct%
        if tokens[0] == 'SCALE' and len(tokens) >= 3:
            pct = _parse_num(tokens[2], lo=0.0, hi=1000.0)
            if tokens[1] == 'DIM' and pct is not None:
                factor = pct / 100.0
                masters = [f for f in self.selection if isinstance(f, MasterFixture)]
                self._push_undo()
                for master in masters:
                    fid = str(master.fixture_id)
                    cur = self.data.get(fid, {}).get('dim', 0.0)
                    self.data.setdefault(fid, {})['dim'] = max(0.0, min(1.0, float(cur) * factor))
                return
            ch = _CH.get(tokens[1])
            if ch and pct is not None:
                factor = pct / 100.0
                subs = self._get_sub_selection()
                self._push_undo()
                for sub in subs:
                    sfid = str(sub.fixture_id)
                    cur = self.data.get(sfid, {}).get(ch, 0)
                    self.data.setdefault(sfid, {})[ch] = max(0, min(255, int(round(cur * factor))))
            return

        # NORMALIZE <ch> — scale all selected subs proportionally so the max = 255
        if tokens[0] == 'NORMALIZE' and len(tokens) >= 2:
            ch = _CH.get(tokens[1])
            if ch:
                subs = self._get_sub_selection()
                vals = [self.data.get(str(s.fixture_id), {}).get(ch, 0) for s in subs]
                peak = max(vals) if vals else 0
                if peak > 0:
                    self._push_undo()
                    for sub, v in zip(subs, vals):
                        # Use integer arithmetic to avoid float rounding drift
                        self.data.setdefault(str(sub.fixture_id), {})[ch] = min(255, (v * 255 + peak // 2) // peak)
            return

        # INVERT <ch|DIM> — flip channel value; DIM: new = 1 - current
        if tokens[0] == 'INVERT' and len(tokens) >= 2:
            if tokens[1] == 'DIM':
                masters = [f for f in self.selection if isinstance(f, MasterFixture)]
                self._push_undo()
                for master in masters:
                    fid = str(master.fixture_id)
                    cur = float(self.data.get(fid, {}).get('dim', 0.0))
                    self.data.setdefault(fid, {})['dim'] = max(0.0, min(1.0, 1.0 - cur))
                return
            ch = _CH.get(tokens[1])
            if ch:
                subs = self._get_sub_selection()
                self._push_undo()
                for sub in subs:
                    sfid = str(sub.fixture_id)
                    cur = self.data.get(sfid, {}).get(ch, 0)
                    self.data.setdefault(sfid, {})[ch] = 255 - int(cur)
            return

        # CLEAR [<ch>] — remove programmer values for the selection (all or one channel)
        if tokens[0] == 'CLEAR':
            ch = _CH.get(tokens[1]) if len(tokens) >= 2 else None
            if len(tokens) >= 2 and not ch:
                # unknown channel name — ignore silently so CLEAR without a ch arg still works
                pass
            self._push_undo()
            if ch:
                # Remove only this channel from each sub-fixture
                for sub in self._get_sub_selection():
                    sfid = str(sub.fixture_id)
                    if sfid in self.data:
                        self.data[sfid].pop(ch, None)
                        if not self.data[sfid]:
                            del self.data[sfid]
            else:
                # Remove all channels for master + all subs in selection
                for f in self.selection:
                    fid = str(f.fixture_id)
                    self.data.pop(fid, None)
                    if isinstance(f, MasterFixture):
                        for sub in f.all_subs():
                            self.data.pop(str(sub.fixture_id), None)
            return

        # COPY <fid> — paste all programmer values from fixture <fid> into each selected fixture
        if tokens[0] == 'COPY' and len(tokens) >= 2:
            try:
                src_fid = int(tokens[1])
            except ValueError:
                return
            if src_fid not in self.patch.fixtures:
                return
            src_master = self.patch.fixtures[src_fid]
            src_dim_key = str(src_fid)
            src_dim = self.data.get(src_dim_key, {}).get('dim')
            src_sub_data = {}
            for sub in src_master.all_subs():
                sfid = str(sub.fixture_id)
                if sfid in self.data:
                    src_sub_data[sfid] = dict(self.data[sfid])
            if src_dim is None and not src_sub_data:
                return
            self._push_undo()
            for f in self.selection:
                if not isinstance(f, MasterFixture):
                    continue
                dst_key = str(f.fixture_id)
                if src_dim is not None:
                    self.data.setdefault(dst_key, {})['dim'] = src_dim
                for i, dst_sub in enumerate(f.all_subs()):
                    src_subs = src_master.all_subs()
                    if i >= len(src_subs):
                        break
                    src_sfid = str(src_subs[i].fixture_id)
                    if src_sfid not in src_sub_data:
                        continue
                    dst_sfid = str(dst_sub.fixture_id)
                    self.data.setdefault(dst_sfid, {}).update(src_sub_data[src_sfid])
            return

        if tokens[0] == 'FULL':
            self.set_dimmer(100)
            return
        if tokens[0] == 'OUT':
            self.set_dimmer(0)
            return
        if tokens[0] in _NAMED:
            r, g, b = _NAMED[tokens[0]]
            self.set_channel('red', r)
            self.set_channel('green', g)
            self.set_channel('blue', b)
            return
        # bare number / percent / relative → dimmer  (e.g. AT 80  AT 80%  AT +10  AT -5)
        # Only applies when it's the sole token to avoid consuming a selection number.
        if len(tokens) == 1:
            val = _parse_num(tokens[0], _cur_dim_pct, 0, 100)
            if val is not None:
                self.set_dimmer(val)
            return
        # Multi-channel sequence: DIM 100 R 255 G 0 B 128 PAN 200 TILT 64 etc.
        # DIM is handled inline so "AT DIM 100 PAN 200" works in a single call.
        # Relative values allowed: AT DIM +10  AT PAN -30  AT R +50
        i = 0
        while i < len(tokens) - 1:
            tok = tokens[i]
            if tok == 'DIM':
                val = _parse_num(tokens[i + 1], _cur_dim_pct, 0, 100)
                if val is not None:
                    self.set_dimmer(val)
                    i += 2
                    continue
            ch = _CH.get(tok)
            if ch:
                base_ch = float(_cur_sub.get(ch, 0))
                val = _parse_num(tokens[i + 1], base_ch, 0, 255)
                if val is not None:
                    self.set_channel(ch, int(round(val)))
                    i += 2
                    continue
            i += 1

    # ----------------------------------------------------------
    # Display
    # ----------------------------------------------------------

    def _print_programmer(self):
        active = {fid: vals for fid, vals in self.data.items() if vals}
        if not active:
            print("programmer empty.")
            return

        print("\n--- programmer ---")
        for fid, vals in active.items():
            if '.' not in fid:
                master = self.patch.get(int(fid))
                label  = master.name if master else fid
                parts  = []
                if 'dim' in vals:
                    parts.append(f"Dim={vals['dim']:.0%}")
                print(f"  {label}: {' '.join(parts)}")

        sub_counts = {}
        sub_sample = {}
        for fid, vals in active.items():
            if '.' in fid and vals:
                master_id = fid.split('.')[0]
                sub_counts[master_id] = sub_counts.get(master_id, 0) + 1
                if master_id not in sub_sample:
                    sub_sample[master_id] = vals

        _COLOUR_DISPLAY = {
            'red': 'R', 'green': 'G', 'blue': 'B', 'white': 'W', 'amber': 'A',
        }
        _ATTR_DISPLAY = [
            'dimmer', 'pan', 'tilt', 'pan_fine', 'tilt_fine',
            'gobo', 'gobo_rot', 'gobo2', 'gobo2_rot',
            'zoom', 'focus', 'iris', 'shutter1', 'color',
            'prism', 'frost', 'animation', 'control', 'macro',
        ]
        for master_id, count in sub_counts.items():
            master = self.patch.get(int(master_id))
            label  = master.name if master else f"Fixture {master_id}"
            sample = sub_sample[master_id]
            parts  = []
            for ch, abbr in _COLOUR_DISPLAY.items():
                if ch in sample:
                    parts.append(f"{abbr}={sample[ch]}")
            for ch in _ATTR_DISPLAY:
                if ch in sample:
                    parts.append(f"{ch}={sample[ch]}")
            px_label = f"({count} pixels)" if count > 1 else ""
            print(f"  {label}{' ' + px_label if px_label else ''}: {' '.join(parts)}")

        # show disabled summary if anything is disabled
        disabled_active = {
            fid: vals for fid, vals in self.disabled.items() if vals
        }
        if disabled_active:
            print("  [disabled]")
            seen_masters = set()
            for fid, vals in disabled_active.items():
                master_id = fid.split('.')[0]
                if master_id not in seen_masters:
                    seen_masters.add(master_id)
                    master = self.patch.get(int(master_id))
                    label  = master.name if master else f"Fixture {master_id}"
                    chs    = ", ".join(vals.keys())
                    print(f"    {label}: {chs}")

        print("------------------\n")

__all__ = ["FixtureProfile", "FixtureLibrary", "GDTFLoader", "SubFixture",
           "MasterFixture", "Patch", "programmer"]
