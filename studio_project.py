# ============================================================
# STUDIO CONSOLE - Core Object Model
# Block 1: Fixture Profile System + SubFixture + MasterFixture
# ============================================================

import os
import json
import copy

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
            print(f"Error: Profile '{profile_name}' not found in library.")
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

# (first Programmer draft removed — active class is below)
# ============================================================
# STUDIO CONSOLE - Core Object Model
# Block 3 UPDATE: Programmer
# Added: self.disabled dict, REMOVE and ENABLE commands
# ============================================================

class Programmer:
    def __init__(self, patch):
        self.patch     = patch
        self.selection = []
        self.data      = {}         # Active parameters — will be recorded/output
        self.disabled  = {}         # Removed parameters — remembered but inactive
        self._clear_stage     = 0   # 0=fresh, 1=values cleared, 2=selection cleared
        self._last_clear_time = 0.0
        self._undo_stack      = []  # list of (data_snapshot, selection_ids) dicts
        self._UNDO_MAX        = 20

    def _push_undo(self):
        """Snapshot current programmer state onto the undo stack."""
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
            return "Nothing to undo"
        snap = self._undo_stack.pop()
        self.data     = snap['data']
        self.disabled = snap['disabled']
        # Restore selection by fixture ID
        sel_ids = set(snap['selection'])
        restored = []
        for m in self.patch.all_fixtures():
            if m.fixture_id in sel_ids:
                restored.append(m)
                restored += m.all_subs()
        self.selection = restored
        return f"Undo — programmer restored  ({len(self._undo_stack)} step(s) remaining)"

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
        self.selection = []
        self.data.clear()
        self.disabled  = {}
        self._clear_stage = 0
        print("Programmer cleared.")

    def do_clear(self):
        """MA3-style three-tap CLEAR.
        Tap 1 — clear fixture selection.
        Tap 2 — clear programmer values.
        Tap 3 — clear output (blackout).
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
            return "Selection cleared  (CLEAR again to clear programmer)"
        elif self._clear_stage == 1:
            for fid in list(self.data.keys()):
                fixture = self._get_fixture_by_fid(fid)
                if fixture:
                    fixture.clear_dirty()
            self.data.clear()
            self.disabled = {}
            self._clear_stage = 2
            return "Programmer cleared  (CLEAR again to clear output)"
        else:
            self._clear_stage = 0
            return "output_clear"  # signal to caller to blackout

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

        print(f"Removed '{channel}' from programmer for current selection.")
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

    def _get_targets_for_channel(self, channel):
        """
        Returns the right fixture objects for a given channel type.
        Dim targets masters. RGB targets sub-fixtures.
        All targets both.
        """
        if channel == 'dim':
            return [f for f in self.selection if isinstance(f, MasterFixture)]
        elif channel in ('red', 'green', 'blue'):
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
        _ACTION_KEYWORDS = {'R', 'G', 'B', 'RED', 'GREEN', 'BLUE', 'FULL', 'OUT', 'DIM'}
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
            self._parse_action(action_tokens)

    def _parse_channel_token(self, token):
        """Maps command token to internal channel name."""
        mapping = {
            'R':   'red',
            'G':   'green',
            'B':   'blue',
            'DIM': 'dim',
            'ALL': 'all',
            'RED':   'red',
            'GREEN': 'green',
            'BLUE':  'blue',
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

            fixture = self._parse_token_to_fixture(token)
            if fixture:
                selected.append(fixture)
            i += 1

        return selected

    def _parse_action(self, tokens):
        if not tokens:
            return
        _CH = {'R': 'red', 'G': 'green', 'B': 'blue',
               'RED': 'red', 'GREEN': 'green', 'BLUE': 'blue'}
        if tokens[0] == 'FULL':
            self.set_dimmer(100)
            return
        if tokens[0] == 'OUT':
            self.set_dimmer(0)
            return
        if tokens[0] == 'DIM' and len(tokens) > 1:
            try:
                self.set_dimmer(float(tokens[1].rstrip('%')))
            except ValueError:
                pass
            return
        # bare number / percent → dimmer  (e.g. AT 80  or  AT 80%)
        bare = tokens[0].rstrip('%')
        if bare.replace('.', '', 1).lstrip('-').isdigit():
            try:
                self.set_dimmer(float(bare))
            except ValueError:
                pass
            return
        # multi-channel sequence: R 255 G 0 B 128 in any order
        i = 0
        while i < len(tokens) - 1:
            ch = _CH.get(tokens[i])
            if ch:
                try:
                    self.set_channel(ch, int(tokens[i + 1]))
                    i += 2
                    continue
                except ValueError:
                    pass
            i += 1

    # ----------------------------------------------------------
    # Display
    # ----------------------------------------------------------

    def _print_programmer(self):
        active = {fid: vals for fid, vals in self.data.items() if vals}
        if not active:
            print("Programmer empty.")
            return

        print("\n--- Programmer ---")
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

        for master_id, count in sub_counts.items():
            master = self.patch.get(int(master_id))
            label  = master.name if master else f"Fixture {master_id}"
            sample = sub_sample[master_id]
            parts  = []
            if 'red'   in sample: parts.append(f"R={sample['red']}")
            if 'green' in sample: parts.append(f"G={sample['green']}")
            if 'blue'  in sample: parts.append(f"B={sample['blue']}")
            print(f"  {label} ({count} pixels): {' '.join(parts)}")

        # Show disabled summary if anything is disabled
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


# ============================================================
# Blocks 4 & 5: Presets, Pools, Groups
# ColorPreset / ColorPool — referenced RGB presets
# DimmerPreset / DimmerPool — referenced dimmer presets
# AttributePreset / AttributePool — generic attribute presets
#   (position, gobo, zoom, focus, beam, control)
# Group / GroupPool — fixture selection groups
# ============================================================

class ColorPreset:
    """
    Selective colour preset — stores a single RGB value.
    apply() pushes it to every sub-fixture in the current programmer selection.
    record() samples from the first selected sub-fixture that carries colour data.

    # Future: add a `scope` field ("selective" | "universe" | "global") to expand
    # targeting without changing the stored RGB format.
    """
    def __init__(self, preset_id, name=""):
        self.preset_id = preset_id
        self.name      = name if name else f"Color {preset_id}"
        self.red   = 0
        self.green = 0
        self.blue  = 0

    def record(self, programmer):
        for f in programmer._get_sub_selection():
            vals = programmer.data.get(str(f.fixture_id), {})
            if any(ch in vals for ch in ('red', 'green', 'blue')):
                self.red   = vals.get('red',   0)
                self.green = vals.get('green', 0)
                self.blue  = vals.get('blue',  0)
                break
        print(f"Recorded: {self}")

    def apply(self, programmer):
        applied = 0
        masters_written = set()
        for f in programmer._get_sub_selection():
            programmer._ensure_data(f)
            fid = str(f.fixture_id)
            programmer.data[fid]['red']   = self.red
            programmer.data[fid]['green'] = self.green
            programmer.data[fid]['blue']  = self.blue
            f.set_rgb(self.red, self.green, self.blue)
            applied += 1
            masters_written.add(str(f.master_id))
        for mfid in masters_written:
            programmer.data.setdefault(mfid, {})['color_ref'] = self.preset_id
        print(f"Applied {self} to {applied} sub-fixture(s).")

    def __repr__(self):
        return (f"[Color Preset {self.preset_id}] \"{self.name}\" "
                f"RGB({self.red},{self.green},{self.blue})")


class ColorPool:
    def __init__(self):
        self.presets = {}   # { preset_id (int): ColorPreset }

    def get(self, pid):
        return self.presets.get(int(pid))

    def record(self, preset_id, programmer, name=""):
        preset = ColorPreset(preset_id, name or f"Color {preset_id}")
        preset.record(programmer)
        self.presets[preset.preset_id] = preset
        return preset

    def apply(self, preset_id, programmer):
        p = self.get(preset_id)
        if p:
            p.apply(programmer)
        else:
            print(f"Color Preset {preset_id} not found.")

    def delete(self, preset_id):
        self.presets.pop(int(preset_id), None)

    def print_pool(self):
        print("\n===== COLOR PRESETS =====")
        for p in self.presets.values():
            print(f"  {p}")


class DimmerPreset:
    """
    Selective dimmer preset — stores a single level (0.0–1.0).
    apply() pushes it to every master fixture in the current programmer selection.
    record() samples from the first selected master that carries dim data.

    # Future: add a `scope` field ("selective" | "universe" | "global") to expand
    # targeting without changing the stored level format.
    """
    def __init__(self, preset_id, name=""):
        self.preset_id = preset_id
        self.name      = name if name else f"Dimmer {preset_id}"
        self.level     = 0.0   # 0.0 – 1.0

    def record(self, programmer):
        for f in programmer.selection:
            if isinstance(f, MasterFixture):
                vals = programmer.data.get(str(f.fixture_id), {})
                if 'dim' in vals:
                    self.level = vals['dim']
                    break
        print(f"Recorded: {self}")

    def apply(self, programmer):
        applied = 0
        for f in programmer.selection:
            if isinstance(f, MasterFixture):
                programmer._ensure_data(f)
                fid = str(f.fixture_id)
                programmer.data[fid]['dim']     = self.level
                programmer.data[fid]['dim_ref'] = self.preset_id
                f.set_dimmer(self.level)
                applied += 1
        print(f"Applied {self} to {applied} fixture(s).")

    def __repr__(self):
        return f"[Dimmer Preset {self.preset_id}] \"{self.name}\" ({self.level:.0%})"


class DimmerPool:
    def __init__(self):
        self.presets = {}   # { preset_id (int): DimmerPreset }

    def get(self, pid):
        return self.presets.get(int(pid))

    def record(self, preset_id, programmer, name=""):
        preset = DimmerPreset(preset_id, name or f"Dimmer {preset_id}")
        preset.record(programmer)
        self.presets[preset.preset_id] = preset
        return preset

    def apply(self, preset_id, programmer):
        p = self.get(preset_id)
        if p:
            p.apply(programmer)
        else:
            print(f"Dimmer Preset {preset_id} not found.")

    def delete(self, preset_id):
        self.presets.pop(int(preset_id), None)

    def print_pool(self):
        print("\n===== DIM PRESETS =====")
        for p in self.presets.values():
            print(f"  {p}")


# ── Generic attribute pools (position, gobo, zoom, focus, beam, control) ──
#
# To add a new pool type:
#   1. Instantiate AttributePool("position") etc. in the main init block.
#   2. Add ShowFile path + save_attribute_pool / load_attribute_pool call.
#   3. Wire RECORD <ATTR> <n> and <ATTR> <n> commands in run_command().
#   4. <attr>_ref expansion is already handled generically in _resolve_cue_refs().

class AttributePreset:
    """
    Generic preset for any fixture attribute family.

    attribute  — logical name (e.g. "position", "gobo", "zoom")
    data       — {fixture_id_str: {channel_name: value, ...}}
    """
    def __init__(self, preset_id, name, attribute):
        self.preset_id = int(preset_id)
        self.name      = name or f"{attribute.title()} {preset_id}"
        self.attribute = attribute
        self.data      = {}

    def record(self, programmer_data, relevant_channels):
        self.data = {}
        for fid, vals in programmer_data.items():
            snap = {k: vals[k] for k in relevant_channels if k in vals}
            if snap:
                self.data[fid] = snap

    def apply(self, programmer):
        ref_key = f"{self.attribute}_ref"
        for fid, vals in self.data.items():
            programmer.data.setdefault(fid, {}).update(vals)
            if '.' not in str(fid):
                programmer.data[fid][ref_key] = self.preset_id

    def to_dict(self):
        return {
            "preset_id": self.preset_id,
            "name":      self.name,
            "attribute": self.attribute,
            "data":      self.data,
        }

    @classmethod
    def from_dict(cls, d):
        p = cls(d["preset_id"], d.get("name", ""), d.get("attribute", "unknown"))
        p.data = d.get("data", {})
        return p

    def __repr__(self):
        return (f"[{self.attribute.upper()} Preset {self.preset_id}] "
                f"{self.name}  ({len(self.data)} fixtures)")


class AttributePool:
    """Registry of AttributePresets for one attribute family."""
    def __init__(self, attribute, relevant_channels=None):
        self.attribute         = attribute
        self.relevant_channels = list(relevant_channels or [attribute])
        self.presets           = {}   # { preset_id: AttributePreset }

    def get(self, preset_id):
        return self.presets.get(int(preset_id))

    def record(self, preset_id, programmer, name=""):
        preset = AttributePreset(preset_id, name, self.attribute)
        preset.record(programmer.data, self.relevant_channels)
        self.presets[preset.preset_id] = preset
        return preset

    def apply(self, preset_id, programmer):
        p = self.get(preset_id)
        if p:
            p.apply(programmer)
        else:
            print(f"{self.attribute.title()} Preset {preset_id} not found.")

    def delete(self, preset_id):
        self.presets.pop(int(preset_id), None)

    def print_pool(self):
        label = self.attribute.upper()
        print(f"\n===== {label} PRESETS =====")
        for p in self.presets.values():
            print(f"  {p}")


class Group:
    """
    A named selection of master fixtures.
    Sub-fixtures are NOT stored — they auto-expand from the master on recall.
    """
    def __init__(self, group_id, name=""):
        self.group_id = group_id
        self.name     = name or f"Group {group_id}"
        self.members  = []   # [ ("master", fixture_id_int), ... ]

    def record(self, programmer):
        self.members = []
        for f in programmer.selection:
            if isinstance(f, MasterFixture):
                self.members.append(("master", f.fixture_id))
        print(f"Recorded: {self}")

    def recall(self, patch):
        """Return list of MasterFixture objects for this group."""
        fixtures = []
        for _type, fid in self.members:
            m = patch.get(int(fid))
            if m:
                fixtures.append(m)
        return fixtures

    def __repr__(self):
        return f"[Group {self.group_id}] \"{self.name}\" ({len(self.members)} fixture(s))"


class GroupPool:
    def __init__(self):
        self.groups = {}   # { group_id (int): Group }

    def get(self, gid):
        return self.groups.get(int(gid))

    def record(self, group_id, programmer, name=""):
        g = Group(group_id, name or f"Group {group_id}")
        g.record(programmer)
        self.groups[g.group_id] = g
        return g

    def recall(self, group_id, programmer):
        """Select the group's fixtures into the programmer."""
        g = self.get(group_id)
        if g:
            fixtures = g.recall(programmer.patch)
            programmer.select(fixtures)
        return g

    def delete(self, group_id):
        self.groups.pop(int(group_id), None)

    def print_pool(self):
        print("\n===== GROUPS =====")
        for g in self.groups.values():
            print(f"  {g}")


# ============================================================
# STUDIO CONSOLE - Core Object Model
# Block 6: Cue and CueStack
# Delta-based tracking, decimal cue numbers,
# fade/delay times, GO/BACK/GOTO playback.
# ============================================================

class Cue:
    """
    A single cue — a snapshot of active programmer data
    at the moment of recording.

    Stores delta only — what changed, not the full state
    of every fixture. Unmentioned fixtures track from
    previous cues.

    cue_number  — supports decimals (1.0, 1.5, 2.0 etc)
    fade_time   — global default crossfade seconds
    delay_time  — global default pre-fade delay seconds
    fade_times  — per-attribute-group overrides: {'colour': float, 'dim': float, ...}
    delay_times — per-attribute-group delay overrides
    """
    def __init__(self, cue_number, name="", fade_time=0.0, delay_time=0.0,
                 fade_times=None, delay_times=None):
        self.cue_number  = float(cue_number)
        self.name        = name if name else f"Cue {cue_number}"
        self.fade_time   = float(fade_time)
        self.delay_time  = float(delay_time)
        self.fade_times  = dict(fade_times)  if fade_times  else {}
        self.delay_times = dict(delay_times) if delay_times else {}

        # Delta snapshot: { fixture_id_string: { channel: value } }
        # Only contains what was active in the programmer at record time
        self.data = {}

    def record(self, programmer):
        """
        Snapshot active programmer data into this cue.
        When a master entry carries color_ref, sub-fixture RGB entries are
        omitted — the reference resolves them live at playback time.
        dim_ref is stored alongside the inline dim value as a fallback.
        """
        self.data = {}
        color_ref_masters = {
            fid for fid, vals in programmer.data.items()
            if '.' not in fid and vals.get('color_ref')
        }
        for fid, vals in programmer.data.items():
            if not vals:
                continue
            if '.' in fid and fid.split('.')[0] in color_ref_masters:
                continue  # color_ref on master covers these sub-fixtures
            self.data[fid] = copy.deepcopy(vals)

        count = len(self.data)
        print(f"Recorded: {self} ({count} fixture/pixel entries)")

    def update(self, programmer):
        """
        Merge programmer data INTO this cue (channel-level LTP).
        Fixtures not in the programmer are left exactly as-is.
        Channels present in the programmer overwrite the cue's value for
        that channel; channels already in the cue but not in the programmer
        are preserved.
        """
        color_ref_masters = {
            fid for fid, vals in programmer.data.items()
            if '.' not in fid and vals.get('color_ref')
        }
        for fid, vals in programmer.data.items():
            if not vals:
                continue
            if '.' in fid and fid.split('.')[0] in color_ref_masters:
                continue
            if fid not in self.data:
                self.data[fid] = {}
            self.data[fid].update(copy.deepcopy(vals))

        count = len(self.data)
        print(f"Updated: {self} ({count} fixture/pixel entries total)")

    def __repr__(self):
        timing = f"Fade:{self.fade_time}s"
        if self.delay_time > 0:
            timing += f" Delay:{self.delay_time}s"
        if self.fade_times:
            for grp, ft in self.fade_times.items():
                dt = self.delay_times.get(grp, 0.0)
                timing += f" {grp.capitalize()}Fade:{ft}s"
                if dt > 0:
                    timing += f"+{dt}s"
        return f"[Cue {self.cue_number}] \"{self.name}\" | {timing}"


class CueStack:
    """
    An ordered list of cues — like a sequence/executor in MA3.
    Supports decimal cue numbers for inserting between existing cues.
    Tracks current playback position.

    Playback commands:
        GO      — advance to next cue
        BACK    — step to previous cue
        GOTO n  — jump to specific cue number
    """
    def __init__(self, stack_id, name=""):
        self.stack_id        = stack_id
        self.name            = name if name else f"CueStack {stack_id}"
        self.cues            = {}        # { cue_number (float): Cue }
        self.current         = None      # Current cue number (float) or None
        self.allow_exec_time = True      # False = ignore executor time override for this stack

    def _sorted_cue_numbers(self):
        """Returns cue numbers in ascending order."""
        return sorted(self.cues.keys())

    def record_cue(self, cue_number, programmer,
                   name="", fade_time=0.0, delay_time=0.0):
        """
        Record a new cue from the programmer.
        If cue_number already exists it gets overwritten.
        """
        if not programmer.data:
            print("Programmer is empty — nothing to record.")
            return None

        cue = Cue(cue_number, name, fade_time, delay_time)
        cue.record(programmer)
        self.cues[float(cue_number)] = cue
        return cue

    def get_cue(self, cue_number):
        return self.cues.get(float(cue_number), None)

    def delete_cue(self, cue_number):
        num = float(cue_number)
        if num in self.cues:
            del self.cues[num]
            if self.current == num:
                self.current = None
            print(f"Deleted Cue {cue_number} from {self.name}")
        else:
            print(f"Cue {cue_number} not found.")

    # ----------------------------------------------------------
    # Playback
    # ----------------------------------------------------------

    def go(self, patch):
        """
        Advance to the next cue and apply it.
        Loops back to first cue after the last.
        """
        numbers = self._sorted_cue_numbers()
        if not numbers:
            print("CueStack is empty.")
            return

        if self.current is None:
            next_num = numbers[0]
        else:
            try:
                idx      = numbers.index(self.current)
                next_num = numbers[(idx + 1) % len(numbers)]
            except ValueError:
                next_num = numbers[0]

        self._fire_cue(next_num, patch)

    def back(self, patch):
        """Step to the previous cue."""
        numbers = self._sorted_cue_numbers()
        if not numbers:
            print("CueStack is empty.")
            return

        if self.current is None:
            prev_num = numbers[-1]
        else:
            try:
                idx      = numbers.index(self.current)
                prev_num = numbers[(idx - 1) % len(numbers)]
            except ValueError:
                prev_num = numbers[-1]

        self._fire_cue(prev_num, patch)

    def goto(self, cue_number, patch):
        """Jump directly to a specific cue number."""
        num = float(cue_number)
        if num not in self.cues:
            print(f"Cue {cue_number} not found in {self.name}.")
            return
        self._fire_cue(num, patch)

    def _fire_cue(self, cue_number, patch):
        """
        Apply a cue's data directly to fixtures.
        This is the playback output layer — separate from
        the programmer. Cue data goes straight to fixtures.

        Note: In the full engine this will merge with the
        output merger (HTP/LTP). For now it writes directly
        so we can verify cue data is correct before the
        network engine is built.
        """
        cue = self.cues[cue_number]
        self.current = cue_number

        applied = 0
        for fid, vals in cue.data.items():
            if '.' in fid:
                parts   = fid.split('.')
                fixture = patch.get_sub(int(parts[0]), int(parts[1]))
                if fixture:
                    if 'red'   in vals: fixture.red   = vals['red']
                    if 'green' in vals: fixture.green = vals['green']
                    if 'blue'  in vals: fixture.blue  = vals['blue']
                    applied += 1
            else:
                fixture = patch.get(int(fid))
                if fixture:
                    if 'dim' in vals:
                        fixture.virtual_dimmer = vals['dim']
                    applied += 1

        print(f"\nFired: {cue}")
        print(f"  Applied to {applied} fixture/pixel entries")
        print(f"  Timing: delay {cue.delay_time}s → fade {cue.fade_time}s")
        print(f"  (Fade engine connects in Block 7)\n")

    # ----------------------------------------------------------
    # Display
    # ----------------------------------------------------------

    def print_stack(self):
        print(f"\n===== {self.name} =====")
        if not self.cues:
            print("  (empty)")
        for num in self._sorted_cue_numbers():
            cue    = self.cues[num]
            marker = " ◀ CURRENT" if num == self.current else ""
            print(f"  {cue}{marker}")
        print("=" * (len(self.name) + 12) + "\n")


class CuePool:
    """Numbered library of standalone Cue objects (1-based slots)."""
    def __init__(self):
        self.cues = {}      # { int slot: Cue }

    def get(self, n):
        return self.cues.get(int(n))

    def store(self, n, cue):
        self.cues[int(n)] = cue

    def delete(self, n):
        self.cues.pop(int(n), None)

    def record(self, n, programmer, name="", fade_time=0.0):
        cue = Cue(n, name or f"Cue {n}", fade_time)
        cue.record(programmer)
        self.cues[int(n)] = cue
        return cue


class CueStackPool:
    """Pool of CueStack objects (executors), numbered 1-based."""
    def __init__(self):
        self.stacks = {}    # { int slot: CueStack }

    def get(self, n):
        return self.stacks.get(int(n))

    def store(self, n, stack):
        self.stacks[int(n)] = stack

    def create(self, n, name=""):
        existing = self.stacks.get(int(n))
        if existing:
            # Rename in-place — preserves cues and executor references
            existing.name = name or f"Cuestack {n}"
            return existing
        cs = CueStack(int(n), name or f"Cuestack {n}")
        self.stacks[int(n)] = cs
        return cs

    def delete(self, n):
        self.stacks.pop(int(n), None)

    def all_slots(self):
        return sorted(self.stacks.keys())


# ============================================================
# Executor + ExecutorPool
# Each executor is a live playback slot that holds a CueStack
# reference and owns its own output layer dict.
# OutputState reads from all active executor layers and merges
# them LTP (most recently fired = highest priority).
# ============================================================

class Executor:
    """One physical playback slot — a cuestack running in real time."""

    # Priority constants
    PRIORITY_LOW    = -1
    PRIORITY_NORMAL =  0
    PRIORITY_HIGH   =  1
    PRIORITY_LABELS = {-1: 'LO', 0: 'NRM', 1: 'HI'}

    def __init__(self, exec_id):
        self.exec_id      = exec_id
        self.cuestack     = None
        self.is_active    = False
        self.level        = 1.0      # master fader, 0.0–1.0
        self.priority     = 0        # -1 low / 0 normal / 1 high
        self.trigger_mode = 'toggle' # 'toggle' (GO/BACK advance) or 'flash' (live only while held)
        self.layer     = {}       # { fid_str: { channel: value } }
        self._fx_ids     = []     # FX engine layer IDs currently active for this executor
        self._fx_counter = 0      # ever-increasing; avoids ID reuse during outfade overlap
        self.fx_engine  = None    # injected from ExecutorPool
        self.form_pool  = None    # injected from ExecutorPool
        self.color_pool = None    # injected from ExecutorPool
        self.dim_pool   = None    # injected from ExecutorPool
        self.group_pool = None    # injected from ExecutorPool
        # Time overrides — None means "use cue's own time"
        self.time_override_fade  = None   # float seconds or None
        self.time_override_delay = None   # float seconds or None
        self.time_override_on    = False  # master enable for this executor's override

    def assign(self, cuestack):
        self.cuestack = cuestack

    def set_value(self, fid, channel, value):
        """Called by Fade.tick() on every interpolation step."""
        if fid not in self.layer:
            self.layer[fid] = {}
        self.layer[fid][channel] = value

    def snapshot_layer(self):
        """Deep copy used as the 'from' state when starting a new fade."""
        return {fid: dict(vals) for fid, vals in self.layer.items()}

    # ── FX management ────────────────────────────────────────

    def _clear_fx(self):
        """Remove all FX layers owned by this executor from the shared engine."""
        if self.fx_engine:
            for fxid in self._fx_ids:
                self.fx_engine.remove(fxid)
        self._fx_ids.clear()

    def _start_cue_fx(self, cue, patch, default_infade=0.0, default_outfade=0.0):
        """
        Read FX defs from cue.data master entries and start layers.
        Old layers are outfaded (not instant-killed) so FX crossfades naturally.
        Each layer ID is exec_id * 10000 + ever-increasing counter so IDs never
        repeat even while outfading layers are still in the engine.
        default_infade  — fallback infade when the FX def doesn't set one;
                          callers pass the effective cue fade time.
        default_outfade — fallback outfade applied to outgoing layers that
                          had no explicit outfade; callers pass eff_fade so
                          old FX ramps out in sync with the DMX crossfade.
        """
        if not self.fx_engine:
            self._fx_ids = []
            return

        # Outfade old layers — they self-remove when amplitude reaches 0
        now = time.monotonic()
        for fxid in self._fx_ids:
            self.fx_engine.remove(fxid, now, default_outfade=default_outfade)
        self._fx_ids = []

        fx_defs_by_fid = {}
        for fid_str, vals in cue.data.items():
            if '.' in fid_str:
                continue
            fx_defs = vals.get('fx', [])
            if fx_defs:
                fx_defs_by_fid[fid_str] = fx_defs

        # Expand color_id refs and resolve group_id targets
        expanded = _expand_color_fx(fx_defs_by_fid, self.color_pool)
        expanded = _expand_group_fx(expanded, patch, self.group_pool)

        def _add(ld, ch, targets):
            self._fx_counter += 1
            fxid = self.exec_id * 10000 + self._fx_counter
            # Use default_infade (cue fade time) when the FX def has no explicit infade
            infade = ld['infade'] if 'infade' in ld else default_infade
            self.fx_engine.add(
                fxid, ld.get('waveform', 'sine'), ch,
                rate_bpm     = ld.get('bpm',          60.0),
                size         = ld.get('size',        100.0),
                targets      = targets,
                spread       = ld.get('spread',        0.0),
                phase_offset = ld.get('phase_offset',  0.0),
                form_id      = ld.get('form_id'),
                rate_id      = ld.get('rate_id'),
                size_id      = ld.get('size_id'),
                spread_id    = ld.get('spread_id'),
                dim_id       = ld.get('dim_id'),
                infade       = infade,
                outfade      = ld.get('outfade',       0.0),
                block_size   = ld.get('block_size',      1),
                order        = ld.get('order',    'linear'),
                direction    = ld.get('direction','forward'),
            )
            self._fx_ids.append(fxid)

        # _bucket_fx_defs (module-level, defined near FXEngine) merges
        # identical defs across fixtures into one layer so spread/chase can
        # cross fixture boundaries — see target_scope in FX command docs.
        for ld, targets in _bucket_fx_defs(expanded, patch):
            _add(ld, ld['channel'], targets)

    # ── Playback ─────────────────────────────────────────────

    def go(self, patch, fade_engine):
        if not self.cuestack:
            return f"Executor {self.exec_id}: no cuestack assigned"
        self.is_active = True
        return self.cuestack.go(patch, fade_engine, self)

    def back(self, patch, fade_engine):
        if not self.cuestack:
            return f"Executor {self.exec_id}: no cuestack assigned"
        self.is_active = True
        return self.cuestack.back(patch, fade_engine, self)

    def goto(self, num, patch, fade_engine):
        if not self.cuestack:
            return f"Executor {self.exec_id}: no cuestack assigned"
        self.is_active = True
        return self.cuestack.goto(num, patch, fade_engine, self)

    def reload(self, patch, fade_engine):
        """Re-fire the current cue from scratch without advancing."""
        if not self.cuestack:
            return f"Executor {self.exec_id}: no cuestack assigned"
        self.is_active = True
        return self.cuestack.reload(patch, fade_engine, self)

    def flash_on(self, patch, fade_engine):
        """
        Snap the current (or first) cue on instantly, bypassing crossfade —
        for 'flash' trigger_mode: live only while held, released via
        flash_off(). Reuses the existing executor time-override mechanism
        (still subject to the cuestack's allow_exec_time flag) rather than
        a separate instant-fire path.
        """
        if not self.cuestack:
            return f"Executor {self.exec_id}: no cuestack assigned"
        prev_override = (self.time_override_on, self.time_override_fade, self.time_override_delay)
        self.time_override_on    = True
        self.time_override_fade  = 0.0
        self.time_override_delay = 0.0
        try:
            if self.cuestack.current is not None:
                result = self.goto(self.cuestack.current, patch, fade_engine)
            else:
                result = self.go(patch, fade_engine)
        finally:
            (self.time_override_on, self.time_override_fade,
             self.time_override_delay) = prev_override
        return result

    def flash_off(self):
        """Release a flash — fully stops the executor (clears layer + FX)."""
        self.stop()

    def stop(self):
        self._clear_fx()
        self.is_active = False
        self.layer.clear()
        if self.cuestack:
            self.cuestack.current = None


class ExecutorPool:
    """Numbered bank of Executor slots (1-based)."""

    def __init__(self):
        self.executors       = {}    # { int: Executor }
        self._fire_order     = []    # exec_ids ordered by last GO (last = highest priority)
        self.default_fx_engine   = None
        self.default_form_pool   = None
        self.default_color_pool  = None
        self.default_dim_pool    = None
        self.default_group_pool  = None
        self.default_attr_pools  = None   # dict of {attribute_name: AttributePool}
        # Pages group executor slots for display/navigation — organizational
        # only, doesn't affect playback. { int: {'name': str, 'slots': [int, ...]} }
        self.pages = {}

    def get(self, n):
        n = int(n)
        if n not in self.executors:
            ex = Executor(n)
            ex.fx_engine  = self.default_fx_engine
            ex.form_pool  = self.default_form_pool
            ex.color_pool = self.default_color_pool
            ex.dim_pool   = self.default_dim_pool
            ex.group_pool = self.default_group_pool
            ex.attr_pools = self.default_attr_pools
            self.executors[n] = ex
        return self.executors[n]

    def assign(self, exec_id, cuestack):
        ex = self.get(exec_id)
        ex.assign(cuestack)
        return ex

    def bump_priority(self, exec_id):
        """Move exec to top of the LTP stack (called when it fires GO)."""
        if exec_id in self._fire_order:
            self._fire_order.remove(exec_id)
        self._fire_order.append(exec_id)

    def active_layers(self):
        """
        Returns list of (layer_dict, level) in merge order.
        First entry = lowest priority, last entry = highest (LTP — last written wins).
        Sorted by: executor priority level first, then fire order within same level.
        """
        entries = []
        for i, eid in enumerate(self._fire_order):
            ex = self.executors.get(eid)
            if ex and ex.is_active and ex.cuestack:
                entries.append((ex.priority, i, ex.layer, ex.level))
        entries.sort(key=lambda e: (e[0], e[1]))
        return [(layer, level) for _, _, layer, level in entries]

    def all_slots(self):
        return sorted(self.executors.keys())

    # ── Pages ────────────────────────────────────────────────

    def get_page(self, n):
        n = int(n)
        if n not in self.pages:
            self.pages[n] = {'name': f'Page {n}', 'cuestacks': []}
        return self.pages[n]

    def set_page_name(self, n, name):
        self.get_page(n)['name'] = name

    def add_to_page(self, n, cs_id):
        page = self.get_page(n)
        cs_id = int(cs_id)
        if cs_id not in page['cuestacks']:
            page['cuestacks'].append(cs_id)

    def remove_from_page(self, n, cs_id):
        page = self.get_page(n)
        cs_id = int(cs_id)
        if cs_id in page['cuestacks']:
            page['cuestacks'].remove(cs_id)

    def delete_page(self, n):
        self.pages.pop(int(n), None)

    def all_pages(self):
        return sorted(self.pages.keys())


# ============================================================
# FXPreset + FXPool
# A preset is a snapshot of one or more FX layer definitions.
# Targets are NOT stored — resolved at fire time from patch/group.
# ============================================================

class FXPreset:
    """One named FX state: a list of layer defs that fire together."""

    def __init__(self, preset_id, name=""):
        self.preset_id = int(preset_id)
        self.name      = name or f"FX {preset_id}"
        self.layers    = []   # list of dicts: {waveform, channel, rate_bpm, size, spread}

    def add_layer(self, waveform, channel, rate_bpm=60.0, size=100.0, spread=0.0,
                  form_id=None, rate_id=None, size_id=None, spread_id=None, bpm=None,
                  dim_id=None, color_id=None, group_id=None,
                  phase_offset=0.0, block_size=1, order='linear', direction='forward',
                  target_scope=None):
        self.layers.append({
            'waveform':      waveform.lower(),
            'channel':       channel.lower(),
            'bpm':           float(bpm if bpm is not None else rate_bpm),
            'size':          float(size),
            'spread':        float(spread),
            'phase_offset':  float(phase_offset),
            'form_id':       form_id,
            'rate_id':       rate_id,
            'size_id':       size_id,
            'spread_id':     spread_id,
            'dim_id':        dim_id,
            'color_id':      color_id,
            'group_id':      group_id,
            'block_size':    block_size,
            'order':         order,
            'direction':     direction,
            'target_scope':  target_scope,
        })

    def fire(self, fx_engine, targets, base_id=1):
        """Start all layers in this preset without clearing other running FX."""
        fired = []
        for i, ld in enumerate(self.layers, 1):
            layer = fx_engine.add(
                base_id + i,
                ld['waveform'],
                ld['channel'],
                rate_bpm     = ld.get('bpm', ld.get('rate_bpm', 60.0)),
                size         = ld['size'],
                targets      = targets,
                spread       = ld['spread'],
                phase_offset = ld.get('phase_offset', 0.0),
                form_id      = ld.get('form_id'),
                rate_id      = ld.get('rate_id'),
                size_id      = ld.get('size_id'),
                spread_id    = ld.get('spread_id'),
                dim_id       = ld.get('dim_id'),
                color_id     = ld.get('color_id'),
                block_size   = ld.get('block_size', 1),
                order        = ld.get('order', 'linear'),
                direction    = ld.get('direction', 'forward'),
            )
            fired.append(layer)
        return fired

    def __repr__(self):
        parts = [f"{ld['waveform']} {ld['channel']}" for ld in self.layers]
        return f"[FX {self.preset_id}] {self.name}  ({', '.join(parts)})"


class FXPool:
    """Numbered library of FXPreset objects (1-based slots)."""

    def __init__(self):
        self.presets = {}   # {int: FXPreset}

    def get(self, n):
        return self.presets.get(int(n))

    def store(self, n, preset):
        self.presets[int(n)] = preset

    def delete(self, n):
        self.presets.pop(int(n), None)

    def record_from_active(self, n, active_fx_list, name=""):
        """Snapshot currently running FXLayer objects into a new preset, preserving pool refs."""
        preset = FXPreset(int(n), name or f"FX {n}")
        for layer in active_fx_list:
            preset.add_layer(
                layer.waveform, layer.channel,
                bpm       = layer._bpm_inline,
                size      = layer._size_inline,
                spread    = layer._spread_inline,
                form_id   = layer.form_id,
                rate_id   = layer._rate_id,
                size_id   = layer._size_id,
                spread_id = layer._spread_id,
            )
        self.presets[int(n)] = preset
        return preset

    def all_slots(self):
        return sorted(self.presets.keys())


# ============================================================
# STUDIO CONSOLE - Block 7: Network Engine
# OutputState — merged DMX output layer
# Fade / FadeEngine — cue timing and crossfades
# NetworkEngine — sACN multicast broadcast at 44Hz
# ============================================================

import sacn
import threading
import time
import random


# ------------------------------------------------------------
# OutputState
# ------------------------------------------------------------

# ------------------------------------------------------------
# Fade
# ------------------------------------------------------------

class Fade:
    """
    One active crossfade between two states.
    Interpolates linearly from data_from → data_to
    over fade_time seconds, after an optional delay_time.
    Writes into executor.layer via executor.set_value().
    """

    # Map channel names to attribute groups for per-group timing
    _CHANNEL_GROUP = {
        'red': 'colour', 'green': 'colour', 'blue': 'colour',
        'dim': 'dim',
    }

    def __init__(self, data_from, data_to, fade_time, delay_time, executor,
                 fade_times=None, delay_times=None):
        self.data_from    = data_from
        self.data_to      = data_to
        self._default_ft  = float(fade_time)
        self._default_dt  = float(delay_time)
        self.executor     = executor
        self.done         = False

        now = time.monotonic()
        _ft  = fade_times  or {}
        _dt  = delay_times or {}

        # Pre-compute start_time and fade_time per group so tick() does no dict creation
        all_groups = set(_ft) | set(_dt)
        self._group_ft    = {g: float(_ft.get(g, self._default_ft)) for g in all_groups}
        self._group_start = {g: now + float(_dt.get(g, self._default_dt)) for g in all_groups}
        self._default_start = now + self._default_dt

    def tick(self, now):
        all_done = True

        for fid in set(self.data_from) | set(self.data_to):
            from_vals = self.data_from.get(fid, {})
            to_vals   = self.data_to.get(fid, {})
            for ch in set(from_vals) | set(to_vals):
                v_from = from_vals.get(ch, 0)
                # Flag channels (fx_kill etc.) reset to 0 when absent from the new
                # cue rather than persisting via LTP — the flag should only be active
                # when explicitly stored in the current cue's data.
                _flag = ch in ('fx_kill',)
                v_to   = to_vals.get(ch, 0 if _flag else v_from)
                if not isinstance(v_from, (int, float)) or not isinstance(v_to, (int, float)):
                    continue  # skip non-DMX keys (fx defs, refs, etc.)

                group   = Fade._CHANNEL_GROUP.get(ch, 'other')
                start   = self._group_start.get(group, self._default_start)
                ft      = self._group_ft.get(group,    self._default_ft)

                elapsed = now - start
                if elapsed < 0:
                    all_done = False
                    continue  # still in delay for this attribute group

                t = 1.0 if ft == 0 else min(1.0, elapsed / ft)
                if t < 1.0:
                    all_done = False

                self.executor.set_value(fid, ch, v_from + (v_to - v_from) * t)

        self.done = all_done


# ------------------------------------------------------------
# FadeEngine
# ------------------------------------------------------------

class FadeEngine:
    """
    Manages all active Fade objects.
    Runs in a background thread at 44Hz.
    Multiple fades can overlap — new cue fires while previous
    is still running and they crossfade naturally.
    Each fade writes to its executor's own layer.
    """
    def __init__(self):
        self._fades  = []
        self._lock   = threading.Lock()
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def fire(self, cue, executor, data_to=None,
             override_fade=None, override_delay=None):
        """Snapshot executor's current layer and fade to new cue state.
        data_to: pre-resolved DMX dict; falls back to cue.data if not provided.
        override_fade / override_delay: time override from executor or programmer."""
        ft = override_fade  if override_fade  is not None else cue.fade_time
        dt = override_delay if override_delay is not None else cue.delay_time
        # Per-attribute times are suppressed when a global override is active
        fat = None if override_fade  is not None else (cue.fade_times  or None)
        dat = None if override_delay is not None else (cue.delay_times or None)
        fade = Fade(
            data_from   = executor.snapshot_layer(),
            data_to     = data_to if data_to is not None else cue.data,
            fade_time   = ft,
            delay_time  = dt,
            executor    = executor,
            fade_times  = fat,
            delay_times = dat,
        )
        with self._lock:
            self._fades.append(fade)
        src = " [override]" if override_fade is not None else ""
        print(f"  Fade: {dt}s delay → {ft}s crossfade{src}")

    def _run(self):
        while self._running:
            now = time.monotonic()
            with self._lock:
                for fade in self._fades:
                    fade.tick(now)
                self._fades = [f for f in self._fades if not f.done]
            time.sleep(1 / 44)

    def fade_progress(self, executor):
        """Return (elapsed_fraction, total_seconds) for the most recent active fade on
        this executor, or None if no fade is currently running."""
        now = time.monotonic()
        best = None
        with self._lock:
            for fade in self._fades:
                if fade.executor is executor and not fade.done:
                    ft = fade._default_ft
                    elapsed = now - fade._default_start
                    t = 1.0 if ft == 0 else min(1.0, max(0.0, elapsed / ft))
                    if best is None or elapsed > best[0]:
                        best = (elapsed, t, ft)
        if best is None:
            return None
        return best[1], best[2]   # (progress 0–1, total_seconds)

    def stop(self):
        self._running = False


# ------------------------------------------------------------
# NetworkEngine
# ------------------------------------------------------------

class NetworkEngine:
    """
    sACN multicast broadcast loop at 44Hz.
    Reads merged DMX values from OutputState every frame.
    """
    def __init__(self, output_state, universes, source_name="Studio Console",
                 broadcast_mode=False, bind_address="", dry_run=False):
        self.output_state   = output_state
        self.universes      = universes
        self.source_name    = source_name
        self.broadcast_mode = broadcast_mode
        self.bind_address   = bind_address
        self.dry_run        = dry_run   # True: compute DMX every tick but never open a real socket
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
        while self._running:
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
            time.sleep(1 / 44)


# ------------------------------------------------------------
# Updated CueStack playback methods
# go / back / goto now route through FadeEngine
# ------------------------------------------------------------

def _resolve_cue_refs(cue_data, patch, color_pool, dim_pool, attr_pools=None):
    """
    Expand all *_ref keys in cue_data to raw DMX values.

    color_ref  → sub-fixture RGB via ColorPool
    dim_ref    → master dim via DimmerPool
    <x>_ref    → master/fixture channel values via attr_pools dict
                 e.g. attr_pools={"position": position_pool, "gobo": gobo_pool}

    Returns a new dict safe to pass to FadeEngine (no ref metadata, no lists).
    """
    attr_pools   = attr_pools or {}
    attr_ref_keys = {f"{name}_ref" for name in attr_pools}
    _SKIP_KEYS   = {'fx', 'color_ref', 'dim_ref', 'color_baked'} | attr_ref_keys
    masters_with_color_ref = set()
    resolved = {}

    # First pass: master entries
    for fid, vals in cue_data.items():
        if '.' in fid:
            continue
        color_ref = vals.get('color_ref')
        dim_ref   = vals.get('dim_ref')
        master_vals = {k: v for k, v in vals.items() if k not in _SKIP_KEYS}

        if dim_ref and dim_pool:
            dp = dim_pool.get(int(dim_ref))
            if dp:
                master_vals['dim'] = dp.level

        # Generic attribute ref expansion (position_ref, gobo_ref, zoom_ref, etc.)
        for attr_name, pool in attr_pools.items():
            ref_id = vals.get(f"{attr_name}_ref")
            if ref_id is not None:
                ap = pool.get(int(ref_id))
                if ap:
                    src = ap.data.get(fid)
                    if src:
                        master_vals.update(src)

        if master_vals:
            resolved[fid] = master_vals

        if color_ref and color_pool:
            masters_with_color_ref.add(fid)
            preset = color_pool.get(int(color_ref))
            if preset:
                try:
                    master = patch.get(int(fid))
                except (ValueError, TypeError):
                    master = None
                if master:
                    for sub in master.all_subs():
                        resolved[str(sub.fixture_id)] = {
                            'red':   preset.red,
                            'green': preset.green,
                            'blue':  preset.blue,
                        }

    # Second pass: sub-fixture entries not covered by a color_ref expansion
    for fid, vals in cue_data.items():
        if '.' not in fid:
            continue
        master_fid = fid.split('.')[0]
        if master_fid in masters_with_color_ref:
            continue  # already written by color_ref expansion
        if fid not in resolved:
            resolved[fid] = {k: v for k, v in vals.items() if k not in _SKIP_KEYS}

    return resolved


def _cuestack_fire_cue(self, cue_number, patch, fade_engine, executor):
    cue = self.cues[cue_number]
    self.current = cue_number
    executor.is_active = True

    # If the new cue doesn't have fx_kill set, explicitly clear it from the executor
    # layer now so the incoming Fade snapshot doesn't carry a stale 1.0 into v_from.
    if not any(v.get('fx_kill') for v in cue.data.values() if isinstance(v, dict)):
        for fid_vals in executor.layer.values():
            fid_vals.pop('fx_kill', None)

    resolved = _resolve_cue_refs(
        cue.data, patch,
        getattr(executor, 'color_pool',    None),
        getattr(executor, 'dim_pool',      None),
        getattr(executor, 'attr_pools',    None),
    )
    print(f"\nGO → {cue}  [exec {executor.exec_id}]")

    # Resolve time override: executor override wins; programmer time is fallback
    ov_fade = ov_delay = None
    cs = executor.cuestack
    if (executor.time_override_on
            and (cs is None or cs.allow_exec_time)):
        if executor.time_override_fade  is not None:
            ov_fade  = executor.time_override_fade
        if executor.time_override_delay is not None:
            ov_delay = executor.time_override_delay
    # Programmer time fallback — only if no executor override applied
    if ov_fade is None and _prog_time.get('on'):
        ov_fade  = float(_prog_time['fade'])
        ov_delay = float(_prog_time['delay'])

    # Effective fade time — used as default FX infade so FX ramps match DMX fades
    eff_fade = ov_fade if ov_fade is not None else cue.fade_time

    executor._start_cue_fx(cue, patch, default_infade=eff_fade, default_outfade=eff_fade)

    fade_engine.fire(cue, executor, data_to=resolved,
                     override_fade=ov_fade, override_delay=ov_delay)
    return f"GO → {cue.name}"

def _cuestack_go(self, patch, fade_engine, executor):
    numbers = self._sorted_cue_numbers()
    if not numbers:
        return "CueStack is empty"
    if self.current is None:
        next_num = numbers[0]
    else:
        try:
            idx      = numbers.index(self.current)
            next_num = numbers[(idx + 1) % len(numbers)]
        except ValueError:
            next_num = numbers[0]
    return _cuestack_fire_cue(self, next_num, patch, fade_engine, executor)

def _cuestack_back(self, patch, fade_engine, executor):
    numbers = self._sorted_cue_numbers()
    if not numbers:
        return "CueStack is empty"
    if self.current is None:
        prev_num = numbers[-1]
    else:
        try:
            idx      = numbers.index(self.current)
            prev_num = numbers[(idx - 1) % len(numbers)]
        except ValueError:
            prev_num = numbers[-1]
    return _cuestack_fire_cue(self, prev_num, patch, fade_engine, executor)

def _cuestack_goto(self, cue_number, patch, fade_engine, executor):
    num = float(cue_number)
    if num not in self.cues:
        return f"Cue {cue_number} not found"
    return _cuestack_fire_cue(self, num, patch, fade_engine, executor)

def _cuestack_reload(self, patch, fade_engine, executor):
    """Re-fire the current cue without advancing the pointer."""
    if self.current is None:
        return "No active cue — use GO to start"
    return _cuestack_fire_cue(self, self.current, patch, fade_engine, executor)

CueStack.go     = _cuestack_go
CueStack.back   = _cuestack_back
CueStack.goto   = _cuestack_goto
CueStack.reload = _cuestack_reload


# ============================================================
# STUDIO CONSOLE - Block 8: FX Engine
# Waveform-based FX: Sine, Ramp, Pulse, Square
# BPM-controlled, phase-spread across pixels for chase effects
# ============================================================

import math


# ------------------------------------------------------------
# Waveform functions
# Input:  t = phase 0.0 → 1.0
# Output: value 0.0 → 1.0
# ------------------------------------------------------------

class Waveform:
    @staticmethod
    def sine(t):
        return (math.sin(2 * math.pi * t - math.pi / 2) + 1) / 2

    @staticmethod
    def ramp(t):
        return t % 1.0

    @staticmethod
    def square(t):
        return 1.0 if (t % 1.0) < 0.5 else 0.0

    @staticmethod
    def pulse(t):
        return 1.0 if (t % 1.0) < 0.25 else 0.0

    @staticmethod
    def triangle(t):
        t = t % 1.0
        return 1.0 - abs(2 * t - 1.0)

    @staticmethod
    def sawtooth(t):
        return 1.0 - (t % 1.0)

    @staticmethod
    def flicker(t):
        # Deterministic noise hash — same phase → same value, but visually random
        n = (int(t * 23) ^ 0xA5B3) & 0xFFFF
        n = ((n ^ (n << 13)) ^ (n >> 7) ^ (n << 17)) & 0xFF
        return n / 255.0

    @staticmethod
    def get(name):
        return {
            'sine':     Waveform.sine,
            'ramp':     Waveform.ramp,
            'pulse':    Waveform.pulse,
            'square':   Waveform.square,
            'triangle': Waveform.triangle,
            'sawtooth': Waveform.sawtooth,
            'flicker':  Waveform.flicker,
        }.get(name.lower(), Waveform.sine)


# ============================================================
# FormPreset + FormPool
# A FormPreset is a waveform shape: either a reference to one
# of the built-in Waveform functions, or a user-defined
# breakpoint curve (list of [phase, value] pairs, 0.0-1.0).
#
# FormPool pre-seeds slots 1-4 with the built-in shapes.
# Custom forms (slot 5+) are persisted to studio_data/forms.json.
# The FX engine resolves form functions at runtime from this pool.
# ============================================================

class FormPreset:
    """One named waveform shape — built-in or breakpoint curve."""

    def __init__(self, form_id, name, form_type='builtin',
                 builtin_name=None, breakpoints=None):
        self.form_id      = int(form_id)
        self.name         = name
        self.form_type    = form_type       # 'builtin' | 'breakpoints'
        self.builtin_name = builtin_name    # e.g. 'sine'
        self.breakpoints  = breakpoints or []  # [[phase, value], ...]

    def get_fn(self):
        """Return a callable: phase (0.0–1.0) → value (0.0–1.0)."""
        if self.form_type == 'builtin':
            return Waveform.get(self.builtin_name or 'sine')

        # Breakpoint interpolation — captured in closure at call time
        preset = self

        def _interp(phase):
            pts = sorted(preset.breakpoints, key=lambda p: p[0])
            if not pts:
                return 0.0
            p = float(phase) % 1.0
            if p <= pts[0][0]:
                return float(pts[0][1])
            if p >= pts[-1][0]:
                return float(pts[-1][1])
            for i in range(len(pts) - 1):
                p0, v0 = pts[i][0], pts[i][1]
                p1, v1 = pts[i + 1][0], pts[i + 1][1]
                if p0 <= p <= p1:
                    t = (p - p0) / (p1 - p0) if p1 != p0 else 0.0
                    return float(v0 + (v1 - v0) * t)
            return 0.0

        return _interp

    def __repr__(self):
        if self.form_type == 'builtin':
            return f"[Form {self.form_id}] {self.name}  (builtin: {self.builtin_name})"
        return (f"[Form {self.form_id}] {self.name}  "
                f"(custom breakpoints: {len(self.breakpoints)} pts)")


class FormPool:
    """Numbered library of FormPreset waveform shapes (1-based).
    Slots 1-4 are always the built-ins; 5+ are user-defined."""

    _BUILTINS = [
        (1, 'Sine',   'sine'),
        (2, 'Ramp',   'ramp'),
        (3, 'Pulse',  'pulse'),
        (4, 'Square', 'square'),
    ]
    FIRST_CUSTOM_SLOT = 5

    def __init__(self):
        self.forms = {}
        for fid, name, bname in self._BUILTINS:
            self.forms[fid] = FormPreset(fid, name, 'builtin', bname)

    def get(self, n):
        return self.forms.get(int(n))

    def get_by_name(self, name):
        """Case-insensitive lookup by name or builtin_name."""
        nu = name.upper()
        for f in self.forms.values():
            if f.name.upper() == nu:
                return f
            if f.builtin_name and f.builtin_name.upper() == nu:
                return f
        return None

    def get_fn(self, ref):
        """
        Resolve a waveform function from a form ID (int) or name (str).
        Falls back to Waveform.get() if not found.
        """
        if isinstance(ref, int):
            form = self.get(ref)
        else:
            form = self.get_by_name(str(ref))
        return form.get_fn() if form else Waveform.get(str(ref))

    def store(self, n, form):
        self.forms[int(n)] = form

    def delete(self, n):
        n = int(n)
        if n < self.FIRST_CUSTOM_SLOT:
            return  # built-ins are read-only
        self.forms.pop(n, None)

    def custom_forms(self):
        """Only the user-defined (non-builtin) forms."""
        return {fid: f for fid, f in self.forms.items()
                if f.form_type != 'builtin'}

    def all_slots(self):
        return sorted(self.forms.keys())


# ============================================================
# RatePool / SizePool / SpreadPool
# Separate numbered pools for each FX property so that
# updating one entry propagates live to all referencing layers.
# ============================================================

class RatePreset:
    """BPM / timing preset."""
    _BUILTINS = [(1,'Slow',30.0),(2,'Medium',60.0),(3,'Fast',120.0),(4,'Very Fast',240.0)]
    def __init__(self, preset_id, name, bpm=60.0):
        self.preset_id = int(preset_id)
        self.name      = name
        self.bpm       = float(bpm)
    def __repr__(self):
        return f"[Rate {self.preset_id}] {self.name}  ({self.bpm:.1f} BPM)"

class RatePool:
    def __init__(self):
        self.presets = {}
        for pid, name, bpm in RatePreset._BUILTINS:
            self.presets[pid] = RatePreset(pid, name, bpm)
    def get(self, n):       return self.presets.get(int(n))
    def store(self, n, p):  self.presets[int(n)] = p
    def delete(self, n):    self.presets.pop(int(n), None)
    def all_slots(self):    return sorted(self.presets.keys())

class SizePreset:
    """Amplitude preset (0–100, where 100 = full DMX 255)."""
    _BUILTINS = [(1,'Subtle',25.0),(2,'Medium',50.0),(3,'Full',100.0)]
    def __init__(self, preset_id, name, size=100.0):
        self.preset_id = int(preset_id)
        self.name      = name
        self.size      = float(size)
    def __repr__(self):
        return f"[Size {self.preset_id}] {self.name}  (size={self.size:.0f})"

class SizePool:
    def __init__(self):
        self.presets = {}
        for pid, name, size in SizePreset._BUILTINS:
            self.presets[pid] = SizePreset(pid, name, size)
    def get(self, n):       return self.presets.get(int(n))
    def store(self, n, p):  self.presets[int(n)] = p
    def delete(self, n):    self.presets.pop(int(n), None)
    def all_slots(self):    return sorted(self.presets.keys())

class SpreadPreset:
    """Phase-distribution preset (0 = sync, 100 = full chase)."""
    _BUILTINS = [(1,'Sync',0.0),(2,'Half',50.0),(3,'Chase',100.0)]
    def __init__(self, preset_id, name, spread=100.0):
        self.preset_id = int(preset_id)
        self.name      = name
        self.spread    = float(spread)
    def __repr__(self):
        return f"[Spread {self.preset_id}] {self.name}  (spread={self.spread:.2f})"

class SpreadPool:
    def __init__(self):
        self.presets = {}
        for pid, name, spread in SpreadPreset._BUILTINS:
            self.presets[pid] = SpreadPreset(pid, name, spread)
    def get(self, n):       return self.presets.get(int(n))
    def store(self, n, p):  self.presets[int(n)] = p
    def delete(self, n):    self.presets.pop(int(n), None)
    def all_slots(self):    return sorted(self.presets.keys())


# ------------------------------------------------------------
# FXLayer — one running effect
# ------------------------------------------------------------

class FXLayer:
    """
    A single FX running across a list of sub-fixtures.

    Pool references (form_id, rate_id, size_id, spread_id) are live-tracked:
    updating a pool entry propagates to all FXLayers referencing it on the
    next tick. Inline values (_bpm_inline, _size_inline, _spread_inline) are
    used as fallbacks when no pool ID is set.
    """
    def __init__(self, fx_id, waveform, channel, rate_bpm, size,
                 targets, spread=0.0,
                 form_pool=None, rate_pool=None, size_pool=None, spread_pool=None,
                 dim_pool=None,
                 form_id=None, rate_id=None, size_id=None, spread_id=None,
                 dim_id=None,
                 phase_offset=0.0, infade=0.0, outfade=0.0,
                 block_size=1, order='linear', direction='forward'):
        self.fx_id        = fx_id
        self.waveform     = waveform
        self.channel      = channel
        self.phase_offset = float(phase_offset)   # 0.0–1.0; shifts entire layer in time
        self.targets      = targets
        self.start        = time.monotonic()
        self.is_active    = True

        # Distribution — how targets are grouped/sequenced across the spread.
        # block_size — adjacent targets per step (1 = one target per step).
        # order      — 'linear' (patch order) or 'random' (shuffled once, stable per fx_id).
        # direction  — 'forward' | 'reverse' (flips step sequence) | 'bounce' (phase
        #              folds forward-then-back in time instead of wrapping — the whole
        #              chase sweeps out across targets and back).
        self.block_size = max(1, int(block_size))
        self.order      = order
        self.direction  = direction
        self._offsets   = self._compute_offsets()

        # Amplitude envelope
        self.infade      = float(infade)    # seconds to ramp 0→1 at start
        self.outfade     = float(outfade)   # seconds to ramp 1→0 when fading out
        self._out_start  = None             # set by begin_outfade()

        # Pool references
        self._form_pool   = form_pool
        self._rate_pool   = rate_pool
        self._size_pool   = size_pool
        self._spread_pool = spread_pool
        self._dim_pool    = dim_pool

        # Pool IDs — live-tracked via properties
        self.form_id     = form_id
        self._rate_id    = rate_id
        self._size_id    = size_id
        self._spread_id  = spread_id
        self._dim_id     = dim_id   # DimmerPreset.level used as amplitude ceiling

        # Inline fallback values
        self._bpm_inline    = float(rate_bpm)
        self._size_inline   = float(size)
        self._spread_inline = float(spread)

    def begin_outfade(self, now=None):
        """Trigger amplitude ramp-out. Engine auto-removes when amplitude hits 0."""
        if self._out_start is None:
            self._out_start = time.monotonic() if now is None else now

    @property
    def rate_bpm(self):
        if self._rate_pool and self._rate_id is not None:
            p = self._rate_pool.get(self._rate_id)
            if p: return p.bpm
        return self._bpm_inline

    @rate_bpm.setter
    def rate_bpm(self, val):
        self._bpm_inline = float(val)
        self._rate_id = None

    def set_rate_smooth(self, new_bpm, now=None):
        """Change BPM while preserving current phase position (no jump/glitch)."""
        if now is None:
            now = time.monotonic()
        old_hz = self.rate_bpm / 60.0
        current_phase = ((now - self.start) * old_hz) % 1.0 if old_hz > 0 else 0.0
        self._bpm_inline = float(new_bpm)
        self._rate_id = None
        new_hz = self._bpm_inline / 60.0
        self.start = (now - current_phase / new_hz) if new_hz > 0 else now

    @property
    def size(self):
        if self._size_pool and self._size_id is not None:
            p = self._size_pool.get(self._size_id)
            val = p.size if p else self._size_inline
        else:
            val = self._size_inline
        # dim_id: live ceiling — DimmerPreset.level (0-1) scales max amplitude
        if self._dim_pool and self._dim_id is not None:
            dp = self._dim_pool.get(self._dim_id)
            if dp:
                val = val * dp.level
        return val

    @size.setter
    def size(self, val):
        self._size_inline = float(val)
        self._size_id = None

    @property
    def spread(self):
        if self._spread_pool and self._spread_id is not None:
            p = self._spread_pool.get(self._spread_id)
            if p: return p.spread
        return self._spread_inline

    @spread.setter
    def spread(self, val):
        self._spread_inline = float(val)
        self._spread_id = None

    def _get_fn(self):
        """Resolve waveform function live from FormPool on every call."""
        if self._form_pool and self.form_id is not None:
            form = self._form_pool.get(self.form_id)
            if form:
                return form.get_fn()
        return Waveform.get(self.waveform)

    def _compute_offsets(self):
        """
        Precompute each target's 0.0-1.0 phase offset (before the spread
        multiplier is applied), honoring block_size/order/direction.
        Computed once at construction — order='random' shuffles groups with
        a seed stable for this layer's lifetime, not re-rolled every tick.

        block_size=1, order='linear', direction='forward' reproduces the
        original i/count offset exactly, so existing saved shows are
        unaffected.
        """
        n = len(self.targets)
        if n <= 1:
            return [0.0] * n

        group_of    = [i // self.block_size for i in range(n)]
        num_groups  = group_of[-1] + 1
        positions   = list(range(num_groups))
        if self.order == 'random':
            random.Random(self.fx_id).shuffle(positions)
        if self.direction == 'reverse':
            positions = positions[::-1]

        denom        = num_groups if num_groups > 1 else 1
        group_offset = [p / denom for p in positions]
        return [group_offset[g] for g in group_of]

    def get_values(self, now):
        if not self.is_active or not self.targets:
            return {}

        # Amplitude envelope: outfade → infade → full
        if self._out_start is not None:
            elapsed_out = now - self._out_start
            env = max(0.0, 1.0 - elapsed_out / self.outfade) if self.outfade > 0 else 0.0
            if env <= 0.0:
                self.is_active = False   # engine will sweep this layer out
                return {}
        elif self.infade > 0:
            env = min(1.0, (now - self.start) / self.infade)
        else:
            env = 1.0

        fn      = self._get_fn()
        rate_hz = self.rate_bpm / 60.0

        # 'bounce' folds elapsed cycles into a triangle wave (0→1→0) instead
        # of wrapping (0→1→0→1), so the whole chase sweeps across targets
        # and back rather than always restarting from the same end.
        if self.direction == 'bounce':
            cycles = (now - self.start) * rate_hz
            frac   = cycles % 2.0
            cycle_phase = frac if frac <= 1.0 else 2.0 - frac
        else:
            cycle_phase = (now - self.start) * rate_hz
        base_phase = cycle_phase + self.phase_offset

        # size  0-100 → 0-255 DMX;  spread 0-100 → 0.0-1.0 phase fraction
        sz     = (self.size / 100.0) * 255.0 * env
        sp     = self.spread / 100.0
        result = {}
        for i, sub in enumerate(self.targets):
            phase = (base_phase + self._offsets[i] * sp) % 1.0
            result[str(sub.fixture_id)] = fn(phase) * sz
        return result

    def __repr__(self):
        refs = []
        if self.form_id    is not None: refs.append(f"form:{self.form_id}")
        if self._rate_id   is not None: refs.append(f"rate:{self._rate_id}")
        if self._size_id   is not None: refs.append(f"size:{self._size_id}")
        if self._spread_id is not None: refs.append(f"spread:{self._spread_id}")
        if self._dim_id    is not None: refs.append(f"dimref:{self._dim_id}")
        ref_s = f" [{','.join(refs)}]" if refs else ""
        dist = []
        if self.block_size != 1:    dist.append(f"block:{self.block_size}")
        if self.order != 'linear':  dist.append(f"order:{self.order}")
        if self.direction != 'forward': dist.append(f"dir:{self.direction}")
        dist_s = f" ({','.join(dist)})" if dist else ""
        return (f"[FX {self.fx_id}] {self.waveform}{ref_s} on {self.channel} | "
                f"{self.rate_bpm:.1f}BPM size={self.size:.0f} spread={self.spread:.2f}{dist_s} "
                f"[{len(self.targets)} targets]")


# ------------------------------------------------------------
# FXEngine — manages all active FX layers
# ------------------------------------------------------------

class FXEngine:
    """
    Runs all active FX layers at 44Hz.
    Writes combined output to output_state.fx_layer.
    Multiple FX on the same channel are additive (clamped later).

    form_pool — optional FormPool; when set, waveform functions are
                resolved from the pool at add() time so custom forms
                are used automatically.
    """
    def __init__(self, output_state, form_pool=None, rate_pool=None,
                 size_pool=None, spread_pool=None, dim_pool=None):
        self.output_state = output_state
        self.form_pool    = form_pool
        self.rate_pool    = rate_pool
        self.size_pool    = size_pool
        self.spread_pool  = spread_pool
        self.dim_pool     = dim_pool
        self._layers      = {}
        self._lock        = threading.Lock()
        self._running     = True
        self._thread      = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def add(self, fx_id, waveform, channel, rate_bpm, size,
            targets, spread=1.0, form_id=None,
            rate_id=None, size_id=None, spread_id=None, dim_id=None,
            phase_offset=0.0, infade=0.0, outfade=0.0,
            block_size=1, order='linear', direction='forward'):
        """
        Add an FX layer.
        waveform    — name string ('sine', 'ramp' …) or ignored when form_id given.
        form_id     — explicit FormPool slot; overrides waveform name lookup.
        dim_id      — DimmerPool slot; live ceiling on amplitude (0–1 scales size).
        infade      — seconds to ramp amplitude 0→1 from layer start.
        outfade     — seconds to ramp amplitude 1→0 when remove() is called.
        block_size  — adjacent targets grouped per step (default 1).
        order       — 'linear' or 'random' target sequencing (default 'linear').
        direction   — 'forward' | 'reverse' | 'bounce' (default 'forward').
        """
        layer = FXLayer(
            fx_id, waveform, channel, rate_bpm, size, targets, spread,
            form_pool    = self.form_pool,
            rate_pool    = self.rate_pool,
            size_pool    = self.size_pool,
            spread_pool  = self.spread_pool,
            dim_pool     = self.dim_pool,
            form_id      = form_id,
            rate_id      = rate_id,
            size_id      = size_id,
            spread_id    = spread_id,
            dim_id       = dim_id,
            phase_offset = phase_offset,
            infade       = infade,
            outfade      = outfade,
            block_size   = block_size,
            order        = order,
            direction    = direction,
        )
        with self._lock:
            self._layers[fx_id] = layer
        print(f"Added: {layer}")
        return layer

    def remove(self, fx_id, now=None, default_outfade=0.0):
        """Remove a layer. Triggers outfade if the layer has outfade > 0;
        otherwise removes immediately. default_outfade is used when the
        layer was created with outfade=0 (callers pass the cue fade time)."""
        with self._lock:
            layer = self._layers.get(fx_id)
            if layer is None:
                return
            # Apply default_outfade when the layer has no explicit outfade set
            if layer.outfade == 0.0 and default_outfade > 0:
                layer.outfade = float(default_outfade)
            if layer.outfade > 0 and layer._out_start is None:
                layer.begin_outfade(now)
                print(f"FX {fx_id} outfading ({layer.outfade}s).")
            else:
                self._layers.pop(fx_id, None)
                print(f"FX {fx_id} removed.")

    def clear(self):
        with self._lock:
            self._layers.clear()
            self.output_state.fx_layer = {}
        print("All FX cleared.")

    def print_fx(self):
        print("\n===== FX LAYERS =====")
        if not self._layers:
            print("  (none active)")
        for layer in self._layers.values():
            print(f"  {layer}")
        print("=====================\n")

    def _run(self):
        while self._running:
            now    = time.monotonic()
            merged = {}
            dead   = []
            with self._lock:
                for fx_id, layer in self._layers.items():
                    vals = layer.get_values(now)
                    if not layer.is_active:
                        dead.append(fx_id)
                        continue
                    for fid, value in vals.items():
                        if fid not in merged:
                            merged[fid] = {}
                        merged[fid][layer.channel] = (
                            merged[fid].get(layer.channel, 0) + value
                        )
                for fx_id in dead:
                    self._layers.pop(fx_id, None)
                    print(f"FX {fx_id} outfade complete — removed.")
            self.output_state.fx_layer = merged
            time.sleep(1 / 44)

    def stop(self):
        self._running = False


# ------------------------------------------------------------
# _bucket_fx_defs — shared by _prog_fx_start and Executor._start_cue_fx
# ------------------------------------------------------------

def _bucket_fx_defs(fx_defs_by_fid, patch):
    """
    Bucket per-fixture FX defs into (ld, targets) groups so identical defs
    across multiple fixtures share ONE FXLayer — this lets spread/chase
    cross fixture boundaries instead of being confined to a single tube.

    fx_defs_by_fid: {master_fixture_id (int or numeric str): [fx_def, ...]}

    Each def's 'target_scope' controls what 'targets' becomes:
      'fixture' — one target per whole master fixture; a chase step moves
                  a whole tube at once. Default for the 'dim' channel.
      'pixel'   — flattened sub-fixture pixels across every matching master,
                  so a chase can run pixel-by-pixel straight through
                  multiple tubes. Default for colour channels.

    Returns a list of (ld, targets) tuples ready for fx_engine.add().
    """
    buckets = {}   # key → (ld, scope, [masters])
    for fid, defs in fx_defs_by_fid.items():
        try:
            master = patch.get(int(fid))
        except (ValueError, TypeError):
            continue
        if not master:
            continue
        for ld in defs:
            scope = ld.get('target_scope') or (
                'fixture' if ld.get('channel') == 'dim' else 'pixel')
            key = (ld.get('waveform', 'sine'), ld.get('channel'),
                   round(ld.get('bpm',    60.0), 3),
                   round(ld.get('size',  100.0), 2),
                   round(ld.get('spread',  0.0), 4),
                   ld.get('phase_offset', 0.0),
                   ld.get('form_id'), ld.get('rate_id'),
                   ld.get('size_id'), ld.get('spread_id'), ld.get('dim_id'),
                   ld.get('group_id'), ld.get('color_id'),
                   scope,
                   ld.get('block_size', 1),
                   ld.get('order',      'linear'),
                   ld.get('direction',  'forward'),
                   ld.get('infade', 0.0), ld.get('outfade', 0.0))
            if key not in buckets:
                buckets[key] = (ld, scope, [])
            buckets[key][2].append(master)

    grouped = []
    for ld, scope, masters in buckets.values():
        if scope == 'pixel':
            targets = [sub for m in masters for sub in m.all_subs()]
        else:
            targets = masters
        grouped.append((ld, targets))
    return grouped


def _expand_color_fx(fx_defs_by_fid, color_pool):
    """
    Expand any fx_def with channel='rgb' and color_id into three separate
    defs (red, green, blue) with sizes scaled by the preset's RGB values.
    Defs on other channels are passed through unchanged.
    color_pool may be None — in that case 'rgb' defs are dropped with a warning.
    """
    expanded = {}
    for fid, defs in fx_defs_by_fid.items():
        out = []
        for ld in defs:
            cid = ld.get('color_id')
            if ld.get('channel') == 'rgb' and cid is not None:
                cp = color_pool.get(cid) if color_pool else None
                if cp:
                    base_size = ld.get('size', 100.0)
                    for ch, val in (('red', cp.red), ('green', cp.green), ('blue', cp.blue)):
                        if val > 0:
                            sub = dict(ld)
                            sub['channel'] = ch
                            sub['size']    = (val / 255.0) * base_size
                            out.append(sub)
                else:
                    print(f"FX color_id {cid} not found — skipping rgb layer for fixture {fid}")
            else:
                out.append(ld)
        if out:
            expanded[fid] = out
    return expanded


def _expand_group_fx(fx_defs_by_fid, patch, group_pool):
    """
    For any fx_def with a group_id set, add that def to every fixture
    in the referenced group (in addition to whatever fixture already holds it).
    The group_id is kept in the def so _bucket_fx_defs can form a shared layer.
    Defs without group_id are passed through unchanged.
    """
    if not group_pool:
        return fx_defs_by_fid
    out = dict(fx_defs_by_fid)
    for fid, defs in fx_defs_by_fid.items():
        for ld in defs:
            gid = ld.get('group_id')
            if gid is None:
                continue
            grp = group_pool.get(gid)
            if not grp:
                continue
            for master in grp.recall(patch):
                mfid = str(master.fixture_id)
                if mfid not in out:
                    out[mfid] = []
                if ld not in out[mfid]:
                    out[mfid].append(ld)
    return out


# ------------------------------------------------------------
# Updated OutputState — now includes fx_layer
# Replaces Block 7 version (Python uses last definition)
# ------------------------------------------------------------

# ============================================================
# STUDIO CONSOLE - Block 9: Audio Engine
# Real-time audio analysis: level + 3-band EQ (low/mid/high)
# Attack/release envelope following
# AudioMapper connects audio values to the lighting output
# ============================================================

import sounddevice as sd
import numpy as np


# ------------------------------------------------------------
# AudioEngine — capture + analyse
# ------------------------------------------------------------

class AudioEngine:
    """
    Captures audio input in real-time and outputs four
    normalized values (0.0 - 1.0):

      level — overall RMS loudness
      low   — bass energy     (20-250 Hz)
      mid   — mid energy      (250-4000 Hz)
      high  — treble energy   (4000-20000 Hz)

    Attack/release envelope smooths transitions:
      attack  — how fast values RISE  (higher = faster snap)
      release — how fast values FALL  (lower = slower decay)
    """

    SAMPLE_RATE = 44100
    CHUNK_SIZE  = 1024

    def __init__(self):
        self.level   = 0.0
        self.low     = 0.0
        self.mid     = 0.0
        self.high    = 0.0

        self.attack  = 0.8    # fast snap to transients
        self.release = 0.15   # slow decay so lights linger
        self.gain    = 3.0    # turn up if signal is quiet

        self._stream  = None
        self._running = False

    @staticmethod
    def list_devices():
        print("\n===== AUDIO INPUT DEVICES =====")
        for i, dev in enumerate(sd.query_devices()):
            if dev['max_input_channels'] > 0:
                print(f"  [{i}] {dev['name']}")
        print("================================\n")

    def start(self, device=None):
        """
        Start capturing. device=None uses the system default.
        Pass a device index from list_devices() to pick a specific input.
        """
        self._running = True
        self._stream  = sd.InputStream(
            samplerate = self.SAMPLE_RATE,
            channels   = 1,
            dtype      = 'float32',
            blocksize  = self.CHUNK_SIZE,
            callback   = self._callback,
            device     = device,
        )
        self._stream.start()
        idx  = device if device is not None else sd.default.device[0]
        name = sd.query_devices(idx)['name']
        print(f"Audio engine started — input: {name}")

    def stop(self):
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
        print("Audio engine stopped.")

    def _callback(self, indata, frames, time_info, status):
        samples = indata[:, 0]

        # Overall RMS level
        rms = min(1.0, float(np.sqrt(np.mean(samples ** 2))) * self.gain)

        # FFT frequency analysis
        window = np.hanning(len(samples))
        fft    = np.abs(np.fft.rfft(samples * window))
        freqs  = np.fft.rfftfreq(len(samples), 1.0 / self.SAMPLE_RATE)

        def band(f_low, f_high):
            mask = (freqs >= f_low) & (freqs < f_high)
            return float(np.mean(fft[mask])) if mask.any() else 0.0

        low_raw  = band(20,   250)
        mid_raw  = band(250,  4000)
        high_raw = band(4000, 20000)

        # Normalize bands relative to each other, scaled by overall level
        peak   = max(low_raw, mid_raw, high_raw, 0.0001)
        low_n  = min(1.0, (low_raw  / peak) * rms * 1.5)
        mid_n  = min(1.0, (mid_raw  / peak) * rms * 1.5)
        high_n = min(1.0, (high_raw / peak) * rms * 1.5)

        self.level = self._env(self.level, rms)
        self.low   = self._env(self.low,   low_n)
        self.mid   = self._env(self.mid,   mid_n)
        self.high  = self._env(self.high,  high_n)

    def _env(self, current, target):
        coef = self.attack if target > current else self.release
        return current + (target - current) * coef

    def print_levels(self):
        def bar(v, w=24):
            return '█' * int(v * w) + '░' * (w - int(v * w))
        print(f"\r  Lvl [{bar(self.level)}] Lo [{bar(self.low)}] "
              f"Mid [{bar(self.mid)}] Hi [{bar(self.high)}]", end='', flush=True)


# ------------------------------------------------------------
# AudioMapper — connects audio values to the lighting stack
# ------------------------------------------------------------

class AudioMapper:
    """
    Reads AudioEngine values every frame and writes to
    output_state.audio_layer.

    Default mapping:
      level → master dimmer on all fixtures
      low   → red   on all sub-fixtures  (bass = red)
      mid   → green on all sub-fixtures  (mids = green)
      high  → blue  on all sub-fixtures  (treble = blue)

    Audio layer sits between FX+cue and programmer —
    programmer still overrides everything when active.
    """

    def __init__(self, audio_engine, output_state, patch):
        self.audio        = audio_engine
        self.output_state = output_state
        self.patch        = patch
        self.enabled      = False
        self._running     = True
        self._thread      = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def enable(self):
        self.enabled = True
        print("Audio mapping enabled — bass=red, mid=green, high=blue, level=dim")

    def disable(self):
        self.enabled = False
        self.output_state.audio_layer = {}
        print("Audio mapping disabled.")

    def _run(self):
        while self._running:
            if self.enabled:
                out = {}
                r   = int(self.audio.low   * 255)
                g   = int(self.audio.mid   * 255)
                b   = int(self.audio.high  * 255)
                dim = self.audio.level

                for master in self.patch.all_fixtures():
                    out[str(master.fixture_id)] = {'dim': dim}
                    for sub in master.all_subs():
                        out[str(sub.fixture_id)] = {
                            'red': r, 'green': g, 'blue': b
                        }
                self.output_state.audio_layer = out
            time.sleep(1 / 44)

    def stop(self):
        self._running = False


# ------------------------------------------------------------
# Final OutputState — merges all executor layers + programmer
# + audio + FX.
# Priority (base layers, highest → lowest):
#   programmer  > audio  > executor layers (LTP)
# FX is additive on top of whichever base layer wins — FX always visible
# ------------------------------------------------------------

class OutputState:
    """
    The final resolved DMX state for every sub-fixture.

    Layers merged in priority order (lowest → highest):
      cue (via executor_pool LTP merge) → audio_layer → programmer_layer → fx_layer
    Master fader and per-fixture dim are applied last.

    get_dmx_for_universe() builds a 512-slot tuple ready to hand
    straight to the sACN sender.
    """
    def __init__(self, patch):
        self.patch            = patch
        self.programmer_layer = {}
        self.fx_layer         = {}
        self.audio_layer      = {}
        self.executor_pool    = None   # set via link_executor_pool()
        self.master_level     = 1.0   # grand master fader (0.0–1.0)
        self.blind            = False  # when True, programmer layer is suppressed from DMX output
        self._lock            = threading.Lock()

    def link_programmer(self, programmer):
        self.programmer_layer = programmer.data

    def link_executor_pool(self, pool):
        self.executor_pool = pool

    def _merged_cue_layer(self):
        """LTP merge of all active executor layers. Called inside _lock."""
        merged = {}
        if not self.executor_pool:
            return merged
        for (layer, level) in self.executor_pool.active_layers():
            for fid, vals in layer.items():
                if fid not in merged:
                    merged[fid] = {}
                for ch, val in vals.items():
                    merged[fid][ch] = val * level
        return merged

    def get_dmx_for_universe(self, universe):
        dmx = [0] * 512
        with self._lock:
            cue_merged = self._merged_cue_layer()

            _blind_prog = self.blind
            for master in self.patch.all_fixtures():
                master_fid   = str(master.fixture_id)
                prog_master  = {} if _blind_prog else self.programmer_layer.get(master_fid, {})
                cue_master   = cue_merged.get(master_fid, {})
                audio_master = self.audio_layer.get(master_fid, {})

                # Priority model:
                #   Colour FX (red/green/blue) → replaces base colour on that channel
                #     (highest priority: FX > programmer > audio > cue)
                #   Dim FX (dim channel) → multiplied against the base dim hierarchy
                #     (programmer dim × FX_dim, so programmer can still kill output)
                #   RGB FX implicit dim → when colour FX is running but no explicit dim
                #     source exists (FX-only cue), default to 1.0 so fixtures are visible.
                #     Explicit cue/programmer dim is respected and NOT overridden.
                # fx_kill in programmer or cue explicitly suppresses all FX for this fixture
                #
                # Dim FX can target this whole fixture (target_scope='fixture' —
                # fx_layer[master_fid]['dim']) or drive each pixel independently
                # (target_scope='pixel' — fx_layer[sub_fid]['dim']). Per-pixel value
                # wins when present; otherwise it falls back to the fixture-level one.
                _fx_kill      = (prog_master.get('fx_kill', 0) >= 0.5 or
                                 cue_master.get('fx_kill',  0) >= 0.5)

                fx_master        = {} if _fx_kill else self.fx_layer.get(master_fid, {})
                _fixture_dim_fx  = fx_master.get('dim')
                _first_sub       = next(iter(master.sub_fixtures.values()), None)
                _rgb_fx_on       = (not _fx_kill and bool(
                                    _first_sub and self.fx_layer.get(str(_first_sub.fixture_id))))

                _base_dim = prog_master.get('dim', audio_master.get('dim',
                             cue_master.get('dim', master.virtual_dimmer)))
                _explicit_cue_dim = cue_master.get('dim')
                _rgb_fallback_dim = prog_master.get('dim', audio_master.get('dim',
                             _explicit_cue_dim if _explicit_cue_dim is not None else 1.0))

                for sub in master.all_subs():
                    fid        = str(sub.fixture_id)
                    prog_vals  = {} if _blind_prog else self.programmer_layer.get(fid, {})
                    audio_vals = self.audio_layer.get(fid, {})
                    cue_vals   = cue_merged.get(fid, {})
                    fx_vals    = {} if _fx_kill else self.fx_layer.get(fid, {})

                    fx_dim_raw = fx_vals.get('dim', _fixture_dim_fx)
                    if fx_dim_raw is not None:
                        # Dim FX: multiplicative on top of static dim hierarchy
                        sub_dim = max(0.0, min(1.0, _base_dim * (fx_dim_raw / 255.0)))
                    elif _rgb_fx_on:
                        # Colour FX running: respect explicit programmer/cue dim;
                        # fall back to 1.0 only when no explicit source exists.
                        sub_dim = _rgb_fallback_dim
                    else:
                        sub_dim = _base_dim

                    # FX has highest output priority for any channel it drives.
                    # Base priority for non-FX channels: programmer > audio > cue
                    base_r = prog_vals.get('red',   audio_vals.get('red',   cue_vals.get('red',   0)))
                    base_g = prog_vals.get('green', audio_vals.get('green', cue_vals.get('green', 0)))
                    base_b = prog_vals.get('blue',  audio_vals.get('blue',  cue_vals.get('blue',  0)))
                    r = int(fx_vals['red'])   if 'red'   in fx_vals else base_r
                    g = int(fx_vals['green']) if 'green' in fx_vals else base_g
                    b = int(fx_vals['blue'])  if 'blue'  in fx_vals else base_b

                    gm      = self.master_level
                    final_r = max(0, min(255, int(r * sub_dim * gm)))
                    final_g = max(0, min(255, int(g * sub_dim * gm)))
                    final_b = max(0, min(255, int(b * sub_dim * gm)))

                    for output in sub.outputs:
                        if output['universe'] == universe:
                            addr = output['address'] - 1
                            if addr + 2 <= 511:
                                dmx[addr]     = final_r
                                dmx[addr + 1] = final_g
                                dmx[addr + 2] = final_b
        return tuple(dmx)


# ============================================================
# STUDIO CONSOLE - Block 10: MIDI Engine
# CC mappings  → parameters (soft-takeover)
# Note mappings → actions (GO, BACK, FX on/off, macros)
# ============================================================

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
        mapping = NoteMapping(name or f"Note{note}", on_callback, off_callback)
        self.note_maps[(channel, note)] = mapping
        print(f"Mapped: CH{channel} Note{note} → {mapping.name}")
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
            print(f"  CH{ch} CC{cc}   → {m.name} [{status}]")
        for (ch, note), m in self.note_maps.items():
            print(f"  CH{ch} Note{note} → {m.name}")
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


# ============================================================
# STUDIO CONSOLE - Block 11: OSC Engine
#
# Two roles:
#   INPUT  — Studio Console receives MA3-style OSC so any tool
#             that was talking to grandMA3 (Chataigne, TouchOSC,
#             Bome, etc.) can talk to Studio Console instead.
#             Listens on UDP port 8000 by default.
#
#   OUTPUT — Studio Console sends OSC to other apps when cues
#             fire. Primary target: Lightform Creator, so video
#             content syncs to lighting cues automatically.
# ============================================================

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
      /gma3/cmd              string   — command line (e.g. "Go+ Cue 1")
      /gma3/fader/P/E        float    — fader 0.0-1.0 (page P, exec E)
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

    def broadcast_state(self, output_state, executor_pool, patch):
        """
        Send a concise state snapshot over OSC to all feedback targets.
        Called from the GUI tick loop at ~1 Hz.

        Addresses:
          /studio/master            float  0.0-1.0
          /studio/exec/N/level      float  0.0-1.0
          /studio/exec/N/cue        string current cue name or ""
          /studio/exec/N/active     int    1/0
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
            if executor_pool:
                for eid, ex in sorted(executor_pool.executors.items()):
                    level  = float(getattr(ex, 'level', 0.0))
                    active = 1 if getattr(ex, 'is_active', False) else 0
                    fb.send_message(f"/studio/exec/{eid}/level",  level)
                    fb.send_message(f"/studio/exec/{eid}/active", active)
                    cs  = getattr(ex, 'cuestack', None)
                    cur = cs.current if cs else None
                    cue = cs.cues.get(cur) if (cs and cur is not None) else None
                    fb.send_message(f"/studio/exec/{eid}/cue",
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


# ============================================================
# STUDIO CONSOLE - Block 12: AI Engine
#
# Natural language → console actions via Claude API.
# The user types anything ("make it dramatic", "slow blue fade",
# "something eerie") and Claude translates it into a sequence
# of console commands that execute immediately.
#
# Requires: ANTHROPIC_API_KEY environment variable.
# Set it once: export ANTHROPIC_API_KEY="sk-ant-..."
# Or add it to ~/.zshrc so it's always available.
# ============================================================

import anthropic


class AIEngine:
    """
    Translates natural language into lighting console actions.

    How it works:
    1. ai.ask("make it dramatic") is called
    2. Current console state is described in a system prompt
    3. Claude returns a JSON list of actions
    4. execute() runs each action on the actual console

    The AI knows about:
    - Your fixtures and their IDs
    - All cuestacks and their cues
    - Available FX waveforms and parameters
    - Programmer commands (same syntax as command line)
    """

    ACTION_SCHEMA = """
Return a JSON array of action objects. Each action is one of:

{"action": "goto_cue",    "stack": 1, "num": 2}
{"action": "cue_go",      "stack": 1}
{"action": "cue_back",    "stack": 1}
{"action": "cue_fire",    "stack": 1, "num": 3}
{"action": "prog",        "cmd": "1 THRU 6 AT R 255 G 0 B 0"}
{"action": "dim",         "value": 0.85}
{"action": "fx_start",    "waveform": "sine", "channel": "red",
                          "bpm": 60, "size": 100, "spread": 0.0}
{"action": "fx_stop",     "channel": "red"}
{"action": "fx_clear"}
{"action": "group_select","group": 2}
{"action": "fade_time",   "seconds": 3.0}
{"action": "exec_level",  "exec": 1, "level": 0.75}

Rules:
- "group_select" selects all fixtures in group N as the programmer selection.
- "fx_stop" stops FX on one channel; omit "channel" to stop all.
- "exec_level" sets executor master fader (level 0.0–1.0).
- "cue_fire" is an alias for goto_cue (fires the named cue immediately).
- Only return the JSON array. No explanation, no markdown.
"""

    _CMD_HISTORY_MAX = 12

    def __init__(self, patch, prog, output_state, fx_engine, fade_engine,
                 cuestacks=None, executor_pool=None, cmd_fn=None, log_fn=None,
                 model="claude-haiku-4-5-20251001"):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("  AI Engine: ANTHROPIC_API_KEY not set — AI disabled.")
            print("  Run:  export ANTHROPIC_API_KEY='sk-ant-...'")
            self._enabled = False
            return
        self._client         = anthropic.Anthropic(api_key=api_key)
        self._model          = model
        self._patch          = patch
        self._prog           = prog
        self._output         = output_state
        self._fx             = fx_engine
        self._fade           = fade_engine
        self._stacks         = cuestacks or {}
        self._executor_pool  = executor_pool
        self._cmd            = cmd_fn    # run_command — full console command parser
        self._log            = log_fn    # GUI log callback
        self._enabled        = True
        self._last_fade      = 2.0
        self._cmd_history    = []        # last N commands for context
        self._token_cb       = None      # optional callback(in_tok, out_tok) for GUI
        print(f"  AI Engine: ready ({model})")

    def push_cmd_history(self, cmd_str):
        """Call after each user command to feed recent context into AI prompts."""
        self._cmd_history.append(cmd_str)
        if len(self._cmd_history) > self._CMD_HISTORY_MAX:
            self._cmd_history = self._cmd_history[-self._CMD_HISTORY_MAX:]

    def _state(self):
        fixtures = [
            {"id": m.fixture_id, "name": m.name,
             "pixels": len(list(m.all_subs()))}
            for m in self._patch.all_fixtures()
        ]
        stacks = {}
        for sid, stack in self._stacks.items():
            cues = [
                {"num": n, "name": stack.cues[n].name,
                 "fade": stack.cues[n].fade_time}
                for n in stack._sorted_cue_numbers()
            ]
            stacks[str(sid)] = {
                "name": stack.name,
                "cues": cues,
                "current": getattr(stack, 'current', None),
            }
        fx_active = []
        for layer in self._fx._layers.values():
            fx_active.append({"waveform": layer.waveform,
                               "channel": layer.channel,
                               "bpm": layer.rate_bpm,
                               "size": layer.size,
                               "spread": layer.spread})
        # Programmer contents (what's currently edited, not yet stored in a cue)
        prog_data = {}
        try:
            for fid, vals in self._prog.data.items():
                prog_data[fid] = {k: round(v, 3) for k, v in vals.items()}
        except Exception:
            pass
        # Active executors
        active_execs = []
        if self._executor_pool:
            for eid, ex in sorted(self._executor_pool.executors.items()):
                if ex.is_active and ex.cuestack:
                    cur  = ex.cuestack.current
                    cue  = ex.cuestack.cues.get(cur) if cur is not None else None
                    active_execs.append({
                        "exec": eid,
                        "cuestack": ex.cuestack.name,
                        "current_cue": cur,
                        "cue_name": cue.name if cue else None,
                        "level": round(ex.level, 2),
                        "priority": Executor.PRIORITY_LABELS.get(ex.priority, 'NRM'),
                    })
        return {
            "fixtures": fixtures,
            "cuestacks": stacks,
            "fx": fx_active,
            "programmer": prog_data,
            "active_executors": active_execs,
            "recent_commands": list(self._cmd_history),
        }

    def ask(self, prompt, execute=True):
        """
        Send a natural language prompt. Returns the list of actions
        and optionally executes them immediately.
        """
        if not self._enabled:
            print("  AI disabled — set ANTHROPIC_API_KEY first.")
            return []

        state_json = json.dumps(self._state(), indent=2)
        system = (
            "You are the AI control layer for Studio Console, "
            "a custom lighting console controlling 6 SGM RGB pixel tubes "
            "(54 pixels each) via sACN. "
            "Translate the user's intent into console actions. "
            "Be creative with lighting — colour, movement, mood. "
            "Available waveforms: sine, ramp, pulse, square. "
            "Available channels: red, green, blue. "
            "Programmer commands use MA3-style syntax: "
            "'FIXTURE_ID AT VALUE', 'R 255 G 0 B 0', 'AT FULL', 'AT OUT'.\n\n"
            + self.ACTION_SCHEMA
        )
        user_msg = f"Console state:\n{state_json}\n\nRequest: {prompt}"

        try:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=512,
                system=system,
                messages=[{"role": "user", "content": user_msg}]
            )
            raw = resp.content[0].text.strip()
            # Strip markdown code fences if model wraps in them
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            actions = json.loads(raw)
            # Report token usage
            try:
                in_tok  = resp.usage.input_tokens
                out_tok = resp.usage.output_tokens
                if self._token_cb:
                    self._token_cb(in_tok, out_tok)
            except Exception:
                in_tok = out_tok = 0
            if self._log:
                self._log(f"AI → {len(actions)} action(s)  [{in_tok}↑ {out_tok}↓ tok]")
                for a in actions:
                    act = a.get("action", "?")
                    detail = ", ".join(f"{k}={v}" for k, v in a.items() if k != "action")
                    self._log(f"  {act}  {detail}")
            else:
                print(f"\n  AI → {len(actions)} action(s):")
                for a in actions:
                    print(f"    {a}")
            if execute:
                self.execute(actions)
            return actions
        except Exception as e:
            msg = f"AI error: {e}"
            if self._log:
                self._log(msg)
            else:
                print(f"\n  {msg}")
            return []

    def execute(self, actions):
        """Run a list of action dicts on the console."""
        for a in actions:
            try:
                act = a.get("action", "")
                if act == "prog":
                    if self._cmd:
                        self._cmd(a["cmd"])
                    else:
                        self._prog.execute(a["cmd"])
                elif act == "goto_cue":
                    ex = self._executor_pool.get(a.get("stack", 1)) if self._executor_pool else None
                    if ex:
                        self._executor_pool.bump_priority(ex.exec_id)
                        ex.goto(a["num"], self._patch, self._fade)
                elif act == "cue_go":
                    ex = self._executor_pool.get(a.get("stack", 1)) if self._executor_pool else None
                    if ex:
                        self._executor_pool.bump_priority(ex.exec_id)
                        ex.go(self._patch, self._fade)
                elif act == "cue_back":
                    ex = self._executor_pool.get(a.get("stack", 1)) if self._executor_pool else None
                    if ex:
                        self._executor_pool.bump_priority(ex.exec_id)
                        ex.back(self._patch, self._fade)
                elif act == "dim":
                    val = float(a["value"])
                    for master in self._patch.all_fixtures():
                        self._output.programmer_layer.setdefault(
                            str(master.fixture_id), {})['dim'] = val
                elif act == "fx_start":
                    # Route through run_command so it goes into the programmer
                    # (channel-additive, doesn't wipe other running FX)
                    wf  = a.get("waveform", "sine").upper()
                    ch  = a.get("channel",  "red").upper()
                    bpm = float(a.get("bpm",    60))
                    sz  = float(a.get("size",  100))
                    sp  = float(a.get("spread", 0.0))
                    cmd = f"FX {wf} {ch} BPM {bpm:.1f} SIZE {sz:.0f} SPREAD {sp:.1f}"
                    if self._cmd:
                        self._cmd(cmd)
                    else:
                        all_s = [s for m in self._patch.all_fixtures()
                                 for s in m.all_subs()]
                        self._fx.add(
                            1, a.get("waveform", "sine"), a.get("channel", "red"),
                            rate_bpm=bpm, size=sz, targets=all_s, spread=sp
                        )
                elif act in ("cue_fire", "goto_cue") and "num" in a:
                    ex = self._executor_pool.get(a.get("stack", 1)) if self._executor_pool else None
                    if ex:
                        self._executor_pool.bump_priority(ex.exec_id)
                        ex.goto(float(a["num"]), self._patch, self._fade)
                elif act == "group_select":
                    if self._cmd:
                        self._cmd(f"GROUP {a['group']}")
                elif act == "fx_stop":
                    ch = a.get("channel")
                    if ch and self._cmd:
                        self._cmd(f"FX CLEAR {ch.upper()}")
                    else:
                        self._fx.clear()
                elif act == "exec_level":
                    if self._executor_pool and self._cmd:
                        self._cmd(f"EXEC {a.get('exec', 1)} LEVEL {float(a.get('level', 1.0)) * 100:.0f}")
                elif act == "fx_clear":
                    self._fx.clear()
                elif act == "fade_time":
                    self._last_fade = float(a["seconds"])
            except Exception as e:
                print(f"  AI execute error ({a}): {e}")


# ============================================================
# STUDIO CONSOLE - Block 13: GUI Engine
#
# DearPyGui retro console. Runs on the main thread (macOS
# requires GUI on main thread). MIDI/OSC/sACN stay in their
# daemon threads. A background refresh thread calls
# dpg.set_value() at ~20 Hz to push live data into widgets.
#
# Panels:
#   - Header: title bar + current cue status
#   - Cuestack: cue list, GO / BACK, live indicator
#   - FX: Rate / Size / Spread sliders, Kill button
#   - Output monitor: per-tube RGB+Dim bars
#   - MIDI mapping: table with add / remove / learn
#   - AI prompt: text input → ai.ask()
# ============================================================

try:
    import dearpygui.dearpygui as dpg
    _DPG_OK = True
except ImportError:
    _DPG_OK = False

# Colour palette — near-black / violet accent
_C_BG        = (3,   2,   8, 255)   # near pure black with faint violet
_C_PANEL     = (13,  10,  28, 255)  # dark indigo panel (was 8,6,18)
_C_BORDER    = (60,  42, 115, 255)  # violet divider — more visible (was 38,26,78)
_C_TEXT      = (232, 226, 255, 255) # clean white with violet cast
_C_DIM       = (95,  74, 148, 255)  # dimmed — readable but recessed (was 72,56,115)
_C_ACCENT    = (162, 115, 255, 255) # violet #a273ff — slightly brighter (was 139,92,246)
_C_HOT       = (212, 152, 255, 255) # bright violet-pink for live status
_C_BTN       = (28,  20,  64, 255)  # resting button — more visible (was 15,10,36)
_C_BTN_H     = (80,  56, 155, 255)  # hover — punchy (was 52,34,106)
_C_BTN_A     = (122,  84, 215, 255) # active — bright violet (was 98,64,182)
_C_CUE_ACT   = (46,  32,  95, 255)  # selected cue row (was 32,22,70)
_C_SLIDER_G  = _C_ACCENT

# Pool panel header colours — violet family, varied lightness/hue for readability
_C_P_GROUPS  = (160, 120, 255, 255)  # mid violet
_C_P_COLORS  = (210,  98, 220, 255)  # pink-violet
_C_P_DIMS    = (180, 160, 255, 255)  # pale lavender
_C_P_CS      = (110, 190, 255, 255)  # cool blue-violet
_C_P_CUES    = ( 92, 162, 240, 255)  # muted sky
_C_P_FX      = (200, 130, 255, 255)  # bright violet
_C_P_FORMS   = (140, 200, 255, 255)  # icy periwinkle
_C_P_POSITION = (130, 155, 255, 255)  # blue-violet
_C_P_GOBO    = (175, 130, 255, 255)  # medium violet
_C_P_ZOOM    = (155, 175, 255, 255)  # blue-lavender
_C_P_FOCUS   = (210, 140, 255, 255)  # light violet-pink
_C_P_BEAM    = (145, 120, 230, 255)  # dim violet
_C_P_CONTROL = (130, 220, 200, 255)  # teal-mint


def _apply_theme():
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg,       _C_BG)
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg,        _C_PANEL)
            dpg.add_theme_color(dpg.mvThemeCol_Border,         _C_BORDER)
            dpg.add_theme_color(dpg.mvThemeCol_Text,           _C_TEXT)
            dpg.add_theme_color(dpg.mvThemeCol_TextDisabled,   _C_DIM)
            dpg.add_theme_color(dpg.mvThemeCol_Button,         _C_BTN)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered,  _C_BTN_H)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,   _C_BTN_A)
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg,        (20, 14,  46, 255))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (40, 28,  90, 255))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive,  (68, 48, 145, 255))
            dpg.add_theme_color(dpg.mvThemeCol_TableRowBg,     ( 0,  0,   0,   0))
            dpg.add_theme_color(dpg.mvThemeCol_TableRowBgAlt,  (26, 18,  56,  70))
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrab,     _C_SLIDER_G)
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive, _C_ACCENT)
            dpg.add_theme_color(dpg.mvThemeCol_Header,         _C_CUE_ACT)
            dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered,  _C_BTN_H)
            dpg.add_theme_color(dpg.mvThemeCol_HeaderActive,   _C_BTN_A)
            dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive,  (35, 24,  80, 255))
            dpg.add_theme_color(dpg.mvThemeCol_TitleBg,        _C_PANEL)
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg,    _C_BG)
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab,  _C_BORDER)
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabHovered, _C_BTN_H)
            dpg.add_theme_color(dpg.mvThemeCol_PopupBg,        (12,  8,  28, 255))
            dpg.add_theme_color(dpg.mvThemeCol_TableBorderLight, _C_BORDER)
            dpg.add_theme_color(dpg.mvThemeCol_TableHeaderBg,  (28, 20,  65, 255))
            dpg.add_theme_color(dpg.mvThemeCol_CheckMark,      _C_ACCENT)
            dpg.add_theme_color(dpg.mvThemeCol_Separator,      (50, 34,  98, 255))
            # Input cursor and selection highlight
            dpg.add_theme_color(dpg.mvThemeCol_TextSelectedBg, (80, 50, 160, 140))
            dpg.add_theme_color(dpg.mvThemeCol_NavHighlight,   _C_ACCENT)
            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding,  4)
            dpg.add_theme_style(dpg.mvStyleVar_ChildRounding,   3)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding,   4)
            dpg.add_theme_style(dpg.mvStyleVar_GrabRounding,    3)
            dpg.add_theme_style(dpg.mvStyleVar_WindowBorderSize, 1)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing,     6, 4)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding,    6, 3)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding,   8, 6)
            dpg.add_theme_style(dpg.mvStyleVar_CellPadding,     4, 3)
    dpg.bind_theme(t)


def _make_go_theme():
    """Amber/orange theme for the GO ▶ button — visually distinct from default purple."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (100, 58, 12, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (180, 110, 22, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (255, 170,  40, 255))
    return t


def _make_fade_bar_theme():
    """Amber progress bar for executor fade progress indicator."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvProgressBar):
            dpg.add_theme_color(dpg.mvThemeCol_PlotHistogram, (200, 130, 20, 200))
    return t


def _make_back_theme():
    """Muted blue theme for the BACK ◀ button."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (20,  50, 100, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (40,  90, 160, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (60, 140, 220, 255))
    return t


def _load_console_font():
    """Load SF Mono if available; returns the font tag or None."""
    sf_mono = "/System/Library/Fonts/SFNSMono.ttf"
    if not os.path.exists(sf_mono):
        return None
    try:
        with dpg.font_registry():
            with dpg.font(sf_mono, 13) as fid:
                dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
        dpg.bind_font(fid)
        return fid
    except Exception as e:
        print(f"  Font: {e} — using default")
        return None


class GUIEngine:
    """
    DearPyGui retro console.

    Usage:
        gui = GUIEngine(midi, fx_engine, fade_engine, output_state,
                        patch, cuestacks, prog, cue_go_fn, cue_back_fn,
                        goto_fn, ai=ai_instance)
        gui.build()    # set up all windows/widgets (main thread)
        gui.run()      # hand control to DearPyGui (blocks until closed)
    """

    # ── Available MIDI target parameters ────────────────────
    # Populated by the live session after binding callbacks.
    # Format: { "display name": (callback_fn, soft_takeover, is_note) }
    target_registry = {}

    def __init__(self, midi, fx_engine, fade_engine, output_state, patch,
                 cuestacks, prog, go_fn, back_fn, goto_fn, reload_fn=None, ai=None,
                 save_fn=None, cmd_fn=None,
                 group_pool=None, color_pool=None, dim_pool=None,
                 cue_pool=None, cuestack_pool=None, active_executor=None,
                 executor_pool=None, fx_pool=None, form_pool=None,
                 rate_pool=None, size_pool=None, spread_pool=None,
                 attr_pools=None, osc=None,
                 library=None, save_patch_fn=None, fx_params=None):
        self._midi       = midi
        self._fx         = fx_engine
        self._fade       = fade_engine
        self._out        = output_state
        self._patch      = patch
        self._stacks     = cuestacks       # {stack_id: CueStack}
        self._prog       = prog
        self._go         = go_fn
        self._back       = back_fn
        self._goto       = goto_fn         # goto_fn(cue_num)
        self._reload     = reload_fn       # reload_fn() — re-fire current cue
        self._ai         = ai
        self._osc        = osc
        self._groups     = group_pool
        self._colors     = color_pool
        self._dims       = dim_pool
        self._cue_pool        = cue_pool
        self._cuestack_pool   = cuestack_pool
        self._active_executor = active_executor  # list[int] so mutations are visible
        self._executor_pool   = executor_pool
        self._fx_pool    = fx_pool
        self._form_pool  = form_pool
        self._rate_pool  = rate_pool
        self._size_pool  = size_pool
        self._spread_pool = spread_pool
        self._attr_pools  = attr_pools or {}   # {name: AttributePool}
        self._library     = library
        self._fx_params   = fx_params
        self._save        = save_fn         # save_fn() → ShowFile.save()
        self._save_patch  = save_patch_fn   # save_patch_fn() → ShowFile.save_patch()
        self._cmd         = cmd_fn          # cmd_fn(str) → result str

        self._cmd_log     = []         # command history lines
        self._cmd_history = []         # entered commands for ↑↓ recall
        self._cmd_hist_i  = -1        # history cursor

        self._flash_held  = {}         # {exec_id: bool} — tracks held state of FLASH buttons
        self._col_btn_themes  = {}     # {slot_n: ((r,g,b), theme_id)} — per-color-preset button themes
        self._dim_btn_themes  = {}     # {slot_n: (level, theme_id)} — per-dim-preset button themes
        self._out_bar_themes  = {}     # {fid: ((r,g,b), theme_id)} — output monitor bar tints
        self._prog_bar_themes = {}     # {fid: ((r,g,b), theme_id)} — programmer bar tints
        self._tap_times       = []     # monotonic timestamps of recent BPM taps

        self._learn_pending      = None    # (ch, number) captured by learn
        self._learn_target       = None    # display name chosen in dropdown
        self._learn_type         = 'cc'    # 'cc' or 'note'
        self._learn_armed_type   = 'cc'    # saved copy — survives MIDI thread clearing _learn_type
        self._learn_armed        = False
        self._pending_table_refresh = False  # set from MIDI thread; consumed by main thread _tick

        # Tags for dynamic MIDI table rows — key=(ch,num,type)
        self._map_rows = {}
        # Reassign flow: stores {'type','ch','num','label'} when user clicks ► on a row
        self._reassign_pending = None
        self._ai_history       = []   # list of {ts, prompt, summary, actions}

    # ── Popup layout persistence ─────────────────────────────

    _POPUP_TAGS = [
        "patch_window", "midi_window", "fx_editor_window",
        "keys_window", "changelog_window", "pages_window", "monitors_window",
        "ai_history_window", "attr_window",
    ]
    _POPUP_LAYOUT_FILE = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "studio_data", "popup_layout.json"
    )

    def _save_popup_layout(self):
        layout = {}
        for tag in self._POPUP_TAGS:
            try:
                cfg = dpg.get_item_configuration(tag)
                layout[tag] = {
                    "pos":    list(cfg.get("pos",    [100, 100])),
                    "width":  int(cfg.get("width",   700)),
                    "height": int(cfg.get("height",  400)),
                    "show":   bool(dpg.is_item_shown(tag)),
                }
            except Exception:
                pass
        try:
            os.makedirs(os.path.dirname(self._POPUP_LAYOUT_FILE), exist_ok=True)
            with open(self._POPUP_LAYOUT_FILE, "w") as f:
                json.dump(layout, f, indent=2)
        except Exception:
            pass

    # Popups that need a data refresh before they can be shown
    _POPUP_REFRESH = {
        "changelog_window": "_refresh_changelog_popup",
        "patch_window":     "_refresh_patch_table",
        "pages_window":     "_refresh_pages_table",
    }

    def _load_popup_layout(self):
        try:
            with open(self._POPUP_LAYOUT_FILE) as f:
                layout = json.load(f)
            for tag, cfg in layout.items():
                try:
                    dpg.configure_item(tag, pos=cfg["pos"],
                                       width=cfg["width"], height=cfg["height"])
                    if cfg.get("show"):
                        refresh = self._POPUP_REFRESH.get(tag)
                        if refresh:
                            getattr(self, refresh)()
                        dpg.show_item(tag)
                except Exception:
                    pass
        except Exception:
            pass

    # ── Build ────────────────────────────────────────────────

    def build(self):
        if not _DPG_OK:
            print("  GUI: dearpygui not installed — pip install dearpygui")
            return

        dpg.create_context()
        _apply_theme()
        _load_console_font()
        self._go_theme       = _make_go_theme()
        self._back_theme     = _make_back_theme()
        self._fade_bar_theme = _make_fade_bar_theme()

        W, H = 1920, 1040   # trimmed from 1080: macOS menu bar eats ~25-38px off a
                            # non-resizable full-height viewport, clipping the bottom
        self._vp_w, self._vp_h = W, H   # stash for overlay builder (viewport not yet created)

        with dpg.window(tag="main", no_close=True, no_collapse=True,
                        no_move=True, no_resize=True, no_title_bar=True):
            # Scrolling left ON (was off): stacked panels (header + 3-col row +
            # pools row + monitors row + AI bar) can exceed the visible viewport
            # height, and with no_scrollbar the overflow was silently clipped
            # with no way to reach it. Scrolling is a safe fallback regardless
            # of the exact overflow amount, which isn't verifiable without a
            # real display.
            self._build_header()
            with dpg.group(horizontal=True):
                self._build_left_column()
                self._build_right_column()
                self._build_stage_panel()
            self._build_pools_row()
            if self._ai:
                self._build_ai_bar()
        self._build_midi_popup()
        self._build_patch_popup()
        self._build_keys_popup()
        self._build_fx_editor_popup()
        self._build_changelog_popup()
        self._build_pages_popup()
        self._build_attr_popup()
        self._build_monitors_popup()
        self._build_ai_history_popup()

        with dpg.handler_registry():
            dpg.add_key_press_handler(dpg.mvKey_Delete,
                                      callback=self._on_delete_key)
            # Route printable keys to cmd_input when no text/number widget has focus.
            # This lets the user type commands immediately after clicking soft-buttons
            # without needing to click the input field first — and avoids the DPG
            # focus-transfer bug where the input text gets select-all'd on focus gain.
            _letter_keys = [
                (dpg.mvKey_A,'a','A'),(dpg.mvKey_B,'b','B'),(dpg.mvKey_C,'c','C'),
                (dpg.mvKey_D,'d','D'),(dpg.mvKey_E,'e','E'),(dpg.mvKey_F,'f','F'),
                (dpg.mvKey_G,'g','G'),(dpg.mvKey_H,'h','H'),(dpg.mvKey_I,'i','I'),
                (dpg.mvKey_J,'j','J'),(dpg.mvKey_K,'k','K'),(dpg.mvKey_L,'l','L'),
                (dpg.mvKey_M,'m','M'),(dpg.mvKey_N,'n','N'),(dpg.mvKey_O,'o','O'),
                (dpg.mvKey_P,'p','P'),(dpg.mvKey_Q,'q','Q'),(dpg.mvKey_R,'r','R'),
                (dpg.mvKey_S,'s','S'),(dpg.mvKey_T,'t','T'),(dpg.mvKey_U,'u','U'),
                (dpg.mvKey_V,'v','V'),(dpg.mvKey_W,'w','W'),(dpg.mvKey_X,'x','X'),
                (dpg.mvKey_Y,'y','Y'),(dpg.mvKey_Z,'z','Z'),
                (dpg.mvKey_0,'0',')'),(dpg.mvKey_1,'1','!'),(dpg.mvKey_2,'2','@'),
                (dpg.mvKey_3,'3','#'),(dpg.mvKey_4,'4','$'),(dpg.mvKey_5,'5','%'),
                (dpg.mvKey_6,'6','^'),(dpg.mvKey_7,'7','&'),(dpg.mvKey_8,'8','*'),
                (dpg.mvKey_9,'9','('),
                (dpg.mvKey_Spacebar,' ',' '),
                (dpg.mvKey_Period,'.','>'),(dpg.mvKey_Minus,'-','_'),
                (dpg.mvKey_Slash,'/','?'),
            ]
            for _k, _lo, _hi in _letter_keys:
                dpg.add_key_press_handler(_k, callback=self._on_global_char,
                                          user_data=(_lo, _hi))
            dpg.add_key_press_handler(dpg.mvKey_Back,
                                      callback=self._on_global_backspace)
            dpg.add_key_press_handler(dpg.mvKey_Return,
                                      callback=self._on_global_enter)
            dpg.add_key_press_handler(dpg.mvKey_NumPadEnter,
                                      callback=self._on_global_enter)
            dpg.add_key_press_handler(dpg.mvKey_F4,
                                      callback=lambda *_: self._back())
            dpg.add_key_press_handler(dpg.mvKey_F5,
                                      callback=lambda *_: self._go())
            dpg.add_key_press_handler(dpg.mvKey_S,
                                      callback=self._on_ctrl_s)
            dpg.add_key_press_handler(dpg.mvKey_Up,
                                      callback=self._on_hist_up)
            dpg.add_key_press_handler(dpg.mvKey_Down,
                                      callback=self._on_hist_down)
            dpg.add_mouse_click_handler(callback=self._on_global_mouse_click)

        # Apply per-item themes after widgets are built
        try:
            dpg.bind_item_theme("go_btn",   self._go_theme)
            dpg.bind_item_theme("back_btn", self._back_theme)
        except Exception:
            pass

        dpg.create_viewport(title="Studio Console", width=W, height=H,
                            resizable=True, x_pos=0, y_pos=32)
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_primary_window("main", True)

    def _build_header(self):
        with dpg.group(horizontal=True):
            dpg.add_text("studio console  v0.16", color=_C_ACCENT)
            dpg.add_text("   |   ", color=_C_DIM)
            dpg.add_text("▶ (none)", tag="hdr_cue", color=_C_TEXT)
            dpg.add_text("   |   ", color=_C_DIM)
            dpg.add_text("fx: off", tag="hdr_fx", color=_C_DIM)
            dpg.add_text("   |   ", color=_C_DIM)
            dpg.add_text("", tag="hdr_clock", color=_C_DIM)
            dpg.add_text("dim: --", tag="hdr_dim", color=_C_TEXT)
            dpg.add_text("   ", color=_C_BORDER)
            dpg.add_button(label="patch", width=60,
                           callback=self._on_patch_toggle)
            dpg.add_spacer(width=4)
            dpg.add_button(label="midi", width=60,
                           callback=self._on_midi_toggle)
            dpg.add_spacer(width=4)
            dpg.add_button(label="fx ed", width=60,
                           callback=self._on_fx_editor_toggle)
            dpg.add_spacer(width=4)
            dpg.add_button(label="?", width=30,
                           callback=self._on_keys_toggle)
            dpg.add_spacer(width=4)
            dpg.add_button(label="log", width=50,
                           callback=self._on_changelog_toggle)
            dpg.add_spacer(width=4)
            dpg.add_button(label="pages", width=55,
                           callback=self._on_pages_toggle)
            dpg.add_spacer(width=4)
            dpg.add_button(label="attr", width=50,
                           callback=self._on_attr_popup_toggle)
            dpg.add_spacer(width=4)
            dpg.add_button(label="mon", width=50,
                           callback=self._on_monitors_toggle)
            dpg.add_spacer(width=4)
            dpg.add_button(label="save show", width=90,
                           callback=self._on_save)
            dpg.add_text("", tag="hdr_save_status", color=_C_DIM)
        dpg.add_separator()
        # ── Programmer + Selection status bar ──────────────────
        with dpg.group(horizontal=True):
            dpg.add_text("●", tag="sb_prog_dot",   color=_C_DIM)
            dpg.add_text("PROGRAMMER", tag="sb_prog_lbl", color=_C_DIM)
            dpg.add_spacer(width=20)
            dpg.add_text("BLIND", tag="sb_blind_lbl", color=_C_DIM)
            dpg.add_spacer(width=10)
            dpg.add_text("BBO", tag="sb_bbo_lbl", color=_C_DIM)
            dpg.add_spacer(width=20)
            dpg.add_text("PT", tag="sb_pt_lbl", color=_C_DIM)
            dpg.add_spacer(width=20)
            dpg.add_text("SEL", color=_C_DIM)
            dpg.add_spacer(width=6)
            # One chip per patched fixture — lit when selected
            if self._patch:
                for master in self._patch.all_fixtures():
                    fid = master.fixture_id
                    dpg.add_text(f"[{fid}]", tag=f"sb_sel_{fid}", color=_C_DIM)
                    dpg.add_spacer(width=2)
        dpg.add_separator()

    def _build_left_column(self):
        self._displayed_executor  = None
        self._displayed_cs_name   = None
        self._last_playbacks_hash = None
        _W = self._W_LEFT
        with dpg.child_window(tag="left_col", width=_W, height=self._H_MAIN,
                              border=True, no_scrollbar=True, no_scroll_with_mouse=True):
            # ── Cue list ─────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("cuestack", color=_C_ACCENT)
                dpg.add_combo(tag="left_cs_combo", items=["—"], default_value="—",
                              width=-1, height_mode=dpg.mvComboHeight_Small,
                              callback=self._on_cs_combo_select)
            dpg.add_separator()
            # Fixed-height scroll area for the cue list so it never pushes content down
            with dpg.child_window(tag="cue_list_scroll", width=-1, height=78,
                                  border=False, no_scrollbar=True, no_scroll_with_mouse=True):
                dpg.add_group(tag="cue_list_group")
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_button(label=" ◀ BACK ", tag="back_btn", width=106,
                               callback=lambda: self._back())
                dpg.add_button(label=" ↺ RELOAD ", width=120,
                               callback=lambda: self._reload() if self._reload else None)
                dpg.add_button(label="  GO ▶  ", tag="go_btn", width=106,
                               callback=lambda: self._go())

            dpg.add_spacer(height=4)
            # ── Active playbacks ─────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("active playbacks", color=_C_ACCENT)
                dpg.add_spacer(width=4)
                dpg.add_button(label="stop all", width=78,
                               callback=self._on_stop_all_executors)
            dpg.add_separator()
            with dpg.child_window(tag="playbacks_list", width=-1, height=90,
                                  border=False, no_scrollbar=True, no_scroll_with_mouse=True):
                dpg.add_text("— none running", tag="playbacks_empty", color=_C_DIM)

            dpg.add_spacer(height=2)
            # ── Cue timing editor ────────────────
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_text("cue timing", color=_C_DIM)
                dpg.add_spacer(width=4)
                dpg.add_text("—", tag="cue_timing_label", color=_C_DIM)
            _tw = _W - 96
            dpg.add_drag_float(tag="cue_fade_input", label="Fade s",
                               default_value=0.0, min_value=0.0, max_value=30.0,
                               speed=0.05, format="%.2f", width=_tw,
                               callback=self._on_cue_fade_edit)
            dpg.add_drag_float(tag="cue_delay_input", label="Dly  s",
                               default_value=0.0, min_value=0.0, max_value=30.0,
                               speed=0.05, format="%.2f", width=_tw,
                               callback=self._on_cue_delay_edit)

            dpg.add_spacer(height=2)
            # ── FX controls ─────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("fx", color=_C_ACCENT)
                dpg.add_spacer(width=4)
                dpg.add_button(label="tap", tag="fx_tap_btn", width=42, height=18,
                               callback=self._on_tap_tempo)
                dpg.add_text("", tag="fx_tap_label", color=_C_DIM)
            dpg.add_separator()
            _sw = _W - 120
            dpg.add_slider_float(label="Rate BPM", tag="fx_rate",
                                 default_value=60.0, min_value=10.0,
                                 max_value=480.0, width=_sw,
                                 callback=self._on_fx_rate)
            dpg.add_slider_float(label="Size    ", tag="fx_size",
                                 default_value=100.0, min_value=0.0,
                                 max_value=100.0, width=_sw,
                                 callback=self._on_fx_size)
            dpg.add_slider_float(label="Spread  ", tag="fx_spread",
                                 default_value=0.0, min_value=0.0,
                                 max_value=100.0, width=_sw,
                                 callback=self._on_fx_spread)
            dpg.add_button(label="kill fx", width=_W - 20,
                           callback=lambda: self._cmd("KILL FX") if self._cmd else None)

    # ── numpad helpers ───────────────────────────────────────────
    def _numpad_append(self, sender, app_data, user_data):
        """Append a string to the command input field."""
        try:
            dpg.set_value("cmd_input",
                          dpg.get_value("cmd_input") + user_data)
        except Exception:
            pass

    def _numpad_exec(self, sender, app_data, user_data):
        """Execute a command immediately (used by CLEAR, GO, BACK buttons)."""
        cmd = user_data
        self._log(f"> {cmd}")
        if self._cmd:
            result = self._cmd(cmd)
            if result:
                for line in str(result).splitlines():
                    self._log(f"  {line}")

    def _numpad_backspace(self, s=None, a=None, u=None):
        try:
            v = dpg.get_value("cmd_input")
            if v:
                dpg.set_value("cmd_input", v[:-1])
        except Exception:
            pass

    def _numpad_clear_input(self, s=None, a=None, u=None):
        try:
            dpg.set_value("cmd_input", "")
        except Exception:
            pass

    def _cmd_input_needs_focus(self):
        """True when a text/number widget other than cmd_input has keyboard focus."""
        try:
            focused = dpg.get_focused_item()
            if focused == 0:
                return False
            t = dpg.get_item_info(focused).get('type', '')
            return ('Input' in t or 'Combo' in t)
        except Exception:
            return False

    def _on_hist_up(self, *_):
        """↑ arrow: scroll backward through command history."""
        if self._cmd_input_needs_focus():
            return
        if not self._cmd_history:
            return
        self._cmd_hist_i = min(len(self._cmd_history) - 1, self._cmd_hist_i + 1)
        try:
            dpg.set_value("cmd_input",
                          self._cmd_history[-(self._cmd_hist_i + 1)])
        except Exception:
            pass

    def _on_hist_down(self, *_):
        """↓ arrow: scroll forward through command history (toward blank)."""
        if self._cmd_input_needs_focus():
            return
        self._cmd_hist_i -= 1
        if self._cmd_hist_i < 0:
            self._cmd_hist_i = -1
            try:
                dpg.set_value("cmd_input", "")
            except Exception:
                pass
        else:
            try:
                dpg.set_value("cmd_input",
                              self._cmd_history[-(self._cmd_hist_i + 1)])
            except Exception:
                pass

    def _on_ctrl_s(self, *_):
        """Ctrl+S: save show."""
        is_ctrl = (dpg.is_key_down(dpg.mvKey_LControl) or
                   dpg.is_key_down(dpg.mvKey_RControl) or
                   dpg.is_key_down(dpg.mvKey_LSuper) or   # Cmd on macOS
                   dpg.is_key_down(dpg.mvKey_RSuper))
        if is_ctrl:
            self._on_save()

    def _on_global_mouse_click(self, sender, app_data):
        """Handle left-click on the stage canvas to select/deselect fixtures."""
        if app_data != 0:   # 0 = left button
            return
        try:
            if not dpg.is_item_hovered("stage_canvas"):
                return
        except Exception:
            return
        try:
            canvas_min = dpg.get_item_rect_min("stage_canvas")
            canvas_sz  = dpg.get_item_rect_size("stage_canvas")
            mouse      = dpg.get_mouse_pos(local=False)
            rel_x = mouse[0] - canvas_min[0]
            w     = canvas_sz[0]
            if w < 1:
                return
            fixtures = list(self._patch.all_fixtures())
            n = len(fixtures)
            if not n:
                return
            gap = 10
            tw  = (w - gap * (n + 1)) / n
            # Which fixture column was clicked?
            clicked_idx = None
            for i in range(n):
                x0 = gap + i * (tw + gap)
                x1 = x0 + tw
                if x0 <= rel_x <= x1:
                    clicked_idx = i
                    break
            if clicked_idx is None:
                return
            master = fixtures[clicked_idx]
            # Shift-click: toggle fixture in/out of selection
            shift = dpg.is_key_down(dpg.mvKey_LShift) or dpg.is_key_down(dpg.mvKey_RShift)
            if shift:
                cur_masters = [f for f in self._prog.selection if isinstance(f, MasterFixture)]
                if master in cur_masters:
                    cur_masters.remove(master)
                else:
                    cur_masters.append(master)
                self._prog.select(cur_masters)
                sel_str = " ".join(str(m.fixture_id) for m in cur_masters) or "none"
                self._log(f"> SELECT {sel_str}")
            else:
                self._prog.select([master])
                self._log(f"> SELECT {master.fixture_id}")
        except Exception:
            pass

    def _on_global_char(self, sender, app_data, user_data):
        """Route printable keys to cmd_input when no other text widget is active."""
        if self._cmd_input_needs_focus():
            return
        lo, hi = user_data
        is_shift = (dpg.is_key_down(dpg.mvKey_LShift) or
                    dpg.is_key_down(dpg.mvKey_RShift))
        # Suppress Ctrl+key combos (they're shortcuts, not text input)
        is_ctrl = (dpg.is_key_down(dpg.mvKey_LControl) or
                   dpg.is_key_down(dpg.mvKey_RControl) or
                   dpg.is_key_down(dpg.mvKey_LSuper) or
                   dpg.is_key_down(dpg.mvKey_RSuper))
        if is_ctrl:
            return
        dpg.set_value("cmd_input",
                      dpg.get_value("cmd_input") + (hi if is_shift else lo))

    def _on_global_backspace(self, *_):
        """Route Backspace to cmd_input when no other text widget is active."""
        if self._cmd_input_needs_focus():
            return
        v = dpg.get_value("cmd_input")
        if v:
            dpg.set_value("cmd_input", v[:-1])

    def _on_global_enter(self, *_):
        """Execute cmd_input command when Enter pressed outside the input field."""
        if self._cmd_input_needs_focus():
            return
        self._on_cmd_execute()

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

    def _on_patch_toggle(self):
        try:
            if dpg.is_item_shown("patch_window"):
                self._save_popup_layout()
                dpg.hide_item("patch_window")
            else:
                self._refresh_patch_table()
                dpg.show_item("patch_window")
        except Exception:
            pass

    def _on_midi_toggle(self):
        try:
            if dpg.is_item_shown("midi_window"):
                self._save_popup_layout()
                dpg.hide_item("midi_window")
            else:
                dpg.show_item("midi_window")
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

    def _on_attr_popup_toggle(self):
        try:
            if dpg.is_item_shown("attr_window"):
                self._save_popup_layout()
                dpg.hide_item("attr_window")
            else:
                dpg.show_item("attr_window")
        except Exception:
            pass

    def _on_monitors_toggle(self):
        try:
            if dpg.is_item_shown("monitors_window"):
                self._save_popup_layout()
                dpg.hide_item("monitors_window")
            else:
                dpg.show_item("monitors_window")
        except Exception:
            pass

    def _build_right_column(self):
        # Digit buttons fill 3 cols; keyword buttons fill 3 cols; all proportioned to right col width.
        # Total numpad width: 3×_NW + gap + _KW + 2×(_NW+gap) = fills ~440px of _W_RIGHT
        _NW = 70   # digit button width
        _NH = 40   # digit button height — 4 rows × 40 + 3 × 4-gap = 172px
        _KW = 108  # keyword button width (wider label)
        _BH = 20   # quick-action button height
        _W  = self._W_RIGHT

        with dpg.child_window(tag="right_col", width=_W, height=self._H_MAIN,
                              border=True, no_scrollbar=True, no_scroll_with_mouse=True):
            # ── Header ─────────────────────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("command line", color=_C_ACCENT)
                dpg.add_spacer(width=10)
                dpg.add_text("sel: —", tag="cmd_sel_count", color=_C_DIM)

            # ── Log — proportioned to leave room for keypad ─────
            with dpg.child_window(tag="cmd_log_win", width=-1, height=88,
                                  border=True, horizontal_scrollbar=False,
                                  no_scrollbar=True, no_scroll_with_mouse=True):
                dpg.add_text("", tag="cmd_log", wrap=0)

            # ── Input row ──────────────────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("cmd >", color=_C_ACCENT)
                dpg.add_input_text(
                    tag="cmd_input",
                    hint="1 THRU 6  |  1 THRU 6 R 255  |  FX SINE RED  |  GO  |  SAVE",
                    width=-220, on_enter=True,
                    callback=self._on_cmd_execute,
                )
                dpg.add_button(label="enter", width=80, height=22,
                               callback=self._on_cmd_execute)
                dpg.add_button(label="clr", width=50, height=22,
                               callback=self._numpad_clear_input)

            dpg.add_separator()

            # ── Quick action row 1: cue / record / FX ──────────
            with dpg.group(horizontal=True):
                for label, ud in [
                    ("REC CUE", "RECORD CUE "), ("UPD CUE", "UPDATE CUE "),
                    ("cue",     "CUE "),         ("rec fx",  "RECORD FX "),
                    ("fx",      "FX "),           ("rec grp", "RECORD GROUP "),
                    ("group",   "GROUP "),
                ]:
                    dpg.add_button(label=label, height=_BH,
                                   callback=self._numpad_append, user_data=ud)

            # ── Quick action row 2: timing / CLEAR / transport ─
            with dpg.group(horizontal=True):
                for label, ud in [
                    ("fade",  " FADE "), ("cfade", " CFADE "),
                    ("dfade", " DFADE "), ("delay", " DELAY "),
                ]:
                    dpg.add_button(label=label, height=_BH,
                                   callback=self._numpad_append, user_data=ud)
                dpg.add_spacer(width=6)
                for label, ud in [
                    ("CLEAR", "CLEAR"), ("reload", "RELOAD"),
                    ("go",    "GO"),    ("back",   "BACK"),
                ]:
                    dpg.add_button(label=label, height=_BH,
                                   callback=self._numpad_exec, user_data=ud)

            dpg.add_separator()

            # ── Numpad + keyword keys ───────────────────────────
            # Digit pad (left) + keyword pad (right), each 4 rows × 3 cols.
            # Total width: 3×_NW + 12 + 3-col-kw, all within _W_RIGHT.
            with dpg.group(horizontal=True):

                # Left: digit pad [7][8][9] / [4][5][6] / [1][2][3] / [⌫][0][.]
                with dpg.group():
                    for row_digits in ([7, 8, 9], [4, 5, 6], [1, 2, 3]):
                        with dpg.group(horizontal=True):
                            for d in row_digits:
                                dpg.add_button(
                                    label=str(d), width=_NW, height=_NH,
                                    callback=self._numpad_append,
                                    user_data=str(d))
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="⌫",  width=_NW, height=_NH,
                                       callback=self._numpad_backspace)
                        dpg.add_button(label="0",   width=_NW, height=_NH,
                                       callback=self._numpad_append, user_data="0")
                        dpg.add_button(label=".",   width=_NW, height=_NH,
                                       callback=self._numpad_append, user_data=".")

                dpg.add_spacer(width=12)

                # Right: keywords — 4 rows × (wide + narrow + narrow)
                _kw_rows = [
                    [("thru", _KW, self._numpad_append, " THRU "),
                     (" +",   _NW, self._numpad_append, " + "),
                     ("at",   _NW, self._numpad_append, " AT ")],
                    [("full", _KW, self._numpad_exec,   "FULL"),
                     ("out",  _NW, self._numpad_exec,   "OUT"),
                     (" R ",  _NW, self._numpad_append, " R ")],
                    [("dim",  _KW, self._numpad_append, " DIM "),
                     (" G ",  _NW, self._numpad_append, " G "),
                     (" B ",  _NW, self._numpad_append, " B ")],
                    [("clr↵", _KW, self._numpad_clear_input, None),
                     ("grp",  _NW, self._numpad_append, "GROUP "),
                     ("col",  _NW, self._numpad_append, "COLOR ")],
                ]
                with dpg.group():
                    for row in _kw_rows:
                        with dpg.group(horizontal=True):
                            for label, w, cb, ud in row:
                                if ud is not None:
                                    dpg.add_button(label=label, width=w, height=_NH,
                                                   callback=cb, user_data=ud)
                                else:
                                    dpg.add_button(label=label, width=w, height=_NH,
                                                   callback=cb)
    # ── Layout budget: 1920 × 1080, no scrollbars anywhere ──────
    _W          = 1920
    _H          = 1080
    # Section heights — sized to fit 1040px viewport with no scroll (no-AI case).
    # Budget: 1040px viewport - 12px WindowPadding - gaps ≈ 988px for content.
    # Header~70 + 3-col row~480 + sep~2 + P1~170 + P2~170 + Forms~88 = 980px ✓ (no AI bar)
    # Attribute pools (position/gobo/zoom/focus/beam) live in a separate popup
    # (_build_attr_popup), not stacked in the main window — see _build_pools_row.
    # AI bar (~70px, only when self._ai is set) is the one section not counted
    # above; the main window keeps scrolling enabled as a fallback for that case
    # since it can't be verified pixel-exact without a real display.
    _H_MAIN     = 480   # main 3-col area — tall enough for all left-col FX controls
    _H_P1       = 170   # pool row 1: 4×24btn + 3×4gap + 26header + 12WP = 146 content, 170 total
    _H_P2       = 170   # pool row 2
    _H_FORMS    =  56   # forms single row (unused — _build_forms_panel computes own height)
    _H_MON      = 270   # monitor popup panel height (not in main layout)
    # Column widths
    _W_LEFT     = 380
    _W_RIGHT    = 720
    # Pool grid
    _POOL_SLOTS = 24    # 4 rows × 6 cols per panel
    _POOL_COLS  = 6
    _PANEL_W    = 634   # panels touch: 3 × 634 = 1902 fits 1920 w/ outer padding
    # BTN_W: (634 - 2×8pad - 2×1border - 5×6gap) / 6 = (616-30)/6 = 97.7 → 97
    _BTN_W      =  97   # exactly fits 6 columns in a 634-wide panel
    _BTN_H      =  24   # 4 rows × 24 + 3 × 4gap + header = 132px content
    _POOL_H     = _H_P1

    @staticmethod
    def _best_sub_layout(pixel_count, slot_w, sub_h):
        """Return (rows, cols, dot_size) maximising dot size for given slot dimensions."""
        import math
        if pixel_count <= 1:
            return 1, 1, int(min(slot_w, sub_h))
        sq = int(math.sqrt(pixel_count))
        while sq > 0 and pixel_count % sq != 0:
            sq -= 1
        if sq == 0:
            sq = 1
        ra, ca = sq, pixel_count // sq          # landscape candidate
        rb, cb = ca, ra                          # portrait candidate
        # dot_s = stride including 1px gap; maximise min of both axes
        dot_a = min(slot_w / ca, sub_h / ra)
        dot_b = min(slot_w / cb, sub_h / rb)
        if dot_b >= dot_a:
            rows, cols, dot_f = rb, cb, dot_b
        else:
            rows, cols, dot_f = ra, ca, dot_a
        return rows, cols, max(1, int(dot_f) - 1)

    def _build_stage_panel(self):
        """Inline stage view — third column in the main row, fills remaining width."""
        vp_w      = getattr(self, '_vp_w', self._W)
        canvas_w  = max(200, vp_w - self._W_LEFT - self._W_RIGHT - 24)
        canvas_h  = self._H_MAIN - 42   # _H_MAIN minus master-fader row and padding
        with dpg.child_window(tag="stage_win", width=-1, height=self._H_MAIN,
                              border=True, no_scrollbar=True,
                              no_scroll_with_mouse=True):
            with dpg.group(horizontal=True):
                dpg.add_text("MASTER", color=_C_ACCENT)
                dpg.add_slider_int(
                    tag="stage_master_fader",
                    default_value=100, min_value=0, max_value=100,
                    format="%d%%", width=-1,
                    callback=lambda s, a, u: (
                        setattr(self._out, 'master_level', a / 100.0)
                        if self._out else None
                    ),
                )
            with dpg.drawlist(tag="stage_canvas", width=canvas_w, height=canvas_h):
                fixtures = list(self._patch.all_fixtures())
                for i, master in enumerate(fixtures):
                    dpg.draw_rectangle(
                        pmin=(0, 0), pmax=(1, 1),
                        tag=f"stage_rect_{i}",
                        fill=(8, 6, 18, 255),
                        color=(38, 26, 78, 255),
                        thickness=1,
                    )
                    dpg.draw_text(
                        pos=(0, 0), tag=f"stage_lbl_{i}",
                        text="", color=_C_TEXT, size=14,
                    )
                    for j in range(len(master.sub_fixtures)):
                        dpg.draw_rectangle(
                            pmin=(0, 0), pmax=(1, 1),
                            tag=f"stage_sub_{i}_{j}",
                            fill=(8, 6, 18, 255),
                            color=(0, 0, 0, 0), thickness=0,
                        )

    def _tick_stage(self):
        """Recompute fixture colours from output state and update stage canvas.
        All geometry is computed here from the actual canvas size so the layout
        scales automatically when the window is resized."""
        try:
            rect = dpg.get_item_rect_size("stage_canvas")
            w, h = rect[0], rect[1]
        except Exception:
            return
        if w < 20 or h < 20:
            return
        fixtures = list(self._patch.all_fixtures())
        n = len(fixtures)
        if not n:
            return

        cue_merged = self._out._merged_cue_layer() if self._out else {}
        gm = self._out.master_level if self._out else 1.0

        # Layout constants
        gap    = 10
        mh     = 50                    # master bar height
        sub_y0 = gap + mh + 10        # top of sub-pixel region
        sub_h  = h - sub_y0 - gap     # vertical space for sub-pixel grid
        tw     = (w - gap * (n + 1)) / n   # width slot per fixture

        for i, master in enumerate(fixtures):
            x0  = gap + i * (tw + gap)
            x1  = x0 + tw
            fid = str(master.fixture_id)

            # --- Master bar colour (sampled from first sub-fixture) ---
            r = g = b = 0
            if self._out:
                first_sub = next(iter(master.sub_fixtures.values()), None)
                if first_sub:
                    sfid   = str(first_sub.fixture_id)
                    prog_s = self._out.programmer_layer.get(sfid, {})
                    cue_s  = cue_merged.get(sfid, {})
                    fx_s   = self._out.fx_layer.get(sfid, {})
                    base_r = prog_s.get('red',   cue_s.get('red',   0))
                    base_g = prog_s.get('green', cue_s.get('green', 0))
                    base_b = prog_s.get('blue',  cue_s.get('blue',  0))
                    r = int(fx_s['red'])   if 'red'   in fx_s else int(base_r)
                    g = int(fx_s['green']) if 'green' in fx_s else int(base_g)
                    b = int(fx_s['blue'])  if 'blue'  in fx_s else int(base_b)
                    mp  = self._out.programmer_layer.get(fid, {})
                    mc  = cue_merged.get(fid, {})
                    fxm = self._out.fx_layer.get(fid, {})
                    fdr = fxm.get('dim')
                    ron = bool('red' in fx_s or 'green' in fx_s or 'blue' in fx_s)
                    if fdr is not None:
                        dim = max(0.0, min(1.0, mp.get('dim', mc.get('dim', master.virtual_dimmer)) * (fdr / 255.0)))
                    elif ron:
                        cd  = mc.get('dim')
                        dim = mp.get('dim', cd if cd is not None else 1.0)
                    else:
                        dim = mp.get('dim', mc.get('dim', master.virtual_dimmer))
                    r = max(0, min(255, int(r * dim * gm)))
                    g = max(0, min(255, int(g * dim * gm)))
                    b = max(0, min(255, int(b * dim * gm)))
            fill = (r, g, b, 255) if (r or g or b) else (8, 6, 18, 255)
            sel_masters = {f.fixture_id for f in self._prog.selection
                           if isinstance(f, MasterFixture)}
            border_col = (162, 115, 255, 255) if master.fixture_id in sel_masters else (38, 26, 78, 255)
            try:
                dpg.configure_item(f"stage_rect_{i}", pmin=(x0, gap), pmax=(x1, gap + mh),
                                   fill=fill, color=border_col, thickness=2)
                dpg.configure_item(f"stage_lbl_{i}",  pos=(x0 + 4, gap + 14), text=master.name[:10])
            except Exception:
                pass

            # --- Sub-pixel dots — auto-pick orientation that maximises dot size ---
            if not self._out or sub_h < 2:
                continue
            subs = list(master.sub_fixtures.values())
            pc   = len(subs)
            rows, cols, dot = self._best_sub_layout(pc, tw, sub_h)
            dot_s = dot + 1   # stride = dot + 1px gap

            for j, sub in enumerate(subs):
                row  = j // cols
                col  = j % cols
                sx0  = x0 + col * dot_s
                sy0  = sub_y0 + row * dot_s
                sfid = str(sub.fixture_id)
                ps   = self._out.programmer_layer.get(sfid, {})
                cs   = cue_merged.get(sfid, {})
                fs   = self._out.fx_layer.get(sfid, {})
                br   = ps.get('red',   cs.get('red',   0))
                bg2  = ps.get('green', cs.get('green', 0))
                bb   = ps.get('blue',  cs.get('blue',  0))
                sr   = int(fs['red'])   if 'red'   in fs else int(br)
                sg   = int(fs['green']) if 'green' in fs else int(bg2)
                sb2  = int(fs['blue'])  if 'blue'  in fs else int(bb)
                mp   = self._out.programmer_layer.get(fid, {})
                mc   = cue_merged.get(fid, {})
                fxm  = self._out.fx_layer.get(fid, {})
                fdr  = fxm.get('dim')
                ron  = bool('red' in fs or 'green' in fs or 'blue' in fs)
                if fdr is not None:
                    sdim = max(0.0, min(1.0, mp.get('dim', mc.get('dim', master.virtual_dimmer)) * (fdr / 255.0)))
                elif ron:
                    cd   = mc.get('dim')
                    sdim = mp.get('dim', cd if cd is not None else 1.0)
                else:
                    sdim = mp.get('dim', mc.get('dim', master.virtual_dimmer))
                sr  = max(0, min(255, int(sr  * sdim * gm)))
                sg  = max(0, min(255, int(sg  * sdim * gm)))
                sb2 = max(0, min(255, int(sb2 * sdim * gm)))
                sfill = (sr, sg, sb2, 255) if (sr or sg or sb2) else (8, 6, 18, 255)
                try:
                    dpg.configure_item(f"stage_sub_{i}_{j}",
                                       pmin=(sx0, sy0), pmax=(sx0 + dot, sy0 + dot),
                                       fill=sfill)
                except Exception:
                    pass

    def _build_pools_row(self):
        # Panels touch each other — no spacers, borders serve as dividers.
        dpg.add_separator()
        # Row 1: Groups | Colors | Dims
        with dpg.group(horizontal=True):
            self._build_group_panel()
            self._build_color_panel()
            self._build_dim_panel()
        # Row 2: Cuestacks | Cues | FX Pool
        with dpg.group(horizontal=True):
            self._build_cuestack_panel()
            self._build_cue_panel()
            self._build_fx_pool_panel()
        # Row 3: Forms (full width)
        self._build_forms_panel()
        # Attr pool panels (position/gobo/zoom/focus/beam) live in a separate
        # floating popup (see _build_attr_popup / 'attr' header button) rather
        # than a 5th stacked row here — they're irrelevant for the pure-RGB
        # pixel tubes in this rig and a 5th row pushed the main window past
        # the 1920x1080 budget.

    def _build_group_panel(self):
        rows = self._POOL_SLOTS // self._POOL_COLS
        with dpg.child_window(tag="pool_groups", width=self._PANEL_W,
                              height=self._POOL_H, border=True,
                              no_scrollbar=True, no_scroll_with_mouse=True):
            dpg.add_text("groups", color=_C_P_GROUPS)
            dpg.add_separator()
            for row in range(rows):
                with dpg.group(horizontal=True):
                    for col in range(self._POOL_COLS):
                        n = row * self._POOL_COLS + col + 1
                        dpg.add_button(
                            tag=f"grp_btn_{n}", label=f"G{n}",
                            width=self._BTN_W, height=self._BTN_H,
                            callback=self._on_group_click, user_data=n)
                        with dpg.tooltip(f"grp_btn_{n}"):
                            dpg.add_text(f"Group {n}", tag=f"grp_tip_{n}")

    def _build_color_panel(self):
        rows = self._POOL_SLOTS // self._POOL_COLS
        with dpg.child_window(tag="pool_colors", width=self._PANEL_W,
                              height=self._POOL_H, border=True,
                              no_scrollbar=True, no_scroll_with_mouse=True):
            dpg.add_text("color presets", color=_C_P_COLORS)
            dpg.add_separator()
            for row in range(rows):
                with dpg.group(horizontal=True):
                    for col in range(self._POOL_COLS):
                        n = row * self._POOL_COLS + col + 1
                        dpg.add_button(
                            tag=f"col_btn_{n}", label=f"C{n}",
                            width=self._BTN_W, height=self._BTN_H,
                            callback=self._on_color_click, user_data=n)

    def _build_dim_panel(self):
        rows = self._POOL_SLOTS // self._POOL_COLS
        with dpg.child_window(tag="pool_dims", width=self._PANEL_W,
                              height=self._POOL_H, border=True,
                              no_scrollbar=True, no_scroll_with_mouse=True):
            dpg.add_text("dim presets", color=_C_P_DIMS)
            dpg.add_separator()
            for row in range(rows):
                with dpg.group(horizontal=True):
                    for col in range(self._POOL_COLS):
                        n = row * self._POOL_COLS + col + 1
                        dpg.add_button(
                            tag=f"dim_btn_{n}", label=f"D{n}",
                            width=self._BTN_W, height=self._BTN_H,
                            callback=self._on_dim_click, user_data=n)
                        with dpg.tooltip(f"dim_btn_{n}"):
                            dpg.add_text(f"Dim {n}", tag=f"dim_tip_{n}")

    def _focus_cmd(self):
        pass  # key routing via global handlers; no focus transfer needed

    def _on_group_click(self, _sender, _app_data, user_data):
        n = user_data
        if self._groups and self._groups.get(n):
            self._groups.recall(n, self._prog)
            self._log(f"> GROUP {n}  recalled — {self._groups.get(n).name}")
        else:
            self._log(f"> GROUP {n} is empty — select fixtures, then name the group:")
            try:
                dpg.set_value("cmd_input", f"RECORD GROUP {n} ")
            except Exception:
                pass
        self._focus_cmd()

    def _on_color_click(self, _sender, _app_data, user_data):
        n = user_data
        if self._colors and self._colors.get(n):
            p = self._colors.get(n)
            p.apply(self._prog)
            self._log(f"> COLOR {n}  applied — {p.name}")
        else:
            self._log(f"> COLOR {n} is empty — set colour in programmer, then name it:")
            try:
                dpg.set_value("cmd_input", f"RECORD COLOR {n} ")
            except Exception:
                pass
        self._focus_cmd()

    def _on_dim_click(self, _sender, _app_data, user_data):
        n = user_data
        if self._dims and self._dims.get(n):
            p = self._dims.get(n)
            p.apply(self._prog)
            self._log(f"> DIM PRESET {n}  applied — {p.name}")
        else:
            self._log(f"> DIM PRESET {n} is empty — set dim in programmer, then name it:")
            try:
                dpg.set_value("cmd_input", f"RECORD DIM {n} ")
            except Exception:
                pass
        self._focus_cmd()

    def _build_cuestack_panel(self):
        rows = self._POOL_SLOTS // self._POOL_COLS
        with dpg.child_window(tag="pool_cuestacks", width=self._PANEL_W,
                              height=self._POOL_H, border=True,
                              no_scrollbar=True, no_scroll_with_mouse=True):
            dpg.add_text("cuestacks", color=_C_P_CS)
            dpg.add_separator()
            for row in range(rows):
                with dpg.group(horizontal=True):
                    for col in range(self._POOL_COLS):
                        n = row * self._POOL_COLS + col + 1
                        dpg.add_button(
                            tag=f"cs_btn_{n}", label=f"CS{n}",
                            width=self._BTN_W, height=self._BTN_H,
                            callback=self._on_cuestack_click, user_data=n)

    def _build_cue_panel(self):
        rows = self._POOL_SLOTS // self._POOL_COLS
        with dpg.child_window(tag="pool_cues", width=self._PANEL_W,
                              height=self._POOL_H, border=True,
                              no_scrollbar=True, no_scroll_with_mouse=True):
            dpg.add_text("cues", color=_C_P_CUES)
            dpg.add_separator()
            for row in range(rows):
                with dpg.group(horizontal=True):
                    for col in range(self._POOL_COLS):
                        n = row * self._POOL_COLS + col + 1
                        dpg.add_button(
                            tag=f"cue_btn_{n}", label=f"{n}",
                            width=self._BTN_W, height=self._BTN_H,
                            callback=self._on_cue_click, user_data=n)
                        with dpg.tooltip(f"cue_btn_{n}"):
                            dpg.add_text(f"Cue {n}", tag=f"cue_tip_{n}")

    def _on_cuestack_click(self, _sender, _app_data, user_data):
        n = user_data
        if self._cuestack_pool and self._cuestack_pool.get(n):
            if self._active_executor is not None:
                self._active_executor[0] = n
            cs = self._cuestack_pool.get(n)
            self._log(f"> CUESTACK {n}  selected — {cs.name}")
        else:
            self._log(f"> CUESTACK {n} is empty — name it to create:")
            try:
                dpg.set_value("cmd_input", f"RECORD CUESTACK {n} ")
            except Exception:
                pass
        self._focus_cmd()

    def _on_cue_click(self, _sender, _app_data, user_data):
        n = user_data
        if self._cue_pool and self._cue_pool.get(n):
            cue = self._cue_pool.get(n)
            if self._goto:
                self._goto(float(n))
            self._log(f"> CUE {n} — {cue.name}")
        else:
            self._log(f"> CUE {n} is empty")
        self._focus_cmd()

    def _build_fx_pool_panel(self):
        rows = self._POOL_SLOTS // self._POOL_COLS
        with dpg.child_window(tag="pool_fx", width=self._PANEL_W,
                              height=self._POOL_H, border=True,
                              no_scrollbar=True, no_scroll_with_mouse=True):
            # Header: title + live summary + CLEAR FX all on one line
            with dpg.group(horizontal=True):
                dpg.add_text("fx pool", color=_C_P_FX)
                dpg.add_spacer(width=6)
                dpg.add_text("—", tag="fx_prog_summary", color=_C_DIM)
                dpg.add_spacer(width=4)
                dpg.add_text("", tag="fx_prog_other", color=_C_DIM)
                dpg.add_spacer(width=4)
                dpg.add_button(label="clr fx", width=60, height=18,
                               callback=self._on_clear_fx)
            dpg.add_separator()
            for row in range(rows):
                with dpg.group(horizontal=True):
                    for col in range(self._POOL_COLS):
                        n = row * self._POOL_COLS + col + 1
                        dpg.add_button(
                            tag=f"fx_btn_{n}", label=f"FX{n}",
                            width=self._BTN_W, height=self._BTN_H,
                            callback=self._on_fx_click, user_data=n)

    def _build_attr_pool_panel(self, attr_name, color, tag_prefix, slot_count=12):
        """Compact 2-row attribute pool panel (12 slots = 2 rows × 6 cols)."""
        _COLS = self._POOL_COLS
        _ROWS = slot_count // _COLS
        _H    = 26 + _ROWS * (self._BTN_H + 4)   # header + rows
        with dpg.child_window(tag=f"pool_{tag_prefix}", width=self._PANEL_W,
                              height=_H, border=True,
                              no_scrollbar=True, no_scroll_with_mouse=True):
            dpg.add_text(attr_name, color=color)
            dpg.add_separator()
            for row in range(_ROWS):
                with dpg.group(horizontal=True):
                    for col in range(_COLS):
                        n = row * _COLS + col + 1
                        dpg.add_button(
                            tag=f"{tag_prefix}_btn_{n}",
                            label=f"{attr_name[0].upper()}{n}",
                            width=self._BTN_W, height=self._BTN_H,
                            callback=self._on_attr_click,
                            user_data=(attr_name, n))
                        with dpg.tooltip(f"{tag_prefix}_btn_{n}"):
                            dpg.add_text(f"{attr_name.title()} {n}",
                                         tag=f"{tag_prefix}_tip_{n}")

    # ── Attribute pools popup ────────────────────────────────
    # Position/gobo/zoom/focus/beam panels used to live in the main pools
    # row but were pulled out (see _build_pools_row) because a 5th stacked
    # row pushed the main window past the 1920x1080 budget. The panels
    # themselves (_build_attr_pool_panel) and their live tick/click wiring
    # (_tick_pools, _on_attr_click) were already correct and untouched —
    # this just gives them a floating home, same pattern as the MIDI and
    # executor-pages popups.

    def _build_attr_popup(self):
        """Floating attribute pool panel — hidden by default, opened via header button."""
        with dpg.window(tag="attr_window", label="Attribute Pools",
                        width=1902, height=290, show=False,
                        pos=(10, 80), no_collapse=False):
            dpg.add_text("position / gobo / zoom / focus / beam / control", color=_C_ACCENT)
            dpg.add_text("Moving-light attributes — not used by the 6 LT-200 pixel tubes "
                         "in this rig, but recalled the same way as color/dim presets "
                         "for any fixture patched with these channels.", color=_C_DIM, wrap=1860)
            dpg.add_separator()
            with dpg.group(horizontal=True):
                self._build_attr_pool_panel("position", _C_P_POSITION, "pos")
                self._build_attr_pool_panel("gobo",     _C_P_GOBO,  "gobo")
                self._build_attr_pool_panel("zoom",     _C_P_ZOOM,  "zoom")
            with dpg.group(horizontal=True):
                self._build_attr_pool_panel("focus",    _C_P_FOCUS,    "focus")
                self._build_attr_pool_panel("beam",     _C_P_BEAM,     "beam")
                self._build_attr_pool_panel("control",  _C_P_CONTROL,  "ctrl")

    def _build_forms_panel(self):
        # Spans the same width as the 3 pool panels above (3 × _PANEL_W).
        # BTN_W: (3×PANEL_W - 2×1border - 2×8WP_X - 11×6IS_X) / 12
        _FORMS_COLS  = 12
        _PANEL_TOTAL = 3 * self._PANEL_W           # 1902px
        _FORMS_BTN_W = (_PANEL_TOTAL - 2 - 16 - (_FORMS_COLS - 1) * 6) // _FORMS_COLS
        _FORMS_H     = 32 + 2 * (self._BTN_H + 4) # header + 2 button rows
        with dpg.child_window(tag="pool_forms", width=_PANEL_TOTAL,
                              height=_FORMS_H, border=True,
                              no_scrollbar=True, no_scroll_with_mouse=True):
            dpg.add_text("forms", color=_C_P_FORMS)
            dpg.add_separator()
            for row in range(2):
                with dpg.group(horizontal=True):
                    for col in range(_FORMS_COLS):
                        n = row * _FORMS_COLS + col + 1
                        dpg.add_button(
                            tag=f"form_btn_{n}", label=f"F{n}",
                            width=_FORMS_BTN_W, height=self._BTN_H,
                            callback=self._on_form_click, user_data=n)

    def _on_fx_click(self, _sender, _app_data, user_data):
        n = user_data
        if self._fx_pool and self._fx_pool.get(n):
            result = self._cmd(f"FIRE FX {n}") if self._cmd else None
            preset = self._fx_pool.get(n)
            self._log(f"> FX {n} — {preset.name}")
            if result:
                self._log(f"  {result}")
            # If the FX editor is open, sync it to this slot
            try:
                if dpg.get_item_configuration("fx_editor_window").get("show", False):
                    self._fxed_select_slot(None, None, n)
            except Exception:
                pass
        else:
            self._log(f"> FX {n} is empty — open FX ED to build a preset")
        self._focus_cmd()

    def _on_clear_fx(self, *_):
        result = self._cmd("CLEAR FX") if self._cmd else None
        self._log("> CLEAR FX")
        if result:
            self._log(f"  {result}")
        self._focus_cmd()

    def _on_attr_click(self, _sender, _app_data, user_data):
        attr_name, n = user_data
        pool = self._attr_pools.get(attr_name) if self._attr_pools else None
        if pool and pool.get(n):
            if self._cmd:
                result = self._cmd(f"{attr_name.upper()} {n}")
                if result:
                    self._log(f"  {result}")
            self._log(f"> {attr_name.upper()} {n} — {pool.get(n).name}")
        else:
            self._log(f"> {attr_name.upper()} {n} is empty")
            self._log(f"  To record: set value in programmer, then  RECORD {attr_name.upper()} {n} Name")
        self._focus_cmd()

    def _on_form_click(self, _sender, _app_data, user_data):
        n = user_data
        if self._form_pool and self._form_pool.get(n):
            form = self._form_pool.get(n)
            self._log(f"> FORM {n} — {form.name}  ({form.form_type})")
            if self._cmd:
                result = self._cmd(f"FX FORM {n}")
                if result:
                    self._log(f"  {result}")
        else:
            self._log(f"> FORM {n} is empty")
            if n < FormPool.FIRST_CUSTOM_SLOT:
                self._log(f"  Slots 1-4 are built-ins (sine/ramp/pulse/square)")
            else:
                self._log(f"  To record: RECORD FORM {n} Name 0.0,0.0 0.5,1.0 1.0,0.0")
        self._focus_cmd()

    def _tick_pools(self):
        """Update pool button labels to show occupied/empty state."""
        for n in range(1, self._POOL_SLOTS + 1):
            # Groups
            g = self._groups.get(n) if self._groups else None
            lbl = f"{n}:{g.name[:7]}" if g else f"G{n}"
            try:
                dpg.set_item_label(f"grp_btn_{n}", lbl)
            except Exception:
                pass
            try:
                if g and self._patch:
                    members = g.recall(self._patch)
                    tip = f"Group {n}: {g.name}\n{len(members)} fixture(s)"
                else:
                    tip = f"Group {n} — empty"
                dpg.set_value(f"grp_tip_{n}", tip)
            except Exception:
                pass
            # Colors
            c = self._colors.get(n) if self._colors else None
            lbl = f"{n}:{c.name[:7]}" if c else f"C{n}"
            try:
                dpg.set_item_label(f"col_btn_{n}", lbl)
            except Exception:
                pass
            # Tint the color button with the preset's actual color
            if c:
                r, g, b = int(c.red), int(c.green), int(c.blue)
                cached = self._col_btn_themes.get(n)
                if cached is None or cached[0] != (r, g, b):
                    if cached:
                        try:
                            dpg.delete_item(cached[1])
                        except Exception:
                            pass
                    try:
                        with dpg.theme() as _cth:
                            with dpg.theme_component(dpg.mvButton):
                                dpg.add_theme_color(dpg.mvThemeCol_Button,
                                                    (max(20, r//3), max(20, g//3), max(20, b//3), 255))
                                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered,
                                                    (min(255, r*2//3+20), min(255, g*2//3+20), min(255, b*2//3+20), 255))
                                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,
                                                    (r, g, b, 255))
                        dpg.bind_item_theme(f"col_btn_{n}", _cth)
                        self._col_btn_themes[n] = ((r, g, b), _cth)
                    except Exception:
                        pass
            elif n in self._col_btn_themes:
                # Preset deleted — remove custom theme, revert to default
                try:
                    dpg.bind_item_theme(f"col_btn_{n}", 0)
                    dpg.delete_item(self._col_btn_themes[n][1])
                except Exception:
                    pass
                del self._col_btn_themes[n]
            # Dims
            d = self._dims.get(n) if self._dims else None
            lbl = f"{n}:{d.name[:7]}" if d else f"D{n}"
            try:
                dpg.set_item_label(f"dim_btn_{n}", lbl)
            except Exception:
                pass
            try:
                tip = (f"Dim {n}: {d.name}  {d.level*100:.0f}%") if d else f"Dim {n} — empty"
                dpg.set_value(f"dim_tip_{n}", tip)
            except Exception:
                pass
            # Tint the dim button with a brightness-scaled grey
            if d:
                lv = max(0.05, float(d.level))
                cached = self._dim_btn_themes.get(n)
                if cached is None or abs(cached[0] - lv) > 0.01:
                    if cached:
                        try:
                            dpg.delete_item(cached[1])
                        except Exception:
                            pass
                    try:
                        br   = int(lv * 180)
                        brH  = min(255, int(lv * 255))
                        with dpg.theme() as _dth:
                            with dpg.theme_component(dpg.mvButton):
                                # violet-tinted brightness scale: dark resting → vivid violet active
                                dpg.add_theme_color(dpg.mvThemeCol_Button,
                                                    (br//5, br//6, br//2, 255))
                                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered,
                                                    (brH//3, brH//5, brH, 255))
                                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,
                                                    (min(220, int(brH*0.85)), min(180, int(brH*0.55)), 255, 255))
                        dpg.bind_item_theme(f"dim_btn_{n}", _dth)
                        self._dim_btn_themes[n] = (lv, _dth)
                    except Exception:
                        pass
            elif n in self._dim_btn_themes:
                try:
                    dpg.bind_item_theme(f"dim_btn_{n}", 0)
                    dpg.delete_item(self._dim_btn_themes[n][1])
                except Exception:
                    pass
                del self._dim_btn_themes[n]

        # Cuestacks (slots 1-48)
        active = self._active_executor[0] if self._active_executor else None
        for n in range(1, self._POOL_SLOTS + 1):
            cs = self._cuestack_pool.get(n) if self._cuestack_pool else None
            lbl = f"{n}:{cs.name[:5]}" if cs else f"CS{n}"
            try:
                dpg.set_item_label(f"cs_btn_{n}", lbl)
            except Exception:
                pass

        # Cues (slots 1-48, from the active cuestack)
        active_cs = None
        if self._cuestack_pool and self._active_executor:
            active_cs = self._cuestack_pool.get(self._active_executor[0])
        current_cue = active_cs.current if active_cs else None
        for n in range(1, self._POOL_SLOTS + 1):
            cue = active_cs.cues.get(float(n)) if active_cs else None
            if cue:
                lbl = f"{n}:{cue.name[:5]}" + (" ◀" if n == current_cue else "")
                ft_s  = f"  fade {cue.fade_time}s" if cue.fade_time  else ""
                dt_s  = f"  delay {cue.delay_time}s" if cue.delay_time else ""
                nfx   = len(cue.data.get('__fx__', [])) if hasattr(cue, 'data') and isinstance(cue.data, dict) else 0
                nfix  = sum(1 for k in getattr(cue, 'data', {}) if not k.startswith('__') and '.' not in k) if hasattr(cue, 'data') else 0
                fix_s = f"\n{nfix} fixture(s)" if nfix else ""
                tip   = f"Cue {n}: {cue.name}{ft_s}{dt_s}{fix_s}"
            else:
                lbl = f"{n}"
                tip = f"Cue {n} — empty"
            try:
                dpg.set_item_label(f"cue_btn_{n}", lbl)
                dpg.configure_item(f"cue_tip_{n}", default_value=tip)
            except Exception:
                pass

        # FX Pool (slots 1-48)
        for n in range(1, self._POOL_SLOTS + 1):
            p = self._fx_pool.get(n) if self._fx_pool else None
            lbl = f"{n}:{p.name[:6]}" if p else f"FX{n}"
            try:
                dpg.set_item_label(f"fx_btn_{n}", lbl)
            except Exception:
                pass

        # Attribute pools (12 slots each)
        _ATTR_SLOTS = 12
        _ATTR_MAP = [
            ("position", "pos"), ("gobo", "gobo"), ("zoom", "zoom"),
            ("focus", "focus"), ("beam", "beam"), ("control", "ctrl"),
        ]
        for attr_name, pfx in _ATTR_MAP:
            pool = self._attr_pools.get(attr_name) if self._attr_pools else None
            for n in range(1, _ATTR_SLOTS + 1):
                p = pool.get(n) if pool else None
                lbl = f"{n}:{p.name[:6]}" if p else f"{pfx[0].upper()}{n}"
                try:
                    dpg.set_item_label(f"{pfx}_btn_{n}", lbl)
                    tip = f"{attr_name.title()} {n}: {p.name}" if p else f"{attr_name.title()} {n} — empty"
                    dpg.set_value(f"{pfx}_tip_{n}", tip)
                except Exception:
                    pass

        # Forms (slots 1-24, matches _POOL_SLOTS)
        for n in range(1, self._POOL_SLOTS + 1):
            f = self._form_pool.get(n) if self._form_pool else None
            lbl = f"{n}:{f.name[:6]}" if f else f"F{n}"
            try:
                dpg.set_item_label(f"form_btn_{n}", lbl)
            except Exception:
                pass

        # FX pool programmer summary
        self._tick_fx_prog_summary()

    def _tick_fx_prog_summary(self):
        """Update the programmer FX summary text in the FX pool panel."""
        if not self._prog:
            return

        fx_parts   = []
        color_seen = {}  # ref_id → name (deduplicated across fixtures)
        dim_seen   = {}

        for master in self._patch.all_fixtures():
            fid    = str(master.fixture_id)
            m_data = self._prog.data.get(fid, {})

            for ld in m_data.get('fx', []):
                if ld.get('form_id') and self._form_pool:
                    frm  = self._form_pool.get(ld['form_id'])
                    wave = f"F{ld['form_id']}:{frm.name[:5]}" if frm else f"F{ld['form_id']}"
                else:
                    wave = ld.get('waveform', '?')[:4]
                ch = ld.get('channel', '?')[:1].upper()

                if ld.get('rate_id') and self._rate_pool:
                    rp    = self._rate_pool.get(ld['rate_id'])
                    bpm_s = f"R{ld['rate_id']}:{rp.bpm:.0f}" if rp else f"R{ld['rate_id']}"
                else:
                    bpm_s = f"{ld.get('bpm', 60):.0f}♩"

                if ld.get('size_id') and self._size_pool:
                    sp   = self._size_pool.get(ld['size_id'])
                    sz_s = f"S{ld['size_id']}:{sp.size:.0f}" if sp else f"S{ld['size_id']}"
                else:
                    sz_s = f"sz{ld.get('size', 200):.0f}"

                fx_parts.append(f"{wave}/{ch} {bpm_s} {sz_s}")

            c_ref = m_data.get('color_ref')
            if c_ref and self._colors:
                p = self._colors.get(c_ref)
                color_seen[c_ref] = p.name if p else f"C{c_ref}"

            d_ref = m_data.get('dim_ref')
            if d_ref and self._dims:
                p = self._dims.get(d_ref)
                dim_seen[d_ref] = p.name if p else f"D{d_ref}"

        # FX line — deduplicate identical layers
        seen_fx = []
        for part in fx_parts:
            if part not in seen_fx:
                seen_fx.append(part)
        fx_summary = "  |  ".join(seen_fx) if seen_fx else "— no FX in programmer"

        # Color / dim line
        color_str = "  ".join(f"C{rid}:{name}" for rid, name in color_seen.items())
        dim_str   = "  ".join(f"D{rid}:{name}" for rid, name in dim_seen.items())
        other_str = "  ".join(filter(None, [color_str, dim_str]))

        try:
            dpg.set_value("fx_prog_summary", fx_summary)
            dpg.configure_item("fx_prog_summary",
                               color=_C_ACCENT if seen_fx else _C_DIM)
            dpg.set_value("fx_prog_other", other_str)
            dpg.configure_item("fx_prog_other",
                               color=_C_DIM if not other_str else (180, 180, 140, 255))
        except Exception:
            pass

    def _build_midi_popup(self):
        """Floating MIDI mapping window — hidden by default, opened via header button."""
        with dpg.window(tag="midi_window", label="midi mappings",
                        width=700, height=420, show=False,
                        pos=(200, 150), no_collapse=False):
            dpg.add_text("midi mappings", color=_C_ACCENT)
            dpg.add_separator()

            with dpg.table(tag="midi_table", header_row=True,
                           borders_innerH=True, borders_outerH=True,
                           borders_innerV=True, borders_outerV=True,
                           row_background=True, scrollY=True,
                           height=200):
                dpg.add_table_column(label="ch",      width_fixed=True, init_width_or_weight=32)
                dpg.add_table_column(label="cc/note", width_fixed=True, init_width_or_weight=65)
                dpg.add_table_column(label="Type",    width_fixed=True, init_width_or_weight=45)
                dpg.add_table_column(label="Name",    width_stretch=True)
                dpg.add_table_column(label="Status",  width_fixed=True, init_width_or_weight=90)
                dpg.add_table_column(label="del",     width_fixed=True, init_width_or_weight=36)
                dpg.add_table_column(label="rsn",     width_fixed=True, init_width_or_weight=36)

            self._refresh_midi_table()

            # Reassign panel — activated when user clicks ► on a row
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_text("reassign:", color=_C_DIM)
                dpg.add_text("select a row →", tag="rsn_selected", color=_C_DIM)
                target_names = list(self.target_registry.keys())
                dpg.add_combo(items=target_names, tag="rsn_target",
                              default_value=target_names[0] if target_names else "",
                              width=230)
                dpg.add_button(label="apply", width=70,
                               callback=self._on_apply_reassign)

            dpg.add_separator()
            dpg.add_text("Add mapping:", color=_C_DIM)
            with dpg.group(horizontal=True):
                dpg.add_radio_button(items=["CC", "Note"],
                                     tag="learn_type_radio",
                                     default_value="CC",
                                     horizontal=True,
                                     callback=self._on_learn_type_change)
                dpg.add_button(label="learn", tag="learn_btn",
                               callback=self._toggle_learn)
                dpg.add_text("", tag="learn_status", color=_C_ACCENT)

            target_names = list(self.target_registry.keys())
            dpg.add_combo(items=target_names,
                          tag="learn_target",
                          default_value=target_names[0] if target_names else "",
                          width=300)
            dpg.add_text("Click LEARN, then move the control (CC) or press a key/pad (Note).", color=_C_DIM)

            dpg.add_separator()
            dpg.add_text("go directly to a cue via note:", color=_C_DIM)
            with dpg.group(horizontal=True):
                dpg.add_text("cs", color=_C_DIM)
                dpg.add_input_int(tag="midi_go_cs",  label="", width=46,
                                  default_value=1, min_value=1, max_value=16,
                                  step=0, step_fast=0)
                dpg.add_text("cue", color=_C_DIM)
                dpg.add_input_float(tag="midi_go_cue", label="", width=52,
                                    default_value=1, min_value=1, max_value=9999,
                                    step=0, format="%.0f")
                dpg.add_button(label="learn note", width=100,
                               callback=self._start_go_cue_learn)
                dpg.add_text("", tag="go_cue_status", color=_C_ACCENT)

            dpg.add_separator()
            dpg.add_text("flash an executor while a pad is held:", color=_C_DIM)
            with dpg.group(horizontal=True):
                dpg.add_text("exec", color=_C_DIM)
                dpg.add_input_int(tag="midi_flash_exec", label="", width=46,
                                  default_value=1, min_value=1, max_value=99,
                                  step=0, step_fast=0)
                dpg.add_button(label="learn note", width=100,
                               callback=self._start_exec_flash_learn)
                dpg.add_text("", tag="flash_learn_status", color=_C_ACCENT)

    def _build_patch_popup(self):
        """Floating patch editor — hidden by default, opened via header PATCH button."""
        profiles = list(self._library.profiles.keys()) if self._library else ["SGM_RGB_54"]
        with dpg.window(tag="patch_window", label="Patch Editor",
                        width=780, height=460, show=False,
                        pos=(160, 120), no_collapse=False):
            dpg.add_text("patch editor", color=_C_ACCENT)
            dpg.add_separator()

            # ── Current patch table ───────────────────────────
            with dpg.table(tag="patch_table", header_row=True,
                           borders_innerH=True, borders_outerH=True,
                           borders_innerV=True, borders_outerV=True,
                           row_background=True, scrollY=True, height=220):
                dpg.add_table_column(label="id",       width_fixed=True,  init_width_or_weight=36)
                dpg.add_table_column(label="Name",     width_fixed=True,  init_width_or_weight=110)
                dpg.add_table_column(label="Profile",  width_fixed=True,  init_width_or_weight=130)
                dpg.add_table_column(label="Univ",     width_fixed=True,  init_width_or_weight=44)
                dpg.add_table_column(label="Start",    width_fixed=True,  init_width_or_weight=52)
                dpg.add_table_column(label="Channels", width_fixed=True,  init_width_or_weight=70)
                dpg.add_table_column(label="End",      width_fixed=True,  init_width_or_weight=52)
                dpg.add_table_column(label="",         width_stretch=True)

            self._refresh_patch_table()

            dpg.add_separator()
            dpg.add_text("Add fixture:", color=_C_DIM)
            with dpg.group(horizontal=True):
                dpg.add_input_int(tag="patch_add_id",    label="", width=46,
                                  default_value=1, min_value=1, max_value=999,
                                  step=0, step_fast=0)
                dpg.add_text("id", color=_C_DIM)
                dpg.add_spacer(width=4)
                dpg.add_input_text(tag="patch_add_name",  label="", width=110,
                                   default_value="Fixture")
                dpg.add_text("Name", color=_C_DIM)
                dpg.add_spacer(width=4)
                dpg.add_combo(tag="patch_add_profile", label="", width=130,
                              items=profiles,
                              default_value=profiles[0] if profiles else "")
                dpg.add_text("Profile", color=_C_DIM)
            with dpg.group(horizontal=True):
                dpg.add_input_int(tag="patch_add_univ",  label="", width=46,
                                  default_value=1, min_value=1, max_value=64,
                                  step=0, step_fast=0)
                dpg.add_text("Universe", color=_C_DIM)
                dpg.add_spacer(width=4)
                dpg.add_input_int(tag="patch_add_addr",  label="", width=60,
                                  default_value=1, min_value=1, max_value=512,
                                  step=0, step_fast=0)
                dpg.add_text("Start Addr", color=_C_DIM)
                dpg.add_spacer(width=4)
                dpg.add_input_int(tag="patch_add_clone_src", label="", width=46,
                                  default_value=0, min_value=0, max_value=999,
                                  step=0, step_fast=0)
                dpg.add_text("Clone from (0=none)", color=_C_DIM)
                dpg.add_spacer(width=8)
                dpg.add_button(label="add fixture", width=110,
                               callback=self._on_patch_add)

            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_button(label="save patch", width=110,
                               callback=self._on_patch_save)
                dpg.add_spacer(width=8)
                dpg.add_text("Changes are live. Re-open console to rebuild monitors.",
                             color=_C_DIM)

    def _refresh_patch_table(self):
        """Rebuild the rows in the patch table from the current patch state."""
        try:
            dpg.delete_item("patch_table", children_only=True, slot=1)
        except Exception:
            return
        for master in self._patch.all_fixtures():
            first_sub = next(iter(master.sub_fixtures.values()), None)
            if not first_sub or not first_sub.outputs:
                continue
            primary = first_sub.outputs[0]
            total_ch = master.profile.total_channels
            end_addr = primary["address"] + total_ch - 1
            with dpg.table_row(parent="patch_table"):
                dpg.add_text(str(master.fixture_id))
                dpg.add_text(master.name)
                dpg.add_text(master.profile.name)
                dpg.add_text(str(primary["universe"]))
                dpg.add_text(str(primary["address"]))
                dpg.add_text(str(total_ch))
                dpg.add_text(str(end_addr))
                dpg.add_button(label="Remove", width=70,
                               callback=self._on_patch_remove,
                               user_data=master.fixture_id)

    def _on_patch_add(self):
        try:
            fid        = dpg.get_value("patch_add_id")
            name       = dpg.get_value("patch_add_name").strip() or f"Fixture {fid}"
            profile    = dpg.get_value("patch_add_profile")
            universe   = dpg.get_value("patch_add_univ")
            addr       = dpg.get_value("patch_add_addr")
            clone_src  = dpg.get_value("patch_add_clone_src")
        except Exception:
            return
        if fid in self._patch.fixtures:
            self._log(f"Fixture ID {fid} already patched — remove it first")
            return
        master = self._patch.patch_fixture(fid, name, profile, universe, addr)
        if master:
            self._log(f"Patched: {master.name} (ID {fid}) — {profile} U{universe}@{addr}")
            if clone_src and clone_src != 0 and clone_src in self._patch.fixtures:
                msg = self._cmd(f"CLONE {clone_src} TO {fid}") if self._cmd else ""
                if msg:
                    self._log(msg)
            elif clone_src and clone_src != 0:
                self._log(f"  Clone src {clone_src} not in patch — skipped")
            self._refresh_patch_table()
        else:
            self._log(f"Failed to patch — check profile name '{profile}'")

    def _on_patch_remove(self, _sender, _app_data, user_data):
        fid = int(user_data)
        if fid in self._patch.fixtures:
            name = self._patch.fixtures[fid].name
            del self._patch.fixtures[fid]
            # Clear any programmer data for this fixture
            fid_str = str(fid)
            self._prog.data.pop(fid_str, None)
            keys_to_del = [k for k in self._prog.data if k.startswith(fid_str + '.')]
            for k in keys_to_del:
                del self._prog.data[k]
            self._log(f"Removed: {name} (ID {fid})")
            self._refresh_patch_table()

    def _on_patch_save(self):
        if self._save_patch:
            self._save_patch()
            self._log("> Patch saved to patch.json")
        else:
            self._log("> No save_patch_fn wired")

    def _build_keys_popup(self):
        """Floating keyboard / command reference — hidden by default, opened via ? button."""

        _S = [  # (section_title, [(command, description), ...])
            ("SELECTION", [
                ("1",                     "Select fixture 1"),
                ("1 THRU 6",              "Select fixtures 1 through 6"),
                ("GRP 1  /  GROUP 1",     "Recall group (expands to all member fixtures)"),
                ("1 + 3 + 5",             "Select multiple individual fixtures"),
            ]),
            ("COLOUR & DIM", [
                ("1 THRU 6 R 255",        "Set red channel (0–255)"),
                ("1 THRU 6 G 128 B 64",   "Set green and blue together"),
                ("1 AT FULL",             "Full brightness (dim = 1.0)"),
                ("1 AT OUT",              "Output off (dim = 0.0)"),
                ("1 AT DIM 75",           "Dim to 75%"),
                ("COL 3  /  COLOR 3",     "Apply colour preset to selection"),
                ("DIM 2",                 "Apply dim preset to selection"),
            ]),
            ("fx", [
                ("FX SINE RED",           "Sine wave on red channel"),
                ("FX RAMP GREEN BPM 60",  "Ramp wave, 60 BPM"),
                ("FX SINE RED SIZE 100",  "Specify amplitude (0–100)"),
                ("FX SINE RED SPREAD 50", "Phase spread across fixtures (0–100)"),
                ("FX SINE RED PHASE 0.33","Phase offset for this layer (0–1)"),
                ("FX SINE RED BLOCK 3",   "Chase in blocks of 3 adjacent targets"),
                ("FX SINE DIM ORDER RANDOM", "Shuffle chase order (stable per effect)"),
                ("FX RAMP RED DIRECTION BOUNCE", "Sweep out across targets, then back"),
                ("FX SINE RED DIRECTION REVERSE", "Chase back-to-front"),
                ("FX SINE RED PIXEL",     "Force per-pixel scope (crosses tube boundaries)"),
                ("FX SINE DIM FIXTURE",   "Force whole-fixture scope (steps by whole tube)"),
                ("BPM 60",                "Set global BPM (live + programmer)"),
                ("SIZE 100",              "Set global FX size (0–100)"),
                ("SPREAD 50",             "Set global FX spread (0–100)"),
                ("FX FORM 5",             "Set waveform to Form Pool slot 5"),
                ("FX COLOR 3",            "Drive R/G/B from Color Preset 3 (sine default)"),
                ("FX RAMP COLOR 3",       "Ramp waveform toward Color Preset 3's hue"),
                ("FX SINE RED GROUP 2",   "Sine red on Group 2 fixtures only"),
                ("FX SINE RED DIMREF 1",  "Size ceiling: live from Dim Preset 1's level"),
                ("FIRE FX 3",             "Load FX preset 3 into programmer"),
                ("FIRE FX 3 GROUP 2",     "Fire preset 3, override target to group 2"),
                ("FX LIST",               "Show all programmer FX defs + pool contents"),
                ("FX CLEAR RED",          "Clear red-channel FX from programmer"),
                ("CLEAR FX",              "Clear all FX from programmer (keep colour/dim)"),
                ("KILL FX",               "Stop all running FX immediately"),
            ]),
            ("LIST / INSPECT", [
                ("CUES / STACK / LIST",   "Show all cues in active cuestack with fade times"),
                ("LIST CUESTACKS",        "List all recorded cuestacks and cue counts"),
                ("LIST COLOR",            "List all color presets with RGB sample"),
                ("LIST DIM",              "List all dim presets with level"),
                ("LIST GROUP",            "List all groups and member counts"),
                ("LIST FX",               "List all FX presets with waveform/channel"),
                ("LIST RATE / SIZE / SPREAD / FORM", "List pool presets"),
                ("FX LIST",               "Show active programmer/executor FX layers"),
                ("PAGE LIST",             "Show all pages and cuestacks on each"),
            ]),
            ("RECORD", [
                ("REC CUE 5",             "Record current programmer to cue 5"),
                ("REC CUE 5 My Cue",      "Record with a name"),
                ("REC FX 2 My FX",        "Record programmer FX to FX pool slot 2"),
                ("REC GROUP 3 Name",      "Record current selection as group 3"),
                ("RECORD COLOR 4 Red",    "Record programmer colour as preset 4"),
                ("RECORD DIM 2 Half",     "Record programmer dim as preset 2"),
                ("RECORD FORM 6 Wave 0,0 0.5,1 1,0",  "Record custom waveform"),
                ("RECORD RATE 3 Name 120","Record 120 BPM to rate pool slot 3"),
                ("RECORD CUESTACK 2 Name","Create a new named cuestack on executor 2"),
            ]),
            ("RENAME / COPY / DELETE", [
                ("RENAME CUESTACK 2 Tour","Rename cuestack 2 — all cues kept"),
                ("RENAME CUE 3 Intro",    "Rename cue 3 in active cuestack"),
                ("RENAME CS 2 CUE 5 End", "Rename cue 5 in cuestack 2"),
                ("RENAME COLOR 4 Coral",  "Rename colour preset 4"),
                ("RENAME GROUP 1 Tubes",  "Rename group 1"),
                ("COPY CUE 3 TO 5",       "Copy cue 3 → cue 5 (active cuestack)"),
                ("COPY CUE 3 TO 5 Intro", "Copy with new name"),
                ("COPY CS 2 CUE 3 TO CS 1 CUE 9", "Cross-cuestack copy"),
                ("DELETE CUE 3",          "Delete cue 3 from active cuestack (saves show)"),
                ("DELETE CUE 3 CS 2",     "Delete cue 3 from cuestack 2"),
                ("CLEAR COLOR 4",         "Delete colour preset 4 from the pool (saves show)"),
                ("CLEAR DIM 2",           "Delete dim preset 2 from the pool (saves show)"),
                ("CLEAR GROUP 1",         "Delete group 1 from the pool (saves show)"),
                ("CLEAR FX 3",            "Delete FX preset 3 from the pool (saves show)"),
                ("CUE 5 SHOW",            "Inspect cue 5 contents (fixtures, RGB, FX, timing)"),
                ("CUE 5 FADE 3",          "Set fade time on cue 5 (no programmer needed)"),
                ("CUE 5 FADE 2 DELAY 1",  "Set fade + delay"),
                ("CUE 5 FADE 2 DFADE 5",  "Global fade + dim-only fade override"),
                ("CS 2 CUE 5 FADE 3",     "Set timing on cue 5 in cuestack 2"),
            ]),
            ("PLAYBACK", [
                ("GO",                    "Advance to next cue on active executor"),
                ("BACK",                  "Step to previous cue"),
                ("GOTO 3",                "Jump directly to cue 3 (active cuestack)"),
                ("CUESTACK 2",            "Switch active executor to slot 2"),
                ("ASSIGN CS 2 TO EXEC 1", "Wire cuestack 2 to executor 1"),
                ("RELEASE 2",             "Stop executor 2"),
                ("RELEASE ALL",           "Stop all active executors"),
                ("PRIORITY 2 HIGH",       "Set executor 2 to high priority (HI/NRM/LO)"),
                ("EXEC 1 TIME 3",         "Override fade time on executor 1 to 3s"),
                ("EXEC 1 TIME 3 DELAY 1", "Override fade + delay on executor 1"),
                ("EXEC 1 TIME OFF",       "Remove executor 1 time override"),
                ("EXEC 1 TIMELOCK OFF",   "Lock cuestack on exec 1 to its own times"),
                ("EXEC 1 TIMELOCK ON",    "Re-enable executor time override for cuestack"),
                ("PROG TIME 2",           "Programmer time: all cues fade at 2s"),
                ("PROG TIME OFF",         "Disable programmer time override"),
            ]),
            ("EXECUTORS & PAGES", [
                ("EXEC 1 GO / BACK / STOP", "Direct executor control"),
                ("EXEC 1 LEVEL 75",       "Set executor master fader to 75% (GUI slider also works)"),
                ("EXEC 1 MODE FLASH",     "Set trigger mode: live only while held"),
                ("EXEC 1 MODE TOGGLE",    "Set trigger mode: GO/BACK advance (default)"),
                ("EXEC 1 FLASH ON",       "Fire instantly (0s), works regardless of mode"),
                ("EXEC 1 FLASH OFF",      "Release a flash — fully stops the executor"),
                ("PAGE 1 NAME Verses",    "Name page 1"),
                ("PAGE 1 ADD CS 3",       "Add cuestack 3 to page 1"),
                ("PAGE 1 REMOVE CS 3",    "Remove cuestack 3 from page 1"),
                ("PAGE 1 DELETE",         "Delete page 1"),
                ("PAGE LIST",             "List all pages and their cuestacks"),
                ("PAGES button",          "Same page commands via a GUI table — no typing needed"),
            ]),
            ("ATTRIBUTE POOLS", [
                ("RECORD POSITION 1 Wide", "Snapshot pan/tilt from programmer into slot 1"),
                ("POSITION 1",            "Apply position preset 1 to programmer"),
                ("RECORD GOBO 1 / GOBO 1", "Same pattern for gobo, zoom, focus, beam, control"),
                ("attr button",           "Open the position/gobo/zoom/focus/beam GUI panels"),
            ]),
            ("programmer", [
                ("CLEAR",                 "Clear selection (tap 1) then programmer (tap 2)"),
                ("CLEAR FX",              "Clear only FX, keep colour/dim references"),
                ("BLIND",                 "Suppress programmer from DMX output — edit safely offline"),
                ("LIVE",                  "Re-enable programmer in DMX output (cancel BLIND)"),
                ("BLACKOUT",              "Cut all DMX output instantly (BLACKOUT OFF to restore)"),
                ("BLACKOUT OFF  / BBO",   "Same as BLACKOUT — BBO is a one-key shorthand"),
                ("SNAPSHOT 5",            "Record current live look (cue+prog merged) as cue 5"),
                ("SNAPSHOT 5 Frozen",     "Snapshot with a custom name"),
                ("SAVE",                  "Save entire show to studio_data/"),
                ("SAVE AS <name>",        "Save a named snapshot to studio_saves/<name>/"),
                ("LOAD SHOW <name>",      "Restore a snapshot (cuestacks/presets reload live)"),
                ("LIST SHOWS",            "List all saved show snapshots"),
                ("UNDO",                  "Undo last programmer change (up to 20 steps)"),
                ("EXPORT PRESETS",        "Bundle colors/dims/fx/forms to preset_export_YYYYMMDD.json"),
                ("EXPORT PRESETS colors", "Export only color presets"),
                ("IMPORT PRESETS <file>", "Merge a preset bundle JSON into live pools"),
                ("CLONE 1 TO 7",          "Copy fixture 1's presets / cue data to fixture 7"),
                ("CLONE 1 TO 7 THRU 9",   "Clone to a range of destinations"),
            ]),
            ("OSC", [
                ("OSC TARGET name host port", "Add an OSC output target"),
                ("OSC REMOVE name",        "Remove a named OSC target"),
                ("OSC LIST",               "Show all targets"),
                ("OSC SEND /gma3/cmd GOTO_CUE_1", "Manually send an OSC message"),
                ("OSC MONITOR",            "Print incoming OSC for 10 s (port 8001)"),
                ("OSC FEEDBACK host port", "Broadcast console state at 1 Hz (/studio/...)"),
                ("OSC FEEDBACK",           "Disable state feedback"),
            ]),
            ("MIDI CLOCK", [
                ("MIDI CLOCK ON",  "Lock FX BPM to incoming MIDI beat clock (24 ppqn); shows CLK in header"),
                ("MIDI CLOCK OFF", "Disable MIDI clock sync; FX BPM returns to manual control"),
            ]),
            ("KEYBOARD", [
                ("↑  /  ↓",               "Scroll command history (up/down arrows)"),
                ("Enter",                 "Execute command"),
                ("Delete",                "Clear selection"),
                ("F5",                    "GO — advance to next cue"),
                ("F4",                    "BACK — step to previous cue"),
                ("Cmd/Ctrl + S",          "Save show"),
                ("tap button (FX panel)", "Set BPM from tap intervals (auto-resets after 3s)"),
                ("MIDI button",           "Open MIDI mapping editor"),
                ("PATCH button",          "Open patch editor"),
                ("PAGES button",          "Open pages editor (assign cuestacks to pages)"),
                ("attr button",           "Open the attribute pools (position/gobo/zoom/focus/beam)"),
            ]),
        ]

        with dpg.window(tag="keys_window", label="Keyboard & Command Reference (manual)",
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
                                dpg.add_text(cmd,  color=_C_TEXT)
                                dpg.add_text(desc, color=_C_DIM)
                    dpg.add_spacer(height=6)

    # ── Changelog popup ──────────────────────────────────────────
    # Reads studio_data/changelog.json — the log gets an entry appended for
    # every meaningful change made to this file, so this is a live view of
    # what's changed and why, not something maintained by hand in the GUI.

    def _build_changelog_popup(self):
        """Floating changelog viewer — hidden by default, opened via 'log' button."""
        with dpg.window(tag="changelog_window", label="Changelog",
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

    # ── Executor Pages popup ─────────────────────────────────────
    # Pages group executor slots for navigation/display only — the
    # ExecutorPool.pages dict and the PAGE <n> [NAME|ADD|REMOVE] commands
    # already existed, but only via the command line. This is the GUI
    # front-end for that same data, same pattern as the MIDI mapping popup.

    def _build_pages_popup(self):
        """Floating pages editor — assign cuestacks to named pages."""
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
                                   hint="page name", default_value="Page 1")
                dpg.add_button(label="rename", width=70,
                               callback=self._on_page_rename)
                dpg.add_spacer(width=6)
                dpg.add_button(label="new page", width=80,
                               callback=self._on_page_new)
                dpg.add_spacer(width=4)
                dpg.add_button(label="del page", width=80,
                               callback=self._on_page_delete)

            dpg.add_separator()

            # ── Cuestack list for selected page ──────────────────
            dpg.add_text("cuestacks on this page:", color=_C_DIM)
            with dpg.child_window(tag="pg_cs_list", width=-1, height=210,
                                  border=True, no_scrollbar=False):
                dpg.add_group(tag="pg_cs_rows")   # rows rebuilt by _refresh_pages_table

            dpg.add_separator()

            # ── Add cuestack row ─────────────────────────────────
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
        """Return list of 'ID — Name' strings for all cuestacks in the pool."""
        if not self._cuestack_pool:
            return []
        items = []
        for sid in sorted(self._cuestack_pool.stacks.keys()):
            cs = self._cuestack_pool.stacks[sid]
            items.append(f"{sid} — {cs.name}")
        return items

    def _refresh_pages_table(self):
        """Rebuild the cuestack list for the currently selected page."""
        try:
            dpg.delete_item("pg_cs_rows", children_only=True)
        except Exception:
            return
        if not self._executor_pool:
            return

        n    = self._pages_current
        page = self._executor_pool.pages.get(n)
        if not page:
            dpg.add_text("(page not created yet — add a cuestack to create it)",
                         parent="pg_cs_rows", color=_C_DIM)
            return

        cs_ids = page.get('cuestacks', [])
        if not cs_ids:
            dpg.add_text("— no cuestacks on this page —",
                         parent="pg_cs_rows", color=_C_DIM)
            return

        for cs_id in cs_ids:
            cs   = self._cuestack_pool.get(cs_id) if self._cuestack_pool else None
            lbl  = f"{cs_id} — {cs.name}" if cs else f"{cs_id} — (not found)"
            with dpg.group(horizontal=True, parent="pg_cs_rows"):
                dpg.add_button(label="×", width=24,
                               callback=lambda s, a, u: self._on_page_remove_cs(u),
                               user_data=cs_id)
                dpg.add_text(lbl)

        # Refresh the page-name field to match loaded data
        try:
            dpg.set_value("pg_name_input", page.get('name', f"Page {n}"))
        except Exception:
            pass

    def _on_page_sel_change(self):
        self._pages_current = int(dpg.get_value("pg_sel_num"))
        page = self._executor_pool.pages.get(self._pages_current) if self._executor_pool else None
        try:
            dpg.set_value("pg_name_input",
                          page['name'] if page else f"Page {self._pages_current}")
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
        self._log(f"> Page {n} renamed to '{name}'")

    def _on_page_new(self):
        # Find next unused page number
        existing = set(self._executor_pool.all_pages()) if self._executor_pool else set()
        n = 1
        while n in existing:
            n += 1
        if self._executor_pool:
            self._executor_pool.get_page(n)   # creates it
            ShowFile.save_executor_pages(self._executor_pool)
        self._pages_current = n
        try:
            dpg.set_value("pg_sel_num", n)
            dpg.set_value("pg_name_input", f"Page {n}")
        except Exception:
            pass
        self._refresh_pages_table()
        self._log(f"> Page {n} created")

    def _on_page_delete(self):
        n = self._pages_current
        if self._cmd:
            self._cmd(f"PAGE {n} DELETE")
        self._log(f"> Page {n} deleted")
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
            result = self._cmd(f"PAGE {n} ADD CS {cs_id}")
            if result:
                self._log(f"  {result}")
        self._refresh_pages_table()

    def _on_page_remove_cs(self, cs_id):
        n = self._pages_current
        if self._cmd:
            result = self._cmd(f"PAGE {n} REMOVE CS {cs_id}")
            if result:
                self._log(f"  {result}")
        self._refresh_pages_table()

    # ── FX Editor popup ────────────────────────────────────────

    _FX_WAVEFORMS = ['sine', 'ramp', 'pulse', 'square', 'triangle', 'sawtooth', 'flicker']
    _FX_CHANNELS  = ['red', 'green', 'blue', 'dim']

    def _build_fx_editor_popup(self):
        """Floating FX preset editor — hidden by default, opened via FX ED button."""
        self._fx_ed_slot   = None   # currently selected preset slot (int)
        self._fx_ed_layers = []     # working copy: list of layer dicts

        with dpg.window(tag="fx_editor_window", label="fx editor",
                        width=940, height=540, show=False,
                        pos=(120, 100), no_collapse=False):

            # ── Preset selector row ───────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("preset", color=_C_ACCENT)
                dpg.add_spacer(width=6)
            # Pool slots: _POOL_SLOTS in rows of 12
            for _fxed_row in range(self._POOL_SLOTS // 12):
                with dpg.group(horizontal=True):
                    for _fxed_col in range(12):
                        n = _fxed_row * 12 + _fxed_col + 1
                        dpg.add_button(tag=f"fxed_slot_{n}", label=str(n),
                                       width=36, height=22,
                                       callback=self._fxed_select_slot,
                                       user_data=n)
            with dpg.group(horizontal=True):
                dpg.add_button(label="new preset", width=100, height=22,
                               callback=self._fxed_new_preset)
                dpg.add_button(label="delete", width=70, height=22,
                               callback=self._fxed_delete_preset)

            dpg.add_separator()

            # ── Name + actions row ────────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("Name:", color=_C_DIM)
                dpg.add_input_text(tag="fxed_name", label="", width=200,
                                   default_value="")
                dpg.add_spacer(width=8)
                dpg.add_button(label="rainbow", width=90, height=22,
                               callback=self._fxed_rainbow)
                dpg.add_button(label="chase rgb", width=90, height=22,
                               callback=self._fxed_chase_rgb)
                dpg.add_spacer(width=8)
                dpg.add_button(label="save preset", width=110, height=22,
                               callback=self._fxed_save)
                dpg.add_button(label="fire", width=70, height=22,
                               callback=self._fxed_fire)

            # ── Target selector ───────────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("Target:", color=_C_DIM)
                dpg.add_combo(tag="fxed_target", label="", width=240,
                              items=["Selection", "All Fixtures"],
                              default_value="Selection")
                dpg.add_spacer(width=6)
                dpg.add_button(label="↻ GROUPS", width=90, height=22,
                               callback=self._fxed_refresh_target)

            dpg.add_separator()

            # ── Layer list ────────────────────────────────────
            dpg.add_text("Layers:", color=_C_DIM)
            with dpg.child_window(tag="fxed_layers_win",
                                  width=-1, height=270, border=True):
                # column headers
                with dpg.group(horizontal=True):
                    dpg.add_text("Waveform",    color=_C_ACCENT, indent=4)
                    dpg.add_spacer(width=66)
                    dpg.add_text("Channel",     color=_C_ACCENT)
                    dpg.add_spacer(width=48)
                    dpg.add_text("bpm",         color=_C_ACCENT)
                    dpg.add_spacer(width=38)
                    dpg.add_text("Size",        color=_C_ACCENT)
                    dpg.add_spacer(width=30)
                    dpg.add_text("Spread",      color=_C_ACCENT)
                    dpg.add_spacer(width=25)
                    dpg.add_text("Phase(0-1)",  color=_C_ACCENT)
                    dpg.add_spacer(width=18)
                    dpg.add_text("Grp",         color=_C_ACCENT)
                    dpg.add_spacer(width=30)
                    dpg.add_text("Col",         color=_C_ACCENT)
                    dpg.add_spacer(width=30)
                    dpg.add_text("Dim",         color=_C_ACCENT)
                dpg.add_separator()
                dpg.add_group(tag="fxed_layer_rows")

            dpg.add_separator()

            # ── Add layer form ────────────────────────────────
            dpg.add_text("Add Layer:", color=_C_DIM)
            with dpg.group(horizontal=True):
                dpg.add_combo(tag="fxed_add_wave",    label="", width=90,
                              items=self._FX_WAVEFORMS,
                              default_value=self._FX_WAVEFORMS[0])
                dpg.add_combo(tag="fxed_add_ch",      label="", width=70,
                              items=self._FX_CHANNELS,
                              default_value=self._FX_CHANNELS[0])
                dpg.add_text("bpm", color=_C_DIM)
                dpg.add_input_float(tag="fxed_add_bpm",    label="", width=60,
                                    default_value=60.0, min_value=1.0, max_value=999.0,
                                    step=0, format="%.1f")
                dpg.add_text("Size", color=_C_DIM)
                dpg.add_input_float(tag="fxed_add_size",   label="", width=60,
                                    default_value=100.0, min_value=0.0, max_value=100.0,
                                    step=0, format="%.0f")
                dpg.add_text("Spread", color=_C_DIM)
                dpg.add_input_float(tag="fxed_add_spread", label="", width=55,
                                    default_value=0.0, min_value=0.0, max_value=100.0,
                                    step=0, format="%.1f")
                dpg.add_text("Phase", color=_C_DIM)
                dpg.add_input_float(tag="fxed_add_phase",  label="", width=55,
                                    default_value=0.0, min_value=0.0, max_value=1.0,
                                    step=0, format="%.3f")
                dpg.add_button(label="add layer", width=90, height=22,
                               callback=self._fxed_add_layer)

        self._fxed_refresh_slot_labels()

    def _refresh_fx_pool_buttons(self):
        for n in range(1, self._POOL_SLOTS + 1):
            p = self._fx_pool.get(n) if self._fx_pool else None
            lbl = f"{n}:{p.name[:6]}" if p else f"FX{n}"
            try:
                dpg.set_item_label(f"fx_btn_{n}", lbl)
            except Exception:
                pass

    def _fxed_refresh_slot_labels(self):
        for n in range(1, self._POOL_SLOTS + 1):
            p = self._fx_pool.get(n) if self._fx_pool else None
            label = p.name[:5] if p else str(n)
            is_selected = (n == self._fx_ed_slot)
            try:
                dpg.set_item_label(f"fxed_slot_{n}", label)
                color = _C_BTN_A if is_selected else (_C_ACCENT if p else _C_BTN)
                dpg.configure_item(f"fxed_slot_{n}", enabled=True)
                _ = color
            except Exception:
                pass

    def _fxed_select_slot(self, _s, _a, user_data):
        self._fx_ed_slot = user_data
        preset = self._fx_pool.get(user_data) if self._fx_pool else None
        if preset:
            dpg.set_value("fxed_name", preset.name)
            self._fx_ed_layers = [dict(ld) for ld in preset.layers]
        else:
            dpg.set_value("fxed_name", f"FX {user_data}")
            self._fx_ed_layers = []
        self._fxed_rebuild_rows()

    def _fxed_new_preset(self, *_):
        for n in range(1, self._POOL_SLOTS + 1):
            if not (self._fx_pool and self._fx_pool.get(n)):
                self._fx_ed_slot = n
                dpg.set_value("fxed_name", f"FX {n}")
                self._fx_ed_layers = []
                self._fxed_rebuild_rows()
                return
        self._log(f"All {self._POOL_SLOTS} FX slots are full — delete one first")

    def _fxed_delete_preset(self, *_):
        if self._fx_ed_slot and self._fx_pool:
            self._fx_pool.delete(self._fx_ed_slot)
            self._fx_ed_layers = []
            dpg.set_value("fxed_name", "")
            self._fxed_rebuild_rows()
            ShowFile.save_fx_pool(self._fx_pool)
            self._fxed_refresh_slot_labels()
            self._refresh_fx_pool_buttons()
            self._log(f"> FX {self._fx_ed_slot} deleted")

    def _fxed_rainbow(self, *_):
        """Load RGB rainbow template into editor (doesn't save until SAVE is clicked)."""
        self._fx_ed_layers = [
            {'waveform': 'sine', 'channel': 'red',   'bpm': 30.0, 'size': 200.0, 'spread': 1.0, 'phase_offset': 0.0},
            {'waveform': 'sine', 'channel': 'green', 'bpm': 30.0, 'size': 200.0, 'spread': 1.0, 'phase_offset': 0.333},
            {'waveform': 'sine', 'channel': 'blue',  'bpm': 30.0, 'size': 200.0, 'spread': 1.0, 'phase_offset': 0.667},
        ]
        if not dpg.get_value("fxed_name"):
            dpg.set_value("fxed_name", "Rainbow")
        self._fxed_rebuild_rows()

    def _fxed_chase_rgb(self, *_):
        """Pixel chase — white pulse travelling through R then G then B."""
        self._fx_ed_layers = [
            {'waveform': 'pulse', 'channel': 'red',   'bpm': 60.0, 'size': 200.0, 'spread': 1.0, 'phase_offset': 0.0},
            {'waveform': 'pulse', 'channel': 'green', 'bpm': 60.0, 'size': 200.0, 'spread': 1.0, 'phase_offset': 0.333},
            {'waveform': 'pulse', 'channel': 'blue',  'bpm': 60.0, 'size': 200.0, 'spread': 1.0, 'phase_offset': 0.667},
        ]
        if not dpg.get_value("fxed_name"):
            dpg.set_value("fxed_name", "Chase RGB")
        self._fxed_rebuild_rows()

    def _fxed_rebuild_rows(self):
        try:
            dpg.delete_item("fxed_layer_rows", children_only=True)
        except Exception:
            return
        for i, ld in enumerate(self._fx_ed_layers):
            # DPG quirk: add_input_float/add_combo set the visual display via
            # default_value, but get_value() returns 0/'' until the widget is
            # explicitly touched by the user. We call set_value() right after
            # creation so _fxed_sync_rows() always reads the correct values.
            with dpg.group(horizontal=True, parent="fxed_layer_rows"):
                dpg.add_combo(tag=f"fxed_r{i}_wave", label="", width=90,
                              items=self._FX_WAVEFORMS,
                              default_value=ld.get('waveform', 'sine'))
                dpg.set_value(f"fxed_r{i}_wave", ld.get('waveform', 'sine'))

                dpg.add_combo(tag=f"fxed_r{i}_ch", label="", width=70,
                              items=self._FX_CHANNELS,
                              default_value=ld.get('channel', 'red'))
                dpg.set_value(f"fxed_r{i}_ch", ld.get('channel', 'red'))

                dpg.add_input_float(tag=f"fxed_r{i}_bpm", label="", width=60,
                                    default_value=ld.get('bpm', 60.0),
                                    min_value=1.0, max_value=999.0,
                                    step=0, format="%.1f")
                dpg.set_value(f"fxed_r{i}_bpm", ld.get('bpm', 60.0))

                dpg.add_input_float(tag=f"fxed_r{i}_size", label="", width=60,
                                    default_value=ld.get('size', 100.0),
                                    min_value=0.0, max_value=100.0,
                                    step=0, format="%.0f")
                dpg.set_value(f"fxed_r{i}_size", ld.get('size', 100.0))

                dpg.add_input_float(tag=f"fxed_r{i}_spread", label="", width=55,
                                    default_value=ld.get('spread', 0.0),
                                    min_value=0.0, max_value=100.0,
                                    step=0, format="%.1f")
                dpg.set_value(f"fxed_r{i}_spread", ld.get('spread', 0.0))

                dpg.add_input_float(tag=f"fxed_r{i}_phase", label="", width=55,
                                    default_value=ld.get('phase_offset', 0.0),
                                    min_value=0.0, max_value=1.0,
                                    step=0, format="%.3f")
                dpg.set_value(f"fxed_r{i}_phase", ld.get('phase_offset', 0.0))

                _ref_items = ["—"] + [str(n) for n in range(1, self._POOL_SLOTS + 1)]
                _gid = ld.get('group_id')
                _cid = ld.get('color_id')
                _did = ld.get('dim_id')
                dpg.add_combo(tag=f"fxed_r{i}_grp", label="", width=46,
                              items=_ref_items,
                              default_value="—" if _gid is None else str(_gid))
                dpg.set_value(f"fxed_r{i}_grp", "—" if _gid is None else str(_gid))
                dpg.add_combo(tag=f"fxed_r{i}_col", label="", width=46,
                              items=_ref_items,
                              default_value="—" if _cid is None else str(_cid))
                dpg.set_value(f"fxed_r{i}_col", "—" if _cid is None else str(_cid))
                dpg.add_combo(tag=f"fxed_r{i}_dim", label="", width=46,
                              items=_ref_items,
                              default_value="—" if _did is None else str(_did))
                dpg.set_value(f"fxed_r{i}_dim", "—" if _did is None else str(_did))

                dpg.add_button(label="X", width=24, height=20,
                               callback=self._fxed_remove_layer,
                               user_data=i)

    def _fxed_add_layer(self, *_):
        self._fxed_sync_rows()   # save any edits in existing rows first
        self._fx_ed_layers.append({
            'waveform':     dpg.get_value("fxed_add_wave"),
            'channel':      dpg.get_value("fxed_add_ch"),
            'bpm':          dpg.get_value("fxed_add_bpm"),
            'size':         dpg.get_value("fxed_add_size"),
            'spread':       dpg.get_value("fxed_add_spread"),
            'phase_offset': dpg.get_value("fxed_add_phase"),
        })
        self._fxed_rebuild_rows()

    def _fxed_remove_layer(self, _s, _a, user_data):
        self._fxed_sync_rows()
        idx = int(user_data)
        if 0 <= idx < len(self._fx_ed_layers):
            self._fx_ed_layers.pop(idx)
        self._fxed_rebuild_rows()

    def _fxed_sync_rows(self):
        """Read current widget values back into _fx_ed_layers."""
        def _ref(v):
            return None if v == "—" else int(v)
        for i in range(len(self._fx_ed_layers)):
            try:
                self._fx_ed_layers[i]['waveform']     = dpg.get_value(f"fxed_r{i}_wave")
                self._fx_ed_layers[i]['channel']       = dpg.get_value(f"fxed_r{i}_ch")
                self._fx_ed_layers[i]['bpm']           = dpg.get_value(f"fxed_r{i}_bpm")
                self._fx_ed_layers[i]['size']          = dpg.get_value(f"fxed_r{i}_size")
                self._fx_ed_layers[i]['spread']        = dpg.get_value(f"fxed_r{i}_spread")
                self._fx_ed_layers[i]['phase_offset']  = dpg.get_value(f"fxed_r{i}_phase")
                self._fx_ed_layers[i]['group_id']      = _ref(dpg.get_value(f"fxed_r{i}_grp"))
                self._fx_ed_layers[i]['color_id']      = _ref(dpg.get_value(f"fxed_r{i}_col"))
                self._fx_ed_layers[i]['dim_id']        = _ref(dpg.get_value(f"fxed_r{i}_dim"))
            except Exception:
                pass

    def _fxed_save(self, *_):
        if self._fx_ed_slot is None:
            self._log("> Select a slot first")
            return
        self._fxed_sync_rows()
        name   = dpg.get_value("fxed_name").strip() or f"FX {self._fx_ed_slot}"
        preset = FXPreset(self._fx_ed_slot, name)
        for ld in self._fx_ed_layers:
            preset.add_layer(
                ld.get('waveform', 'sine'),
                ld.get('channel',  'red'),
                bpm          = ld.get('bpm',          60.0),
                size         = ld.get('size',         200.0),
                spread       = ld.get('spread',         1.0),
                phase_offset = ld.get('phase_offset',   0.0),
                group_id     = ld.get('group_id'),
                color_id     = ld.get('color_id'),
                dim_id       = ld.get('dim_id'),
            )
        self._fx_pool.store(self._fx_ed_slot, preset)
        ShowFile.save_fx_pool(self._fx_pool)
        self._fxed_refresh_slot_labels()
        self._refresh_fx_pool_buttons()
        self._log(f"> Saved FX {self._fx_ed_slot}: {name}  ({len(preset.layers)} layers)")

    def _fxed_refresh_target(self, *_):
        """Rebuild the target combo with current group list."""
        items = ["Selection", "All Fixtures"]
        if self._groups:
            for gid in sorted(self._groups.groups):
                g = self._groups.groups[gid]
                if g.members:
                    items.append(f"Group {gid}: {g.name}")
        try:
            dpg.configure_item("fxed_target", items=items)
        except Exception:
            pass

    def _fxed_fire(self, *_):
        if self._fx_ed_slot is None:
            self._log("> Select a slot first")
            return
        self._fxed_save()

        try:
            target = dpg.get_value("fxed_target")
        except Exception:
            target = "Selection"

        saved_sel = list(self._prog.selection)

        if target == "All Fixtures":
            self._prog.clear_selection()
        elif target.startswith("Group "):
            try:
                gid = int(target.split(":")[0].split()[-1])
                self._groups.recall(gid, self._prog)
            except (ValueError, IndexError, AttributeError):
                pass

        result = self._cmd(f"FIRE FX {self._fx_ed_slot}") if self._cmd else ""

        # Restore selection unless it was already empty
        if saved_sel:
            self._prog.select(saved_sel)

        if result:
            self._log(f"  {result}")

    def _on_fx_editor_toggle(self, *_):
        vis = dpg.get_item_configuration("fx_editor_window").get("show", False)
        if vis:
            self._save_popup_layout()
        dpg.configure_item("fx_editor_window", show=not vis)
        if not vis:
            self._fxed_refresh_target()

    def _on_cmd_execute(self):
        raw = dpg.get_value("cmd_input").strip()
        if not raw:
            return
        dpg.set_value("cmd_input", "")
        dpg.focus_item("cmd_input")

        # Save to history
        self._cmd_history.append(raw)
        self._cmd_hist_i = -1

        # Echo input
        self._log(f"> {raw}")

        # Route to cmd_fn; it returns a result string to display
        if self._cmd:
            result = self._cmd(raw)
            if result:
                is_err = any(str(result).startswith(p) for p in self._ERR_PREFIXES)
                for line in str(result).splitlines():
                    if is_err:
                        self._log_error(f"  {line}")
                    else:
                        self._log(f"  {line}")

        # Feed command into AI history for future context
        if self._ai:
            try:
                self._ai.push_cmd_history(raw)
            except Exception:
                pass

    def _on_delete_key(self):
        # Only fire CLEAR when cmd_input is empty (so Delete still edits text normally)
        if dpg.get_value("cmd_input"):
            return
        if self._cmd:
            result = self._cmd("CLEAR")
            self._log("> CLEAR")
            if result:
                self._log(f"  {result}")
        dpg.focus_item("cmd_input")

    _ERR_PREFIXES = ("Usage:", "Error:", "bad ", "not found", "unknown verb",
                     "Unknown", "invalid", "no cuestack", "no active", "not set",
                     "AI error")

    def _log(self, line):
        self._cmd_log.append(line)
        if len(self._cmd_log) > 200:
            self._cmd_log = self._cmd_log[-200:]
        try:
            dpg.set_value("cmd_log", "\n".join(self._cmd_log))
            dpg.set_y_scroll("cmd_log_win", 99999)
        except Exception:
            pass

    def _log_error(self, line):
        self._log(f"⚠ {line}")

    def _build_ai_history_popup(self):
        with dpg.window(tag="ai_history_window", label="ai history",
                        width=700, height=460, show=False, pos=(240, 140)):
            with dpg.group(horizontal=True):
                dpg.add_text("recent ai prompts", color=_C_ACCENT)
                dpg.add_spacer(width=8)
                dpg.add_button(label="clear",
                               callback=lambda: (self._ai_history.clear(),
                                                 self._refresh_ai_history()))
            dpg.add_separator()
            with dpg.child_window(tag="ai_hist_scroll", width=-1, height=-1,
                                  border=False):
                dpg.add_text("", tag="ai_hist_text", wrap=680, color=_C_TEXT)

    def _build_monitors_popup(self):
        """Floating programmer/output monitor popup — no inner boxes, just tables."""
        with dpg.window(tag="monitors_window", label="monitors",
                        width=1600, height=360, show=False,
                        pos=(160, 360), no_collapse=False):
            with dpg.group(horizontal=True):
                # ── Programmer ──────────────────────────────────────
                with dpg.group(tag="prog_panel"):
                    dpg.add_text("programmer", tag="prog_mon_title", color=_C_DIM)
                    dpg.add_separator()
                    with dpg.table(tag="prog_table", header_row=True,
                                   borders_innerV=True, borders_outerV=True,
                                   borders_outerH=True, row_background=True,
                                   width=768, scrollY=False):
                        dpg.add_table_column(label="Fixture", width_fixed=True, init_width_or_weight=110)
                        dpg.add_table_column(label="R",   width_fixed=True, init_width_or_weight=42)
                        dpg.add_table_column(label="G",   width_fixed=True, init_width_or_weight=42)
                        dpg.add_table_column(label="B",   width_fixed=True, init_width_or_weight=42)
                        dpg.add_table_column(label="Dim", width_fixed=True, init_width_or_weight=56)
                        dpg.add_table_column(label="fx",  width_stretch=True)
                        dpg.add_table_column(label="Bar", width_fixed=True, init_width_or_weight=130)

                        for master in self._patch.all_fixtures():
                            fid = str(master.fixture_id)
                            with dpg.table_row(tag=f"prog_row_{fid}"):
                                dpg.add_text(master.name, tag=f"prog_name_{fid}", color=_C_DIM)
                                dpg.add_text("—", tag=f"prog_r_{fid}",   color=_C_DIM)
                                dpg.add_text("—", tag=f"prog_g_{fid}",   color=_C_DIM)
                                dpg.add_text("—", tag=f"prog_b_{fid}",   color=_C_DIM)
                                dpg.add_text("—", tag=f"prog_dim_{fid}", color=_C_DIM)
                                dpg.add_text("—", tag=f"prog_fx_{fid}",  color=_C_DIM)
                                dpg.add_progress_bar(default_value=0.0,
                                                     tag=f"prog_bar_{fid}", width=-1)

                dpg.add_spacer(width=24)

                # ── Output Monitor ──────────────────────────────────
                with dpg.group(tag="out_panel"):
                    dpg.add_text("output monitor", color=_C_ACCENT)
                    dpg.add_separator()
                    with dpg.table(tag="out_table", header_row=True,
                                   borders_innerV=True, borders_outerV=True,
                                   borders_outerH=True, row_background=True,
                                   scrollY=False):
                        dpg.add_table_column(label="Fixture", width_fixed=True, init_width_or_weight=110)
                        dpg.add_table_column(label="R",   width_fixed=True, init_width_or_weight=42)
                        dpg.add_table_column(label="G",   width_fixed=True, init_width_or_weight=42)
                        dpg.add_table_column(label="B",   width_fixed=True, init_width_or_weight=42)
                        dpg.add_table_column(label="Dim", width_fixed=True, init_width_or_weight=56)
                        dpg.add_table_column(label="Bar", width_stretch=True)

                        for master in self._patch.all_fixtures():
                            fid = str(master.fixture_id)
                            with dpg.table_row(tag=f"out_row_{fid}"):
                                dpg.add_text(master.name, tag=f"out_name_{fid}")
                                dpg.add_text("0",  tag=f"out_r_{fid}",   color=(200, 80,  80,  255))
                                dpg.add_text("0",  tag=f"out_g_{fid}",   color=(80,  200, 80,  255))
                                dpg.add_text("0",  tag=f"out_b_{fid}",   color=(80,  130, 220, 255))
                                dpg.add_text("--", tag=f"out_dim_{fid}", color=_C_DIM)
                                dpg.add_progress_bar(default_value=0.0,
                                                     tag=f"out_bar_{fid}", width=-1)

    _AI_CHIPS = [
        ("warm wash",    "warm amber golden wash on all fixtures, moderate brightness"),
        ("strobe",       "fast white strobe on all fixtures"),
        ("blackout",     "full blackout, all fixtures off immediately"),
        ("rgb chase",    "RGB color chase effect rippling through all fixtures"),
        ("cool wash",    "cool blue-white wash, clean and bright"),
        ("purple haze",  "deep violet-purple haze atmosphere"),
        ("sunrise",      "slow sunrise from deep red to orange to gold"),
        ("pulse",        "slow red breathing pulse on all fixtures"),
        ("thunderstorm", "chaotic random flicker simulating lightning"),
        ("disco",        "fast random colourful disco effect"),
    ]

    def _build_ai_bar(self):
        dpg.add_separator()
        # Header + chips merged into one row — keeps total bar height to 2 rows
        # so the input never falls under the macOS dock on 1080p displays.
        with dpg.group(horizontal=True):
            dpg.add_text("ai prompt", color=_C_ACCENT)
            dpg.add_spacer(width=8)
            dpg.add_text("", tag="ai_status", color=_C_DIM)
            dpg.add_spacer(width=8)
            dpg.add_text("", tag="ai_tokens", color=_C_DIM)
            dpg.add_spacer(width=8)
            dpg.add_button(label="history", width=70,
                           callback=lambda: dpg.configure_item(
                               "ai_history_window",
                               show=not dpg.is_item_shown("ai_history_window")))
            dpg.add_spacer(width=16)
            for label, prompt in self._AI_CHIPS:
                dpg.add_button(label=label, width=98,
                               callback=self._on_ai_chip,
                               user_data=prompt)
        with dpg.group(horizontal=True):
            dpg.add_input_text(tag="ai_input", hint="describe the look...",
                               width=-120, on_enter=True,
                               callback=self._on_ai_send)
            dpg.add_button(label="send", width=110,
                           callback=self._on_ai_send)

    # ── Callbacks ────────────────────────────────────────────

    def _on_fx_rate(self, sender, value):
        now = time.monotonic()
        for layer in self._fx._layers.values():
            if layer.fx_id >= 10000:  # skip executor (cue) FX — programmer sliders don't own them
                continue
            layer.set_rate_smooth(value, now)
        self._fx_sliders_to_prog('bpm', value)
        if self._fx_params is not None:
            self._fx_params['rate_bpm'] = value

    def _on_fx_size(self, sender, value):
        for layer in self._fx._layers.values():
            if layer.fx_id >= 10000:
                continue
            layer.size = value
        self._fx_sliders_to_prog('size', value)
        if self._fx_params is not None:
            self._fx_params['size'] = value

    def _on_fx_spread(self, sender, value):
        for layer in self._fx._layers.values():
            if layer.fx_id >= 10000:
                continue
            layer.spread = value
        self._fx_sliders_to_prog('spread', value)
        if self._fx_params is not None:
            self._fx_params['spread'] = value

    def _on_tap_tempo(self, *_):
        """Record a tap and compute BPM from the average of the last 4 intervals."""
        now = time.monotonic()
        self._tap_times.append(now)
        # Drop taps older than 3 seconds — they're from a different phrase
        self._tap_times = [t for t in self._tap_times if now - t < 3.0]
        # Keep only last 5 taps (4 intervals)
        if len(self._tap_times) > 5:
            self._tap_times = self._tap_times[-5:]
        if len(self._tap_times) >= 2:
            intervals = [self._tap_times[i+1] - self._tap_times[i]
                         for i in range(len(self._tap_times) - 1)]
            avg_interval = sum(intervals) / len(intervals)
            bpm = round(60.0 / avg_interval, 1) if avg_interval > 0 else 60.0
            bpm = max(10.0, min(480.0, bpm))
            try:
                dpg.set_value("fx_rate", bpm)
                dpg.set_value("fx_tap_label", f"{bpm:.0f} bpm")
            except Exception:
                pass
            if self._cmd:
                self._cmd(f"BPM {bpm:.1f}")
        else:
            try:
                dpg.set_value("fx_tap_label", "tap…")
            except Exception:
                pass

    def _fx_sliders_to_prog(self, key, value):
        """Propagate FX slider change into programmer so it can be recorded."""
        if not self._prog:
            return
        for vals in self._prog.data.values():
            layers = vals.get('fx')
            if isinstance(layers, list):
                for ld in layers:
                    ld[key] = value

    def _on_save(self):
        if self._save:
            self._save()
            dpg.set_value("hdr_save_status", "  saved ✓")
        else:
            dpg.set_value("hdr_save_status", "  no save_fn")

    def _on_learn_type_change(self, sender, value):
        self._learn_type = 'cc' if value == 'CC' else 'note'

    def _toggle_learn(self):
        if self._learn_armed:
            # Already armed — cancel
            self._learn_armed = False
            self._midi.cancel_learn()
            dpg.set_item_label("learn_btn", "LEARN")
            dpg.set_value("learn_status", "cancelled")
            return
        target_name = dpg.get_value("learn_target")
        if not target_name or target_name not in self.target_registry:
            dpg.set_value("learn_status", "← pick target first")
            return
        self._learn_target = target_name
        self._learn_armed  = True
        type_str = dpg.get_value("learn_type_radio")
        self._learn_type = 'cc' if type_str == 'CC' else 'note'
        self._learn_armed_type = self._learn_type
        wait_label = "CC knob/fader" if self._learn_type == 'cc' else "key or pad"
        dpg.set_value("learn_status", f"waiting for {wait_label}...")
        dpg.set_item_label("learn_btn", "CANCEL")
        self._midi.start_learn(self._learn_type, self._on_learn_captured)

    def _start_go_cue_learn(self):
        try:
            cs_n  = int(dpg.get_value("midi_go_cs"))
            cue_n = float(dpg.get_value("midi_go_cue"))
        except Exception:
            return
        name = f"GO CS {cs_n} CUE {int(cue_n)}"
        cmd  = f"GO CS {cs_n} CUE {cue_n}"
        cb   = (lambda c=cmd: self._cmd(c)) if self._cmd else (lambda: None)
        GUIEngine.target_registry[name] = (cb, False, True)
        # Arm learn as a note targeting this dynamic entry
        self._learn_target     = name
        self._learn_armed      = True
        self._learn_armed_type = 'note'
        self._midi.start_learn('note', self._on_go_cue_captured)
        dpg.set_value("go_cue_status", f"waiting for note → {name}...")

    def _start_exec_flash_learn(self):
        """
        Learn a note for 'Exec <n> Flash' — live only while the pad is held.
        Unlike _start_go_cue_learn (GO-only, no release action), this needs
        an off_callback, so it delegates to the general _on_learn_captured
        handler (which already reads entry[3] as off_cb) instead of a
        bespoke capture handler.
        """
        try:
            ex_n = int(dpg.get_value("midi_flash_exec"))
        except Exception:
            return
        name    = f"Exec {ex_n} Flash"
        on_cmd  = f"EXEC {ex_n} FLASH ON"
        off_cmd = f"EXEC {ex_n} FLASH OFF"
        on_cb   = (lambda c=on_cmd:  self._cmd(c)) if self._cmd else (lambda: None)
        off_cb  = (lambda c=off_cmd: self._cmd(c)) if self._cmd else (lambda: None)
        GUIEngine.target_registry[name] = (on_cb, False, True, off_cb)
        self._learn_target     = name
        self._learn_armed      = True
        self._learn_armed_type = 'note'
        self._midi.start_learn('note', self._on_learn_captured)
        dpg.set_value("flash_learn_status", f"waiting for note → {name}...")

    def _on_go_cue_captured(self, ch, number):
        """MIDI-thread callback for GO CS+CUE note learn."""
        name = self._learn_target
        self._learn_armed = False
        entry = GUIEngine.target_registry.get(name)
        if entry:
            self._midi.map_note(ch, number, entry[0], name=name)
        dpg.set_value("go_cue_status", f"CH{ch} Note{number} → {name}")
        try:
            dpg.set_item_label("learn_btn", "LEARN")
        except Exception:
            pass
        self._pending_table_refresh = True

    def _on_learn_captured(self, ch, number):
        """Called from MIDI thread when a CC/note is received during learn.
        NOTE: self._learn_type is already None here (cleared by MIDIEngine
        before firing the callback), so we use self._learn_armed_type instead.
        Table rebuild is deferred to the main-thread update loop via a flag
        because DearPyGui item creation/deletion must happen on the main thread.
        """
        armed_type  = self._learn_armed_type   # 'cc' or 'note', still valid
        target_name = self._learn_target
        self._learn_armed = False

        entry = self.target_registry.get(target_name)
        if entry is None:
            dpg.set_value("learn_status", "target gone?")
            return

        cb, soft_takeover = entry[0], entry[1]
        off_cb = entry[3] if len(entry) > 3 else None
        if armed_type == 'cc':
            self._midi.map_cc(ch, number, cb,
                              name=target_name, soft_takeover=soft_takeover)
            type_label = "CC"
        else:
            self._midi.map_note(ch, number, cb, off_cb, name=target_name)
            type_label = "Note"

        # set_value is thread-safe; item rebuild deferred to main thread
        dpg.set_value("learn_status",
                      f"CH{ch} {type_label}{number} → {target_name}")
        try:
            dpg.set_item_label("learn_btn", "LEARN")
        except Exception:
            pass
        self._pending_table_refresh = True

    def _on_ai_chip(self, sender, app_data, user_data):
        """Fire a quick-prompt chip — set the input text and send immediately."""
        if self._ai is None:
            return
        try:
            dpg.set_value("ai_input", user_data)
        except Exception:
            pass
        self._on_ai_send()

    def _on_ai_send(self):
        if self._ai is None:
            return
        prompt = dpg.get_value("ai_input")
        if not prompt.strip():
            return
        dpg.set_value("ai_input", "")
        self._log(f"AI ← {prompt}")
        import datetime as _dt
        ts = _dt.datetime.now().strftime("%H:%M:%S")
        try:
            dpg.configure_item("ai_status", default_value="thinking…", color=_C_DIM)
        except Exception:
            pass

        def _run():
            actions = self._ai.ask(prompt)
            try:
                dpg.configure_item("ai_status", default_value="", color=_C_DIM)
            except Exception:
                pass
            summary = f"{len(actions)} action(s)" if actions else "no actions"
            entry = {'ts': ts, 'prompt': prompt, 'summary': summary,
                     'actions': [a.get('action', '?') for a in (actions or [])]}
            self._ai_history.append(entry)
            if len(self._ai_history) > 100:
                self._ai_history = self._ai_history[-100:]
            self._refresh_ai_history()

        # Install token display callback once
        if self._ai and self._ai._token_cb is None:
            def _tok_cb(in_t, out_t):
                try:
                    dpg.set_value("ai_tokens", f"↑{in_t} ↓{out_t} tok")
                except Exception:
                    pass
            self._ai._token_cb = _tok_cb

        threading.Thread(target=_run, daemon=True).start()

    def _refresh_ai_history(self):
        try:
            lines = []
            for e in reversed(self._ai_history[-50:]):
                acts = ", ".join(e['actions'][:6]) or "—"
                lines.append(f"[{e['ts']}] {e['prompt']}")
                lines.append(f"  → {e['summary']}: {acts}")
                lines.append("")
            dpg.set_value("ai_hist_text", "\n".join(lines))
        except Exception:
            pass

    def _remove_cc_map(self, ch, cc):
        self._midi.cc_maps.pop((ch, cc), None)
        ShowFile.save_midi(self._midi)
        self._refresh_midi_table()

    def _remove_note_map(self, ch, note):
        self._midi.note_maps.pop((ch, note), None)
        ShowFile.save_midi(self._midi)
        self._refresh_midi_table()

    def _on_midi_row_select_reassign(self, sender, app_data, user_data):
        """Mark a mapping row for reassignment and update the reassign UI."""
        kind, ch, num, current_name = user_data
        self._reassign_pending = {'type': kind, 'ch': ch, 'num': num}
        label = f"CH{ch} {'CC' if kind == 'cc' else 'Note'}{num}  ({current_name})"
        try:
            dpg.set_value("rsn_selected", label)
            dpg.configure_item("rsn_selected", color=_C_ACCENT)
            if current_name in self.target_registry:
                dpg.set_value("rsn_target", current_name)
        except Exception:
            pass

    def _on_apply_reassign(self):
        """Apply the pending reassignment from rsn_target combo."""
        p = self._reassign_pending
        if p is None:
            return
        new_name = dpg.get_value("rsn_target")
        if not new_name or new_name not in self.target_registry:
            return
        entry   = self.target_registry[new_name]
        cb      = entry[0]
        off_cb  = entry[3] if len(entry) > 3 else None
        soft    = entry[1]
        ch, num = p['ch'], p['num']
        if p['type'] == 'cc':
            self._midi.map_cc(ch, num, cb, name=new_name, soft_takeover=soft)
        else:
            self._midi.map_note(ch, num, cb, off_cb, name=new_name)
        ShowFile.save_midi(self._midi)
        self._reassign_pending = None
        try:
            dpg.set_value("rsn_selected", "select a row →")
            dpg.configure_item("rsn_selected", color=_C_DIM)
        except Exception:
            pass
        self._refresh_midi_table()

    def _reassign_cc_map(self, ch, cc, new_target):
        """Reassign an existing CC mapping to a different target by name."""
        if new_target not in self.target_registry:
            return
        entry  = self.target_registry[new_target]
        cb, soft = entry[0], entry[1]
        self._midi.map_cc(ch, cc, cb, name=new_target, soft_takeover=soft)
        ShowFile.save_midi(self._midi)
        self._refresh_midi_table()

    def _reassign_note_map(self, ch, note, new_target):
        """Reassign an existing Note mapping to a different target by name."""
        if new_target not in self.target_registry:
            return
        entry  = self.target_registry[new_target]
        cb     = entry[0]
        off_cb = entry[3] if len(entry) > 3 else None
        self._midi.map_note(ch, note, cb, off_cb, name=new_target)
        ShowFile.save_midi(self._midi)
        self._refresh_midi_table()

    # ── MIDI table (re)build ─────────────────────────────────

    def _refresh_midi_table(self):
        """Rebuild the MIDI mapping table rows from current mappings."""
        # Delete existing rows
        for tag in list(self._map_rows.values()):
            try:
                dpg.delete_item(tag)
            except Exception:
                pass
        self._map_rows.clear()

        for (ch, cc), m in list(self._midi.cc_maps.items()):
            row_tag = f"mr_cc_{ch}_{cc}"
            self._map_rows[('cc', ch, cc)] = row_tag
            status = "live" if m.taken_over else "⧖ takeover"
            with dpg.table_row(tag=row_tag, parent="midi_table"):
                dpg.add_text(str(ch))
                dpg.add_text(str(cc))
                dpg.add_text("cc", color=_C_ACCENT)
                dpg.add_text(m.name, tag=f"mr_name_cc_{ch}_{cc}")
                dpg.add_text(status, tag=f"mr_st_cc_{ch}_{cc}",
                             color=_C_TEXT if m.taken_over else _C_DIM)
                dpg.add_button(label="del",
                               callback=lambda s, a, u: self._remove_cc_map(*u),
                               user_data=(ch, cc), width=34)
                dpg.add_button(label="►",
                               callback=self._on_midi_row_select_reassign,
                               user_data=('cc', ch, cc, m.name), width=34)

        for (ch, note), m in list(self._midi.note_maps.items()):
            row_tag = f"mr_note_{ch}_{note}"
            self._map_rows[('note', ch, note)] = row_tag
            with dpg.table_row(tag=row_tag, parent="midi_table"):
                dpg.add_text(str(ch))
                dpg.add_text(str(note))
                dpg.add_text("Note", color=_C_P_BEAM)
                dpg.add_text(m.name, tag=f"mr_name_note_{ch}_{note}")
                dpg.add_text("—")
                dpg.add_button(label="del",
                               callback=lambda s, a, u: self._remove_note_map(*u),
                               user_data=(ch, note), width=34)
                dpg.add_button(label="►",
                               callback=self._on_midi_row_select_reassign,
                               user_data=('note', ch, note, m.name), width=34)

    # ── Live update loop ─────────────────────────────────────

    def start_update_loop(self):
        """Start background thread that refreshes live data at 20 Hz."""
        self._running = True
        t = threading.Thread(target=self._update_loop, daemon=True)
        t.start()

    def _update_loop(self):
        while self._running and dpg.is_dearpygui_running():
            try:
                self._tick()
            except Exception:
                pass
            time.sleep(0.05)
        self._running = False

    def _rebuild_cue_list(self, stack):
        """Clear and repopulate the left-column cue list for the given stack."""
        dpg.delete_item("cue_list_group", children_only=True)
        if not stack:
            return
        sid = stack.stack_id
        for num in stack._sorted_cue_numbers():
            cue   = stack.cues[num]
            tag   = f"cue_row_{sid}_{num}"
            ft    = f" {cue.fade_time:.1f}s" if cue.fade_time else ""
            label = f"  [{num:.0f}]  {cue.name}{ft}"
            with dpg.group(parent="cue_list_group", horizontal=True):
                dpg.add_selectable(label=label, tag=tag,
                                   callback=lambda *_, u=num: self._goto(u),
                                   user_data=num)

    def _playbacks_state_hash(self):
        """Compact snapshot of active executor state — used to detect changes."""
        if not self._executor_pool:
            return ()
        return tuple(
            (eid, ex.priority, ex.cuestack.current if ex.cuestack else None,
             ex.time_override_on, ex.time_override_fade)
            for eid, ex in sorted(self._executor_pool.executors.items())
            if ex.is_active and ex.cuestack
        )

    def _rebuild_playbacks(self):
        """Rebuild the active-playbacks list inside the left column."""
        try:
            dpg.delete_item("playbacks_list", children_only=True)
        except Exception:
            return

        active = []
        if self._executor_pool:
            for eid in reversed(self._executor_pool._fire_order):
                ex = self._executor_pool.executors.get(eid)
                if ex and ex.is_active and ex.cuestack:
                    active.append(ex)

        if not active:
            dpg.add_text("— none running", tag="playbacks_empty",
                         color=_C_DIM, parent="playbacks_list")
            return

        for ex in active:
            cs  = ex.cuestack
            cur = cs.current
            if cur is not None:
                cue = cs.cues.get(cur)
                cue_label = f"▶ {cur:.0f}: {cue.name[:10]}" if cue else f"▶ {cur:.0f}"
            else:
                cue_label = "▶ —"
            pri_label = Executor.PRIORITY_LABELS.get(ex.priority, 'NRM')
            with dpg.group(horizontal=True, parent="playbacks_list"):
                dpg.add_text(f"[{ex.exec_id}] {cs.name[:11]}", color=_C_TEXT)
                dpg.add_spacer(width=2)
                dpg.add_text(cue_label, color=_C_ACCENT)
                # Time override badge
                if ex.time_override_on and ex.time_override_fade is not None:
                    t_label  = f"T{ex.time_override_fade:.1f}s"
                    dpg.add_button(label=t_label, width=52, height=18,
                                   callback=self._on_exec_time_toggle,
                                   user_data=ex.exec_id)
                    dpg.configure_item(dpg.last_item(), enabled=cs.allow_exec_time)
                    if not cs.allow_exec_time:
                        dpg.add_text("🔒", color=_C_DIM)
                else:
                    dpg.add_button(label="time", width=44, height=18,
                                   callback=self._on_exec_time_toggle,
                                   user_data=ex.exec_id)
                dpg.add_button(label=pri_label, width=40, height=18,
                               callback=self._on_priority_cycle,
                               user_data=ex.exec_id)
                dpg.add_button(label="flash", tag=f"flash_btn_{ex.exec_id}",
                               width=40, height=18)
                dpg.add_button(label="stop", width=46, height=18,
                               callback=self._on_stop_executor,
                               user_data=ex.exec_id)
            # Fader level row
            dpg.add_slider_float(
                tag=f"exec_fader_{ex.exec_id}",
                default_value=ex.level,
                min_value=0.0, max_value=1.0,
                width=-1, height=14,
                format="%.2f",
                callback=self._on_exec_fader,
                user_data=ex.exec_id,
                parent="playbacks_list")
            # Fade progress bar (thin, amber) — shows crossfade progress live
            dpg.add_progress_bar(
                tag=f"exec_fade_{ex.exec_id}",
                default_value=0.0,
                width=-1, height=4,
                overlay="",
                parent="playbacks_list")
            try:
                dpg.bind_item_theme(f"exec_fade_{ex.exec_id}",
                                    self._fade_bar_theme)
            except Exception:
                pass

    def _on_exec_time_toggle(self, sender, app_data, user_data):  # noqa: ARG002
        """Toggle executor time override on/off from playbacks panel."""
        if self._executor_pool:
            ex = self._executor_pool.executors.get(int(user_data))
            if ex:
                ex.time_override_on = not ex.time_override_on
        self._last_playbacks_hash = None

    def _on_priority_cycle(self, sender, app_data, user_data):
        if self._executor_pool:
            ex = self._executor_pool.executors.get(int(user_data))
            if ex:
                # NRM → HI → LO → NRM
                cycle = {0: 1, 1: -1, -1: 0}
                ex.priority = cycle.get(ex.priority, 0)
        self._last_playbacks_hash = None

    def _on_stop_executor(self, sender, app_data, user_data):
        if self._executor_pool:
            ex = self._executor_pool.executors.get(int(user_data))
            if ex:
                ex.stop()
        self._last_playbacks_hash = None

    def _on_stop_all_executors(self):
        if self._executor_pool:
            for ex in list(self._executor_pool.executors.values()):
                if ex.is_active:
                    ex.stop()
        self._last_playbacks_hash = None   # force rebuild next tick

    def _on_cs_combo_select(self, _sender, value, _user_data):
        """Switch active cuestack from the left-column combo."""
        if not value or value == "—":
            return
        try:
            n = int(value.split(":")[0])
        except (ValueError, IndexError):
            return
        if self._cmd:
            self._cmd(f"CUESTACK {n}")

    def _on_exec_fader(self, _sender, value, user_data):
        if self._executor_pool:
            ex = self._executor_pool.executors.get(int(user_data))
            if ex:
                ex.level = float(value)

    def _cue_timing_target(self):
        """Return (CueStack, Cue) for the currently active cue, or (None, None)."""
        active_n = self._active_executor[0] if self._active_executor else 1
        cs = self._cuestack_pool.get(active_n) if self._cuestack_pool else None
        if not cs or cs.current is None:
            return None, None
        cue = cs.cues.get(cs.current)
        return cs, cue

    def _on_cue_fade_edit(self, _sender, value, _user_data):
        _, cue = self._cue_timing_target()
        if cue and self._cmd:
            self._cmd(f"CUE {cue.cue_number} FADE {value:.2f}")

    def _on_cue_delay_edit(self, _sender, value, _user_data):
        _, cue = self._cue_timing_target()
        if cue and self._cmd:
            self._cmd(f"CUE {cue.cue_number} DELAY {value:.2f}")

    _tick_first = True   # sync one-shot values on first tick

    def _tick(self):
        # One-shot sync on first tick — apply loaded values to GUI widgets
        if GUIEngine._tick_first:
            GUIEngine._tick_first = False
            try:
                if self._out:
                    dpg.set_value("stage_master_fader",
                                  int(self._out.master_level * 100))
            except Exception:
                pass
            # Re-apply saved dim fader to programmer layer so output is correct on cold boot
            try:
                fd = _fader_dim[0]
                if fd > 0.0:
                    for master in patch.all_fixtures():
                        self._out.programmer_layer.setdefault(
                            str(master.fixture_id), {})['dim'] = fd
            except Exception:
                pass
            # Auto-reload all executors that have a saved cue position so DMX
            # outputs immediately on startup without requiring a manual RELOAD.
            try:
                if self._cmd:
                    for ex in executor_pool.executors.values():
                        cs = ex.cuestack
                        if cs and cs.current is not None:
                            ex.reload(patch, fade_engine)
                            ex.is_active = True
                    self._log("↺  auto-reload — DMX live")
            except Exception:
                pass

        # Consume deferred MIDI table rebuild (must be on main thread)
        if self._pending_table_refresh:
            self._pending_table_refresh = False
            self._refresh_midi_table()

        self._tick_pools()
        self._tick_stage()

        # ── Status bar: programmer + selection ──────────────────
        prog_data   = self._prog.data if self._prog else {}
        prog_active = any(v for v in prog_data.values() if v)
        try:
            if prog_active:
                dpg.configure_item("sb_prog_dot", color=_C_ACCENT)
                dpg.configure_item("sb_prog_lbl", color=_C_ACCENT)
                dpg.set_value("sb_prog_lbl", "PROGRAMMER  DIRTY")
            else:
                dpg.configure_item("sb_prog_dot", color=_C_DIM)
                dpg.configure_item("sb_prog_lbl", color=_C_DIM)
                dpg.set_value("sb_prog_lbl", "programmer  clear")
        except Exception:
            pass

        # BLIND indicator
        try:
            blind = self._out.blind if self._out else False
            _blind_col  = (255, 60, 60, 255)   # red when active — important warning
            dpg.configure_item("sb_blind_lbl",
                               color=_blind_col if blind else _C_DIM)
            dpg.set_value("sb_blind_lbl", "■ BLIND" if blind else "blind")
        except Exception:
            pass

        # BLACKOUT indicator
        try:
            bbo = (self._out.master_level == 0.0) if self._out else False
            _bbo_col = (255, 30, 30, 255)
            dpg.configure_item("sb_bbo_lbl", color=_bbo_col if bbo else _C_DIM)
            dpg.set_value("sb_bbo_lbl", "■ BBO" if bbo else "bbo")
            # Also sync master fader widget
            if bbo:
                try:
                    if not dpg.is_item_active("stage_master_fader"):
                        dpg.set_value("stage_master_fader", 0)
                except Exception:
                    pass
        except Exception:
            pass

        try:
            sel = self._prog.selection if self._prog else []
            sel_ids = {f.fixture_id if isinstance(f, MasterFixture)
                       else getattr(f, 'master_id', None) for f in sel}
            sel_ids.discard(None)
            for master in self._patch.all_fixtures():
                fid = master.fixture_id
                active = fid in sel_ids
                dpg.configure_item(f"sb_sel_{fid}",
                                   color=_C_TEXT if active else _C_DIM)
        except Exception:
            pass

        try:
            pt = _prog_time
            if pt.get('on'):
                pt_label = f"PT {pt['fade']:.1f}s"
                if pt.get('delay', 0.0):
                    pt_label += f" d{pt['delay']:.1f}"
                dpg.set_value("sb_pt_lbl", pt_label)
                dpg.configure_item("sb_pt_lbl", color=_C_ACCENT)
            else:
                dpg.set_value("sb_pt_lbl", "PT")
                dpg.configure_item("sb_pt_lbl", color=_C_DIM)
        except Exception:
            pass

        # Selection counter in command bar (keep small label too)
        try:
            sel = self._prog.selection
            masters = sum(1 for f in sel if isinstance(f, MasterFixture))
            if masters:
                dpg.set_value("cmd_sel_count", f"SEL: {masters} fixture(s)")
                dpg.configure_item("cmd_sel_count", color=_C_ACCENT)
            else:
                dpg.set_value("cmd_sel_count", "sel: —")
                dpg.configure_item("cmd_sel_count", color=_C_DIM)
        except Exception:
            pass

        # Active playbacks — rebuild list when executor state changes
        ph = self._playbacks_state_hash()
        if ph != self._last_playbacks_hash:
            self._last_playbacks_hash = ph
            try:
                self._rebuild_playbacks()
            except Exception:
                pass

        # Sync executor fader sliders and fade progress bars
        if self._executor_pool:
            for eid, ex in self._executor_pool.executors.items():
                if not ex.is_active:
                    continue
                tag = f"exec_fader_{eid}"
                try:
                    if not dpg.is_item_active(tag):
                        dpg.set_value(tag, ex.level)
                except Exception:
                    pass
                # Fade progress bar
                try:
                    fp = self._fade.fade_progress(ex) if self._fade else None
                    fade_tag = f"exec_fade_{eid}"
                    if fp is not None:
                        prog, secs = fp
                        dpg.set_value(fade_tag, prog)
                        dpg.configure_item(fade_tag,
                                           overlay=f"fade  {prog*100:.0f}%  ({secs:.1f}s)")
                    else:
                        dpg.set_value(fade_tag, 0.0)
                        dpg.configure_item(fade_tag, overlay="")
                except Exception:
                    pass

        # FLASH button hold detection — poll is_item_active per active executor
        if self._executor_pool and self._cmd:
            active_eids = {
                eid for eid, ex in self._executor_pool.executors.items()
                if ex.is_active and ex.cuestack
            }
            for eid in list(self._flash_held):
                if eid not in active_eids:
                    if self._flash_held.pop(eid, False):
                        try:
                            self._cmd(f"EXEC {eid} FLASH OFF")
                        except Exception:
                            pass
            for eid in active_eids:
                try:
                    held = dpg.is_item_active(f"flash_btn_{eid}")
                except Exception:
                    held = False
                was_held = self._flash_held.get(eid, False)
                if held and not was_held:
                    try:
                        self._cmd(f"EXEC {eid} FLASH ON")
                    except Exception:
                        pass
                elif not held and was_held:
                    try:
                        self._cmd(f"EXEC {eid} FLASH OFF")
                    except Exception:
                        pass
                self._flash_held[eid] = held

        # Active stack — refresh left column when executor changes
        active_n = self._active_executor[0] if self._active_executor else 1
        active_cs   = self._cuestack_pool.get(active_n) if self._cuestack_pool else None
        current_name = active_cs.name if active_cs else f"Cuestack {active_n}"
        # Build cuestack combo items from pool
        if self._cuestack_pool:
            cs_items = ["—"] + [
                f"{sid}: {self._cuestack_pool.stacks[sid].name}"
                for sid in sorted(self._cuestack_pool.stacks)
            ]
        else:
            cs_items = ["—"]
        active_item = f"{active_n}: {current_name}" if active_cs else "—"
        try:
            dpg.configure_item("left_cs_combo", items=cs_items)
            if not dpg.is_item_active("left_cs_combo"):
                dpg.set_value("left_cs_combo", active_item if active_item in cs_items else "—")
        except Exception:
            pass

        if active_n != self._displayed_executor or current_name != self._displayed_cs_name:
            self._displayed_executor = active_n
            self._displayed_cs_name  = current_name
            try:
                self._rebuild_cue_list(active_cs)
            except Exception:
                pass

        # Header: current cue
        cur = getattr(active_cs, 'current', None) if active_cs else None
        try:
            if cur is not None:
                cue  = active_cs.cues.get(cur)
                name = cue.name if cue else str(cur)
                dpg.set_value("hdr_cue", f"▶  Cue {cur:.0f}: {name}")
            else:
                dpg.set_value("hdr_cue", "▶  (none)")
        except Exception:
            pass

        # Cue timing editor — sync drag floats to active cue's fade/delay
        try:
            _, cue_t = self._cue_timing_target()
            if cue_t:
                dpg.set_value("cue_timing_label", f"Cue {cue_t.cue_number} — {cue_t.name[:14]}")
                if not dpg.is_item_active("cue_fade_input"):
                    dpg.set_value("cue_fade_input", cue_t.fade_time)
                if not dpg.is_item_active("cue_delay_input"):
                    dpg.set_value("cue_delay_input", cue_t.delay_time)
            else:
                dpg.set_value("cue_timing_label", "—")
        except Exception:
            pass

        # Highlight active cue row in left column
        if active_cs:
            sid = active_cs.stack_id
            for num in active_cs._sorted_cue_numbers():
                tag = f"cue_row_{sid}_{num}"
                try:
                    dpg.set_value(tag, num == cur)
                except Exception:
                    pass

        # Header: FX
        layers = list(self._fx._layers.values())
        if layers:
            l = layers[0]
            dpg.set_value("hdr_fx",
                          f"FX: {l.waveform} {l.rate_bpm:.0f}BPM")
            dpg.configure_item("hdr_fx", color=_C_ACCENT)
            # Sync sliders to actual FX state
            dpg.set_value("fx_rate",   l.rate_bpm)
            dpg.set_value("fx_size",   l.size)
            dpg.set_value("fx_spread", l.spread)
        else:
            dpg.set_value("hdr_fx", "fx: off")
            dpg.configure_item("hdr_fx", color=_C_DIM)

        # Header: dim (from programmer layer)
        pl = self._out.programmer_layer
        any_dim = next(iter(pl.values()), {}).get('dim') if pl else None
        if any_dim is not None:
            dpg.set_value("hdr_dim", f"DIM: {any_dim:.0%}")

        # Programmer monitor title colour (mirrors status bar)
        try:
            dpg.configure_item("prog_mon_title",
                               color=_C_ACCENT if prog_active else _C_DIM)
        except Exception:
            pass

        for master in self._patch.all_fixtures():
            fid     = str(master.fixture_id)
            sub_fid = f"{master.fixture_id}.1"
            m_vals  = prog_data.get(fid, {})
            s_vals  = prog_data.get(sub_fid, {})

            has_data = bool(m_vals or s_vals)
            txt_col  = _C_TEXT if has_data else _C_DIM
            r_col    = (200, 80,  80,  255) if has_data else _C_DIM
            g_col    = (80,  200, 80,  255) if has_data else _C_DIM
            b_col    = (80,  130, 220, 255) if has_data else _C_DIM

            r   = int(s_vals.get('red',   0))
            g   = int(s_vals.get('green', 0))
            b   = int(s_vals.get('blue',  0))
            dim = m_vals.get('dim')

            fx_defs  = m_vals.get('fx', [])
            has_fx   = bool(fx_defs)
            if fx_defs:
                parts = []
                for ld in fx_defs:
                    # Waveform: prefer form slot label over raw name
                    if ld.get('form_id') and self._form_pool:
                        frm = self._form_pool.get(ld['form_id'])
                        wave = f"F{ld['form_id']}:{frm.name[:4]}" if frm else f"F{ld['form_id']}"
                    else:
                        wave = ld.get('waveform', '?')[:4]
                    ch = ld.get('channel', '?')[:1].upper()
                    # BPM: pool ref or inline
                    if ld.get('rate_id') and self._rate_pool:
                        rp = self._rate_pool.get(ld['rate_id'])
                        bpm_s = f"R{ld['rate_id']}:{rp.bpm:.0f}" if rp else f"R{ld['rate_id']}"
                    else:
                        bpm_s = f"{ld.get('bpm', 60):.0f}"
                    # Size: pool ref or inline
                    if ld.get('size_id') and self._size_pool:
                        sp = self._size_pool.get(ld['size_id'])
                        sz_s = f"S{ld['size_id']}" if sp else f"S?"
                    else:
                        sz_s = f"sz{ld.get('size', 200):.0f}"
                    parts.append(f"{wave}/{ch} {bpm_s}♩ {sz_s}")
                fx_lbl = "  |  ".join(parts)
            else:
                fx_lbl = "—"

            try:
                dpg.configure_item(f"prog_name_{fid}", color=txt_col)
                dpg.set_value(f"prog_r_{fid}",   str(r)         if has_data else "—")
                dpg.configure_item(f"prog_r_{fid}", color=r_col)
                dpg.set_value(f"prog_g_{fid}",   str(g)         if has_data else "—")
                dpg.configure_item(f"prog_g_{fid}", color=g_col)
                dpg.set_value(f"prog_b_{fid}",   str(b)         if has_data else "—")
                dpg.configure_item(f"prog_b_{fid}", color=b_col)
                dpg.set_value(f"prog_dim_{fid}", f"{dim:.0%}"   if dim is not None else "—")
                dpg.configure_item(f"prog_dim_{fid}", color=txt_col)
                dpg.set_value(f"prog_fx_{fid}",  fx_lbl)
                dpg.configure_item(f"prog_fx_{fid}",
                                   color=_C_ACCENT if has_fx else _C_DIM)
                brightness = (r + g + b) / (3 * 255) * float(dim if dim is not None else 1.0)
                # When only FX is in programmer, show a fixed partial bar so it's visible
                bar_val = max(brightness, 0.25) if (has_fx and not (r or g or b)) else brightness
                dpg.set_value(f"prog_bar_{fid}", min(1.0, bar_val) if has_data else 0.0)
                fx_tag   = f"  ~FX" if has_fx else ""
                dpg.configure_item(f"prog_bar_{fid}",
                                   overlay=f"R{r} G{g} B{b}{fx_tag}" if has_data else "")
                # Tint programmer bar to match RGB color
                _pcached = self._prog_bar_themes.get(fid)
                if has_data and (r > 0 or g > 0 or b > 0):
                    if _pcached is None or _pcached[0] != (r, g, b):
                        if _pcached:
                            try: dpg.delete_item(_pcached[1])
                            except: pass
                        try:
                            with dpg.theme() as _pth:
                                with dpg.theme_component(dpg.mvProgressBar):
                                    dpg.add_theme_color(dpg.mvThemeCol_PlotHistogram,
                                                        (r, g, b, 255))
                            dpg.bind_item_theme(f"prog_bar_{fid}", _pth)
                            self._prog_bar_themes[fid] = ((r, g, b), _pth)
                        except: pass
                else:
                    if _pcached:
                        try:
                            dpg.bind_item_theme(f"prog_bar_{fid}", 0)
                            dpg.delete_item(_pcached[1])
                        except: pass
                        del self._prog_bar_themes[fid]
            except Exception:
                pass

        # Output monitor — sample first sub-fixture for RGB (pixel 1 of each tube),
        # master entry for dim. Keys are 'red'/'green'/'blue' throughout.
        for master in self._patch.all_fixtures():
            fid     = str(master.fixture_id)          # e.g. "1"
            sub_fid = f"{master.fixture_id}.1"        # e.g. "1.1" — first pixel

            # Dim lives on the master entry
            pl_master  = self._out.programmer_layer.get(fid, {})
            cue_merged = self._out._merged_cue_layer()
            cue_master = cue_merged.get(fid, {})
            dim = pl_master.get('dim', cue_master.get('dim', 1.0))

            # RGB lives on sub-fixture entries; use pixel 1 as representative
            pl_sub  = self._out.programmer_layer.get(sub_fid, {})
            cue_sub = cue_merged.get(sub_fid, {})
            fx_sub  = self._out.fx_layer.get(sub_fid, {})

            # Mirror the actual merger: programmer wins; otherwise cue+FX additive
            if 'red' in pl_sub:
                r = int(pl_sub['red'])
                g = int(pl_sub.get('green', 0))
                b = int(pl_sub.get('blue',  0))
            else:
                r = min(255, int(cue_sub.get('red',   0)) + int(fx_sub.get('red',   0)))
                g = min(255, int(cue_sub.get('green', 0)) + int(fx_sub.get('green', 0)))
                b = min(255, int(cue_sub.get('blue',  0)) + int(fx_sub.get('blue',  0)))

            dpg.set_value(f"out_r_{fid}",   str(r))
            dpg.set_value(f"out_g_{fid}",   str(g))
            dpg.set_value(f"out_b_{fid}",   str(b))
            dpg.set_value(f"out_dim_{fid}", f"{dim:.0%}")
            brightness = (r + g + b) / (3 * 255) * float(dim)
            dpg.set_value(f"out_bar_{fid}", min(1.0, brightness))
            dpg.configure_item(f"out_bar_{fid}", overlay=f"R{r} G{g} B{b}")
            # Tint output bar to match actual RGB color
            _ocached = self._out_bar_themes.get(fid)
            if r > 0 or g > 0 or b > 0:
                if _ocached is None or _ocached[0] != (r, g, b):
                    if _ocached:
                        try: dpg.delete_item(_ocached[1])
                        except: pass
                    try:
                        with dpg.theme() as _oth:
                            with dpg.theme_component(dpg.mvProgressBar):
                                dpg.add_theme_color(dpg.mvThemeCol_PlotHistogram,
                                                    (r, g, b, 255))
                        dpg.bind_item_theme(f"out_bar_{fid}", _oth)
                        self._out_bar_themes[fid] = ((r, g, b), _oth)
                    except: pass
            else:
                if _ocached:
                    try:
                        dpg.bind_item_theme(f"out_bar_{fid}", 0)
                        dpg.delete_item(_ocached[1])
                    except: pass
                    del self._out_bar_themes[fid]

        # MIDI status column (soft-takeover state)
        for (ch, cc), m in self._midi.cc_maps.items():
            tag = f"mr_st_cc_{ch}_{cc}"
            try:
                status = "live" if m.taken_over else "⧖ takeover"
                col    = _C_TEXT if m.taken_over else _C_DIM
                dpg.set_value(tag, status)
                dpg.configure_item(tag, color=col)
            except Exception:
                pass

        # MIDI clock sync — when active, apply detected BPM to all programmer FX layers
        if self._midi and getattr(self._midi, 'clock_sync', False):
            clk_bpm = self._midi.clock_bpm
            try:
                if clk_bpm is not None:
                    if not dpg.is_item_active("fx_rate"):
                        dpg.set_value("fx_rate", clk_bpm)
                    try:
                        dpg.set_value("fx_tap_label", f"{clk_bpm:.0f} bpm")
                    except Exception:
                        pass
                    now = time.monotonic()
                    for layer in self._fx._layers.values():
                        if layer.fx_id < 10000:
                            layer.set_rate_smooth(clk_bpm, now)
                    dpg.set_value("hdr_clock", f"CLK {clk_bpm:.0f}")
                    dpg.configure_item("hdr_clock", color=_C_ACCENT)
                else:
                    dpg.set_value("hdr_clock", "CLK …")
                    dpg.configure_item("hdr_clock", color=_C_DIM)
            except Exception:
                pass
        else:
            try:
                dpg.set_value("hdr_clock", "")
            except Exception:
                pass

        # OSC state feedback — broadcast at ~1 Hz (every ~20 ticks at 20Hz)
        self._osc_fb_counter = getattr(self, '_osc_fb_counter', 0) + 1
        if self._osc_fb_counter >= 20:
            self._osc_fb_counter = 0
            if self._osc and self._out and self._patch:
                self._osc.broadcast_state(self._out, self._executor_pool, self._patch)

    # ── Run ─────────────────────────────────────────────────

    def run(self):
        if not _DPG_OK:
            # Fall back to the old sleep loop
            try:
                while True:
                    time.sleep(0.1)
            except KeyboardInterrupt:
                pass
            return
        self.start_update_loop()
        self._load_popup_layout()   # restore saved popup positions/sizes
        dpg.focus_item("cmd_input")
        dpg.start_dearpygui()
        self._running = False   # signal update thread before destroying context
        time.sleep(0.1)         # give thread one tick to see the flag
        self._save_popup_layout()   # persist popup positions on clean exit
        try:
            save_show()
        except Exception:
            pass
        dpg.destroy_context()


# ============================================================
# STUDIO CONSOLE - Block 14: Show File Persistence
#
# Saves/loads the entire show state to studio_show.json so
# you don't re-record cues or re-wire MIDI on every startup.
#
# Saves:
#   cuestacks  — cue data, names, fade/delay times
#   MIDI CC    — mapping by target name (not callback ref)
#   MIDI Note  — same
#   FX params  — rate/size/spread knob positions
#   Groups     — fixture ID lists
#   state.json — master_level, active_executor, executor assignments + cue positions
#
# Does NOT save:
#   sACN/OSC   — set in code
#   live FX    — programmer preview layers (transient)
# ============================================================

# ── Data directory — one file per category ──────────────────
import shutil as _shutil

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(_SCRIPT_DIR, "studio_data")
SAVES_DIR   = os.path.join(_SCRIPT_DIR, "studio_saves")

if os.environ.get('STUDIO_HEADLESS') == '1':
    # Automated/unattended smoke-test runs must never read or overwrite the
    # real show — use a throwaway scratch directory so RECORD/GO/save_show
    # during the smoke test can't touch studio_data/*.json.
    import tempfile as _tempfile
    DATA_DIR = _tempfile.mkdtemp(prefix="studio_console_headless_")
    print(f"*** STUDIO_HEADLESS — using isolated scratch data dir (not your real show): {DATA_DIR} ***")

os.makedirs(DATA_DIR, exist_ok=True)

# Legacy single-file path (read-only — migrated on first run)
_LEGACY_FILE = os.path.join(_SCRIPT_DIR, "studio_show.json")


def _write_file(path, doc):
    """Backup the existing file then write doc as JSON."""
    if os.path.exists(path):
        _shutil.copy2(path, path + '.bak')
    with open(path, 'w') as f:
        json.dump(doc, f, indent=2)


def _read_file(path):
    """Return parsed JSON or None if missing/corrupt."""
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"  {os.path.basename(path)}: unreadable — {e}")
        return None


class ShowFile:
    VERSION    = "3.0"
    FX_SCALE   = 2       # bump when size/spread scale changes

    # ── Per-category file paths ──────────────────────────────
    CUESTACKS = os.path.join(DATA_DIR, "cuestacks.json")
    GROUPS    = os.path.join(DATA_DIR, "groups.json")
    COLORS    = os.path.join(DATA_DIR, "colors.json")
    DIMS      = os.path.join(DATA_DIR, "dims.json")
    MIDI      = os.path.join(DATA_DIR, "midi.json")
    FX        = os.path.join(DATA_DIR, "fx.json")
    FX_POOL   = os.path.join(DATA_DIR, "fx_pool.json")
    FORMS     = os.path.join(DATA_DIR, "forms.json")
    RATES     = os.path.join(DATA_DIR, "rate_pool.json")
    SIZES     = os.path.join(DATA_DIR, "size_pool.json")
    SPREADS   = os.path.join(DATA_DIR, "spread_pool.json")
    PATCH     = os.path.join(DATA_DIR, "patch.json")
    # Attribute pools — one file per attribute family
    POSITION  = os.path.join(DATA_DIR, "position_pool.json")
    GOBO      = os.path.join(DATA_DIR, "gobo_pool.json")
    ZOOM      = os.path.join(DATA_DIR, "zoom_pool.json")
    FOCUS     = os.path.join(DATA_DIR, "focus_pool.json")
    BEAM      = os.path.join(DATA_DIR, "beam_pool.json")
    CONTROL   = os.path.join(DATA_DIR, "control_pool.json")
    GDTF_DIR  = os.path.join(DATA_DIR, "gdtf")
    STATE     = os.path.join(DATA_DIR, "state.json")
    EXEC_PAGES   = os.path.join(DATA_DIR, "executor_pages.json")
    EXECUTORS    = os.path.join(DATA_DIR, "executors.json")
    CHANGELOG    = os.path.join(DATA_DIR, "changelog.json")

    # ── Save ────────────────────────────────────────────────

    @staticmethod
    def _migrate_fx_ld(ld):
        """Rescale a single FX layer dict from old (size 0-255, spread 0-1/10) to new 0-100."""
        sz = ld.get('size', 100.0)
        if sz > 100.0:
            ld['size'] = round((sz / 255.0) * 100.0, 1)
        sp = ld.get('spread', 0.0)
        if 0.0 < sp <= 10.0:
            ld['spread'] = min(100.0, round(sp * 100.0, 1))   # old 0-1.0 → new 0-100
        elif sp > 100.0:
            ld['spread'] = 100.0

    @staticmethod
    def _migrate_fx_scale(data):
        """Walk a cue data dict and migrate all embedded FX layer dicts."""
        for fvals in data.values():
            if not isinstance(fvals, dict):
                continue
            for ld in fvals.get('fx', []):
                ShowFile._migrate_fx_ld(ld)

    @staticmethod
    def save_cuestacks(cuestack_pool):
        doc = {"version": ShowFile.VERSION, "fx_scale": ShowFile.FX_SCALE, "cuestacks": {}}
        for sid, stack in cuestack_pool.stacks.items():
            cues_out = {}
            for num in stack._sorted_cue_numbers():
                cue = stack.cues[num]
                entry = {
                    "name":       cue.name,
                    "fade_time":  cue.fade_time,
                    "delay_time": cue.delay_time,
                    "data":       cue.data,
                }
                if cue.fade_times:
                    entry["fade_times"]  = cue.fade_times
                if cue.delay_times:
                    entry["delay_times"] = cue.delay_times
                cues_out[str(num)] = entry
            doc["cuestacks"][str(sid)] = {
                "name":            stack.name,
                "allow_exec_time": stack.allow_exec_time,
                "cues":            cues_out,
            }
        _write_file(ShowFile.CUESTACKS, doc)
        total = sum(len(s.cues) for s in cuestack_pool.stacks.values())
        print(f"  Saved cuestacks → {len(cuestack_pool.stacks)} stack(s), {total} cue(s)")

    @staticmethod
    def save_groups(group_pool):
        doc = {"version": ShowFile.VERSION, "groups": {}}
        for gid, group in group_pool.groups.items():
            doc["groups"][str(gid)] = {
                "name":    group.name,
                "members": [{"type": m[0], "fixture_id": m[1]} for m in group.members],
            }
        _write_file(ShowFile.GROUPS, doc)
        print(f"  Saved groups    → {len(group_pool.groups)}")

    @staticmethod
    def save_executor_pages(executor_pool):
        doc = {"version": ShowFile.VERSION, "pages": {}}
        for n, page in executor_pool.pages.items():
            doc["pages"][str(n)] = {
                "name":       page.get("name", f"Page {n}"),
                "cuestacks":  list(page.get("cuestacks", [])),
            }
        _write_file(ShowFile.EXEC_PAGES, doc)
        print(f"  Saved exec pages → {len(executor_pool.pages)}")

    @staticmethod
    def load_executor_pages(executor_pool):
        doc = _read_file(ShowFile.EXEC_PAGES)
        if not doc:
            return False
        for n_str, pdata in doc.get("pages", {}).items():
            n = int(n_str)
            # "slots" was the old key (executor IDs); "cuestacks" is the current key
            cuestacks = pdata.get("cuestacks", pdata.get("slots", []))
            executor_pool.pages[n] = {
                "name":      pdata.get("name", f"Page {n}"),
                "cuestacks": list(cuestacks),
            }
        print(f"  Loaded exec pages — {len(executor_pool.pages)}")
        return True

    @staticmethod
    def save_executors(executor_pool):
        """Persist executor slot assignments (cuestack, level, priority, trigger_mode)."""
        doc = {"version": ShowFile.VERSION, "executors": {}}
        for eid, ex in executor_pool.executors.items():
            cs_id = ex.cuestack.stack_id if ex.cuestack else None
            doc["executors"][str(eid)] = {
                "cuestack_id":  cs_id,
                "level":        ex.level,
                "priority":     ex.priority,
                "trigger_mode": ex.trigger_mode,
            }
        _write_file(ShowFile.EXECUTORS, doc)
        print(f"  Saved executors  → {len(doc['executors'])} slot(s)")

    @staticmethod
    def load_executors(executor_pool, cuestack_pool):
        """Re-wire executor→cuestack assignments and settings from disk."""
        doc = _read_file(ShowFile.EXECUTORS)
        if not doc:
            return False
        count = 0
        for eid_str, edata in doc.get("executors", {}).items():
            eid  = int(eid_str)
            ex   = executor_pool.get(eid)
            cs_id = edata.get("cuestack_id")
            if cs_id is not None:
                cs = cuestack_pool.get(int(cs_id))
                if cs:
                    executor_pool.assign(eid, cs)
                    count += 1
            ex.level        = float(edata.get("level",  1.0))
            ex.priority     = int(edata.get("priority", 0))
            ex.trigger_mode = edata.get("trigger_mode", "toggle")
        print(f"  Loaded executors — {count} assignment(s)")
        return True

    @staticmethod
    def save_colors(color_pool):
        doc = {"version": ShowFile.VERSION, "colors": {}}
        for pid, preset in color_pool.presets.items():
            doc["colors"][str(pid)] = {
                "name":  preset.name,
                "red":   preset.red,
                "green": preset.green,
                "blue":  preset.blue,
            }
        _write_file(ShowFile.COLORS, doc)
        print(f"  Saved colors    → {len(color_pool.presets)}")

    @staticmethod
    def save_dims(dim_pool):
        doc = {"version": ShowFile.VERSION, "dims": {}}
        for pid, preset in dim_pool.presets.items():
            doc["dims"][str(pid)] = {"name": preset.name, "level": preset.level}
        _write_file(ShowFile.DIMS, doc)
        print(f"  Saved dims      → {len(dim_pool.presets)}")

    @staticmethod
    def save_midi(midi):
        doc = {"version": ShowFile.VERSION, "midi_cc": [], "midi_note": []}
        for (ch, cc), m in midi.cc_maps.items():
            doc["midi_cc"].append({
                "channel": ch, "cc": cc, "target": m.name,
                "soft_takeover": m.soft_takeover,
                "software_val":  m.software_val,
                "taken_over":    m.taken_over,
            })
        for (ch, note), m in midi.note_maps.items():
            doc["midi_note"].append({"channel": ch, "note": note, "target": m.name})
        _write_file(ShowFile.MIDI, doc)
        print(f"  Saved midi      → {len(midi.cc_maps)} CC, {len(midi.note_maps)} note")

    @staticmethod
    def save_fx(fx_params):
        doc = {"version": ShowFile.VERSION, "fx_scale": ShowFile.FX_SCALE, "fx_params": dict(fx_params)}
        _write_file(ShowFile.FX, doc)

    @staticmethod
    def save_state(output_state, executor_pool, active_executor,
                   prog_time=None, fader_dim=0.0):
        """Save live session state: master level, active executor, exec→cuestack assignments."""
        execs = {}
        for eid, ex in executor_pool.executors.items():
            execs[str(eid)] = {
                "stack_id":  ex.cuestack.stack_id if ex.cuestack else None,
                "current":   ex.cuestack.current  if ex.cuestack else None,
                "priority":  ex.priority,
                "level":     ex.level,
                "time_on":   ex.time_override_on,
                "time_fade": ex.time_override_fade,
                "time_delay":ex.time_override_delay,
            }
        doc = {
            "version":        ShowFile.VERSION,
            "master_level":   output_state.master_level,
            "active_executor": active_executor[0] if active_executor else 1,
            "executors":      execs,
            "prog_time":      prog_time or {"on": False, "fade": 0.0, "delay": 0.0},
            "fader_dim":      float(fader_dim),
        }
        _write_file(ShowFile.STATE, doc)

    @staticmethod
    def load_state(output_state, executor_pool, cuestack_pool, active_executor,
                   prog_time=None, fader_dim=None):
        """Restore master level, active executor, and exec→cuestack assignments."""
        doc = _read_file(ShowFile.STATE)
        if not doc:
            return False
        output_state.master_level = float(doc.get("master_level", 1.0))
        if active_executor is not None:
            active_executor[0] = int(doc.get("active_executor", 1))
        for eid_str, edata in doc.get("executors", {}).items():
            eid = int(eid_str)
            sid = edata.get("stack_id")
            cur = edata.get("current")
            if sid is None:
                continue
            cs = cuestack_pool.get(sid)
            if cs:
                executor_pool.assign(eid, cs)
                if cur is not None:
                    cs.current = float(cur)
            ex = executor_pool.get(eid)
            ex.priority            = int(edata.get("priority", 0))
            ex.level               = float(edata.get("level", 1.0))
            ex.time_override_on    = bool(edata.get("time_on",    False))
            ex.time_override_fade  = edata.get("time_fade",  None)
            ex.time_override_delay = edata.get("time_delay", None)
        if prog_time is not None and "prog_time" in doc:
            pt = doc["prog_time"]
            prog_time['on']    = bool(pt.get('on',    False))
            prog_time['fade']  = float(pt.get('fade',  0.0))
            prog_time['delay'] = float(pt.get('delay', 0.0))
        if fader_dim is not None and "fader_dim" in doc:
            fader_dim[0] = float(doc["fader_dim"])
        print(f"  Loaded state    — master={output_state.master_level:.0%} "
              f"active_exec={active_executor[0] if active_executor else '?'}")
        return True

    # ── Load ────────────────────────────────────────────────

    @staticmethod
    def load_cuestacks(cuestack_pool, cue_pool):
        doc = _read_file(ShowFile.CUESTACKS)
        if not doc:
            return False
        needs_migration = doc.get("fx_scale", 1) < ShowFile.FX_SCALE
        for sid_str, sdata in doc.get("cuestacks", {}).items():
            sid   = int(sid_str)
            stack = CueStack(sid, sdata["name"])
            stack.allow_exec_time = bool(sdata.get("allow_exec_time", True))
            for num_str, cdata in sdata["cues"].items():
                num      = float(num_str)
                cue      = Cue(num, cdata["name"],
                               cdata.get("fade_time", 2.0),
                               cdata.get("delay_time", 0.0),
                               cdata.get("fade_times"),
                               cdata.get("delay_times"))
                cue.data = copy.deepcopy(cdata["data"])
                if needs_migration:
                    ShowFile._migrate_fx_scale(cue.data)
                stack.cues[num] = cue
                if num == int(num):   # decimal cues have no panel button
                    cue_pool.store(int(num), cue)
            cuestack_pool.store(sid, stack)
        total = sum(len(s.cues) for s in cuestack_pool.stacks.values())
        if needs_migration:
            print(f"  Migrated FX scale (0-255/0-1 → 0-100) in {total} cue(s)")
        print(f"  Loaded cuestacks — {len(cuestack_pool.stacks)} stack(s), {total} cue(s)")
        return True

    @staticmethod
    def load_groups(group_pool):
        doc = _read_file(ShowFile.GROUPS)
        if not doc:
            return False
        for gid_str, gdata in doc.get("groups", {}).items():
            gid   = int(gid_str)
            group = Group(gid, gdata.get("name", f"Group {gid}"))
            group.members = [(m["type"], m["fixture_id"])
                             for m in gdata.get("members", [])]
            group_pool.groups[gid] = group
        print(f"  Loaded groups   — {len(group_pool.groups)}")
        return True

    @staticmethod
    def load_colors(color_pool):
        doc = _read_file(ShowFile.COLORS)
        if not doc:
            return False
        for pid_str, pdata in doc.get("colors", {}).items():
            pid    = int(pid_str)
            preset = ColorPreset(pid, pdata.get("name", f"Color {pid}"))
            if "data" in pdata:
                # Migrate old per-fixture format: sample first entry
                for fdata in pdata["data"].values():
                    preset.red   = fdata.get("red",   0)
                    preset.green = fdata.get("green", 0)
                    preset.blue  = fdata.get("blue",  0)
                    break
            else:
                preset.red   = pdata.get("red",   0)
                preset.green = pdata.get("green", 0)
                preset.blue  = pdata.get("blue",  0)
            color_pool.presets[pid] = preset
        print(f"  Loaded colors   — {len(color_pool.presets)}")
        return True

    @staticmethod
    def load_dims(dim_pool):
        doc = _read_file(ShowFile.DIMS)
        if not doc:
            return False
        for pid_str, pdata in doc.get("dims", {}).items():
            pid    = int(pid_str)
            preset = DimmerPreset(pid, pdata.get("name", f"Dimmer {pid}"))
            if "data" in pdata:
                # Migrate old per-fixture format: sample first entry
                for fdata in pdata["data"].values():
                    preset.level = fdata.get("dim", 0.0)
                    break
            else:
                preset.level = pdata.get("level", 0.0)
            dim_pool.presets[pid] = preset
        print(f"  Loaded dims     — {len(dim_pool.presets)}")
        return True

    @staticmethod
    def load_midi(doc, midi, target_registry):
        """doc is already-parsed JSON (passed in because MIDI restore must happen
        after target_registry is built, which is after GUI setup)."""
        if not doc:
            return
        midi.clear_maps()
        skipped = 0
        for entry in doc.get("midi_cc", []):
            name = entry["target"]
            if name not in target_registry:
                skipped += 1
                continue
            reg = target_registry[name]
            m = midi.map_cc(entry["channel"], entry["cc"], reg[0],
                            name=name,
                            soft_takeover=entry.get("soft_takeover", reg[1]))
            m.software_val = entry.get("software_val", 0.0)
            m.taken_over   = entry.get("taken_over",   not reg[1])
        for entry in doc.get("midi_note", []):
            name = entry["target"]
            if name not in target_registry:
                skipped += 1
                continue
            reg    = target_registry[name]
            off_cb = reg[3] if len(reg) > 3 else None
            midi.map_note(entry["channel"], entry["note"], reg[0], off_cb, name=name)
        s = f", {skipped} skipped" if skipped else ""
        print(f"  Loaded midi     — {len(midi.cc_maps)} CC, {len(midi.note_maps)} note{s}")

    @staticmethod
    def load_fx(fx_params):
        doc = _read_file(ShowFile.FX)
        if doc and doc.get("fx_params"):
            p = doc["fx_params"]
            if doc.get("fx_scale", 1) < ShowFile.FX_SCALE:
                sz = p.get('size', 100.0)
                if sz > 100.0:
                    p['size'] = round((sz / 255.0) * 100.0, 1)
                sp = p.get('spread', 0.0)
                if 0.0 < sp <= 10.0:
                    p['spread'] = min(100.0, round(sp * 100.0, 1))
            fx_params.update(p)

    @staticmethod
    def save_fx_pool(fx_pool):
        doc = {"version": ShowFile.VERSION, "fx_scale": ShowFile.FX_SCALE, "fx_presets": {}}
        for pid, preset in fx_pool.presets.items():
            layers_out = []
            for ld in preset.layers:
                layers_out.append({
                    'waveform':     ld.get('waveform', 'sine'),
                    'channel':      ld.get('channel', 'red'),
                    'bpm':          ld.get('bpm', 60.0),
                    'size':         ld.get('size', 100.0),
                    'spread':       ld.get('spread', 0.0),
                    'phase_offset': ld.get('phase_offset', 0.0),
                    'form_id':      ld.get('form_id'),
                    'rate_id':      ld.get('rate_id'),
                    'size_id':      ld.get('size_id'),
                    'spread_id':    ld.get('spread_id'),
                    'dim_id':       ld.get('dim_id'),
                    'color_id':     ld.get('color_id'),
                    'group_id':     ld.get('group_id'),
                    'block_size':   ld.get('block_size', 1),
                    'order':        ld.get('order', 'linear'),
                    'direction':    ld.get('direction', 'forward'),
                    'target_scope': ld.get('target_scope'),
                })
            doc["fx_presets"][str(pid)] = {"name": preset.name, "layers": layers_out}
        _write_file(ShowFile.FX_POOL, doc)
        print(f"  Saved fx_pool   → {len(fx_pool.presets)}")

    @staticmethod
    def load_fx_pool(fx_pool):
        doc = _read_file(ShowFile.FX_POOL)
        if not doc:
            return False
        needs_migration = doc.get("fx_scale", 1) < ShowFile.FX_SCALE
        for pid_str, pdata in doc.get("fx_presets", {}).items():
            pid    = int(pid_str)
            preset = FXPreset(pid, pdata.get("name", f"FX {pid}"))
            for ld in pdata.get("layers", []):
                if needs_migration:
                    ShowFile._migrate_fx_ld(ld)
                preset.add_layer(
                    ld["waveform"], ld["channel"],
                    bpm          = ld.get("bpm", ld.get("rate_bpm", 60.0)),
                    size         = ld.get("size",         100.0),
                    spread       = ld.get("spread",         0.0),
                    phase_offset = ld.get("phase_offset",   0.0),
                    form_id      = ld.get("form_id"),
                    rate_id      = ld.get("rate_id"),
                    size_id      = ld.get("size_id"),
                    spread_id    = ld.get("spread_id"),
                    dim_id       = ld.get("dim_id"),
                    color_id     = ld.get("color_id"),
                    group_id     = ld.get("group_id"),
                    block_size   = ld.get("block_size",     1),
                    order        = ld.get("order",   "linear"),
                    direction    = ld.get("direction","forward"),
                    target_scope = ld.get("target_scope"),
                )
            fx_pool.store(pid, preset)
        print(f"  Loaded fx_pool  — {len(fx_pool.presets)}")
        return True

    @staticmethod
    def save_forms(form_pool):
        """Only persist custom (non-builtin) forms — builtins are always reconstructed."""
        custom = form_pool.custom_forms()
        doc = {"version": ShowFile.VERSION, "forms": {}}
        for fid, form in custom.items():
            doc["forms"][str(fid)] = {
                "name":        form.name,
                "form_type":   form.form_type,
                "breakpoints": form.breakpoints,
            }
        _write_file(ShowFile.FORMS, doc)
        print(f"  Saved forms     → {len(custom)} custom")

    @staticmethod
    def load_forms(form_pool):
        doc = _read_file(ShowFile.FORMS)
        if not doc:
            return False
        for fid_str, fdata in doc.get("forms", {}).items():
            fid  = int(fid_str)
            form = FormPreset(
                fid,
                fdata.get("name", f"Form {fid}"),
                fdata.get("form_type", "breakpoints"),
                breakpoints=fdata.get("breakpoints", []),
            )
            form_pool.store(fid, form)
        n = len(doc.get("forms", {}))
        if n:
            print(f"  Loaded forms    — {n} custom")
        return True

    @staticmethod
    def save_rate_pool(rate_pool):
        doc = {"version": ShowFile.VERSION, "rate_presets": {}}
        for pid, p in rate_pool.presets.items():
            doc["rate_presets"][str(pid)] = {"name": p.name, "bpm": p.bpm}
        _write_file(ShowFile.RATES, doc)
        print(f"  Saved rate_pool  → {len(rate_pool.presets)}")

    @staticmethod
    def load_rate_pool(rate_pool):
        doc = _read_file(ShowFile.RATES)
        if not doc: return False
        for pid_str, pd in doc.get("rate_presets", {}).items():
            pid = int(pid_str)
            rate_pool.store(pid, RatePreset(pid, pd.get("name", f"Rate {pid}"),
                                            pd.get("bpm", 60.0)))
        n = len(doc.get("rate_presets", {}))
        if n: print(f"  Loaded rate_pool — {n}")
        return True

    @staticmethod
    def save_size_pool(size_pool):
        doc = {"version": ShowFile.VERSION, "size_presets": {}}
        for pid, p in size_pool.presets.items():
            doc["size_presets"][str(pid)] = {"name": p.name, "size": p.size}
        _write_file(ShowFile.SIZES, doc)
        print(f"  Saved size_pool  → {len(size_pool.presets)}")

    @staticmethod
    def load_size_pool(size_pool):
        doc = _read_file(ShowFile.SIZES)
        if not doc: return False
        for pid_str, pd in doc.get("size_presets", {}).items():
            pid = int(pid_str)
            size_pool.store(pid, SizePreset(pid, pd.get("name", f"Size {pid}"),
                                            pd.get("size", 200.0)))
        n = len(doc.get("size_presets", {}))
        if n: print(f"  Loaded size_pool — {n}")
        return True

    @staticmethod
    def save_spread_pool(spread_pool):
        doc = {"version": ShowFile.VERSION, "spread_presets": {}}
        for pid, p in spread_pool.presets.items():
            doc["spread_presets"][str(pid)] = {"name": p.name, "spread": p.spread}
        _write_file(ShowFile.SPREADS, doc)
        print(f"  Saved spread_pool → {len(spread_pool.presets)}")

    @staticmethod
    def load_spread_pool(spread_pool):
        doc = _read_file(ShowFile.SPREADS)
        if not doc: return False
        for pid_str, pd in doc.get("spread_presets", {}).items():
            pid = int(pid_str)
            spread_pool.store(pid, SpreadPreset(pid, pd.get("name", f"Spread {pid}"),
                                                pd.get("spread", 1.0)))
        n = len(doc.get("spread_presets", {}))
        if n: print(f"  Loaded spread_pool — {n}")
        return True

    # ── Generic attribute pools ──────────────────────────────

    @staticmethod
    def save_attribute_pool(pool, path):
        """Persist any AttributePool to the given JSON path."""
        doc = {
            "version":   ShowFile.VERSION,
            "attribute": pool.attribute,
            "presets":   {str(pid): p.to_dict() for pid, p in pool.presets.items()},
        }
        _write_file(path, doc)
        print(f"  Saved {pool.attribute} pool → {len(pool.presets)} preset(s)")

    @staticmethod
    def load_attribute_pool(pool, path):
        """Restore an AttributePool from its JSON file."""
        doc = _read_file(path)
        if not doc:
            return False
        for pdata in doc.get("presets", {}).values():
            p = AttributePreset.from_dict(pdata)
            pool.presets[p.preset_id] = p
        print(f"  Loaded {pool.attribute} pool — {len(pool.presets)} preset(s)")
        return True

    # Convenience wrappers so call sites don't need to know the path

    @staticmethod
    def save_position_pool(pool):
        ShowFile.save_attribute_pool(pool, ShowFile.POSITION)

    @staticmethod
    def load_position_pool(pool):
        return ShowFile.load_attribute_pool(pool, ShowFile.POSITION)

    @staticmethod
    def save_gobo_pool(pool):
        ShowFile.save_attribute_pool(pool, ShowFile.GOBO)

    @staticmethod
    def load_gobo_pool(pool):
        return ShowFile.load_attribute_pool(pool, ShowFile.GOBO)

    @staticmethod
    def save_zoom_pool(pool):
        ShowFile.save_attribute_pool(pool, ShowFile.ZOOM)

    @staticmethod
    def load_zoom_pool(pool):
        return ShowFile.load_attribute_pool(pool, ShowFile.ZOOM)

    @staticmethod
    def save_focus_pool(pool):
        ShowFile.save_attribute_pool(pool, ShowFile.FOCUS)

    @staticmethod
    def load_focus_pool(pool):
        return ShowFile.load_attribute_pool(pool, ShowFile.FOCUS)

    @staticmethod
    def save_beam_pool(pool):
        ShowFile.save_attribute_pool(pool, ShowFile.BEAM)

    @staticmethod
    def load_beam_pool(pool):
        return ShowFile.load_attribute_pool(pool, ShowFile.BEAM)

    @staticmethod
    def save_control_pool(pool):
        ShowFile.save_attribute_pool(pool, ShowFile.CONTROL)

    @staticmethod
    def load_control_pool(pool):
        return ShowFile.load_attribute_pool(pool, ShowFile.CONTROL)

    # ── Legacy migration ─────────────────────────────────────

    @staticmethod
    def save_patch(patch):
        fixtures = []
        for master in patch.all_fixtures():
            # Collect primary output from first sub-fixture
            first_sub = next(iter(master.sub_fixtures.values()), None)
            if not first_sub or not first_sub.outputs:
                continue
            primary = first_sub.outputs[0]
            extra = first_sub.outputs[1:] if len(first_sub.outputs) > 1 else []
            fixtures.append({
                "fixture_id":    master.fixture_id,
                "name":          master.name,
                "profile":       master.profile.name,
                "universe":      primary["universe"],
                "start_address": primary["address"],
                "extra_outputs": [{"universe": o["universe"], "address": o["address"] - (primary["address"] - 1)}
                                  for o in extra],
            })
        doc = {"version": ShowFile.VERSION, "fixtures": fixtures}
        _write_file(ShowFile.PATCH, doc)
        print(f"  Saved patch     → {len(fixtures)} fixture(s)")

    @staticmethod
    def load_patch(patch):
        doc = _read_file(ShowFile.PATCH)
        if not doc:
            return False
        for f in doc.get("fixtures", []):
            patch.patch_fixture(
                fixture_id    = int(f["fixture_id"]),
                name          = f.get("name", f"Fixture {f['fixture_id']}"),
                profile_name  = f.get("profile", "Generic_RGB"),
                universe      = int(f.get("universe", 1)),
                start_address = int(f.get("start_address", 1)),
                extra_outputs = f.get("extra_outputs") or None,
            )
        print(f"  Loaded patch    — {len(patch.fixtures)} fixture(s)")
        return True

    @staticmethod
    def migrate_legacy(cuestack_pool, cue_pool, group_pool, color_pool, dim_pool, fx_params):
        """Read old studio_show.json and write to new per-file format, then rename it."""
        if not os.path.exists(_LEGACY_FILE):
            return False
        try:
            with open(_LEGACY_FILE) as f:
                old = json.load(f)
        except Exception:
            return False

        print("  Migrating studio_show.json → studio_data/ ...")

        # Cuestacks
        if old.get("cuestacks"):
            for sid_str, sdata in old["cuestacks"].items():
                sid   = int(sid_str)
                stack = CueStack(sid, sdata["name"])
                for num_str, cdata in sdata["cues"].items():
                    num      = float(num_str)
                    cue      = Cue(num, cdata["name"],
                                   cdata.get("fade_time", 2.0),
                                   cdata.get("delay_time", 0.0),
                                   cdata.get("fade_times"),
                                   cdata.get("delay_times"))
                    cue.data = copy.deepcopy(cdata["data"])
                    stack.cues[num] = cue
                    if num == int(num):
                        cue_pool.store(int(num), cue)
                cuestack_pool.store(sid, stack)
            ShowFile.save_cuestacks(cuestack_pool)

        # Groups
        for gid_str, gdata in old.get("groups", {}).items():
            gid   = int(gid_str)
            group = Group(gid, gdata.get("name", f"Group {gid}"))
            group.members = [(m["type"], m["fixture_id"])
                             for m in gdata.get("members", [])]
            group_pool.groups[gid] = group
        if group_pool.groups:
            ShowFile.save_groups(group_pool)

        # Colors
        for pid_str, pdata in old.get("color_presets", {}).items():
            pid    = int(pid_str)
            preset = ColorPreset(pid, pdata.get("name", f"Color {pid}"))
            preset.data = pdata.get("data", {})
            color_pool.presets[pid] = preset
        if color_pool.presets:
            ShowFile.save_colors(color_pool)

        # Dims
        for pid_str, pdata in old.get("dim_presets", {}).items():
            pid    = int(pid_str)
            preset = DimmerPreset(pid, pdata.get("name", f"Dimmer {pid}"))
            preset.data = pdata.get("data", {})
            dim_pool.presets[pid] = preset
        if dim_pool.presets:
            ShowFile.save_dims(dim_pool)

        # FX
        if old.get("fx_params"):
            fx_params.update(old["fx_params"])
            ShowFile.save_fx(fx_params)

        # Rename old file so we don't migrate twice
        _shutil.move(_LEGACY_FILE, _LEGACY_FILE + '.migrated')
        if os.path.exists(_LEGACY_FILE + '.bak'):
            _shutil.move(_LEGACY_FILE + '.bak', _LEGACY_FILE + '.bak.migrated')
        print("  Migration complete — studio_show.json renamed to .migrated")
        return True


# ============================================================
# STUDIO CONSOLE — Live Session
# Cuestack 1 / Axiom 25 MkII mapped
# ============================================================

# ----------------------------------------------------------
# Setup
# ----------------------------------------------------------

library = FixtureLibrary()

# Load JSON profiles from profiles/ folder (custom fixtures without touching code)
library.load_from_folder(os.path.join(DATA_DIR, "profiles"))

# Load GDTF fixtures — drop .gdtf files into studio_data/gdtf/ to auto-import
os.makedirs(ShowFile.GDTF_DIR, exist_ok=True)
library.load_gdtf_folder(ShowFile.GDTF_DIR)

patch   = Patch(library)

if not ShowFile.load_patch(patch):
    # First-run defaults — 6 SGM RGB 54-pixel tubes across two universes
    patch.patch_fixture(1, "Tube 1", "SGM_RGB_54", universe=1, start_address=1)
    patch.patch_fixture(2, "Tube 2", "SGM_RGB_54", universe=1, start_address=163)
    patch.patch_fixture(3, "Tube 3", "SGM_RGB_54", universe=1, start_address=325)
    patch.patch_fixture(4, "Tube 4", "SGM_RGB_54", universe=2, start_address=1)
    patch.patch_fixture(5, "Tube 5", "SGM_RGB_54", universe=2, start_address=163)
    patch.patch_fixture(6, "Tube 6", "SGM_RGB_54", universe=2, start_address=325)
    ShowFile.save_patch(patch)

prog         = Programmer(patch)
group_pool   = GroupPool()
color_pool   = ColorPool()
dim_pool     = DimmerPool()
output_state = OutputState(patch)
output_state.link_programmer(prog)
_blackout_saved_level = [1.0]   # saved master level before BLACKOUT; shared mutable ref
executor_pool = ExecutorPool()
output_state.link_executor_pool(executor_pool)
fade_engine  = FadeEngine()
form_pool    = FormPool()   # built-ins pre-seeded; custom forms loaded below
rate_pool    = RatePool()
size_pool    = SizePool()
spread_pool  = SpreadPool()
fx_engine    = FXEngine(output_state, form_pool=form_pool,
                        rate_pool=rate_pool, size_pool=size_pool,
                        spread_pool=spread_pool, dim_pool=dim_pool)
# Wire fx_engine + form_pool into executor_pool so new executors inherit them
executor_pool.default_fx_engine  = fx_engine
executor_pool.default_form_pool  = form_pool
executor_pool.default_color_pool = color_pool
executor_pool.default_dim_pool   = dim_pool
executor_pool.default_group_pool = group_pool
# STUDIO_DRY_RUN=1 disables real sACN output (no socket, nothing sent to the
# tubes) while still running the full FX/cue/output pipeline — used for
# unattended/automated testing. STUDIO_HEADLESS=1 additionally skips the
# blocking DearPyGui window (see the GUI launch block near the end of file).
STUDIO_DRY_RUN  = os.environ.get('STUDIO_DRY_RUN')  == '1'
STUDIO_HEADLESS = os.environ.get('STUDIO_HEADLESS') == '1'
if STUDIO_DRY_RUN:
    print("*** STUDIO_DRY_RUN active — sACN output disabled, no data sent to fixtures ***")

network      = NetworkEngine(output_state, universes=[1, 2],
                             bind_address="192.168.1.161",
                             dry_run=STUDIO_DRY_RUN)
network.start()

midi = MIDIEngine()
MIDIEngine.list_ports()
midi.start(port=1)  # Axiom 25 Axiom USB In

# OSC engine
# Port 8000 is grandMA3's OSC port — Studio Console uses 8001 so
# both can run at the same time during transition.
# When you fully replace MA3, stop app_gma3 and switch to port 8000.
osc = OSCEngine()
osc.start(port=8001)

# Lightform Creator — update IP to match your Lightform machine
# Leave commented if Lightform isn't running yet
# osc.add_target("lightform", "192.168.1.XXX", 9000)

osc.list_targets()

all_subs = [sub for master in patch.all_fixtures() for sub in master.all_subs()]

# ----------------------------------------------------------
# State tracking (defined before show-file load so it can
# be updated from the file's saved fx_params)
# ----------------------------------------------------------

active_fx    = []    # programmer preview FX layer objects (while editing)
_prog_fx_ids = []    # FX engine layer IDs for programmer preview (cleared on CLEAR stage 2)
_fader_dim   = [0.0] # last dim value from fader (for flash restore)

def _stop_prog_fx_preview():
    """Stop programmer preview FX layers without wiping prog.data['fx'] entries."""
    for fxid in _prog_fx_ids:
        fx_engine.remove(fxid)
    _prog_fx_ids.clear()
    active_fx.clear()

_fx_params = {
    'rate_bpm': 60.0,
    'size':     100.0,   # 0-100 (100 = full DMX 255)
    'spread':   0.0,     # 0-100 (100 = full 1-cycle phase spread)
    'infade':   0.0,
    'outfade':  0.0,
}

# ----------------------------------------------------------
# Pools — Cues and Cuestacks (executors)
# ----------------------------------------------------------

cue_pool       = CuePool()
cuestack_pool  = CueStackPool()
fx_pool        = FXPool()
active_executor = [1]   # list so closures can rebind it

# Programmer time override — when on, overrides cue fade/delay for manually fired cues
_prog_time = {
    'on':    False,
    'fade':  0.0,
    'delay': 0.0,
}

# Attribute preset pools — extend this list as new fixture types are added
position_pool = AttributePool("position", ["pan", "tilt", "pan_fine", "tilt_fine"])
gobo_pool     = AttributePool("gobo",     ["gobo", "gobo_rot", "gobo2", "gobo2_rot"])
zoom_pool     = AttributePool("zoom",     ["zoom"])
focus_pool    = AttributePool("focus",    ["focus"])
beam_pool     = AttributePool("beam",     ["iris", "shutter1", "strobe"])
control_pool  = AttributePool("control",  ["control", "macro", "prism", "frost", "animation"])

# Wire attribute pools into executor_pool now that they exist
_attr_pools = {
    "position": position_pool,
    "gobo":     gobo_pool,
    "zoom":     zoom_pool,
    "focus":    focus_pool,
    "beam":     beam_pool,
    "control":  control_pool,
}
executor_pool.default_attr_pools = _attr_pools

# ── Load all data files (migrate legacy file if present) ──
ShowFile.load_fx(_fx_params)
ShowFile.load_fx_pool(fx_pool)
ShowFile.load_forms(form_pool)
ShowFile.load_rate_pool(rate_pool)
ShowFile.load_size_pool(size_pool)
ShowFile.load_spread_pool(spread_pool)
ShowFile.load_groups(group_pool)
ShowFile.load_colors(color_pool)
ShowFile.load_dims(dim_pool)
_cs_loaded = ShowFile.load_cuestacks(cuestack_pool, cue_pool)
ShowFile.load_position_pool(position_pool)
ShowFile.load_gobo_pool(gobo_pool)
ShowFile.load_zoom_pool(zoom_pool)
ShowFile.load_focus_pool(focus_pool)
ShowFile.load_beam_pool(beam_pool)
ShowFile.load_control_pool(control_pool)
ShowFile.load_executor_pages(executor_pool)
ShowFile.load_executors(executor_pool, cuestack_pool)
ShowFile.load_state(output_state, executor_pool, cuestack_pool, active_executor,
                    prog_time=_prog_time, fader_dim=_fader_dim)

# Migrate old single-file if new files don't exist yet
if not _cs_loaded:
    _migrated = ShowFile.migrate_legacy(
        cuestack_pool, cue_pool, group_pool, color_pool, dim_pool, _fx_params)
    if not _migrated:
        # ── First-run factory defaults ─────────────────────────────────
        # Helper to set all fixtures to a colour quickly
        def _set_all(r, g, b, dim=100):
            prog.execute(f"1 THRU 6 AT FULL")
            prog.execute(f"1 THRU 6 AT R {r}")
            prog.execute(f"1 THRU 6 AT G {g}")
            prog.execute(f"1 THRU 6 AT B {b}")
            if dim != 100:
                prog.execute(f"1 THRU 6 AT DIM {dim}")

        # ── Custom Forms (slots 5-8) ──────────────────────────────────
        form_pool.store(5, FormPreset(5, "Bounce",
            form_type='breakpoints',
            breakpoints=[[0.0,0.0],[0.1,1.0],[1.0,0.0]]))

        form_pool.store(6, FormPreset(6, "Heartbeat",
            form_type='breakpoints',
            breakpoints=[[0.0,0.0],[0.05,1.0],[0.12,0.0],
                         [0.22,0.8],[0.30,0.0],[1.0,0.0]]))

        form_pool.store(7, FormPreset(7, "Spike",
            form_type='breakpoints',
            breakpoints=[[0.0,0.0],[0.03,1.0],[0.06,0.0],[1.0,0.0]]))

        form_pool.store(8, FormPreset(8, "Trapezoid",
            form_type='breakpoints',
            breakpoints=[[0.0,0.0],[0.2,1.0],[0.65,1.0],[0.85,0.0],[1.0,0.0]]))

        ShowFile.save_forms(form_pool)

        # ── FX Pool (slots 1-8) ───────────────────────────────────────
        def _fx(pid, name, layers):
            p = FXPreset(pid, name)
            for lyr in layers:
                p.add_layer(*lyr[0:2], rate_bpm=lyr[2], size=lyr[3], spread=lyr[4],
                            form_id=lyr[5] if len(lyr) > 5 else None)
            return p

        fx_pool.store(1, _fx(1, "Red Sine",    [("sine",  "red",   60,  220, 1.0)]))
        fx_pool.store(2, _fx(2, "Blue Sine",   [("sine",  "blue",  60,  220, 1.0)]))
        fx_pool.store(3, _fx(3, "Magenta Sine",[("sine",  "red",   60,  200, 1.0),
                                                ("sine",  "blue",  60,  200, 1.0)]))
        fx_pool.store(4, _fx(4, "White Pulse", [("pulse", "red",   90,  200, 0.0),
                                                ("pulse", "green", 90,  200, 0.0),
                                                ("pulse", "blue",  90,  200, 0.0)]))
        fx_pool.store(5, _fx(5, "RGB Chase",   [("sine",  "red",   50,  180, 0.33),
                                                ("sine",  "green", 50,  180, 0.33),
                                                ("sine",  "blue",  50,  180, 0.33)]))
        fx_pool.store(6, _fx(6, "Green Sine",  [("sine",  "green", 60,  220, 1.0)]))
        fx_pool.store(7, _fx(7, "Strobe",      [("pulse", "red",   240, 255, 0.0),
                                                ("pulse", "green", 240, 255, 0.0),
                                                ("pulse", "blue",  240, 255, 0.0)]))

        p8 = FXPreset(8, "Bounce Red+Blue")
        p8.add_layer("sine", "red",  50, 210, 1.0, form_id=5)
        p8.add_layer("sine", "blue", 50, 210, 1.0, form_id=5)
        fx_pool.store(8, p8)

        ShowFile.save_fx_pool(fx_pool)

        # ── Cuestack 1: Color Show ────────────────────────────────────
        cs1 = CueStack(1, "Color Show")

        _set_all(255, 0, 0)
        cs1.record_cue(1, prog, name="Red", fade_time=2.0)
        prog.execute("CLEAR")

        _set_all(0, 0, 255)
        cs1.record_cue(2, prog, name="Blue", fade_time=2.0)
        prog.execute("CLEAR")

        _set_all(0, 200, 0)
        cs1.record_cue(3, prog, name="Green", fade_time=2.0)
        prog.execute("CLEAR")

        _set_all(0, 200, 200)
        cs1.record_cue(4, prog, name="Cyan", fade_time=2.0)
        prog.execute("CLEAR")

        _set_all(0, 0, 0, dim=0)
        cs1.record_cue(5, prog, name="Off", fade_time=2.0)
        prog.execute("CLEAR")

        # ── Cuestack 2: Dynamic ───────────────────────────────────────
        cs2 = CueStack(2, "Dynamic")

        _set_all(255, 255, 255)
        cs2.record_cue(1, prog, name="White Full", fade_time=1.5)
        prog.execute("CLEAR")

        _set_all(255, 80, 0)
        cs2.record_cue(2, prog, name="Amber", fade_time=1.5)
        prog.execute("CLEAR")

        _set_all(0, 0, 180)
        cs2.record_cue(3, prog, name="Deep Blue", fade_time=1.5)
        prog.execute("CLEAR")

        _set_all(200, 0, 200)
        cs2.record_cue(4, prog, name="Magenta", fade_time=1.5)
        prog.execute("CLEAR")

        _set_all(0, 0, 0, dim=0)
        cs2.record_cue(5, prog, name="Fade Out", fade_time=3.0)
        prog.execute("CLEAR")

        # ── Cuestack 3: Warm Tones ────────────────────────────────────
        cs3 = CueStack(3, "Warm")

        _set_all(255, 30, 0)
        cs3.record_cue(1, prog, name="Hot Red", fade_time=2.0)
        prog.execute("CLEAR")

        _set_all(255, 100, 0)
        cs3.record_cue(2, prog, name="Orange", fade_time=2.0)
        prog.execute("CLEAR")

        _set_all(255, 160, 60)
        cs3.record_cue(3, prog, name="Warm Amber", fade_time=2.0)
        prog.execute("CLEAR")

        _set_all(220, 60, 80)
        cs3.record_cue(4, prog, name="Soft Pink", fade_time=2.0)
        prog.execute("CLEAR")

        _set_all(0, 0, 0, dim=0)
        cs3.record_cue(5, prog, name="Out", fade_time=3.0)
        prog.execute("CLEAR")

        # ── Store everything ─────────────────────────────────────────
        for _cs in (cs1, cs2, cs3):
            cuestack_pool.store(_cs.stack_id, _cs)
            for _cnum, _cue in _cs.cues.items():
                if _cnum == int(_cnum):
                    cue_pool.store(int(_cnum), _cue)
            _cs.print_stack()

        ShowFile.save_cuestacks(cuestack_pool)

cs1 = cuestack_pool.get(1) or CueStack(1, "Cuestack 1")
cuestack_pool.store(1, cs1)

# Wire every loaded cuestack into an executor slot (1:1 by default)
for _slot, _stack in cuestack_pool.stacks.items():
    executor_pool.assign(_slot, _stack)

# CLEAR rebinds prog.data — re-link so programmer_layer points
# to the fresh empty dict, not the old one with stale values.
output_state.link_programmer(prog)

def _active_stack():
    """Returns the CueStack for the current active executor."""
    return cuestack_pool.get(active_executor[0])

def _active_executor():
    """Returns the Executor object for the current active executor."""
    return executor_pool.get(active_executor[0])

# ----------------------------------------------------------
# FX helpers — called by cue fire and manual pads
# ----------------------------------------------------------

def _start_magenta_sine():
    fx_engine.clear()
    active_fx.clear()
    r = fx_engine.add(1, 'sine', 'red',  rate_bpm=_fx_params['rate_bpm'],
                      size=_fx_params['size'], targets=all_subs,
                      spread=_fx_params['spread'])
    b = fx_engine.add(2, 'sine', 'blue', rate_bpm=_fx_params['rate_bpm'],
                      size=_fx_params['size'], targets=all_subs,
                      spread=_fx_params['spread'])
    active_fx.extend([r, b])
    print(f"\n  FX: magenta sine  "
          f"{_fx_params['rate_bpm']:.0f}BPM  "
          f"size={_fx_params['size']:.0f}  "
          f"spread={_fx_params['spread']:.2f}")

def _stop_fx():
    # Programmer-based kill: sets fx_kill in programmer so CLEAR can release it.
    # Equivalent to typing KILL FX at the command line.
    run_command("KILL FX")

# Lightform OSC map — what to send to Lightform when each cue fires.
# Edit the address/value to match your Lightform Creator OSC setup.
# These are sent automatically every time a cue fires.
LIGHTFORM_CUE_MAP = {
    1.0: ("/lightform/layer/show", 1),   # Cue 1 Red   → Lightform layer 1
    2.0: ("/lightform/layer/show", 2),   # Cue 2 Blue  → Lightform layer 2
    3.0: ("/lightform/layer/show", 3),   # Cue 3 Sine  → Lightform layer 3
    4.0: ("/lightform/layer/show", 0),   # Cue 4 Off   → Lightform layer 0 (hide)
}

# Called every time a cue fires — manages FX and sends OSC.
def _on_cue_fire(cue_num):
    # Send to Lightform if mapped AND target is configured
    if cue_num in LIGHTFORM_CUE_MAP and "lightform" in osc._clients:
        address, value = LIGHTFORM_CUE_MAP[cue_num]
        osc.send(address, value, target="lightform")

# ----------------------------------------------------------
# MA3-compatible OSC input handlers
# Any tool that was sending to grandMA3 can now send here.
# ----------------------------------------------------------

def _osc_cmd(_, *args):  # _ = OSC address, unused here
    """
    /gma3/cmd  "Go+ Cue 1"
    Receives a grandMA3 command string and runs it through
    the programmer — same as typing it on the command line.
    """
    if not args:
        return
    cmd = str(args[0])
    print(f"\n  OSC cmd: {cmd}")
    # Translate a small set of MA3 shorthand → our command parser
    # Add more translations as you discover what Chataigne sends
    translations = {
        'go+':  'GO',
        'go-':  'BACK',
        'go':   'GO',
        'back': 'BACK',
    }
    lower = cmd.strip().lower()
    for ma3_word, our_word in translations.items():
        lower = lower.replace(ma3_word, our_word)
    try:
        prog.execute(lower.upper())
    except Exception as e:
        print(f"  OSC cmd error: {e}")

def _osc_fader(address, *args):
    """
    /gma3/fader/PAGE/EXEC  float(0.0-1.0)
    Fader on page PAGE, executor EXEC.
    We map Page 1 Exec 1 → grandmaster dim for now.
    """
    if not args:
        return
    val = float(args[0])
    # Parse page/exec from address: /gma3/fader/1/1
    parts = address.strip('/').split('/')
    page = int(parts[2]) if len(parts) > 2 else 1
    exec_num = int(parts[3]) if len(parts) > 3 else 1
    print(f"\n  OSC fader P{page}/E{exec_num} → {val:.0%}")
    if page == 1 and exec_num == 1:
        set_all_dim(val)

def _osc_key(address, *args):
    """
    /gma3/key/PAGE/EXEC/TYPE  int(0/1)
    Key press on an executor.  1=press, 0=release.
    We map Page 1 Exec 1 Go key → cue_go().
    """
    if not args:
        return
    pressed = int(args[0]) == 1
    parts = address.strip('/').split('/')
    page     = int(parts[2]) if len(parts) > 2 else 1
    exec_num = int(parts[3]) if len(parts) > 3 else 1
    key_type = parts[4] if len(parts) > 4 else "go"
    print(f"\n  OSC key P{page}/E{exec_num}/{key_type} {'▼' if pressed else '▲'}")
    if pressed and page == 1 and exec_num == 1:
        if key_type.lower() in ('go', 'go+'):
            cue_go()
        elif key_type.lower() in ('back', 'go-'):
            cue_back()

# Register MA3-style OSC handlers
osc.map("/gma3/cmd",         _osc_cmd)
osc.map("/gma3/fader/*/*/*", _osc_fader)  # /gma3/fader/page/exec
osc.map("/gma3/key/*/*/*",   _osc_key)    # /gma3/key/page/exec/type
# Catch-all: print anything else (helps discover what Chataigne is sending)
osc.map("/*", lambda addr, *a: print(f"  OSC (unmapped): {addr}  {list(a)}"),
         default_handler=True)

# ----------------------------------------------------------
# Grandmaster dim — writes to programmer_layer (highest priority)
# ----------------------------------------------------------

def set_all_dim(val):
    _fader_dim[0] = val
    for master in patch.all_fixtures():
        output_state.programmer_layer.setdefault(str(master.fixture_id), {})['dim'] = val
    print(f"\r  Dim → {val:.0%}      ", end='', flush=True)

# ----------------------------------------------------------
# Knob callbacks
# Each knob saves to _fx_params AND updates any running FX live.
# If no FX is active the value is remembered for when Cue 3 fires.
# ----------------------------------------------------------

def set_fx_rate(val):
    bpm = 20 + val * 460   # 20 – 480 BPM
    _fx_params['rate_bpm'] = bpm
    now = time.monotonic()
    for fx in active_fx:
        fx.set_rate_smooth(bpm, now)
    suffix = f"  ({len(active_fx)} FX live)" if active_fx else "  (pending — fire Cue 3)"
    print(f"\r  FX rate → {bpm:.0f} BPM{suffix}   ", end='', flush=True)

def set_fx_size(val):
    size = val * 100
    _fx_params['size'] = size
    for fx in active_fx:
        fx.size = size
    suffix = f"  ({len(active_fx)} FX live)" if active_fx else "  (pending)"
    print(f"\r  FX size → {size:.0f}{suffix}      ", end='', flush=True)

def set_fx_spread(val):
    spread = val * 100
    _fx_params['spread'] = spread
    for fx in active_fx:
        fx.spread = spread
    suffix = f"  ({len(active_fx)} FX live)" if active_fx else "  (pending)"
    print(f"\r  FX spread → {spread:.1f}{suffix}   ", end='', flush=True)

# ----------------------------------------------------------
# Cue navigation — GO/BACK auto-trigger _on_cue_fire
# ----------------------------------------------------------

def cue_go():
    _stop_prog_fx_preview()
    ex = _active_executor()
    executor_pool.bump_priority(ex.exec_id)
    ex.go(patch, fade_engine)
    cs = ex.cuestack
    if cs:
        _on_cue_fire(cs.current)

def cue_back():
    _stop_prog_fx_preview()
    ex = _active_executor()
    executor_pool.bump_priority(ex.exec_id)
    ex.back(patch, fade_engine)
    cs = ex.cuestack
    if cs:
        _on_cue_fire(cs.current)

def cue_reload():
    """Re-fire the current cue from scratch: resets FX, re-applies fade."""
    _stop_prog_fx_preview()
    ex = _active_executor()
    cs = ex.cuestack
    if not cs or cs.current is None:
        return "No active cue to reload"
    executor_pool.bump_priority(ex.exec_id)
    result = ex.reload(patch, fade_engine)
    _on_cue_fire(cs.current)
    return result

def goto_cue(num):
    _stop_prog_fx_preview()
    ex = _active_executor()
    executor_pool.bump_priority(ex.exec_id)
    ex.goto(num, patch, fade_engine)
    _on_cue_fire(float(num))

# ----------------------------------------------------------
# Direct cue triggers (pads 1-4)
# ----------------------------------------------------------

def goto_1(): goto_cue(1)
def goto_2(): goto_cue(2)
def goto_3(): goto_cue(3)
def goto_4(): goto_cue(4)

# ----------------------------------------------------------
# Flash white — uses programmer_layer so it trumps cues
# ----------------------------------------------------------

def flash_on():
    for master in patch.all_fixtures():
        output_state.programmer_layer.setdefault(str(master.fixture_id), {})['dim'] = 1.0
    for sub in all_subs:
        pl = output_state.programmer_layer.setdefault(str(sub.fixture_id), {})
        pl['red'] = pl['green'] = pl['blue'] = 255

def flash_off():
    for sub in all_subs:
        pl = output_state.programmer_layer.get(str(sub.fixture_id), {})
        for ch in ('red', 'green', 'blue'):
            pl.pop(ch, None)
    set_all_dim(_fader_dim[0])   # restore fader position

# ----------------------------------------------------------
# Transport CC helpers (value 127=press, 0=release)
# ----------------------------------------------------------

def transport_go(val):
    if val > 0.5:
        cue_go()

def transport_back(val):
    if val > 0.5:
        cue_back()

def transport_rewind(val):
    if val > 0.5:
        goto_cue(1)

# ----------------------------------------------------------
# MIDI mappings — Axiom 25 MkII
# ----------------------------------------------------------

# Vol slider / Knob 1 → grandmaster dim
# Names MUST match target_registry keys so show-file restore works
midi.map_cc(channel=1, cc=7,  callback=set_all_dim,   name="Grandmaster Dim",   soft_takeover=True)
midi.map_cc(channel=1, cc=74, callback=set_all_dim,   name="Grandmaster Dim",   soft_takeover=True)

# FX knobs — immediately live (no critical software state to protect)
midi.map_cc(channel=1, cc=71, callback=set_fx_rate,   name="FX Rate",    soft_takeover=False)
midi.map_cc(channel=1, cc=91, callback=set_fx_size,   name="FX Size",    soft_takeover=False)
midi.map_cc(channel=1, cc=93, callback=set_fx_spread, name="FX Spread",  soft_takeover=False)

# Pads (ch=10)
# Row 1 — direct cue jumps
midi.map_note(channel=10, note=36, on_callback=goto_1,   name="Cue 1 Red")
midi.map_note(channel=10, note=38, on_callback=goto_2,   name="Cue 2 Blue")
midi.map_note(channel=10, note=42, on_callback=goto_3,   name="Cue 3 Magenta")
midi.map_note(channel=10, note=46, on_callback=goto_4,   name="Cue 4 Off")
# Row 2 — navigation + flash
midi.map_note(channel=10, note=50, on_callback=cue_back, name="BACK")
midi.map_note(channel=10, note=45, on_callback=cue_go,   name="GO")
midi.map_note(channel=10, note=51, on_callback=flash_on, off_callback=flash_off,
              name="Flash White (hold)")
midi.map_note(channel=10, note=49, on_callback=_stop_fx, name="FX Kill")

# Transport (ch=16, CC toggles)
midi.map_cc(channel=16, cc=118, callback=transport_rewind, name="Transport Rewind",
            soft_takeover=False)
midi.map_cc(channel=16, cc=117, callback=transport_go,     name="Transport GO",
            soft_takeover=False)
midi.map_cc(channel=16, cc=116, callback=transport_back,   name="Transport BACK",
            soft_takeover=False)

midi.print_maps()

# ── AI Engine ─────────────────────────────────────────────
ai = AIEngine(
    patch         = patch,
    prog          = prog,
    output_state  = output_state,
    fx_engine     = fx_engine,
    fade_engine   = fade_engine,
    cuestacks     = {1: cs1},
    executor_pool = executor_pool,
    # cmd_fn and log_fn wired after run_command / GUIEngine are defined below
)

# ── MIDI target registry ───────────────────────────────────
# All parameters that can be assigned to a knob/fader/pad
# via the GUI's MIDI learn panel.
# Format: "Display Name": (callback, soft_takeover, is_note)
#   soft_takeover=True  → physical must reach software value first (faders)
#   is_note=True        → hints to GUI this suits Note mappings
GUIEngine.target_registry = {
    "Grandmaster Dim":  (set_all_dim,      True,  False),
    "FX Rate":          (set_fx_rate,      False, False),
    "FX Size":          (set_fx_size,      False, False),
    "FX Spread":        (set_fx_spread,    False, False),
    "Transport GO":     (transport_go,     False, False),
    "Transport BACK":   (transport_back,   False, False),
    "Transport Rewind": (transport_rewind, False, False),
    "Cue 1 Red":        (goto_1,           False, True),
    "Cue 2 Blue":       (goto_2,           False, True),
    "Cue 3 Magenta":    (goto_3,           False, True),
    "Cue 4 Off":        (goto_4,           False, True),
    "GO":               (cue_go,           False, True),
    "BACK":             (cue_back,         False, True),
    "FX Kill":          (_stop_fx,         False, True),
    # 4-tuple: (on_cb, soft_takeover, is_note, off_cb)
    "Flash White (hold)": (flash_on,       False, True, flash_off),
}

# ── Save helpers — one call per category ──────────────────
def save_show():
    ShowFile.save_patch(patch)
    ShowFile.save_cuestacks(cuestack_pool)
    ShowFile.save_groups(group_pool)
    ShowFile.save_colors(color_pool)
    ShowFile.save_dims(dim_pool)
    ShowFile.save_midi(midi)
    ShowFile.save_fx(_fx_params)
    ShowFile.save_fx_pool(fx_pool)
    ShowFile.save_forms(form_pool)
    ShowFile.save_rate_pool(rate_pool)
    ShowFile.save_size_pool(size_pool)
    ShowFile.save_spread_pool(spread_pool)
    ShowFile.save_position_pool(position_pool)
    ShowFile.save_gobo_pool(gobo_pool)
    ShowFile.save_zoom_pool(zoom_pool)
    ShowFile.save_focus_pool(focus_pool)
    ShowFile.save_beam_pool(beam_pool)
    ShowFile.save_control_pool(control_pool)
    ShowFile.save_executor_pages(executor_pool)
    ShowFile.save_executors(executor_pool)
    ShowFile.save_state(output_state, executor_pool, active_executor,
                        prog_time=_prog_time, fader_dim=_fader_dim[0])


def save_show_as(name):
    """Copy current show files into studio_saves/<name>/."""
    import shutil as _sh
    if not name or not name.strip():
        return "SAVE AS: provide a show name"
    safe = "".join(c for c in name.strip() if c.isalnum() or c in (' ', '-', '_')).strip()
    if not safe:
        return "SAVE AS: invalid name"
    save_show()  # flush current state first
    dest = os.path.join(SAVES_DIR, safe)
    os.makedirs(dest, exist_ok=True)
    for fname in os.listdir(DATA_DIR):
        if fname.endswith('.json') and not fname.endswith('.bak'):
            _sh.copy2(os.path.join(DATA_DIR, fname), os.path.join(dest, fname))
    return f"Show saved as '{safe}'  →  studio_saves/{safe}/"


def load_show_from(name):
    """Copy saved show files back into studio_data/ and reload all pools."""
    import shutil as _sh
    if not name or not name.strip():
        return "LOAD SHOW: provide a show name"
    src = os.path.join(SAVES_DIR, name.strip())
    if not os.path.isdir(src):
        # fuzzy match
        try:
            all_saves = [d for d in os.listdir(SAVES_DIR)
                         if os.path.isdir(os.path.join(SAVES_DIR, d))]
        except OSError:
            return "LOAD SHOW: no saves directory found — use SAVE AS first"
        matches = [s for s in all_saves if name.strip().lower() in s.lower()]
        if len(matches) == 1:
            src = os.path.join(SAVES_DIR, matches[0])
            name = matches[0]
        elif matches:
            return f"LOAD SHOW: ambiguous — matches: {', '.join(matches)}"
        else:
            return f"LOAD SHOW: '{name}' not found — LIST SHOWS to see saves"
    for fname in os.listdir(src):
        if fname.endswith('.json'):
            _sh.copy2(os.path.join(src, fname), os.path.join(DATA_DIR, fname))
    # Reload pools from newly-copied files
    doc = _read_file(ShowFile.CUESTACKS)
    if doc:
        ShowFile.load_cuestacks(doc, cuestack_pool)
    doc = _read_file(ShowFile.GROUPS)
    if doc:
        ShowFile.load_groups(doc, group_pool)
    doc = _read_file(ShowFile.COLORS)
    if doc:
        ShowFile.load_colors(doc, color_pool)
    doc = _read_file(ShowFile.DIMS)
    if doc:
        ShowFile.load_dims(doc, dim_pool)
    doc = _read_file(ShowFile.FX_POOL)
    if doc:
        ShowFile.load_fx_pool(doc, fx_pool)
    doc = _read_file(ShowFile.FORMS)
    if doc:
        ShowFile.load_forms(doc, form_pool)
    doc = _read_file(ShowFile.RATES)
    if doc:
        ShowFile.load_rate_pool(doc, rate_pool)
    doc = _read_file(ShowFile.SIZES)
    if doc:
        ShowFile.load_size_pool(doc, size_pool)
    doc = _read_file(ShowFile.SPREADS)
    if doc:
        ShowFile.load_spread_pool(doc, spread_pool)
    return f"Show '{name}' loaded — restart may be needed for patch/MIDI changes"


def list_shows():
    """List all saved shows in studio_saves/."""
    try:
        saves = [d for d in sorted(os.listdir(SAVES_DIR))
                 if os.path.isdir(os.path.join(SAVES_DIR, d))]
    except OSError:
        return "No saves yet — use: SAVE AS <name>"
    if not saves:
        return "No saved shows — use: SAVE AS <name>"
    import datetime as _dt
    lines = ["Saved shows:"]
    for s in saves:
        mtime = os.path.getmtime(os.path.join(SAVES_DIR, s))
        ts = _dt.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        lines.append(f"  {s}  [{ts}]")
    return "\n".join(lines)


def export_presets(what='all'):
    """
    Bundle presets into a single JSON file in studio_data/.
    what: 'all' | 'colors' | 'dims' | 'fx' | 'forms' | 'rates' | 'sizes' | 'spreads'
    Returns the output path on success.
    """
    import datetime as _dt
    bundle = {"version": ShowFile.VERSION,
              "exported": _dt.datetime.now().isoformat()}
    what_l = what.lower()

    if what_l in ('all', 'colors'):
        bundle['colors'] = {}
        for pid, p in color_pool.presets.items():
            bundle['colors'][str(pid)] = {'name': p.name, 'red': p.red,
                                           'green': p.green, 'blue': p.blue}
    if what_l in ('all', 'dims'):
        bundle['dims'] = {}
        for pid, p in dim_pool.presets.items():
            bundle['dims'][str(pid)] = {'name': p.name, 'level': p.level}
    if what_l in ('all', 'fx'):
        doc = _read_file(ShowFile.FX_POOL)
        if doc:
            bundle['fx_pool'] = doc.get('fx_presets', {})
    if what_l in ('all', 'forms'):
        doc = _read_file(ShowFile.FORMS)
        if doc:
            bundle['forms'] = doc.get('forms', {})
    if what_l in ('all', 'rates'):
        doc = _read_file(ShowFile.RATES)
        if doc:
            bundle['rate_pool'] = doc.get('rates', {})
    if what_l in ('all', 'sizes'):
        doc = _read_file(ShowFile.SIZES)
        if doc:
            bundle['size_pool'] = doc.get('sizes', {})
    if what_l in ('all', 'spreads'):
        doc = _read_file(ShowFile.SPREADS)
        if doc:
            bundle['spread_pool'] = doc.get('spreads', {})

    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(DATA_DIR, f"preset_export_{ts}.json")
    with open(out_path, 'w') as f:
        json.dump(bundle, f, indent=2)
    cats = [k for k in ('colors','dims','fx_pool','forms','rate_pool','size_pool','spread_pool')
            if k in bundle]
    return f"Exported {', '.join(cats)} → {os.path.basename(out_path)}"


def import_presets(path):
    """
    Merge a preset bundle JSON into the live pools.
    Existing presets are overwritten only where the bundle has data.
    """
    if not os.path.isabs(path):
        # try relative to DATA_DIR first, then cwd
        candidate = os.path.join(DATA_DIR, path)
        if os.path.exists(candidate):
            path = candidate
    if not os.path.exists(path):
        return f"IMPORT PRESETS: file not found — {path}"
    try:
        with open(path) as f:
            bundle = json.load(f)
    except Exception as e:
        return f"IMPORT PRESETS: bad JSON — {e}"

    imported = []
    if 'colors' in bundle:
        for pid_s, d in bundle['colors'].items():
            pid = int(pid_s)
            p = color_pool.presets.setdefault(pid, type('ColorPreset', (), {
                'preset_id': pid, 'name': '', 'red': 0, 'green': 0, 'blue': 0})())
            p.name = d.get('name', ''); p.red = d.get('red', 0)
            p.green = d.get('green', 0); p.blue = d.get('blue', 0)
        ShowFile.save_colors(color_pool)
        imported.append(f"{len(bundle['colors'])} colors")
    if 'dims' in bundle:
        for pid_s, d in bundle['dims'].items():
            pid = int(pid_s)
            p = dim_pool.presets.setdefault(pid, type('DimPreset', (), {
                'preset_id': pid, 'name': '', 'level': 1.0})())
            p.name = d.get('name', ''); p.level = d.get('level', 1.0)
        ShowFile.save_dims(dim_pool)
        imported.append(f"{len(bundle['dims'])} dims")
    if not imported:
        return "IMPORT PRESETS: nothing imported (bundle has no recognized preset categories)"
    return "Imported: " + ", ".join(imported)

# ── MIDI restore (must happen after target_registry is built) ──
_midi_doc = _read_file(ShowFile.MIDI)
if _midi_doc:
    # Pre-generate callbacks for any dynamic "GO CS N CUE M" / "Exec N Flash"
    # targets saved in midi.json — these aren't in the static target_registry
    # dict (executor/cuestack numbers aren't known ahead of time), so they're
    # regenerated by name pattern on load, same as when they were first learned.
    import re as _re_midi
    for _entry in _midi_doc.get("midi_note", []):
        _name = _entry.get("target", "")
        if _name not in GUIEngine.target_registry:
            _m = _re_midi.match(r'^GO CS (\d+) CUE (\d+(?:\.\d+)?)$', _name)
            if _m:
                _cs, _cue = int(_m.group(1)), float(_m.group(2))
                def _make_go(c=f"GO CS {_cs} CUE {_cue}"): return lambda: run_command(c)
                GUIEngine.target_registry[_name] = (_make_go(), False, True)
                continue
            _mf = _re_midi.match(r'^Exec (\d+) Flash$', _name)
            if _mf:
                _ex_n = int(_mf.group(1))
                def _make_flash(on_c=f"EXEC {_ex_n} FLASH ON", off_c=f"EXEC {_ex_n} FLASH OFF"):
                    return (lambda: run_command(on_c)), (lambda: run_command(off_c))
                _on_cb, _off_cb = _make_flash()
                GUIEngine.target_registry[_name] = (_on_cb, False, True, _off_cb)
    ShowFile.load_midi(_midi_doc, midi, GUIEngine.target_registry)
else:
    save_show()   # first run — write all files now

midi.print_maps()

# ── Command line router ────────────────────────────────────
# Handles both console-level commands and programmer commands.
# Returns a result string that the GUI logs below the input.
#
# Console commands:
#   GO / BACK / GOTO <n>
#   RECORD CUE <n> ["<name>"] [FADE <t>]
#   SAVE
#   CUES  — list current stack
#
# Everything else is forwarded to prog.execute() (programmer).
# Programmer syntax:  <fixtures> AT <value>  |  CLEAR  |  etc.

import re as _re

def _name_after(raw_cmd, skip_token_count):
    """
    Extract a name from a command string after skipping skip_token_count words.
    Quoted string takes priority: RECORD GROUP 1 "All Tubes" → "All Tubes"
    Without quotes: RECORD GROUP 1 All Tubes → "All Tubes"
    Returns "" if nothing left after skipping.
    """
    m = _re.search(r'"([^"]*)"', raw_cmd)
    if m:
        return m.group(1).strip()
    parts = raw_cmd.split(None, skip_token_count)
    if len(parts) > skip_token_count:
        return parts[skip_token_count].strip()
    return ""

def _apply_timing_edit(cue, raw_str):
    """Write timing keywords from raw_str onto cue in-place. No programmer needed.

    Supported keywords (all case-insensitive):
      FADE / INFADE / OUTFADE   — cue crossfade time (all three are synonyms here)
      DELAY                     — global pre-wait before fade starts
      CFADE / CINFADE           — colour-group fade override
      DFADE / DINFADE           — dim-group fade override
      CDELAY / CDDELAY          — colour-group delay override
      DDELAY / DDDELAY          — dim-group delay override
    """
    up = raw_str.upper()
    def _get(*kws):
        """Return first match across multiple keyword aliases."""
        import re as _r
        for kw in kws:
            m = _r.search(rf'\b{kw}\s+([\d.]+)', up)
            if m:
                return float(m.group(1))
        return None

    # Global fade: FADE / INFADE / OUTFADE are all synonyms for crossfade time
    v = _get('FADE', 'INFADE', 'OUTFADE')
    if v is not None:
        cue.fade_time = v

    v = _get('DELAY')
    if v is not None:
        cue.delay_time = v

    for grp, kw_f, kw_d in [
        ('colour', ('CFADE', 'CINFADE'), ('CDELAY',)),
        ('dim',    ('DFADE', 'DINFADE'), ('DDELAY',)),
    ]:
        vf = _get(*kw_f)
        vd = _get(*kw_d)
        if vf is not None: cue.fade_times[grp]  = vf
        if vd is not None: cue.delay_times[grp] = vd


def run_command(cmd_str):
    raw    = cmd_str.strip()
    tokens = raw.upper().split()
    if not tokens:
        return ""

    # REC is a shorthand alias for RECORD
    if tokens[0] == 'REC':
        tokens[0] = 'RECORD'

    t0 = tokens[0]

    # ── Executor selection ────────────────────────────────────
    # CUESTACK N  — make executor N the active one
    if t0 == 'CUESTACK' and len(tokens) > 1:
        try:
            n = int(tokens[1])
        except ValueError:
            return f"CUESTACK: bad number '{tokens[1]}'"
        if cuestack_pool.get(n):
            active_executor[0] = n
            cs = cuestack_pool.get(n)
            return f"Active executor → Cuestack {n}: {cs.name}"
        return f"Cuestack {n} is empty  (use: RECORD CUESTACK {n} My Show)"

    # RECORD CUESTACK N [name]  — create a new empty cuestack in slot N
    if t0 == 'RECORD' and len(tokens) > 2 and tokens[1] == 'CUESTACK':
        try:
            n = int(tokens[2])
        except ValueError:
            return f"RECORD CUESTACK: bad number '{tokens[2]}'"
        name = _name_after(raw, 3) or f"Cuestack {n}"
        cs = cuestack_pool.create(n, name)
        executor_pool.assign(n, cs)
        active_executor[0] = n
        save_show()
        return f"Created: Cuestack {n} '{name}'  (now active on executor {n})"

    # ── Navigation ───────────────────────────────────────────
    # ── ASSIGN CS <n> TO EXEC <n> ────────────────────────────
    # Wire a cuestack into an executor slot.
    if t0 == 'ASSIGN' and 'CS' in tokens and 'TO' in tokens and 'EXEC' in tokens:
        try:
            cs_idx   = tokens.index('CS')
            exec_idx = tokens.index('EXEC')
            cs_n     = int(tokens[cs_idx   + 1])
            ex_n     = int(tokens[exec_idx + 1])
        except (ValueError, IndexError):
            return "Usage: ASSIGN CS <n> TO EXEC <n>"
        stack = cuestack_pool.get(cs_n)
        if not stack:
            return f"CueStack {cs_n} not found"
        executor_pool.assign(ex_n, stack)
        return f"CS {cs_n} assigned to Executor {ex_n}"

    # ── EXEC <n> GO / BACK / STOP ────────────────────────────
    if t0 == 'EXEC' and len(tokens) >= 2:
        try:
            ex_n = int(tokens[1])
        except ValueError:
            return f"EXEC: bad executor number '{tokens[1]}'"
        ex  = executor_pool.get(ex_n)
        verb = tokens[2].upper() if len(tokens) > 2 else 'GO'
        if verb == 'GO':
            executor_pool.bump_priority(ex_n)
            msg = ex.go(patch, fade_engine)
            if ex.cuestack:
                _on_cue_fire(ex.cuestack.current)
            return msg or f"Exec {ex_n} GO"
        elif verb == 'BACK':
            executor_pool.bump_priority(ex_n)
            msg = ex.back(patch, fade_engine)
            if ex.cuestack:
                _on_cue_fire(ex.cuestack.current)
            return msg or f"Exec {ex_n} BACK"
        elif verb == 'STOP':
            ex.stop()
            return f"Exec {ex_n} stopped"
        elif verb == 'GOTO' and len(tokens) > 3:
            try:
                num = float(tokens[3])
            except ValueError:
                return f"EXEC GOTO: bad cue number '{tokens[3]}'"
            executor_pool.bump_priority(ex_n)
            msg = ex.goto(num, patch, fade_engine)
            _on_cue_fire(num)
            return msg or f"Exec {ex_n} GOTO {num}"
        elif verb == 'TIME':
            # EXEC <n> TIME <fade> [DELAY <delay>]  |  EXEC <n> TIME OFF
            if len(tokens) > 3 and tokens[3] == 'OFF':
                ex.time_override_on   = False
                ex.time_override_fade  = None
                ex.time_override_delay = None
                return f"Exec {ex_n} time override OFF"
            try:
                fade_t = float(tokens[3]) if len(tokens) > 3 else None
            except ValueError:
                return "EXEC TIME: usage  EXEC <n> TIME <seconds> [DELAY <seconds>]  or  OFF"
            delay_t = None
            if 'DELAY' in tokens:
                di = tokens.index('DELAY')
                try:
                    delay_t = float(tokens[di + 1])
                except (IndexError, ValueError):
                    return "EXEC TIME: bad DELAY value"
            ex.time_override_fade  = fade_t
            ex.time_override_delay = delay_t if delay_t is not None else 0.0
            ex.time_override_on    = True
            delay_str = f"  delay {delay_t}s" if delay_t else ""
            return f"Exec {ex_n} time override → {fade_t}s{delay_str}"
        elif verb == 'TIMELOCK':
            # EXEC <n> TIMELOCK ON/OFF  — whether this executor's cuestack accepts overrides
            if len(tokens) < 4:
                return "Usage: EXEC <n> TIMELOCK ON | OFF"
            state = tokens[3]
            cs = ex.cuestack
            if not cs:
                return f"Exec {ex_n} has no cuestack"
            if state == 'ON':
                cs.allow_exec_time = True
                return f"Exec {ex_n}: executor time override ENABLED for '{cs.name}'"
            elif state == 'OFF':
                cs.allow_exec_time = False
                return f"Exec {ex_n}: executor time override LOCKED OUT for '{cs.name}'"
            return "TIMELOCK: use ON or OFF"
        elif verb == 'FLASH':
            # EXEC <n> FLASH ON | OFF  — instant on-while-held, for trigger_mode='flash'.
            # Independent of trigger_mode itself so GUI/MIDI press/release can call
            # this directly regardless of how the mode was set.
            if len(tokens) < 4 or tokens[3] not in ('ON', 'OFF'):
                return "Usage: EXEC <n> FLASH ON | OFF"
            if tokens[3] == 'ON':
                executor_pool.bump_priority(ex_n)
                msg = ex.flash_on(patch, fade_engine)
                if ex.cuestack:
                    _on_cue_fire(ex.cuestack.current)
                return msg or f"Exec {ex_n} FLASH ON"
            else:
                ex.flash_off()
                return f"Exec {ex_n} FLASH OFF"
        elif verb == 'MODE':
            # EXEC <n> MODE TOGGLE | FLASH — how GUI/MIDI should trigger this executor.
            # 'toggle' = GO/BACK advance normally. 'flash' = live only while held
            # (use EXEC <n> FLASH ON/OFF, or a MIDI note's on/off callbacks).
            if len(tokens) < 4 or tokens[3] not in ('TOGGLE', 'FLASH'):
                return "Usage: EXEC <n> MODE TOGGLE | FLASH"
            ex.trigger_mode = tokens[3].lower()
            return f"Exec {ex_n} trigger_mode → {ex.trigger_mode}"
        elif verb == 'LEVEL':
            # EXEC <n> LEVEL <0-100>  — set master fader (0 = blackout, 100 = full)
            if len(tokens) < 4:
                return f"Exec {ex_n} level: {ex.level * 100:.0f}%  (usage: EXEC {ex_n} LEVEL 0–100)"
            try:
                pct = float(tokens[3])
            except ValueError:
                return "EXEC LEVEL: usage  EXEC <n> LEVEL <0-100>"
            ex.level = max(0.0, min(1.0, pct / 100.0))
            save_show()
            return f"Exec {ex_n} level → {ex.level * 100:.0f}%"
        else:
            return f"EXEC {ex_n}: unknown verb '{verb}'"

    # ── PAGE <n> NAME ... / ADD CS <m> / REMOVE CS <m> / DELETE / LIST ─
    if t0 == 'PAGE':
        if len(tokens) >= 2 and tokens[1] == 'LIST':
            if not executor_pool.pages:
                return "Pages: (none)"
            lines = ["Pages:"]
            for n in executor_pool.all_pages():
                p = executor_pool.get_page(n)
                cs_ids = p.get('cuestacks', [])
                cs_names = []
                for cid in cs_ids:
                    cs = cuestack_pool.get(cid)
                    cs_names.append(f"{cid}:{cs.name}" if cs else str(cid))
                lines.append(f"  [{n}] {p['name']} — {', '.join(cs_names) or '(empty)'}")
            return "\n".join(lines)

        if len(tokens) < 2:
            return "Usage: PAGE <n> NAME <name> | PAGE <n> ADD CS <m> | PAGE <n> REMOVE CS <m> | PAGE <n> DELETE | PAGE LIST"
        try:
            page_n = int(tokens[1])
        except ValueError:
            return f"PAGE: bad page number '{tokens[1]}'"

        if len(tokens) == 2:
            p = executor_pool.get_page(page_n)
            cs_ids = p.get('cuestacks', [])
            cs_names = []
            for cid in cs_ids:
                cs = cuestack_pool.get(cid)
                cs_names.append(f"{cid}:{cs.name}" if cs else str(cid))
            return f"[{page_n}] {p['name']} — {', '.join(cs_names) or '(empty)'}"

        sub2 = tokens[2]
        if sub2 == 'NAME':
            name = " ".join(raw.split()[3:]) if len(tokens) > 3 else f"Page {page_n}"
            executor_pool.set_page_name(page_n, name)
            ShowFile.save_executor_pages(executor_pool)
            return f"Page {page_n} → '{name}'"
        if sub2 == 'DELETE':
            executor_pool.delete_page(page_n)
            ShowFile.save_executor_pages(executor_pool)
            return f"Page {page_n} deleted"
        if sub2 in ('ADD', 'REMOVE') and len(tokens) >= 4 and tokens[3] == 'CS':
            try:
                target_cs = int(tokens[4]) if len(tokens) > 4 else int(tokens[3])
            except (ValueError, IndexError):
                return f"PAGE: bad cuestack number"
            cs = cuestack_pool.get(target_cs)
            if sub2 == 'ADD':
                executor_pool.add_to_page(page_n, target_cs)
                ShowFile.save_executor_pages(executor_pool)
                return f"CS {target_cs} ({cs.name if cs else '?'}) added to page {page_n}"
            else:
                executor_pool.remove_from_page(page_n, target_cs)
                ShowFile.save_executor_pages(executor_pool)
                return f"CS {target_cs} removed from page {page_n}"
        return "Usage: PAGE <n> NAME <name> | PAGE <n> ADD CS <m> | PAGE <n> REMOVE CS <m> | PAGE <n> DELETE | PAGE LIST"

    # ── PROG TIME — programmer time override ──────────────────
    if t0 == 'PROG' and len(tokens) >= 2 and tokens[1] == 'TIME':
        if len(tokens) == 3 and tokens[2] == 'OFF':
            _prog_time['on'] = False
            return "Programmer time override OFF"
        try:
            fade_t = float(tokens[2]) if len(tokens) > 2 else None
        except ValueError:
            return "PROG TIME: usage  PROG TIME <seconds> [DELAY <seconds>]  or  OFF"
        if fade_t is None:
            return "PROG TIME: usage  PROG TIME <seconds> [DELAY <seconds>]  or  OFF"
        delay_t = 0.0
        if 'DELAY' in tokens:
            di = tokens.index('DELAY')
            try:
                delay_t = float(tokens[di + 1])
            except (IndexError, ValueError):
                return "PROG TIME: bad DELAY value"
        _prog_time['fade']  = fade_t
        _prog_time['delay'] = delay_t
        _prog_time['on']    = True
        delay_str = f"  delay {delay_t}s" if delay_t else ""
        return f"Programmer time → {fade_t}s{delay_str}"

    # ── EXECUTOR <n> — switch active executor ─────────────────
    if t0 == 'EXECUTOR' and len(tokens) == 2:
        try:
            n = int(tokens[1])
        except ValueError:
            return f"EXECUTOR: bad number '{tokens[1]}'"
        active_executor[0] = n
        ex = executor_pool.get(n)
        cs_name = ex.cuestack.name if ex.cuestack else "(no cuestack)"
        return f"Active executor → {n}  [{cs_name}]"

    if t0 == 'GO' and len(tokens) == 1:
        cue_go()
        cs = _active_stack()
        cur = cs.current if cs else None
        return f"GO → Cue {cur}" if cur else "GO (no cue)"

    if t0 == 'BACK' and len(tokens) == 1:
        cue_back()
        cs = _active_stack()
        cur = cs.current if cs else None
        return f"BACK → Cue {cur}" if cur else "BACK (no cue)"

    if t0 == 'GOTO' and len(tokens) > 1:
        try:
            num = float(tokens[1])
            goto_cue(num)
            return f"GOTO → Cue {num}"
        except ValueError:
            return f"GOTO: bad cue number '{tokens[1]}'"

    if t0 == 'RELOAD' and len(tokens) == 1:
        return cue_reload() or "Reloaded"

    if t0 == 'DELETE' and len(tokens) >= 2 and tokens[1] == 'CUE':
        if len(tokens) < 3:
            return "Usage: DELETE CUE <n>  [CS <stack_n>]"
        try:
            cue_num = float(tokens[2])
        except ValueError:
            return f"DELETE CUE: bad cue number '{tokens[2]}'"
        if 'CS' in tokens:
            cs_idx = tokens.index('CS')
            try:
                cs_n = int(tokens[cs_idx + 1])
            except (ValueError, IndexError):
                return "Usage: DELETE CUE <n> CS <stack_n>"
            cs = cuestack_pool.get(cs_n)
            if not cs:
                return f"CueStack {cs_n} not found"
        else:
            active_n = active_executor[0] if active_executor else 1
            cs = cuestack_pool.get(active_n)
            if not cs:
                return "No active cuestack"
        if cue_num not in cs.cues:
            return f"Cue {cue_num} not found in {cs.name}"
        cs.delete_cue(cue_num)
        save_show()
        return f"Deleted Cue {cue_num} from {cs.name}"

    # ── Shared record/update-cue helper ──────────────────────
    def _record_cue_into(cs, cue_num, suffix_tokens, raw_str, merge=False):
        """
        Apply preset tokens then record (or merge-update) a cue into cs.
        suffix_tokens: everything after CUE <num> (already upper-cased).
        raw_str: original mixed-case command (for quoted name search).
        merge=True  → UPDATE mode: merges programmer into existing cue.
        merge=False → RECORD mode: replaces cue data entirely.
        Returns result string.
        """
        _KW = {'FADE', 'INFADE', 'OUTFADE', 'DELAY',
               'CFADE', 'CINFADE', 'DFADE', 'DINFADE', 'CDELAY', 'DDELAY',
               'GROUP', 'COLOR', 'COLOUR', 'DIM'}
        up  = raw_str.upper()

        # Quoted name wins; otherwise build from leading non-keyword tokens.
        # If no name is given and a cue already exists at this number, keep its name.
        name_match = _re.search(r'"([^"]*)"', raw_str)
        if name_match:
            name = name_match.group(1)
        else:
            name_parts = []
            for tok in suffix_tokens:
                if tok in _KW or (tok and tok[0].isdigit()):
                    break
                name_parts.append(tok.capitalize())
            if name_parts:
                name = " ".join(name_parts)
            else:
                existing = cs.get_cue(cue_num)
                name = existing.name if existing else f"Cue {cue_num:.0f}"

        # Timing extraction helper — tries multiple keyword aliases in order
        def _get_timing(*kws):
            for kw in kws:
                m = _re.search(rf'\b{kw}\s+([\d.]+)', up)
                if m:
                    return float(m.group(1))
            return None

        # Global fade: FADE / INFADE / OUTFADE are synonyms for cue crossfade time
        _ft = _get_timing('FADE', 'INFADE', 'OUTFADE')
        fade  = _ft if _ft is not None else 2.0
        _dt = _get_timing('DELAY')
        delay = _dt if _dt is not None else 0.0

        # Per-attribute-group overrides: CFade / DFade / CDelay / DDelay
        fade_times, delay_times = {}, {}
        _v = _get_timing('CFADE', 'CINFADE')
        if _v is not None: fade_times['colour']  = _v
        _v = _get_timing('DFADE', 'DINFADE')
        if _v is not None: fade_times['dim']     = _v
        _v = _get_timing('CDELAY')
        if _v is not None: delay_times['colour'] = _v
        _v = _get_timing('DDELAY')
        if _v is not None: delay_times['dim']    = _v

        # Preset look-up by name across all pools
        def _find_by_name(tok):
            t = tok.upper()
            for p in color_pool.presets.values():
                if p.name.upper() == t:
                    return ('color', p)
            for p in dim_pool.presets.values():
                if p.name.upper() == t:
                    return ('dim', p)
            for g in group_pool.groups.values():
                if g.name.upper() == t:
                    return ('group', g)
            return None

        def _extract_int(keyword):
            m = _re.search(rf'\b{keyword}\s+(\d+)', up)
            return int(m.group(1)) if m else None

        # Numeric keyword forms (GROUP 1, COLOR 2, DIM 3)
        group_n = _extract_int('GROUP')
        color_n = _extract_int('COLOR') or _extract_int('COLOUR')
        dim_n   = _extract_int('DIM')

        if group_n is not None:
            g = group_pool.get(group_n)
            if not g: return f"RECORD CUE: Group {group_n} not found"
            prog.select(g.recall(patch))
        if color_n is not None:
            p = color_pool.get(color_n)
            if not p: return f"RECORD CUE: Color {color_n} not found"
            p.apply(prog)
        if dim_n is not None:
            p = dim_pool.get(dim_n)
            if not p: return f"RECORD CUE: Dim {dim_n} not found"
            p.apply(prog)

        # Name-based preset tokens (any token not a keyword/number that
        # wasn't consumed by the above — i.e. the leading name tokens)
        for tok in suffix_tokens:
            if tok in _KW or (tok and tok[0].isdigit()):
                break   # hit a keyword or number — stop
            hit = _find_by_name(tok)
            if hit:
                kind, preset = hit
                if kind == 'color':
                    preset.apply(prog)
                elif kind == 'dim':
                    preset.apply(prog)
                elif kind == 'group':
                    prog.select(preset.recall(patch))

        # Treat programmer as empty if it only contains flag values (fx_kill etc.)
        # with no actual DMX data — prevents CFADE/DFADE from accidentally wiping cue data.
        _prog_has_dmx = any(
            any(k not in ('fx_kill',) for k in vals)
            for vals in prog.data.values() if vals
        )

        if not _prog_has_dmx:
            # Programmer has no DMX data — allow timing/name update on any existing cue.
            existing = cs.get_cue(cue_num)
            if existing:
                _apply_timing_edit(existing, raw_str)
                if name:
                    existing.name = name
                save_show()
                action = "Updated" if merge else "Updated timing"
                return f"{action}: {existing}"
            if merge:
                return f"UPDATE CUE: cue {cue_num} not found — create it first with RECORD CUE"
            return "RECORD CUE: programmer is empty — set values or use preset names / GROUP / COLOR / DIM"

        if merge:
            # UPDATE mode: merge programmer into existing cue (or create if missing)
            cue = cs.get_cue(cue_num)
            if not cue:
                return f"UPDATE CUE: cue {cue_num} not found — create it first with RECORD CUE"
            cue.update(prog)
            _apply_timing_edit(cue, raw_str)
            if name:
                cue.name = name
            if cue_num == int(cue_num):
                cue_pool.store(int(cue_num), cue)
            save_show()

            # Auto-reload if this cue is the currently running cue on any executor
            _reloaded = []
            for _ex in executor_pool.executors.values():
                if _ex.cuestack is cs and _ex.cuestack.current == cue_num and _ex.is_active:
                    executor_pool.bump_priority(_ex.exec_id)
                    _ex.reload(patch, fade_engine)
                    _on_cue_fire(cue_num)
                    _reloaded.append(_ex.exec_id)
            _reload_note = f"  (live-reloaded exec {_reloaded})" if _reloaded else ""
            return f"Updated: {cue}  (merged into {cs.name}){_reload_note}"

        cue = cs.record_cue(cue_num, prog, name=name, fade_time=fade)
        cue.delay_time  = delay
        cue.fade_times  = fade_times
        cue.delay_times = delay_times
        if cue_num == int(cue_num):
            cue_pool.store(int(cue_num), cue)
        save_show()
        return f"Recorded: {cue}  into {cs.name}  (auto-saved)"

    # ── RECORD CS [n] CUE <m> [presets...] ──────────────────
    # e.g.  RECORD CS CUE 4 RED
    #        RECORD CS 2 CUE 4 RED FULL
    if t0 == 'RECORD' and 'CS' in tokens and 'CUE' in tokens:
        cs_idx  = tokens.index('CS')
        cue_idx = tokens.index('CUE')

        # Optional cuestack number after CS
        cs_n = None
        if cue_idx > cs_idx + 1:
            try:
                cs_n = int(tokens[cs_idx + 1])
            except ValueError:
                pass

        try:
            cue_num = float(tokens[cue_idx + 1])
        except (IndexError, ValueError):
            return "Usage: RECORD CS [n] CUE <num> [preset-names / GROUP n COLOR n DIM n FADE t]"

        cs = cuestack_pool.get(cs_n) if cs_n is not None else _active_stack()
        if not cs:
            return f"CueStack {cs_n} not found" if cs_n else "No active cuestack"

        return _record_cue_into(cs, cue_num, tokens[cue_idx + 2:], raw)

    # ── RECORD CUE <n> ["name"] [GROUP g] [COLOR c] [DIM d] [FADE t]
    if t0 == 'RECORD' and len(tokens) > 2 and tokens[1] == 'CUE':
        try:
            cue_num = float(tokens[2])
        except ValueError:
            return f"RECORD: bad cue number '{tokens[2]}'"
        cs = _active_stack()
        if not cs:
            return "RECORD CUE: no active cuestack — use RECORD CUESTACK 1 first"
        return _record_cue_into(cs, cue_num, tokens[3:], raw)

    # ── UPDATE CUE / UPDATE CS CUE — merge programmer into existing cue ──
    # UPDATE CUE <n> [presets] [FADE <t>]
    # UPDATE CS [n] CUE <m> [presets] [FADE <t>]
    # Only merges what is in the programmer — untouched fixtures keep their data.
    if t0 in ('UPDATE', 'UPD'):
        if 'CS' in tokens and 'CUE' in tokens:
            cs_idx  = tokens.index('CS')
            cue_idx = tokens.index('CUE')
            cs_n    = None
            if cue_idx > cs_idx + 1:
                try:
                    cs_n = int(tokens[cs_idx + 1])
                except ValueError:
                    pass
            try:
                cue_num = float(tokens[cue_idx + 1])
            except (IndexError, ValueError):
                return "Usage: UPDATE CS [n] CUE <num> [presets / FADE t]"
            cs = cuestack_pool.get(cs_n) if cs_n is not None else _active_stack()
            if not cs:
                return f"CueStack {cs_n} not found" if cs_n else "No active cuestack"
            return _record_cue_into(cs, cue_num, tokens[cue_idx + 2:], raw, merge=True)
        if 'CUE' in tokens:
            cue_idx = tokens.index('CUE')
            try:
                cue_num = float(tokens[cue_idx + 1])
            except (IndexError, ValueError):
                return "Usage: UPDATE CUE <num> [presets / FADE t]"
            cs = _active_stack()
            if not cs:
                return "UPDATE CUE: no active cuestack"
            return _record_cue_into(cs, cue_num, tokens[cue_idx + 2:], raw, merge=True)

    # ── GO CS [n] CUE <m> ────────────────────────────────────
    # e.g.  GO CS 2 CUE 4
    #        GO CS CUE 1       (active cuestack)
    if t0 == 'GO' and 'CS' in tokens and 'CUE' in tokens:
        cs_idx  = tokens.index('CS')
        cue_idx = tokens.index('CUE')

        cs_n = None
        if cue_idx > cs_idx + 1:
            try:
                cs_n = int(tokens[cs_idx + 1])
            except ValueError:
                pass

        try:
            cue_num = float(tokens[cue_idx + 1])
        except (IndexError, ValueError):
            return "Usage: GO CS [n] CUE <num>"

        # Find executor for this cuestack (match by stack_id, fallback to slot)
        if cs_n is not None:
            ex = None
            for e in executor_pool.executors.values():
                if e.cuestack and e.cuestack.stack_id == cs_n:
                    ex = e
                    break
            if not ex:
                ex = executor_pool.get(cs_n)
                cs = cuestack_pool.get(cs_n)
                if cs:
                    ex.assign(cs)
        else:
            ex = _active_executor()

        executor_pool.bump_priority(ex.exec_id)
        msg = ex.goto(cue_num, patch, fade_engine)
        if ex.cuestack:
            _on_cue_fire(ex.cuestack.current)
        return msg or f"GO CS {cs_n or active_executor[0]} CUE {cue_num}"

    # ── FORM commands ─────────────────────────────────────────
    # FORM LIST
    # RECORD FORM <n> <name> <phase,value> ...   (breakpoint curve)
    if t0 == 'FORM' and len(tokens) >= 2 and tokens[1] == 'LIST':
        lines = []
        for f in form_pool.forms.values():
            lines.append(f"  {f}")
        return "\n".join(lines) if lines else "Form pool empty"

    if t0 == 'RECORD' and len(tokens) >= 3 and tokens[1] == 'FORM':
        try:
            form_n = int(tokens[2])
        except ValueError:
            return f"RECORD FORM: bad number '{tokens[2]}'"
        if form_n < FormPool.FIRST_CUSTOM_SLOT:
            return f"Slots 1–{FormPool.FIRST_CUSTOM_SLOT - 1} are built-in read-only. Use slot {FormPool.FIRST_CUSTOM_SLOT}+."

        # Collect name tokens until first phase,value pattern
        name_parts  = []
        bp_start    = 3
        for i, tok in enumerate(tokens[3:], 3):
            if ',' in tok:
                bp_start = i
                break
            name_parts.append(tok.capitalize())

        name = " ".join(name_parts) if name_parts else f"Form {form_n}"

        # Parse breakpoints: "0.0,0.0" "0.5,1.0" "1.0,0.0"
        breakpoints = []
        for tok in tokens[bp_start:]:
            try:
                p, v = tok.split(',')
                breakpoints.append([float(p), float(v)])
            except ValueError:
                return f"Bad breakpoint '{tok}' — format: phase,value  e.g. 0.5,1.0"

        if not breakpoints:
            return "Usage: RECORD FORM <n> [name] <phase,value> <phase,value> ..."

        form = FormPreset(form_n, name, 'breakpoints', breakpoints=breakpoints)
        form_pool.store(form_n, form)
        ShowFile.save_forms(form_pool)
        return f"Recorded: {form}  (auto-saved)"

    # ── FX helpers (used by FX commands and CLEAR) ───────────

    def _prog_fx_stop():
        """Stop all programmer-preview FX layers."""
        for fxid in _prog_fx_ids:
            fx_engine.remove(fxid)
        _prog_fx_ids.clear()
        active_fx.clear()

    def _prog_fx_start(fx_defs_by_fid):
        """
        Start live-preview FX layers for the given fixture→fx_defs mapping.
        fx_defs_by_fid: {fixture_id (int): [fx_def, ...]}

        Tree references are expanded before bucketing:
          color_id  → 'rgb' channel split into R/G/B layers scaled by preset
          group_id  → fixture list replaced by group members
          dim_id    → passed live to FXLayer as a size ceiling (no expansion needed)
        """
        expanded = _expand_color_fx(fx_defs_by_fid, color_pool)
        expanded = _expand_group_fx(expanded, patch, group_pool)
        for ld, targets in _bucket_fx_defs(expanded, patch):
            fxid = max(_prog_fx_ids, default=8999) + 1
            layer = fx_engine.add(
                fxid,
                ld.get('waveform', 'sine'),
                ld['channel'],
                rate_bpm     = ld.get('bpm',          _fx_params['rate_bpm']),
                size         = ld.get('size',         _fx_params['size']),
                targets      = targets,
                spread       = ld.get('spread',       _fx_params['spread']),
                phase_offset = ld.get('phase_offset', 0.0),
                infade       = ld.get('infade',       _fx_params['infade']),
                outfade      = ld.get('outfade',      _fx_params['outfade']),
                form_id      = ld.get('form_id'),
                rate_id      = ld.get('rate_id'),
                size_id      = ld.get('size_id'),
                spread_id    = ld.get('spread_id'),
                dim_id       = ld.get('dim_id'),
                block_size   = ld.get('block_size',      1),
                order        = ld.get('order',    'linear'),
                direction    = ld.get('direction','forward'),
            )
            _prog_fx_ids.append(fxid)
            active_fx.append(layer)

    def _prog_fx_rebuild():
        """
        Rebuild all programmer FX from prog.data in one shot.
        Called after any FX change so all fixtures keep their effects —
        not just the ones in the latest selection.
        """
        all_fx = {}
        for fid_str, vals in prog.data.items():
            if '.' in fid_str:
                continue
            layers = vals.get('fx')
            if layers:
                try:
                    all_fx[int(fid_str)] = layers
                except ValueError:
                    pass
        _prog_fx_stop()
        if all_fx:
            _prog_fx_start(all_fx)

    # ── FX commands ──────────────────────────────────────────
    # FX applies to the programmer against the current selection.
    # The FX def is written into prog.data[master_fid]['fx'] and a
    # live preview layer is started so output is visible immediately.
    # RECORD CUE captures FX defs along with colour/dim automatically.
    # CLEAR stage 2 (programmer) removes FX defs and stops preview.

    _WAVEFORMS = {'SINE', 'RAMP', 'PULSE', 'SQUARE', 'TRIANGLE', 'SAWTOOTH', 'FLICKER'}
    _CHANNELS  = {'RED', 'GREEN', 'BLUE', 'DIM'}

    # ── BPM / SIZE / SPREAD  — set global FX parameters ────────────
    # Updates live layers, programmer data, and GUI sliders in one shot.

    if t0 == 'BPM' and len(tokens) >= 2:
        try:
            val = float(tokens[1])
        except ValueError:
            return f"BPM: expected a number, got '{tokens[1]}'"
        val = max(10.0, min(480.0, val))
        _fx_params['rate_bpm'] = val
        now = time.monotonic()
        for layer in fx_engine._layers.values():
            if layer.fx_id >= 10000:  # skip executor (cue) FX
                continue
            layer.set_rate_smooth(val, now)
        for fvals in prog.data.values():
            for ld in fvals.get('fx', []):
                ld['bpm'] = val
        try:
            import dearpygui.dearpygui as _dpg_local
            _dpg_local.set_value("fx_rate", val)
        except Exception:
            pass
        return f"BPM → {val:.1f}"

    if t0 == 'SIZE' and len(tokens) >= 2:
        try:
            val = float(tokens[1])
        except ValueError:
            return f"SIZE: expected a number, got '{tokens[1]}'"
        val = max(0.0, min(100.0, val))
        _fx_params['size'] = val
        for layer in fx_engine._layers.values():
            if layer.fx_id >= 10000:  # skip executor (cue) FX
                continue
            layer.size = val
        for fvals in prog.data.values():
            for ld in fvals.get('fx', []):
                ld['size'] = val
        try:
            import dearpygui.dearpygui as _dpg_local
            _dpg_local.set_value("fx_size", val)
        except Exception:
            pass
        return f"Size → {val:.0f}"

    if t0 == 'SPREAD' and len(tokens) >= 2:
        try:
            val = float(tokens[1])
        except ValueError:
            return f"SPREAD: expected a number, got '{tokens[1]}'"
        val = max(0.0, min(100.0, val))
        _fx_params['spread'] = val
        for layer in fx_engine._layers.values():
            if layer.fx_id >= 10000:  # skip executor (cue) FX
                continue
            layer.spread = val
        for fvals in prog.data.values():
            for ld in fvals.get('fx', []):
                ld['spread'] = val
        try:
            import dearpygui.dearpygui as _dpg_local
            _dpg_local.set_value("fx_spread", val)
        except Exception:
            pass
        return f"Spread → {val:.1f}"

    if t0 == 'FX' and len(tokens) >= 2:
        sub = tokens[1]

        # FX FORM <n>  — set form on all running layers + store as pending in programmer
        if sub == 'FORM' and len(tokens) == 3:
            try:
                fid_n = int(tokens[2])
            except ValueError:
                return f"FX FORM: bad slot '{tokens[2]}'"
            form = form_pool.get(fid_n)
            if not form:
                return f"Form {fid_n} is empty"

            # Store pending form_id in programmer so next FX command picks it up
            _fx_params['pending_form_id'] = fid_n

            changed = 0
            # Update every active programmer-preview layer live
            for fxid in _prog_fx_ids:
                layer = fx_engine._layers.get(fxid)
                if layer:
                    layer.form_id = fid_n
                    changed += 1
            # Update FX defs already in programmer data
            for vals in prog.data.values():
                for ld in vals.get('fx', []):
                    ld['form_id'] = fid_n

            if changed:
                return f"Form → {form.name}  ({changed} layer(s) updated live)"
            return f"Form → {form.name}  (pending — next FX command will use this form)"

        if sub == 'CLEAR':
            # FX CLEAR            → clear all channels
            # FX CLEAR <channel>  → clear only that channel (dim / red / green / blue)
            if len(tokens) >= 3 and tokens[2].upper() in _CHANNELS:
                ch = tokens[2].upper().lower()
                for vals in prog.data.values():
                    existing = vals.get('fx', [])
                    filtered = [ld for ld in existing if ld.get('channel') != ch]
                    if filtered:
                        vals['fx'] = filtered
                    else:
                        vals.pop('fx', None)
                _prog_fx_rebuild()
                return f"FX {ch} cleared from programmer"
            _prog_fx_stop()
            # Also remove FX defs from programmer
            for vals in prog.data.values():
                vals.pop('fx', None)
            return "FX cleared from programmer"

        if sub == 'LIST':
            lines = []
            # Programmer FX
            prog_fx = {fid: v['fx'] for fid, v in prog.data.items()
                       if '.' not in fid and 'fx' in v}
            if prog_fx:
                lines.append("Programmer FX:")
                for fid, defs in prog_fx.items():
                    for ld in defs:
                        dist = []
                        if ld.get('block_size', 1) != 1:      dist.append(f"block={ld['block_size']}")
                        if ld.get('order', 'linear') != 'linear': dist.append(f"order={ld['order']}")
                        if ld.get('direction', 'forward') != 'forward': dist.append(f"dir={ld['direction']}")
                        if ld.get('target_scope'):             dist.append(ld['target_scope'])
                        dist_s = f" [{' '.join(dist)}]" if dist else ""
                        lines.append(f"  fixture {fid}: {ld['waveform']} {ld['channel']} "
                                     f"BPM={ld.get('bpm',60)} size={ld.get('size',200)}{dist_s}")
            else:
                lines.append("Programmer FX: (none)")
            # Active executor FX
            exec_fx_lines = []
            for eid, ex in sorted(executor_pool.executors.items()):
                if ex.is_active and ex._fx_ids and ex.fx_engine:
                    for fxid in ex._fx_ids:
                        layer = ex.fx_engine._layers.get(fxid)
                        if layer:
                            exec_fx_lines.append(
                                f"  Exec {eid}: {layer.waveform} {layer.channel} "
                                f"BPM={layer.rate_bpm:.0f} size={layer.size:.0f}")
            if exec_fx_lines:
                lines.append("Active executor FX:")
                lines.extend(exec_fx_lines)
            # FX pool
            if fx_pool.presets:
                lines.append("Pool:")
                for p in fx_pool.presets.values():
                    lines.append(f"  {p}")
            else:
                lines.append("Pool: (empty)")
            return "\n".join(lines)

        # FX [ADD] <waveform|FORM n|COLOR n> [channel] [BPM n] [SIZE n] [SPREAD n]
        #   [GROUP n] [DIMREF n] [BLOCK n] [ORDER RANDOM] [DIRECTION FWD|REV|BOUNCE] [PIXEL|FIXTURE]
        #
        # Tree references:
        #   COLOR n  — drives R/G/B from ColorPreset n (waveform drives intensity of that color)
        #   GROUP n  — target only fixtures in GroupPool slot n instead of programmer selection
        #   DIMREF n — live size ceiling: DimmerPreset n's level scales FX amplitude (0–1)
        add_mode = (sub == 'ADD')
        base_idx = 2 if add_mode else 1

        if base_idx >= len(tokens):
            return ("Usage: FX [ADD] <waveform|FORM n|COLOR n> [channel] "
                    "[BPM n] [SIZE n] [SPREAD n] [GROUP n] [DIMREF n] "
                    "[BLOCK n] [ORDER RANDOM] [DIRECTION FWD|REV|BOUNCE]")

        form_id  = None
        color_id = None
        waveform = tokens[base_idx]
        ch_idx   = base_idx + 1

        if waveform == 'FORM':
            try:
                form_id  = int(tokens[base_idx + 1])
                form     = form_pool.get(form_id)
                waveform = form.builtin_name or form.name.lower() if form else 'sine'
                ch_idx   = base_idx + 2
            except (IndexError, ValueError):
                return "Usage: FX [ADD] FORM <n> <channel> [...]"
        elif waveform == 'COLOR':
            # FX COLOR <preset_id> — drives R/G/B channels from the preset's color
            try:
                color_id = int(tokens[base_idx + 1])
                ch_idx   = base_idx + 2
            except (IndexError, ValueError):
                return "Usage: FX [ADD] COLOR <preset_id> [BPM n] [SIZE n] [GROUP n] [DIMREF n]"
            waveform = 'sine'
            channel  = 'rgb'   # virtual; expanded into R/G/B at _prog_fx_start time
        elif waveform not in _WAVEFORMS:
            return f"Unknown waveform '{waveform}' — use sine|ramp|pulse|square, FORM <n>, or COLOR <n>"

        if color_id is None:
            # Check if channel position is 'COLOR' (e.g. FX RAMP COLOR 3)
            if ch_idx < len(tokens) and tokens[ch_idx] == 'COLOR':
                try:
                    color_id = int(tokens[ch_idx + 1])
                    ch_idx  += 2
                except (IndexError, ValueError):
                    return "Usage: FX [ADD] <waveform> COLOR <preset_id>"
                waveform = waveform.lower()
                channel  = 'rgb'
            elif ch_idx >= len(tokens) or tokens[ch_idx] not in _CHANNELS:
                return f"Usage: FX [ADD] <waveform> red|green|blue|dim [BPM n] [SIZE n] [SPREAD n]"
            else:
                channel = tokens[ch_idx]

        up = raw.upper()
        def _fx_val(key, default):
            m = _re.search(rf'\b{key}\s+([\d.]+)', up)
            return float(m.group(1)) if m else default

        bpm       = _fx_val('BPM',     _fx_params['rate_bpm'])
        size      = _fx_val('SIZE',    _fx_params['size'])
        spread    = _fx_val('SPREAD',  _fx_params['spread'])
        phase     = _fx_val('PHASE',   0.0)
        infade    = _fx_val('INFADE',  _fx_params['infade'])
        outfade   = _fx_val('OUTFADE', _fx_params['outfade'])

        def _fx_pool_id(key):
            m = _re.search(rf'\b{key}\s+(\d+)', up)
            return int(m.group(1)) if m else None

        rate_id   = _fx_pool_id('RATE')
        size_id   = _fx_pool_id('SIZEP')
        spread_id = _fx_pool_id('SPREADP')
        dim_id    = _fx_pool_id('DIMREF')   # DimmerPreset slot as live size ceiling
        group_id  = _fx_pool_id('GROUP')    # GroupPool slot as target override

        # Distribution: BLOCK n groups adjacent targets into steps of n.
        # ORDER RANDOM shuffles step order (stable per effect); default LINEAR.
        # DIRECTION FWD|REV|BOUNCE — patch order / reversed / sweeps out-and-back.
        # PIXEL|FIXTURE picks target_scope; omit to use the per-channel default
        # (dim → whole fixtures, colour → individual pixels — see _bucket_fx_defs).
        up_tokens = up.split()

        block_m = _re.search(r'\bBLOCK\s+(\d+)', up)
        block_size = int(block_m.group(1)) if block_m else 1

        order = 'random' if 'RANDOM' in up_tokens else 'linear'

        direction = 'forward'
        dir_m = _re.search(r'\bDIRECTION\s+(\w+)', up)
        dir_word = dir_m.group(1) if dir_m else None
        if dir_word in ('REV', 'REVERSE') or 'REVERSE' in up_tokens:
            direction = 'reverse'
        elif dir_word == 'BOUNCE' or 'BOUNCE' in up_tokens:
            direction = 'bounce'
        elif dir_word in ('FWD', 'FORWARD'):
            direction = 'forward'

        target_scope = None
        if 'PIXEL' in up_tokens:
            target_scope = 'pixel'
        elif 'FIXTURE' in up_tokens:
            target_scope = 'fixture'

        # Use pending form from a prior "FX FORM <n>" call if none explicit here
        if form_id is None:
            form_id = _fx_params.pop('pending_form_id', None)

        fx_def = {
            'waveform':     waveform.lower(),
            'channel':      channel.lower(),
            'bpm':          bpm,
            'size':         size,
            'spread':       spread,
            'phase_offset': phase,
            'infade':       infade,
            'outfade':      outfade,
            'form_id':      form_id,
            'rate_id':      rate_id,
            'size_id':      size_id,
            'spread_id':    spread_id,
            'dim_id':       dim_id,
            'color_id':     color_id,
            'group_id':     group_id,
            'block_size':   block_size,
            'order':        order,
            'direction':    direction,
            'target_scope': target_scope,
        }

        # Resolve target fixtures — GROUP n overrides programmer selection
        if group_id is not None:
            grp = group_pool.get(group_id)
            if not grp:
                return f"Group {group_id} not found"
            sel_fids = [m.fixture_id for m in grp.recall(patch)]
            if not sel_fids:
                return f"Group {group_id} is empty"
        elif prog.selection:
            seen_m, sel_fids = set(), []
            for f in prog.selection:
                mid = f.fixture_id if isinstance(f, MasterFixture) else getattr(f, 'master_id', None)
                if mid and mid not in seen_m:
                    seen_m.add(mid)
                    sel_fids.append(mid)
        else:
            sel_fids = [m.fixture_id for m in patch.all_fixtures()]

        # Write into programmer data (master entries).
        # Each fixture gets its own copy of fx_def so per-fixture edits
        # (e.g. changing BPM on just one fixture) don't bleed to others.
        for fid in sel_fids:
            entry = prog.data.setdefault(str(fid), {})
            if not add_mode:
                entry['fx'] = [dict(fx_def)]
            else:
                entry.setdefault('fx', []).append(dict(fx_def))

        # Live preview — rebuild ALL programmer FX so other fixtures keep their effects
        _prog_fx_rebuild()

        ref_parts = []
        if group_id  is not None: ref_parts.append(f"group:{group_id}")
        if color_id  is not None: ref_parts.append(f"color:{color_id}")
        if dim_id    is not None: ref_parts.append(f"dimref:{dim_id}")
        ref_s = f" [{', '.join(ref_parts)}]" if ref_parts else ""
        verb  = "Added FX" if add_mode else "Applied FX"
        disp_ch = "rgb" if channel == 'rgb' else channel
        return f"{verb}: {waveform} {disp_ch}{ref_s} → {len(sel_fids)} fixture(s)"

    # RECORD FX <n> [name]  — snapshot programmer FX defs into the pool
    if t0 == 'RECORD' and len(tokens) >= 3 and tokens[1] == 'FX':
        try:
            fx_n = int(tokens[2])
        except ValueError:
            return f"RECORD FX: bad number '{tokens[2]}'"

        # Collect unique FX defs from programmer master entries
        seen, defs = set(), []
        for fid_str, vals in prog.data.items():
            if '.' in fid_str:
                continue
            for ld in vals.get('fx', []):
                key = (ld['waveform'], ld['channel'])
                if key not in seen:
                    seen.add(key)
                    defs.append(ld)

        if not defs:
            return "RECORD FX: no FX in programmer — apply with  FX SINE RED  first"

        name = " ".join(t.capitalize() for t in tokens[3:]) if len(tokens) > 3 else ""
        preset = FXPreset(fx_n, name or f"FX {fx_n}")
        for ld in defs:
            preset.add_layer(
                ld['waveform'], ld['channel'],
                bpm          = ld.get('bpm',    60.0),
                size         = ld.get('size',   100.0),
                spread       = ld.get('spread',   0.0),
                form_id      = ld.get('form_id'),
                rate_id      = ld.get('rate_id'),
                size_id      = ld.get('size_id'),
                spread_id    = ld.get('spread_id'),
                dim_id       = ld.get('dim_id'),
                color_id     = ld.get('color_id'),
                group_id     = ld.get('group_id'),
                block_size   = ld.get('block_size',      1),
                order        = ld.get('order',    'linear'),
                direction    = ld.get('direction','forward'),
                target_scope = ld.get('target_scope'),
            )
        fx_pool.store(fx_n, preset)
        ShowFile.save_fx_pool(fx_pool)
        return f"Recorded: {preset}  (auto-saved)"

    # FIRE FX <n> [GROUP n]  — write preset defs into programmer + preview
    # GROUP n overrides the preset's stored group_id or programmer selection.
    if t0 == 'FIRE' and len(tokens) >= 3 and tokens[1] == 'FX':
        try:
            fx_n = int(tokens[2])
        except ValueError:
            return f"FIRE FX: bad number '{tokens[2]}'"
        preset = fx_pool.get(fx_n)
        if not preset:
            return f"FX preset {fx_n} not found"

        # FIRE FX n GROUP g — group override at fire time
        _re_fire = _re
        fire_grp_m = _re_fire.search(r'\bGROUP\s+(\d+)', raw.upper())
        fire_group_id = int(fire_grp_m.group(1)) if fire_grp_m else None

        if fire_group_id is not None:
            grp = group_pool.get(fire_group_id)
            if not grp:
                return f"FIRE FX: Group {fire_group_id} not found"
            sel_fids = [m.fixture_id for m in grp.recall(patch)]
        elif prog.selection:
            seen_m, sel_fids = set(), []
            for f in prog.selection:
                mid = f.fixture_id if isinstance(f, MasterFixture) else getattr(f, 'master_id', None)
                if mid and mid not in seen_m:
                    seen_m.add(mid)
                    sel_fids.append(mid)
        else:
            sel_fids = [m.fixture_id for m in patch.all_fixtures()]

        # Write preset layers into programmer — channel-additive merge.
        # Layers on channels already covered by this preset are replaced;
        # layers on other channels (e.g. existing rainbow stays when adding dim) are kept.
        # For 'rgb' virtual channel, treat red/green/blue as the replaced set.
        new_channels = set()
        for ld in preset.layers:
            if ld['channel'] == 'rgb':
                new_channels.update(('red', 'green', 'blue'))
            else:
                new_channels.add(ld['channel'])

        for fid in sel_fids:
            entry = prog.data.setdefault(str(fid), {})
            kept  = [ld for ld in entry.get('fx', [])
                     if ld.get('channel') not in new_channels]
            fired_defs = [dict(ld) for ld in preset.layers]
            # Apply fire-time group override
            if fire_group_id is not None:
                for d in fired_defs:
                    d['group_id'] = fire_group_id
            entry['fx'] = kept + fired_defs

        _prog_fx_rebuild()

        ref_s = f" [group:{fire_group_id}]" if fire_group_id else ""
        return f"Fired: {preset}{ref_s}  → {len(sel_fids)} fixture(s)"

    # ── CLONE <src_id> TO <dst_id> ───────────────────────────
    # Copies all pool data from one fixture to another:
    # color/dim presets, group memberships, cue data (master + sub entries).
    if t0 == 'CLONE' and 'TO' in tokens:
        try:
            to_idx  = tokens.index('TO')
            src_id  = int(tokens[1])
            dst_ids = []
            # Support: CLONE 1 TO 7  OR  CLONE 1 TO 7 THRU 9
            rest = tokens[to_idx + 1:]
            if len(rest) == 3 and rest[1] == 'THRU':
                dst_ids = list(range(int(rest[0]), int(rest[2]) + 1))
            elif rest:
                dst_ids = [int(rest[0])]
        except (ValueError, IndexError):
            return "Usage: CLONE <src> TO <dst>  |  CLONE <src> TO <dst> THRU <end>"

        if src_id not in patch.fixtures:
            return f"Clone source fixture {src_id} not in patch"
        missing = [d for d in dst_ids if d not in patch.fixtures]
        if missing:
            return f"Destination(s) {missing} not in patch — patch them first"

        src_str  = str(src_id)
        src_master = patch.fixtures[src_id]
        n_subs   = len(src_master.sub_fixtures)

        for dst_id in dst_ids:
            dst_str = str(dst_id)

            # Color presets
            for preset in color_pool.presets.values():
                if src_str in preset.data:
                    preset.data[dst_str] = dict(preset.data[src_str])
                # Also copy per-sub entries (pixel-mapped colors)
                for si in range(1, n_subs + 1):
                    src_sub = f"{src_str}.{si}"
                    if src_sub in preset.data:
                        preset.data[f"{dst_str}.{si}"] = dict(preset.data[src_sub])

            # Dim presets
            for preset in dim_pool.presets.values():
                if src_str in preset.data:
                    preset.data[dst_str] = dict(preset.data[src_str])

            # Groups — add dst to every group that contains src
            for group in group_pool.groups.values():
                src_entry = ("master", src_id)
                dst_entry = ("master", dst_id)
                if src_entry in group.members and dst_entry not in group.members:
                    group.members.append(dst_entry)

            # Cues — copy master key and all sub-fixture keys
            for stack in cuestack_pool.stacks.values():
                for cue in stack.cues.values():
                    if src_str in cue.data:
                        cue.data[dst_str] = dict(cue.data[src_str])
                    for si in range(1, n_subs + 1):
                        src_sub = f"{src_str}.{si}"
                        if src_sub in cue.data:
                            cue.data[f"{dst_str}.{si}"] = dict(cue.data[src_sub])

        save_show()
        dst_label = dst_ids[0] if len(dst_ids) == 1 else f"{dst_ids[0]}–{dst_ids[-1]}"
        return f"Cloned fixture {src_id} → {dst_label}  ({len(dst_ids)} dest, show saved)"

    # ── SNAPSHOT ─────────────────────────────────────────────
    # SNAPSHOT <cue_num> [name] — record current live output (cue + programmer merged)
    # as a new cue. Unlike RECORD CUE which only records programmer data, SNAPSHOT
    # captures the full merged look (useful when multiple executors are running).
    if t0 == 'SNAPSHOT' and len(tokens) >= 2:
        try:
            cue_num = float(tokens[1])
        except ValueError:
            return f"SNAPSHOT: bad cue number '{tokens[1]}'"
        cs = _active_stack()
        if not cs:
            return "SNAPSHOT: no active cuestack"
        cue_name = _name_after(raw, 2) or f"Snapshot {cue_num}"

        cue_merged = output_state._merged_cue_layer()
        prog_layer = output_state.programmer_layer

        snapshot_data = {}
        for master in patch.all_fixtures():
            fid = str(master.fixture_id)
            pm  = prog_layer.get(fid, {})
            cm  = cue_merged.get(fid, {})
            dim = pm.get('dim', cm.get('dim'))
            if dim is not None:
                snapshot_data.setdefault(fid, {})['dim'] = float(dim)
            for sub in master.sub_fixtures.values():
                sfid = str(sub.fixture_id)
                ps   = prog_layer.get(sfid, {})
                cs_  = cue_merged.get(sfid, {})
                r = ps.get('red',   cs_.get('red',   0))
                g = ps.get('green', cs_.get('green', 0))
                b = ps.get('blue',  cs_.get('blue',  0))
                if r or g or b:
                    snapshot_data[sfid] = {'red': float(r), 'green': float(g), 'blue': float(b)}

        if not snapshot_data:
            return "SNAPSHOT: nothing in output — all fixtures are dark"

        cue = Cue(cue_num, cue_name)
        cue.data = snapshot_data
        cs.cues[float(cue_num)] = cue
        save_show()
        fixture_count = len({k.split('.')[0] for k in snapshot_data})
        return f"Snapshot → Cue {cue_num}: {cue_name}  ({fixture_count} fixtures, show saved)"

    # ── Blind mode ───────────────────────────────────────────
    if t0 == 'BLIND':
        output_state.blind = True
        return "BLIND mode ON — programmer suppressed from DMX output"

    if t0 == 'LIVE':
        output_state.blind = False
        return "LIVE mode — programmer active in output"

    if t0 == 'BLACKOUT':
        off = len(tokens) > 1 and tokens[1] == 'OFF'
        if off or output_state.master_level == 0.0:
            output_state.master_level = _blackout_saved_level[0]
            return f"BLACKOUT OFF — master restored to {output_state.master_level:.0%}"
        else:
            _blackout_saved_level[0] = output_state.master_level
            output_state.master_level = 0.0
            return "BLACKOUT ON — all output cut (BLACKOUT OFF to restore)"

    if t0 == 'BBO':
        _blackout_saved_level[0] = output_state.master_level
        output_state.master_level = 0.0
        return "BLACKOUT ON"

    # ── Save ─────────────────────────────────────────────────
    if t0 == 'SAVE':
        if len(tokens) >= 3 and tokens[1] == 'AS':
            name = raw.split(None, 2)[2] if len(raw.split(None, 2)) > 2 else ""
            return save_show_as(name)
        save_show()
        return "Show saved."

    if t0 in ('LOAD',) and len(tokens) >= 3 and tokens[1] in ('SHOW', 'CS'):
        if tokens[1] == 'SHOW':
            name = raw.split(None, 2)[2] if len(raw.split(None, 2)) > 2 else ""
            return load_show_from(name)

    if t0 == 'LIST' and len(tokens) >= 2 and tokens[1] == 'SHOWS':
        return list_shows()

    if t0 == 'EXPORT' and len(tokens) >= 2 and tokens[1] == 'PRESETS':
        what = tokens[2] if len(tokens) >= 3 else 'all'
        return export_presets(what)

    if t0 == 'IMPORT' and len(tokens) >= 3 and tokens[1] == 'PRESETS':
        path = raw.split(None, 2)[2]
        return import_presets(path)

    if t0 == 'OSC':
        t1 = tokens[1] if len(tokens) > 1 else ''
        if t1 == 'TARGET' and len(tokens) >= 5:
            osc.add_target(tokens[2], tokens[3], int(tokens[4]))
            return f"OSC target '{tokens[2]}' → {tokens[3]}:{tokens[4]}"
        if t1 == 'REMOVE' and len(tokens) >= 3:
            osc.remove_target(tokens[2])
            return f"OSC target '{tokens[2]}' removed"
        if t1 == 'LIST':
            lines = []
            for nm, c in osc._clients.items():
                lines.append(f"  [{nm}] → {c._address}:{c._port}")
            return "OSC targets:\n" + ("\n".join(lines) if lines else "  (none)")
        if t1 == 'SEND' and len(tokens) >= 3:
            addr = tokens[2]
            args_raw = tokens[3:]
            def _cast(v):
                try: return int(v)
                except ValueError:
                    try: return float(v)
                    except ValueError: return v
            osc.send(addr, *[_cast(x) for x in args_raw])
            return f"OSC sent {addr}"
        if t1 == 'MONITOR':
            return "OSC MONITOR: see terminal output"
        if t1 == 'FEEDBACK' and len(tokens) >= 4:
            host = tokens[2]
            port = int(tokens[3])
            osc.add_feedback_target(host, port)
            return f"OSC feedback → {host}:{port}  (state broadcasts at ~1 Hz)"
        if t1 == 'FEEDBACK' and len(tokens) == 2:
            osc.remove_target("_feedback")
            return "OSC feedback disabled"
        return "OSC usage: TARGET name host port | REMOVE name | LIST | FEEDBACK host port | SEND /addr [args]"

    if t0 == 'MIDI' and len(tokens) >= 3 and tokens[1] == 'CLOCK':
        if tokens[2] == 'ON':
            midi.clock_sync = True
            midi._clock_times = []
            midi.clock_bpm = None
            def _clock_cb(bpm):
                # Forward detected BPM to FX engine via run_command on main thread
                # (just store — the GUI tick reads midi.clock_bpm and updates sliders)
                pass
            midi.clock_callback = _clock_cb
            return "MIDI clock sync ON — BPM will lock to incoming clock when detected"
        elif tokens[2] == 'OFF':
            midi.clock_sync = False
            midi.clock_bpm  = None
            midi.clock_callback = None
            return "MIDI clock sync OFF"
        return "MIDI CLOCK ON | OFF"

    # ── Stack info ───────────────────────────────────────────
    if t0 in ('CUES', 'STACK', 'LIST'):
        cs = _active_stack()
        if not cs:
            return "No active cuestack"
        lines = [f"Cuestack {cs.stack_id} — {cs.name}  [executor {active_executor[0]}]"]
        for n in cs._sorted_cue_numbers():
            c   = cs.cues[n]
            cur = " ◀" if n == cs.current else ""
            lines.append(f"  [{n:.0f}] {c.name}  Fade:{c.fade_time}s{cur}")
        return "\n".join(lines)

    # ── Group recall / record ─────────────────────────────────
    # GROUP <n>                — recall (select fixtures)
    # RECORD GROUP <n> ["name"] — save current selection as group
    if t0 == 'GROUP' and len(tokens) > 1:
        try:
            gid = int(tokens[1])
        except ValueError:
            return f"GROUP: bad id '{tokens[1]}'"
        group_pool.recall(gid, prog)
        g = group_pool.get(gid)
        return f"Group {gid} recalled" if g else f"Group {gid} not found"

    if t0 == 'RECORD' and len(tokens) > 2 and tokens[1] == 'GROUP':
        try:
            gid = int(tokens[2])
        except ValueError:
            return f"RECORD GROUP: bad slot number '{tokens[2]}'"
        name = _name_after(raw, 3) or f"Group {gid}"
        if not prog.selection:
            return (f"RECORD GROUP: nothing selected — "
                    f"first type  1 THRU 6  (or any fixture range)  "
                    f"then  RECORD GROUP {gid} {name}")
        g = group_pool.record(gid, prog, name=name)
        if g:
            save_show()
            return f"Recorded: {g}  (show saved)"
        return "RECORD GROUP: nothing selected"

    # ── Colour preset recall / record ─────────────────────────
    # COLOR <n>                 — apply to current selection
    # RECORD COLOR <n> [name]   — save RGB from programmer
    if t0 in ('COLOR', 'COLOUR') and len(tokens) > 1:
        try:
            pid = int(tokens[1])
        except ValueError:
            return f"COLOR: bad slot number '{tokens[1]}'"
        p = color_pool.get(pid)
        if not p:
            return f"Color Preset {pid} is empty  (use: RECORD COLOR {pid} Red)"
        p.apply(prog)
        return f"Applied: {p}"

    if t0 == 'RECORD' and len(tokens) > 2 and tokens[1] in ('COLOR', 'COLOUR'):
        try:
            pid = int(tokens[2])
        except ValueError:
            return f"RECORD COLOR: bad slot number '{tokens[2]}'"
        name = _name_after(raw, 3) or f"Color {pid}"
        p = color_pool.record(pid, prog, name=name)
        if p and p.data:
            save_show()
            return f"Recorded: {p}  (show saved)"
        return "RECORD COLOR: no RGB data in programmer  (set a colour first)"

    # ── Dim preset recall / record ────────────────────────────
    # DIM PRESET <n>            — apply dim preset n
    # DIM <val>                 — set dimmer to val% (raw)
    # RECORD DIM <n> [name]     — save dimmer from programmer
    if t0 == 'DIM' and len(tokens) > 1:
        if tokens[1] == 'PRESET' and len(tokens) > 2:
            try:
                pid = int(tokens[2])
            except ValueError:
                return f"DIM PRESET: bad slot number '{tokens[2]}'"
            p = dim_pool.get(pid)
            if not p:
                return f"Dim Preset {pid} is empty  (use: RECORD DIM {pid} Full)"
            p.apply(prog)
            return f"Applied: {p}"
        # bare DIM <val> → raw dimmer value (AT DIM <val>)
        try:
            val = float(tokens[1].rstrip('%'))
        except ValueError:
            return f"DIM: bad value '{tokens[1]}'  (use: DIM 80  or  DIM PRESET 1)"
        prog.execute(f"AT DIM {val}")
        return ""

    if t0 == 'RECORD' and len(tokens) > 2 and tokens[1] == 'DIM':
        try:
            pid = int(tokens[2])
        except ValueError:
            return f"RECORD DIM: bad slot number '{tokens[2]}'"
        name = _name_after(raw, 3) or f"Dimmer {pid}"
        p = dim_pool.record(pid, prog, name=name)
        if p and p.data:
            save_show()
            return f"Recorded: {p}  (show saved)"
        return "RECORD DIM: no dimmer data in programmer  (set a dim level first)"

    # ── Attribute pool record / recall ───────────────────────────
    # Covers: POSITION, GOBO, ZOOM, FOCUS, BEAM, CONTROL
    # RECORD POSITION 1 [name]   — snapshot pan/tilt from programmer
    # POSITION 1                 — apply position preset 1 to programmer
    _ATTR_POOL_MAP = {
        'POSITION': position_pool,
        'GOBO':     gobo_pool,
        'ZOOM':     zoom_pool,
        'FOCUS':    focus_pool,
        'BEAM':     beam_pool,
        'CONTROL':  control_pool,
    }
    if t0 == 'RECORD' and len(tokens) > 2 and tokens[1] in _ATTR_POOL_MAP:
        pool_key = tokens[1]
        pool     = _ATTR_POOL_MAP[pool_key]
        try:
            pid = int(tokens[2])
        except ValueError:
            return f"RECORD {pool_key}: bad slot number '{tokens[2]}'"
        name = _name_after(raw, 3) or f"{pool_key.title()} {pid}"
        p = pool.record(pid, prog, name=name)
        if p and p.data:
            save_show()
            return f"Recorded: {p}  (show saved)"
        return (f"RECORD {pool_key}: no {pool_key.lower()} data in programmer "
                f"(channels: {', '.join(pool.relevant_channels)})")

    if t0 in _ATTR_POOL_MAP and len(tokens) > 1:
        pool_key = t0
        pool     = _ATTR_POOL_MAP[pool_key]
        try:
            pid = int(tokens[1])
        except ValueError:
            return f"{pool_key}: bad slot number '{tokens[1]}'"
        p = pool.get(pid)
        if not p:
            return f"{pool_key} Preset {pid} is empty  (use: RECORD {pool_key} {pid} Name)"
        p.apply(prog)
        return f"Applied: {p}"

    # ── Rate / Size / Spread pool record ─────────────────────────
    # RECORD RATE <n> [name] <bpm>      — e.g. RECORD RATE 5 Strobe 240
    if t0 == 'RECORD' and len(tokens) >= 4 and tokens[1] == 'RATE':
        try:
            pid = int(tokens[2])
        except ValueError:
            return f"RECORD RATE: bad slot '{tokens[2]}'"
        try:
            bpm = float(tokens[-1])
        except ValueError:
            return "RECORD RATE: last token must be BPM value  e.g. RECORD RATE 5 Strobe 240"
        name = " ".join(tokens[3:-1]).title() or f"Rate {pid}"
        p = RatePreset(pid, name, bpm)
        rate_pool.store(pid, p)
        ShowFile.save_rate_pool(rate_pool)
        return f"Recorded: {p}  (saved)"

    # RECORD SIZEP <n> [name] <size>    — e.g. RECORD SIZEP 4 Blinding 255
    if t0 == 'RECORD' and len(tokens) >= 4 and tokens[1] == 'SIZEP':
        try:
            pid = int(tokens[2])
        except ValueError:
            return f"RECORD SIZEP: bad slot '{tokens[2]}'"
        try:
            size = float(tokens[-1])
        except ValueError:
            return "RECORD SIZEP: last token must be size value 0-100  e.g. RECORD SIZEP 4 Big 100"
        name = " ".join(tokens[3:-1]).title() or f"Size {pid}"
        p = SizePreset(pid, name, size)
        size_pool.store(pid, p)
        ShowFile.save_size_pool(size_pool)
        return f"Recorded: {p}  (saved)"

    # RECORD SPREADP <n> [name] <spread>  — e.g. RECORD SPREADP 4 Wave 0.5
    if t0 == 'RECORD' and len(tokens) >= 4 and tokens[1] == 'SPREADP':
        try:
            pid = int(tokens[2])
        except ValueError:
            return f"RECORD SPREADP: bad slot '{tokens[2]}'"
        try:
            spread = float(tokens[-1])
        except ValueError:
            return "RECORD SPREADP: last token must be spread 0.0-1.0  e.g. RECORD SPREADP 4 Wave 0.5"
        name = " ".join(tokens[3:-1]).title() or f"Spread {pid}"
        p = SpreadPreset(pid, name, spread)
        spread_pool.store(pid, p)
        ShowFile.save_spread_pool(spread_pool)
        return f"Recorded: {p}  (saved)"

    # LIST RATE / SIZEP / SPREADP / FORM
    if t0 == 'LIST' and len(tokens) >= 2:
        sub = tokens[1]
        if sub == 'RATE':
            lines = ["Rate Presets:"] + [f"  {p}" for p in sorted(rate_pool.presets.values(), key=lambda x: x.preset_id)]
            return "\n".join(lines)
        if sub in ('SIZEP', 'SIZE'):
            lines = ["Size Presets:"] + [f"  {p}" for p in sorted(size_pool.presets.values(), key=lambda x: x.preset_id)]
            return "\n".join(lines)
        if sub in ('SPREADP', 'SPREAD'):
            lines = ["Spread Presets:"] + [f"  {p}" for p in sorted(spread_pool.presets.values(), key=lambda x: x.preset_id)]
            return "\n".join(lines)
        if sub == 'FORM':
            lines = ["Form Presets:"] + [f"  {f}" for f in sorted(form_pool.forms.values(), key=lambda x: x.form_id)]
            return "\n".join(lines)
        if sub in ('COLOR', 'COLOUR', 'COLORS', 'COLOURS'):
            if not color_pool.presets:
                return "Color pool is empty"
            lines = ["Color Presets:"]
            for pid in sorted(color_pool.presets):
                p = color_pool.presets[pid]
                # Sample RGB from first sub-fixture entry that has RGB data
                rgb = "—"
                for fid, vals in p.data.items():
                    if 'red' in vals:
                        r, g, b = int(vals['red']), int(vals.get('green', 0)), int(vals.get('blue', 0))
                        rgb = f"R{r} G{g} B{b}"
                        break
                lines.append(f"  [{pid}] {p.name}  {rgb}")
            return "\n".join(lines)
        if sub in ('DIM', 'DIMS'):
            if not dim_pool.presets:
                return "Dim pool is empty"
            lines = ["Dim Presets:"]
            for pid in sorted(dim_pool.presets):
                p = dim_pool.presets[pid]
                dim_val = next((v.get('dim') for v in p.data.values() if 'dim' in v), None)
                dim_str = f"{dim_val:.0%}" if dim_val is not None else "?"
                lines.append(f"  [{pid}] {p.name}  {dim_str}")
            return "\n".join(lines)
        if sub in ('GROUP', 'GROUPS'):
            if not group_pool.groups:
                return "Group pool is empty"
            lines = ["Groups:"]
            for gid in sorted(group_pool.groups):
                g = group_pool.groups[gid]
                count = len(g.members)
                lines.append(f"  [{gid}] {g.name}  ({count} entries)")
            return "\n".join(lines)
        if sub in ('FX', 'FXPRESET', 'FXPRESETS'):
            lines = [f"FX Presets:"]
            for pid in sorted(fx_pool.presets):
                p = fx_pool.presets[pid]
                waveforms = ", ".join(
                    f"{ld.get('waveform','?')}/{ld.get('channel','?')}"
                    for ld in p.layers)
                lines.append(f"  [{pid}] {p.name}  {waveforms or '(empty)'}")
            return "\n".join(lines) if len(lines) > 1 else "FX pool is empty"
        if sub in ('CUESTACKS', 'STACKS', 'CS'):
            lines = ["CueStacks:"]
            for sid in sorted(cuestack_pool.stacks):
                cs = cuestack_pool.stacks[sid]
                cue_count = len(cs.cues)
                cur = f"  ◀ on Cue {cs.current:.0f}" if cs.current is not None else ""
                lines.append(f"  [{sid}] {cs.name}  ({cue_count} cues){cur}")
            return "\n".join(lines) if len(lines) > 1 else "No cuestacks recorded"

    # ── Clear — programmer only, never touches cuestacks ────────
    # ── RELEASE — stop executor(s) ───────────────────────────
    # ── PRIORITY — set executor merge priority ────────────────
    if t0 == 'PRIORITY' and len(tokens) >= 3:
        try:
            n = int(tokens[1])
        except ValueError:
            return "Usage: PRIORITY <n> HIGH | LOW | NORMAL"
        lvl_str = tokens[2]
        lvl_map = {'HIGH': 1, 'HI': 1, 'LOW': -1, 'LO': -1, 'NORMAL': 0, 'NRM': 0}
        if lvl_str not in lvl_map:
            return f"Unknown priority '{lvl_str}' — use HIGH, LOW or NORMAL"
        ex = executor_pool.get(n)
        ex.priority = lvl_map[lvl_str]
        lbl = Executor.PRIORITY_LABELS[ex.priority]
        return f"Executor {n} priority → {lbl}"

    if t0 == 'RELEASE':
        if len(tokens) == 1 or (len(tokens) == 2 and tokens[1] == 'ALL'):
            stopped = []
            for ex in executor_pool.executors.values():
                if ex.is_active:
                    ex.stop()
                    stopped.append(ex.exec_id)
            return f"Released {len(stopped)} executor(s): {stopped}" if stopped else "No active executors"
        try:
            n = int(tokens[1])
        except (ValueError, IndexError):
            return "Usage: RELEASE <n>  or  RELEASE ALL"
        ex = executor_pool.get(n)
        if ex.is_active:
            ex.stop()
            return f"Released executor {n}"
        return f"Executor {n} was not running"

    # ── CUE timing editor (no programmer required) ─────────────
    # CUE <n> FADE/INFADE/OUTFADE <t> [DELAY <t>] [CFADE <t>] [DFADE <t>]
    # CS <n> CUE <m> FADE <t> [...]
    # RECORD CUE <n> FADE <t>  also works when programmer is empty (updates existing cue)
    _TIMING_KW = {'FADE', 'INFADE', 'OUTFADE', 'DELAY',
                  'CFADE', 'CINFADE', 'DFADE', 'DINFADE', 'CDELAY', 'DDELAY'}
    _has_timing = bool(_TIMING_KW & set(tokens))

    # CUE <n> SHOW / INFO — inspect cue contents without firing it
    if t0 == 'CUE' and len(tokens) >= 3 and tokens[2] in ('SHOW', 'INFO', 'PRINT'):
        try:
            cue_num = float(tokens[1])
        except ValueError:
            return f"CUE: bad cue number '{tokens[1]}'"
        cs = _active_stack()
        if not cs:
            return "CUE: no active cuestack"
        cue = cs.cues.get(cue_num)
        if not cue:
            return f"Cue {cue_num} not found in active cuestack"
        lines = [f"Cue {cue_num}: {cue.name}  |  Fade:{cue.fade_time}s  Delay:{cue.delay_time}s"]
        # Gather master-level keys (dim, fx) and sub-fixture RGB
        masters = {}; subs = {}
        for fid, vals in cue.data.items():
            if '.' in str(fid):
                subs[fid] = vals
            else:
                masters[fid] = vals
        for fid, vals in sorted(masters.items()):
            parts = []
            if 'dim' in vals:
                parts.append(f"dim:{vals['dim']:.0%}")
            fx_defs = vals.get('fx', [])
            if fx_defs:
                for ld in fx_defs:
                    parts.append(f"FX:{ld.get('waveform','?')} {ld.get('channel','?')} {ld.get('bpm',60):.0f}BPM")
            if parts:
                lines.append(f"  Fixture {fid}: {', '.join(parts)}")
        # Sub-fixture RGB — show unique colors only
        color_map = {}
        for fid, vals in subs.items():
            r = vals.get('red', 0); g = vals.get('green', 0); b = vals.get('blue', 0)
            color_map.setdefault((r, g, b), []).append(fid)
        for (r, g, b), fids in sorted(color_map.items()):
            if r == 0 and g == 0 and b == 0:
                continue
            sample = fids[0]
            lines.append(f"  Pixel {sample} (+{len(fids)-1} others): R{r} G{g} B{b}")
        if len(lines) == 1:
            lines.append("  (empty — no data recorded)")
        return "\n".join(lines)

    if _has_timing and t0 == 'CUE' and len(tokens) >= 3:
        try:
            cue_num = float(tokens[1])
        except ValueError:
            return f"CUE: bad cue number '{tokens[1]}'"
        cs = _active_stack()
        if not cs:
            return "CUE: no active cuestack"
        cue = cs.cues.get(float(cue_num))
        if not cue:
            return f"Cue {cue_num} not found in active cuestack"
        _apply_timing_edit(cue, raw)
        save_show()
        return f"Updated: {cue}"

    if _has_timing and t0 in ('CS', 'CUESTACK') and 'CUE' in tokens:
        cue_idx = tokens.index('CUE')
        try:
            cs_n    = int(tokens[1])
            cue_num = float(tokens[cue_idx + 1])
        except (ValueError, IndexError):
            return "Usage: CS <n> CUE <m> FADE <t> [DELAY <t>] [CFADE <t>] [DFADE <t>]"
        cs = cuestack_pool.get(cs_n)
        if not cs:
            return f"Cuestack {cs_n} not found"
        cue = cs.cues.get(float(cue_num))
        if not cue:
            return f"Cue {cue_num} not found in cuestack {cs_n}"
        _apply_timing_edit(cue, raw)
        save_show()
        return f"Updated: {cue}"

    # RENAME CUESTACK <n> <new name>
    # RENAME CUE <n> <new name>          (active cuestack)
    # RENAME CS <n> CUE <m> <new name>   (explicit cuestack)
    # RENAME COLOR/COLOUR <n> <new name>
    # RENAME DIM <n> <new name>
    # RENAME GROUP <n> <new name>
    # RENAME FX <n> <new name>
    # RENAME RATE/SIZEP/SPREADP/FORM <n> <new name>
    if t0 == 'RENAME' and len(tokens) >= 3:
        sub = tokens[1]

        # RENAME CUESTACK <n> <name>
        if sub == 'CUESTACK':
            try:
                n = int(tokens[2])
            except ValueError:
                return f"RENAME CUESTACK: bad number '{tokens[2]}'"
            cs = cuestack_pool.get(n)
            if not cs:
                return f"Cuestack {n} not found"
            new_name = _name_after(raw, 3)
            if not new_name:
                return "RENAME CUESTACK: provide a new name"
            cs.name = new_name
            save_show()
            return f"Cuestack {n} → \"{new_name}\""

        # RENAME CS <n> CUE <m> <name>  or  RENAME CUE <n> <name>
        if sub == 'CUE' or (sub == 'CS' and 'CUE' in tokens):
            if sub == 'CS' and 'CUE' in tokens:
                cue_idx = tokens.index('CUE')
                try:
                    cs_n    = int(tokens[2])
                    cue_num = float(tokens[cue_idx + 1])
                except (ValueError, IndexError):
                    return "Usage: RENAME CS <n> CUE <m> <name>"
                cs = cuestack_pool.get(cs_n)
                if not cs:
                    return f"Cuestack {cs_n} not found"
                new_name = _name_after(raw, cue_idx + 2)
            else:
                try:
                    cue_num = float(tokens[2])
                except ValueError:
                    return f"RENAME CUE: bad cue number '{tokens[2]}'"
                cs = _active_stack()
                if not cs:
                    return "RENAME CUE: no active cuestack"
                new_name = _name_after(raw, 3)
            if not new_name:
                return "RENAME CUE: provide a new name"
            cue = cs.cues.get(float(cue_num))
            if not cue:
                return f"Cue {cue_num} not found"
            cue.name = new_name
            save_show()
            return f"Cue {cue_num} → \"{new_name}\""

        # RENAME COLOR / COLOUR <n> <name>
        if sub in ('COLOR', 'COLOUR'):
            try:
                n = int(tokens[2])
            except ValueError:
                return f"RENAME COLOR: bad number '{tokens[2]}'"
            p = color_pool.get(n)
            if not p:
                return f"Color preset {n} not found"
            new_name = _name_after(raw, 3)
            if not new_name:
                return "RENAME COLOR: provide a new name"
            p.name = new_name
            save_show()
            return f"Color {n} → \"{new_name}\""

        # RENAME DIM <n> <name>
        if sub == 'DIM':
            try:
                n = int(tokens[2])
            except ValueError:
                return f"RENAME DIM: bad number '{tokens[2]}'"
            p = dim_pool.get(n)
            if not p:
                return f"Dim preset {n} not found"
            new_name = _name_after(raw, 3)
            if not new_name:
                return "RENAME DIM: provide a new name"
            p.name = new_name
            save_show()
            return f"Dim {n} → \"{new_name}\""

        # RENAME GROUP <n> <name>
        if sub == 'GROUP':
            try:
                n = int(tokens[2])
            except ValueError:
                return f"RENAME GROUP: bad number '{tokens[2]}'"
            g = group_pool.get(n)
            if not g:
                return f"Group {n} not found"
            new_name = _name_after(raw, 3)
            if not new_name:
                return "RENAME GROUP: provide a new name"
            g.name = new_name
            save_show()
            return f"Group {n} → \"{new_name}\""

        # RENAME FX <n> <name>
        if sub == 'FX':
            try:
                n = int(tokens[2])
            except ValueError:
                return f"RENAME FX: bad number '{tokens[2]}'"
            p = fx_pool.get(n)
            if not p:
                return f"FX preset {n} not found"
            new_name = _name_after(raw, 3)
            if not new_name:
                return "RENAME FX: provide a new name"
            p.name = new_name
            save_show()
            return f"FX {n} → \"{new_name}\""

        # RENAME RATE / SIZEP / SPREADP / FORM <n> <name>
        _rename_pool_map = {
            'RATE':    rate_pool.presets,
            'SIZEP':   size_pool.presets,
            'SPREADP': spread_pool.presets,
            'FORM':    form_pool.forms,
        }
        if sub in _rename_pool_map:
            try:
                n = int(tokens[2])
            except ValueError:
                return f"RENAME {sub}: bad number '{tokens[2]}'"
            store = _rename_pool_map[sub]
            item  = store.get(n)
            if not item:
                return f"{sub} preset {n} not found"
            new_name = _name_after(raw, 3)
            if not new_name:
                return f"RENAME {sub}: provide a new name"
            item.name = new_name
            save_show()
            return f"{sub} {n} → \"{new_name}\""

        return f"RENAME: unknown type '{sub}' — use CUESTACK, CUE, COLOR, DIM, GROUP, FX, RATE, SIZEP, SPREADP, FORM"

    # ── COPY CUE ──────────────────────────────────────────────────────────────
    # COPY CUE <src> TO <dst>               — within active cuestack
    # COPY CUE <src> TO <dst> <name>        — with new name
    # COPY CS <cs> CUE <src> TO <dst>       — explicit source cuestack
    # COPY CS <cs> CUE <src> TO CS <cs2> CUE <dst>  — cross-cuestack
    if t0 == 'COPY':
        try:
            # Locate TO keyword
            if 'TO' not in tokens:
                return "COPY CUE: missing TO — e.g. COPY CUE 3 TO 5"
            to_idx = tokens.index('TO')

            # Parse source side (before TO)
            src_tokens = tokens[1:to_idx]
            if src_tokens and src_tokens[0] in ('CS', 'CUESTACK'):
                if len(src_tokens) < 3 or src_tokens[2] not in ('CUE',):
                    return "COPY: use COPY CS <n> CUE <src> TO ..."
                src_cs_n = int(src_tokens[1])
                src_cue_n = float(src_tokens[3]) if len(src_tokens) > 3 else float(src_tokens[2])
                # re-parse: CS <n> CUE <src>
                src_cs_n  = int(src_tokens[1])
                src_cue_n = float(src_tokens[3])
                src_cs = cuestack_pool.get(src_cs_n)
            elif src_tokens and src_tokens[0] == 'CUE':
                src_cue_n = float(src_tokens[1])
                src_cs    = cuestack_pool.get(active_executor[0])
            else:
                return "COPY: use COPY CUE <n> TO <m>  or  COPY CS <n> CUE <src> TO ..."

            # Parse destination side (after TO)
            dst_tokens = tokens[to_idx + 1:]
            if not dst_tokens:
                return "COPY CUE: missing destination after TO"

            if dst_tokens[0] in ('CS', 'CUESTACK'):
                # COPY ... TO CS <n> CUE <dst>
                if len(dst_tokens) < 4 or dst_tokens[2] != 'CUE':
                    return "COPY: use ... TO CS <n> CUE <dst>"
                dst_cs_n  = int(dst_tokens[1])
                dst_cue_n = float(dst_tokens[3])
                dst_cs    = cuestack_pool.get(dst_cs_n)
                new_name  = _name_after(raw, tokens.index('CUE', to_idx + 1) + 2) if len(dst_tokens) > 4 else ""
            else:
                dst_cue_n = float(dst_tokens[0])
                dst_cs    = cuestack_pool.get(active_executor[0])
                new_name  = " ".join(dst_tokens[1:]) if len(dst_tokens) > 1 else ""

            if not src_cs:
                return f"COPY CUE: source cuestack not found"
            if not dst_cs:
                return f"COPY CUE: destination cuestack not found"

            src_cue = src_cs.get_cue(src_cue_n)
            if not src_cue:
                return f"COPY CUE: cue {src_cue_n} not found in '{src_cs.name}'"

            # Build the destination cue — deep-copy all data
            dst_cue = Cue(
                cue_number  = dst_cue_n,
                name        = new_name if new_name else src_cue.name,
                fade_time   = src_cue.fade_time,
                delay_time  = src_cue.delay_time,
                fade_times  = copy.deepcopy(src_cue.fade_times),
                delay_times = copy.deepcopy(src_cue.delay_times),
            )
            dst_cue.data = copy.deepcopy(src_cue.data)
            dst_cs.cues[float(dst_cue_n)] = dst_cue
            save_show()
            return (f"Copied Cue {src_cue_n} '{src_cue.name}' → "
                    f"Cue {dst_cue_n} '{dst_cue.name}'  in '{dst_cs.name}'")

        except (ValueError, IndexError) as _e:
            return f"COPY CUE: bad syntax — {_e}"

    if t0 == 'KILL' and len(tokens) >= 2 and tokens[1] == 'FX':
        # Write fx_kill flag into programmer master data for selected (or all) fixtures.
        # The FX engine keeps running; the flag suppresses FX in the output merge.
        # CLEAR removes this flag so cue FX resumes automatically.
        masters = [f for f in prog.selection if isinstance(f, MasterFixture)]
        if not masters:
            masters = list(patch.all_fixtures())
        _prog_fx_stop()
        for master in masters:
            fid = str(master.fixture_id)
            if fid not in prog.data:
                prog.data[fid] = {}
            prog.data[fid]['fx_kill'] = True
        return (f"FX killed for {len(masters)} fixture(s) — "
                "record into cue to make permanent, or CLEAR to release")

    if t0 == 'CLEAR' and len(tokens) == 2 and tokens[1] == 'FX':
        cleared = 0
        for fid, vals in prog.data.items():
            if 'fx' in vals:
                del vals['fx']
                cleared += 1
            vals.pop('fx_kill', None)
        _prog_fx_stop()
        _fx_params.pop('pending_form_id', None)
        return f"FX cleared from {cleared} fixture(s) — colour/dim preserved"

    # CLEAR COLOR/DIM/GROUP/FX <n> — clear a specific pool slot
    if t0 == 'CLEAR' and len(tokens) == 3:
        sub = tokens[1]
        try:
            slot = int(tokens[2])
        except ValueError:
            return f"CLEAR {sub}: bad slot number '{tokens[2]}'"
        if sub in ('COLOR', 'COLOUR'):
            if slot in color_pool.presets:
                del color_pool.presets[slot]
                save_show()
                return f"Color Preset {slot} cleared (show saved)"
            return f"Color Preset {slot} is already empty"
        if sub == 'DIM':
            if slot in dim_pool.presets:
                del dim_pool.presets[slot]
                save_show()
                return f"Dim Preset {slot} cleared (show saved)"
            return f"Dim Preset {slot} is already empty"
        if sub in ('GROUP', 'GRP'):
            if slot in group_pool.groups:
                del group_pool.groups[slot]
                save_show()
                return f"Group {slot} cleared (show saved)"
            return f"Group {slot} is already empty"
        if sub == 'FX':
            if slot in fx_pool.presets:
                del fx_pool.presets[slot]
                save_show()
                return f"FX Preset {slot} cleared (show saved)"
            return f"FX Preset {slot} is already empty"

    if t0 == 'CLEAR' and len(tokens) == 1:
        result = prog.do_clear()
        if result.startswith("Programmer cleared"):
            _prog_fx_stop()
        return result

    if t0 == 'UNDO':
        return prog.undo()

    # ── Default: programmer ───────────────────────────────────
    try:
        prog.execute(raw)
        return ""   # programmer already prints its own output
    except Exception as e:
        return f"Error: {e}"


# ── GUI ───────────────────────────────────────────────────
gui = GUIEngine(
    midi             = midi,
    fx_engine        = fx_engine,
    fade_engine      = fade_engine,
    output_state     = output_state,
    patch            = patch,
    cuestacks        = {cs.stack_id: cs for cs in cuestack_pool.stacks.values()},
    prog             = prog,
    go_fn            = cue_go,
    back_fn          = cue_back,
    goto_fn          = goto_cue,
    reload_fn        = cue_reload,
    ai               = ai,
    save_fn          = save_show,
    cmd_fn           = run_command,
    group_pool       = group_pool,
    color_pool       = color_pool,
    dim_pool         = dim_pool,
    cue_pool         = cue_pool,
    cuestack_pool    = cuestack_pool,
    active_executor  = active_executor,
    executor_pool    = executor_pool,
    fx_pool          = fx_pool,
    form_pool        = form_pool,
    rate_pool        = rate_pool,
    size_pool        = size_pool,
    spread_pool      = spread_pool,
    attr_pools       = _attr_pools,
    osc              = osc,
    library          = library,
    save_patch_fn    = lambda: ShowFile.save_patch(patch),
    fx_params        = _fx_params,
)
# Wire run_command and GUI log into AI engine (both defined after ai was created)
if getattr(ai, '_enabled', False):
    ai._cmd = run_command
    ai._log = gui._log

if STUDIO_HEADLESS:
    # Scripted smoke test — no GUI, no real hardware (paired with
    # STUDIO_DRY_RUN). Exercises the FX-as-programmer path this file's own
    # doc comments flagged as written-but-untested: FX -> RECORD CUE ->
    # GO -> verify FX actually fires. Exits with status 0/1 instead of
    # blocking on dpg.start_dearpygui().
    import sys as _sys

    print("\n*** STUDIO_HEADLESS smoke test ***")
    _results = []
    def _check(label, cond):
        _results.append((label, bool(cond)))
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}")

    try:
        r1 = run_command("FX SINE RED BLOCK 2 DIRECTION BOUNCE PIXEL")
        _check("FX command applied to programmer", "FX" in r1)

        r2 = run_command("RECORD CS 1 CUE 5")
        _check("cue recorded", "Recorded" in r2 or "Cue" in r2)

        run_command("GO CS 1 CUE 5")
        time.sleep(0.25)   # let FadeEngine/FXEngine tick at least once
        ex = executor_pool.get(1)
        _check("executor has active FX after GO", len(ex._fx_ids) > 0)

        dmx = output_state.get_dmx_for_universe(1)
        _check("DMX output computes without exception", len(dmx) == 512)

        # Pages + trigger modes
        run_command('PAGE 1 NAME "Test Page"')
        run_command("PAGE 1 ADD CS 1")
        r3 = run_command("PAGE LIST")
        _check("page created and cuestack added", "Test Page" in r3 and "[1]" in r3)

        run_command("EXEC 1 MODE FLASH")
        _check("trigger_mode set", executor_pool.get(1).trigger_mode == 'flash')

        run_command("EXEC 1 FLASH ON")
        time.sleep(0.05)
        _check("executor active after FLASH ON", executor_pool.get(1).is_active)

        run_command("EXEC 1 FLASH OFF")
        _check("executor inactive after FLASH OFF", not executor_pool.get(1).is_active)
    except Exception as e:
        _check(f"smoke test raised {type(e).__name__}: {e}", False)

    ok = all(passed for _, passed in _results)
    print(f"\n*** SMOKE TEST {'PASSED' if ok else 'FAILED'} "
          f"({sum(p for _, p in _results)}/{len(_results)}) ***\n")

    network.stop()
    midi.stop()
    osc.stop()
    fx_engine.stop()
    fade_engine.stop()
    _sys.exit(0 if ok else 1)
else:
    gui.build()   # build all widgets (main thread)
    gui.run()     # hand control to DearPyGui — blocks until window closed

midi.stop()
network.stop()
fade_engine.stop()
fx_engine.stop()


# =============================================================================
# SESSION HANDOFF NOTE  —  2026-06-25
# =============================================================================
#
# PROJECT: Studio Console
# FILE:    /Users/c/Documents/studio_project.py  (~6000 lines, single file)
# SHOW DATA: /Users/c/Documents/studio_data/  (per-category JSON files)
#
# ── WHAT THIS IS ──────────────────────────────────────────────────────────────
# Custom Python lighting console controlling 6 SGM LT-200 pixel tubes
# (54 RGB pixels each, 324 sub-fixtures total) via sACN multicast.
# GUI: DearPyGui retro console aesthetic.
# Command line: MA3-style text syntax (see run_command()).
#
# ── HARDWARE / NETWORK ────────────────────────────────────────────────────────
# sACN multicast on 192.168.1.161, universes 1 & 2, 44 Hz output loop.
# MIDI: Axiom 25 on port 1 (fader control).
# OSC: Studio Console on port 8001, grandMA3 on 8000.
#
# ── THREE-LAYER OUTPUT MERGE ──────────────────────────────────────────────────
# programmer  >  executor layers (LTP)  >  FX (additive)
#
# OutputState._merged_cue_layer()  — LTP merge of all active executor layers
#   in fire-order (last GO wins). Each Executor owns its own `layer` dict.
#   FadeEngine.Fade.tick() writes directly into executor.layer, not a shared dict.
#
# FXEngine runs additively on top of the merged cue layer.
# FX layers are split into two namespaces:
#   - Programmer preview:  IDs 9000+   tracked in _prog_fx_ids  (module-level list)
#   - Per-executor cue FX: IDs exec_id*10000+n  owned by Executor._fx_ids
#
# ── FX ARCHITECTURE (just redesigned this session) ────────────────────────────
# FX is now PROGRAMMER-NATIVE, not a standalone global thing.
#
# HOW IT WORKS:
#   1. `FX SINE RED`  writes  {'waveform':'sine','channel':'red','bpm':60,...}
#      into prog.data[fid_str]['fx'] for each selected master fixture.
#      Also starts a live-preview FXLayer (ID 9000+) so you see output immediately.
#
#   2. `RECORD CUE <n>` — Cue.record() does dict(vals) on programmer data,
#      which captures the 'fx' list automatically. No special handling needed.
#
#   3. `GO` on a cue calls executor._start_cue_fx(cue, patch):
#      - reads cue.data[master_fid]['fx'] lists
#      - starts FXLayer objects in the executor's own ID namespace
#      - clears previous executor FX first (_clear_fx)
#
#   4. `CLEAR` (stage 2 — programmer clear):
#      - also stops _prog_fx_ids preview layers  (_prog_fx_stop())
#
#   5. `Executor.stop()` calls _clear_fx() before clearing its layer.
#
#   6. `RECORD FX <n>` — snapshots unique FX defs from programmer into fx_pool.
#      (Reads from prog.data, NOT from active_fx list anymore.)
#
#   7. `FIRE FX <n>` — writes pool preset layers into programmer data + preview.
#      Does NOT fire directly to an executor — goes via programmer → RECORD CUE → GO.
#
#   8. `FX ADD ...` — appends additional FX layers to existing programmer FX.
#
#   9. `FX CLEAR` — removes 'fx' keys from programmer entries + stops preview.
#
# KEY OBJECTS:
#   _prog_fx_ids   — module-level list of active programmer-preview FX IDs
#   active_fx      — module-level list of active FXLayer objects (preview)
#   Executor._fx_ids   — list of FX IDs owned by that executor slot
#   Executor.fx_engine / Executor.form_pool — injected from ExecutorPool defaults
#   ExecutorPool.default_fx_engine / .default_form_pool / .default_color_pool / .default_dim_pool — set at startup
#
# ── SHOW FILE SPLIT ───────────────────────────────────────────────────────────
# ShowFile class (static methods only) — each category saves/loads independently.
# Files: studio_data/cuestacks.json, groups.json, colors.json, dims.json,
#        midi.json, fx.json, fx_pool.json, forms.json
# Legacy migration: if studio_show.json exists, it's read and split on first run,
#   then renamed to studio_show.json.migrated.
#
# ── PLAYBACK LAYER ────────────────────────────────────────────────────────────
# ExecutorPool holds numbered Executor slots.
# Each Executor: one CueStack, its own layer dict, its own FX IDs, level fader.
# LTP priority: _fire_order list — last GO = highest priority.
# FadeEngine fires Fade objects that tick() directly into executor.layer.
#
# COMMANDS:
#   ASSIGN CS <n> TO EXEC <n>    — wire cuestack to executor slot
#   EXEC <n> GO/BACK/STOP/GOTO   — control specific executor
#   EXECUTOR <n>                 — set active executor for bare GO/BACK
#
# ── KEY COMMANDS ──────────────────────────────────────────────────────────────
#   FX SINE RED [BPM n] [SIZE n] [SPREAD n]
#   FX ADD SINE BLUE [...]
#   FX FORM <n> RED [...]          — use FormPool waveform shape
#   FX CLEAR                       — clear all FX from programmer
#   FX CLEAR DIM                   — clear only dim channel FX (leaves RGB FX)
#   FX CLEAR RED / GREEN / BLUE    — clear only that colour channel FX
#   FX LIST
#   RECORD FX <n> [name]           — snapshot programmer FX → pool
#   FIRE FX <n>                    — add preset to programmer (channel-additive; same-channel layers replaced)
#   FORM LIST
#   RECORD FORM <n> [name] 0.0,0.0 0.5,1.0 1.0,0.0   — custom breakpoint curve
#   RECORD CS [n] CUE <m> [preset-tokens]
#   GO CS [n] CUE <m>
#
# ── POOLS ──────────────────────────────────────────────────────────────────────
#   color_pool    — ColorPreset  (numbered, saved to colors.json)
#   dim_pool      — DimPreset    (numbered, saved to dims.json)
#   group_pool    — Group        (numbered, saved to groups.json)
#   cuestack_pool — CueStack     (numbered, saved to cuestacks.json)
#   fx_pool       — FXPreset     (numbered, 1-12 visible in GUI, saved to fx_pool.json)
#   form_pool     — FormPreset   (1-4 built-in builtins: sine/ramp/pulse/square;
#                                 5+ custom breakpoint curves; saved to forms.json)
#   executor_pool — Executor     (cuestack/level/priority/mode saved to executors.json)
#
# ── WHAT WORKS ────────────────────────────────────────────────────────────────
# - Full output pipeline (sACN, FX additive, programmer+cue merge)
# - CueStack playback with fades, executor isolation, LTP priority
# - FX as programmer-native (redesigned this session — just landed)
# - CLEAR 3-tap protocol: selection → programmer → full output
# - FX pool record/fire, Forms pool with custom breakpoints
# - Show file per-category save/load with .bak auto-backup
# - GUI panels: cuestacks, groups, colors, dims, FX pool, forms pool
# - MIDI fader control, OSC bridge, AI command layer (ANTHROPIC_API_KEY gated)
#
# ── KNOWN ISSUES / TODO ───────────────────────────────────────────────────────
# - executor_pool now persists cuestack assignments to executors.json; loaded
#   at startup so GO works immediately after restart without re-assigning.
#
# =============================================================================
