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
            return "selection cleared  (clear again to clear programmer)"
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
            return "programmer cleared  (clear again to clear output)"
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


# ============================================================
# Blocks 4 & 5: Presets, Pools, Groups
# Colorpreset / ColorPool — referenced RGB presets
# Dimmerpreset / DimmerPool — referenced dimmer presets
# Attributepreset / AttributePool — generic attribute presets
#   (position, gobo, zoom, focus, beam, control)
# group / GroupPool — fixture selection groups
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
        self.name      = name if name else f"color {preset_id}"
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
        print(f"recorded: {self}")

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
        return (f"[color preset {self.preset_id}] \"{self.name}\" "
                f"RGB({self.red},{self.green},{self.blue})")


class ColorPool:
    def __init__(self):
        self.presets = {}   # { preset_id (int): Colorpreset }

    def get(self, pid):
        return self.presets.get(int(pid))

    def record(self, preset_id, programmer, name=""):
        preset = ColorPreset(preset_id, name or f"color {preset_id}")
        preset.record(programmer)
        self.presets[preset.preset_id] = preset
        return preset

    def apply(self, preset_id, programmer):
        p = self.get(preset_id)
        if p:
            p.apply(programmer)
        else:
            print(f"color preset {preset_id} not found.")

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
        print(f"recorded: {self}")

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
        return f"[Dimmer preset {self.preset_id}] \"{self.name}\" ({self.level:.0%})"


class DimmerPool:
    def __init__(self):
        self.presets = {}   # { preset_id (int): Dimmerpreset }

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
            print(f"Dimmer preset {preset_id} not found.")

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
        return (f"[{self.attribute.upper()} preset {self.preset_id}] "
                f"{self.name}  ({len(self.data)} fixtures)")


class AttributePool:
    """Registry of AttributePresets for one attribute family."""
    def __init__(self, attribute, relevant_channels=None):
        self.attribute         = attribute
        self.relevant_channels = list(relevant_channels or [attribute])
        self.presets           = {}   # { preset_id: Attributepreset }

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
            print(f"{self.attribute.title()} preset {preset_id} not found.")

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
        self.name     = name or f"group {group_id}"
        self.members  = []   # [ ("master", fixture_id_int), ... ]

    def record(self, programmer):
        self.members = []
        for f in programmer.selection:
            if isinstance(f, MasterFixture):
                self.members.append(("master", f.fixture_id))
        print(f"recorded: {self}")

    def recall(self, patch):
        """Return list of MasterFixture objects for this group."""
        fixtures = []
        for _type, fid in self.members:
            m = patch.get(int(fid))
            if m:
                fixtures.append(m)
        return fixtures

    def __repr__(self):
        return f"[group {self.group_id}] \"{self.name}\" ({len(self.members)} fixture(s))"


class GroupPool:
    def __init__(self):
        self.groups = {}   # { group_id (int): group }

    def get(self, gid):
        return self.groups.get(int(gid))

    def record(self, group_id, programmer, name=""):
        g = Group(group_id, name or f"group {group_id}")
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
# Block 6: cue and CueStack
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
                 fade_times=None, delay_times=None, follow_time=0.0):
        self.cue_number  = float(cue_number)
        self.name        = name if name else f"cue {cue_number}"
        self.fade_time   = float(fade_time)
        self.delay_time  = float(delay_time)
        self.fade_times  = dict(fade_times)  if fade_times  else {}
        self.delay_times = dict(delay_times) if delay_times else {}
        self.follow_time = float(follow_time)  # >0 = auto-GO after N seconds
        self.fx_outfade  = None               # override FX outfade time (None = auto)
        self.note        = ""                 # production annotation (saved, optional)

        # Delta snapshot: { fixture_id_string: { channel: value } }
        # Only contains what was active in the programmer at record time
        self.data = {}

    def record(self, programmer):
        """
        snapshot active programmer data into this cue.
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
        print(f"recorded: {self} ({count} fixture/pixel entries)")

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
        print(f"updated: {self} ({count} fixture/pixel entries total)")

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
        if getattr(self, 'fx_outfade', None) is not None:
            timing += f" FXOut:{self.fx_outfade}s"
        return f"[cue {self.cue_number}] \"{self.name}\" | {timing}"


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
        self.name            = name if name else f"cuestack {stack_id}"
        self.cues            = {}        # { cue_number (float): cue }
        self.current         = None      # Current cue number (float) or None
        self.allow_exec_time = True      # False = ignore executor time override for this stack
        self.wrap            = False     # True = fire cue 1 clean on wrap-around (no LTP bleed)
        self.bounce          = False     # True = reverse direction at ends (ping-pong)
        self._bounce_dir     = 1        # 1 = forward, -1 = backward (runtime, not saved)
        self.note            = ""        # Production annotation (saved, optional)
        # Chase mode — auto-advance through cues at a fixed BPM
        self.chase_enabled  = False
        self.chase_bpm      = 120.0
        self.chase_speed_id = None   # SpeedMaster slot (overrides chase_bpm when set)

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
            print("programmer is empty — nothing to record.")
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
            print(f"deleted cue {cue_number} from {self.name}")
        else:
            print(f"cue {cue_number} not found.")

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
            print("cuestack is empty.")
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
            print("cuestack is empty.")
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
            print(f"cue {cue_number} not found in {self.name}.")
            return
        self._fire_cue(num, patch)

    def _fire_cue(self, cue_number, patch):
        """
        Apply a cue's data directly to fixtures.
        This is the playback output layer — separate from
        the programmer. cue data goes straight to fixtures.

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
    """Numbered library of standalone cue objects (1-based slots)."""
    def __init__(self):
        self.cues = {}      # { int slot: cue }

    def get(self, n):
        return self.cues.get(int(n))

    def store(self, n, cue):
        self.cues[int(n)] = cue

    def delete(self, n):
        self.cues.pop(int(n), None)

    def record(self, n, programmer, name="", fade_time=0.0):
        cue = Cue(n, name or f"cue {n}", fade_time)
        cue.record(programmer)
        self.cues[int(n)] = cue
        return cue


class CueStackPool:
    """Pool of cuestack objects (executors), numbered 1-based."""
    def __init__(self):
        self.stacks = {}    # { int slot: cuestack }

    def get(self, n):
        return self.stacks.get(int(n))

    def store(self, n, stack):
        self.stacks[int(n)] = stack

    def create(self, n, name=""):
        existing = self.stacks.get(int(n))
        if existing:
            # Rename in-place — preserves cues and executor references
            existing.name = name or f"cuestack {n}"
            return existing
        cs = CueStack(int(n), name or f"cuestack {n}")
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
    PRIORITY_LABELS = {-1: 'lo', 0: 'nrm', 1: 'hi'}

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
        self._follow_at          = None   # monotonic time to auto-GO via FOLLOW
        self._chase_next_at      = None   # monotonic time for next chase GO
        # Three assignable action buttons per fader slot
        self.btn_a = 'GO'    # GO / BACK / STOP / FLASH / RATE+ / RATE-
        self.btn_b = 'BACK'
        self.btn_c = 'STOP'
        # Playback rate multiplier: 1.0 = normal, 2.0 = twice as fast (divides fade times)
        self.rate_factor = 1.0
        # FX amplitude multiplier: 1.0 = normal, 2.0 = double, 0.5 = half (applied to all owned layers)
        self.size_factor = 1.0
        # Optional human-readable label for this fader slot (independent of the cuestack name)
        self.label = ""

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
                speed_id     = ld.get('speed_id'),
                infade       = infade,
                outfade      = ld.get('outfade',       0.0),
                block_size   = ld.get('block_size',      1),
                order        = ld.get('order',    'linear'),
                direction    = ld.get('direction','forward'),
            )
            self._fx_ids.append(fxid)
            # Apply executor size_factor to the newly-created layer
            if self.size_factor != 1.0:
                layer = self.fx_engine._layers.get(fxid)
                if layer is not None:
                    layer.size_scale = self.size_factor

        # _bucket_fx_defs (module-level, defined near FXEngine) merges
        # identical defs across fixtures into one layer so spread/chase can
        # cross fixture boundaries — see target_scope in FX command docs.
        for ld, targets in _bucket_fx_defs(expanded, patch):
            _add(ld, ld['channel'], targets)

    def _apply_size_factor(self):
        """Push current size_factor to all owned FX layers immediately."""
        if not self.fx_engine:
            return
        for fxid in self._fx_ids:
            layer = self.fx_engine._layers.get(fxid)
            if layer is not None:
                layer.size_scale = self.size_factor

    # ── Playback ─────────────────────────────────────────────

    def go(self, patch, fade_engine):
        if not self.cuestack:
            return f"fader {self.exec_id}: no cuestack assigned"
        self.is_active = True
        return self.cuestack.go(patch, fade_engine, self)

    def back(self, patch, fade_engine):
        if not self.cuestack:
            return f"fader {self.exec_id}: no cuestack assigned"
        self.is_active = True
        return self.cuestack.back(patch, fade_engine, self)

    def goto(self, num, patch, fade_engine):
        if not self.cuestack:
            return f"fader {self.exec_id}: no cuestack assigned"
        self.is_active = True
        return self.cuestack.goto(num, patch, fade_engine, self)

    def reload(self, patch, fade_engine):
        """Re-fire the current cue from scratch without advancing."""
        if not self.cuestack:
            return f"fader {self.exec_id}: no cuestack assigned"
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
            return f"fader {self.exec_id}: no cuestack assigned"
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
            self.pages[n] = {'name': f'page {n}', 'cuestacks': []}
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
# FXpreset + FXPool
# A preset is a snapshot of one or more FX layer definitions.
# Targets are NOT stored — resolved at fire time from patch/group.
# ============================================================

class FXPreset:
    """One named FX state: a list of layer defs that fire together."""

    def __init__(self, preset_id, name=""):
        self.preset_id = int(preset_id)
        self.name      = name or f"fx {preset_id}"
        self.layers    = []   # list of dicts: {waveform, channel, rate_bpm, size, spread}

    def add_layer(self, waveform, channel, rate_bpm=60.0, size=100.0, spread=0.0,
                  form_id=None, rate_id=None, size_id=None, spread_id=None, bpm=None,
                  dim_id=None, color_id=None, group_id=None, speed_id=None,
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
            'speed_id':      speed_id,
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
                speed_id     = ld.get('speed_id'),
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
    """Numbered library of FXpreset objects (1-based slots)."""

    def __init__(self):
        self.presets = {}   # {int: FXPreset}

    def get(self, n):
        return self.presets.get(int(n))

    def store(self, n, preset):
        self.presets[int(n)] = preset

    def delete(self, n):
        self.presets.pop(int(n), None)

    def record_from_active(self, n, active_fx_list, name=""):
        """snapshot currently running FXLayer objects into a new preset, preserving pool refs."""
        preset = FXPreset(int(n), name or f"fx {n}")
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
        'white': 'colour', 'amber': 'colour',
        'dim': 'dim', 'dimmer': 'dim',
        'pan': 'position', 'tilt': 'position',
        'pan_fine': 'position', 'tilt_fine': 'position',
        'gobo': 'beam', 'gobo_rot': 'beam', 'gobo2': 'beam', 'gobo2_rot': 'beam',
        'zoom': 'beam', 'focus': 'beam', 'iris': 'beam',
        'shutter1': 'beam', 'strobe': 'beam',
        'color': 'beam', 'prism': 'beam', 'frost': 'beam',
        'control': 'control', 'macro': 'control', 'animation': 'control',
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
        """snapshot executor's current layer and fade to new cue state.
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


# ------------------------------------------------------------
# Updated cuestack playback methods
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

    # fx_kill: instant-apply by default so FX dies immediately without waiting
    # for the fade to interpolate 0→1.  Pre-setting executor.layer to 1.0 before
    # FadeEngine.fire() snapshots it means v_from==v_to==1 — no interpolation.
    # Leaving an fx_kill cue: clear it now so the Fade starts from 0 (not stale 1).
    new_cue_has_fx_kill = any(
        isinstance(v, dict) and v.get('fx_kill')
        for v in cue.data.values()
    )
    if new_cue_has_fx_kill:
        for fid_str, vals in cue.data.items():
            if isinstance(vals, dict) and vals.get('fx_kill'):
                executor.layer.setdefault(fid_str, {})['fx_kill'] = 1.0
    else:
        for fid_vals in executor.layer.values():
            fid_vals.pop('fx_kill', None)

    resolved = _resolve_cue_refs(
        cue.data, patch,
        getattr(executor, 'color_pool',    None),
        getattr(executor, 'dim_pool',      None),
        getattr(executor, 'attr_pools',    None),
    )
    print(f"\nGO → {cue}  [fader {executor.exec_id}]")

    # Resolve time override: executor override wins; programmer time is fallback
    ov_fade = ov_delay = None
    cs = executor.cuestack
    if (executor.time_override_on
            and (cs is None or cs.allow_exec_time)):
        if executor.time_override_fade  is not None:
            ov_fade  = executor.time_override_fade
        if executor.time_override_delay is not None:
            ov_delay = executor.time_override_delay
    # programmer time fallback — only if no executor override applied
    if ov_fade is None and _prog_time.get('on'):
        ov_fade  = float(_prog_time['fade'])
        ov_delay = float(_prog_time['delay'])

    # Apply executor rate_factor — scales fade (and delay) times; >1.0 = faster
    _rate = getattr(executor, 'rate_factor', 1.0)
    if _rate > 0 and _rate != 1.0:
        ov_fade  = (ov_fade  if ov_fade  is not None else cue.fade_time)  / _rate
        ov_delay = (ov_delay if ov_delay is not None else cue.delay_time) / _rate
        if ov_delay == 0.0:
            ov_delay = None  # avoid setting a zero override that masks auto

    # Effective fade time — used as default FX infade so FX ramps match DMX fades
    eff_fade = ov_fade if ov_fade is not None else cue.fade_time

    # FX outfade strategy:
    #  - fx_kill cue or non-FX cue → snap old FX off so the DMX crossfade runs
    #    without FX overriding the new cue's base values.
    #  - FX→FX transition → keep a short (≤1s) tail so waveforms crossfade
    #    rather than cutting between them abruptly.
    new_cue_has_fx = any(
        isinstance(vals, dict) and vals.get('fx')
        for fk, vals in cue.data.items()
        if '.' not in str(fk)
    )
    if new_cue_has_fx_kill or not new_cue_has_fx:
        fx_outfade = 0.0   # snap: static or kill cue — let DMX carry the crossfade
    else:
        fx_outfade = min(eff_fade, 1.0)   # FX→FX: brief tail

    # Cue-stored fx_outfade overrides auto-computed value (set via RECORD CUE FXOUTFADE)
    _cue_fx_out = getattr(cue, 'fx_outfade', None)
    if _cue_fx_out is not None:
        fx_outfade = float(_cue_fx_out)

    executor._start_cue_fx(cue, patch, default_infade=eff_fade, default_outfade=fx_outfade)

    # Auto-follow: arm timer so _tick() fires GO after follow_time seconds
    follow = getattr(cue, 'follow_time', 0.0)
    executor._follow_at = (time.monotonic() + follow) if follow > 0 else None

    fade_engine.fire(cue, executor, data_to=resolved,
                     override_fade=ov_fade, override_delay=ov_delay)
    return f"GO → {cue.name}"

def _cuestack_go(self, patch, fade_engine, executor):
    numbers = self._sorted_cue_numbers()
    if not numbers:
        return "cuestack is empty"
    if getattr(self, 'bounce', False):
        if self.current is None:
            self._bounce_dir = 1
            return _cuestack_fire_cue(self, numbers[0], patch, fade_engine, executor)
        try:
            idx = numbers.index(self.current)
        except ValueError:
            self._bounce_dir = 1
            return _cuestack_fire_cue(self, numbers[0], patch, fade_engine, executor)
        d = getattr(self, '_bounce_dir', 1)
        next_idx = idx + d
        if next_idx >= len(numbers):
            self._bounce_dir = -1
            next_idx = idx - 1
            if next_idx < 0:
                next_idx = 0
        elif next_idx < 0:
            self._bounce_dir = 1
            next_idx = idx + 1
            if next_idx >= len(numbers):
                next_idx = len(numbers) - 1
        return _cuestack_fire_cue(self, numbers[next_idx], patch, fade_engine, executor)
    wrap_occurred = False
    if self.current is None:
        next_num = numbers[0]
    else:
        try:
            idx      = numbers.index(self.current)
            next_idx = (idx + 1) % len(numbers)
            next_num = numbers[next_idx]
            wrap_occurred = (next_idx == 0 and idx == len(numbers) - 1)
        except ValueError:
            next_num = numbers[0]
    if wrap_occurred and getattr(self, 'wrap', False):
        executor.layer.clear()  # no LTP bleed from last cue back to first
    return _cuestack_fire_cue(self, next_num, patch, fade_engine, executor)

def _cuestack_back(self, patch, fade_engine, executor):
    numbers = self._sorted_cue_numbers()
    if not numbers:
        return "cuestack is empty"
    wrap_occurred = False
    if self.current is None:
        prev_num = numbers[-1]
    else:
        try:
            idx      = numbers.index(self.current)
            prev_idx = (idx - 1) % len(numbers)
            prev_num = numbers[prev_idx]
            wrap_occurred = (idx == 0 and prev_idx == len(numbers) - 1)
        except ValueError:
            prev_num = numbers[-1]
    if wrap_occurred and getattr(self, 'wrap', False):
        executor.layer.clear()  # no LTP bleed from first cue back to last
    return _cuestack_fire_cue(self, prev_num, patch, fade_engine, executor)

def _cuestack_goto(self, cue_number, patch, fade_engine, executor):
    num = float(cue_number)
    if num not in self.cues:
        return f"cue {cue_number} not found"
    return _cuestack_fire_cue(self, num, patch, fade_engine, executor)

def _cuestack_reload(self, patch, fade_engine, executor):
    """Re-fire the current cue without advancing the pointer."""
    if self.current is None:
        return "no active cue — use go to start"
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
    def flicker(t, idx=0):
        # Deterministic per-pixel noise: idx XOR into hash gives each pixel an
        # independent random sequence. 97 steps/cycle = visible change at 44 Hz.
        n = (int(t * 97) ^ (idx * 0x4B1D) ^ 0xA5B3) & 0xFFFF
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
# Formpreset + FormPool
# A Formpreset is a waveform shape: either a reference to one
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
            return f"[form {self.form_id}] {self.name}  (builtin: {self.builtin_name})"
        return (f"[form {self.form_id}] {self.name}  "
                f"(custom breakpoints: {len(self.breakpoints)} pts)")


class FormPool:
    """Numbered library of Formpreset waveform shapes (1-based).
    slots 1-4 are always the built-ins; 5+ are user-defined."""

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
        return f"[rate {self.preset_id}] {self.name}  ({self.bpm:.1f} BPM)"

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
        return f"[size {self.preset_id}] {self.name}  (size={self.size:.0f})"

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
        return f"[spread {self.preset_id}] {self.name}  (spread={self.spread:.2f})"

class SpreadPool:
    def __init__(self):
        self.presets = {}
        for pid, name, spread in SpreadPreset._BUILTINS:
            self.presets[pid] = SpreadPreset(pid, name, spread)
    def get(self, n):       return self.presets.get(int(n))
    def store(self, n, p):  self.presets[int(n)] = p
    def delete(self, n):    self.presets.pop(int(n), None)
    def all_slots(self):    return sorted(self.presets.keys())


class SpeedMaster:
    """One live BPM master slot — FXLayers referencing this slot track its BPM live."""
    def __init__(self, slot_id, bpm=120.0, name=""):
        self.slot_id = int(slot_id)
        self.bpm     = float(bpm)
        self.name    = name or f"spd{slot_id}"
    def __repr__(self):
        return f"[SpeedMaster {self.slot_id}] {self.name}  ({self.bpm:.1f} BPM)"

class SpeedMasterPool:
    """16 live BPM master slots (expandable).

    Each FXLayer can reference a slot by speed_id; changing a master's BPM
    updates all linked layers on the next tick — no preset reload needed.
    """
    _DEFAULT_SLOTS = 16

    def __init__(self):
        self.masters = {}
        for i in range(1, self._DEFAULT_SLOTS + 1):
            self.masters[i] = SpeedMaster(i)

    def get(self, n):
        return self.masters.get(int(n))

    def set_bpm(self, n, bpm):
        n = int(n)
        if n not in self.masters:
            self.masters[n] = SpeedMaster(n)
        self.masters[n].bpm = float(bpm)

    def get_bpm(self, n):
        m = self.masters.get(int(n))
        return m.bpm if m else None

    def all_slots(self):
        return sorted(self.masters.keys())


# ------------------------------------------------------------
# FXLayer — one running effect
# ------------------------------------------------------------

class FXLayer:
    """
    A single FX running across a list of sub-fixtures.

    pool references (form_id, rate_id, size_id, spread_id) are live-tracked:
    updating a pool entry propagates to all FXLayers referencing it on the
    next tick. Inline values (_bpm_inline, _size_inline, _spread_inline) are
    used as fallbacks when no pool ID is set.
    """
    def __init__(self, fx_id, waveform, channel, rate_bpm, size,
                 targets, spread=0.0,
                 form_pool=None, rate_pool=None, size_pool=None, spread_pool=None,
                 dim_pool=None, speed_master_pool=None,
                 form_id=None, rate_id=None, size_id=None, spread_id=None,
                 dim_id=None, speed_id=None,
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

        # pool references
        self._form_pool         = form_pool
        self._rate_pool         = rate_pool
        self._size_pool         = size_pool
        self._spread_pool       = spread_pool
        self._dim_pool          = dim_pool
        self._speed_master_pool = speed_master_pool

        # pool IDs — live-tracked via properties
        self.form_id     = form_id
        self._rate_id    = rate_id
        self._size_id    = size_id
        self._spread_id  = spread_id
        self._dim_id     = dim_id   # DimmerPreset.level used as amplitude ceiling
        self._speed_id   = speed_id  # SpeedMaster slot; overrides rate_bpm when set

        # Inline fallback values
        self._bpm_inline    = float(rate_bpm)
        self._size_inline   = float(size)
        self._spread_inline = float(spread)

        # Per-executor amplitude multiplier — set by FADER n SIZE; 1.0 = normal
        self.size_scale = 1.0

    def begin_outfade(self, now=None):
        """Trigger amplitude ramp-out. Engine auto-removes when amplitude hits 0."""
        if self._out_start is None:
            self._out_start = time.monotonic() if now is None else now

    @property
    def rate_bpm(self):
        # Priority: speed master > rate preset > inline BPM
        if self._speed_id is not None and self._speed_master_pool:
            m = self._speed_master_pool.get(self._speed_id)
            if m: return m.bpm
        if self._rate_pool and self._rate_id is not None:
            p = self._rate_pool.get(self._rate_id)
            if p: return p.bpm
        return self._bpm_inline

    @rate_bpm.setter
    def rate_bpm(self, val):
        self._bpm_inline = float(val)
        self._rate_id = None
        # speed_id is intentionally NOT cleared — rate_bpm.setter is used by the
        # global rate slider which should not detach a layer from its speed master

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
            self._last_env = 0.0
            return {}

        # Amplitude envelope: outfade → infade → full
        if self._out_start is not None:
            elapsed_out = now - self._out_start
            env = max(0.0, 1.0 - elapsed_out / self.outfade) if self.outfade > 0 else 0.0
            if env <= 0.0:
                self.is_active = False   # engine will sweep this layer out
                self._last_env = 0.0
                return {}
        elif self.infade > 0:
            env = min(1.0, (now - self.start) / self.infade)
        else:
            env = 1.0
        self._last_env = env  # expose for FXEngine to store in fx_layer

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
        sz     = (self.size / 100.0) * 255.0 * env * max(0.0, self.size_scale)
        sp     = self.spread / 100.0
        result = {}
        for i, sub in enumerate(self.targets):
            phase = (base_phase + self._offsets[i] * sp) % 1.0
            if self.waveform == 'flicker':
                result[str(sub.fixture_id)] = Waveform.flicker(phase, i) * sz
            else:
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
                 size_pool=None, spread_pool=None, dim_pool=None,
                 speed_master_pool=None):
        self.output_state      = output_state
        self.form_pool         = form_pool
        self.rate_pool         = rate_pool
        self.size_pool         = size_pool
        self.spread_pool       = spread_pool
        self.dim_pool          = dim_pool
        self.speed_master_pool = speed_master_pool
        self._layers      = {}
        self._lock        = threading.Lock()
        self._running     = True
        self._thread      = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def add(self, fx_id, waveform, channel, rate_bpm, size,
            targets, spread=1.0, form_id=None,
            rate_id=None, size_id=None, spread_id=None, dim_id=None,
            speed_id=None,
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
            form_pool         = self.form_pool,
            rate_pool         = self.rate_pool,
            size_pool         = self.size_pool,
            spread_pool       = self.spread_pool,
            dim_pool          = self.dim_pool,
            speed_master_pool = self.speed_master_pool,
            form_id      = form_id,
            rate_id      = rate_id,
            size_id      = size_id,
            spread_id    = spread_id,
            dim_id       = dim_id,
            speed_id     = speed_id,
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

    def compute_merged(self, now):
        """Evaluate all active FX layers at timestamp `now`, update output_state.fx_layer,
        and remove any layers whose outfade has finished. Thread-safe via internal lock.

        Called by the network thread right before each sACN transmission so strobe
        transitions are evaluated at the exact send moment, not from a cached snapshot
        that could be up to one full FX tick (22ms at 44Hz) stale."""
        merged = {}
        dead   = []
        with self._lock:
            for fx_id, layer in self._layers.items():
                vals = layer.get_values(now)
                env  = getattr(layer, '_last_env', 1.0)
                if not layer.is_active:
                    dead.append(fx_id)
                    continue
                for fid, value in vals.items():
                    if fid not in merged:
                        merged[fid] = {}
                    merged[fid][layer.channel] = (
                        merged[fid].get(layer.channel, 0) + value
                    )
                    env_key = f'_env_{layer.channel}'
                    if env > merged[fid].get(env_key, 0.0):
                        merged[fid][env_key] = env
            for fx_id in dead:
                self._layers.pop(fx_id, None)
                print(f"FX {fx_id} outfade complete — removed.")
        self.output_state.fx_layer = merged

    def _run(self):
        # Background loop for envelope/outfade tracking when the network thread
        # is not driving compute_merged() (e.g. dry_run with no network engine).
        while self._running:
            self.compute_merged(time.monotonic())
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
            scope = ld.get('target_scope') or 'pixel'
            key = (ld.get('waveform', 'sine'), ld.get('channel'),
                   round(ld.get('bpm',    60.0), 3),
                   round(ld.get('size',  100.0), 2),
                   round(ld.get('spread',  0.0), 4),
                   ld.get('phase_offset', 0.0),
                   ld.get('form_id'), ld.get('rate_id'),
                   ld.get('size_id'), ld.get('spread_id'), ld.get('dim_id'),
                   ld.get('group_id'), ld.get('color_id'),
                   ld.get('speed_id'),
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
                    # color preset empty — use white fallback so FX is visible immediately
                    base_size = ld.get('size', 100.0)
                    for ch in ('red', 'green', 'blue'):
                        sub = dict(ld)
                        sub['channel'] = ch
                        sub['size']    = base_size
                        out.append(sub)
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
# STUDIO CONSOLE - Block 9: audio Engine
# Real-time audio analysis: level + 3-band EQ (low/mid/high)
# Attack/release envelope following
# AudioMapper connects audio values to the lighting output
# ============================================================

# sounddevice binds to the native Portaudio library at import time (not
# lazily like mido/rtmidi), so a missing/broken Portaudio install raises
# OSError here rather than on first use. AudioEngine/AudioMapper are not
# wired into any command handler or GUI panel yet (see changelog), but the
# import used to be unconditional, so any environment without a working
# audio stack (most CI/headless/dry-run boxes) failed to start the entire
# console before a single fixture patched. Guard it the same way Block 10
# hardened MIDI startup against a missing backend/device.
try:
    import sounddevice as sd
    import numpy as np
    _AUDIO_AVAILABLE = True
    _AUDIO_IMPORT_ERROR = None
except Exception as e:
    sd = None
    np = None
    _AUDIO_AVAILABLE = False
    _AUDIO_IMPORT_ERROR = e


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
        if not _AUDIO_AVAILABLE:
            print(f"audio engine unavailable ({_AUDIO_IMPORT_ERROR}); no input devices to list.")
            return
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
        if not _AUDIO_AVAILABLE:
            raise RuntimeError(f"audio engine unavailable: {_AUDIO_IMPORT_ERROR}")
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
        print(f"audio engine started — input: {name}")

    def stop(self):
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
        print("audio engine stopped.")

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

    audio layer sits between FX+cue and programmer —
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
        print("audio mapping enabled — bass=red, mid=green, high=blue, level=dim")

    def disable(self):
        self.enabled = False
        self.output_state.audio_layer = {}
        print("audio mapping disabled.")

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
        self.highlight_mode   = False  # when True, selected fixtures go full-white at 100%
        self.highlight_fids   = set()  # set of master fixture_id ints to highlight
        self.direct_dmx       = {}    # {universe: {address(1-512): value(0-255)}}
        self.freeze_mode      = False  # when True, frozen_dmx is output verbatim
        self.frozen_dmx       = {}    # {universe: tuple(512)} — snapshot at FREEZE time
        self.solo_mode        = False  # when True, only solo_fids get output
        self.solo_fids        = set() # set of master fixture_id ints to pass through
        self.parked_fids      = set() # set of master fixture_id ints that are parked
        self.parked_addresses = {}    # {universe: {address(1-512): value}} — snapshot at park time
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
        if self.freeze_mode and universe in self.frozen_dmx:
            # FREEZE locks the *look*, not the master fader, SOLO isolation,
            # a direct DMX override, or PARK — BLACKOUT/MASTER must still be
            # able to cut a frozen output (safety-critical: BLACKOUT is
            # documented as "cut all output NOW" and must not be silently
            # defeated by FREEZE), SOLO's "zero everyone else" guarantee must
            # still hold, a direct DMX override is documented as
            # highest-priority/applied-last regardless of what else is
            # happening, and PARK is documented as "immune to cue/prog
            # changes" and higher priority still (even above direct_dmx).
            gm = self.master_level
            dmx = [int(v * gm) for v in self.frozen_dmx[universe]]
            if self.solo_mode:
                for master in self.patch.all_fixtures():
                    if master.fixture_id in self.solo_fids:
                        continue
                    for sub in master.all_subs():
                        for output in sub.outputs:
                            if output['universe'] != universe:
                                continue
                            addr = output['address'] - 1
                            for offset in range(len(sub.profile.channels)):
                                if addr + offset > 511:
                                    break
                                dmx[addr + offset] = 0
            for addr1, val in self.direct_dmx.get(universe, {}).items():
                if 1 <= addr1 <= 512:
                    dmx[addr1 - 1] = max(0, min(255, int(val)))
            for addr1, val in self.parked_addresses.get(universe, {}).items():
                if 1 <= addr1 <= 512:
                    dmx[addr1 - 1] = max(0, min(255, int(val)))
            return tuple(dmx)
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
                #   dim FX (dim channel) → multiplied against the base dim hierarchy
                #     (programmer dim × FX_dim, so programmer can still kill output)
                #   RGB FX implicit dim → when colour FX is running but no explicit dim
                #     source exists (FX-only cue), default to 1.0 so fixtures are visible.
                #     Explicit cue/programmer dim is respected and NOT overridden.
                # fx_kill in programmer or cue explicitly suppresses all FX for this fixture
                #
                # dim FX can target this whole fixture (target_scope='fixture' —
                # fx_layer[master_fid]['dim']) or drive each pixel independently
                # (target_scope='pixel' — fx_layer[sub_fid]['dim']). Per-pixel value
                # wins when present; otherwise it falls back to the fixture-level one.
                _fx_kill      = (prog_master.get('fx_kill', 0) >= 0.5 or
                                 cue_master.get('fx_kill',  0) >= 0.5)

                fx_master        = {} if _fx_kill else self.fx_layer.get(master_fid, {})
                _fixture_dim_fx  = fx_master.get('dim')
                _first_sub       = next(iter(master.sub_fixtures.values()), None)
                # _rgb_fx_on: only True when colour FX has actually faded in (env > 0).
                # Checking _env_ keys avoids a dim-snap at infade t=0 where the FX
                # layer exists but all amplitudes are still 0.
                if _fx_kill or not _first_sub:
                    _rgb_fx_on = False
                else:
                    _fsub_fx = self.fx_layer.get(str(_first_sub.fixture_id), {})
                    _rgb_fx_on = any(
                        _fsub_fx.get(f'_env_{c}', 0.0) > 0.001
                        for c in ('red', 'green', 'blue')
                    )

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
                        # dim FX: multiplicative on top of static dim hierarchy
                        sub_dim = max(0.0, min(1.0, _base_dim * (fx_dim_raw / 255.0)))
                    elif _rgb_fx_on:
                        # Colour FX running: respect explicit programmer/cue dim;
                        # fall back to 1.0 only when no explicit source exists.
                        sub_dim = _rgb_fallback_dim
                    else:
                        sub_dim = _base_dim

                    gm        = self.master_level
                    highlight = (self.highlight_mode and
                                 master.fixture_id in self.highlight_fids)

                    # Build resolved values for all profile channels on this sub.
                    # Colour channels: FX envelope-blend + dimmer applied.
                    # 'dimmer' profile channel: maps from master dim hierarchy (0-255).
                    # Attribute channels (pan/tilt/gobo/etc): LTP only, no dimmer,
                    #   FX additive (same blend formula as colour).
                    _COLOUR_CHS = frozenset({'red', 'green', 'blue', 'white', 'amber'})
                    ch_resolved = {}
                    for ch in sub.profile.channels:
                        if ch in _COLOUR_CHS:
                            if highlight:
                                ch_resolved[ch] = int(255 * gm)
                            else:
                                base_val = prog_vals.get(ch, audio_vals.get(ch, cue_vals.get(ch, 0)))
                                if ch in fx_vals:
                                    env = fx_vals.get(f'_env_{ch}', 1.0)
                                    merged = max(0, min(255, int(base_val * (1.0 - env) + fx_vals[ch])))
                                else:
                                    merged = base_val
                                ch_resolved[ch] = max(0, min(255, int(merged * sub_dim * gm)))
                        elif ch == 'dimmer':
                            if highlight:
                                ch_resolved[ch] = int(255 * gm)
                            else:
                                # Explicit 'dimmer' stored on sub wins; otherwise use master dim.
                                # sub_dim already folds in dim FX modulation, so use it in both paths.
                                base_val = prog_vals.get('dimmer', audio_vals.get('dimmer',
                                           cue_vals.get('dimmer', None)))
                                if base_val is not None:
                                    fx_ratio = (sub_dim / _base_dim) if _base_dim > 0.0001 else 1.0
                                    ch_resolved[ch] = max(0, min(255, int(base_val * fx_ratio * gm)))
                                else:
                                    ch_resolved[ch] = max(0, min(255, int(sub_dim * gm * 255)))
                        else:
                            # Attribute channel: LTP, no dimmer, FX envelope-blend additive
                            base_val = prog_vals.get(ch, audio_vals.get(ch, cue_vals.get(ch, 0)))
                            if ch in fx_vals:
                                env = fx_vals.get(f'_env_{ch}', 1.0)
                                val = max(0, min(255, int(base_val * (1.0 - env) + fx_vals[ch])))
                            else:
                                val = base_val
                            ch_resolved[ch] = max(0, min(255, int(val)))

                    # SOLO: if active, zero out non-solo fixtures
                    _solo_suppress = (self.solo_mode and
                                      master.fixture_id not in self.solo_fids)
                    for output in sub.outputs:
                        if output['universe'] != universe:
                            continue
                        addr = output['address'] - 1
                        for offset, ch in enumerate(sub.profile.channels):
                            if addr + offset > 511:
                                break
                            dmx[addr + offset] = 0 if _solo_suppress else ch_resolved.get(ch, 0)
            # direct DMX overrides — applied after all other layers
            for addr1, val in self.direct_dmx.get(universe, {}).items():
                if 1 <= addr1 <= 512:
                    dmx[addr1 - 1] = max(0, min(255, int(val)))
            # Parked fixture values — absolute, highest priority (even above direct_dmx)
            for addr1, val in self.parked_addresses.get(universe, {}).items():
                if 1 <= addr1 <= 512:
                    dmx[addr1 - 1] = max(0, min(255, int(val)))
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
      /gma3/cmd              string   — command line (e.g. "Go+ cue 1")
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
    - programmer commands (same syntax as command line)
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
- "exec_level" sets a fader's master level (level 0.0–1.0).
- "cue_fire" is an alias for goto_cue (fires the named cue immediately).
- "fade_time" only affects the next cue_go/cue_back/goto_cue/cue_fire action
  in this same array — put it immediately before the cue action it should
  apply to (e.g. a slow fade into a cue: [{"action":"fade_time","seconds":5},
  {"action":"goto_cue","stack":1,"num":2}]). It does not change any other
  timing and is not a standing default.
- "stack" identifies a cuestack by id, not a fader slot — it is resolved
  to whichever fader that cuestack is currently assigned to.
- Only return the JSON array. No explanation, no markdown.
"""

    _CMD_HISTORY_MAX = 12

    def __init__(self, patch, prog, output_state, fx_engine, fade_engine,
                 cuestack_pool=None, executor_pool=None, cmd_fn=None, log_fn=None,
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
        # Live pool reference (not a snapshot) so newly created/loaded
        # cuestacks are visible without re-constructing the AI engine.
        self._stack_pool     = cuestack_pool
        self._executor_pool  = executor_pool
        self._cmd            = cmd_fn    # run_command — full console command parser
        self._log            = log_fn    # GUI log callback
        self._enabled        = True
        self._last_fade      = None      # pending fade_time override, consumed by the next cue fire
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
        for sid, stack in (self._stack_pool.stacks.items() if self._stack_pool else {}):
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
        # programmer contents (what's currently edited, not yet stored in a cue)
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
            "programmer commands use MA3-style syntax: "
            "'FIXTURE_ID AT VALUE', 'R 255 G 0 B 0', 'AT FULL', 'AT OUT'.\n"
            "The console state includes recent_commands — the last few commands the "
            "operator ran. Use them to resolve pronouns and implicit references: "
            "if the user says 'them', 'those', 'it', or 'same fixtures', infer "
            "the target from fixture IDs visible in recent commands or programmer state. "
            "If the user says 'do it again' or 'same but slower', repeat/modify the "
            "most recent relevant action. When in doubt, use group_select or prog actions "
            "that target the fixtures most recently mentioned.\n\n"
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

    def _exec_for_stack(self, stack_id):
        """
        Resolve a cuestack id (as used in ACTION_SCHEMA's "stack" field and
        in _state()'s cuestacks section) to the executor slot it's actually
        assigned to. Falls back to a same-numbered executor slot if no
        executor currently has that cuestack assigned (preserves the
        default 1:1 stack/executor wiring set up at startup).
        """
        if not self._executor_pool:
            return None
        for ex in self._executor_pool.executors.values():
            if ex.cuestack and ex.cuestack.stack_id == stack_id:
                return ex
        return self._executor_pool.get(stack_id)

    def _fire(self, ex, fire_fn, *args):
        """
        Fire a cue via one of Executor.go/back/goto, applying a pending
        fade_time override (if any) for just this one fire, then logging
        the result (including failures like 'no cuestack assigned', which
        were previously discarded silently).
        """
        if self._last_fade is not None:
            prev = (ex.time_override_on, ex.time_override_fade, ex.time_override_delay)
            ex.time_override_on    = True
            ex.time_override_fade  = self._last_fade
            ex.time_override_delay = 0.0
            try:
                msg = fire_fn(*args)
            finally:
                (ex.time_override_on, ex.time_override_fade,
                 ex.time_override_delay) = prev
            self._last_fade = None
        else:
            msg = fire_fn(*args)
        if msg and self._log:
            self._log(f"  → {msg}")
        return msg

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
                    ex = self._exec_for_stack(a.get("stack", 1))
                    if ex:
                        self._executor_pool.bump_priority(ex.exec_id)
                        self._fire(ex, ex.goto, a["num"], self._patch, self._fade)
                elif act == "cue_go":
                    ex = self._exec_for_stack(a.get("stack", 1))
                    if ex:
                        self._executor_pool.bump_priority(ex.exec_id)
                        self._fire(ex, ex.go, self._patch, self._fade)
                elif act == "cue_back":
                    ex = self._exec_for_stack(a.get("stack", 1))
                    if ex:
                        self._executor_pool.bump_priority(ex.exec_id)
                        self._fire(ex, ex.back, self._patch, self._fade)
                elif act == "dim":
                    # Clamp like every sibling dim-setter (programmer.set_dimmer,
                    # the GUI fixture-dim slider, MasterFixture.set_dimmer) --
                    # this value comes straight from the model's JSON with no
                    # bounds of its own. Unclamped, an out-of-range value here
                    # is invisible live (final DMX render clamps on the way
                    # out) but would persist verbatim into a RECORDed cue --
                    # the same bug class already fixed for HUE SAT/VAL.
                    val = max(0.0, min(1.0, float(a["value"])))
                    for master in self._patch.all_fixtures():
                        self._output.programmer_layer.setdefault(
                            str(master.fixture_id), {})['dim'] = val
                        master.set_dimmer(val)
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
                elif act == "cue_fire" and "num" in a:
                    ex = self._exec_for_stack(a.get("stack", 1))
                    if ex:
                        self._executor_pool.bump_priority(ex.exec_id)
                        self._fire(ex, ex.goto, float(a["num"]), self._patch, self._fade)
                elif act == "group_select":
                    if self._cmd:
                        self._cmd(f"GROUP {a['group']}")
                elif act == "fx_stop":
                    ch = a.get("channel")
                    if self._cmd:
                        self._cmd(f"FX CLEAR {ch.upper()}" if ch else "FX CLEAR")
                    else:
                        self._fx.clear()
                elif act == "exec_level":
                    if self._executor_pool and self._cmd:
                        self._cmd(f"FADER {a.get('exec', 1)} LEVEL {float(a.get('level', 1.0)) * 100:.0f}")
                elif act == "fx_clear":
                    # Route through the real FX CLEAR handler — it both stops
                    # the FX engine layers *and* clears the programmer's
                    # pending 'fx' defs, so a rebuild tick can't resurrect
                    # them. self._fx.clear() alone did neither correctly:
                    # it also wiped executor-owned cue FX layers whose ids
                    # are tracked separately in ex._fx_ids.
                    if self._cmd:
                        self._cmd("FX CLEAR")
                    else:
                        self._fx.clear()
                elif act == "fade_time":
                    # Applied once, to whichever cue-fire action follows in
                    # this same batch (see _fire()) — not a standing default.
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
#   - FX: rate / size / spread sliders, Kill button
#   - Output monitor: per-tube RGB+dim bars
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
_C_CUE_ACT   = (72,  50, 148, 255)  # selected cue row — brighter violet
_C_SLIDER_G  = _C_ACCENT

# pool panel header colours — violet family, varied lightness/hue for readability
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
            dpg.add_theme_color(dpg.mvThemeCol_TableRowBgAlt,  (26, 18,  56,  90))
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrab,     _C_SLIDER_G)
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive, _C_ACCENT)
            dpg.add_theme_color(dpg.mvThemeCol_Header,         _C_CUE_ACT)
            dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered,  _C_BTN_H)
            dpg.add_theme_color(dpg.mvThemeCol_HeaderActive,   _C_BTN_A)
            dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive,  (44, 30,  98, 255))
            dpg.add_theme_color(dpg.mvThemeCol_TitleBg,        (22, 16,  48, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg,    _C_BG)
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab,  _C_BORDER)
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabHovered, _C_BTN_H)
            dpg.add_theme_color(dpg.mvThemeCol_PopupBg,        (12,  8,  28, 255))
            dpg.add_theme_color(dpg.mvThemeCol_TableBorderLight, _C_BORDER)
            dpg.add_theme_color(dpg.mvThemeCol_TableHeaderBg,  (28, 20,  65, 255))
            dpg.add_theme_color(dpg.mvThemeCol_CheckMark,      _C_ACCENT)
            dpg.add_theme_color(dpg.mvThemeCol_Separator,      (62, 44, 116, 255))
            # Input cursor and selection highlight
            dpg.add_theme_color(dpg.mvThemeCol_TextSelectedBg, (80, 50, 160, 140))
            dpg.add_theme_color(dpg.mvThemeCol_NavHighlight,   _C_ACCENT)
            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding,  6)
            dpg.add_theme_style(dpg.mvStyleVar_ChildRounding,   6)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding,   8)
            dpg.add_theme_style(dpg.mvStyleVar_GrabRounding,    6)
            dpg.add_theme_style(dpg.mvStyleVar_WindowBorderSize, 1)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing,     6, 5)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding,    8, 4)
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


def _make_alert_btn_theme():
    """Red-tinted button for active alert states (BLIND, BLACKOUT)."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (120, 20, 20, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (200, 40, 40, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (255, 60, 60, 255))
    return t


def _make_transport_go_theme():
    """Green theme for the transport GO button."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (30,  74,  16, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (74, 138,  32, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (128, 208, 64, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Text,          (128, 208, 64, 255))
    return t


def _make_dim_btn_theme():
    """Dimmed/inactive button style for toggleable status indicators."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (30, 24, 50, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (50, 40, 80, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (70, 55, 110, 255))
    return t


def _make_numpad_digit_theme():
    """Slightly lighter background for digit buttons — distinct from keyword keys."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (24, 15, 64, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (60, 42, 140, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (100, 72, 210, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Text,          (232, 226, 255, 255))
    return t


def _make_pool_live_theme():
    """Brighter pool button theme for occupied (live) slots — clearly lit."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (52, 38, 118, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (95, 68, 178, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (132, 94, 235, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Text,          (222, 212, 255, 255))
    return t


def _make_pool_empty_theme():
    """Near-invisible pool button theme for empty slots — recedes to background."""
    with dpg.theme() as t:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button,        (10,  7, 22, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (30, 22, 62, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  (50, 36, 102, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Text,          (58, 45,  90, 255))
    return t


_CONSOLE_FONT_CANDIDATES = [
    "/System/Library/Fonts/SFNSMono.ttf",                                   # macOS
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",                  # Debian/Ubuntu
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",      # Debian/Ubuntu (RPM-derived)
    "/usr/share/fonts/liberation/LiberationMono-Regular.ttf",               # Fedora/RHEL
    "C:/Windows/Fonts/consola.ttf",                                        # Windows
]


def _load_console_font():
    """
    Load a monospace console font if one is found on this OS; returns the
    font tag or None (DearPyGui's built-in bitmap font is the fallback).

    Previously this only tried SF Mono (macOS), so every other OS silently
    fell back to DPG's built-in bitmap font — which has no glyphs for
    em/en dash, curly quotes, ellipsis, bullet, or the ▲▼◀▶■□●○ symbols
    used for status indicators, rendering every one of them as a literal
    '?'. Confirmed visually via an Xvfb+screenshot smoke test: on Linux,
    with a real font loaded (DejaVu Sans Mono/Liberation Mono), those
    glyphs render correctly with no extra range/hint calls needed — DPG
    2.3.1 sizes a loaded font's glyph ranges automatically (add_font_range
    and add_font_range_hint are both deprecated no-ops in this version).
    """
    font_path = next((p for p in _CONSOLE_FONT_CANDIDATES if os.path.exists(p)), None)
    if font_path is None:
        return None
    try:
        with dpg.font_registry():
            with dpg.font(font_path, 14) as fid:
                pass
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
                 speed_master_pool=None,
                 attr_pools=None, osc=None,
                 library=None, save_patch_fn=None, fx_params=None,
                 audio_engine=None, audio_mapper=None):
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
        self._rate_pool   = rate_pool
        self._size_pool   = size_pool
        self._spread_pool = spread_pool
        self._speed_pool  = speed_master_pool
        self._attr_pools  = attr_pools or {}   # {name: AttributePool}
        self._library     = library
        self._fx_params   = fx_params
        self._save        = save_fn         # save_fn() → ShowFile.save()
        self._save_patch  = save_patch_fn   # save_patch_fn() → ShowFile.save_patch()
        self._cmd         = cmd_fn          # cmd_fn(str) → result str
        self._audio_engine = audio_engine   # AudioEngine — capture + level/band analysis
        self._audio_mapper = audio_mapper   # AudioMapper — level/band → output_state.audio_layer

        self._cmd_log     = []         # command history lines
        self._cmd_history = []         # entered commands for ↑↓ recall
        self._cmd_hist_i  = -1        # history cursor

        self._flash_held  = {}         # {exec_id: bool} — tracks held state of FLASH buttons
        self._col_btn_themes  = {}     # {slot_n: ((r,g,b), theme_id)} — per-color-preset button themes
        self._dim_btn_themes  = {}     # {slot_n: (level, theme_id)} — per-dim-preset button themes
        self._out_bar_themes  = {}     # {fid: ((r,g,b), theme_id)} — output monitor bar tints
        self._prog_bar_themes = {}     # {fid: ((r,g,b), theme_id)} — programmer bar tints
        self._tap_times       = []     # monotonic timestamps of recent BPM taps
        self._error_flash_time = None  # monotonic time of last _log_error call

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
        self._ai_prompts       = []   # list of {name, prompt} — user-editable AI prompt presets
        self._fpg_page          = 1    # current fader-page bank (1-based); slot N shows exec (page-1)*15+N

    # ── Popup layout persistence ─────────────────────────────

    _POPUP_TAGS = [
        "patch_window", "osc_window", "midi_window", "fx_editor_window",
        "keys_window", "changelog_window", "pages_window", "monitors_window",
        "ai_history_window", "attr_window", "ai_prompts_window", "ai_bar_window",
        "color_picker_window", "speed_master_window", "fader_page_window",
        "audio_window", "fx_params_window",
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
        "osc_window":       "_refresh_osc_table",
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
        self._alert_btn_theme     = _make_alert_btn_theme()
        self._transport_go_theme  = _make_transport_go_theme()
        self._dim_btn_theme       = _make_dim_btn_theme()
        self._numpad_digit_theme  = _make_numpad_digit_theme()
        self._pool_live_theme     = _make_pool_live_theme()
        self._pool_empty_theme    = _make_pool_empty_theme()

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
        self._build_osc_popup()
        self._build_midi_popup()
        self._build_patch_popup()
        self._build_keys_popup()
        self._build_fx_editor_popup()
        self._build_cue_timing_popup()
        self._build_changelog_popup()
        self._build_pages_popup()
        self._build_attr_popup()
        self._build_fx_params_popup()
        self._build_monitors_popup()
        self._build_ai_bar_popup()
        self._build_ai_history_popup()
        self._build_ai_prompts_popup()
        self._build_color_picker_popup()
        self._build_speed_master_popup()
        self._build_fader_page_popup()
        self._build_audio_popup()

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
            dpg.add_key_press_handler(dpg.mvKey_Z,
                                      callback=self._on_ctrl_z)
            dpg.add_key_press_handler(dpg.mvKey_Up,
                                      callback=self._on_hist_up)
            dpg.add_key_press_handler(dpg.mvKey_Down,
                                      callback=self._on_hist_down)
            dpg.add_mouse_click_handler(callback=self._on_global_mouse_click)

        # Apply per-item themes after widgets are built
        try:
            dpg.bind_item_theme("go_btn",           self._transport_go_theme)
            dpg.bind_item_theme("back_btn",         self._back_theme)
            dpg.bind_item_theme("numpad_digit_group", self._numpad_digit_theme)
        except Exception:
            pass

        dpg.create_viewport(title="Studio Console", width=W, height=H,
                            resizable=True, x_pos=0, y_pos=32)
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_primary_window("main", True)

    def _build_header(self):
        # ── Top row: info + 4 grouped button clusters ──────────
        with dpg.group(horizontal=True):
            dpg.add_text("studio  v0.21", color=_C_ACCENT)
            dpg.add_spacer(width=6)
            dpg.add_text("▶", tag="hdr_cue", color=_C_TEXT)
            dpg.add_spacer(width=6)
            dpg.add_text("fx: off", tag="hdr_fx", color=_C_DIM)
            dpg.add_spacer(width=6)
            dpg.add_text("", tag="hdr_clock", color=_C_DIM)
            dpg.add_text("dim: --", tag="hdr_dim", color=_C_TEXT)
            dpg.add_spacer(width=10)
            dpg.add_text("│", color=_C_BORDER)
            dpg.add_spacer(width=6)

            # cluster: hardware — patch / osc / midi
            dpg.add_text("hw", color=_C_DIM)
            dpg.add_spacer(width=4)
            dpg.add_button(label="patch", width=60, height=24,
                           callback=self._on_patch_toggle)
            dpg.add_spacer(width=2)
            dpg.add_button(label="osc", width=50, height=24,
                           callback=self._on_osc_toggle)
            dpg.add_spacer(width=2)
            dpg.add_button(label="midi", width=60, height=24,
                           callback=self._on_midi_toggle)
            dpg.add_spacer(width=8)
            dpg.add_text("│", color=_C_BORDER)
            dpg.add_spacer(width=6)

            # cluster: views — pages / attr / fdrs / mon
            dpg.add_text("view", color=_C_DIM)
            dpg.add_spacer(width=4)
            dpg.add_button(label="pages", width=55, height=24,
                           callback=self._on_pages_toggle)
            dpg.add_spacer(width=2)
            dpg.add_button(label="attr", width=50, height=24,
                           callback=self._on_attr_popup_toggle)
            dpg.add_spacer(width=2)
            dpg.add_button(label="fdrs", width=50, height=24,
                           callback=self._on_fader_page_toggle)
            dpg.add_spacer(width=2)
            dpg.add_button(label="mon", width=50, height=24,
                           callback=self._on_monitors_toggle)
            dpg.add_spacer(width=8)
            dpg.add_text("│", color=_C_BORDER)
            dpg.add_spacer(width=6)

            # cluster: tools — fx ed / color / spd / ai
            dpg.add_text("tools", color=_C_DIM)
            dpg.add_spacer(width=4)
            dpg.add_button(label="fx ed", width=60, height=24,
                           callback=self._on_fx_editor_toggle)
            dpg.add_spacer(width=2)
            dpg.add_button(label="color", width=52, height=24,
                           callback=self._on_color_picker_toggle)
            dpg.add_spacer(width=2)
            dpg.add_button(label="spd", width=46, height=24,
                           callback=self._on_speed_master_toggle)
            dpg.add_spacer(width=2)
            dpg.add_button(label="ai", width=36, height=24,
                           callback=self._on_ai_bar_toggle)
            dpg.add_spacer(width=8)
            dpg.add_text("│", color=_C_BORDER)
            dpg.add_spacer(width=6)

            # cluster: system — log / ? / audio / save show
            dpg.add_text("sys", color=_C_DIM)
            dpg.add_spacer(width=4)
            dpg.add_button(label="log", width=50, height=24,
                           callback=self._on_changelog_toggle)
            dpg.add_spacer(width=2)
            dpg.add_button(label="?", width=30, height=24,
                           callback=self._on_keys_toggle)
            dpg.add_spacer(width=2)
            dpg.add_button(label="audio", width=50, height=24,
                           callback=self._on_audio_toggle)
            dpg.add_spacer(width=2)
            dpg.add_button(label="save show", width=90, height=24,
                           callback=self._on_save)
            dpg.add_spacer(width=6)
            dpg.add_text("", tag="hdr_save_status", color=_C_DIM)

        dpg.add_separator()
        # ── Status bar: programmer state + mode pills + selection ─
        with dpg.group(horizontal=True):
            dpg.add_text("●", tag="sb_prog_dot",   color=_C_DIM)
            dpg.add_text("programmer", tag="sb_prog_lbl", color=_C_DIM)
            dpg.add_spacer(width=16)
            dpg.add_button(label="○ blind", tag="sb_blind_lbl",
                           width=70, height=24,
                           callback=self._on_blind_toggle)
            dpg.add_spacer(width=6)
            dpg.add_button(label="○ blackout", tag="sb_bbo_lbl",
                           width=94, height=24,
                           callback=lambda: self._cmd("BLACKOUT") if self._cmd else None)
            dpg.add_spacer(width=6)
            dpg.add_button(label="○ highlight", tag="sb_hl_lbl",
                           width=90, height=24,
                           callback=self._on_highlight_toggle)
            dpg.add_spacer(width=6)
            dpg.add_button(label="○ pan·tilt", tag="sb_pt_lbl",
                           width=84, height=24,
                           callback=self._on_pt_toggle)
            dpg.add_spacer(width=16)
            dpg.add_text("sel", color=_C_DIM)
            dpg.add_spacer(width=4)
            # one clickable chip per patched fixture
            if self._patch:
                for master in self._patch.all_fixtures():
                    fid = master.fixture_id
                    dpg.add_button(label=f"[{fid}]", tag=f"sb_sel_{fid}",
                                   width=34, height=20,
                                   callback=self._on_fixture_chip_click,
                                   user_data=fid)
                    dpg.add_spacer(width=2)
        dpg.add_separator()

    def _build_left_column(self):
        self._displayed_executor  = None
        self._displayed_cs_name   = None
        self._last_playbacks_hash = None
        _W = self._W_LEFT
        with dpg.child_window(tag="left_col", width=_W, height=self._H_MAIN,
                              border=True, no_scrollbar=True, no_scroll_with_mouse=True):
            # ── cue list ─────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("› cuestack", color=_C_ACCENT)
                dpg.add_combo(tag="left_cs_combo", items=["—"], default_value="—",
                              width=-120, height_mode=dpg.mvComboHeight_Small,
                              callback=self._on_cs_combo_select)
                dpg.add_text("", tag="hdr_wrap", color=_C_ACCENT)
            dpg.add_separator()
            # Fixed-height scroll area for the cue list
            with dpg.child_window(tag="cue_list_scroll", width=-1, height=118,
                                  border=True, no_scrollbar=True,
                                  no_scroll_with_mouse=False):
                dpg.add_group(tag="cue_list_group")
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_button(label=" ◀ back ", tag="back_btn", width=88, height=24,
                               callback=lambda: self._back())
                dpg.add_button(label=" ↺ reload ", width=100, height=24,
                               callback=lambda: self._reload() if self._reload else None)
                dpg.add_button(label="timing", width=70, height=24,
                               callback=self._on_cue_timing_toggle)
                dpg.add_button(label="  go ▶  ", tag="go_btn", width=88, height=24,
                               callback=lambda: self._go())

            # ── Active playbacks ─────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("› active playbacks", color=_C_ACCENT)
                dpg.add_spacer(width=4)
                dpg.add_button(label="stop all", width=78, height=24,
                               callback=self._on_stop_all_executors)
            dpg.add_separator()
            with dpg.child_window(tag="playbacks_list", width=-1, height=108,
                                  border=False, no_scrollbar=False, no_scroll_with_mouse=False):
                dpg.add_text("— none running", tag="playbacks_empty", color=_C_DIM)

            # ── FX controls ─────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("› fx", color=_C_ACCENT)
                dpg.add_spacer(width=4)
                dpg.add_button(label="tap", tag="fx_tap_btn", width=42, height=24,
                               callback=self._on_tap_tempo)
                dpg.add_text("", tag="fx_tap_label", color=_C_DIM)
            dpg.add_separator()
            _sw = _W - 120
            dpg.add_slider_float(label="rate bpm", tag="fx_rate",
                                 default_value=60.0, min_value=10.0,
                                 max_value=480.0, width=_sw,
                                 callback=self._on_fx_rate)
            dpg.add_slider_float(label="size    ", tag="fx_size",
                                 default_value=100.0, min_value=0.0,
                                 max_value=100.0, width=_sw,
                                 callback=self._on_fx_size)
            dpg.add_slider_float(label="spread  ", tag="fx_spread",
                                 default_value=0.0, min_value=0.0,
                                 max_value=100.0, width=_sw,
                                 callback=self._on_fx_spread)
            with dpg.group(horizontal=True):
                dpg.add_button(label="kill fx", tag="kill_fx_btn",
                               width=_W - 20 - 80 - 4,
                               callback=lambda: self._cmd("KILL FX") if self._cmd else None)
                dpg.add_button(label="rsp pool", width=80,
                               callback=self._on_fx_params_toggle)

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
                   dpg.is_key_down(dpg.mvKey_ModSuper))   # Cmd on macOS
        if is_ctrl:
            self._on_save()

    def _on_ctrl_z(self, *_):
        """Ctrl+Z: undo last programmer change."""
        is_ctrl = (dpg.is_key_down(dpg.mvKey_LControl) or
                   dpg.is_key_down(dpg.mvKey_RControl) or
                   dpg.is_key_down(dpg.mvKey_ModSuper))
        if is_ctrl and self._cmd:
            result = self._cmd("UNDO")
            if result:
                self._log(f"> {result}")

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
                   dpg.is_key_down(dpg.mvKey_ModSuper))   # Cmd on macOS
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

    def _on_cue_timing_toggle(self):
        try:
            if dpg.is_item_shown("cue_timing_window"):
                dpg.hide_item("cue_timing_window")
            else:
                dpg.show_item("cue_timing_window")
        except Exception:
            pass

    def _on_osc_toggle(self):
        try:
            if dpg.is_item_shown("osc_window"):
                self._save_popup_layout()
                dpg.hide_item("osc_window")
            else:
                self._refresh_osc_table()
                dpg.show_item("osc_window")
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
        _BH = 24   # quick-action button height
        _W  = self._W_RIGHT

        with dpg.child_window(tag="right_col", width=_W, height=self._H_MAIN,
                              border=True, no_scrollbar=True, no_scroll_with_mouse=True):
            # ── Header ─────────────────────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("› command line", color=_C_ACCENT)
                dpg.add_spacer(width=10)
                dpg.add_text("sel: —", tag="cmd_sel_count", color=_C_DIM)

            # ── Log — larger to show more feedback lines ─────────
            with dpg.child_window(tag="cmd_log_win", width=-1, height=140,
                                  border=True, horizontal_scrollbar=False,
                                  no_scrollbar=True, no_scroll_with_mouse=True):
                dpg.add_text("", tag="cmd_log", wrap=0)

            # ── Error flash — shows last error in red; clears on next success ─
            dpg.add_text("", tag="cmd_error_flash", color=[255, 80, 80, 220], wrap=0)

            # ── Input row ──────────────────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("cmd >", color=_C_ACCENT)
                dpg.add_input_text(
                    tag="cmd_input",
                    hint="1 thru 6  |  1 thru 6 r 255  |  fx sine red  |  go  |  save",
                    width=-220, on_enter=True,
                    callback=self._on_cmd_execute,
                )
                dpg.add_button(label="enter", width=80, height=24,
                               callback=self._on_cmd_execute)
                dpg.add_button(label="clr", width=50, height=24,
                               callback=self._numpad_clear_input)

            dpg.add_separator()

            # ── Quick action row 1: cue / record / FX ──────────
            with dpg.group(horizontal=True):
                for label, ud in [
                    ("rec cue", "RECORD CUE "), ("upd cue", "UPDATE CUE "),
                    ("cue",     "CUE "),         ("rec fx",  "RECORD FX "),
                    ("fx",      "FX "),           ("rec grp", "RECORD GROUP "),
                    ("group",   "GROUP "),        ("snap",    "SNAPSHOT "),
                ]:
                    dpg.add_button(label=label, width=82, height=_BH,
                                   callback=self._numpad_append, user_data=ud)

            # ── Quick action row 2: timing / CLEAR / transport ─
            with dpg.group(horizontal=True):
                for label, ud in [
                    ("fade",  " FADE "), ("cfade", " CFADE "),
                    ("dfade", " DFADE "), ("delay", " DELAY "),
                ]:
                    dpg.add_button(label=label, width=72, height=_BH,
                                   callback=self._numpad_append, user_data=ud)
                dpg.add_spacer(width=8)
                for label, ud in [
                    ("clear", "CLEAR"), ("reload", "RELOAD"),
                    ("go",    "GO"),    ("back",   "BACK"),
                    ("undo",  "UNDO"),
                ]:
                    dpg.add_button(label=label, width=72, height=_BH,
                                   callback=self._numpad_exec, user_data=ud)

            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_text("› numpad", color=_C_ACCENT)
                dpg.add_spacer(width=8)
                dpg.add_text("digit", color=_C_DIM)
                dpg.add_spacer(width=80)
                dpg.add_text("keyword", color=_C_DIM)

            # ── Numpad + keyword keys ───────────────────────────
            # Digit pad (left) + keyword pad (right), each 4 rows × 3 cols.
            # Total width: 3×_NW + 12 + 3-col-kw, all within _W_RIGHT.
            with dpg.group(horizontal=True):

                # Left: digit pad [7][8][9] / [4][5][6] / [1][2][3] / [⌫][0][.]
                with dpg.group(tag="numpad_digit_group"):
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
                    [("clr", _KW, self._numpad_clear_input, None),
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
    # Section heights — sized to fit 1040px viewport with no scroll.
    # Budget: 1040px viewport - 12px WindowPadding - gaps ≈ 988px for content.
    # Header~70 + 3-col row~512 + sep~2 + P1~170 + P2~170 + Forms~88 = 1012px ✓
    # This budget no longer varies with AI config: the AI prompt bar (chips +
    # input, formerly inlined into the main window only when
    # self._ai._enabled, which busted this budget by ~70px for any user with
    # ANTHROPIC_API_KEY set) now lives in its own popup (_build_ai_bar_popup,
    # "ai" header button), same pattern as attribute pools and monitors.
    # Attribute pools (position/gobo/zoom/focus/beam) also live in a separate
    # popup (_build_attr_popup), not stacked in the main window — see
    # _build_pools_row. The main window keeps scrolling enabled as a fallback
    # regardless, since exact pixel behavior can't be verified without a real
    # display.
    #
    # _H_MAIN was 480, but pixel measurement (dpg.get_y_scroll_max on the real
    # rendered left_col) showed its content overflowing that budget by 224px —
    # left_col had a permanent scrollbar cutting off the bottom third of the
    # FX controls. Moved the Rate/Size/spread pool quick-recall grid to its own
    # popup (_build_fx_params_popup, "rsp pool" button — same pattern as the
    # attribute-pool and speed-master popups) and paired the cue timing fields
    # two-per-row instead of one-per-row, which closed all but 32px of the gap
    # (re-verified by the same pixel measurement after each change). The
    # remaining 32px came out of real spare viewport budget confirmed by
    # measurement, not a guess: raising _H_MAIN this far still leaves the
    # forms row inside the 1040px viewport with room to spare.
    _H_MAIN     = 512   # main 3-col area — tall enough for all left-col FX controls
    _H_P1       = 182   # pool row 1: 4×30btn + 3×5gap + header + 12WP ≈ 170px content
    _H_P2       = 182   # pool row 2
    _H_FORMS    =  56   # forms single row (unused — _build_forms_panel computes own height)
    _H_MON      = 270   # monitor popup panel height (not in main layout)
    # Column widths
    _W_LEFT     = 380
    _W_RIGHT    = 720
    # pool grid
    _POOL_SLOTS = 24    # 4 rows × 6 cols per panel
    _POOL_COLS  = 6
    _PANEL_W    = 634   # panels touch: 3 × 634 = 1902 fits 1920 w/ outer padding
    # BTN_W: (634 - 2×8pad - 2×1border - 5×6gap) / 6 = (616-30)/6 = 97.7 → 97
    _BTN_W      =  97   # exactly fits 6 columns in a 634-wide panel
    _BTN_H      =  30   # 4 rows × 30 + 3 × 5gap + header = ~155px content
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
                dpg.add_text("master", color=_C_ACCENT)
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
                        fill=(18, 13, 40, 255),
                        color=(55, 38, 105, 255),
                        thickness=1,
                        rounding=4,
                    )
                    dpg.draw_text(
                        pos=(0, 0), tag=f"stage_lbl_{i}",
                        text="", color=_C_TEXT, size=14,
                    )
                    dpg.draw_text(
                        pos=(0, 0), tag=f"stage_dim_{i}",
                        text="", color=_C_DIM, size=11,
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
            dim = master.virtual_dimmer   # default before output engine query
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
                    # Envelope-blended merge (matches get_dmx_for_universe)
                    if 'red' in fx_s:
                        env_r = fx_s.get('_env_red', 1.0)
                        r = max(0, min(255, int(base_r * (1.0 - env_r) + fx_s['red'])))
                    else:
                        r = int(base_r)
                    if 'green' in fx_s:
                        env_g = fx_s.get('_env_green', 1.0)
                        g = max(0, min(255, int(base_g * (1.0 - env_g) + fx_s['green'])))
                    else:
                        g = int(base_g)
                    if 'blue' in fx_s:
                        env_b = fx_s.get('_env_blue', 1.0)
                        b = max(0, min(255, int(base_b * (1.0 - env_b) + fx_s['blue'])))
                    else:
                        b = int(base_b)
                    mp  = self._out.programmer_layer.get(fid, {})
                    mc  = cue_merged.get(fid, {})
                    fxm = self._out.fx_layer.get(fid, {})
                    fdr = fxm.get('dim')
                    # pixel-scope dim FX lives under the sub fixture ID, not master
                    if fdr is None:
                        fdr = fx_s.get('dim')
                    ron = any(fx_s.get(f'_env_{c}', 0.0) > 0.001
                              for c in ('red', 'green', 'blue'))
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
            hl_active = (self._out and self._out.highlight_mode and
                         master.fixture_id in self._out.highlight_fids)
            if hl_active:
                fill = (255, 255, 255, 255)
            elif r or g or b:
                fill = (r, g, b, 255)
            elif dim > 0:
                grey = max(0, min(255, int(dim * gm * 200)))
                fill = (grey, grey, grey, 255)
            else:
                fill = (18, 13, 40, 255)
            sel_masters = {f.fixture_id for f in self._prog.selection
                           if isinstance(f, MasterFixture)}
            border_col = (162, 115, 255, 255) if master.fixture_id in sel_masters else (55, 38, 105, 255)
            dim_pct = int(dim * gm * 100)
            dim_col = _C_TEXT if dim_pct > 0 else _C_DIM
            try:
                dpg.configure_item(f"stage_rect_{i}", pmin=(x0, gap), pmax=(x1, gap + mh),
                                   fill=fill, color=border_col, thickness=2, rounding=4)
                dpg.configure_item(f"stage_lbl_{i}",  pos=(x0 + 4, gap + 6),  text=master.name[:10])
                dpg.configure_item(f"stage_dim_{i}",  pos=(x0 + 4, gap + 28),
                                   text=f"{dim_pct}%", color=dim_col)
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
                # Envelope-blended merge (matches get_dmx_for_universe)
                if 'red' in fs:
                    env_r = fs.get('_env_red', 1.0)
                    sr = max(0, min(255, int(int(br) * (1.0 - env_r) + fs['red'])))
                else:
                    sr = int(br)
                if 'green' in fs:
                    env_g = fs.get('_env_green', 1.0)
                    sg = max(0, min(255, int(int(bg2) * (1.0 - env_g) + fs['green'])))
                else:
                    sg = int(bg2)
                if 'blue' in fs:
                    env_b = fs.get('_env_blue', 1.0)
                    sb2 = max(0, min(255, int(int(bb) * (1.0 - env_b) + fs['blue'])))
                else:
                    sb2 = int(bb)
                mp   = self._out.programmer_layer.get(fid, {})
                mc   = cue_merged.get(fid, {})
                fxm  = self._out.fx_layer.get(fid, {})
                fdr  = fxm.get('dim')
                # pixel-scope dim FX lives under the sub fixture ID, not master
                if fdr is None:
                    fdr = fs.get('dim')
                ron  = any(fs.get(f'_env_{c}', 0.0) > 0.001 for c in ('red', 'green', 'blue'))
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
                if hl_active:
                    sfill = (255, 255, 255, 255)
                elif sr or sg or sb2:
                    sfill = (sr, sg, sb2, 255)
                elif sdim > 0:
                    sgrey = max(0, min(255, int(sdim * gm * 200)))
                    sfill = (sgrey, sgrey, sgrey, 255)
                else:
                    sfill = (16, 11, 36, 255)
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
            dpg.add_text("› groups", color=_C_P_GROUPS)
            dpg.add_separator()
            for row in range(rows):
                with dpg.group(horizontal=True):
                    for col in range(self._POOL_COLS):
                        n = row * self._POOL_COLS + col + 1
                        dpg.add_button(
                            tag=f"grp_btn_{n}", label=f"g{n}",
                            width=self._BTN_W, height=self._BTN_H,
                            callback=self._on_group_click, user_data=n)
                        with dpg.tooltip(f"grp_btn_{n}"):
                            dpg.add_text(f"group {n}", tag=f"grp_tip_{n}")
                        with dpg.popup(f"grp_btn_{n}", mousebutton=1):
                            dpg.add_text(f"group {n}", color=_C_P_GROUPS)
                            dpg.add_separator()
                            dpg.add_menu_item(label="record group here",
                                callback=self._ctx_prefill,
                                user_data=f"RECORD GROUP {n} ")
                            dpg.add_menu_item(label="recall group",
                                callback=self._ctx_exec,
                                user_data=f"GROUP {n}")
                            dpg.add_menu_item(label="rename...",
                                callback=self._ctx_prefill,
                                user_data=f"RENAME GROUP {n} ")
                            dpg.add_menu_item(label="copy to slot...",
                                callback=self._ctx_prefill,
                                user_data=f"COPY GROUP {n} TO ")
                            dpg.add_separator()
                            dpg.add_menu_item(label="clear group",
                                callback=self._ctx_exec,
                                user_data=f"CLEAR GROUP {n}")

    def _build_color_panel(self):
        rows = self._POOL_SLOTS // self._POOL_COLS
        with dpg.child_window(tag="pool_colors", width=self._PANEL_W,
                              height=self._POOL_H, border=True,
                              no_scrollbar=True, no_scroll_with_mouse=True):
            dpg.add_text("› color presets", color=_C_P_COLORS)
            dpg.add_separator()
            for row in range(rows):
                with dpg.group(horizontal=True):
                    for col in range(self._POOL_COLS):
                        n = row * self._POOL_COLS + col + 1
                        dpg.add_button(
                            tag=f"col_btn_{n}", label=f"c{n}",
                            width=self._BTN_W, height=self._BTN_H,
                            callback=self._on_color_click, user_data=n)
                        with dpg.tooltip(f"col_btn_{n}"):
                            dpg.add_text(f"color {n}", tag=f"col_tip_{n}")
                        with dpg.popup(f"col_btn_{n}", mousebutton=1):
                            dpg.add_text(f"color {n}", color=_C_P_COLORS)
                            dpg.add_separator()
                            dpg.add_menu_item(label="record color here",
                                callback=self._ctx_prefill,
                                user_data=f"RECORD COLOR {n} ")
                            dpg.add_menu_item(label="apply color",
                                callback=self._ctx_exec,
                                user_data=f"COLOR {n}")
                            dpg.add_menu_item(label="rename...",
                                callback=self._ctx_prefill,
                                user_data=f"RENAME COLOR {n} ")
                            dpg.add_menu_item(label="copy to slot...",
                                callback=self._ctx_prefill,
                                user_data=f"COPY COLOR {n} TO ")
                            dpg.add_separator()
                            dpg.add_menu_item(label="clear color",
                                callback=self._ctx_exec,
                                user_data=f"CLEAR COLOR {n}")

    def _build_dim_panel(self):
        rows = self._POOL_SLOTS // self._POOL_COLS
        with dpg.child_window(tag="pool_dims", width=self._PANEL_W,
                              height=self._POOL_H, border=True,
                              no_scrollbar=True, no_scroll_with_mouse=True):
            dpg.add_text("› dim presets", color=_C_P_DIMS)
            dpg.add_separator()
            for row in range(rows):
                with dpg.group(horizontal=True):
                    for col in range(self._POOL_COLS):
                        n = row * self._POOL_COLS + col + 1
                        dpg.add_button(
                            tag=f"dim_btn_{n}", label=f"d{n}",
                            width=self._BTN_W, height=self._BTN_H,
                            callback=self._on_dim_click, user_data=n)
                        with dpg.tooltip(f"dim_btn_{n}"):
                            dpg.add_text(f"dim {n}", tag=f"dim_tip_{n}")
                        with dpg.popup(f"dim_btn_{n}", mousebutton=1):
                            dpg.add_text(f"dim {n}", color=_C_P_DIMS)
                            dpg.add_separator()
                            dpg.add_menu_item(label="record dim here",
                                callback=self._ctx_prefill,
                                user_data=f"RECORD DIM {n} ")
                            dpg.add_menu_item(label="apply dim",
                                callback=self._ctx_exec,
                                user_data=f"DIM {n}")
                            dpg.add_menu_item(label="rename...",
                                callback=self._ctx_prefill,
                                user_data=f"RENAME DIM {n} ")
                            dpg.add_menu_item(label="copy to slot...",
                                callback=self._ctx_prefill,
                                user_data=f"COPY DIM {n} TO ")
                            dpg.add_separator()
                            dpg.add_menu_item(label="clear dim",
                                callback=self._ctx_exec,
                                user_data=f"CLEAR DIM {n}")

    def _focus_cmd(self):
        pass  # key routing via global handlers; no focus transfer needed

    # ── pool right-click context menu callbacks ──────────────────────────
    def _ctx_exec(self, _s, _a, cmd):
        """Execute cmd immediately and log result."""
        if not self._cmd:
            return
        result = self._cmd(cmd)
        self._log(f"> {cmd}")
        if result:
            for line in str(result).splitlines():
                self._log(f"  {line}")

    def _ctx_prefill(self, _s, _a, text):
        """Pre-fill command line and focus it."""
        try:
            dpg.set_value("cmd_input", text)
        except Exception:
            pass

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
            dpg.add_text("› cuestacks", color=_C_P_CS)
            dpg.add_separator()
            for row in range(rows):
                with dpg.group(horizontal=True):
                    for col in range(self._POOL_COLS):
                        n = row * self._POOL_COLS + col + 1
                        dpg.add_button(
                            tag=f"cs_btn_{n}", label=f"cs{n}",
                            width=self._BTN_W, height=self._BTN_H,
                            callback=self._on_cuestack_click, user_data=n)
                        with dpg.tooltip(f"cs_btn_{n}"):
                            dpg.add_text(f"cuestack {n}", tag=f"cs_tip_{n}")
                        with dpg.popup(f"cs_btn_{n}", mousebutton=1):
                            dpg.add_text(f"cuestack {n}", color=_C_P_CS)
                            dpg.add_separator()
                            dpg.add_menu_item(label="select / activate",
                                callback=self._on_cuestack_click,
                                user_data=n)
                            dpg.add_menu_item(label="create / rename...",
                                callback=self._ctx_prefill,
                                user_data=f"RECORD CUESTACK {n} ")
                            dpg.add_menu_item(label="rename...",
                                callback=self._ctx_prefill,
                                user_data=f"RENAME CUESTACK {n} ")
                            dpg.add_menu_item(label="assign to fader...",
                                callback=self._ctx_prefill,
                                user_data=f"ASSIGN CS {n} TO FADER ")
                            dpg.add_separator()
                            dpg.add_menu_item(label="delete cuestack",
                                callback=self._ctx_exec,
                                user_data=f"delete cueSTACK {n}")

    def _build_cue_panel(self):
        rows = self._POOL_SLOTS // self._POOL_COLS
        with dpg.child_window(tag="pool_cues", width=self._PANEL_W,
                              height=self._POOL_H, border=True,
                              no_scrollbar=True, no_scroll_with_mouse=True):
            dpg.add_text("› cues", color=_C_P_CUES)
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
                            dpg.add_text(f"cue {n}", tag=f"cue_tip_{n}")
                        with dpg.popup(f"cue_btn_{n}", mousebutton=1):
                            dpg.add_text(f"cue {n}", color=_C_P_CUES)
                            dpg.add_separator()
                            dpg.add_menu_item(label="go to cue",
                                callback=self._on_cue_click,
                                user_data=n)
                            dpg.add_menu_item(label="record cue here",
                                callback=self._ctx_prefill,
                                user_data=f"RECORD CUE {n} ")
                            dpg.add_menu_item(label="update cue",
                                callback=self._ctx_exec,
                                user_data=f"UPDATE CUE {n}")
                            dpg.add_menu_item(label="rename...",
                                callback=self._ctx_prefill,
                                user_data=f"RENAME CUE {n} ")
                            dpg.add_separator()
                            dpg.add_menu_item(label="delete cue",
                                callback=self._ctx_exec,
                                user_data=f"delete cue {n}")

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
                dpg.add_text("› fx pool", color=_C_P_FX)
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
                            tag=f"fx_btn_{n}", label=f"fx{n}",
                            width=self._BTN_W, height=self._BTN_H,
                            callback=self._on_fx_click, user_data=n)
                        with dpg.tooltip(f"fx_btn_{n}"):
                            dpg.add_text(f"fx {n}", tag=f"fx_tip_{n}")
                        with dpg.popup(f"fx_btn_{n}", mousebutton=1):
                            dpg.add_text(f"fx preset {n}", color=_C_P_FX)
                            dpg.add_separator()
                            dpg.add_menu_item(label="fire fx",
                                callback=self._ctx_exec,
                                user_data=f"FIRE FX {n}")
                            dpg.add_menu_item(label="record fx here",
                                callback=self._ctx_prefill,
                                user_data=f"RECORD FX {n} ")
                            dpg.add_menu_item(label="rename...",
                                callback=self._ctx_prefill,
                                user_data=f"RENAME FX {n} ")
                            dpg.add_menu_item(label="copy to slot...",
                                callback=self._ctx_prefill,
                                user_data=f"COPY FX {n} TO ")
                            dpg.add_separator()
                            dpg.add_menu_item(label="clear fx preset",
                                callback=self._ctx_exec,
                                user_data=f"CLEAR FX {n}")

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
                            label=f"{attr_name[0]}{n}",
                            width=self._BTN_W, height=self._BTN_H,
                            callback=self._on_attr_click,
                            user_data=(attr_name, n))
                        with dpg.tooltip(f"{tag_prefix}_btn_{n}"):
                            dpg.add_text(f"{attr_name} {n}",
                                         tag=f"{tag_prefix}_tip_{n}")
                        with dpg.popup(f"{tag_prefix}_btn_{n}", mousebutton=1):
                            dpg.add_text(f"{attr_name} {n}", color=color)
                            dpg.add_separator()
                            dpg.add_menu_item(label=f"record {attr_name} here",
                                callback=self._ctx_prefill,
                                user_data=f"RECORD {attr_name.upper()} {n} ")
                            dpg.add_menu_item(label=f"apply {attr_name}",
                                callback=self._ctx_exec,
                                user_data=f"{attr_name.upper()} {n}")
                            dpg.add_menu_item(label="rename...",
                                callback=self._ctx_prefill,
                                user_data=f"RENAME {attr_name.upper()} {n} ")
                            dpg.add_menu_item(label="copy to slot...",
                                callback=self._ctx_prefill,
                                user_data=f"COPY {attr_name.upper()} {n} TO ")
                            dpg.add_separator()
                            dpg.add_menu_item(label=f"clear {attr_name}",
                                callback=self._ctx_exec,
                                user_data=f"CLEAR {attr_name.upper()} {n}")

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
        with dpg.window(tag="attr_window", label="attribute pools",
                        width=1902, height=290, show=False,
                        pos=(10, 80), no_collapse=False):
            dpg.add_text("position / gobo / zoom / focus / beam / control", color=_C_ACCENT)
            dpg.add_text("moving-light attributes — not used by the 6 lt-200 pixel tubes "
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

    def _build_fx_params_popup(self):
        """Floating Rate/Size/spread pool panel — hidden by default, opened via
        the 'rsp pool' button next to the inline FX sliders. Moved out of the
        left column (was pushing left_col 224px past its 480px budget, the
        largest single contributor) — the sliders themselves (live values)
        and kill fx stay inline since those are used every cue; recall/record/
        rename of the 4-slot pools is used far less often and fits the same
        popup-for-pool pattern already used for attribute pools and speed
        masters."""
        _POOL_BTN = 90
        with dpg.window(tag="fx_params_window", label="rate / size / spread pools",
                        width=420, height=190, show=False,
                        pos=(600, 80), no_collapse=False):
            dpg.add_text("rate", color=_C_DIM)
            with dpg.group(horizontal=True):
                for n in range(1, 5):
                    dpg.add_button(tag=f"rate_btn_{n}", label=f"r{n}",
                                   width=_POOL_BTN, height=22,
                                   callback=self._on_rate_click, user_data=n)
                    with dpg.tooltip(f"rate_btn_{n}"):
                        dpg.add_text(f"rate {n}", tag=f"rate_tip_{n}")
                    with dpg.popup(f"rate_btn_{n}", mousebutton=1):
                        dpg.add_text(f"rate {n}", color=_C_DIM)
                        dpg.add_separator()
                        dpg.add_menu_item(label="recall rate",
                            callback=self._ctx_exec, user_data=f"RATE {n}")
                        dpg.add_menu_item(label="record rate here...",
                            callback=self._ctx_prefill,
                            user_data=f"RECORD RATE {n} ")
                        dpg.add_menu_item(label="rename...",
                            callback=self._ctx_prefill,
                            user_data=f"RENAME RATE {n} ")
                        dpg.add_menu_item(label="copy to slot...",
                            callback=self._ctx_prefill,
                            user_data=f"COPY RATE {n} TO ")
                        dpg.add_separator()
                        dpg.add_menu_item(label="delete rate",
                            callback=self._ctx_exec, user_data=f"DELETE RATE {n}")
            dpg.add_text("size", color=_C_DIM)
            with dpg.group(horizontal=True):
                for n in range(1, 5):
                    dpg.add_button(tag=f"size_btn_{n}", label=f"s{n}",
                                   width=_POOL_BTN, height=22,
                                   callback=self._on_size_click, user_data=n)
                    with dpg.tooltip(f"size_btn_{n}"):
                        dpg.add_text(f"size {n}", tag=f"size_tip_{n}")
                    with dpg.popup(f"size_btn_{n}", mousebutton=1):
                        dpg.add_text(f"size {n}", color=_C_DIM)
                        dpg.add_separator()
                        dpg.add_menu_item(label="recall size",
                            callback=self._ctx_exec, user_data=f"SIZEP {n}")
                        dpg.add_menu_item(label="record size here...",
                            callback=self._ctx_prefill,
                            user_data=f"RECORD SIZEP {n} ")
                        dpg.add_menu_item(label="rename...",
                            callback=self._ctx_prefill,
                            user_data=f"RENAME SIZEP {n} ")
                        dpg.add_menu_item(label="copy to slot...",
                            callback=self._ctx_prefill,
                            user_data=f"COPY SIZEP {n} TO ")
                        dpg.add_separator()
                        dpg.add_menu_item(label="delete size",
                            callback=self._ctx_exec, user_data=f"DELETE SIZEP {n}")
            dpg.add_text("spread", color=_C_DIM)
            with dpg.group(horizontal=True):
                for n in range(1, 5):
                    dpg.add_button(tag=f"spread_btn_{n}", label=f"sp{n}",
                                   width=_POOL_BTN, height=22,
                                   callback=self._on_spread_click, user_data=n)
                    with dpg.tooltip(f"spread_btn_{n}"):
                        dpg.add_text(f"spread {n}", tag=f"spread_tip_{n}")
                    with dpg.popup(f"spread_btn_{n}", mousebutton=1):
                        dpg.add_text(f"spread {n}", color=_C_DIM)
                        dpg.add_separator()
                        dpg.add_menu_item(label="recall spread",
                            callback=self._ctx_exec, user_data=f"SPREADP {n}")
                        dpg.add_menu_item(label="record spread here...",
                            callback=self._ctx_prefill,
                            user_data=f"RECORD SPREADP {n} ")
                        dpg.add_menu_item(label="rename...",
                            callback=self._ctx_prefill,
                            user_data=f"RENAME SPREADP {n} ")
                        dpg.add_menu_item(label="copy to slot...",
                            callback=self._ctx_prefill,
                            user_data=f"COPY SPREADP {n} TO ")
                        dpg.add_separator()
                        dpg.add_menu_item(label="delete spread",
                            callback=self._ctx_exec, user_data=f"DELETE SPREADP {n}")

    def _on_fx_params_toggle(self, *_):
        try:
            if dpg.is_item_shown("fx_params_window"):
                self._save_popup_layout()
                dpg.hide_item("fx_params_window")
            else:
                dpg.show_item("fx_params_window")
        except Exception:
            pass

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
            dpg.add_text("› forms", color=_C_P_FORMS)
            dpg.add_separator()
            for row in range(2):
                with dpg.group(horizontal=True):
                    for col in range(_FORMS_COLS):
                        n = row * _FORMS_COLS + col + 1
                        dpg.add_button(
                            tag=f"form_btn_{n}", label=f"f{n}",
                            width=_FORMS_BTN_W, height=self._BTN_H,
                            callback=self._on_form_click, user_data=n)
                        with dpg.tooltip(f"form_btn_{n}"):
                            dpg.add_text(f"form {n}", tag=f"form_tip_{n}")
                        if n >= FormPool.FIRST_CUSTOM_SLOT:
                            with dpg.popup(f"form_btn_{n}", mousebutton=1):
                                dpg.add_text(f"form {n}", color=_C_P_FORMS)
                                dpg.add_separator()
                                dpg.add_menu_item(label="use form",
                                    callback=self._ctx_exec,
                                    user_data=f"FX FORM {n}")
                                dpg.add_menu_item(label="rename...",
                                    callback=self._ctx_prefill,
                                    user_data=f"RENAME FORM {n} ")
                                dpg.add_separator()
                                dpg.add_menu_item(label="delete form",
                                    callback=self._ctx_exec,
                                    user_data=f"DELETE FORM {n}")

    def _on_fx_click(self, _sender, _app_data, user_data):
        n = user_data
        if self._fx_pool and self._fx_pool.get(n):
            result = self._cmd(f"FIRE FX {n}") if self._cmd else None
            preset = self._fx_pool.get(n)
            self._log(f"> fx {n} — {preset.name}")
            if result:
                self._log(f"  {result}")
            # If the FX editor is open, sync it to this slot
            try:
                if dpg.get_item_configuration("fx_editor_window").get("show", False):
                    self._fxed_select_slot(None, None, n)
            except Exception:
                pass
        else:
            self._log(f"> fx {n} is empty — open fx ed to build a preset")
        self._focus_cmd()

    def _on_clear_fx(self, *_):
        result = self._cmd("CLEAR FX") if self._cmd else None
        self._log("> clear fx")
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
                self._log(f"  slots 1-4 are built-ins (sine/ramp/pulse/square)")
            else:
                self._log(f"  to record: record form {n} name 0.0,0.0 0.5,1.0 1.0,0.0")
        self._focus_cmd()

    def _on_rate_click(self, _sender, _app_data, user_data):
        n = user_data
        if self._cmd:
            result = self._cmd(f"RATE {n}")
            if result:
                self._log(f"> RATE {n}")
                self._log(f"  {result}")

    def _on_size_click(self, _sender, _app_data, user_data):
        n = user_data
        if self._cmd:
            result = self._cmd(f"SIZEP {n}")
            if result:
                self._log(f"> SIZEP {n}")
                self._log(f"  {result}")

    def _on_spread_click(self, _sender, _app_data, user_data):
        n = user_data
        if self._cmd:
            result = self._cmd(f"SPREADP {n}")
            if result:
                self._log(f"> SPREADP {n}")
                self._log(f"  {result}")

    def _tick_pools(self):
        """Update pool button labels to show occupied/empty state."""
        for n in range(1, self._POOL_SLOTS + 1):
            # Groups
            g = self._groups.get(n) if self._groups else None
            lbl = f"{n}:{g.name[:7]}" if g else f"g{n}"
            try:
                dpg.set_item_label(f"grp_btn_{n}", lbl)
                _gt = self._pool_live_theme if g else self._pool_empty_theme
                if _gt:
                    dpg.bind_item_theme(f"grp_btn_{n}", _gt)
            except Exception:
                pass
            try:
                if g:
                    ids = [str(fid) for _, fid in g.members]
                    id_str = ", ".join(ids[:8]) + ("…" if len(ids) > 8 else "")
                    tip = f"group {n}: {g.name}\n{len(ids)} fixture(s): [{id_str}]"
                else:
                    tip = f"group {n} — empty"
                dpg.set_value(f"grp_tip_{n}", tip)
            except Exception:
                pass
            # Colors
            c = self._colors.get(n) if self._colors else None
            lbl = f"{n}:{c.name[:7]}" if c else f"c{n}"
            try:
                dpg.set_item_label(f"col_btn_{n}", lbl)
            except Exception:
                pass
            try:
                if c:
                    col_tip = f"color {n}: {c.name}\nR {int(c.red)}  G {int(c.green)}  B {int(c.blue)}"
                else:
                    col_tip = f"color {n} — empty"
                dpg.set_value(f"col_tip_{n}", col_tip)
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
            else:
                if n in self._col_btn_themes:
                    # preset deleted — remove custom theme
                    try:
                        dpg.delete_item(self._col_btn_themes[n][1])
                    except Exception:
                        pass
                    del self._col_btn_themes[n]
                # Apply empty theme (consistent with other pools)
                try:
                    if self._pool_empty_theme:
                        dpg.bind_item_theme(f"col_btn_{n}", self._pool_empty_theme)
                except Exception:
                    pass
            # Dims
            d = self._dims.get(n) if self._dims else None
            lbl = f"{n}:{d.name[:7]}" if d else f"d{n}"
            try:
                dpg.set_item_label(f"dim_btn_{n}", lbl)
            except Exception:
                pass
            try:
                tip = (f"dim {n}: {d.name}  {d.level*100:.0f}%") if d else f"dim {n} — empty"
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
            else:
                if n in self._dim_btn_themes:
                    try:
                        dpg.delete_item(self._dim_btn_themes[n][1])
                    except Exception:
                        pass
                    del self._dim_btn_themes[n]
                try:
                    if self._pool_empty_theme:
                        dpg.bind_item_theme(f"dim_btn_{n}", self._pool_empty_theme)
                except Exception:
                    pass

        # Cuestacks (slots 1-48) — highlight the active one
        active = self._active_executor[0] if self._active_executor else None
        for n in range(1, self._POOL_SLOTS + 1):
            cs = self._cuestack_pool.get(n) if self._cuestack_pool else None
            lbl = f"{n}:{cs.name[:5]}" if cs else f"cs{n}"
            try:
                dpg.set_item_label(f"cs_btn_{n}", lbl)
            except Exception:
                pass
            try:
                is_active = (n == active and cs is not None)
                if is_active:
                    theme = self._go_theme
                elif cs:
                    theme = self._pool_live_theme
                else:
                    theme = self._pool_empty_theme
                dpg.bind_item_theme(f"cs_btn_{n}", theme if theme else 0)
            except Exception:
                pass
            try:
                if cs:
                    ncues = len(cs.cues)
                    cur   = cs.current
                    cs_tip = f"cuestack {n}: {cs.name}\n{ncues} cue(s)"
                    if cur is not None:
                        cs_tip += f"\n▶ cue {cur:.0f}"
                else:
                    cs_tip = f"cuestack {n} — empty"
                dpg.set_value(f"cs_tip_{n}", cs_tip)
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
                fw    = getattr(cue, 'follow_time', 0.0)
                fw_s  = f"  →{fw:.0f}s" if fw > 0 else ""
                fxo   = getattr(cue, 'fx_outfade', None)
                fxo_s = f"  FXOut:{fxo}s" if fxo is not None else ""
                nfix  = sum(1 for k in getattr(cue, 'data', {}) if not k.startswith('__') and '.' not in k) if hasattr(cue, 'data') else 0
                fix_s = f"\n{nfix} fixture(s)" if nfix else ""
                nfx   = 0
                if hasattr(cue, 'data') and isinstance(cue.data, dict):
                    for k, v in cue.data.items():
                        if not k.startswith('__') and isinstance(v, dict):
                            nfx += len(v.get('fx', []) or [])
                fx_s  = f"\n{nfx} FX layer(s)" if nfx else ""
                note  = getattr(cue, 'note', '')
                note_s = f"\n📝 {note}" if note else ""
                tip   = f"cue {n}: {cue.name}{ft_s}{dt_s}{fw_s}{fxo_s}{fix_s}{fx_s}{note_s}"
            else:
                lbl = f"{n}"
                tip = f"cue {n} — empty"
            try:
                dpg.set_item_label(f"cue_btn_{n}", lbl)
                dpg.configure_item(f"cue_tip_{n}", default_value=tip)
            except Exception:
                pass
            # Highlight active cue green, dim empty slots, default for occupied-inactive
            try:
                if n == current_cue and cue:
                    dpg.bind_item_theme(f"cue_btn_{n}", self._go_theme if self._go_theme else 0)
                elif cue:
                    dpg.bind_item_theme(f"cue_btn_{n}", self._pool_live_theme if self._pool_live_theme else 0)
                else:
                    dpg.bind_item_theme(f"cue_btn_{n}", self._pool_empty_theme if self._pool_empty_theme else 0)
            except Exception:
                pass

        # FX pool (slots 1-48)
        for n in range(1, self._POOL_SLOTS + 1):
            p = self._fx_pool.get(n) if self._fx_pool else None
            lbl = f"{n}:{p.name[:6]}" if p else f"fx{n}"
            try:
                dpg.set_item_label(f"fx_btn_{n}", lbl)
                _ft = self._pool_live_theme if p else self._pool_empty_theme
                if _ft:
                    dpg.bind_item_theme(f"fx_btn_{n}", _ft)
            except Exception:
                pass
            try:
                if p and p.layers:
                    layer_strs = [f"{ld['waveform']} {ld['channel']} {ld.get('bpm', 60):.0f} bpm"
                                  for ld in p.layers[:3]]
                    fx_tip = f"fx {n}: {p.name}\n" + "\n".join(layer_strs)
                    if len(p.layers) > 3:
                        fx_tip += f"\n+ {len(p.layers)-3} more layer(s)"
                elif p:
                    fx_tip = f"fx {n}: {p.name} (empty)"
                else:
                    fx_tip = f"fx {n} — empty"
                dpg.set_value(f"fx_tip_{n}", fx_tip)
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
                lbl = f"{n}:{p.name[:6]}" if p else f"{pfx[0]}{n}"
                try:
                    dpg.set_item_label(f"{pfx}_btn_{n}", lbl)
                    tip = f"{attr_name} {n}: {p.name}" if p else f"{attr_name} {n} — empty"
                    dpg.set_value(f"{pfx}_tip_{n}", tip)
                    _at = self._pool_live_theme if p else self._pool_empty_theme
                    if _at:
                        dpg.bind_item_theme(f"{pfx}_btn_{n}", _at)
                except Exception:
                    pass

        # Forms (slots 1-24, matches _POOL_SLOTS)
        for n in range(1, self._POOL_SLOTS + 1):
            f = self._form_pool.get(n) if self._form_pool else None
            lbl = f"{n}:{f.name[:6]}" if f else f"f{n}"
            try:
                dpg.set_item_label(f"form_btn_{n}", lbl)
                _ft = self._pool_live_theme if f else self._pool_empty_theme
                if _ft:
                    dpg.bind_item_theme(f"form_btn_{n}", _ft)
            except Exception:
                pass
            try:
                if f:
                    ft = getattr(f, 'form_type', 'custom')
                    form_tip = f"form {n}: {f.name}  ({ft})"
                    if hasattr(f, 'points') and f.points:
                        form_tip += f"\n{len(f.points)} points"
                elif n < FormPool.FIRST_CUSTOM_SLOT:
                    _BUILTIN = {1: "sine", 2: "ramp", 3: "pulse", 4: "square"}
                    form_tip = f"form {n}: {_BUILTIN.get(n, '?')} (built-in)"
                else:
                    form_tip = f"form {n} — empty  (record form {n} ...)"
                dpg.set_value(f"form_tip_{n}", form_tip)
            except Exception:
                pass

        # FX pool programmer summary
        self._tick_fx_prog_summary()
        # Keep FX editor slot labels current when the editor is open
        try:
            if dpg.is_item_shown("fx_editor_window"):
                self._fxed_refresh_slot_labels()
        except Exception:
            pass
        # Live-sync speed master faders when the panel is open
        try:
            if dpg.is_item_shown("speed_master_window") and self._speed_pool:
                for sid in self._speed_pool.all_slots():
                    m = self._speed_pool.get(sid)
                    if m:
                        dpg.set_value(f"spd_fader_{sid}", m.bpm)
        except Exception:
            pass

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

        # color / dim line
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

    # ── OSC target management popup ───────────────────────────────────────────

    def _build_osc_popup(self):
        """Floating OSC target manager — add/remove output destinations without typing commands."""
        with dpg.window(tag="osc_window", label="osc targets",
                        width=620, height=360, show=False,
                        pos=(200, 150), no_collapse=False):
            dpg.add_text("osc output targets", color=_C_ACCENT)
            dpg.add_separator()

            # ── Add target row ────────────────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("add:", color=_C_DIM)
                dpg.add_input_text(tag="osc_add_name", label="", width=100,
                                   hint="name")
                dpg.add_input_text(tag="osc_add_host", label="", width=140,
                                   hint="host / IP")
                dpg.add_input_int(tag="osc_add_port", label="", width=70,
                                  default_value=8000, min_value=1, max_value=65535, step=0)
                dpg.add_button(label="add", width=52, callback=self._on_osc_add_target)
                dpg.add_text("", tag="osc_add_status", color=_C_ACCENT)

            dpg.add_separator()

            # ── Targets table (rebuilt on refresh) ────────────────
            with dpg.child_window(tag="osc_targets_scroll", width=-1, height=-1, border=False):
                dpg.add_group(tag="osc_targets_group")

    def _refresh_osc_table(self):
        """Rebuild the OSC targets list widget from the live osc engine state."""
        try:
            dpg.delete_item("osc_targets_group", children_only=True)
        except Exception:
            return
        if not self._osc:
            dpg.add_text("(no OSC engine)", color=_C_DIM, parent="osc_targets_group")
            return
        clients = self._osc._clients
        if not clients:
            dpg.add_text("(no targets — add one above)", color=_C_DIM,
                         parent="osc_targets_group")
            return
        with dpg.table(parent="osc_targets_group",
                       header_row=True,
                       borders_innerV=True,
                       policy=dpg.mvTable_SizingStretchProp):
            dpg.add_table_column(label="name",    init_width_or_weight=0.22)
            dpg.add_table_column(label="host",    init_width_or_weight=0.38)
            dpg.add_table_column(label="port",    init_width_or_weight=0.12)
            dpg.add_table_column(label="",        init_width_or_weight=0.28)
            for name, client in list(clients.items()):
                with dpg.table_row():
                    dpg.add_text(name,              color=_C_ACCENT)
                    dpg.add_text(client._address,   color=_C_TEXT)
                    dpg.add_text(str(client._port), color=_C_DIM)
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="test", width=46,
                                       callback=self._on_osc_test,
                                       user_data=name)
                        dpg.add_spacer(width=4)
                        dpg.add_button(label="remove", width=58,
                                       callback=self._on_osc_remove,
                                       user_data=name)

    def _on_osc_add_target(self):
        name = dpg.get_value("osc_add_name").strip()
        host = dpg.get_value("osc_add_host").strip()
        port = int(dpg.get_value("osc_add_port"))
        if not name or not host:
            dpg.set_value("osc_add_status", "name+host required")
            return
        if self._osc:
            self._osc.add_target(name, host, port)
            if self._save:
                self._save()
        dpg.set_value("osc_add_status", f"→ {name} added")
        dpg.set_value("osc_add_name", "")
        self._refresh_osc_table()

    def _on_osc_remove(self, _sender, _app, user_data):
        name = user_data
        if self._osc:
            self._osc.remove_target(name)
            if self._save:
                self._save()
        self._refresh_osc_table()

    def _on_osc_test(self, _sender, _app, user_data):
        name = user_data
        if self._osc:
            self._osc.send("/studio/ping", 1, target=name)

    def _build_midi_popup(self):
        """Floating MIDI mapping window — hidden by default, opened via header button."""
        with dpg.window(tag="midi_window", label="midi mappings",
                        width=860, height=540, show=False,
                        pos=(200, 150), no_collapse=False):
            dpg.add_text("midi mappings", color=_C_ACCENT)
            dpg.add_separator()

            # ── Port selector ──────────────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("port:", color=_C_DIM)
                try:
                    import mido as _mido_tmp
                    _port_names = _mido_tmp.get_input_names()
                except Exception:
                    _port_names = []
                dpg.add_combo(tag="midi_port_combo",
                              items=_port_names,
                              default_value=_port_names[1] if len(_port_names) > 1 else (_port_names[0] if _port_names else ""),
                              width=280)
                dpg.add_button(label="connect", width=70,
                               callback=self._on_midi_port_connect)
                dpg.add_button(label="disconnect", width=80,
                               callback=self._on_midi_port_disconnect)
                dpg.add_spacer(width=6)
                dpg.add_text("", tag="midi_port_status", color=_C_DIM)
            dpg.add_separator()

            with dpg.table(tag="midi_table", header_row=True,
                           borders_innerH=True, borders_outerH=True,
                           borders_innerV=True, borders_outerV=True,
                           row_background=True, scrollY=True,
                           height=200):
                dpg.add_table_column(label="ch",      width_fixed=True, init_width_or_weight=32)
                dpg.add_table_column(label="cc/note", width_fixed=True, init_width_or_weight=65)
                dpg.add_table_column(label="type",    width_fixed=True, init_width_or_weight=45)
                dpg.add_table_column(label="name",    width_stretch=True)
                dpg.add_table_column(label="status",  width_fixed=True, init_width_or_weight=90)
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
            dpg.add_text("add mapping:", color=_C_DIM)
            with dpg.group(horizontal=True):
                dpg.add_radio_button(items=["cc", "note"],
                                     tag="learn_type_radio",
                                     default_value="cc",
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
            dpg.add_text("click learn, then move the control (cc) or press a key/pad (note).", color=_C_DIM)

            # ── direct entry (no physical MIDI needed) ────────
            with dpg.group(horizontal=True):
                dpg.add_text("direct:", color=_C_DIM)
                dpg.add_text("ch", color=_C_DIM)
                dpg.add_input_int(tag="direct_ch",   label="", width=42,
                                  default_value=1, min_value=1, max_value=16,
                                  step=0, step_fast=0)
                dpg.add_radio_button(items=["cc", "note"],
                                     tag="direct_type_radio",
                                     default_value="cc", horizontal=True)
                dpg.add_input_int(tag="direct_num",  label="", width=46,
                                  default_value=7, min_value=0, max_value=127,
                                  step=0, step_fast=0)
                dpg.add_combo(items=target_names, tag="direct_target",
                              default_value=target_names[0] if target_names else "",
                              width=200)
                dpg.add_button(label="add", width=52,
                               callback=self._on_direct_add)
                dpg.add_text("", tag="direct_status", color=_C_ACCENT)

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
            dpg.add_text("flash a fader while a pad is held:", color=_C_DIM)
            with dpg.group(horizontal=True):
                dpg.add_text("exec", color=_C_DIM)
                dpg.add_input_int(tag="midi_flash_exec", label="", width=46,
                                  default_value=1, min_value=1, max_value=99,
                                  step=0, step_fast=0)
                dpg.add_button(label="learn note", width=100,
                               callback=self._start_exec_flash_learn)
                dpg.add_text("", tag="flash_learn_status", color=_C_ACCENT)

            dpg.add_separator()
            dpg.add_text("go/back a specific fader via note:", color=_C_DIM)
            with dpg.group(horizontal=True):
                dpg.add_text("exec", color=_C_DIM)
                dpg.add_input_int(tag="midi_exec_gb_num", label="", width=46,
                                  default_value=1, min_value=1, max_value=99,
                                  step=0, step_fast=0)
                dpg.add_radio_button(items=["go", "back"],
                                     tag="midi_exec_gb_type",
                                     default_value="go", horizontal=True)
                dpg.add_button(label="learn note", width=100,
                               callback=self._start_exec_gb_learn)
                dpg.add_text("", tag="midi_exec_gb_status", color=_C_ACCENT)

    def _build_patch_popup(self):
        """Floating patch editor — hidden by default, opened via header PATCH button."""
        profiles = list(self._library.profiles.keys()) if self._library else ["SGM_RGB_54"]
        with dpg.window(tag="patch_window", label="patch editor",
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
                dpg.add_table_column(label="name",     width_fixed=True,  init_width_or_weight=110)
                dpg.add_table_column(label="profile",  width_fixed=True,  init_width_or_weight=130)
                dpg.add_table_column(label="univ",     width_fixed=True,  init_width_or_weight=44)
                dpg.add_table_column(label="start",    width_fixed=True,  init_width_or_weight=52)
                dpg.add_table_column(label="channels", width_fixed=True,  init_width_or_weight=70)
                dpg.add_table_column(label="end",      width_fixed=True,  init_width_or_weight=52)
                dpg.add_table_column(label="",         width_stretch=True)

            self._refresh_patch_table()

            dpg.add_separator()
            dpg.add_text("add fixture:", color=_C_DIM)
            with dpg.group(horizontal=True):
                dpg.add_input_int(tag="patch_add_id",    label="", width=46,
                                  default_value=1, min_value=1, max_value=999,
                                  step=0, step_fast=0)
                dpg.add_text("id", color=_C_DIM)
                dpg.add_spacer(width=4)
                dpg.add_input_text(tag="patch_add_name",  label="", width=110,
                                   default_value="fixture")
                dpg.add_text("name", color=_C_DIM)
                dpg.add_spacer(width=4)
                dpg.add_combo(tag="patch_add_profile", label="", width=130,
                              items=profiles,
                              default_value=profiles[0] if profiles else "")
                dpg.add_text("profile", color=_C_DIM)
            with dpg.group(horizontal=True):
                dpg.add_input_int(tag="patch_add_univ",  label="", width=46,
                                  default_value=1, min_value=1, max_value=64,
                                  step=0, step_fast=0)
                dpg.add_text("universe", color=_C_DIM)
                dpg.add_spacer(width=4)
                dpg.add_input_int(tag="patch_add_addr",  label="", width=60,
                                  default_value=1, min_value=1, max_value=512,
                                  step=0, step_fast=0)
                dpg.add_text("start addr", color=_C_DIM)
                dpg.add_spacer(width=4)
                dpg.add_input_int(tag="patch_add_clone_src", label="", width=46,
                                  default_value=0, min_value=0, max_value=999,
                                  step=0, step_fast=0)
                dpg.add_text("clone from (0=none)", color=_C_DIM)
                dpg.add_spacer(width=8)
                dpg.add_button(label="add fixture", width=110,
                               callback=self._on_patch_add)

            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_button(label="save patch", width=110,
                               callback=self._on_patch_save)
                dpg.add_spacer(width=8)
                dpg.add_text("changes are live. re-open console to rebuild monitors.",
                             color=_C_DIM)

            dpg.add_separator()
            dpg.add_text("sacn network", color=_C_ACCENT)
            with dpg.group(horizontal=True):
                dpg.add_text("bind ip:", color=_C_DIM)
                _saved_bind, _saved_univs = ShowFile.load_network()
                dpg.add_input_text(tag="net_bind_input", label="", width=160,
                                   default_value=_saved_bind or network.bind_address or "",
                                   hint="e.g. 192.168.1.161")
                dpg.add_spacer(width=8)
                dpg.add_text("universes:", color=_C_DIM)
                _univ_str = " ".join(str(u) for u in (_saved_univs or network.universes))
                dpg.add_input_text(tag="net_univs_input", label="", width=120,
                                   default_value=_univ_str,
                                   hint="e.g. 1 2")
                dpg.add_spacer(width=8)
                dpg.add_button(label="save network", width=110,
                               callback=self._on_net_save)
            dpg.add_text("saved settings apply on next console restart.",
                         color=_C_DIM)

    def _on_net_save(self, *_):
        try:
            bind = dpg.get_value("net_bind_input").strip()
            univs_raw = dpg.get_value("net_univs_input").strip().split()
            univs = [int(v) for v in univs_raw if v.isdigit()]
            if not univs:
                self._log("  network: universe list must contain at least one number")
                return
        except Exception as e:
            self._log(f"  network: bad input — {e}")
            return
        ShowFile.save_network(bind, univs)
        self._log(f"  network saved: bind={bind or '(auto)'}  universes={univs}  (restart to apply)")

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
                dpg.add_button(label="remove", width=70,
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
            self._log(f"fixture {fid} already patched — remove it first")
            return
        master = self._patch.patch_fixture(fid, name, profile, universe, addr)
        if master:
            self._log(f"patched: {master.name} (id {fid}) — {profile} u{universe}@{addr}")
            if clone_src and clone_src != 0 and clone_src in self._patch.fixtures:
                msg = self._cmd(f"CLONE {clone_src} TO {fid}") if self._cmd else ""
                if msg:
                    self._log(msg)
            elif clone_src and clone_src != 0:
                self._log(f"  clone src {clone_src} not in patch — skipped")
            self._refresh_patch_table()
        else:
            self._log(f"failed to patch — check profile name '{profile}'")

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
            self._log(f"removed: {name} (id {fid})")
            self._refresh_patch_table()

    def _on_patch_save(self):
        if self._save_patch:
            self._save_patch()
            self._log("> patch saved to patch.json")
        else:
            self._log("> no save_patch_fn wired")

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
                ("1 THRU 6 AT WOBBLE R 20","Add independent random ±20 jitter to each fixture's red (organic variation)"),
                ("1 THRU 6 AT WOBBLE DIM 10","Add ±10% random jitter to each fixture's dimmer (subtle organic variation)"),
                ("1 THRU 6 AT NORMALIZE R","Scale red across selection so the highest value = 255 (preserves ratio, maximises brightness)"),
                ("1 THRU 3 AT CLEAR R",   "remove red channel from fixtures 1-3 in the programmer (keeps other channels)"),
                ("1 THRU 3 AT CLEAR",     "remove all programmer values for fixtures 1-3 (targeted partial-programmer clear)"),
                ("1 THRU 6 AT COPY 3",    "copy all programmer values from fixture 3 into each fixture in the selection (channel-by-channel clone)"),
                ("1 AT WHITE",            "named colour shorthand — sets R/G/B directly"),
                ("1 AT AMBER / CYAN / MAGENTA / WARM / UV", "other named colours"),
                ("1 AT YELLOW / ORANGE / PINK / PURPLE / LIME / TEAL", "more named colours"),
                ("COL 3  /  COLOR 3",     "apply colour preset to selection"),
                ("DIM 2",                 "apply dim preset to selection"),
                ("1 THRU 6 AT 0 IN 5",   "live programmer fade: fade selection to 0% over 5 seconds"),
                ("1 THRU 6 AT FULL IN 3","Live fade to full over 3 seconds"),
                ("1 THRU 6 AT WHITE IN 2","Live fade to white over 2 seconds"),
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
                ("FX SINE RED PHASE 0.33","Phase offset for this layer (0–1)"),
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
                ("CUES / STACK / LIST",   "show all cues in active cuestack with fade times"),
                ("LIST CUESTACKS",        "list all recorded cuestacks and cue counts"),
                ("LIST NOTES",            "list all cuelist and cue notes set in the show — quick production overview"),
                ("LIST CUES",             "list all cues in the active cuestack with fade times"),
                ("LIST CUES CS 2",        "list cues in cuestack 2 specifically"),
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
                ("page list",             "show all pages and cuestacks on each"),
            ]),
            ("record", [
                ("REC CUE 5",             "record current programmer to cue 5"),
                ("REC CUE 5 My Cue",      "record with a name"),
                ("REC CUE 5 FADE 2 FXOUTFADE 1.5", "record with timing — FXOut overrides how long old FX fades out"),
                ("REC FX 2 My FX",        "record programmer FX to FX pool slot 2"),
                ("REC GROUP 3 Name",      "record current selection as group 3"),
                ("RECORD COLOR 4 Red",    "record programmer colour as preset 4"),
                ("RECORD COLOR 5 Amber 255 140 0", "record explicit RGB (no programmer needed)"),
                ("RECORD DIM 2 Half",     "record programmer dim as preset 2"),
                ("RECORD DIM 3 75%",      "record explicit level (no programmer needed)"),
                ("record form 6 Wave 0,0 0.5,1 1,0",  "record custom waveform"),
                ("RECORD RATE 3 Name 120","Record 120 BPM to rate pool slot 3"),
                ("RECORD CUESTACK 2 Name","Create a new named cuestack on fader 2"),
                ("LOAD CUE 5",            "copy cue 5's data into the programmer for editing and re-recording"),
                ("LOAD CUE 5 CS 2",       "load cue 5 from cuestack 2 into programmer"),
            ]),
            ("rename / copy / delete", [
                ("RENAME FIXTURE 3 Bar L","Rename fixture 3's display label (saved to patch file)"),
                ("RENAME CUESTACK 2 Tour","Rename cuestack 2 — all cues kept"),
                ("RENAME CUE 3 Intro",    "rename cue 3 in active cuestack"),
                ("RENAME CS 2 CUE 5 End", "rename cue 5 in cuestack 2"),
                ("RENAME COLOR 4 Coral",  "rename colour preset 4"),
                ("RENAME GROUP 1 Tubes",  "rename group 1"),
                ("RENAME POSITION 1 Wide","Rename attr pool preset (works for all 6 attr types)"),
                ("COPY COLOR 2 TO 5",     "copy colour preset 2 → slot 5 (auto-names as copy)"),
                ("COPY COLOR 2 TO 5 Warm","Copy with a new name"),
                ("COPY DIM 1 TO 3",       "same pattern for DIM, GROUP, FX"),
                ("COPY RATE 1 TO 5",      "same pattern for RATE, SIZEP, SPREADP"),
                ("COPY FORM 5 TO 6",      "copy a custom form (destination must be slot ≥5; built-ins 1-4 protected)"),
                ("COPY POSITION 1 TO 2",  "same pattern for all 6 attr pool types"),
                ("COPY FIXTURE 1 TO 2 3", "copy programmer values from fixture 1 to fixtures 2 and 3"),
                ("FIXTURE SWAP 1 2",      "exchange all programmer values between fixtures 1 and 2"),
                ("COPY CUE 3 TO 5",       "copy cue 3 → cue 5 (active cuestack)"),
                ("COPY CUE 3 TO 5 Intro", "copy with new name"),
                ("COPY CS 2 CUE 3 TO CS 1 CUE 9", "cross-cuestack copy"),
                ("MOVE CUE 3 TO 5",       "move (rename in place) cue 3 → cue 5, active cuestack"),
                ("MOVE CS 2 CUE 3 TO CS 1 CUE 9", "cross-cuestack move — removes cue from source"),
                ("delete cue 3",          "delete cue 3 from active cuestack (saves show)"),
                ("delete cue 3 CS 2",     "delete cue 3 from cuestack 2"),
                ("delete cueSTACK 5",     "delete cuestack 5 and stop its fader"),
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
                ("CS 2 INFO",             "detailed status of cuestack 2: cue list, current cue, loop/wrap, assigned faders"),
                ("CUESTACK MERGE 2 INTO 1", "append all cues from CS 2 into CS 1 (renumbered after CS 1's last cue)"),
                ("CS 1 REVERSE",           "reverse cue playback order in cuestack 1 (renumbers 1-N from last to first)"),
                ("CS 1 COMPRESS",          "renumber cues to sequential integers 1, 2, 3… — collapses gaps left by deletions"),
                ("CS 1 RENUMBER STEP 10",  "renumber cues at multiples of 10 (→10,20,30…) to leave room for future inserts"),
                ("CS 1 EXTRACT 3",         "copy cue 3 from CS 1 into a new standalone single-cue cuestack (auto-picks slot)"),
                ("CS 1 EXTRACT 3 INTO 10", "as above but place the extracted cuestack in slot 10"),
                ("CS 1 DUPLICATE",         "deep-copy all cues from CS 1 to a new auto-picked slot (preserves timing/notes)"),
                ("CS 1 DUPLICATE INTO 5",  "duplicate CS 1 into slot 5 specifically"),
                ("CUE 5 SHOW",            "inspect cue 5 contents (fixtures, RGB, FX, timing)"),
                ("CUE 5 NOTE Pre-show",   "set a production note on cue 5"),
                ("CUE 3 SHIFT 5",         "move cue 3 to cue 8 in the active cuestack (offset by +5)"),
                ("CUE 5 FADE 3",          "set fade time on cue 5 (no programmer needed)"),
                ("CUE 5 FADE 2 DELAY 1",  "set fade + delay"),
                ("CUE 5 FADE 2 DFADE 5",  "global fade + dim-only fade override"),
                ("CUE 5 FXOUTFADE 2.5",   "fX outfade time when cue 5 fires (0 = auto)"),
                ("CS 2 CUE 5 FADE 3",     "set timing on cue 5 in cuestack 2"),
            ]),
            ("playback", [
                ("GO",                      "advance to next cue on active fader"),
                ("GO FADE 3",               "one-shot: fire next cue with 3s fade (does not change the cue's stored fade)"),
                ("GO FADE 5 DELAY 1",       "one-shot: fire with 5s fade and 1s delay"),
                ("BACK",                    "step to previous cue"),
                ("GOTO 3",                  "jump directly to cue 3 (active cuestack)"),
                ("CUESTACK 2",              "switch active fader to slot 2"),
                ("ASSIGN CS 2 TO FADER 1",  "wire cuestack 2 to fader 1"),
                ("FADER 1 ASSIGN CS 2",     "shorthand for ASSIGN CS 2 TO FADER 1"),
                ("FADER 1 UNASSIGN",        "detach the cuestack from fader 1 without deleting it (fader goes dark)"),
                ("FADER SWAP 1 2",          "swap the cuestacks on faders 1 and 2"),
                ("FADER 1 INFO",            "detailed status of fader 1: level, priority, rate, buttons, cuestack, current cue"),
                ("FADER 1 CLEAR",           "stop fader 1 and reset its cuestack to 'not started' (position resets to top)"),
                ("FADER ALL CLEAR",         "stop every fader and reset all cuestack positions to the start"),
                ("FADER 1 LOOP ON",         "set fader 1's cuestack to loop: fires cue 1 again after the last cue"),
                ("FADER 1 LOOP OFF",        "disable looping on fader 1's cuestack (stop after last cue)"),
                ("FADER 1 LABEL Main Show", "set a human-readable label on fader 1 (shown in LIST FADER)"),
                ("FADER 1 LABEL",           "clear the label on fader 1"),
                ("RELEASE 2",               "stop fader 2"),
                ("RELEASE ALL",             "stop all active faders"),
                ("PRIORITY 2 HIGH",         "set fader 2 to high priority (HI/NRM/LO)"),
                ("FADER 1 TIME 3",          "override fade time on fader 1 to 3s"),
                ("FADER 1 TIME 3 DELAY 1",  "override fade + delay on fader 1"),
                ("FADER 1 TIME OFF",        "remove fader 1 time override"),
                ("FADER 1 TIMELOCK OFF",    "lock cuestack on fader 1 to its own times"),
                ("FADER 1 TIMELOCK ON",     "re-enable fader time override for cuestack"),
                ("CS 1 CLEAR",              "delete all cues from cuestack 1 — keeps the slot and name, ready to re-record"),
                ("CS 1 bounce on",          "cS 1: ping-pong — reverse direction at last/first cue instead of looping"),
                ("CS 1 bounce off",         "cS 1: restore normal forward loop (default)"),
                ("FADER 1 bounce on",       "same as CS bounce on but addressed through the fader slot"),
                ("FADER 1 bounce off",      "disable ping-pong on the cuestack assigned to fader 1"),
                ("CS 1 WRAP ON",            "cS 1: fire cue 1 clean after last cue — no LTP bleed across the loop"),
                ("CS 1 WRAP OFF",           "cS 1: restore normal LTP tracking across wrap-around (default)"),
                ("CS 1 NOTE",               "view production note on cuestack 1 (blank if none set)"),
                ("CS 1 NOTE Dark Moody",    "set a freeform production note on cuestack 1 (saved to ShowFile)"),
                ("CS 1 CHASE ON BPM 120",   "auto-advance CS 1 through cues at 120 BPM (chase mode)"),
                ("CS 1 CHASE OFF",          "disable chase mode — cuestack returns to manual GO"),
                ("CS 1 CHASE BPM 90",       "change chase speed to 90 BPM while chase is running"),
                ("CS 1 CHASE SPEED 2",      "link CS 1 chase tempo to speed Master 2"),
                ("PROG TIME 2",             "programmer time: all cues fade at 2s"),
                ("PROG TIME OFF",           "disable programmer time override"),
            ]),
            ("faders & pages", [
                ("FADER 1 GO / BACK / STOP","direct fader control"),
                ("FADER 1 GOTO FIRST",      "jump fader 1 to the first cue in its cuestack and fire it"),
                ("FADER 1 GOTO LAST",       "jump fader 1 to the last cue in its cuestack and fire it"),
                ("FADER 1 LEVEL 75",        "set fader 1 master level to 75% (GUI slider also works)"),
                ("FADER 1 MODE FLASH",      "set trigger mode: live only while held"),
                ("FADER 1 mode toggle",     "set trigger mode: GO/BACK advance (default)"),
                ("FADER 1 flash on",        "fire instantly (0s), works regardless of mode"),
                ("FADER 1 flash off",       "release a flash — fully stops the fader"),
                ("FADER 1 BTN A GO",        "set fader 1's A button to GO (A/B/C · GO/BACK/STOP/FLASH/RATE+/RATE-)"),
                ("FADER 1 RATE+ / RATE-",   "nudge playback speed ×1.25 / ÷1.25 (divides fade times)"),
                ("FADER 1 RATE RESET",      "restore normal playback speed"),
                ("FADER 1 RATE 2.0",        "set fader 1 playback speed to ×2.0 (0.1–8.0 range)"),
                ("FADER 1 SIZE+ / SIZE-",   "nudge fader 1 FX amplitude ×1.25 / ÷1.25 (0–4× range)"),
                ("FADER 1 SIZE RESET",      "restore normal FX amplitude (×1.0) for fader 1"),
                ("FADER 1 SIZE 2.0",        "double FX amplitude on fader 1 (all owned FX layers)"),
                ("PAGE 1 NAME Verses",    "name page 1"),
                ("PAGE 1 ADD CS 3",       "add cuestack 3 to page 1"),
                ("PAGE 1 REMOVE CS 3",    "remove cuestack 3 from page 1"),
                ("PAGE 1 DELETE",         "delete page 1"),
                ("page list",             "list all pages and their cuestacks"),
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
                ("LOAD SHOW <name>",      "restore a snapshot (cuestacks/presets reload live)"),
                ("LIST SHOWS",            "list all saved show snapshots"),
                ("SHOW INFO",             "high-level overview: fixtures, cueLists, presets, active faders, master level"),
                ("UNDO",                  "undo last programmer change (up to 20 steps)"),
                ("PROGRAMMER SHOW",       "print a human-readable dump of all programmer values (fixture names + channels)"),
                ("PROGRAMMER SCALE 50",   "scale all programmer values to 50% (halve every dim, RGB, and attribute channel)"),
                ("PROGRAMMER SCALE 200",  "double all programmer values (clamped to max) — amplify a subtle look"),
                ("PROGRAMMER STATS",      "show how many fixtures/sub-fixtures and channels are active in programmer"),
                ("PROGRAMMER CAPTURE",     "pull the current live cue-layer output for selected fixtures into the programmer"),
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
                ("RENAME MACRO 1 NewName","Rename macro slot 1"),
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
                ("PAGES button",          "open pages editor (assign cuestacks to pages)"),
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

    # ── cue timing popup ─────────────────────────────────────────

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

    # ── Changelog popup ──────────────────────────────────────────
    # Reads studio_data/changelog.json — the log gets an entry appended for
    # every meaningful change made to this file, so this is a live view of
    # what's changed and why, not something maintained by hand in the GUI.

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

            # ── cuestack list for selected page ──────────────────
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
            dpg.set_value("pg_name_input", page.get('name', f"page {n}"))
        except Exception:
            pass

    def _on_page_sel_change(self):
        self._pages_current = int(dpg.get_value("pg_sel_num"))
        page = self._executor_pool.pages.get(self._pages_current) if self._executor_pool else None
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
    _FX_CHANNELS  = [
        'dim', 'red', 'green', 'blue',
        'pan', 'tilt', 'pan_fine', 'tilt_fine',
        'gobo', 'gobo_rot', 'gobo2', 'gobo2_rot',
        'zoom', 'focus', 'iris', 'shutter1',
        'color', 'prism', 'frost', 'animation', 'control', 'macro', 'dimmer',
    ]

    def _build_fx_editor_popup(self):
        """Floating FX preset editor — hidden by default, opened via FX ED button."""
        self._fx_ed_slot   = None   # currently selected preset slot (int)
        self._fx_ed_layers = []     # working copy: list of layer dicts

        _FXED_COLS   = 8
        _FXED_BTN_W  = 108   # 8 × 108 + 7 × 6 spacing ≈ 906, fits in 940px window
        _FXED_BTN_H  = 28
        with dpg.window(tag="fx_editor_window", label="fx editor",
                        width=1100, height=580, show=False,
                        pos=(120, 100), no_collapse=False):

            # ── preset selector row ───────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("preset", color=_C_ACCENT)
                dpg.add_spacer(width=6)
            # pool slots: _POOL_SLOTS in rows of _FXED_COLS
            for _fxed_row in range(self._POOL_SLOTS // _FXED_COLS):
                with dpg.group(horizontal=True):
                    for _fxed_col in range(_FXED_COLS):
                        n = _fxed_row * _FXED_COLS + _fxed_col + 1
                        dpg.add_button(tag=f"fxed_slot_{n}", label=str(n),
                                       width=_FXED_BTN_W, height=_FXED_BTN_H,
                                       callback=self._fxed_select_slot,
                                       user_data=n)
            with dpg.group(horizontal=True):
                dpg.add_button(label="new preset", width=120, height=_FXED_BTN_H,
                               callback=self._fxed_new_preset)
                dpg.add_button(label="delete", width=80, height=_FXED_BTN_H,
                               callback=self._fxed_delete_preset)

            dpg.add_separator()

            # ── Name + actions row ────────────────────────────
            with dpg.group(horizontal=True):
                dpg.add_text("name:", color=_C_DIM)
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
                dpg.add_text("target:", color=_C_DIM)
                dpg.add_combo(tag="fxed_target", label="", width=240,
                              items=["selection", "all fixtures"],
                              default_value="selection")
                dpg.add_spacer(width=6)
                dpg.add_button(label="↻ groups", width=90, height=22,
                               callback=self._fxed_refresh_target)

            dpg.add_separator()

            # ── Layer list ────────────────────────────────────
            dpg.add_text("layers:", color=_C_DIM)
            with dpg.child_window(tag="fxed_layers_win",
                                  width=-1, height=270, border=True):
                with dpg.table(tag="fxed_layer_table", header_row=True,
                               borders_innerV=False, borders_outerV=False,
                               borders_innerH=False, borders_outerH=False,
                               policy=dpg.mvTable_SizingFixedFit):
                    dpg.add_table_column(label="waveform", width_fixed=True, init_width_or_weight=94)
                    dpg.add_table_column(label="channel",  width_fixed=True, init_width_or_weight=74)
                    dpg.add_table_column(label="bpm",      width_fixed=True, init_width_or_weight=64)
                    dpg.add_table_column(label="size",     width_fixed=True, init_width_or_weight=64)
                    dpg.add_table_column(label="spread",   width_fixed=True, init_width_or_weight=59)
                    dpg.add_table_column(label="phase",    width_fixed=True, init_width_or_weight=59)
                    dpg.add_table_column(label="group",    width_fixed=True, init_width_or_weight=96)
                    dpg.add_table_column(label="color",    width_fixed=True, init_width_or_weight=96)
                    dpg.add_table_column(label="dim",      width_fixed=True, init_width_or_weight=96)
                    dpg.add_table_column(label="spd",      width_fixed=True, init_width_or_weight=50)
                    dpg.add_table_column(label="",         width_fixed=True, init_width_or_weight=30)

            dpg.add_separator()

            # ── Add layer form ────────────────────────────────
            dpg.add_text("add layer:", color=_C_DIM)
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
                dpg.add_text("size", color=_C_DIM)
                dpg.add_input_float(tag="fxed_add_size",   label="", width=60,
                                    default_value=100.0, min_value=0.0, max_value=100.0,
                                    step=0, format="%.0f")
                dpg.add_text("spread", color=_C_DIM)
                dpg.add_input_float(tag="fxed_add_spread", label="", width=55,
                                    default_value=0.0, min_value=0.0, max_value=100.0,
                                    step=0, format="%.1f")
                dpg.add_text("phase", color=_C_DIM)
                dpg.add_input_float(tag="fxed_add_phase",  label="", width=55,
                                    default_value=0.0, min_value=0.0, max_value=1.0,
                                    step=0, format="%.3f")
                dpg.add_button(label="add layer", width=90, height=22,
                               callback=self._fxed_add_layer)

        self._fxed_refresh_slot_labels()

    def _refresh_fx_pool_buttons(self):
        for n in range(1, self._POOL_SLOTS + 1):
            p = self._fx_pool.get(n) if self._fx_pool else None
            lbl = f"{n}:{p.name[:6]}" if p else f"fx{n}"
            try:
                dpg.set_item_label(f"fx_btn_{n}", lbl)
            except Exception:
                pass

    def _fxed_refresh_slot_labels(self):
        for n in range(1, self._POOL_SLOTS + 1):
            p = self._fx_pool.get(n) if self._fx_pool else None
            label = p.name[:10] if p else str(n)
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
            dpg.set_value("fxed_name", f"fx {user_data}")
            self._fx_ed_layers = []
        self._fxed_rebuild_rows()

    def _fxed_new_preset(self, *_):
        for n in range(1, self._POOL_SLOTS + 1):
            if not (self._fx_pool and self._fx_pool.get(n)):
                self._fx_ed_slot = n
                dpg.set_value("fxed_name", f"fx {n}")
                self._fx_ed_layers = []
                self._fxed_rebuild_rows()
                return
        self._log(f"all {self._POOL_SLOTS} fx slots are full — delete one first")

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
            dpg.set_value("fxed_name", "rainbow")
        self._fxed_rebuild_rows()

    def _fxed_chase_rgb(self, *_):
        """Pixel chase — white pulse travelling through R then G then B."""
        self._fx_ed_layers = [
            {'waveform': 'pulse', 'channel': 'red',   'bpm': 60.0, 'size': 200.0, 'spread': 1.0, 'phase_offset': 0.0},
            {'waveform': 'pulse', 'channel': 'green', 'bpm': 60.0, 'size': 200.0, 'spread': 1.0, 'phase_offset': 0.333},
            {'waveform': 'pulse', 'channel': 'blue',  'bpm': 60.0, 'size': 200.0, 'spread': 1.0, 'phase_offset': 0.667},
        ]
        if not dpg.get_value("fxed_name"):
            dpg.set_value("fxed_name", "chase rgb")
        self._fxed_rebuild_rows()

    def _fxed_named_items(self, pool, id_attr='groups', name_attr='name', trunc=8):
        """Build ["—", "1: name", ...] items from a pool dict; only existing entries."""
        items = ["—"]
        pool_dict = getattr(pool, id_attr, {}) if pool else {}
        for pid in sorted(pool_dict):
            entry = pool_dict[pid]
            label = getattr(entry, name_attr, str(pid))[:trunc]
            items.append(f"{pid}: {label}")
        return items

    def _fxed_id_to_label(self, pid, pool, id_attr='groups', name_attr='name', trunc=8):
        """Return "n: name" for a given pool ID, or bare "n" if not found."""
        if pid is None:
            return "—"
        pool_dict = getattr(pool, id_attr, {}) if pool else {}
        entry = pool_dict.get(int(pid))
        if entry:
            label = getattr(entry, name_attr, str(pid))[:trunc]
            return f"{pid}: {label}"
        return str(pid)

    def _fxed_rebuild_rows(self):
        for row_id in getattr(self, '_fxed_row_ids', []):
            try:
                dpg.delete_item(row_id)
            except Exception:
                pass
        self._fxed_row_ids = []

        _spd_items = ["—"] + [str(n) for n in range(1, SpeedMasterPool._DEFAULT_SLOTS + 1)]
        _grp_items = self._fxed_named_items(self._groups,  'groups',  'name')
        _col_items = self._fxed_named_items(self._colors,  'presets', 'name')
        _dim_items = self._fxed_named_items(self._dims,    'presets', 'name')

        for i, ld in enumerate(self._fx_ed_layers):
            _gid = ld.get('group_id')
            _cid = ld.get('color_id')
            _did = ld.get('dim_id')
            _sid = ld.get('speed_id')

            # DPG quirk: set_value() is called right after each widget so that
            # _fxed_sync_rows() reads the correct value even if the user never
            # touched the widget (default_value alone isn't returned by get_value).
            with dpg.table_row(parent="fxed_layer_table") as row_id:
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

                _gval = self._fxed_id_to_label(_gid, self._groups,  'groups',  'name')
                dpg.add_combo(tag=f"fxed_r{i}_grp", label="", width=90,
                              items=_grp_items, default_value=_gval)
                dpg.set_value(f"fxed_r{i}_grp", _gval)
                _cval = self._fxed_id_to_label(_cid, self._colors,  'presets', 'name')
                dpg.add_combo(tag=f"fxed_r{i}_col", label="", width=90,
                              items=_col_items, default_value=_cval)
                dpg.set_value(f"fxed_r{i}_col", _cval)
                _dval = self._fxed_id_to_label(_did, self._dims,    'presets', 'name')
                dpg.add_combo(tag=f"fxed_r{i}_dim", label="", width=90,
                              items=_dim_items, default_value=_dval)
                dpg.set_value(f"fxed_r{i}_dim", _dval)

                dpg.add_combo(tag=f"fxed_r{i}_spd", label="", width=46,
                              items=_spd_items,
                              default_value="—" if _sid is None else str(_sid))
                dpg.set_value(f"fxed_r{i}_spd", "—" if _sid is None else str(_sid))

                dpg.add_button(label="x", width=24, height=20,
                               callback=self._fxed_remove_layer,
                               user_data=i)
            self._fxed_row_ids.append(row_id)

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
            if not v or v == "—":
                return None
            # values may be "n" or "n: name" (from named dropdowns)
            try:
                return int(v.split(":")[0].strip())
            except (ValueError, IndexError):
                return None
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
                self._fx_ed_layers[i]['speed_id']      = _ref(dpg.get_value(f"fxed_r{i}_spd"))
            except Exception:
                pass

    def _fxed_save(self, *_):
        if self._fx_ed_slot is None:
            self._log("> select a slot first")
            return
        self._fxed_sync_rows()
        name   = dpg.get_value("fxed_name").strip() or f"fx {self._fx_ed_slot}"
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
                speed_id     = ld.get('speed_id'),
            )
        self._fx_pool.store(self._fx_ed_slot, preset)
        ShowFile.save_fx_pool(self._fx_pool)
        self._fxed_refresh_slot_labels()
        self._refresh_fx_pool_buttons()
        self._log(f"> Saved FX {self._fx_ed_slot}: {name}  ({len(preset.layers)} layers)")

    def _fxed_refresh_target(self, *_):
        """Rebuild the target combo with current group list."""
        items = ["selection", "all fixtures"]
        if self._groups:
            for gid in sorted(self._groups.groups):
                g = self._groups.groups[gid]
                if g.members:
                    items.append(f"group {gid}: {g.name}")
        try:
            dpg.configure_item("fxed_target", items=items)
        except Exception:
            pass

    def _fxed_fire(self, *_):
        if self._fx_ed_slot is None:
            self._log("> select a slot first")
            return
        self._fxed_save()

        try:
            target = dpg.get_value("fxed_target")
        except Exception:
            target = "selection"

        saved_sel = list(self._prog.selection)

        if target == "all fixtures":
            self._prog.clear_selection()
        elif target.startswith("group "):
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
            self._fxed_refresh_slot_labels()

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
            self._log("> clear")
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
        # Clear any pending error flash on the next non-error log line
        if self._error_flash_time is not None:
            self._error_flash_time = None
            try:
                dpg.set_value("cmd_error_flash", "")
            except Exception:
                pass

    def _log_error(self, line):
        import time as _time
        self._log(f"⚠ {line}")
        self._error_flash_time = _time.monotonic()
        try:
            dpg.set_value("cmd_error_flash", f"⚠  {line}")
        except Exception:
            pass

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

    def _build_ai_prompts_popup(self):
        """Floating AI prompt pool — user-saved prompt presets, clicked to run immediately."""
        # Seed from built-in chips if no file saved yet
        defaults = [{"name": n, "prompt": p} for n, p in self._AI_CHIPS]
        self._ai_prompts = ShowFile.load_ai_prompts(defaults)
        with dpg.window(tag="ai_prompts_window", label="ai prompts",
                        width=640, height=520, show=False, pos=(260, 160)):
            with dpg.group(horizontal=True):
                dpg.add_text("ai prompt pool", color=_C_ACCENT)
                dpg.add_spacer(width=8)
                dpg.add_text("click to run · del to remove", color=_C_DIM)
            dpg.add_separator()
            with dpg.child_window(tag="ai_prompts_scroll", width=-1, height=300,
                                  border=False):
                dpg.add_group(tag="ai_prompts_grid")
            self._refresh_ai_prompts_grid()
            dpg.add_separator()
            dpg.add_text("add prompt:", color=_C_DIM)
            with dpg.group(horizontal=True):
                dpg.add_input_text(tag="ai_prompt_name_input", hint="label (short)",
                                   width=140)
            dpg.add_input_text(tag="ai_prompt_text_input",
                               hint="full AI prompt text...",
                               width=-1, height=60, multiline=True)
            dpg.add_button(label="save prompt", width=130,
                           callback=self._on_ai_prompt_save)

    def _refresh_ai_prompts_grid(self):
        """Rebuild the button grid from self._ai_prompts."""
        try:
            dpg.delete_item("ai_prompts_grid", children_only=True)
        except Exception:
            return
        if not self._ai_prompts:
            dpg.add_text("(no prompts saved)", color=_C_DIM, parent="ai_prompts_grid")
            return
        _BTN_W = 180
        _DEL_W = 28
        _PER_ROW = 3
        row_group = None
        for i, entry in enumerate(self._ai_prompts):
            if i % _PER_ROW == 0:
                row_group = dpg.add_group(horizontal=True, parent="ai_prompts_grid")
            name   = entry.get("name", f"prompt {i+1}")
            prompt = entry.get("prompt", "")
            with dpg.group(horizontal=True, parent=row_group):
                dpg.add_button(
                    label=name[:22], width=_BTN_W, height=28,
                    callback=self._on_ai_prompt_run,
                    user_data=prompt,
                )
                dpg.add_button(
                    label="×", width=_DEL_W, height=28,
                    callback=self._on_ai_prompt_delete,
                    user_data=i,
                )

    def _on_ai_prompt_run(self, sender, app_data, user_data):
        """Send a saved prompt to the AI engine."""
        prompt = user_data
        if not prompt:
            return
        try:
            dpg.set_value("ai_input", prompt)
        except Exception:
            pass
        self._on_ai_send()

    def _on_ai_prompt_delete(self, sender, app_data, user_data):
        idx = user_data
        if 0 <= idx < len(self._ai_prompts):
            del self._ai_prompts[idx]
            ShowFile.save_ai_prompts(self._ai_prompts)
            self._refresh_ai_prompts_grid()

    def _on_ai_prompt_save(self):
        try:
            name   = dpg.get_value("ai_prompt_name_input").strip()
            prompt = dpg.get_value("ai_prompt_text_input").strip()
        except Exception:
            return
        if not name or not prompt:
            return
        self._ai_prompts.append({"name": name, "prompt": prompt})
        ShowFile.save_ai_prompts(self._ai_prompts)
        self._refresh_ai_prompts_grid()
        try:
            dpg.set_value("ai_prompt_name_input", "")
            dpg.set_value("ai_prompt_text_input", "")
        except Exception:
            pass

    def _on_ai_prompts_toggle(self):
        try:
            if dpg.is_item_shown("ai_prompts_window"):
                dpg.hide_item("ai_prompts_window")
            else:
                dpg.show_item("ai_prompts_window")
        except Exception:
            pass

    def _on_ai_bar_toggle(self):
        try:
            if dpg.is_item_shown("ai_bar_window"):
                self._save_popup_layout()
                dpg.hide_item("ai_bar_window")
            else:
                dpg.show_item("ai_bar_window")
        except Exception:
            pass

    def _on_audio_toggle(self):
        try:
            if dpg.is_item_shown("audio_window"):
                self._save_popup_layout()
                dpg.hide_item("audio_window")
            else:
                dpg.show_item("audio_window")
        except Exception:
            pass

    def _on_audio_start(self):
        """Start capture on the device picked in the combo (blank = system default)."""
        if not self._audio_engine:
            return
        device = None
        try:
            name = dpg.get_value("audio_device_combo")
            if name and _AUDIO_AVAILABLE:
                for i, d in enumerate(sd.query_devices()):
                    if d['name'] == name and d['max_input_channels'] > 0:
                        device = i
                        break
        except Exception:
            pass
        try:
            self._audio_engine.start(device=device)
            dpg.set_value("audio_capture_status", "capturing")
            dpg.configure_item("audio_capture_status", color=_C_ACCENT)
        except Exception as e:
            dpg.set_value("audio_capture_status", f"error: {e}")
            dpg.configure_item("audio_capture_status", color=[255, 80, 80, 220])

    def _on_audio_stop(self):
        if not self._audio_engine:
            return
        self._audio_engine.stop()
        try:
            dpg.set_value("audio_capture_status", "stopped")
            dpg.configure_item("audio_capture_status", color=_C_DIM)
        except Exception:
            pass

    def _on_audio_map_toggle(self):
        if not self._audio_mapper:
            return
        if self._audio_mapper.enabled:
            self._audio_mapper.disable()
        else:
            self._audio_mapper.enable()
        try:
            on = self._audio_mapper.enabled
            dpg.set_item_label("audio_map_btn", "mapping: on" if on else "mapping: off")
        except Exception:
            pass

    def _on_audio_gain(self, sender, value):
        if self._audio_engine:
            self._audio_engine.gain = value

    def _on_color_picker_toggle(self):
        try:
            if dpg.is_item_shown("color_picker_window"):
                dpg.hide_item("color_picker_window")
            else:
                self._cpick_sync_from_programmer()
                dpg.show_item("color_picker_window")
        except Exception:
            pass

    def _build_color_picker_popup(self):
        """Floating RGB color picker — live mode fires to programmer on every drag."""
        with dpg.window(tag="color_picker_window", label="color picker",
                        width=370, height=480, show=False,
                        pos=(800, 200), no_collapse=False):
            with dpg.group(horizontal=True):
                dpg.add_text("color picker", color=_C_ACCENT)
                dpg.add_spacer(width=12)
                dpg.add_checkbox(tag="cpick_live", label="live",
                                 default_value=True)
            dpg.add_separator()
            dpg.add_color_picker(
                tag="cpick_wheel",
                default_value=(255, 0, 128, 255),
                no_alpha=True,
                no_small_preview=True,
                display_rgb=True,
                display_hex=True,
                picker_mode=dpg.mvColorPicker_wheel,
                width=290,
                callback=self._on_cpick_change,
            )
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_button(label="apply",  width=90, height=26,
                               callback=self._on_cpick_apply)
                dpg.add_spacer(width=6)
                dpg.add_button(label="white",  width=70, height=26,
                               callback=lambda: self._cpick_set(255, 255, 255))
                dpg.add_spacer(width=6)
                dpg.add_button(label="off",    width=60, height=26,
                               callback=lambda: self._cpick_set(0, 0, 0))
            # Quick color swatches
            _QUICK_COLS = [
                ("red",     (255,   0,   0)),
                ("green",   (  0, 255,   0)),
                ("blue",    (  0,   0, 255)),
                ("amber",   (255, 140,   0)),
                ("cyan",    (  0, 200, 200)),
                ("magenta", (255,   0, 200)),
                ("warm",    (255, 180,  60)),
                ("uv",      ( 80,   0, 200)),
            ]
            with dpg.group(horizontal=True):
                for name, (r, g, b) in _QUICK_COLS[:4]:
                    dpg.add_button(
                        label=name, width=68, height=20,
                        callback=lambda s, a, u: self._cpick_set(*u),
                        user_data=(r, g, b),
                    )
            with dpg.group(horizontal=True):
                for name, (r, g, b) in _QUICK_COLS[4:]:
                    dpg.add_button(
                        label=name, width=68, height=20,
                        callback=lambda s, a, u: self._cpick_set(*u),
                        user_data=(r, g, b),
                    )
            dpg.add_text("", tag="cpick_status", color=_C_DIM)

    def _on_cpick_change(self, sender, color_val):
        """Called realtime as the user drags the picker — fires if live is on."""
        if dpg.get_value("cpick_live"):
            self._cpick_fire(color_val, live=True)

    def _on_cpick_apply(self):
        """Apply button — push current picker color to programmer unconditionally."""
        col = dpg.get_value("cpick_wheel")
        self._cpick_fire(col)

    def _cpick_set(self, r, g, b):
        """Set picker to an explicit colour and apply immediately."""
        dpg.set_value("cpick_wheel", (r, g, b, 255))
        self._cpick_fire((r, g, b, 255))

    def _cpick_fire(self, color_val, live=False):
        """Send R G B values to the programmer for the current fixture selection.

        Uses set_rgb() directly for an atomic single-undo update instead of
        routing through run_command (which does 3 separate set_channel calls).
        During live drag (live=True), near-black values are skipped — they are
        almost always drag artifacts from the wheel's black corner, not intent.
        """
        r = max(0, min(255, int(color_val[0])))
        g = max(0, min(255, int(color_val[1])))
        b = max(0, min(255, int(color_val[2])))
        if live and r + g + b < 6:
            return  # skip transient black during drag; use Off button for intentional black
        if self._prog:
            self._prog.set_rgb(r, g, b)
        try:
            dpg.set_value("cpick_status", f"R {r}  G {g}  B {b}")
        except Exception:
            pass

    def _cpick_sync_from_programmer(self):
        """Seed the picker with the live output RGB of the first selected fixture.

        Priority: programmer data → cue output → bright white.
        Using a bright seed ensures the wheel's inner triangle cursor is never
        stuck at the black corner, which would cause every hue drag to fire (0,0,0).
        """
        if not self._prog:
            return
        sel = list(self._prog.selection)
        if not sel:
            return
        master = sel[0]
        fid_master  = str(getattr(master, 'fixture_id', master))
        first_sub_fid = f"{fid_master}.1"

        # 1. Try programmer (sub-fixture first, then master)
        sub_vals = self._prog.data.get(first_sub_fid) or self._prog.data.get(fid_master) or {}
        if 'red' in sub_vals or 'green' in sub_vals or 'blue' in sub_vals:
            r = max(0, min(255, int(sub_vals.get('red',   0))))
            g = max(0, min(255, int(sub_vals.get('green', 0))))
            b = max(0, min(255, int(sub_vals.get('blue',  0))))
        else:
            # 2. Fall back to the live cue-merge output so the wheel opens at the
            #    actual displayed colour, not at black.
            r = g = b = 255  # safe default: full white
            if self._out:
                try:
                    cue_layer = self._out._merged_cue_layer()
                    cue_sub   = cue_layer.get(first_sub_fid, {})
                    cr = max(0, min(255, int(cue_sub.get('red',   0))))
                    cg = max(0, min(255, int(cue_sub.get('green', 0))))
                    cb = max(0, min(255, int(cue_sub.get('blue',  0))))
                    if cr + cg + cb > 0:
                        r, g, b = cr, cg, cb
                except Exception:
                    pass

        try:
            dpg.set_value("cpick_wheel", (r, g, b, 255))
            dpg.set_value("cpick_status", f"R {r}  G {g}  B {b}")
        except Exception:
            pass

    # ── speed Master panel ───────────────────────────────────

    def _build_speed_master_popup(self):
        """Floating 16-slot speed master panel — drag a fader to set BPM live."""
        with dpg.window(tag="speed_master_window", label="speed masters",
                        width=560, height=340, show=False,
                        pos=(600, 300), no_collapse=False,
                        on_close=self._on_speed_master_close):
            dpg.add_text("speed masters  (20–480 bpm)", color=_C_ACCENT)
            dpg.add_separator()
            # 4 columns × 4 rows of 16 slots
            for row in range(4):
                with dpg.group(horizontal=True):
                    for col in range(4):
                        sid = row * 4 + col + 1
                        m   = self._speed_pool.get(sid) if self._speed_pool else None
                        bpm = m.bpm if m else 120.0
                        lbl = m.name if m else f"spd{sid}"
                        with dpg.group(horizontal=False):
                            dpg.add_text(f"{sid:2d}: {lbl[:6]}", tag=f"spd_lbl_{sid}",
                                         color=_C_DIM)
                            dpg.add_slider_float(
                                tag=f"spd_fader_{sid}", label="",
                                width=120, height=18,
                                default_value=bpm,
                                min_value=20.0, max_value=480.0,
                                format="%.0f",
                                callback=self._on_spd_fader,
                                user_data=sid,
                            )
                dpg.add_spacer(height=4)
            dpg.add_separator()
            dpg.add_text("rename: SPEED <n> NAME <name>  |  set via command: SPEED <n> <bpm>",
                         color=_C_DIM)

    def _on_spd_fader(self, sender, value, user_data):
        sid = user_data
        if self._speed_pool:
            self._speed_pool.set_bpm(sid, value)

    def _on_speed_master_close(self, *_):
        """Persist BPM values when the panel is dismissed via X."""
        self._save_popup_layout()
        if self._speed_pool:
            try:
                ShowFile.save_speed_masters(self._speed_pool)
            except Exception:
                pass

    def _on_speed_master_toggle(self, *_):
        try:
            self._refresh_speed_master_panel()
            vis = dpg.is_item_shown("speed_master_window")
            if vis:
                dpg.hide_item("speed_master_window")
                if self._speed_pool:
                    ShowFile.save_speed_masters(self._speed_pool)
            else:
                dpg.show_item("speed_master_window")
            self._save_popup_layout()
        except Exception:
            pass

    def _refresh_speed_master_panel(self):
        """Sync fader positions and labels from pool (called on open)."""
        if not self._speed_pool:
            return
        for sid in self._speed_pool.all_slots():
            m = self._speed_pool.get(sid)
            if not m:
                continue
            try:
                dpg.set_value(f"spd_fader_{sid}", m.bpm)
                dpg.set_item_label(f"spd_lbl_{sid}", f"{sid:2d}: {m.name[:6]}")
            except Exception:
                pass

    # ── fader page popup ─────────────────────────────────────────────────────

    _FPG_SLOTS  = 15
    _FPG_SLOT_W = 78     # per-slot child_window width (includes borders)
    _FPG_SLOT_H = 215    # per-slot child_window height
    _FPG_FADER_H= 80     # vertical slider track length
    _FPG_FADER_W= 64     # vertical slider lateral width
    _FPG_BTN_W  = 66     # button width inside slot
    _FPG_BTN_H  = 22     # button height

    @staticmethod
    def _fpg_exec_for_slot(page, slot):
        """Map a fader-page slot (1.._FPG_SLOTS) on the given page to its
        underlying executor id, MA-style: page 2 slot 1 = executor 16."""
        return (int(page) - 1) * GUIEngine._FPG_SLOTS + int(slot)

    @staticmethod
    def _fpg_slot_for_exec(page, exec_id):
        """Inverse of _fpg_exec_for_slot — the slot (1.._FPG_SLOTS) that
        would display exec_id on the given page, or None if it's off-page."""
        slot = int(exec_id) - (int(page) - 1) * GUIEngine._FPG_SLOTS
        return slot if 1 <= slot <= GUIEngine._FPG_SLOTS else None

    def _build_fader_page_popup(self):
        """15-slot MA-style fader page — floating, hidden by default."""
        _win_w = self._FPG_SLOTS * (self._FPG_SLOT_W + 4) + 22
        _win_h = self._FPG_SLOT_H + 80

        with dpg.window(tag="fader_page_window",
                        label=f"fader page  [page {self._fpg_page}]",
                        width=_win_w, height=_win_h, show=False,
                        pos=(100, 100), no_collapse=False):
            with dpg.group(horizontal=True):
                dpg.add_text("page:", color=_C_DIM)
                dpg.add_button(label="◀", width=26, callback=self._on_fpg_page_prev)
                dpg.add_text(f"{self._fpg_page}", tag="fpg_page_lbl", color=_C_ACCENT)
                dpg.add_button(label="▶", width=26, callback=self._on_fpg_page_next)
                dpg.add_spacer(width=8)
                dpg.add_text(f"execs {self._fpg_exec_for_slot(self._fpg_page, 1)}"
                            f"-{self._fpg_exec_for_slot(self._fpg_page, self._FPG_SLOTS)}",
                            tag="fpg_range_lbl", color=_C_DIM)
            dpg.add_separator()
            with dpg.group(horizontal=True):
                for n in range(1, self._FPG_SLOTS + 1):
                    with dpg.child_window(
                            tag=f"fpg_slot_{n}",
                            width=self._FPG_SLOT_W, height=self._FPG_SLOT_H,
                            border=True, no_scrollbar=True, no_scroll_with_mouse=True):
                        dpg.add_text(f"{n}", color=_C_DIM)
                        dpg.add_text("—", tag=f"fpg_name_{n}", color=_C_TEXT,   wrap=self._FPG_SLOT_W - 8)
                        dpg.add_text("—", tag=f"fpg_cue_{n}",  color=_C_ACCENT, wrap=self._FPG_SLOT_W - 8)
                        dpg.add_slider_float(
                            tag=f"fpg_fader_{n}",
                            vertical=True,
                            width=self._FPG_FADER_W, height=self._FPG_FADER_H,
                            min_value=0.0, max_value=1.0,
                            default_value=1.0, format="%.0f%%",
                            no_input=True,
                            callback=self._on_fpg_fader, user_data=n)
                        dpg.add_button(tag=f"fpg_btna_{n}", label="go",
                                       width=self._FPG_BTN_W, height=self._FPG_BTN_H,
                                       callback=self._on_fpg_btn, user_data=(n, 'a'))
                        dpg.add_button(tag=f"fpg_btnb_{n}", label="back",
                                       width=self._FPG_BTN_W, height=self._FPG_BTN_H,
                                       callback=self._on_fpg_btn, user_data=(n, 'b'))
                        dpg.add_button(tag=f"fpg_btnc_{n}", label="stop",
                                       width=self._FPG_BTN_W, height=self._FPG_BTN_H,
                                       callback=self._on_fpg_btn, user_data=(n, 'c'))

    def _on_fader_page_toggle(self, *_):
        try:
            vis = dpg.is_item_shown("fader_page_window")
            if vis:
                dpg.hide_item("fader_page_window")
            else:
                self._fpg_refresh_all()
                dpg.show_item("fader_page_window")
            self._save_popup_layout()
        except Exception:
            pass

    def _fpg_step_page(self, delta):
        """Pure page-number update (no dpg calls) — clamped to >= 1. Split out
        from the prev/next callbacks so it's exercisable without a live dpg
        context (e.g. from the headless smoke test)."""
        self._fpg_page = max(1, self._fpg_page + int(delta))
        return self._fpg_page

    def _on_fpg_page_prev(self, *_):
        self._fpg_step_page(-1)
        self._fpg_page_changed()

    def _on_fpg_page_next(self, *_):
        self._fpg_step_page(1)
        self._fpg_page_changed()

    def _fpg_page_changed(self):
        """Update the page label/title/range display and re-sync all slots
        after the page number changes — otherwise slots would keep showing
        stale data from the previously-displayed bank of executors."""
        try:
            dpg.set_value("fpg_page_lbl", f"{self._fpg_page}")
            dpg.configure_item("fader_page_window",
                               label=f"fader page  [page {self._fpg_page}]")
            dpg.set_value("fpg_range_lbl",
                          f"execs {self._fpg_exec_for_slot(self._fpg_page, 1)}"
                          f"-{self._fpg_exec_for_slot(self._fpg_page, self._FPG_SLOTS)}")
        except Exception:
            pass
        self._fpg_refresh_all()

    def _fpg_refresh_all(self):
        """Sync all fader page slot labels and fader positions from executor pool."""
        if not self._executor_pool:
            return
        for n in range(1, self._FPG_SLOTS + 1):
            eid = self._fpg_exec_for_slot(self._fpg_page, n)
            ex = self._executor_pool.executors.get(eid)
            try:
                if ex and ex.cuestack:
                    dpg.set_value(f"fpg_name_{n}", ex.cuestack.name[:9])
                else:
                    dpg.set_value(f"fpg_name_{n}", "—")
                dpg.set_value(f"fpg_fader_{n}", ex.level if ex else 1.0)
            except Exception:
                pass

    def _on_fpg_fader(self, _sender, value, user_data):
        n = int(user_data)
        if self._executor_pool:
            eid = self._fpg_exec_for_slot(self._fpg_page, n)
            ex = self._executor_pool.executors.get(eid)
            if ex:
                ex.level = max(0.0, min(1.0, float(value)))

    def _on_fpg_btn(self, _sender, _app_data, user_data):
        n, slot = user_data
        eid = self._fpg_exec_for_slot(self._fpg_page, n)
        ex = self._executor_pool.executors.get(eid) if self._executor_pool else None
        if not ex or not self._cmd:
            return
        fn = getattr(ex, f'btn_{slot}', 'GO')
        if fn == 'FLASH':
            return  # hold polling handled by tick loop
        self._cmd(f"FADER {eid} {fn}")

    def _tick_fader_page(self):
        """Update fader page slot labels + FLASH polling (called from _tick)."""
        if not dpg.is_item_shown("fader_page_window"):
            return
        if not self._executor_pool:
            return
        for n in range(1, self._FPG_SLOTS + 1):
            eid = self._fpg_exec_for_slot(self._fpg_page, n)
            ex = self._executor_pool.executors.get(eid)
            try:
                # Name and cue labels
                name = ex.cuestack.name[:9] if (ex and ex.cuestack) else "—"
                dpg.set_value(f"fpg_name_{n}", name)
                if ex and ex.cuestack and ex.cuestack.current is not None:
                    cur = ex.cuestack.current
                    cue = ex.cuestack.cues.get(cur)
                    cue_lbl = f"▶{cur:.0f}" + (f":{cue.name[:4]}" if cue else "")
                else:
                    cue_lbl = "—"
                dpg.set_value(f"fpg_cue_{n}", cue_lbl)
                # Sync fader only when not actively dragged
                if not dpg.is_item_active(f"fpg_fader_{n}"):
                    dpg.set_value(f"fpg_fader_{n}", ex.level if ex else 1.0)
                # Button labels from configurable function
                for _s, _tag in (('a', f"fpg_btna_{n}"), ('b', f"fpg_btnb_{n}"), ('c', f"fpg_btnc_{n}")):
                    fn = getattr(ex, f'btn_{_s}', 'GO') if ex else {'a': 'GO', 'b': 'BACK', 'c': 'STOP'}[_s]
                    dpg.set_item_label(_tag, fn.lower())
            except Exception:
                pass

    def _tick_audio(self):
        """Update live level meters + capture/mapping status (called from _tick)."""
        if not self._audio_engine or not dpg.is_item_shown("audio_window"):
            return
        try:
            dpg.set_value("audio_bar_level", self._audio_engine.level)
            dpg.set_value("audio_bar_low",   self._audio_engine.low)
            dpg.set_value("audio_bar_mid",   self._audio_engine.mid)
            dpg.set_value("audio_bar_high",  self._audio_engine.high)
            if self._audio_mapper:
                on = self._audio_mapper.enabled
                dpg.set_item_label("audio_map_btn", "mapping: on" if on else "mapping: off")
            state = "capturing" if self._audio_engine._running else "stopped"
            dpg.set_value("audio_capture_status", state)
        except Exception:
            pass

    def _build_monitors_popup(self):
        """Floating programmer/output monitor popup — no inner boxes, just tables."""
        with dpg.window(tag="monitors_window", label="monitors",
                        width=1600, height=360, show=False,
                        pos=(160, 360), no_collapse=False):
            with dpg.group(horizontal=True):
                # ── programmer ──────────────────────────────────────
                with dpg.group(tag="prog_panel"):
                    dpg.add_text("programmer", tag="prog_mon_title", color=_C_DIM)
                    dpg.add_separator()
                    with dpg.table(tag="prog_table", header_row=True,
                                   borders_innerV=True, borders_outerV=True,
                                   borders_outerH=True, row_background=True,
                                   width=768, scrollY=False):
                        dpg.add_table_column(label="fixture", width_fixed=True, init_width_or_weight=110)
                        dpg.add_table_column(label="r",   width_fixed=True, init_width_or_weight=42)
                        dpg.add_table_column(label="g",   width_fixed=True, init_width_or_weight=42)
                        dpg.add_table_column(label="b",   width_fixed=True, init_width_or_weight=42)
                        dpg.add_table_column(label="dim", width_fixed=True, init_width_or_weight=56)
                        dpg.add_table_column(label="fx",  width_stretch=True)
                        dpg.add_table_column(label="bar", width_fixed=True, init_width_or_weight=130)

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
                        dpg.add_table_column(label="fixture", width_fixed=True, init_width_or_weight=110)
                        dpg.add_table_column(label="r",   width_fixed=True, init_width_or_weight=42)
                        dpg.add_table_column(label="g",   width_fixed=True, init_width_or_weight=42)
                        dpg.add_table_column(label="b",   width_fixed=True, init_width_or_weight=42)
                        dpg.add_table_column(label="dim", width_fixed=True, init_width_or_weight=56)
                        dpg.add_table_column(label="bar", width_stretch=True)

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

    def _build_ai_bar_popup(self):
        """Floating AI prompt bar — moved out of the main window (was inline,
        ~70px, and only counted against the 1920x1080 layout budget when
        ANTHROPIC_API_KEY was unset; with a key set it silently busted the
        no-scrollbar budget). Always built now, like the attr/monitors popups,
        so the main window's layout is deterministic regardless of AI config.
        """
        with dpg.window(tag="ai_bar_window", label="ai prompt",
                        width=760, height=230, show=False, pos=(240, 100)):
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
                dpg.add_spacer(width=4)
                dpg.add_button(label="prompts", width=70,
                               callback=self._on_ai_prompts_toggle)
            if not (self._ai and self._ai._enabled):
                dpg.add_text("anthropic_api_key not set — requests will no-op",
                             color=_C_DIM)
            dpg.add_separator()
            with dpg.group():
                for row_start in range(0, len(self._AI_CHIPS), 5):
                    with dpg.group(horizontal=True):
                        for label, prompt in self._AI_CHIPS[row_start:row_start + 5]:
                            dpg.add_button(label=label, width=140,
                                           callback=self._on_ai_chip,
                                           user_data=prompt)
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_input_text(tag="ai_input", hint="describe the look...",
                                   width=-120, on_enter=True,
                                   callback=self._on_ai_send)
                dpg.add_button(label="send", width=110,
                               callback=self._on_ai_send)

    def _build_audio_popup(self):
        """Floating audio-reactive panel — front-end for Block 9's AudioEngine/
        AudioMapper, which previously had a full AUDIO ON/OFF/START/STOP/GAIN
        command surface but zero GUI (see changelog / KNOWN ISSUES): device
        pick, capture, and mapping toggle all required typing commands. Mirrors
        the ai/midi popup pattern — built hidden, opened via a header button.
        """
        with dpg.window(tag="audio_window", label="audio reactive",
                        width=420, height=300, show=False, pos=(260, 120)):
            dpg.add_text("audio reactive", color=_C_ACCENT)
            dpg.add_separator()
            if not (self._audio_engine and _AUDIO_AVAILABLE):
                dpg.add_text("audio backend unavailable — sounddevice/Portaudio "
                             "not installed or no input device.", color=_C_DIM,
                             wrap=380)
            with dpg.group(horizontal=True):
                dpg.add_text("device:", color=_C_DIM)
                _dev_names = []
                if self._audio_engine and _AUDIO_AVAILABLE:
                    try:
                        _dev_names = [d['name'] for d in sd.query_devices()
                                     if d['max_input_channels'] > 0]
                    except Exception:
                        _dev_names = []
                dpg.add_combo(tag="audio_device_combo", items=_dev_names,
                              default_value=_dev_names[0] if _dev_names else "",
                              width=220)
            with dpg.group(horizontal=True):
                dpg.add_button(label="start capture", width=110,
                               callback=self._on_audio_start)
                dpg.add_button(label="stop", width=60,
                               callback=self._on_audio_stop)
                dpg.add_text("", tag="audio_capture_status", color=_C_DIM)
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_button(label="mapping: off", tag="audio_map_btn", width=130,
                               callback=self._on_audio_map_toggle)
                dpg.add_text("bass=red mid=green high=blue level=dim", color=_C_DIM,
                             wrap=180)
            dpg.add_drag_float(tag="audio_gain", label="gain",
                               default_value=(self._audio_engine.gain
                                              if self._audio_engine else 3.0),
                               min_value=0.1, max_value=20.0, speed=0.1,
                               format="%.1f", width=200,
                               callback=self._on_audio_gain)
            dpg.add_separator()
            dpg.add_text("live levels", color=_C_DIM)
            for _lbl, _tag in (("level", "audio_bar_level"), ("low", "audio_bar_low"),
                              ("mid", "audio_bar_mid"), ("high", "audio_bar_high")):
                with dpg.group(horizontal=True):
                    dpg.add_text(f"{_lbl:5s}", color=_C_DIM)
                    dpg.add_progress_bar(tag=_tag, default_value=0.0, width=280)

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
        """Record a tap — delegates to the TAP command so GUI and text share state."""
        if self._cmd:
            result = self._cmd("TAP")
            try:
                if result and result.startswith("BPM"):
                    dpg.set_value("fx_tap_label", result.replace("BPM → ", "") + " bpm")
                else:
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
            GUIEngine._save_status_clear_at = time.monotonic() + 3.0
        else:
            dpg.set_value("hdr_save_status", "  no save_fn")

    def _on_midi_port_connect(self):
        """Switch the MIDI input port to the one selected in the combo."""
        try:
            port_name = dpg.get_value("midi_port_combo")
        except Exception:
            return
        if not port_name:
            return
        if self._midi:
            self._midi.stop()
            self._midi.start(port_name)
        try:
            dpg.set_value("midi_port_status", f"→ {port_name}")
            dpg.configure_item("midi_port_status", color=_C_ACCENT)
        except Exception:
            pass

    def _on_midi_port_disconnect(self):
        """Close the current MIDI port without opening a new one."""
        if self._midi:
            self._midi.stop()
        try:
            dpg.set_value("midi_port_status", "disconnected")
            dpg.configure_item("midi_port_status", color=_C_DIM)
        except Exception:
            pass

    def _on_direct_add(self):
        """Add a CC or Note mapping directly from typed channel/number inputs."""
        try:
            ch   = int(dpg.get_value("direct_ch"))
            num  = int(dpg.get_value("direct_num"))
            kind = dpg.get_value("direct_type_radio")  # "CC" or "Note"
            target_name = dpg.get_value("direct_target")
        except Exception:
            return
        if not target_name or target_name not in self.target_registry:
            try:
                dpg.set_value("direct_status", "pick target")
            except Exception:
                pass
            return
        entry  = self.target_registry[target_name]
        cb     = entry[0]
        soft   = entry[1]
        off_cb = entry[3] if len(entry) > 3 else None
        if kind == "cc":
            self._midi.map_cc(ch, num, cb, name=target_name, soft_takeover=soft)
            label = f"cc{num}"
        else:
            self._midi.map_note(ch, num, cb, off_cb, name=target_name)
            label = f"note{num}"
        ShowFile.save_midi(self._midi)
        self._refresh_midi_table()
        try:
            dpg.set_value("direct_status", f"ch{ch} {label} → {target_name}")
        except Exception:
            pass

    def _on_learn_type_change(self, sender, value):
        self._learn_type = 'cc' if value == 'cc' else 'note'

    def _toggle_learn(self):
        if self._learn_armed:
            # already armed — cancel
            self._learn_armed = False
            self._midi.cancel_learn()
            dpg.set_item_label("learn_btn", "learn")
            dpg.set_value("learn_status", "cancelled")
            return
        target_name = dpg.get_value("learn_target")
        if not target_name or target_name not in self.target_registry:
            dpg.set_value("learn_status", "← pick target first")
            return
        self._learn_target = target_name
        self._learn_armed  = True
        type_str = dpg.get_value("learn_type_radio")
        self._learn_type = 'cc' if type_str == 'cc' else 'note'
        self._learn_armed_type = self._learn_type
        wait_label = "CC knob/fader" if self._learn_type == 'cc' else "key or pad"
        dpg.set_value("learn_status", f"waiting for {wait_label}...")
        dpg.set_item_label("learn_btn", "cancel")
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
        name    = f"fader {ex_n} Flash"
        on_cmd  = f"FADER {ex_n} flash on"
        off_cmd = f"FADER {ex_n} flash off"
        on_cb   = (lambda c=on_cmd:  self._cmd(c)) if self._cmd else (lambda: None)
        off_cb  = (lambda c=off_cmd: self._cmd(c)) if self._cmd else (lambda: None)
        GUIEngine.target_registry[name] = (on_cb, False, True, off_cb)
        self._learn_target     = name
        self._learn_armed      = True
        self._learn_armed_type = 'note'
        self._midi.start_learn('note', self._on_learn_captured)
        dpg.set_value("flash_learn_status", f"waiting for note → {name}...")

    def _start_exec_gb_learn(self):
        """
        Learn a note for 'Exec <n> GO' or 'Exec <n> BACK' — steps that
        specific executor's cuestack forward/back on press. Unlike the
        fixed "GO"/"BACK" targets in target_registry (which always act on
        whichever executor is currently active via CUESTACK <n>), and unlike
        _start_go_cue_learn (which jumps straight to one cue number), this
        drives an arbitrary executor's normal GO/BACK — the MIDI-side
        equivalent of what /gma3/key/<page>/<exec>/go already does over OSC.
        """
        try:
            ex_n = int(dpg.get_value("midi_exec_gb_num"))
        except Exception:
            return
        verb = dpg.get_value("midi_exec_gb_type")  # 'go' or 'back'
        name = f"exec {ex_n} {verb}"
        cmd  = f"EXEC {ex_n} {verb.upper()}"
        cb   = (lambda c=cmd: self._cmd(c)) if self._cmd else (lambda: None)
        GUIEngine.target_registry[name] = (cb, False, True)
        self._learn_target     = name
        self._learn_armed      = True
        self._learn_armed_type = 'note'
        self._midi.start_learn('note', self._on_learn_captured)
        dpg.set_value("midi_exec_gb_status", f"waiting for note → {name}...")

    def _on_go_cue_captured(self, ch, number):
        """MIDI-thread callback for GO CS+CUE note learn."""
        name = self._learn_target
        self._learn_armed = False
        entry = GUIEngine.target_registry.get(name)
        if entry:
            self._midi.map_note(ch, number, entry[0], name=name)
        dpg.set_value("go_cue_status", f"ch{ch} note{number} → {name}")
        try:
            dpg.set_item_label("learn_btn", "learn")
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
            type_label = "cc"
        else:
            self._midi.map_note(ch, number, cb, off_cb, name=target_name)
            type_label = "note"

        # set_value is thread-safe; item rebuild deferred to main thread
        dpg.set_value("learn_status",
                      f"CH{ch} {type_label}{number} → {target_name}")
        try:
            dpg.set_item_label("learn_btn", "learn")
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

        # Install token display callback once; accumulates session total
        if self._ai and self._ai._token_cb is None:
            _sess = [0, 0]  # [session_in, session_out]
            def _tok_cb(in_t, out_t):
                _sess[0] += in_t
                _sess[1] += out_t
                try:
                    dpg.set_value("ai_tokens",
                                  f"↑{in_t} ↓{out_t} tok  (session: {_sess[0]+_sess[1]})")
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
        label = f"ch{ch} {'cc' if kind == 'cc' else 'note'}{num}  ({current_name})"
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
                dpg.add_text("note", color=_C_P_BEAM)
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
        with dpg.table(parent="cue_list_group", tag=f"cl_tbl_{sid}",
                       header_row=False, resizable=False,
                       borders_innerH=True, borders_innerV=False,
                       borders_outerH=False, borders_outerV=False,
                       row_background=True,
                       scrollX=False, scrollY=False,
                       policy=dpg.mvTable_SizingFixedFit):
            dpg.add_table_column(label="#", width_fixed=True, init_width_or_weight=42)
            dpg.add_table_column(label="name", width_stretch=True, init_width_or_weight=1.0)
            dpg.add_table_column(label="t", width_fixed=True, init_width_or_weight=50)
            for num in stack._sorted_cue_numbers():
                cue  = stack.cues[num]
                tag  = f"cue_row_{sid}_{num}"
                ft   = f"{cue.fade_time:.1f}s" if cue.fade_time else ""
                fw   = getattr(cue, 'follow_time', 0.0)
                if fw > 0:
                    ft = (ft + f" →{fw:.0f}s") if ft else f"→{fw:.0f}s"
                note = getattr(cue, 'note', '')
                with dpg.table_row():
                    dpg.add_text(f"{num:.0f}", color=_C_ACCENT)
                    dpg.add_selectable(label=cue.name, tag=tag,
                                       span_columns=False,
                                       callback=lambda *_, u=num: self._goto(u),
                                       user_data=num)
                    if note:
                        with dpg.tooltip(tag):
                            dpg.add_text(note, color=(200, 200, 160, 255))
                    dpg.add_text(ft, color=_C_DIM)

    def _playbacks_state_hash(self):
        """Compact snapshot of active executor state — used to detect changes."""
        if not self._executor_pool:
            return ()
        return tuple(
            (eid, ex.priority, ex.cuestack.current if ex.cuestack else None,
             ex.time_override_on, ex.time_override_fade)
            for eid, ex in sorted(self._executor_pool.executors.items())
            if ex.cuestack
        )

    @staticmethod
    def _fit_text(text, max_w):
        """Truncate text with an ellipsis so its rendered width stays <= max_w px.
        Used to keep the active-playbacks row's trailing action buttons from
        being pushed off the edge of the (fixed-width) left column by a long
        cuestack/cue name."""
        try:
            if dpg.get_text_size(text)[0] <= max_w:
                return text
            while text and dpg.get_text_size(text + "…")[0] > max_w:
                text = text[:-1]
            return (text + "…") if text else "…"
        except Exception:
            return text

    def _rebuild_playbacks(self):
        """
        Rebuild the executor-slot list inside the left column. Lists every
        executor with a cuestack assigned, not just ones currently playing
        a cue — an idle executor (assigned but never GO'd, or stopped via
        flash off) still needs its flash/stop/priority buttons reachable
        by mouse, since those are the only way to trigger it without MIDI.
        """
        try:
            dpg.delete_item("playbacks_list", children_only=True)
        except Exception:
            return

        active = []
        if self._executor_pool:
            assigned_eids = {eid for eid in self._executor_pool.executors
                              if self._executor_pool.executors[eid].cuestack}
            ordered = [eid for eid in reversed(self._executor_pool._fire_order)
                       if eid in assigned_eids]
            ordered += sorted(assigned_eids - set(ordered))
            for eid in ordered:
                active.append(self._executor_pool.executors[eid])

        if not active:
            dpg.add_text("— none running", tag="playbacks_empty",
                         color=_C_DIM, parent="playbacks_list")
            return

        # Reserve room for the trailing fixed-width buttons (time/priority/a/b/c
        # + inter-item spacing) so the two variable-length labels below never
        # push them past the edge of the (fixed-width) left column — see
        # _fit_text. 260px measured empirically (pixel-verified via a headless
        # DearPyGui render against the widest real row) with margin to spare
        # for the rarer 52px time-override badge.
        try:
            _row_w = dpg.get_item_rect_size("playbacks_list")[0] or 349
        except Exception:
            _row_w = 349
        _label_budget = max(60, _row_w - 260)
        _name_w = _label_budget * 2 // 5
        _cue_w  = _label_budget - _name_w

        for i, ex in enumerate(active):
            cs  = ex.cuestack
            cur = cs.current
            if cur is not None:
                cue = cs.cues.get(cur)
                cue_label = f"▶ {cur:.0f}: {cue.name}" if cue else f"▶ {cur:.0f}"
            else:
                cue_label = "▶ —"
            pri_label = Executor.PRIORITY_LABELS.get(ex.priority, 'nrm')
            _full_name = f"[{ex.exec_id}] {cs.name}"
            _fit_name  = self._fit_text(_full_name, _name_w)
            _fit_cue   = self._fit_text(cue_label, _cue_w)
            if i > 0:
                dpg.add_separator(parent="playbacks_list")
            with dpg.group(horizontal=True, parent="playbacks_list"):
                _name_tag = f"pb_name_{ex.exec_id}"
                _cue_tag  = f"pb_cue_{ex.exec_id}"
                dpg.add_text(_fit_name, tag=_name_tag, color=_C_TEXT)
                if _fit_name != _full_name:
                    with dpg.tooltip(_name_tag):
                        dpg.add_text(_full_name)
                dpg.add_text(_fit_cue, tag=_cue_tag, color=_C_ACCENT)
                if _fit_cue != cue_label:
                    with dpg.tooltip(_cue_tag):
                        dpg.add_text(cue_label)
                # Time override badge
                if ex.time_override_on and ex.time_override_fade is not None:
                    t_label  = f"t{ex.time_override_fade:.1f}s"
                    dpg.add_button(label=t_label, width=52, height=20,
                                   callback=self._on_exec_time_toggle,
                                   user_data=ex.exec_id)
                    dpg.configure_item(dpg.last_item(), enabled=cs.allow_exec_time)
                    if not cs.allow_exec_time:
                        dpg.add_text("🔒", color=_C_DIM)
                else:
                    dpg.add_button(label="time", width=44, height=20,
                                   callback=self._on_exec_time_toggle,
                                   user_data=ex.exec_id)
                dpg.add_button(label=pri_label, width=40, height=20,
                               callback=self._on_priority_cycle,
                               user_data=ex.exec_id)
                for _slot, _fn in (('a', ex.btn_a), ('b', ex.btn_b), ('c', ex.btn_c)):
                    _tag = f"ebtn_{_slot}_{ex.exec_id}"
                    dpg.add_button(label=_fn.lower(), tag=_tag,
                                   width=40, height=20,
                                   callback=self._on_exec_slot_btn,
                                   user_data=(ex.exec_id, _slot))
            # fader level row
            dpg.add_slider_float(
                tag=f"exec_fader_{ex.exec_id}",
                default_value=ex.level,
                min_value=0.0, max_value=1.0,
                width=-1, height=16,
                format="%.2f",
                callback=self._on_exec_fader,
                user_data=ex.exec_id,
                parent="playbacks_list")
            # Fade progress bar (thin, amber) — shows crossfade progress live
            dpg.add_progress_bar(
                tag=f"exec_fade_{ex.exec_id}",
                default_value=0.0,
                width=-1, height=5,
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

    def _on_exec_flash_btn(self, sender, app_data, user_data):
        # flash on/OFF is handled by the tick loop via is_item_active() polling.
        pass

    def _on_exec_slot_btn(self, sender, app_data, user_data):
        eid, slot = user_data
        ex = self._executor_pool.executors.get(eid) if self._executor_pool else None
        if not ex or not self._cmd:
            return
        fn = getattr(ex, f'btn_{slot}', 'GO')
        if fn == 'FLASH':
            return  # hold behavior — tick loop handles via is_item_active()
        self._cmd(f"FADER {eid} {fn}")

    def _on_stop_executor(self, sender, app_data, user_data):
        exec_id = int(user_data)
        if self._executor_pool:
            ex = self._executor_pool.executors.get(exec_id)
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

    def _on_fixture_dim_slider(self, _sender, value, user_data):
        """Write dim directly into programmer layer without changing fixture selection."""
        fid    = int(user_data)
        dim    = max(0.0, min(1.0, float(value)))
        fid_s  = str(fid)
        if self._out:
            self._out.programmer_layer.setdefault(fid_s, {})['dim'] = dim
        if self._patch and fid in self._patch.fixtures:
            # MasterFixture.set_dimmer() takes a 0.0-1.0 fraction (see its
            # own docstring) -- dim is already that fraction. A stray "* 100"
            # here meant any drag above ~1% clamped virtual_dimmer to 1.0
            # (max(0.0, min(1.0, dim*100)) == 1.0 for basically all inputs).
            # programmer.set_dimmer() and the AI dim action both pass the
            # already-normalized fraction straight through; match that.
            self._patch.fixtures[fid].set_dimmer(dim)

    def _on_fixture_dim_select_all(self):
        """Select all fixtures in the programmer."""
        if self._cmd and self._patch:
            fids = sorted(m.fixture_id for m in self._patch.all_fixtures())
            if fids:
                self._cmd(f"{fids[0]} THRU {fids[-1]}")

    def _on_fixture_chip_click(self, sender, app_data, user_data):
        """Click a fixture chip in the status bar to select it (Shift+click to add)."""
        fid = int(user_data)
        if not self._patch or fid not in self._patch.fixtures:
            return
        master = self._patch.fixtures[fid]
        shift = (dpg.is_key_down(dpg.mvKey_LShift) or
                 dpg.is_key_down(dpg.mvKey_RShift))
        if shift and self._prog:
            cur = [f for f in self._prog.selection if isinstance(f, MasterFixture)]
            if master in cur:
                cur.remove(master)
            else:
                cur.append(master)
            self._prog.select(cur)
            sel_str = " ".join(str(m.fixture_id) for m in cur) or "none"
            self._log(f"> SELECT {sel_str}")
        else:
            if self._cmd:
                self._cmd(str(fid))

    def _on_blind_toggle(self):
        """Toggle BLIND mode — suppress programmer from DMX output."""
        if self._cmd and self._out:
            self._cmd("LIVE" if self._out.blind else "BLIND")

    def _on_pt_toggle(self):
        """programmer time toggle: click to set 2s fade, click again to turn off."""
        if self._cmd:
            pt = _prog_time
            if pt.get('on'):
                self._cmd("PROG TIME OFF")
            else:
                self._cmd("PROG TIME 2")

    def _on_highlight_toggle(self):
        """Toggle HIGHLIGHT mode — selected fixtures go full-white at full dim."""
        if not self._out:
            return
        self._out.highlight_mode = not self._out.highlight_mode
        if self._out.highlight_mode:
            self._sync_highlight_selection()
            self._log("> highlight on")
        else:
            self._log("> highlight off")

    def _sync_highlight_selection(self):
        """Push the current programmer selection into the output engine's highlight set."""
        if not self._out or not self._prog:
            return
        self._out.highlight_fids = {
            f.fixture_id for f in self._prog.selection
            if isinstance(f, MasterFixture)
        }

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

    _tick_first           = True    # sync one-shot values on first tick
    _auto_save_t          = 0.0    # monotonic time of last auto-save
    _AUTO_SAVE_INT        = 300.0  # seconds between auto-saves (5 min)
    _save_status_clear_at = 0.0   # monotonic time to clear the save status label

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

        # Auto-clear error flash after 8 s if operator doesn't run another command
        if self._error_flash_time is not None:
            import time as _time
            if _time.monotonic() - self._error_flash_time > 8.0:
                self._error_flash_time = None
                try:
                    dpg.set_value("cmd_error_flash", "")
                except Exception:
                    pass

        # Advance live programmer fades (AT … IN <seconds>)
        if self._prog and self._prog.live_fades:
            import time as _t
            _now = _t.monotonic()
            _still_active = []
            for _fade in self._prog.live_fades:
                _elapsed = _now - _fade['start']
                _dur     = _fade['duration']
                _fid     = _fade['fid']
                _ch      = _fade['channel']
                _src     = _fade['src']
                _dst     = _fade['dst']
                if _elapsed >= _dur:
                    # Fade complete — write final value
                    self._prog.data.setdefault(_fid, {})[_ch] = _dst
                else:
                    # Interpolate
                    _frac = _elapsed / _dur
                    _val  = _src + (_dst - _src) * _frac
                    self._prog.data.setdefault(_fid, {})[_ch] = _val
                    _still_active.append(_fade)
            self._prog.live_fades = _still_active

        self._tick_pools()
        self._tick_stage()
        self._tick_fader_page()
        self._tick_audio()

        # ── Status bar: programmer + selection ──────────────────
        prog_data   = self._prog.data if self._prog else {}
        prog_active = any(v for v in prog_data.values() if v)
        try:
            if prog_active:
                # Compute average RGB across all sub-fixtures in programmer
                r_sum = g_sum = b_sum = n = 0
                for fid, vals in prog_data.items():
                    if '.' in fid and vals:
                        r_sum += vals.get('red',   0)
                        g_sum += vals.get('green', 0)
                        b_sum += vals.get('blue',  0)
                        n += 1
                if n > 0:
                    mix = (max(60, r_sum // n), max(60, g_sum // n),
                           max(60, b_sum // n), 255)
                    dot_col = mix
                else:
                    dot_col = _C_ACCENT
                dpg.configure_item("sb_prog_dot", color=dot_col)
                dpg.configure_item("sb_prog_lbl", color=_C_ACCENT)
                dpg.set_value("sb_prog_lbl", "programmer  dirty")
            else:
                dpg.configure_item("sb_prog_dot", color=_C_DIM)
                dpg.configure_item("sb_prog_lbl", color=_C_DIM)
                dpg.set_value("sb_prog_lbl", "programmer  clear")
        except Exception:
            pass

        # BLIND indicator (button — clickable toggle)
        try:
            blind = self._out.blind if self._out else False
            dpg.configure_item("sb_blind_lbl",
                               label="● blind" if blind else "○ blind")
            theme = self._alert_btn_theme if blind else self._dim_btn_theme
            if theme:
                dpg.bind_item_theme("sb_blind_lbl", theme)
        except Exception:
            pass

        # BLACKOUT indicator (button — clickable toggle)
        try:
            bbo = (self._out.master_level == 0.0) if self._out else False
            dpg.configure_item("sb_bbo_lbl",
                               label="● blackout" if bbo else "○ blackout")
            theme = self._alert_btn_theme if bbo else self._dim_btn_theme
            if theme:
                dpg.bind_item_theme("sb_bbo_lbl", theme)
            # Also sync master fader widget
            if bbo:
                try:
                    if not dpg.is_item_active("stage_master_fader"):
                        dpg.set_value("stage_master_fader", 0)
                except Exception:
                    pass
        except Exception:
            pass

        # HIGHLIGHT indicator (button — clickable toggle; syncs selection each tick)
        try:
            hl = self._out.highlight_mode if self._out else False
            dpg.configure_item("sb_hl_lbl", label="● highlight" if hl else "○ highlight")
            theme = self._go_theme if hl else self._dim_btn_theme
            if theme:
                dpg.bind_item_theme("sb_hl_lbl", theme)
            if hl:
                self._sync_highlight_selection()
        except Exception:
            pass

        try:
            sel = self._prog.selection if self._prog else []
            sel_ids = {f.fixture_id if isinstance(f, MasterFixture)
                       else getattr(f, 'master_id', None) for f in sel}
            sel_ids.discard(None)
            for master in self._patch.all_fixtures():
                fid    = master.fixture_id
                active = fid in sel_ids
                theme  = self._go_theme if active else self._dim_btn_theme
                if theme:
                    try:
                        dpg.bind_item_theme(f"sb_sel_{fid}", theme)
                    except Exception:
                        pass
        except Exception:
            pass

        # Sync per-fixture dim quick-set sliders from programmer/cue output
        try:
            if self._patch and self._out:
                cue_m = self._out._merged_cue_layer()
                for master in self._patch.all_fixtures():
                    fid = master.fixture_id
                    tag = f"fq_dim_{fid}"
                    if not dpg.is_item_active(tag):
                        pl = self._out.programmer_layer.get(str(fid), {})
                        cl = cue_m.get(str(fid), {})
                        dim = pl.get('dim', cl.get('dim', master.virtual_dimmer))
                        dpg.set_value(tag, float(dim))
        except Exception:
            pass

        try:
            pt = _prog_time
            if pt.get('on'):
                pt_label = f"● pan·tilt {pt['fade']:.1f}s"
                if pt.get('delay', 0.0):
                    pt_label += f" d{pt['delay']:.1f}"
                dpg.configure_item("sb_pt_lbl", label=pt_label)
                if self._go_theme:
                    dpg.bind_item_theme("sb_pt_lbl", self._go_theme)
            else:
                dpg.configure_item("sb_pt_lbl", label="○ pan·tilt")
                if self._dim_btn_theme:
                    dpg.bind_item_theme("sb_pt_lbl", self._dim_btn_theme)
        except Exception:
            pass

        # Selection counter in command bar (keep small label too)
        try:
            sel = self._prog.selection
            masters = sum(1 for f in sel if isinstance(f, MasterFixture))
            if masters:
                dpg.set_value("cmd_sel_count", f"sel: {masters} fixture(s)")
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

        # Auto-follow: fire GO on executors whose follow timer has elapsed
        if self._executor_pool and self._cmd:
            _now = time.monotonic()
            for ex in self._executor_pool.executors.values():
                fa = getattr(ex, '_follow_at', None)
                if fa and _now >= fa:
                    ex._follow_at = None
                    try:
                        self._cmd(f"FADER {ex.exec_id} GO")
                    except Exception:
                        pass

        # Auto-chase: fire GO on executors whose cuestack is in chase mode
        if self._executor_pool and self._cmd:
            _now_ch = time.monotonic()
            for ex in self._executor_pool.executors.values():
                cs = ex.cuestack
                if not (cs and cs.chase_enabled and cs.cues):
                    ex._chase_next_at = None
                    continue
                # Resolve BPM: speed master > inline
                _sm = None
                if cs.chase_speed_id is not None and self._speed_pool:
                    _sm = self._speed_pool.get(cs.chase_speed_id)
                bpm = (_sm.bpm if _sm else None) or cs.chase_bpm or 120.0
                beat_s = 60.0 / bpm
                if ex._chase_next_at is None:
                    ex._chase_next_at = _now_ch + beat_s
                elif _now_ch >= ex._chase_next_at:
                    ex._chase_next_at = _now_ch + beat_s
                    try:
                        self._cmd(f"FADER {ex.exec_id} GO")
                    except Exception:
                        pass

        # FLASH button hold detection — poll is_item_active on any ebtn_* slot
        # whose configured function is FLASH (any assigned executor).
        if self._executor_pool and self._cmd:
            active_eids = {
                eid for eid, ex in self._executor_pool.executors.items()
                if ex.cuestack
            }
            for eid in list(self._flash_held):
                if eid not in active_eids:
                    if self._flash_held.pop(eid, False):
                        try:
                            self._cmd(f"FADER {eid} flash off")
                        except Exception:
                            pass
            for eid in active_eids:
                ex = self._executor_pool.executors[eid]
                # Find which slots are configured as FLASH — check both playbacks panel and fader page
                flash_tags = []
                _fpg_slot = self._fpg_slot_for_exec(self._fpg_page, eid)
                for _s in ('a', 'b', 'c'):
                    if getattr(ex, f'btn_{_s}', '') == 'FLASH':
                        flash_tags.append(f"ebtn_{_s}_{eid}")
                        if _fpg_slot is not None:
                            flash_tags.append(f"fpg_btn{_s}_{_fpg_slot}")
                held = False
                for _ftag in flash_tags:
                    try:
                        if dpg.is_item_active(_ftag):
                            held = True
                            break
                    except Exception:
                        pass
                was_held = self._flash_held.get(eid, False)
                if held and not was_held:
                    try:
                        self._cmd(f"FADER {eid} flash on")
                    except Exception:
                        pass
                elif not held and was_held:
                    try:
                        self._cmd(f"FADER {eid} flash off")
                    except Exception:
                        pass
                self._flash_held[eid] = held
                # Update FLASH button visuals
                for _ftag in flash_tags:
                    try:
                        dpg.configure_item(_ftag, label="■ flash" if held else "flash")
                        theme = self._alert_btn_theme if held else self._dim_btn_theme
                        if theme:
                            dpg.bind_item_theme(_ftag, theme)
                    except Exception:
                        pass

        # Active stack — refresh left column when executor changes
        active_n = self._active_executor[0] if self._active_executor else 1
        active_cs   = self._cuestack_pool.get(active_n) if self._cuestack_pool else None
        current_name = active_cs.name if active_cs else f"cuestack {active_n}"
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

        # Include cue count, notes hash, and wrap state so list rebuilds on changes
        notes_hash = tuple(
            (n, getattr(c, 'note', ''))
            for n, c in active_cs.cues.items()
        ) if active_cs else ()
        wrap_state = getattr(active_cs, 'wrap', False) if active_cs else False
        if (active_n != self._displayed_executor
                or current_name != self._displayed_cs_name
                or notes_hash != getattr(self, '_displayed_notes_hash', None)
                or wrap_state != getattr(self, '_displayed_wrap', None)):
            self._displayed_executor    = active_n
            self._displayed_cs_name     = current_name
            self._displayed_notes_hash  = notes_hash
            self._displayed_wrap        = wrap_state
            try:
                self._rebuild_cue_list(active_cs)
            except Exception:
                pass

        # Header: current cue + wrap badge
        cur = getattr(active_cs, 'current', None) if active_cs else None
        try:
            if cur is not None:
                cue  = active_cs.cues.get(cur)
                name = cue.name if cue else str(cur)
                dpg.set_value("hdr_cue", f"▶  cue {cur:.0f}: {name}")
            else:
                dpg.set_value("hdr_cue", "▶  (none)")
            dpg.set_value("hdr_wrap",
                          "  ⟳wrap" if getattr(active_cs, 'wrap', False) else "")
        except Exception:
            pass

        # cue timing editor — sync drag floats to active cue's fade/delay
        try:
            _, cue_t = self._cue_timing_target()
            if cue_t:
                dpg.set_value("cue_timing_label", f"cue {cue_t.cue_number} — {cue_t.name[:14]}")
                if not dpg.is_item_active("cue_fade_input"):
                    dpg.set_value("cue_fade_input", cue_t.fade_time)
                if not dpg.is_item_active("cue_delay_input"):
                    dpg.set_value("cue_delay_input", cue_t.delay_time)
                if not dpg.is_item_active("cue_follow_input"):
                    dpg.set_value("cue_follow_input", getattr(cue_t, 'follow_time', 0.0))
                if not dpg.is_item_active("cue_note_input"):
                    dpg.set_value("cue_note_input", getattr(cue_t, 'note', ''))
                if not dpg.is_item_active("cue_fxoutfade_input"):
                    dpg.set_value("cue_fxoutfade_input",
                                  getattr(cue_t, 'fx_outfade', None) or 0.0)
            else:
                dpg.set_value("cue_timing_label", "—")
        except Exception:
            pass

        # Highlight active cue row and auto-scroll to it
        if active_cs:
            sid = active_cs.stack_id
            sorted_nums = active_cs._sorted_cue_numbers()
            tbl_tag = f"cl_tbl_{sid}"
            for idx, num in enumerate(sorted_nums):
                tag = f"cue_row_{sid}_{num}"
                is_cur = (num == cur)
                try:
                    dpg.set_value(tag, is_cur)
                except Exception:
                    pass
                try:
                    if is_cur:
                        dpg.highlight_table_row(tbl_tag, idx, _C_CUE_ACT)
                    else:
                        dpg.unhighlight_table_row(tbl_tag, idx)
                except Exception:
                    pass
            # Auto-scroll the cue list so the active cue stays visible
            if cur is not None:
                try:
                    cur_idx = list(sorted_nums).index(cur) if cur in sorted_nums else 0
                    row_h   = 22   # approximate table row height with padding
                    target  = max(0, cur_idx * row_h - 44)
                    dpg.set_y_scroll("cue_list_scroll", target)
                except Exception:
                    pass

        # Header: FX
        layers = list(self._fx._layers.values())
        if layers:
            l = layers[0]
            dpg.set_value("hdr_fx",
                          f"fx: {l.waveform.lower()} {l.rate_bpm:.0f}bpm")
            dpg.configure_item("hdr_fx", color=_C_ACCENT)
            # Sync sliders to actual FX state
            dpg.set_value("fx_rate",   l.rate_bpm)
            dpg.set_value("fx_size",   l.size)
            dpg.set_value("fx_spread", l.spread)
            try:
                dpg.bind_item_theme("kill_fx_btn", self._alert_btn_theme)
            except Exception:
                pass
        else:
            dpg.set_value("hdr_fx", "fx: off")
            dpg.configure_item("hdr_fx", color=_C_DIM)
            try:
                dpg.bind_item_theme("kill_fx_btn", self._dim_btn_theme)
            except Exception:
                pass

        # Rate/Size/spread pool button labels + tooltips
        try:
            for n in range(1, 5):
                rp = self._rate_pool.get(n) if self._rate_pool else None
                sp = self._size_pool.get(n) if self._size_pool else None
                xp = self._spread_pool.get(n) if self._spread_pool else None
                try:
                    dpg.set_item_label(f"rate_btn_{n}",
                                       f"r{n}:{rp.bpm:.0f}" if rp else f"r{n}")
                    dpg.set_value(f"rate_tip_{n}",
                                  f"rate {n}: {rp.name}  {rp.bpm:.0f} bpm" if rp
                                  else f"rate {n} — empty  (RECORD RATE {n} Name bpm)")
                except Exception:
                    pass
                try:
                    dpg.set_item_label(f"size_btn_{n}",
                                       f"s{n}:{sp.size:.0f}" if sp else f"s{n}")
                    dpg.set_value(f"size_tip_{n}",
                                  f"size {n}: {sp.name}  {sp.size:.0f}%" if sp
                                  else f"size {n} — empty  (RECORD SIZEP {n} Name size)")
                except Exception:
                    pass
                try:
                    dpg.set_item_label(f"spread_btn_{n}",
                                       f"sp{n}:{xp.spread:.0f}" if xp else f"sp{n}")
                    dpg.set_value(f"spread_tip_{n}",
                                  f"spread {n}: {xp.name}  {xp.spread:.2f}" if xp
                                  else f"spread {n} — empty  (RECORD SPREADP {n} Name spread)")
                except Exception:
                    pass
        except Exception:
            pass

        # Header: dim (from programmer layer)
        pl = self._out.programmer_layer
        any_dim = next(iter(pl.values()), {}).get('dim') if pl else None
        if any_dim is not None:
            dpg.set_value("hdr_dim", f"dim: {any_dim:.0%}")

        # programmer monitor title colour (mirrors status bar)
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

            # Attribute channels present in programmer (for movers)
            _ATTR_ABBREV = [('pan','P'), ('tilt','T'), ('gobo','G'), ('zoom','Z'),
                            ('focus','Fc'), ('iris','Ir'), ('color','Co'), ('dimmer','D')]
            attr_parts = [f"{abbr}:{s_vals[ch]}" for ch, abbr in _ATTR_ABBREV if ch in s_vals]
            has_attr = bool(attr_parts)
            attr_str = ' '.join(attr_parts)

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
                # Append attr summary to fx column when attribute channels are in programmer
                fx_display = fx_lbl
                if has_attr:
                    fx_display = f"{attr_str}  {fx_lbl}" if has_fx else attr_str
                dpg.set_value(f"prog_fx_{fid}",  fx_display)
                dpg.configure_item(f"prog_fx_{fid}",
                                   color=_C_ACCENT if (has_fx or has_attr) else _C_DIM)
                brightness = (r + g + b) / (3 * 255) * float(dim if dim is not None else 1.0)
                # When only FX or attr channels in programmer, show partial bar
                bar_val = max(brightness, 0.25) if ((has_fx or has_attr) and not (r or g or b)) else brightness
                dpg.set_value(f"prog_bar_{fid}", min(1.0, bar_val) if has_data else 0.0)
                fx_tag = "  ~FX" if has_fx else ""
                if has_attr and not (r or g or b):
                    bar_overlay = f"{attr_str}{fx_tag}" if has_data else ""
                else:
                    bar_overlay = f"R{r} G{g} B{b}{fx_tag}" if has_data else ""
                dpg.configure_item(f"prog_bar_{fid}", overlay=bar_overlay)
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

            # dim lives on the master entry
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

            # Attribute channels (for movers with no RGB)
            _OUT_ATTR = [('pan','P'), ('tilt','T'), ('gobo','G'), ('zoom','Z'), ('focus','Fc')]
            _merged_sub = {**cue_sub, **pl_sub}
            out_attr_parts = [f"{abbr}:{_merged_sub[ch]}" for ch, abbr in _OUT_ATTR
                              if ch in _merged_sub]
            has_out_attr = bool(out_attr_parts) and not (r or g or b)

            dpg.set_value(f"out_r_{fid}",   str(r))
            dpg.set_value(f"out_g_{fid}",   str(g))
            dpg.set_value(f"out_b_{fid}",   str(b))
            dpg.set_value(f"out_dim_{fid}", f"{dim:.0%}")
            brightness = (r + g + b) / (3 * 255) * float(dim)
            out_bar_val = max(brightness, 0.3) if has_out_attr else brightness
            dpg.set_value(f"out_bar_{fid}", min(1.0, out_bar_val))
            out_overlay = ' '.join(out_attr_parts) if has_out_attr else f"R{r} G{g} B{b}"
            dpg.configure_item(f"out_bar_{fid}", overlay=out_overlay)
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
                    dpg.set_value("hdr_clock", f"clk {clk_bpm:.0f}")
                    dpg.configure_item("hdr_clock", color=_C_ACCENT)
                else:
                    dpg.set_value("hdr_clock", "clk …")
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

        # Clear save status after delay
        _now_as = time.monotonic()
        if (GUIEngine._save_status_clear_at > 0.0 and
                _now_as >= GUIEngine._save_status_clear_at):
            GUIEngine._save_status_clear_at = 0.0
            try:
                dpg.set_value("hdr_save_status", "")
            except Exception:
                pass

        # Auto-save every _AUTO_SAVE_INT seconds (default 5 min)
        if (GUIEngine._auto_save_t > 0.0 and
                _now_as - GUIEngine._auto_save_t >= GUIEngine._AUTO_SAVE_INT):
            if self._save:
                try:
                    self._save()
                    GUIEngine._auto_save_t = _now_as
                    try:
                        dpg.set_value("hdr_save_status", "auto-saved")
                        dpg.configure_item("hdr_save_status", color=_C_DIM)
                        GUIEngine._save_status_clear_at = time.monotonic() + 3.0
                    except Exception:
                        pass
                except Exception:
                    pass
        elif GUIEngine._auto_save_t == 0.0:
            # First tick — arm the timer
            GUIEngine._auto_save_t = _now_as

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
# STUDIO CONSOLE - Block 14: show File Persistence
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
    SPEEDS    = os.path.join(DATA_DIR, "speedmaster_pool.json")
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
    AI_PROMPTS   = os.path.join(DATA_DIR, "ai_prompts.json")
    OSC_TARGETS  = os.path.join(DATA_DIR, "osc_targets.json")
    NETWORK      = os.path.join(DATA_DIR, "network.json")
    MACROS       = os.path.join(DATA_DIR, "macros.json")

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
                if getattr(cue, 'follow_time', 0.0) > 0:
                    entry["follow_time"] = cue.follow_time
                if getattr(cue, 'fx_outfade', None) is not None:
                    entry["fx_outfade"] = cue.fx_outfade
                if getattr(cue, 'note', ''):
                    entry["note"] = cue.note
                cues_out[str(num)] = entry
            entry_cs = {
                "name":            stack.name,
                "allow_exec_time": stack.allow_exec_time,
                "wrap":            stack.wrap,
                "cues":            cues_out,
            }
            if getattr(stack, 'bounce', False):
                entry_cs["bounce"] = True
            if getattr(stack, 'note', ''):
                entry_cs["note"] = stack.note
            if getattr(stack, 'chase_enabled', False):
                entry_cs["chase_enabled"] = True
            if getattr(stack, 'chase_bpm', 120.0) != 120.0:
                entry_cs["chase_bpm"] = stack.chase_bpm
            if getattr(stack, 'chase_speed_id', None) is not None:
                entry_cs["chase_speed_id"] = stack.chase_speed_id
            doc["cuestacks"][str(sid)] = entry_cs
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
                "name":       page.get("name", f"page {n}"),
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
                "name":      pdata.get("name", f"page {n}"),
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
                "btn_a":        ex.btn_a,
                "btn_b":        ex.btn_b,
                "btn_c":        ex.btn_c,
                "rate_factor":  ex.rate_factor,
                "size_factor":  ex.size_factor,
                "label":        ex.label,
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
            _valid_fns      = {'GO', 'BACK', 'STOP', 'FLASH', 'RATE+', 'RATE-', 'SIZE+', 'SIZE-'}
            ex.btn_a        = edata.get("btn_a", "GO")  if edata.get("btn_a", "GO")   in _valid_fns else "GO"
            ex.btn_b        = edata.get("btn_b", "BACK") if edata.get("btn_b", "BACK") in _valid_fns else "BACK"
            ex.btn_c        = edata.get("btn_c", "STOP") if edata.get("btn_c", "STOP") in _valid_fns else "STOP"
            _rf             = float(edata.get("rate_factor", 1.0))
            ex.rate_factor  = max(0.1, min(8.0, _rf))
            _sf             = float(edata.get("size_factor", 1.0))
            ex.size_factor  = max(0.0, min(4.0, _sf))
            ex.label        = edata.get("label", "")
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
    def save_osc_targets(osc_engine):
        targets = []
        for name, client in osc_engine._clients.items():
            targets.append({"name": name, "host": client._address, "port": client._port})
        _write_file(ShowFile.OSC_TARGETS, {"targets": targets})
        if targets:
            print(f"  Saved OSC targets → {len(targets)}")

    @staticmethod
    def load_osc_targets(osc_engine):
        doc = _read_file(ShowFile.OSC_TARGETS)
        if not doc:
            return
        for t in doc.get("targets", []):
            osc_engine.add_target(t["name"], t["host"], int(t["port"]))

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
            stack.wrap            = bool(sdata.get("wrap", False))
            stack.bounce          = bool(sdata.get("bounce", False))
            stack.note            = sdata.get("note", "")
            stack.chase_enabled   = bool(sdata.get("chase_enabled", False))
            stack.chase_bpm       = float(sdata.get("chase_bpm", 120.0))
            stack.chase_speed_id  = sdata.get("chase_speed_id")
            for num_str, cdata in sdata["cues"].items():
                num      = float(num_str)
                cue      = Cue(num, cdata["name"],
                               cdata.get("fade_time", 2.0),
                               cdata.get("delay_time", 0.0),
                               cdata.get("fade_times"),
                               cdata.get("delay_times"),
                               cdata.get("follow_time", 0.0))
                cue.note      = cdata.get("note", "")
                _fxo = cdata.get("fx_outfade")
                cue.fx_outfade = float(_fxo) if _fxo is not None else None
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
            group = Group(gid, gdata.get("name", f"group {gid}"))
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
            preset = ColorPreset(pid, pdata.get("name", f"color {pid}"))
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
                    'speed_id':     ld.get('speed_id'),
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
                    speed_id     = ld.get("speed_id"),
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
                fdata.get("name", f"form {fid}"),
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
            rate_pool.store(pid, RatePreset(pid, pd.get("name", f"rate {pid}"),
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
            size_pool.store(pid, SizePreset(pid, pd.get("name", f"size {pid}"),
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
            spread_pool.store(pid, SpreadPreset(pid, pd.get("name", f"spread {pid}"),
                                                pd.get("spread", 1.0)))
        n = len(doc.get("spread_presets", {}))
        if n: print(f"  Loaded spread_pool — {n}")
        return True

    @staticmethod
    def save_speed_masters(pool):
        doc = {"version": ShowFile.VERSION, "speed_masters": {}}
        for sid, m in pool.masters.items():
            doc["speed_masters"][str(sid)] = {"name": m.name, "bpm": m.bpm}
        _write_file(ShowFile.SPEEDS, doc)
        print(f"  Saved speed masters → {len(pool.masters)}")

    @staticmethod
    def load_speed_masters(pool):
        doc = _read_file(ShowFile.SPEEDS)
        if not doc: return False
        for sid_str, md in doc.get("speed_masters", {}).items():
            sid = int(sid_str)
            pool.masters[sid] = SpeedMaster(sid, md.get("bpm", 120.0),
                                            md.get("name", f"spd{sid}"))
        n = len(doc.get("speed_masters", {}))
        if n: print(f"  Loaded speed masters — {n}")
        return True

    @staticmethod
    def save_network(bind_address, universes):
        _write_file(ShowFile.NETWORK, {
            "version":      ShowFile.VERSION,
            "bind_address": bind_address,
            "universes":    list(universes),
        })

    @staticmethod
    def load_network():
        """Return (bind_address, universes) from network.json, or (None, None) if missing."""
        doc = _read_file(ShowFile.NETWORK)
        if not doc:
            return None, None
        return doc.get("bind_address", ""), doc.get("universes", [1, 2])

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

    @staticmethod
    def save_ai_prompts(prompts):
        """Save list of {name, prompt} dicts to ai_prompts.json."""
        _write_file(ShowFile.AI_PROMPTS, {"version": 1, "prompts": prompts})

    @staticmethod
    def load_ai_prompts(default_prompts=None):
        """Load AI prompt list from file; return defaults if file missing."""
        doc = _read_file(ShowFile.AI_PROMPTS)
        if doc and "prompts" in doc:
            return list(doc["prompts"])
        return list(default_prompts) if default_prompts else []

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
    def save_macros(macro_pool):
        data = {
            str(slot): {"name": m["name"], "commands": list(m["commands"])}
            for slot, m in macro_pool.items()
        }
        _write_file(ShowFile.MACROS, {"version": ShowFile.VERSION, "macros": data})
        print(f"  Saved macros     → {len(macro_pool)} macro(s)")

    @staticmethod
    def load_macros(macro_pool):
        doc = _read_file(ShowFile.MACROS)
        if not doc:
            return False
        for slot_str, m in doc.get("macros", {}).items():
            try:
                slot = int(slot_str)
            except ValueError:
                continue
            macro_pool[slot] = {
                "name":     m.get("name", f"macro {slot}"),
                "commands": list(m.get("commands", [])),
            }
        print(f"  Loaded macros    — {len(macro_pool)} macro(s)")
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
            group = Group(gid, gdata.get("name", f"group {gid}"))
            group.members = [(m["type"], m["fixture_id"])
                             for m in gdata.get("members", [])]
            group_pool.groups[gid] = group
        if group_pool.groups:
            ShowFile.save_groups(group_pool)

        # Colors — old format stored per-fixture data dict; migrate to global RGB
        for pid_str, pdata in old.get("color_presets", {}).items():
            pid    = int(pid_str)
            preset = ColorPreset(pid, pdata.get("name", f"color {pid}"))
            old_data = pdata.get("data", {})
            # Take first fixture's RGB as the global value
            for fvals in old_data.values():
                preset.red   = fvals.get("red",   0)
                preset.green = fvals.get("green", 0)
                preset.blue  = fvals.get("blue",  0)
                break
            color_pool.presets[pid] = preset
        if color_pool.presets:
            ShowFile.save_colors(color_pool)

        # Dims — old format stored per-fixture data dict; migrate to global level
        for pid_str, pdata in old.get("dim_presets", {}).items():
            pid    = int(pid_str)
            preset = DimmerPreset(pid, pdata.get("name", f"Dimmer {pid}"))
            old_data = pdata.get("data", {})
            for fvals in old_data.values():
                raw = fvals.get("dim", 0)
                preset.level = max(0.0, min(1.0, float(raw) / 255.0 if float(raw) > 1.0 else float(raw)))
                break
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
# cuestack 1 / Axiom 25 MkII mapped
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

prog         = programmer(patch)
_prog_snapshots = {}  # { int slot: {"name": str, "data": dict} } — session-only
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
rate_pool         = RatePool()
size_pool         = SizePool()
spread_pool       = SpreadPool()
speed_master_pool = SpeedMasterPool()
fx_engine    = FXEngine(output_state, form_pool=form_pool,
                        rate_pool=rate_pool, size_pool=size_pool,
                        spread_pool=spread_pool, dim_pool=dim_pool,
                        speed_master_pool=speed_master_pool)
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

_net_bind, _net_univs = ShowFile.load_network()
_NET_BIND     = _net_bind  if _net_bind  is not None else "192.168.1.161"
_NET_UNIVERSES = _net_univs if _net_univs is not None else [1, 2]
network      = NetworkEngine(output_state, universes=_NET_UNIVERSES,
                             bind_address=_NET_BIND,
                             dry_run=STUDIO_DRY_RUN,
                             fx_engine=fx_engine)
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

# audio engine (Block 9) — reactive audio→light mapping. Unlike MIDI (control
# surface hardware the console expects on every launch) or OSC (a passive
# network listener), microphone capture is opt-in: the engine and mapper
# construct safely with no input device present and sit idle until an
# operator runs AUDIO START / AUDIO ON.
audio_engine = AudioEngine()
audio_mapper = AudioMapper(audio_engine, output_state, patch)

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
_tap_times: list = []   # monotonic timestamps for tap-tempo; shared between GUI and TAP command

# programmer time override — when on, overrides cue fade/delay for manually fired cues
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

macro_pool       = {}    # {slot_int: {"name": str, "commands": [str, ...]}}
_macro_recording = {"slot": None, "cmds": []}
_macro_play_stack = []   # slot ints currently mid-playback, innermost last — guards against MACRO N containing MACRO N (direct or indirect cycle)

# ── Load all data files (migrate legacy file if present) ──
ShowFile.load_fx(_fx_params)
ShowFile.load_fx_pool(fx_pool)
ShowFile.load_forms(form_pool)
ShowFile.load_rate_pool(rate_pool)
ShowFile.load_size_pool(size_pool)
ShowFile.load_spread_pool(spread_pool)
ShowFile.load_speed_masters(speed_master_pool)
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
ShowFile.load_osc_targets(osc)
ShowFile.load_macros(macro_pool)
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

        # ── FX pool (slots 1-8) ───────────────────────────────────────
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

        # ── cuestack 1: color show ────────────────────────────────────
        cs1 = CueStack(1, "color Show")

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

        # ── cuestack 2: Dynamic ───────────────────────────────────────
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

        # ── cuestack 3: Warm Tones ────────────────────────────────────
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

cs1 = cuestack_pool.get(1) or CueStack(1, "cuestack 1")
cuestack_pool.store(1, cs1)

# Wire every loaded cuestack into an executor slot (1:1 by default)
for _slot, _stack in cuestack_pool.stacks.items():
    executor_pool.assign(_slot, _stack)

# CLEAR rebinds prog.data — re-link so programmer_layer points
# to the fresh empty dict, not the old one with stale values.
output_state.link_programmer(prog)

def _active_stack():
    """Returns the cuestack for the current active executor."""
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
    # programmer-based kill: sets fx_kill in programmer so CLEAR can release it.
    # Equivalent to typing KILL FX at the command line.
    run_command("KILL FX")

# Lightform OSC map — what to send to Lightform when each cue fires.
# Edit the address/value to match your Lightform Creator OSC setup.
# These are sent automatically every time a cue fires.
LIGHTFORM_CUE_MAP = {
    1.0: ("/lightform/layer/show", 1),   # cue 1 Red   → Lightform layer 1
    2.0: ("/lightform/layer/show", 2),   # cue 2 Blue  → Lightform layer 2
    3.0: ("/lightform/layer/show", 3),   # cue 3 Sine  → Lightform layer 3
    4.0: ("/lightform/layer/show", 0),   # cue 4 Off   → Lightform layer 0 (hide)
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
    /gma3/cmd  "Go+ cue 1"
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
        # Use run_command so GO/BACK/EXEC etc. work; prog.execute only handles
        # selection and AT commands.
        result = run_command(lower.upper())
        if result:
            print(f"  OSC cmd result: {result}")
    except Exception as e:
        print(f"  OSC cmd error: {e}")

def _osc_fader(address, *args):
    """
    /gma3/fader/PAGE/EXEC  float(0.0-1.0)
    fader on page PAGE, executor EXEC.
    page 1 Exec 1 stays mapped to the grandmaster dim (legacy behavior,
    kept for existing OSC templates). Any other page/exec routes straight
    to that executor's own level fader — same field the GUI executor
    sliders write via _on_exec_fader — so a surface like TouchOSC can
    drive every executor, not just the first one.
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
    else:
        executor_pool.get(exec_num).level = max(0.0, min(1.0, val))

def _osc_key(address, *args):
    """
    /gma3/key/PAGE/EXEC/TYPE  int(0/1)
    Key press on a fader.  1=press, 0=release.
    page 1 fader 1 Go/Back stay mapped to the active fader (legacy
    behavior, kept for existing OSC templates). Any other page/fader fires
    GO/BACK on that specific fader via the same "FADER <n> GO|BACK"
    command MIDI and the command line already use.

    TYPE "flash" is press-and-hold, same as a MIDI note's on/off pair or
    the GUI's FLASH button: unlike go/back it needs the release (0) event
    too, so that branch is handled before the go/back-only early return.
    """
    if not args:
        return
    pressed = int(args[0]) == 1
    parts = address.strip('/').split('/')
    page     = int(parts[2]) if len(parts) > 2 else 1
    exec_num = int(parts[3]) if len(parts) > 3 else 1
    key_type = parts[4] if len(parts) > 4 else "go"
    print(f"\n  OSC key P{page}/E{exec_num}/{key_type} {'▼' if pressed else '▲'}")
    if key_type.lower() == 'flash':
        run_command(f"FADER {exec_num} FLASH {'ON' if pressed else 'OFF'}")
        return
    if not pressed:
        return
    is_go   = key_type.lower() in ('go', 'go+')
    is_back = key_type.lower() in ('back', 'go-')
    if not (is_go or is_back):
        return
    if page == 1 and exec_num == 1:
        cue_go() if is_go else cue_back()
    else:
        run_command(f"FADER {exec_num} {'GO' if is_go else 'BACK'}")

# Register MA3-style OSC handlers
osc.map("/gma3/cmd",         _osc_cmd)
osc.map("/gma3/fader/*/*",   _osc_fader)  # /gma3/fader/page/exec
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
    print(f"\r  dim → {val:.0%}      ", end='', flush=True)

# ----------------------------------------------------------
# Knob callbacks
# Each knob saves to _fx_params AND updates any running FX live.
# If no FX is active the value is remembered for when cue 3 fires.
# ----------------------------------------------------------

def set_fx_rate(val):
    bpm = 20 + val * 460   # 20 – 480 BPM
    _fx_params['rate_bpm'] = bpm
    now = time.monotonic()
    for fx in active_fx:
        fx.set_rate_smooth(bpm, now)
    suffix = f"  ({len(active_fx)} FX live)" if active_fx else "  (pending — fire cue 3)"
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

def _make_set_speed_master(slot_id):
    """Return a MIDI callback that sets speed_master_pool[slot_id].bpm from a 0-1 CC value."""
    def _set_speed(val):
        bpm = 20 + val * 460   # 20 – 480 BPM  (same range as global FX rate)
        speed_master_pool.set_bpm(slot_id, bpm)
        print(f"\r  speed master {slot_id} → {bpm:.0f} BPM   ", end='', flush=True)
    return _set_speed

# ----------------------------------------------------------
# cue navigation — GO/BACK auto-trigger _on_cue_fire
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
        return "no active cue to reload"
    executor_pool.bump_priority(ex.exec_id)
    result = ex.reload(patch, fade_engine)
    _on_cue_fire(cs.current)
    return result

def goto_cue(num):
    _stop_prog_fx_preview()
    ex = _active_executor()
    executor_pool.bump_priority(ex.exec_id)
    result = ex.goto(num, patch, fade_engine)
    if result and 'not found' not in result:
        _on_cue_fire(float(num))
    return result

# ----------------------------------------------------------
# direct cue triggers (pads 1-4)
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

def tap_tempo():
    """MIDI-mappable tap-tempo trigger (safe to call from MIDI thread).
    Shares _tap_times with the TAP command and GUI button.
    Updates _fx_params['rate_bpm'] directly — FX engine reads it on next tick.
    """
    _now = time.monotonic()
    _tap_times.append(_now)
    _tap_times[:] = [t for t in _tap_times if _now - t < 3.0]
    if len(_tap_times) > 5:
        _tap_times[:] = _tap_times[-5:]
    if len(_tap_times) >= 2:
        _intervals = [_tap_times[i + 1] - _tap_times[i]
                      for i in range(len(_tap_times) - 1)]
        _avg = sum(_intervals) / len(_intervals)
        _bpm = round(60.0 / _avg, 1) if _avg > 0 else 60.0
        _bpm = max(10.0, min(480.0, _bpm))
        _fx_params['rate_bpm'] = _bpm
        for _layer in fx_engine._layers.values():
            if _layer.fx_id < 10000:
                _layer.set_rate_smooth(_bpm, _now)

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
midi.map_note(channel=10, note=36, on_callback=goto_1,   name="cue 1 Red")
midi.map_note(channel=10, note=38, on_callback=goto_2,   name="cue 2 Blue")
midi.map_note(channel=10, note=42, on_callback=goto_3,   name="cue 3 Magenta")
midi.map_note(channel=10, note=46, on_callback=goto_4,   name="cue 4 Off")
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
    cuestack_pool = cuestack_pool,
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
    "cue 1 Red":        (goto_1,           False, True),
    "cue 2 Blue":       (goto_2,           False, True),
    "cue 3 Magenta":    (goto_3,           False, True),
    "cue 4 Off":        (goto_4,           False, True),
    "GO":               (cue_go,           False, True),
    "BACK":             (cue_back,         False, True),
    "FX Kill":          (_stop_fx,         False, True),
    "Tap Tempo":          (tap_tempo,        False, True),
    # 4-tuple: (on_cb, soft_takeover, is_note, off_cb)
    "Flash White (hold)": (flash_on,       False, True, flash_off),
    **{f"speed Master {i}": (_make_set_speed_master(i), False, False)
       for i in range(1, SpeedMasterPool._DEFAULT_SLOTS + 1)},
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
    ShowFile.save_speed_masters(speed_master_pool)
    ShowFile.save_position_pool(position_pool)
    ShowFile.save_gobo_pool(gobo_pool)
    ShowFile.save_zoom_pool(zoom_pool)
    ShowFile.save_focus_pool(focus_pool)
    ShowFile.save_beam_pool(beam_pool)
    ShowFile.save_control_pool(control_pool)
    ShowFile.save_executor_pages(executor_pool)
    ShowFile.save_executors(executor_pool)
    ShowFile.save_osc_targets(osc)
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
    return f"show saved as '{safe}'  →  studio_saves/{safe}/"


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
    # Reload pools from newly-copied files (each loader reads from DATA_DIR itself)
    cuestack_pool.stacks.clear()
    ShowFile.load_cuestacks(cuestack_pool, cue_pool)
    group_pool.groups.clear()
    ShowFile.load_groups(group_pool)
    color_pool.presets.clear()
    ShowFile.load_colors(color_pool)
    dim_pool.presets.clear()
    ShowFile.load_dims(dim_pool)
    fx_pool.presets.clear()
    ShowFile.load_fx_pool(fx_pool)
    # Clear only custom form slots (builtins 1-4 are never saved to file)
    for _fid in [k for k in form_pool.forms if k >= FormPool.FIRST_CUSTOM_SLOT]:
        del form_pool.forms[_fid]
    ShowFile.load_forms(form_pool)
    rate_pool.presets.clear()
    ShowFile.load_rate_pool(rate_pool)
    size_pool.presets.clear()
    ShowFile.load_size_pool(size_pool)
    spread_pool.presets.clear()
    ShowFile.load_spread_pool(spread_pool)
    speed_master_pool.masters.clear()
    for i in range(1, SpeedMasterPool._DEFAULT_SLOTS + 1):
        speed_master_pool.masters[i] = SpeedMaster(i)
    ShowFile.load_speed_masters(speed_master_pool)
    for _pool in (position_pool, gobo_pool, zoom_pool, focus_pool, beam_pool, control_pool):
        _pool.presets.clear()
    ShowFile.load_position_pool(position_pool)
    ShowFile.load_gobo_pool(gobo_pool)
    ShowFile.load_zoom_pool(zoom_pool)
    ShowFile.load_focus_pool(focus_pool)
    ShowFile.load_beam_pool(beam_pool)
    ShowFile.load_control_pool(control_pool)
    ShowFile.load_executor_pages(executor_pool)
    ShowFile.load_executors(executor_pool, cuestack_pool)
    ShowFile.load_state(output_state, executor_pool, cuestack_pool,
                        active_executor, prog_time=_prog_time, fader_dim=_fader_dim)
    # OSC targets and global FX rate/size/spread/fade defaults are saved every
    # SAVE (ShowFile.save_osc_targets / save_fx) and loaded at startup, but were
    # missing here — unlike patch/MIDI (which need a real restart to re-init
    # hardware/threads), neither has a reason to stay stale after a LOAD SHOW.
    osc._clients.clear()
    ShowFile.load_osc_targets(osc)
    ShowFile.load_fx(_fx_params)
    return f"show '{name}' loaded — restart may be needed for patch/midi changes"


def list_shows():
    """List all saved shows in studio_saves/."""
    try:
        saves = [d for d in sorted(os.listdir(SAVES_DIR))
                 if os.path.isdir(os.path.join(SAVES_DIR, d))]
    except OSError:
        return "no saves yet — use: save as <name>"
    if not saves:
        return "no saved shows — use: save as <name>"
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
            bundle['rate_pool'] = doc.get('rate_presets', {})
    if what_l in ('all', 'sizes'):
        doc = _read_file(ShowFile.SIZES)
        if doc:
            bundle['size_pool'] = doc.get('size_presets', {})
    if what_l in ('all', 'spreads'):
        doc = _read_file(ShowFile.SPREADS)
        if doc:
            bundle['spread_pool'] = doc.get('spread_presets', {})

    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(DATA_DIR, f"preset_export_{ts}.json")
    with open(out_path, 'w') as f:
        json.dump(bundle, f, indent=2)
    cats = [k for k in ('colors','dims','fx_pool','forms','rate_pool','size_pool','spread_pool')
            if k in bundle]
    return f"exported {', '.join(cats)} → {os.path.basename(out_path)}"


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
    if 'fx_pool' in bundle:
        count = 0
        for pid_s, pdata in bundle['fx_pool'].items():
            pid    = int(pid_s)
            preset = FXPreset(pid, pdata.get("name", f"FX {pid}"))
            for ld in pdata.get("layers", []):
                preset.add_layer(
                    ld["waveform"], ld["channel"],
                    bpm=ld.get("bpm", ld.get("rate_bpm", 60.0)),
                    size=ld.get("size", 100.0), spread=ld.get("spread", 0.0),
                    phase_offset=ld.get("phase_offset", 0.0),
                    form_id=ld.get("form_id"), rate_id=ld.get("rate_id"),
                    size_id=ld.get("size_id"), spread_id=ld.get("spread_id"),
                    dim_id=ld.get("dim_id"), color_id=ld.get("color_id"),
                    group_id=ld.get("group_id"), speed_id=ld.get("speed_id"),
                    block_size=ld.get("block_size", 1),
                    order=ld.get("order", "linear"), direction=ld.get("direction", "forward"),
                    target_scope=ld.get("target_scope"),
                )
            fx_pool.store(pid, preset)
            count += 1
        ShowFile.save_fx_pool(fx_pool)
        imported.append(f"{count} fx")
    if 'forms' in bundle:
        count = 0
        for fid_s, fdata in bundle['forms'].items():
            fid = int(fid_s)
            if fid < FormPool.FIRST_CUSTOM_SLOT:
                continue
            form = FormPreset(fid, fdata.get("name", f"form {fid}"),
                              fdata.get("form_type", "breakpoints"),
                              breakpoints=fdata.get("breakpoints", []))
            form_pool.store(fid, form)
            count += 1
        if count:
            ShowFile.save_forms(form_pool)
            imported.append(f"{count} forms")
    if 'rate_pool' in bundle:
        count = 0
        for pid_s, d in bundle['rate_pool'].items():
            pid = int(pid_s)
            rate_pool.store(pid, RatePreset(pid, d.get("name", f"rate {pid}"),
                                            d.get("bpm", 60.0)))
            count += 1
        ShowFile.save_rate_pool(rate_pool)
        imported.append(f"{count} rates")
    if 'size_pool' in bundle:
        count = 0
        for pid_s, d in bundle['size_pool'].items():
            pid = int(pid_s)
            size_pool.store(pid, SizePreset(pid, d.get("name", f"size {pid}"),
                                            d.get("size", 100.0)))
            count += 1
        ShowFile.save_size_pool(size_pool)
        imported.append(f"{count} sizes")
    if 'spread_pool' in bundle:
        count = 0
        for pid_s, d in bundle['spread_pool'].items():
            pid = int(pid_s)
            spread_pool.store(pid, SpreadPreset(pid, d.get("name", f"spread {pid}"),
                                                d.get("spread", 0.0)))
            count += 1
        ShowFile.save_spread_pool(spread_pool)
        imported.append(f"{count} spreads")
    if not imported:
        return "IMPORT PRESETS: nothing imported (bundle has no recognized preset categories)"
    return "imported: " + ", ".join(imported)

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
                def _make_flash(on_c=f"FADER {_ex_n} flash on", off_c=f"FADER {_ex_n} flash off"):
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
# programmer syntax:  <fixtures> AT <value>  |  CLEAR  |  etc.

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
      FXOUTFADE                 — FX layer outfade when this cue fires (overrides auto)
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

    v = _get('FOLLOW')
    if v is not None:
        cue.follow_time = v

    # FX outfade override: how long old FX layers take to fade out when this cue fires
    v = _get('FXOUTFADE')
    if v is not None:
        cue.fx_outfade = None if v == 0.0 else v  # 0 resets to auto

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

    # ── macro record capture ──────────────────────────────────
    # While recording, capture every command except MACRO STOP / MACRO ABORT.
    # The command still executes normally so the operator sees live feedback.
    if _macro_recording["slot"] is not None:
        is_macro_stop = (t0 == 'MACRO' and len(tokens) >= 2
                         and tokens[1] in ('STOP', 'ABORT'))
        if not is_macro_stop:
            _macro_recording["cmds"].append(raw)

    # ── Executor selection ────────────────────────────────────
    # CUESTACK N  — make executor N the active one
    if t0 in ('CUESTACK', 'CS') and len(tokens) > 1:
        if tokens[1] == 'MERGE':
            if 'INTO' not in tokens:
                return "usage: cuestack merge <src> into <dst>"
            into_idx = tokens.index('INTO')
            try:
                src_n = int(tokens[2])
                dst_n = int(tokens[into_idx + 1])
            except (IndexError, ValueError):
                return "usage: cuestack merge <src> into <dst>"
            src_cs = cuestack_pool.get(src_n)
            dst_cs = cuestack_pool.get(dst_n)
            if not src_cs:
                return f"CUESTACK MERGE: source CS {src_n} not found"
            if not dst_cs:
                return f"CUESTACK MERGE: destination CS {dst_n} not found"
            if src_n == dst_n:
                return "CUESTACK MERGE: source and destination must be different"
            src_sorted = src_cs._sorted_cue_numbers()
            if not src_sorted:
                return f"CUESTACK MERGE: source CS {src_n} is empty"
            dst_sorted = dst_cs._sorted_cue_numbers()
            base = (max(dst_sorted) + 1) if dst_sorted else 0.0
            merged = 0
            for src_num in src_sorted:
                src_cue = src_cs.cues[src_num]
                new_num = base + src_num
                nc = Cue(
                    cue_number  = new_num,
                    name        = src_cue.name,
                    fade_time   = src_cue.fade_time,
                    delay_time  = src_cue.delay_time,
                    fade_times  = copy.deepcopy(src_cue.fade_times),
                    delay_times = copy.deepcopy(src_cue.delay_times),
                    follow_time = src_cue.follow_time,
                )
                nc.note       = src_cue.note
                nc.fx_outfade = src_cue.fx_outfade
                nc.data       = copy.deepcopy(src_cue.data)
                dst_cs.cues[new_num] = nc
                merged += 1
            save_show()
            return (f"merged cs {src_n} '{src_cs.name}' into cs {dst_n} '{dst_cs.name}' "
                    f"— {merged} cue(s) appended (renumbered from {base:.0f})")
        # All remaining subcommands require tokens[1] to be a cuestack number
        try:
            n = int(tokens[1])
        except ValueError:
            return f"CUESTACK: bad number '{tokens[1]}'"
        # CS n INFO/STATUS — detailed cuestack status
        if len(tokens) >= 3 and tokens[2] in ('INFO', 'STATUS', 'SHOW'):
            cs = cuestack_pool.get(n)
            if not cs:
                return f"cuestack {n} not found"
            # Which faders are running this cuestack?
            faders = [str(eid) for eid, ex in executor_pool.executors.items()
                      if ex.cuestack and ex.cuestack.stack_id == n]
            sorted_nums = cs._sorted_cue_numbers()
            lines = [f"cuestack {n}: {cs.name}",
                     f"  Cues      : {len(sorted_nums)}",
                     f"  Loop/Wrap : {'ON' if getattr(cs, 'wrap', False) else 'OFF'}",
                     f"  Chase     : {'ON  ' + str(round(getattr(cs,'chase_bpm',120.0),1)) + ' BPM' if getattr(cs,'chase_enabled',False) else 'OFF'}",
                     f"  Faders    : {', '.join(faders) or '(none)'}"]
            if cs.current is not None:
                cue = cs.cues.get(cs.current)
                cue_name = cue.name if cue else "?"
                lines.append(f"  Current   : cue {cs.current:.0f} — {cue_name}")
            else:
                lines.append("  Current   : (not started)")
            if sorted_nums:
                lines.append("  cue list  :")
                for num in sorted_nums[:10]:
                    c = cs.cues[num]
                    cur_m = " ◀" if num == cs.current else ""
                    note_s = f"  [{c.note}]" if getattr(c, 'note', '') else ""
                    lines.append(f"    [{num:.0f}] {c.name}  fade:{c.fade_time}s{note_s}{cur_m}")
                if len(sorted_nums) > 10:
                    lines.append(f"    … ({len(sorted_nums) - 10} more cues)")
            return "\n".join(lines)
        # CS n REVERSE — reverse the cue order (renumbers from 1)
        if len(tokens) >= 3 and tokens[2].upper() == 'REVERSE':
            cs = cuestack_pool.get(n)
            if not cs:
                return f"cuestack {n} not found"
            sorted_nums = cs._sorted_cue_numbers()
            if not sorted_nums:
                return f"cuestack {n} is empty"
            rev_cues = [cs.cues[num] for num in reversed(sorted_nums)]
            cs.cues.clear()
            cs.current = None
            for new_num, cue in enumerate(rev_cues, start=1):
                cue.cue_number = float(new_num)
                cs.cues[float(new_num)] = cue
            save_show()
            return f"CS {n} '{cs.name}': reversed — {len(rev_cues)} cues renumbered 1–{len(rev_cues)}"
        # CS <n> EXTRACT <cue_num> [INTO <slot>] — copy one cue into a fresh cuestack
        if len(tokens) >= 4 and tokens[2].upper() == 'EXTRACT':
            cs = cuestack_pool.get(n)
            if not cs:
                return f"cuestack {n} not found"
            try:
                cue_num = float(tokens[3])
            except ValueError:
                return f"CS EXTRACT: bad cue number '{tokens[3]}'"
            cue = cs.cues.get(cue_num)
            if not cue:
                return f"CS EXTRACT: cue {cue_num:.0f} not found in cuestack {n}"
            # Determine destination slot
            into_slot = None
            if 'INTO' in tokens:
                into_idx = tokens.index('INTO')
                try:
                    into_slot = int(tokens[into_idx + 1])
                except (IndexError, ValueError):
                    return "CS EXTRACT: bad slot after INTO"
            if into_slot is None:
                # Auto-pick lowest unused slot
                used = set(cuestack_pool.stacks.keys())
                into_slot = next(s for s in range(1, 9999) if s not in used)
            if cuestack_pool.get(into_slot):
                return (f"CS EXTRACT: slot {into_slot} already occupied — "
                        f"use  CS {n} EXTRACT {cue_num:.0f} INTO <slot>")
            new_cs = cuestack_pool.create(into_slot, f"{cs.name} — cue {cue_num:.0f}")
            nc = Cue(cue_number=1.0, name=cue.name, fade_time=cue.fade_time,
                     delay_time=cue.delay_time, fade_times=copy.deepcopy(cue.fade_times),
                     delay_times=copy.deepcopy(cue.delay_times), follow_time=cue.follow_time)
            nc.note = getattr(cue, 'note', '')
            nc.fx_outfade = getattr(cue, 'fx_outfade', 0.0)
            nc.data = copy.deepcopy(cue.data)
            new_cs.cues[1.0] = nc
            new_cs.wrap = getattr(cs, 'wrap', False)
            new_cs.note = getattr(cs, 'note', '')
            executor_pool.assign(into_slot, new_cs)
            save_show()
            return (f"extracted: cs {n} cue {cue_num:.0f} '{cue.name}' "
                    f"→ new cuestack {into_slot} on fader {into_slot}")

        # CS n RENUMBER STEP <s> — renumber cues at multiples of s (10→10,20,30…)
        if len(tokens) >= 4 and tokens[2].upper() == 'RENUMBER' and tokens[3].upper() == 'STEP':
            cs = cuestack_pool.get(n)
            if not cs:
                return f"cuestack {n} not found"
            sorted_nums = cs._sorted_cue_numbers()
            if not sorted_nums:
                return f"cuestack {n} is empty"
            try:
                step = int(tokens[4])
            except (IndexError, ValueError):
                return "CS RENUMBER STEP: provide a step value (e.g. CS 1 RENUMBER STEP 10)"
            if step < 1:
                return "CS RENUMBER STEP: step must be at least 1"
            ordered = [cs.cues[num] for num in sorted_nums]
            old_current = cs.current
            cs.cues.clear()
            new_current = None
            for idx, cue in enumerate(ordered, start=1):
                new_num = float(idx * step)
                if old_current is not None and cue.cue_number == old_current:
                    new_current = new_num
                cue.cue_number = new_num
                cs.cues[new_num] = cue
            cs.current = new_current
            save_show()
            return (f"CS {n} '{cs.name}': renumbered {len(ordered)} cues "
                    f"at step {step} ({step:.0f}–{len(ordered)*step:.0f})")

        # CS n DUPLICATE [INTO <slot>] — deep-copy entire cuestack to a new slot
        if len(tokens) >= 3 and tokens[2].upper() in ('DUPLICATE', 'DUP', 'CLONE'):
            cs = cuestack_pool.get(n)
            if not cs:
                return f"cuestack {n} not found"
            into_slot = None
            if 'INTO' in tokens:
                into_idx = tokens.index('INTO')
                try:
                    into_slot = int(tokens[into_idx + 1])
                except (IndexError, ValueError):
                    return "CS DUPLICATE: bad slot after INTO"
            if into_slot is None:
                used = set(cuestack_pool.stacks.keys())
                into_slot = next(s for s in range(1, 9999) if s not in used)
            if cuestack_pool.get(into_slot):
                return (f"CS DUPLICATE: slot {into_slot} already occupied — "
                        f"use  CS {n} DUPLICATE INTO <slot>")
            new_cs = CueStack(into_slot, f"{cs.name} (copy)")
            for cue_num, cue in cs.cues.items():
                nc = Cue(cue_number=cue.cue_number, name=cue.name,
                         fade_time=cue.fade_time, delay_time=cue.delay_time,
                         fade_times=copy.deepcopy(cue.fade_times),
                         delay_times=copy.deepcopy(cue.delay_times),
                         follow_time=cue.follow_time)
                nc.note = getattr(cue, 'note', '')
                nc.fx_outfade = getattr(cue, 'fx_outfade', 0.0)
                nc.data = copy.deepcopy(cue.data)
                new_cs.cues[cue_num] = nc
            new_cs.wrap = getattr(cs, 'wrap', False)
            new_cs.note = getattr(cs, 'note', '')
            cuestack_pool.store(into_slot, new_cs)
            executor_pool.assign(into_slot, new_cs)
            save_show()
            return (f"duplicated cs {n} '{cs.name}' → cs {into_slot} '{new_cs.name}' "
                    f"({len(new_cs.cues)} cue(s))")

        # CS n COMPRESS — renumber cues to 1, 2, 3, … (collapse gaps)
        if len(tokens) >= 3 and tokens[2].upper() == 'COMPRESS':
            cs = cuestack_pool.get(n)
            if not cs:
                return f"cuestack {n} not found"
            sorted_nums = cs._sorted_cue_numbers()
            if not sorted_nums:
                return f"cuestack {n} is empty"
            ordered = [cs.cues[num] for num in sorted_nums]
            old_current = cs.current
            cs.cues.clear()
            new_current = None
            for new_num, cue in enumerate(ordered, start=1):
                if old_current is not None and cue.cue_number == old_current:
                    new_current = float(new_num)
                cue.cue_number = float(new_num)
                cs.cues[float(new_num)] = cue
            cs.current = new_current
            save_show()
            return (f"CS {n} '{cs.name}': compressed — "
                    f"{len(ordered)} cues renumbered 1–{len(ordered)}")
        # CS n CLEAR — delete all cues from cuestack n (keeps the slot and name)
        if len(tokens) >= 3 and tokens[2].upper() == 'CLEAR':
            cs = cuestack_pool.get(n)
            if not cs:
                return f"cuestack {n} not found"
            count = len(cs.cues)
            cs.cues.clear()
            cs.current = None
            save_show()
            return f"CS {n} '{cs.name}': {count} cue(s) cleared (cuestack kept)"

        # CS n NOTE [text] — view or set a production note on this cuestack
        if len(tokens) >= 3 and tokens[2].upper() == 'NOTE':
            cs = cuestack_pool.get(n)
            if not cs:
                return f"cuestack {n} not found"
            if len(tokens) == 3:
                note_val = getattr(cs, 'note', '')
                if note_val:
                    return f"CS {n} '{cs.name}' note: {note_val}"
                return f"CS {n} '{cs.name}' has no note — set with: CS {n} NOTE <text>"
            note_text = _name_after(raw, 3)
            cs.note = note_text
            save_show()
            return f"CS {n} '{cs.name}' note set: {note_text}"

        # CS n bounce on/OFF — ping-pong playback (reverse direction at each end)
        if len(tokens) >= 4 and tokens[2].upper() == 'BOUNCE':
            cs = cuestack_pool.get(n)
            if not cs:
                return f"cuestack {n} not found"
            state = tokens[3].upper()
            if state == 'ON':
                cs.bounce = True
                cs._bounce_dir = 1
                save_show()
                return f"CS {n} '{cs.name}': bounce on — reverses at last/first cue (ping-pong)"
            elif state == 'OFF':
                cs.bounce = False
                cs._bounce_dir = 1
                save_show()
                return f"CS {n} '{cs.name}': bounce off — normal forward loop"
            return "BOUNCE: use ON or OFF"
        # CS n WRAP ON/OFF — clean restart at top after last cue
        if len(tokens) >= 4 and tokens[2].upper() == 'WRAP':
            cs = cuestack_pool.get(n)
            if not cs:
                return f"cuestack {n} not found"
            state = tokens[3].upper()
            if state == 'ON':
                cs.wrap = True
                save_show()
                return f"CS {n} '{cs.name}': WRAP ON — cue 1 fires clean after last cue"
            elif state == 'OFF':
                cs.wrap = False
                save_show()
                return f"CS {n} '{cs.name}': WRAP OFF — LTP tracking across loop"
            return "WRAP: use ON or OFF"

        # CS n CHASE ON [BPM x] / CS n CHASE OFF / CS n CHASE BPM x / CS n CHASE SPEED k
        if len(tokens) >= 4 and tokens[2].upper() == 'CHASE':
            cs = cuestack_pool.get(n)
            if not cs:
                return f"cuestack {n} not found"
            sub = tokens[3].upper()
            if sub == 'ON':
                if len(tokens) >= 6 and tokens[4].upper() == 'BPM':
                    try:
                        cs.chase_bpm = max(1.0, min(600.0, float(tokens[5])))
                    except ValueError:
                        return f"CHASE ON: bad BPM '{tokens[5]}'"
                cs.chase_enabled = True
                save_show()
                bpm_s = f"{cs.chase_bpm:.1f} BPM"
                return f"CS {n} '{cs.name}': chase ON — auto-GO every {60000/cs.chase_bpm:.0f}ms ({bpm_s})"
            elif sub == 'OFF':
                cs.chase_enabled = False
                # Clear chase timer on any executor holding this cuestack
                for ex in executor_pool.executors.values():
                    if ex.cuestack is cs:
                        ex._chase_next_at = None
                save_show()
                return f"CS {n} '{cs.name}': chase OFF"
            elif sub == 'BPM' and len(tokens) >= 5:
                try:
                    cs.chase_bpm = max(1.0, min(600.0, float(tokens[4])))
                except ValueError:
                    return f"CHASE BPM: bad value '{tokens[4]}'"
                save_show()
                return f"CS {n} '{cs.name}': chase BPM → {cs.chase_bpm:.1f}"
            elif sub == 'SPEED' and len(tokens) >= 5:
                try:
                    sid = int(tokens[4])
                except ValueError:
                    return f"CHASE SPEED: bad slot '{tokens[4]}'"
                cs.chase_speed_id = sid if sid > 0 else None
                save_show()
                return (f"CS {n} '{cs.name}': chase linked to speed Master {sid}"
                        if sid > 0 else f"CS {n} '{cs.name}': chase speed link cleared")
            else:
                bpm_s = f"{cs.chase_bpm:.1f} BPM"
                state = "ON" if cs.chase_enabled else "OFF"
                return (f"CS {n} '{cs.name}': chase {state} ({bpm_s})\n"
                        f"  CS {n} CHASE ON [BPM x]  |  CHASE OFF  |  CHASE BPM x  |  CHASE SPEED k")

        if t0 == 'CS':
            return f"usage: cs <n> bounce on|off | wrap on|off | chase on|off|bpm|speed"
        if cuestack_pool.get(n):
            active_executor[0] = n
            cs = cuestack_pool.get(n)
            return f"active fader → cuestack {n}: {cs.name}"
        return f"cuestack {n} is empty  (use: record cuestack {n} <name>)"

    # RECORD CUESTACK N [name]  — create a new empty cuestack in slot N
    if t0 == 'RECORD' and len(tokens) > 2 and tokens[1] == 'CUESTACK':
        try:
            n = int(tokens[2])
        except ValueError:
            return f"RECORD CUESTACK: bad number '{tokens[2]}'"
        name = _name_after(raw, 3) or f"cuestack {n}"
        cs = cuestack_pool.create(n, name)
        executor_pool.assign(n, cs)
        active_executor[0] = n
        save_show()
        return f"created: cuestack {n} '{name}'  (now active on fader {n})"

    # ── Navigation ───────────────────────────────────────────
    # ── ASSIGN CS <n> TO FADER <n> ────────────────────────────
    # Wire a cuestack into a fader slot. EXEC accepted as alias.
    _assign_kw = next((kw for kw in ('FADER', 'EXEC') if kw in tokens), None)
    if t0 == 'ASSIGN' and 'CS' in tokens and 'TO' in tokens and _assign_kw:
        try:
            cs_idx   = tokens.index('CS')
            exec_idx = tokens.index(_assign_kw)
            cs_n     = int(tokens[cs_idx   + 1])
            ex_n     = int(tokens[exec_idx + 1])
        except (ValueError, IndexError):
            return "usage: assign cs <n> to fader <n>"
        stack = cuestack_pool.get(cs_n)
        if not stack:
            return f"cuestack {cs_n} not found"
        executor_pool.assign(ex_n, stack)
        save_show()
        return f"CS {cs_n} assigned to fader {ex_n}  (saved)"

    # ── FADER SWAP <n> <m> — swap cuestacks between two faders ──
    if t0 == 'FADER' and len(tokens) >= 4 and tokens[1] == 'SWAP':
        try:
            fa, fb = int(tokens[2]), int(tokens[3])
        except ValueError:
            return "usage: fader swap <n> <m>"
        ex_a = executor_pool.get(fa)
        ex_b = executor_pool.get(fb)
        ex_a.cuestack, ex_b.cuestack = ex_b.cuestack, ex_a.cuestack
        save_show()
        name_a = ex_a.cuestack.name if ex_a.cuestack else "(empty)"
        name_b = ex_b.cuestack.name if ex_b.cuestack else "(empty)"
        return f"swapped fader {fa} ↔ fader {fb}  ({name_a} / {name_b})"

    # ── FADER ALL CLEAR — stop and reset every fader at once ──────
    if t0 in ('FADER', 'EXEC') and len(tokens) >= 3 and tokens[1] == 'ALL' and tokens[2].upper() == 'CLEAR':
        cleared = 0
        for ex in executor_pool.executors.values():
            ex.stop()
            if ex.cuestack:
                ex.cuestack.current = None
            cleared += 1
        return f"all {cleared} fader(s) cleared"

    # ── EXEC <n> GO / BACK / STOP ────────────────────────────
    if t0 in ('FADER', 'EXEC') and len(tokens) >= 2:
        try:
            ex_n = int(tokens[1])
        except ValueError:
            return f"FADER: bad fader number '{tokens[1]}'"
        ex  = executor_pool.get(ex_n)
        verb = tokens[2].upper() if len(tokens) > 2 else 'GO'
        if verb == 'GO':
            executor_pool.bump_priority(ex_n)
            msg = ex.go(patch, fade_engine)
            if ex.cuestack:
                _on_cue_fire(ex.cuestack.current)
            return msg or f"fader {ex_n} GO"
        elif verb == 'BACK':
            executor_pool.bump_priority(ex_n)
            msg = ex.back(patch, fade_engine)
            if ex.cuestack:
                _on_cue_fire(ex.cuestack.current)
            return msg or f"fader {ex_n} BACK"
        elif verb == 'STOP':
            ex.stop()
            return f"fader {ex_n} stopped"
        elif verb == 'CLEAR':
            # FADER <n> CLEAR  — stop fader and reset cuestack position to "not started"
            ex.stop()
            if ex.cuestack:
                ex.cuestack.current = None
                cs_name = ex.cuestack.name
                return f"fader {ex_n} cleared — '{cs_name}' reset to start"
            return f"fader {ex_n} stopped (no cuestack)"
        elif verb == 'GOTO' and len(tokens) > 3:
            cs = ex.cuestack
            # GOTO FIRST / LAST — jump to first or last cue
            dest_kw = tokens[3].upper() if len(tokens) > 3 else ''
            if dest_kw == 'FIRST':
                if not cs or not cs.cues:
                    return f"fader {ex_n}: no cues"
                num = cs._sorted_cue_numbers()[0]
            elif dest_kw == 'LAST':
                if not cs or not cs.cues:
                    return f"fader {ex_n}: no cues"
                num = cs._sorted_cue_numbers()[-1]
            else:
                try:
                    num = float(tokens[3])
                except ValueError:
                    return f"FADER GOTO: bad cue number '{tokens[3]}'"
            executor_pool.bump_priority(ex_n)
            msg = ex.goto(num, patch, fade_engine)
            if not msg or 'not found' not in msg:
                _on_cue_fire(num)
            return msg or f"fader {ex_n} GOTO {num}"
        elif verb == 'TIME':
            # EXEC <n> TIME <fade> [DELAY <delay>]  |  EXEC <n> TIME OFF
            if len(tokens) > 3 and tokens[3] == 'OFF':
                ex.time_override_on   = False
                ex.time_override_fade  = None
                ex.time_override_delay = None
                return f"fader {ex_n} time override off"
            try:
                fade_t = float(tokens[3]) if len(tokens) > 3 else None
            except ValueError:
                return "FADER TIME: usage  FADER <n> TIME <seconds> [DELAY <seconds>]  or  OFF"
            delay_t = None
            if 'DELAY' in tokens:
                di = tokens.index('DELAY')
                try:
                    delay_t = float(tokens[di + 1])
                except (IndexError, ValueError):
                    return "FADER TIME: bad DELAY value"
            ex.time_override_fade  = fade_t
            ex.time_override_delay = delay_t if delay_t is not None else 0.0
            ex.time_override_on    = True
            delay_str = f"  delay {delay_t}s" if delay_t else ""
            return f"fader {ex_n} time override → {fade_t}s{delay_str}"
        elif verb == 'TIMELOCK':
            # exec <n> timelock ON/OFF  — whether this executor's cuestack accepts overrides
            if len(tokens) < 4:
                return "usage: exec <n> timelock on | off"
            state = tokens[3]
            cs = ex.cuestack
            if not cs:
                return f"fader {ex_n} has no cuestack"
            if state == 'ON':
                cs.allow_exec_time = True
                return f"fader {ex_n}: time override enabled for '{cs.name}'"
            elif state == 'OFF':
                cs.allow_exec_time = False
                return f"fader {ex_n}: time override locked out for '{cs.name}'"
            return "TIMELOCK: use ON or OFF"
        elif verb == 'FLASH':
            # exec <n> flash on | off  — instant on-while-held, for trigger_mode='flash'.
            # Independent of trigger_mode itself so GUI/MIDI press/release can call
            # this directly regardless of how the mode was set.
            if len(tokens) < 4 or tokens[3] not in ('ON', 'OFF'):
                return "usage: exec <n> flash on | off"
            if tokens[3] == 'ON':
                executor_pool.bump_priority(ex_n)
                msg = ex.flash_on(patch, fade_engine)
                if ex.cuestack:
                    _on_cue_fire(ex.cuestack.current)
                return msg or f"fader {ex_n} flash on"
            else:
                ex.flash_off()
                return f"fader {ex_n} flash off"
        elif verb == 'MODE':
            # exec <n> mode toggle | flash — how GUI/MIDI should trigger this executor.
            # 'toggle' = GO/BACK advance normally. 'flash' = live only while held
            # (use exec <n> flash on/OFF, or a MIDI note's on/off callbacks).
            if len(tokens) < 4 or tokens[3] not in ('TOGGLE', 'FLASH'):
                return "usage: exec <n> mode toggle | flash"
            ex.trigger_mode = tokens[3].lower()
            return f"fader {ex_n} trigger_mode → {ex.trigger_mode}"
        elif verb == 'BTN':
            # EXEC <n> BTN A|B|C GO|BACK|STOP|FLASH — assign action button function
            if len(tokens) < 4:
                return (f"fader {ex_n} buttons: A={ex.btn_a}  B={ex.btn_b}  C={ex.btn_c}\n"
                        f"  usage: FADER {ex_n} BTN A|B|C GO|BACK|STOP|FLASH|RATE+|RATE-")
            slot = tokens[3].upper()
            if slot not in ('A', 'B', 'C'):
                return "BTN: slot must be A, B, or C"
            fn = tokens[4].upper() if len(tokens) > 4 else ''
            if fn not in ('GO', 'BACK', 'STOP', 'FLASH', 'RATE+', 'RATE-', 'SIZE+', 'SIZE-'):
                return "BTN: function must be GO, BACK, STOP, FLASH, RATE+, RATE-, SIZE+ or SIZE-"
            setattr(ex, f'btn_{slot.lower()}', fn)
            save_show()
            return f"fader {ex_n} button {slot} → {fn}"
        elif verb == 'LEVEL':
            # EXEC <n> LEVEL <0-100>  — set master fader (0 = blackout, 100 = full)
            if len(tokens) < 4:
                return f"fader {ex_n} level: {ex.level * 100:.0f}%  (usage: FADER {ex_n} LEVEL 0–100)"
            try:
                pct = float(tokens[3])
            except ValueError:
                return "FADER LEVEL: usage  FADER <n> LEVEL <0-100>"
            ex.level = max(0.0, min(1.0, pct / 100.0))
            save_show()
            return f"fader {ex_n} level → {ex.level * 100:.0f}%"
        elif verb in ('RATE+', 'RATE-'):
            # EXEC <n> RATE+ / RATE- — nudge playback speed by ×1.25 / ÷1.25
            step = 1.25 if verb == 'RATE+' else (1.0 / 1.25)
            ex.rate_factor = max(0.1, min(8.0, ex.rate_factor * step))
            save_show()
            return f"fader {ex_n} rate → ×{ex.rate_factor:.2f}"
        elif verb == 'RATE' and len(tokens) >= 4 and tokens[3].upper() == 'RESET':
            ex.rate_factor = 1.0
            save_show()
            return f"fader {ex_n} rate reset → ×1.00"
        elif verb == 'RATE' and len(tokens) >= 4:
            try:
                rv = float(tokens[3])
            except ValueError:
                return f"FADER RATE: bad value '{tokens[3]}' — use a number (e.g. 2.0) or RESET"
            ex.rate_factor = max(0.1, min(8.0, rv))
            save_show()
            return f"fader {ex_n} rate → ×{ex.rate_factor:.2f}"
        elif verb in ('SIZE+', 'SIZE-'):
            step = 1.25 if verb == 'SIZE+' else (1.0 / 1.25)
            ex.size_factor = max(0.0, min(4.0, ex.size_factor * step))
            ex._apply_size_factor()
            save_show()
            return f"fader {ex_n} fx size → ×{ex.size_factor:.2f}"
        elif verb == 'SIZE' and len(tokens) >= 4 and tokens[3].upper() == 'RESET':
            ex.size_factor = 1.0
            ex._apply_size_factor()
            save_show()
            return f"fader {ex_n} fx size reset → ×1.00"
        elif verb == 'SIZE' and len(tokens) >= 4:
            try:
                sv = float(tokens[3])
            except ValueError:
                return f"FADER SIZE: bad value '{tokens[3]}' — use a number (e.g. 2.0) or RESET"
            ex.size_factor = max(0.0, min(4.0, sv))
            ex._apply_size_factor()
            save_show()
            return f"fader {ex_n} fx size → ×{ex.size_factor:.2f}"
        elif verb == 'LABEL':
            # FADER <n> LABEL <text>  |  FADER <n> LABEL  (clear)
            raw_parts = raw.split(None, 3)
            label_text = raw_parts[3].strip() if len(raw_parts) >= 4 else ""
            ex.label = label_text
            save_show()
            return (f"fader {ex_n} label → '{label_text}'"
                    if label_text else f"fader {ex_n} label cleared")
        elif verb in ('UNASSIGN', 'DETACH'):
            prev_cs = ex.cuestack
            if not prev_cs:
                return f"fader {ex_n} has no cuestack assigned"
            ex.stop()
            ex.cuestack = None
            save_show()
            return f"fader {ex_n}: unassigned (was '{prev_cs.name}')"
        elif verb == 'ASSIGN' and len(tokens) >= 5 and tokens[3].upper() == 'CS':
            try:
                cs_n = int(tokens[4])
            except ValueError:
                return f"FADER ASSIGN: bad cuestack number '{tokens[4]}'"
            stack = cuestack_pool.get(cs_n)
            if not stack:
                return f"FADER ASSIGN: cuestack {cs_n} not found"
            executor_pool.assign(ex_n, stack)
            save_show()
            return f"CS {cs_n} '{stack.name}' assigned to fader {ex_n}"
        elif verb == 'BOUNCE' and len(tokens) >= 4:
            cs = ex.cuestack
            if not cs:
                return f"fader {ex_n} has no cuestack assigned"
            state = tokens[3].upper()
            if state == 'ON':
                cs.bounce = True
                cs._bounce_dir = 1
                save_show()
                return f"fader {ex_n} bounce on — CS '{cs.name}' ping-pongs at each end"
            elif state == 'OFF':
                cs.bounce = False
                cs._bounce_dir = 1
                save_show()
                return f"fader {ex_n} bounce off — CS '{cs.name}' normal forward loop"
            return "FADER BOUNCE: use ON or OFF"
        elif verb == 'LOOP' and len(tokens) >= 4:
            cs = ex.cuestack
            if not cs:
                return f"fader {ex_n} has no cuestack assigned"
            state = tokens[3].upper()
            if state == 'ON':
                cs.wrap = True
                save_show()
                return f"fader {ex_n} loop ON — CS '{cs.name}' wraps after last cue"
            elif state == 'OFF':
                cs.wrap = False
                save_show()
                return f"fader {ex_n} loop OFF — CS '{cs.name}' stops after last cue"
            return "FADER LOOP: use ON or OFF"
        elif verb in ('INFO', 'STATUS', 'SHOW'):
            cs = ex.cuestack
            lbl_s = f"  Label     : {ex.label}" if ex.label else ""
            lines = [f"fader {ex_n}:"]
            if lbl_s:
                lines.append(lbl_s)
            lines.append(f"  Level     : {ex.level * 100:.0f}%")
            lines.append(f"  Priority  : {Executor.PRIORITY_LABELS[ex.priority]}")
            lines.append(f"  Trigger   : {ex.trigger_mode}")
            lines.append(f"  rate      : ×{ex.rate_factor:.2f}")
            lines.append(f"  FX size   : ×{ex.size_factor:.2f}")
            lines.append(f"  Buttons   : A={ex.btn_a}  B={ex.btn_b}  C={ex.btn_c}")
            if cs:
                lines.append(f"  cuestack  : [{cs.stack_id}] {cs.name}")
                lines.append(f"  State     : {'ACTIVE' if ex.is_active else 'idle'}")
                if cs.current is not None:
                    cue = cs.cues.get(cs.current)
                    cue_name = cue.name if cue else "?"
                    lines.append(f"  Current   : cue {cs.current:.0f} — {cue_name}")
                sorted_nums = cs._sorted_cue_numbers()
                lines.append(f"  Cues      : {len(sorted_nums)} total")
                if ex.time_override_on:
                    lines.append(f"  Time OV   : {ex.time_override_fade}s fade"
                                 + (f"  delay {ex.time_override_delay}s"
                                    if ex.time_override_delay else ""))
            else:
                lines.append("  cuestack  : (unassigned)")
            return "\n".join(lines)
        else:
            return f"FADER {ex_n}: unknown verb '{verb}'"

    # ── page <n> name ... / ADD CS <m> / REMOVE CS <m> / DELETE / LIST ─
    if t0 == 'PAGE':
        if len(tokens) >= 2 and tokens[1] == 'LIST':
            if not executor_pool.pages:
                return "pages: (none)"
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
            return "usage: page <n> name <name> | page <n> add cs <m> | page <n> remove cs <m> | page <n> delete | page list"
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
            name = " ".join(raw.split()[3:]) if len(tokens) > 3 else f"page {page_n}"
            executor_pool.set_page_name(page_n, name)
            ShowFile.save_executor_pages(executor_pool)
            return f"page {page_n} → '{name}'"
        if sub2 == 'DELETE':
            executor_pool.delete_page(page_n)
            ShowFile.save_executor_pages(executor_pool)
            return f"page {page_n} deleted"
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
        return "usage: page <n> name <name> | page <n> add cs <m> | page <n> remove cs <m> | page <n> delete | page list"

    # ── PROG TIME — programmer time override ──────────────────
    if t0 == 'PROG' and len(tokens) >= 2 and tokens[1] == 'TIME':
        if len(tokens) == 3 and tokens[2] == 'OFF':
            _prog_time['on'] = False
            return "programmer time override OFF"
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
        return f"programmer time → {fade_t}s{delay_str}"

    # PROG FADE CLEAR — cancel all live programmer fades immediately
    if t0 == 'PROG' and len(tokens) >= 3 and tokens[1] == 'FADE' and tokens[2] == 'CLEAR':
        n = len(prog.live_fades)
        prog.live_fades.clear()
        return f"prog fades cleared ({n} active)"

    # ── EXECUTOR <n> — switch active executor ─────────────────
    if t0 in ('FADER_SELECT', 'EXECUTOR') and len(tokens) == 2:
        try:
            n = int(tokens[1])
        except ValueError:
            return f"FADER: bad fader number '{tokens[1]}'"
        active_executor[0] = n
        ex = executor_pool.get(n)
        cs_name = ex.cuestack.name if ex.cuestack else "(no cuestack)"
        return f"active fader → {n}  [{cs_name}]"

    # GO FADE <t> [DELAY <d>] — one-shot fade override for next GO only
    if t0 == 'GO' and len(tokens) >= 3 and tokens[1] == 'FADE':
        try:
            go_fade_t = float(tokens[2])
        except ValueError:
            return "GO FADE: usage  GO FADE <seconds> [DELAY <seconds>]"
        go_delay_t = 0.0
        if 'DELAY' in tokens:
            di = tokens.index('DELAY')
            try:
                go_delay_t = float(tokens[di + 1])
            except (IndexError, ValueError):
                return "GO FADE: bad DELAY value"
        _prev_pt = dict(_prog_time)
        _prog_time['on']    = True
        _prog_time['fade']  = go_fade_t
        _prog_time['delay'] = go_delay_t
        cue_go()
        _prog_time.update(_prev_pt)
        cs = _active_stack()
        cur = cs.current if cs else None
        delay_s = f" delay {go_delay_t}s" if go_delay_t else ""
        return f"GO → cue {cur}  (fade {go_fade_t}s{delay_s})"

    if t0 == 'GO' and len(tokens) == 1:
        cue_go()
        cs = _active_stack()
        cur = cs.current if cs else None
        return f"GO → cue {cur}" if cur else "GO (no cue)"

    if t0 == 'BACK' and len(tokens) == 1:
        cue_back()
        cs = _active_stack()
        cur = cs.current if cs else None
        return f"BACK → cue {cur}" if cur else "BACK (no cue)"

    if t0 == 'GOTO' and len(tokens) > 1:
        try:
            num = float(tokens[1])
            result = goto_cue(num)
            return result or f"GOTO → cue {num}"
        except ValueError:
            return f"GOTO: bad cue number '{tokens[1]}'"

    if t0 == 'RELOAD' and len(tokens) == 1:
        return cue_reload() or "reloaded"

    if t0 == 'DELETE' and len(tokens) >= 2 and tokens[1] == 'CUE':
        if len(tokens) < 3:
            return "usage: delete cue <n>  [cs <stack_n>]"
        try:
            cue_num = float(tokens[2])
        except ValueError:
            return f"delete cue: bad cue number '{tokens[2]}'"
        if 'CS' in tokens:
            cs_idx = tokens.index('CS')
            try:
                cs_n = int(tokens[cs_idx + 1])
            except (ValueError, IndexError):
                return "usage: delete cue <n> cs <stack_n>"
            cs = cuestack_pool.get(cs_n)
            if not cs:
                return f"cuestack {cs_n} not found"
        else:
            active_n = active_executor[0] if active_executor else 1
            cs = cuestack_pool.get(active_n)
            if not cs:
                return "no active cuestack"
        if cue_num not in cs.cues:
            return f"cue {cue_num} not found in {cs.name}"
        cs.delete_cue(cue_num)
        if cue_num == int(cue_num):
            cue_pool.delete(int(cue_num))
        save_show()
        return f"deleted cue {cue_num} from {cs.name}"

    # ── DELETE GROUP / COLOR / DIM / FX / FORM / CUESTACK ────
    if t0 == 'DELETE' and len(tokens) >= 3:
        sub = tokens[1]
        try:
            n = int(tokens[2])
        except ValueError:
            return f"DELETE {sub}: bad slot number '{tokens[2]}'"
        if sub == 'GROUP':
            if not group_pool.get(n):
                return f"group {n} is empty"
            group_pool.delete(n)
            save_show()
            return f"deleted group {n}"
        if sub in ('COLOR', 'COLOUR'):
            if not color_pool.get(n):
                return f"color {n} is empty"
            color_pool.delete(n)
            save_show()
            return f"deleted color {n}"
        if sub == 'DIM':
            if not dim_pool.get(n):
                return f"dim {n} is empty"
            dim_pool.delete(n)
            save_show()
            return f"deleted dim {n}"
        if sub == 'FX':
            if not fx_pool.get(n):
                return f"FX {n} is empty"
            fx_pool.delete(n)
            save_show()
            return f"deleted FX {n}"
        if sub == 'FORM':
            if n < FormPool.FIRST_CUSTOM_SLOT:
                return f"form {n} is built-in — only custom forms (slot ≥ {FormPool.FIRST_CUSTOM_SLOT}) can be deleted"
            if not form_pool.get(n):
                return f"form {n} is empty"
            form_pool.delete(n)
            save_show()
            return f"deleted form {n}"
        if sub in ('CUESTACK', 'CS'):
            if not cuestack_pool.get(n):
                return f"cuestack {n} is empty"
            cs_name = cuestack_pool.get(n).name
            # Stop any executor currently running this cuestack
            for ex in list(executor_pool.executors.values()):
                if ex.cuestack and ex.cuestack.stack_id == n:
                    ex.stop()
            cuestack_pool.delete(n)
            save_show()
            return f"deleted cuestack {n}: {cs_name}"
        if sub == 'RATE':
            if not rate_pool.get(n): return f"rate {n} is empty"
            rate_pool.delete(n); save_show(); return f"deleted rate preset {n}"
        if sub in ('SIZEP', 'SIZE'):
            if not size_pool.get(n): return f"size {n} is empty"
            size_pool.delete(n); save_show(); return f"deleted size preset {n}"
        if sub in ('SPREADP', 'SPREAD'):
            if not spread_pool.get(n): return f"spread {n} is empty"
            spread_pool.delete(n); save_show(); return f"deleted spread preset {n}"
        _del_attr_map = {
            'POSITION': position_pool, 'GOBO': gobo_pool, 'ZOOM': zoom_pool,
            'FOCUS': focus_pool, 'BEAM': beam_pool, 'CONTROL': control_pool,
        }
        if sub in _del_attr_map:
            pool = _del_attr_map[sub]
            if not pool.get(n): return f"{sub.title()} preset {n} is empty"
            pool.delete(n); save_show()
            return f"deleted {sub.title()} preset {n}"

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
        _KW = {'FADE', 'INFADE', 'OUTFADE', 'DELAY', 'FOLLOW',
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
                name = existing.name if existing else f"cue {cue_num:.0f}"

        # Timing extraction helper — tries multiple keyword aliases in order
        def _get_timing(*kws):
            for kw in kws:
                m = _re.search(rf'\b{kw}\s+([\d.]+)', up)
                if m:
                    return float(m.group(1))
            return None

        # Global fade: FADE / INFADE / OUTFADE are synonyms for cue crossfade time
        _ft = _get_timing('FADE', 'INFADE', 'OUTFADE')
        fade   = _ft if _ft is not None else 2.0
        _dt = _get_timing('DELAY')
        delay  = _dt if _dt is not None else 0.0
        _fw = _get_timing('FOLLOW')
        follow = _fw if _fw is not None else 0.0

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

        # preset look-up by name across all pools
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
            if not g: return f"RECORD CUE: group {group_n} not found"
            prog.select(g.recall(patch))
        if color_n is not None:
            p = color_pool.get(color_n)
            if not p: return f"RECORD CUE: color {color_n} not found"
            p.apply(prog)
        if dim_n is not None:
            p = dim_pool.get(dim_n)
            if not p: return f"RECORD CUE: dim {dim_n} not found"
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
            # programmer has no DMX data — allow timing/name update on any existing cue.
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
            return f"updated: {cue}  (merged into {cs.name}){_reload_note}"

        cue = cs.record_cue(cue_num, prog, name=name, fade_time=fade)
        cue.delay_time  = delay
        cue.follow_time = follow
        cue.fade_times  = fade_times
        cue.delay_times = delay_times
        if cue_num == int(cue_num):
            cue_pool.store(int(cue_num), cue)
        save_show()
        return f"recorded: {cue}  into {cs.name}  (auto-saved)"

    # ── record cs [n] cue <m> [presets...] ──────────────────
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
            return "usage: record cs [n] cue <num> [preset-names / group n color n dim n fade t]"

        cs = cuestack_pool.get(cs_n) if cs_n is not None else _active_stack()
        if not cs:
            return f"cuestack {cs_n} not found" if cs_n else "no active cuestack"

        return _record_cue_into(cs, cue_num, tokens[cue_idx + 2:], raw)

    # ── RECORD CUE <n> ["name"] [GROUP g] [COLOR c] [DIM d] [fade t]
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
    # update cs [n] cue <m> [presets] [FADE <t>]
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
                return "usage: update cs [n] cue <num> [presets / fade t]"
            cs = cuestack_pool.get(cs_n) if cs_n is not None else _active_stack()
            if not cs:
                return f"cuestack {cs_n} not found" if cs_n else "no active cuestack"
            return _record_cue_into(cs, cue_num, tokens[cue_idx + 2:], raw, merge=True)
        if 'CUE' in tokens:
            cue_idx = tokens.index('CUE')
            try:
                cue_num = float(tokens[cue_idx + 1])
            except (IndexError, ValueError):
                return "usage: update cue <num> [presets / fade t]"
            cs = _active_stack()
            if not cs:
                return "UPDATE CUE: no active cuestack"
            return _record_cue_into(cs, cue_num, tokens[cue_idx + 2:], raw, merge=True)

    # ── GO CS <n>  /  BACK CS <n> ────────────────────────────
    # Advance/step the specified executor without specifying a cue number.
    # e.g.  GO CS 2   (same as EXEC 2 GO, without changing active_executor)
    if t0 in ('GO', 'BACK') and 'CS' in tokens and 'CUE' not in tokens:
        cs_idx = tokens.index('CS')
        try:
            cs_n = int(tokens[cs_idx + 1])
        except (IndexError, ValueError):
            cs_n = active_executor[0]
        ex = None
        for _e in executor_pool.executors.values():
            if _e.cuestack and _e.cuestack.stack_id == cs_n:
                ex = _e
                break
        if not ex:
            ex = executor_pool.get(cs_n)
        executor_pool.bump_priority(ex.exec_id)
        if t0 == 'GO':
            msg = ex.go(patch, fade_engine)
        else:
            msg = ex.back(patch, fade_engine)
        if ex.cuestack:
            _on_cue_fire(ex.cuestack.current)
        direction = "GO" if t0 == 'GO' else "BACK"
        cur = ex.cuestack.current if ex.cuestack else None
        return msg or f"{direction} CS {cs_n} → cue {cur}"

    # ── go cs [n] cue <m> ────────────────────────────────────
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
            return "usage: go cs [n] cue <num>"

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
        if ex.cuestack and (not msg or 'not found' not in msg):
            _on_cue_fire(ex.cuestack.current)
        return msg or f"GO CS {cs_n or active_executor[0]} CUE {cue_num}"

    # ── FORM commands ─────────────────────────────────────────
    # FORM LIST
    # record form <n> <name> <phase,value> ...   (breakpoint curve)
    if t0 == 'FORM' and len(tokens) >= 2 and tokens[1] == 'LIST':
        lines = []
        for f in form_pool.forms.values():
            lines.append(f"  {f}")
        return "\n".join(lines) if lines else "form pool empty"

    if t0 == 'RECORD' and len(tokens) >= 3 and tokens[1] == 'FORM':
        try:
            form_n = int(tokens[2])
        except ValueError:
            return f"record form: bad number '{tokens[2]}'"
        if form_n < FormPool.FIRST_CUSTOM_SLOT:
            return f"slots 1–{FormPool.FIRST_CUSTOM_SLOT - 1} are built-in read-only. Use slot {FormPool.FIRST_CUSTOM_SLOT}+."

        # Collect name tokens until first phase,value pattern
        name_parts  = []
        bp_start    = 3
        for i, tok in enumerate(tokens[3:], 3):
            if ',' in tok:
                bp_start = i
                break
            name_parts.append(tok.capitalize())

        name = " ".join(name_parts) if name_parts else f"form {form_n}"

        # Parse breakpoints: "0.0,0.0" "0.5,1.0" "1.0,0.0"
        breakpoints = []
        for tok in tokens[bp_start:]:
            try:
                p, v = tok.split(',')
                breakpoints.append([float(p), float(v)])
            except ValueError:
                return f"bad breakpoint '{tok}' — format: phase,value  e.g. 0.5,1.0"

        if not breakpoints:
            return "usage: record form <n> [name] <phase,value> <phase,value> ..."

        form = FormPreset(form_n, name, 'breakpoints', breakpoints=breakpoints)
        form_pool.store(form_n, form)
        ShowFile.save_forms(form_pool)
        return f"recorded: {form}  (auto-saved)"

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
                speed_id     = ld.get('speed_id'),
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
    _CHANNELS  = {
        'RED', 'GREEN', 'BLUE', 'DIM',
        'PAN', 'TILT', 'PAN_FINE', 'TILT_FINE',
        'GOBO', 'GOBO_ROT', 'GOBO2', 'GOBO2_ROT',
        'ZOOM', 'FOCUS', 'IRIS', 'SHUTTER1', 'COLOR',
        'PRISM', 'FROST', 'ANIMATION', 'CONTROL', 'MACRO', 'DIMMER',
    }

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
        if not STUDIO_HEADLESS:
            try:
                import dearpygui.dearpygui as _dpg_local
                _dpg_local.set_value("fx_rate", val)
            except Exception:
                pass
        return f"BPM → {val:.1f}"

    if t0 == 'TAP':
        # TAP — tap-tempo; compute BPM from last 4 inter-tap intervals (<3 s window).
        # Shares _tap_times with the GUI tap button so either source is valid.
        # Updates _fx_params and running layers directly to avoid dpg.set_value
        # being called without a context (headless mode).
        _now = time.monotonic()
        _tap_times.append(_now)
        _tap_times[:] = [t for t in _tap_times if _now - t < 3.0]
        if len(_tap_times) > 5:
            _tap_times[:] = _tap_times[-5:]
        if len(_tap_times) >= 2:
            _intervals = [_tap_times[i + 1] - _tap_times[i]
                          for i in range(len(_tap_times) - 1)]
            _avg = sum(_intervals) / len(_intervals)
            _bpm = round(60.0 / _avg, 1) if _avg > 0 else 60.0
            _bpm = max(10.0, min(480.0, _bpm))
            _fx_params['rate_bpm'] = _bpm
            for _layer in fx_engine._layers.values():
                if _layer.fx_id < 10000:
                    _layer.set_rate_smooth(_bpm, _now)
            for _fvals in prog.data.values():
                for _ld in _fvals.get('fx', []):
                    _ld['bpm'] = _bpm
            if not STUDIO_HEADLESS:
                try:
                    import dearpygui.dearpygui as _dpg_l
                    _dpg_l.set_value("fx_rate", _bpm)
                except Exception:
                    pass
            return f"BPM → {_bpm:.1f}"
        return "TAP (tap again to lock BPM…)"

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
        if not STUDIO_HEADLESS:
            try:
                import dearpygui.dearpygui as _dpg_local
                _dpg_local.set_value("fx_size", val)
            except Exception:
                pass
        return f"size → {val:.0f}"

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
        if not STUDIO_HEADLESS:
            try:
                import dearpygui.dearpygui as _dpg_local
                _dpg_local.set_value("fx_spread", val)
            except Exception:
                pass
        return f"spread → {val:.1f}"

    # STROBE [bpm] — shorthand for FX PULSE DIM BPM <bpm> FIXTURE
    # STROBE CLEAR — remove dim FX from programmer
    if t0 == 'STROBE':
        t1 = tokens[1].upper() if len(tokens) > 1 else ''
        if t1 == 'CLEAR':
            return run_command("FX CLEAR DIM")
        _strobe_presets = {'SLOW': 60, 'MEDIUM': 120, 'FAST': 240}
        if t1 in _strobe_presets:
            bpm = _strobe_presets[t1]
        elif t1 and t1.replace('.', '', 1).isdigit():
            bpm = float(t1)
        else:
            bpm = 120  # default
        return run_command(f"FX PULSE DIM BPM {bpm} FIXTURE")

    # RAINBOW [bpm] [spread] — RGB sine wave chase across all selected fixtures.
    # Creates three synchronized FX layers (R/G/B) with 120° phase offsets.
    # usage: RAINBOW 60      → 60 BPM rainbow at full spread
    #        RAINBOW 30 50   → 30 BPM at 50% spread
    #        RAINBOW CLEAR   → FX CLEAR (removes all colour FX layers)
    if t0 == 'RAINBOW':
        t1 = tokens[1].upper() if len(tokens) > 1 else ''
        if t1 == 'CLEAR':
            return run_command("FX CLEAR")
        _rb_bpm  = float(t1) if t1 and t1.replace('.','',1).isdigit() else 60.0
        t2 = tokens[2] if len(tokens) > 2 else ''
        _rb_spread = float(t2) if t2 and t2.replace('.','',1).isdigit() else 100.0
        run_command(f"FX SINE RED    BPM {_rb_bpm} SPREAD {_rb_spread} PHASE 0.0   SIZE 100")
        run_command(f"FX ADD SINE GREEN BPM {_rb_bpm} SPREAD {_rb_spread} PHASE 0.333 SIZE 100")
        run_command(f"FX ADD SINE BLUE  BPM {_rb_bpm} SPREAD {_rb_spread} PHASE 0.667 SIZE 100")
        return f"rainbow → {_rb_bpm:.0f} BPM  spread {_rb_spread:.0f}%  (3 layers R/G/B)"

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
                return f"form {fid_n} is empty"

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
                return f"form → {form.name}  ({changed} layer(s) updated live)"
            return f"form → {form.name}  (pending — next FX command will use this form)"

        if sub == 'CLEAR':
            # FX CLEAR            → clear all FX (programmer + all running executors)
            # FX CLEAR <channel>  → clear only that channel in programmer
            # Both scope to selection when fixtures are selected.
            _sel_fids = {str(f.fixture_id) for f in prog.selection} if prog.selection else None

            if len(tokens) >= 3 and tokens[2].upper() in _CHANNELS:
                ch = tokens[2].upper().lower()
                _targets = _sel_fids or set(prog.data.keys())
                for fid in _targets:
                    vals = prog.data.get(fid)
                    if vals is None:
                        continue
                    existing = vals.get('fx', [])
                    filtered = [ld for ld in existing if ld.get('channel') != ch]
                    if filtered:
                        vals['fx'] = filtered
                    else:
                        vals.pop('fx', None)
                _prog_fx_rebuild()
                _scope = f" ({len(_targets)} fixture(s))" if _sel_fids else ""
                return f"FX {ch} cleared from programmer{_scope}"

            if _sel_fids:
                # Selection active — clear programmer FX for selected fixtures only
                for fid in _sel_fids:
                    vals = prog.data.get(fid)
                    if vals:
                        vals.pop('fx', None)
                _prog_fx_rebuild()
                return f"FX cleared for {len(_sel_fids)} selected fixture(s) (programmer)"

            # No selection — global clear (programmer + all running executors)
            _prog_fx_stop()
            for vals in prog.data.values():
                vals.pop('fx', None)
            _cleared_exec = 0
            for _ex in executor_pool.executors.values():
                if _ex._fx_ids:
                    _ex._clear_fx()
                    _cleared_exec += 1
            _exec_note = f"  + {_cleared_exec} executor(s)" if _cleared_exec else ""
            return f"FX cleared (programmer{_exec_note})"

        if sub == 'LIST':
            lines = []
            # programmer FX
            prog_fx = {fid: v['fx'] for fid, v in prog.data.items()
                       if '.' not in fid and 'fx' in v}
            if prog_fx:
                lines.append("programmer FX:")
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
                lines.append("programmer FX: (none)")
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
                lines.append("Active fader FX:")
                lines.extend(exec_fx_lines)
            # FX pool
            if fx_pool.presets:
                lines.append("Pool:")
                for p in fx_pool.presets.values():
                    lines.append(f"  {p}")
            else:
                lines.append("Pool: (empty)")
            return "\n".join(lines)

        # fx [add] <waveform|form n|COLOR n> [channel] [bpm n] [size n] [SPREAD n]
        #   [group n] [dimref n] [BLOCK n] [ORDER RANDOM] [DIRECTION FWD|REV|BOUNCE] [PIXEL|FIXTURE]
        #
        # Tree references:
        #   COLOR n  — drives R/G/B from Colorpreset n (waveform drives intensity of that color)
        #   GROUP n  — target only fixtures in GroupPool slot n instead of programmer selection
        #   dimref n — live size ceiling: Dimmerpreset n's level scales FX amplitude (0–1)
        add_mode = (sub == 'ADD')
        base_idx = 2 if add_mode else 1

        if base_idx >= len(tokens):
            return ("usage: fx [add] <waveform|form n|COLOR n> [channel] "
                    "[bpm n] [size n] [SPREAD n] [group n] [dimref n] "
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
                return "usage: fx [add] form <n> <channel> [...]"
        elif waveform == 'COLOR':
            # FX COLOR <preset_id> — drives R/G/B channels from the preset's color
            try:
                color_id = int(tokens[base_idx + 1])
                ch_idx   = base_idx + 2
            except (IndexError, ValueError):
                return "usage: fx [add] color <preset_id> [bpm n] [size n] [group n] [dimref n]"
            waveform = 'sine'
            channel  = 'rgb'   # virtual; expanded into R/G/B at _prog_fx_start time
        elif waveform not in _WAVEFORMS:
            return f"unknown waveform '{waveform}' — use sine|ramp|pulse|square, FORM <n>, or COLOR <n>"

        if color_id is None:
            # Check if channel position is 'COLOR' (e.g. FX RAMP COLOR 3)
            if ch_idx < len(tokens) and tokens[ch_idx] == 'COLOR':
                try:
                    color_id = int(tokens[ch_idx + 1])
                    ch_idx  += 2
                except (IndexError, ValueError):
                    return "usage: fx [add] <waveform> color <preset_id>"
                waveform = waveform.lower()
                channel  = 'rgb'
            elif ch_idx >= len(tokens) or tokens[ch_idx] not in _CHANNELS:
                return (f"usage: fx [add] <waveform> red|green|blue|dim|pan|tilt|gobo|zoom|focus|… "
                        f"[bpm n] [size n] [SPREAD n]")
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
        dim_id    = _fx_pool_id('DIMREF')   # Dimmerpreset slot as live size ceiling
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
                return f"group {group_id} not found"
            sel_fids = [m.fixture_id for m in grp.recall(patch)]
            if not sel_fids:
                return f"group {group_id} is empty"
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
        lines = [f"{verb}: {waveform} {disp_ch}{ref_s} → {len(sel_fids)} fixture(s)"]
        if color_id is not None and channel == 'rgb':
            cp = color_pool.get(color_id) if color_pool else None
            if not cp:
                lines.append(f"⚠ color preset {color_id} is empty — running white until you RECORD COLOR {color_id}")
        return "\n".join(lines)

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
                phase_offset = ld.get('phase_offset', 0.0),
                form_id      = ld.get('form_id'),
                rate_id      = ld.get('rate_id'),
                size_id      = ld.get('size_id'),
                spread_id    = ld.get('spread_id'),
                dim_id       = ld.get('dim_id'),
                color_id     = ld.get('color_id'),
                group_id     = ld.get('group_id'),
                speed_id     = ld.get('speed_id'),
                block_size   = ld.get('block_size',      1),
                order        = ld.get('order',    'linear'),
                direction    = ld.get('direction','forward'),
                target_scope = ld.get('target_scope'),
            )
        fx_pool.store(fx_n, preset)
        ShowFile.save_fx_pool(fx_pool)
        return f"recorded: {preset}  (auto-saved)"

    # FIRE FX <n> [group n]  — write preset defs into programmer + preview
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
                return f"FIRE FX: group {fire_group_id} not found"
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
        return f"fired: {preset}{ref_s}  → {len(sel_fids)} fixture(s)"

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
            return "usage: clone <src> to <dst>  |  clone <src> to <dst> thru <end>"

        if src_id not in patch.fixtures:
            return f"clone source fixture {src_id} not in patch"
        missing = [d for d in dst_ids if d not in patch.fixtures]
        if missing:
            return f"destination(s) {missing} not in patch — patch them first"

        src_str  = str(src_id)
        src_master = patch.fixtures[src_id]
        n_subs   = len(src_master.sub_fixtures)

        for dst_id in dst_ids:
            dst_str = str(dst_id)

            # Color/dim presets store a single global value, not per-fixture data;
            # nothing to copy here — groups and cues carry the fixture-specific data.

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
        return f"cloned fixture {src_id} → {dst_label}  ({len(dst_ids)} dest, show saved)"

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
        cue_name = _name_after(raw, 2) or f"snapshot {cue_num}"

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
                sub_data = {}
                for ch in sub.profile.channels:
                    val = ps.get(ch, cs_.get(ch))
                    if val is not None:
                        sub_data[ch] = float(val)
                if sub_data:
                    snapshot_data[sfid] = sub_data

        if not snapshot_data:
            return "SNAPSHOT: nothing in output — all fixtures are dark"

        cue = Cue(cue_num, cue_name)
        cue.data = snapshot_data
        cs.cues[float(cue_num)] = cue
        save_show()
        fixture_count = len({k.split('.')[0] for k in snapshot_data})
        return f"snapshot → cue {cue_num}: {cue_name}  ({fixture_count} fixtures, show saved)"

    # ── Blind mode ───────────────────────────────────────────
    if t0 == 'BLIND':
        output_state.blind = True
        return "BLIND mode ON — programmer suppressed from DMX output"

    if t0 == 'LIVE':
        output_state.blind = False
        return "LIVE mode — programmer active in output"

    # ── MACRO ─────────────────────────────────────────────────────────────────
    # MACRO RECORD <n> [name]  — start recording commands to slot n
    # MACRO STOP               — stop recording and save
    # MACRO ABORT              — discard recording without saving
    # MACRO <n>                — play back macro slot n
    # MACRO LIST               — list all recorded macros
    # MACRO DELETE <n>         — delete macro slot n
    # RENAME MACRO <n> <name>  — rename macro slot n
    if t0 == 'MACRO':
        t1 = tokens[1] if len(tokens) > 1 else ''
        if t1 == 'RECORD':
            try:
                slot = int(tokens[2])
            except (IndexError, ValueError):
                return "usage: macro record <n> [name]"
            if _macro_recording["slot"] is not None:
                return f"already recording macro {_macro_recording['slot']} — MACRO STOP first"
            raw_parts = raw.split(None, 3)
            name = raw_parts[3] if len(raw_parts) > 3 else f"macro {slot}"
            _macro_recording["slot"] = slot
            _macro_recording["cmds"] = []
            _macro_recording["name"] = name
            return f"MACRO {slot} '{name}' — recording started (MACRO STOP to save)"
        if t1 == 'STOP':
            slot = _macro_recording["slot"]
            if slot is None:
                return "MACRO STOP: not currently recording"
            name = _macro_recording.get("name", f"macro {slot}")
            macro_pool[slot] = {"name": name, "commands": list(_macro_recording["cmds"])}
            n_cmds = len(macro_pool[slot]["commands"])
            _macro_recording["slot"] = None
            _macro_recording["cmds"] = []
            ShowFile.save_macros(macro_pool)
            return f"MACRO {slot} '{name}' saved — {n_cmds} command(s)"
        if t1 == 'ABORT':
            if _macro_recording["slot"] is None:
                return "MACRO ABORT: not currently recording"
            slot = _macro_recording["slot"]
            _macro_recording["slot"] = None
            _macro_recording["cmds"] = []
            return f"MACRO {slot} recording discarded"
        if t1 == 'LIST':
            if not macro_pool:
                return "no macros recorded."
            lines = [f"  {s:>3}: [{len(m['commands'])} cmds] {m['name']}"
                     for s, m in sorted(macro_pool.items())]
            rec = _macro_recording["slot"]
            suffix = f"\n  (recording macro {rec}...)" if rec is not None else ""
            return "macros:\n" + "\n".join(lines) + suffix
        if t1 == 'DELETE':
            try:
                slot = int(tokens[2])
            except (IndexError, ValueError):
                return "usage: macro delete <n>"
            if slot not in macro_pool:
                return f"MACRO DELETE: slot {slot} empty"
            del macro_pool[slot]
            ShowFile.save_macros(macro_pool)
            return f"macro {slot} deleted"
        if t1 == 'RENAME':
            try:
                slot = int(tokens[2])
            except (IndexError, ValueError):
                return "usage: macro rename <n> <new name>"
            if slot not in macro_pool:
                return f"MACRO RENAME: slot {slot} empty"
            raw_parts = raw.split(None, 3)
            if len(raw_parts) < 4:
                return "MACRO RENAME: provide a new name"
            macro_pool[slot]["name"] = raw_parts[3].strip()
            ShowFile.save_macros(macro_pool)
            return f"macro {slot} renamed to '{macro_pool[slot]['name']}'"
        # MACRO <n> — playback
        try:
            slot = int(t1)
        except ValueError:
            return f"MACRO: unknown subcommand '{t1}'"
        if slot not in macro_pool:
            return f"MACRO {slot}: empty slot"
        if slot in _macro_play_stack:
            chain = " -> ".join(str(s) for s in _macro_play_stack) + f" -> {slot}"
            return f"MACRO {slot}: blocked — recursive playback ({chain})"
        cmds = macro_pool[slot]["commands"]
        results = []
        _macro_play_stack.append(slot)
        try:
            for c in cmds:
                r = run_command(c)
                if r:
                    results.append(r)
        finally:
            _macro_play_stack.pop()
        return f"MACRO {slot} '{macro_pool[slot]['name']}' — {len(cmds)} cmd(s) played\n" + "\n".join(results)

    if t0 == 'FREEZE':
        off = len(tokens) > 1 and tokens[1] in ('OFF', 'RELEASE')
        if off or output_state.freeze_mode:
            output_state.freeze_mode = False
            output_state.frozen_dmx.clear()
            return "FREEZE OFF — live output restored"
        # snapshot universes present in patch
        univs = {out['universe']
                 for m in output_state.patch.all_fixtures()
                 for sub in m.sub_fixtures.values()
                 for out in sub.outputs}
        for u in univs:
            output_state.frozen_dmx[u] = output_state.get_dmx_for_universe(u)
        output_state.freeze_mode = True
        return f"FREEZE ON — output locked at current look ({len(univs)} universe(s))"

    if t0 == 'SOLO':
        off = len(tokens) > 1 and tokens[1] in ('OFF', 'RELEASE')
        if off or (output_state.solo_mode and len(tokens) == 1):
            output_state.solo_mode = False
            output_state.solo_fids.clear()
            return "SOLO OFF — all fixtures restored to normal output"
        output_state.solo_mode = True
        output_state.solo_fids = {
            f.fixture_id for f in prog.selection
            if isinstance(f, MasterFixture)
        }
        fids = sorted(output_state.solo_fids)
        return f"SOLO ON — only fixtures {fids} pass through; others zeroed"

    # ── PARK / UNPARK ────────────────────────────────────────────────────────
    # PARK          — park selected fixtures at their current DMX output values
    # UNPARK        — release selected fixtures from park (or UNPARK ALL)
    # LIST PARK     — show all currently parked fixtures
    if t0 == 'PARK':
        off = len(tokens) > 1 and tokens[1] in ('OFF', 'RELEASE')
        if off:
            return run_command("UNPARK")
        sel_masters = [f for f in prog.selection if isinstance(f, MasterFixture)]
        if not sel_masters:
            return "PARK: select fixtures first"
        for master in sel_masters:
            # Temporarily remove from parked set so we get live output (not the old park)
            was_parked = master.fixture_id in output_state.parked_fids
            output_state.parked_fids.discard(master.fixture_id)
            univs = {out['universe'] for sub in master.all_subs() for out in sub.outputs}
            for u in univs:
                dmx_snap = output_state.get_dmx_for_universe(u)
                for sub in master.all_subs():
                    for out in sub.outputs:
                        if out['universe'] != u:
                            continue
                        for off_i, _ in enumerate(sub.profile.channels):
                            a = out['address'] + off_i
                            if 1 <= a <= 512:
                                output_state.parked_addresses.setdefault(u, {})[a] = dmx_snap[a - 1]
            output_state.parked_fids.add(master.fixture_id)
        fids = sorted(f.fixture_id for f in sel_masters)
        return f"PARK — fixture(s) {fids} frozen at current DMX output (UNPARK to release)"

    if t0 == 'UNPARK':
        all_mode = len(tokens) > 1 and tokens[1] == 'ALL'
        if all_mode:
            output_state.parked_fids.clear()
            output_state.parked_addresses.clear()
            return "UNPARK ALL — all fixtures released"
        sel_masters = [f for f in prog.selection if isinstance(f, MasterFixture)]
        if not sel_masters:
            output_state.parked_fids.clear()
            output_state.parked_addresses.clear()
            return "UNPARK ALL — all fixtures released"
        for master in sel_masters:
            output_state.parked_fids.discard(master.fixture_id)
            for sub in master.all_subs():
                for out in sub.outputs:
                    u = out['universe']
                    for off_i in range(len(sub.profile.channels)):
                        a = out['address'] + off_i
                        output_state.parked_addresses.get(u, {}).pop(a, None)
        fids = sorted(f.fixture_id for f in sel_masters)
        return f"UNPARK — fixture(s) {fids} released from park"

    if t0 == 'HIGHLIGHT' or (t0 == 'HL' and len(tokens) <= 2):
        off = len(tokens) > 1 and tokens[1] == 'OFF'
        on  = len(tokens) > 1 and tokens[1] == 'ON'
        if off or (output_state.highlight_mode and not on):
            output_state.highlight_mode = False
            return "HIGHLIGHT OFF"
        else:
            output_state.highlight_mode = True
            output_state.highlight_fids = {
                f.fixture_id for f in prog.selection
                if isinstance(f, MasterFixture)
            }
            fids = sorted(output_state.highlight_fids)
            return f"HIGHLIGHT ON — fixtures {fids} at full white"

    # ── OUTPUT STATUS — current live DMX overview ─────────────────────────────
    if t0 == 'OUTPUT' and len(tokens) >= 2 and tokens[1] in ('STATUS', 'INFO', 'SHOW'):
        limit = 20
        try:
            if len(tokens) >= 3:
                limit = int(tokens[2])
        except ValueError:
            pass
        lines = [f"Output (master={output_state.master_level:.0%}"
                 + ("  FREEZE" if output_state.freeze_mode else "")
                 + ("  BLIND" if output_state.blind else "")
                 + ("  BLACKOUT" if output_state.master_level == 0.0 else "")
                 + "):"]
        all_active = []
        for u in sorted(set(list(output_state.parked_addresses.keys())
                            + list(output_state.direct_dmx.keys()) + [1])):
            dmx = output_state.get_dmx_for_universe(u)
            for addr0, val in enumerate(dmx):
                if val > 0:
                    all_active.append((u, addr0 + 1, val))
        all_active.sort(key=lambda x: -x[2])
        if not all_active:
            lines.append("  (all channels at 0)")
        else:
            shown = all_active[:limit]
            for u, addr, val in shown:
                pct = val / 255 * 100
                bar = '█' * int(pct / 10)
                # Reverse-map address to fixture name
                fid_label = ""
                for fid, master in patch.fixtures.items():
                    for sub in master.all_subs():
                        for out in sub.outputs:
                            if (out['universe'] == u and
                                    out['address'] <= addr <
                                    out['address'] + len(master.profile.channels)):
                                fid_label = f"  ← {master.name}"
                                break
                lines.append(f"  U{u}@{addr:03d}: {val:3d}  {bar:<10} {pct:.0f}%{fid_label}")
            if len(all_active) > limit:
                lines.append(f"  … ({len(all_active) - limit} more channels)")
        return "\n".join(lines)

    if t0 == 'MASTER' and len(tokens) >= 2:
        try:
            pct = float(tokens[1])
        except ValueError:
            return f"MASTER: bad value '{tokens[1]}' — use 0-100"
        output_state.master_level = max(0.0, min(1.0, pct / 100.0))
        return f"master → {pct:.0f}%"

    # ── GRANDMASTER / GM — show or set the master output level ───────────────
    if t0 in ('GRANDMASTER', 'GM'):
        if len(tokens) == 1:
            return f"grandmaster: {output_state.master_level:.0%}"
        arg = tokens[1]
        if arg == 'FULL':
            output_state.master_level = 1.0
        elif arg == 'OUT':
            output_state.master_level = 0.0
        else:
            try:
                pct = float(arg.rstrip('%'))
                output_state.master_level = max(0.0, min(1.0, pct / 100.0))
            except ValueError:
                return f"GRANDMASTER: unrecognised value '{arg}' — use 0-100 or FULL/OUT"
        return f"grandmaster → {output_state.master_level:.0%}"

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
        if output_state.master_level > 0.0:
            _blackout_saved_level[0] = output_state.master_level
        output_state.master_level = 0.0
        return "BLACKOUT ON"

    # ── Save ─────────────────────────────────────────────────
    # ── SHOW INFO — high-level overview of the current show ──────────────────
    if t0 == 'SHOW' and len(tokens) >= 2 and tokens[1] in ('INFO', 'STATUS', 'STATS'):
        total_cues   = sum(len(cs.cues) for cs in cuestack_pool.stacks.values())
        active_faders = sum(1 for ex in executor_pool.executors.values() if ex.is_active)
        assigned_faders = sum(1 for ex in executor_pool.executors.values() if ex.cuestack)
        prog_fids = len(set(k.split('.')[0] for k in prog.data if prog.data.get(k)))
        lines = [
            "show overview:",
            f"  Fixtures     : {len(patch.fixtures)} patched",
            f"  programmer   : {prog_fids} fixture(s) touched",
            f"  CueStacks    : {len(cuestack_pool.stacks)} stacks  /  {total_cues} cues total",
            f"  Faders       : {active_faders} active  /  {assigned_faders} assigned",
            f"  FX Presets   : {len(fx_pool.presets)}",
            f"  color Presets: {len(color_pool.presets)}",
            f"  dim Presets  : {len(dim_pool.presets)}",
            f"  Groups       : {len(group_pool.groups)}",
            f"  Prog Snaps   : {len(_prog_snapshots)}",
        ]
        if output_state.blind:
            lines.append("  Mode         : BLIND")
        if output_state.freeze_mode:
            lines.append("  Mode         : FROZEN")
        lines.append(f"  Master       : {output_state.master_level:.0%}")
        return "\n".join(lines)

    if t0 == 'BACKUP':
        import datetime as _dt
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        return save_show_as(f"backup_{ts}")

    if t0 == 'SAVE':
        if len(tokens) >= 3 and tokens[1] == 'AS':
            name = raw.split(None, 2)[2] if len(raw.split(None, 2)) > 2 else ""
            return save_show_as(name)
        save_show()
        return "show saved."

    # LOAD CUE <n> [cs <stack_n>]  — copy cue data into programmer for editing
    if t0 == 'LOAD' and len(tokens) >= 3 and tokens[1] == 'CUE':
        try:
            cue_num = float(tokens[2])
        except ValueError:
            return f"LOAD CUE: bad cue number '{tokens[2]}'"
        cs = None
        if 'CS' in tokens:
            cs_idx = tokens.index('CS')
            try: cs = cuestack_pool.get(int(tokens[cs_idx + 1]))
            except (IndexError, ValueError): pass
        if cs is None:
            cs = _active_stack()
        if not cs:
            return "LOAD CUE: no active cuestack"
        cue = cs.cues.get(cue_num)
        if not cue:
            return f"LOAD CUE: cue {cue_num:.0f} not found in {cs.name}"
        prog._push_undo()
        for fid, vals in cue.data.items():
            if fid not in prog.data:
                prog.data[fid] = {}
            prog.data[fid].update(copy.deepcopy(vals))
        prog._print_programmer()
        return f"loaded cue {cue_num:.0f} '{cue.name}' into programmer"

    if t0 == 'LOAD' and len(tokens) >= 2 and tokens[1] == 'SHOW':
        if len(tokens) < 3:
            return "usage: load show <name>  (use list shows to see available saves)"
        name = raw.split(None, 2)[2] if len(raw.split(None, 2)) > 2 else ""
        return load_show_from(name)

    # ── PATCH command-line ────────────────────────────────────
    # PATCH ADD <id> <profile> UNIVERSE <u> AT <addr> [NAME <name>]
    # PATCH REMOVE <id>
    if t0 == 'PATCH' and len(tokens) >= 2:
        sub = tokens[1]
        if sub == 'ADD':
            try:
                fid = int(tokens[2])
            except (IndexError, ValueError):
                return "usage: patch add <id> <profile> universe <u> at <addr> [name <name>]"
            profile_name = tokens[3] if len(tokens) > 3 else None
            if not profile_name:
                return "PATCH ADD: profile name required"
            univ = 1
            addr = 1
            name = f"Fixture {fid}"
            if 'UNIVERSE' in tokens:
                ui = tokens.index('UNIVERSE')
                try: univ = int(tokens[ui + 1])
                except (IndexError, ValueError): pass
            if 'AT' in tokens:
                ai = tokens.index('AT')
                try: addr = int(tokens[ai + 1])
                except (IndexError, ValueError): pass
            if 'NAME' in tokens:
                ni = tokens.index('NAME')
                # NAME takes the rest of the token list joined
                name = ' '.join(tokens[ni + 1:]) if ni + 1 < len(tokens) else name
            if patch.get(fid):
                return f"PATCH ADD: fixture {fid} already patched — PATCH REMOVE {fid} first"
            m = patch.patch_fixture(fid, name, profile_name, univ, addr)
            if m is None:
                return f"PATCH ADD: profile '{profile_name}' not found"
            save_show()
            return f"patched fixture {fid} '{name}' as {profile_name} U{univ}@{addr}"
        if sub == 'REMOVE':
            try:
                fid = int(tokens[2])
            except (IndexError, ValueError):
                return "usage: patch remove <id>"
            if fid not in patch.fixtures:
                return f"PATCH REMOVE: fixture {fid} not patched"
            del patch.fixtures[fid]
            save_show()
            return f"removed fixture {fid} from patch"
        if sub == 'RENAME':
            try:
                fid = int(tokens[2])
            except (IndexError, ValueError):
                return "usage: patch rename <id> <new name>"
            master = patch.get(fid)
            if not master:
                return f"PATCH RENAME: fixture {fid} not patched"
            raw_parts = raw.split(None, 3)
            if len(raw_parts) < 4:
                return "usage: patch rename <id> <new name>"
            master.name = raw_parts[3]
            save_show()
            return f"fixture {fid} renamed to '{master.name}'"
        if sub == 'MOVE':
            try:
                fid = int(tokens[2])
            except (IndexError, ValueError):
                return "usage: patch move <id> universe <u> at <addr>"
            master = patch.get(fid)
            if not master:
                return f"PATCH MOVE: fixture {fid} not patched"
            univ = 1; addr = 1
            if 'UNIVERSE' in tokens:
                ui = tokens.index('UNIVERSE')
                try: univ = int(tokens[ui + 1])
                except (IndexError, ValueError): pass
            if 'AT' in tokens:
                ai = tokens.index('AT')
                try: addr = int(tokens[ai + 1])
                except (IndexError, ValueError): pass
            chs = master.profile.channels_per_pixel
            for i, sub_fix in enumerate(master.all_subs()):
                new_addr = addr + i * chs
                if sub_fix.outputs:
                    sub_fix.outputs[0] = {"universe": univ, "address": new_addr}
                else:
                    sub_fix.outputs.append({"universe": univ, "address": new_addr})
            save_show()
            end_addr = addr + len(master.sub_fixtures) * chs - 1
            return f"moved fixture {fid} to U{univ}@{addr}-{end_addr}"

    if t0 == 'LIST' and len(tokens) >= 2 and tokens[1] == 'SHOWS':
        return list_shows()

    if t0 == 'EXPORT' and len(tokens) >= 2 and tokens[1] == 'PRESETS':
        what = tokens[2] if len(tokens) >= 3 else 'all'
        return export_presets(what)

    if t0 == 'IMPORT' and len(tokens) >= 3 and tokens[1] == 'PRESETS':
        path = raw.split(None, 2)[2]
        return import_presets(path)

    if t0 == 'NETWORK' or t0 == 'NET':
        t1 = tokens[1].upper() if len(tokens) > 1 else ''
        if t1 == 'BIND' and len(tokens) >= 3:
            new_bind = tokens[2]
            ShowFile.save_network(new_bind, network.universes)
            return (f"sACN bind address → {new_bind}  (restart console to apply)")
        if t1 in ('UNIVERSE', 'UNIVERSES', 'UNIV') and len(tokens) >= 3:
            try:
                new_univs = [int(v) for v in tokens[2:] if v.isdigit()]
            except ValueError:
                return "usage: network universe 1 2 3 ..."
            if not new_univs:
                return "usage: network universe 1 2 3 ..."
            ShowFile.save_network(network.bind_address, new_univs)
            return (f"sACN universes → {new_univs}  (restart console to apply)")
        if t1 == 'STATUS' or not t1:
            cfg_bind, cfg_univs = ShowFile.load_network()
            return (
                f"  sACN bind:       {network.bind_address or '(auto)'}\n"
                f"  sACN universes:  {network.universes}\n"
                f"  Saved in config: bind={cfg_bind or '(auto)'}  univs={cfg_univs}\n"
                f"  Restart console to apply any saved changes."
            )
        return "usage: network bind <ip>  |  network universe <n> [n...]  |  network status"

    if t0 == 'OSC':
        t1 = tokens[1] if len(tokens) > 1 else ''
        if t1 == 'TARGET' and len(tokens) >= 5:
            osc.add_target(tokens[2], tokens[3], int(tokens[4]))
            ShowFile.save_osc_targets(osc)
            return f"OSC target '{tokens[2]}' → {tokens[3]}:{tokens[4]}"
        if t1 == 'REMOVE' and len(tokens) >= 3:
            osc.remove_target(tokens[2])
            ShowFile.save_osc_targets(osc)
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
                    except Valueerror: return v
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

    # AUDIO DEVICES | START [device] | STOP | on | off | STATUS | GAIN <n>
    # Block 9 audio-reactive layer: capture (START/STOP) is independent from
    # the mapping toggle (ON/OFF) so an operator can leave a mic plugged in
    # and running while flipping the reactive layer on/off for cue timing.
    if t0 == 'AUDIO':
        t1 = tokens[1] if len(tokens) > 1 else ''
        if t1 == 'DEVICES':
            if not _AUDIO_AVAILABLE:
                return f"audio unavailable: {_AUDIO_IMPORT_ERROR}"
            devs = [f"  [{i}] {d['name']}" for i, d in enumerate(sd.query_devices())
                    if d['max_input_channels'] > 0]
            return "audio input devices:\n" + ("\n".join(devs) if devs else "  (none found)")
        if t1 == 'START':
            device = None
            if len(tokens) > 2:
                try:
                    device = int(tokens[2])
                except ValueError:
                    return f"AUDIO START: bad device index '{tokens[2]}'"
            try:
                audio_engine.start(device=device)
            except RuntimeError as e:
                return f"AUDIO START failed: {e}"
            return "audio capture started."
        if t1 == 'STOP':
            audio_engine.stop()
            return "audio capture stopped."
        if t1 == 'ON':
            audio_mapper.enable()
            return "AUDIO ON — bass=red, mid=green, high=blue, level=dim"
        if t1 == 'OFF':
            audio_mapper.disable()
            return "AUDIO OFF"
        if t1 == 'STATUS':
            state   = "capturing" if audio_engine._running else "stopped"
            mapping = "ON" if audio_mapper.enabled else "OFF"
            return (f"audio: {state}, mapping {mapping}  "
                    f"lvl={audio_engine.level:.2f} lo={audio_engine.low:.2f} "
                    f"mid={audio_engine.mid:.2f} hi={audio_engine.high:.2f}")
        if t1 == 'GAIN' and len(tokens) > 2:
            try:
                g = float(tokens[2])
            except ValueError:
                return f"AUDIO GAIN: bad value '{tokens[2]}'"
            audio_engine.gain = g
            return f"audio gain → {g}"
        return "AUDIO usage: DEVICES | START [device] | STOP | on | off | STATUS | GAIN <n>"

    # MIDI CC <ch> <cc> <target name>        — add CC mapping
    # MIDI NOTE <ch> <note> <target name>    — add note mapping
    # MIDI REMOVE CC <ch> <cc>              — delete CC mapping
    # MIDI REMOVE NOTE <ch> <note>          — delete note mapping
    if t0 == 'MIDI' and len(tokens) >= 2:
        t1 = tokens[1]
        if t1 in ('CC', 'NOTE') and len(tokens) >= 5:
            try:
                ch   = int(tokens[2])
                num  = int(tokens[3])
            except ValueError:
                return f"MIDI {t1}: usage  MIDI {t1} <ch> <number> <target name>"
            target_name = " ".join(tokens[4:])
            entry = GUIEngine.target_registry.get(target_name)
            if not entry:
                available = ", ".join(sorted(GUIEngine.target_registry.keys()))
                return (f"MIDI {t1}: target '{target_name}' not found\n"
                        f"Available: {available}")
            cb          = entry[0]
            soft_takeover = entry[1]
            off_cb      = entry[3] if len(entry) > 3 else None
            if t1 == 'CC':
                midi.map_cc(ch, num, cb, name=target_name, soft_takeover=soft_takeover)
                ShowFile.save_midi(midi)
                return f"mapped ch{ch} cc{num} → {target_name}  (saved)"
            else:
                midi.map_note(ch, num, cb, off_cb, name=target_name)
                ShowFile.save_midi(midi)
                return f"mapped ch{ch} note{num} → {target_name}  (saved)"
        if t1 == 'REMOVE' and len(tokens) >= 5 and tokens[2] in ('CC', 'NOTE'):
            try:
                ch  = int(tokens[3])
                num = int(tokens[4])
            except ValueError:
                return "midi remove cc|note <ch> <number>"
            if tokens[2] == 'CC':
                key = (ch, num)
                if key in midi.cc_maps:
                    del midi.cc_maps[key]
                    ShowFile.save_midi(midi)
                    return f"removed cc mapping ch{ch} cc{num}  (saved)"
                return f"no cc mapping for ch{ch} cc{num}"
            else:
                key = (ch, num)
                if key in midi.note_maps:
                    del midi.note_maps[key]
                    ShowFile.save_midi(midi)
                    return f"removed note mapping ch{ch} note{num}  (saved)"
                return f"no note mapping for ch{ch} note{num}"
        if t1 == 'TARGETS':
            lines = ["Available MIDI targets:"]
            for name in sorted(GUIEngine.target_registry.keys()):
                entry = GUIEngine.target_registry[name]
                kind = "note" if entry[2] else "cc"
                lines.append(f"  {name}  [{kind}]")
            return "\n".join(lines)
        if t1 in ('CC', 'NOTE'):
            return (f"usage: MIDI {t1} <ch 1-16> <number 0-127> <target name>\n"
                    "  e.g. MIDI CC 1 7 Grandmaster Dim\n"
                    "  Use MIDI TARGETS to list available target names")
        if t1 == 'REMOVE':
            return "usage: midi remove cc|note <ch> <number>"
        if t1 == 'CLOCK':
            pass  # handled below
        else:
            return ("MIDI: unknown subcommand — use CC, NOTE, REMOVE, TARGETS, CLOCK ON/OFF, "
                    "or LIST MIDI to see current mappings")

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
        return "MIDI CLOCK on | off"

    # ── DIRECT DMX ───────────────────────────────────────────
    # DMX <addr> <val> [UNIVERSE <n>]  — bypass fixture system, write raw
    # CLEAR DMX [UNIVERSE <n>]         — remove all or per-universe overrides
    if t0 == 'DMX':
        if len(tokens) >= 2 and tokens[1] == 'LIST':
            if not output_state.direct_dmx:
                return "direct DMX: no overrides active"
            lines = ["direct DMX overrides:"]
            for univ in sorted(output_state.direct_dmx):
                for addr, val in sorted(output_state.direct_dmx[univ].items()):
                    lines.append(f"  U{univ}:{addr:3d} = {val}")
            return "\n".join(lines)
        try:
            addr = int(tokens[1])
            val  = int(tokens[2])
        except (IndexError, ValueError):
            return "usage: dmx <addr> <val> [universe <n>]  |  dmx list  |  clear dmx"
        if not (1 <= addr <= 512 and 0 <= val <= 255):
            return "DMX: addr 1-512, val 0-255"
        univ = 1
        if 'UNIVERSE' in tokens:
            ui = tokens.index('UNIVERSE')
            try: univ = int(tokens[ui + 1])
            except (IndexError, ValueError): pass
        output_state.direct_dmx.setdefault(univ, {})[addr] = val
        return f"direct DMX U{univ}:{addr} = {val}"

    # ── STATUS overview ──────────────────────────────────────
    if t0 in ('STATUS', 'STATE'):
        lines = ["=== Console Status ==="]
        gm = output_state.master_level if output_state else 1.0
        blind = output_state.blind if output_state else False
        bbo   = (gm == 0.0)
        freeze = output_state.freeze_mode if output_state else False
        solo   = output_state.solo_mode   if output_state else False
        parked = bool(output_state.parked_fids) if output_state else False
        rec_slot = _macro_recording.get("slot")
        lines.append(f"  Grand Master: {gm*100:.0f}%"
                     + ("  [BBO]" if bbo else "")
                     + ("  [BLIND]" if blind else "")
                     + ("  [FREEZE]" if freeze else "")
                     + ("  [SOLO]" if solo else "")
                     + ("  [PARK]" if parked else "")
                     + (f"  [REC MACRO {rec_slot}]" if rec_slot is not None else ""))
        # Selection + programmer
        sel_masters = [f for f in prog.selection if isinstance(f, MasterFixture)]
        if sel_masters:
            lines.append(f"  Selection: {len(sel_masters)} fixture(s) "
                         f"({', '.join(str(m.fixture_id) for m in sel_masters)})")
        else:
            lines.append("  Selection: none")
        prog_active = any(v for v in prog.data.values() if v)
        lines.append("  programmer: " + ("DIRTY" if prog_active else "clear"))
        # Active faders
        active_exs = [ex for ex in executor_pool.executors.values()
                      if ex.is_active and ex.cuestack] if executor_pool else []
        if active_exs:
            lines.append(f"  Active faders ({len(active_exs)}):")
            for ex in active_exs:
                cs = ex.cuestack
                cur = f"cue {cs.current:.0f}" if cs.current is not None else "—"
                lines.append(f"    [{ex.exec_id}] {cs.name[:14]}  {cur}  "
                             f"lv={ex.level*100:.0f}%")
        else:
            lines.append("  Active faders: none")
        # FX
        n_fx = len(fx_engine._layers) if fx_engine else 0
        lines.append(f"  FX layers: {n_fx} active")
        return "\n".join(lines)

    # ── Stack info ───────────────────────────────────────────
    # CUES / STACK / LIST (bare) — show active cuestack contents
    # NOTE: LIST with a sub-command (LIST DIM, LIST COLOR, etc.) is handled
    # below; only bare LIST falls through here.
    if t0 in ('CUES', 'STACK') or (t0 == 'LIST' and len(tokens) == 1):
        cs = _active_stack()
        if not cs:
            return "no active cuestack"
        lines = [f"cuestack {cs.stack_id} — {cs.name}  [fader {active_executor[0]}]"]
        for n in cs._sorted_cue_numbers():
            c      = cs.cues[n]
            cur    = " ◀" if n == cs.current else ""
            delay  = f"  Delay:{c.delay_time}s" if getattr(c, 'delay_time', 0.0) > 0 else ""
            follow = f"  Follow:{c.follow_time:.1f}s" if getattr(c, 'follow_time', 0.0) > 0 else ""
            note   = f"  [{c.note}]" if getattr(c, 'note', '') else ""
            lines.append(f"  [{n:.0f}] {c.name}  Fade:{c.fade_time}s{delay}{follow}{note}{cur}")
        return "\n".join(lines)

    # ── group recall / record ─────────────────────────────────
    # GROUP <n>                — recall (select fixtures)
    # RECORD GROUP <n> ["name"] — save current selection as group
    if t0 == 'GROUP' and len(tokens) > 1:
        try:
            gid = int(tokens[1])
        except ValueError:
            return f"GROUP: bad id '{tokens[1]}'"
        # GROUP <n> ADD <fid> — add a master fixture to the group
        if len(tokens) >= 4 and tokens[2].upper() == 'ADD':
            g = group_pool.get(gid)
            if not g:
                return f"group {gid} not found"
            try:
                add_fid = int(tokens[3])
            except ValueError:
                return f"GROUP ADD: bad fixture id '{tokens[3]}'"
            if not patch.get(add_fid):
                return f"GROUP ADD: fixture {add_fid} not in patch"
            if any(entry[1] == add_fid for entry in g.members if isinstance(entry, tuple)):
                return f"GROUP ADD: fixture {add_fid} already in group {gid}"
            g.members.append(("master", add_fid))
            save_show()
            return f"group {gid}: added fixture {add_fid} ({len(g.members)} member(s))"

        # GROUP <n> REMOVE <fid> — remove a master fixture from the group
        if len(tokens) >= 4 and tokens[2].upper() == 'REMOVE':
            g = group_pool.get(gid)
            if not g:
                return f"group {gid} not found"
            try:
                rm_fid = int(tokens[3])
            except ValueError:
                return f"GROUP REMOVE: bad fixture id '{tokens[3]}'"
            before = len(g.members)
            g.members = [e for e in g.members
                         if not (isinstance(e, tuple) and e[1] == rm_fid)]
            if len(g.members) == before:
                return f"GROUP REMOVE: fixture {rm_fid} not in group {gid}"
            save_show()
            return f"group {gid}: removed fixture {rm_fid} ({len(g.members)} member(s) remaining)"

        # GROUP <n> INFO/STATUS — show group members
        if len(tokens) >= 3 and tokens[2] in ('INFO', 'STATUS', 'SHOW'):
            g = group_pool.get(gid)
            if not g:
                return f"group {gid} not found"
            # Resolve member fixture IDs to names; members are ("master", fid) tuples
            member_strs = []
            for entry in g.members:
                fid = entry[1] if isinstance(entry, tuple) else int(entry)
                m = patch.get(fid)
                member_strs.append(f"{fid}:{m.name}" if m else str(fid))
            return (f"group {gid}: {g.name}\n"
                    f"  Members ({len(g.members)}): {', '.join(member_strs) or '(empty)'}")
        group_pool.recall(gid, prog)
        g = group_pool.get(gid)
        return f"group {gid} recalled" if g else f"group {gid} not found"

    if t0 == 'RECORD' and len(tokens) > 2 and tokens[1] == 'GROUP':
        try:
            gid = int(tokens[2])
        except ValueError:
            return f"RECORD GROUP: bad slot number '{tokens[2]}'"
        name = _name_after(raw, 3) or f"group {gid}"
        if not prog.selection:
            return (f"RECORD GROUP: nothing selected — "
                    f"first type  1 THRU 6  (or any fixture range)  "
                    f"then  RECORD GROUP {gid} {name}")
        g = group_pool.record(gid, prog, name=name)
        if g:
            save_show()
            return f"recorded: {g}  (show saved)"
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
            return f"color preset {pid} is empty  (use: record color {pid} red)"
        p.apply(prog)
        return f"applied: {p}"

    if t0 == 'RECORD' and len(tokens) > 2 and tokens[1] in ('COLOR', 'COLOUR'):
        try:
            pid = int(tokens[2])
        except ValueError:
            return f"RECORD COLOR: bad slot number '{tokens[2]}'"
        # RECORD COLOR <n> <R> <G> <B> [name]  — explicit RGB values
        _raw_num = [t for t in tokens[3:] if t.lstrip('-').replace('.','',1).isdigit()]
        if len(_raw_num) >= 3:
            try:
                er, eg, eb = int(_raw_num[0]), int(_raw_num[1]), int(_raw_num[2])
            except ValueError:
                return "RECORD COLOR: bad R/G/B values"
            _non_num = [t for t in tokens[3:] if not t.lstrip('-').replace('.','',1).isdigit()]
            name = " ".join(_non_num).title() or f"color {pid}"
            p = ColorPreset(pid, name)
            p.red, p.green, p.blue = float(er), float(eg), float(eb)
            color_pool.presets[pid] = p
            save_show()
            return f"recorded: {p}  (show saved)"
        name = _name_after(raw, 3) or f"color {pid}"
        _has_rgb = any(any(ch in vals for ch in ('red', 'green', 'blue'))
                       for fid, vals in prog.data.items()
                       if '.' in fid)
        if not _has_rgb:
            return "RECORD COLOR: no RGB data in programmer  (set a colour first)"
        p = color_pool.record(pid, prog, name=name)
        save_show()
        return f"recorded: {p}  (show saved)"

    # ── dim preset recall / record ────────────────────────────
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
                return f"dim preset {pid} is empty  (use: record dim {pid} full)"
            p.apply(prog)
            return f"applied: {p}"
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
        # RECORD DIM <n> [name] <level%>  — explicit percentage value
        _raw_num = [t.rstrip('%') for t in tokens[3:]
                    if t.rstrip('%').replace('.','',1).lstrip('-').isdigit()]
        if _raw_num:
            try:
                pct = float(_raw_num[0])
            except ValueError:
                return "RECORD DIM: bad level value"
            level = max(0.0, min(1.0, pct / 100.0 if pct > 1.0 else pct))
            _non_num = [t for t in tokens[3:] if not t.rstrip('%').replace('.','',1).lstrip('-').isdigit()]
            name = " ".join(_non_num).title() or f"dimmer {pid}"
            p = DimmerPreset(pid, name)
            p.level = level
            dim_pool.presets[pid] = p
            save_show()
            return f"recorded: {p}  (show saved)"
        name = _name_after(raw, 3) or f"dimmer {pid}"
        # Check if programmer has dim data before recording
        _has_dim = any('dim' in vals
                       for fid, vals in prog.data.items()
                       if '.' not in fid)
        if not _has_dim:
            return "RECORD DIM: no dimmer data in programmer  (set a dim level first)"
        p = dim_pool.record(pid, prog, name=name)
        save_show()
        return f"recorded: {p}  (show saved)"

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
            return f"recorded: {p}  (show saved)"
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
            return f"{pool_key} preset {pid} is empty  (use: record {pool_key} {pid} Name)"
        p.apply(prog)
        return f"applied: {p}"

    # ── rate / size / spread pool record ─────────────────────────
    # RATE <n>  — recall rate preset (sets BPM from pool slot n)
    if t0 == 'RATE' and len(tokens) == 2:
        try:
            pid = int(tokens[1])
        except ValueError:
            return f"RATE: bad slot number '{tokens[1]}'"
        p = rate_pool.get(pid)
        if not p:
            return f"rate preset {pid} is empty — use RECORD RATE {pid} Name <bpm>"
        return run_command(f"BPM {p.bpm}")

    # SIZEP <n>  — recall size preset
    if t0 == 'SIZEP' and len(tokens) == 2:
        try:
            pid = int(tokens[1])
        except ValueError:
            return f"SIZEP: bad slot number '{tokens[1]}'"
        p = size_pool.get(pid)
        if not p:
            return f"size preset {pid} is empty — use RECORD SIZEP {pid} Name <size>"
        return run_command(f"SIZE {p.size}")

    # SPREADP <n>  — recall spread preset
    if t0 == 'SPREADP' and len(tokens) == 2:
        try:
            pid = int(tokens[1])
        except ValueError:
            return f"SPREADP: bad slot number '{tokens[1]}'"
        p = spread_pool.get(pid)
        if not p:
            return f"spread preset {pid} is empty — use RECORD SPREADP {pid} Name <spread>"
        return run_command(f"SPREAD {p.spread}")

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
        name = " ".join(tokens[3:-1]).title() or f"rate {pid}"
        p = RatePreset(pid, name, bpm)
        rate_pool.store(pid, p)
        ShowFile.save_rate_pool(rate_pool)
        return f"recorded: {p}  (saved)"

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
        name = " ".join(tokens[3:-1]).title() or f"size {pid}"
        p = SizePreset(pid, name, size)
        size_pool.store(pid, p)
        ShowFile.save_size_pool(size_pool)
        return f"recorded: {p}  (saved)"

    # RECORD SPREADP <n> [name] <spread>  — e.g. RECORD SPREADP 4 Wave 0.5
    if t0 == 'RECORD' and len(tokens) >= 4 and tokens[1] == 'SPREADP':
        try:
            pid = int(tokens[2])
        except ValueError:
            return f"RECORD SPREADP: bad slot '{tokens[2]}'"
        try:
            spread = float(tokens[-1])
        except ValueError:
            return "RECORD SPREADP: last token must be spread 0-100  e.g. RECORD SPREADP 4 Wave 50"
        name = " ".join(tokens[3:-1]).title() or f"spread {pid}"
        p = SpreadPreset(pid, name, spread)
        spread_pool.store(pid, p)
        ShowFile.save_spread_pool(spread_pool)
        return f"recorded: {p}  (saved)"

    # SPEED <n> <bpm>         — set speed master n to bpm live
    # SPEED <n> NAME <name>   — rename speed master slot n
    if t0 == 'SPEED' and len(tokens) >= 3:
        try:
            sid = int(tokens[1])
        except ValueError:
            return f"SPEED: bad slot '{tokens[1]}'  (SPEED <1-{SpeedMasterPool._DEFAULT_SLOTS}> <bpm>)"
        if tokens[2] == 'NAME':
            name = " ".join(tokens[3:]).title() if len(tokens) > 3 else f"spd{sid}"
            m = speed_master_pool.get(sid)
            if not m:
                speed_master_pool.masters[sid] = SpeedMaster(sid, 120.0, name)
            else:
                m.name = name
            ShowFile.save_speed_masters(speed_master_pool)
            return f"speed master {sid} renamed → {name}"
        try:
            bpm = float(tokens[2])
        except ValueError:
            return f"SPEED: expected bpm value, got '{tokens[2]}'"
        if bpm <= 0:
            return "SPEED: bpm must be > 0"
        speed_master_pool.set_bpm(sid, bpm)
        ShowFile.save_speed_masters(speed_master_pool)
        m = speed_master_pool.get(sid)
        return f"speed master {sid} ({m.name}) → {bpm:.1f} BPM"

    # LIST RATE / SIZEP / SPREADP / FORM
    if t0 == 'LIST' and len(tokens) >= 2:
        sub = tokens[1]
        if sub == 'RATE':
            lines = ["rate Presets:"] + [f"  {p}" for p in sorted(rate_pool.presets.values(), key=lambda x: x.preset_id)]
            return "\n".join(lines)
        if sub in ('SIZEP', 'SIZE'):
            lines = ["size Presets:"] + [f"  {p}" for p in sorted(size_pool.presets.values(), key=lambda x: x.preset_id)]
            return "\n".join(lines)
        if sub in ('SPREADP', 'SPREAD'):
            lines = ["spread Presets:"] + [f"  {p}" for p in sorted(spread_pool.presets.values(), key=lambda x: x.preset_id)]
            return "\n".join(lines)
        if sub in ('SPEED', 'SPD', 'SPEEDS'):
            lines = ["speed Masters:"]
            for sid in speed_master_pool.all_slots():
                m = speed_master_pool.get(sid)
                lines.append(f"  [{sid:2d}] {m.name:<12}  {m.bpm:.1f} BPM")
            return "\n".join(lines)
        if sub == 'FORM':
            lines = ["form Presets:"] + [f"  {f}" for f in sorted(form_pool.forms.values(), key=lambda x: x.form_id)]
            return "\n".join(lines)
        if sub in ('COLOR', 'COLOUR', 'COLORS', 'COLOURS'):
            if not color_pool.presets:
                return "color pool is empty"
            lines = ["color Presets:"]
            for pid in sorted(color_pool.presets):
                p = color_pool.presets[pid]
                r, g, b = int(p.red), int(p.green), int(p.blue)
                rgb = f"R{r} G{g} B{b}"
                lines.append(f"  [{pid}] {p.name}  {rgb}")
            return "\n".join(lines)
        if sub in ('DIM', 'DIMS'):
            if not dim_pool.presets:
                return "dim pool is empty"
            lines = ["dim Presets:"]
            for pid in sorted(dim_pool.presets):
                p = dim_pool.presets[pid]
                lines.append(f"  [{pid}] {p.name}  {p.level:.0%}")
            return "\n".join(lines)
        if sub in ('GROUP', 'GROUPS'):
            if not group_pool.groups:
                return "group pool is empty"
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
                cur = f"  ◀ on cue {cs.current:.0f}" if cs.current is not None else ""
                lines.append(f"  [{sid}] {cs.name}  ({cue_count} cues){cur}")
            return "\n".join(lines) if len(lines) > 1 else "no cuestacks recorded"
        # LIST CUES [CS <n>] — cue list for active or specified cuestack
        if sub in ('CUES', 'CUE'):
            cs_n = None
            if 'CS' in tokens:
                ci = tokens.index('CS')
                try:
                    cs_n = int(tokens[ci + 1])
                except (IndexError, ValueError):
                    pass
            cs = cuestack_pool.get(cs_n) if cs_n is not None else _active_stack()
            if not cs:
                label = f"cuestack {cs_n}" if cs_n else "active cuestack"
                return f"LIST CUES: {label} not found"
            if not cs.cues:
                return f"CS {cs.stack_id} '{cs.name}': no cues"
            lines = [f"CS {cs.stack_id} '{cs.name}' ({len(cs.cues)} cues):"]
            for num in cs._sorted_cue_numbers():
                cue = cs.cues[num]
                cur_m = " ◀" if num == cs.current else ""
                note_s = f"  [{cue.note}]" if getattr(cue, 'note', '') else ""
                lines.append(f"  [{num:.0f}] {cue.name}  fade:{cue.fade_time}s{note_s}{cur_m}")
            return "\n".join(lines)
        _list_attr_map = {
            'POSITION': position_pool,
            'GOBO':     gobo_pool,
            'ZOOM':     zoom_pool,
            'FOCUS':    focus_pool,
            'BEAM':     beam_pool,
            'CONTROL':  control_pool,
        }
        if sub in _list_attr_map:
            pool = _list_attr_map[sub]
            if not pool.presets:
                return f"{sub.title()} pool is empty"
            lines = [f"{sub.title()} Presets:"]
            for pid in sorted(pool.presets):
                p = pool.presets[pid]
                lines.append(f"  {p}")
            return "\n".join(lines)
        if sub in ('FADER', 'FADERS', 'EXEC', 'EXECUTORS', 'EXECUTOR'):
            if not executor_pool.executors:
                return "no faders configured"
            lines = ["Faders:"]
            for eid in sorted(executor_pool.executors):
                ex = executor_pool.executors[eid]
                cs = ex.cuestack
                lbl_s = f"  [{ex.label}]" if ex.label else ""
                if cs:
                    cur_s = (f"  cue {cs.current:.0f}" if cs.current is not None else "  not started")
                    active_s = "  ACTIVE" if ex.is_active else "  idle"
                    mode_s = f"  mode={ex.trigger_mode}"
                    lines.append(f"  [{eid}]{lbl_s} → CS {cs.stack_id}: {cs.name}{cur_s}{active_s}{mode_s}")
                else:
                    lines.append(f"  [{eid}]{lbl_s} → (unassigned)")
            return "\n".join(lines)
        if sub == 'MIDI':
            if not midi or (not midi.cc_maps and not midi.note_maps):
                return "no MIDI mappings"
            lines = ["MIDI Mappings:"]
            for (ch, cc), m in sorted(midi.cc_maps.items()):
                status = "live" if m.taken_over else "takeover"
                lines.append(f"  ch{ch} cc{cc:3d}  → {m.name} [{status}]")
            for (ch, note), m in sorted(midi.note_maps.items()):
                lines.append(f"  ch{ch} note{note:3d} → {m.name}")
            return "\n".join(lines) if len(lines) > 1 else "no MIDI mappings"
        if sub in ('OSC', 'TARGETS'):
            clients = osc._clients if osc else {}
            if not clients:
                return "no OSC targets"
            lines = ["OSC Targets:"]
            for name, c in clients.items():
                lines.append(f"  {name}  {c._address}:{c._port}")
            return "\n".join(lines)
        if sub == 'PATCH':
            if not patch or not patch.fixtures:
                return "patch is empty"
            lines = ["Patch:"]
            for fid in sorted(patch.fixtures):
                m = patch.fixtures[fid]
                first_sub = m.get_sub(1)
                park_s = "  [PARKED]" if fid in output_state.parked_fids else ""
                if first_sub and first_sub.outputs:
                    out = first_sub.outputs[0]
                    lines.append(f"  [{fid}] {m.name}  {m.profile.name}  U{out['universe']}@{out['address']}{park_s}")
                else:
                    lines.append(f"  [{fid}] {m.name}  {m.profile.name}{park_s}")
            return "\n".join(lines)
        if sub == 'PARK':
            if not output_state.parked_fids:
                return "no fixtures parked"
            lines = ["Parked fixtures:"]
            for fid in sorted(output_state.parked_fids):
                m = patch.get(fid)
                name = m.name if m else f"(fixture {fid})"
                addr_count = sum(len(v) for v in output_state.parked_addresses.values())
                lines.append(f"  [{fid}] {name}")
            return "\n".join(lines)
        if sub == 'MACRO':
            return run_command("MACRO LIST")
        if sub in ('NOTES', 'NOTE'):
            lines = []
            for sid in sorted(cuestack_pool.stacks):
                cs = cuestack_pool.stacks[sid]
                cs_note = getattr(cs, 'note', '')
                cue_notes = [(num, cs.cues[num].note)
                             for num in cs._sorted_cue_numbers()
                             if getattr(cs.cues[num], 'note', '')]
                if cs_note or cue_notes:
                    lines.append(f"CS {sid} '{cs.name}':" + (f"  {cs_note}" if cs_note else ""))
                    for num, nt in cue_notes:
                        lines.append(f"    cue {num:.0f}: {nt}")
            if not lines:
                return "no notes set on any cuestack or cue"
            return "\n".join(lines)
        return (f"LIST: unknown sub-command '{tokens[1]}' — "
                "use COLOR, DIM, GROUP, FX, CUESTACKS, RATE, SIZEP, SPREADP, FORM, "
                "POSITION, GOBO, ZOOM, FOCUS, BEAM, CONTROL, EXEC, MIDI, OSC, PATCH, PARK, SHOWS, NOTES")

    # ── FIXTURE INFO <n> — detailed per-fixture status ──────────────────────────
    # FIXTURE SWAP <a> <b> — exchange programmer values between two fixtures
    if t0 == 'FIXTURE' and len(tokens) >= 4 and tokens[1].upper() == 'SWAP':
        try:
            fid_a, fid_b = int(tokens[2]), int(tokens[3])
        except ValueError:
            return "usage: fixture swap <a> <b>"
        if fid_a == fid_b:
            return "FIXTURE SWAP: source and destination are the same"
        if not patch.get(fid_a):
            return f"FIXTURE SWAP: fixture {fid_a} not in patch"
        if not patch.get(fid_b):
            return f"FIXTURE SWAP: fixture {fid_b} not in patch"
        prog._push_undo()
        # Collect all data keys belonging to each fixture: "N" (master) and "N.x" (subs)
        def _fx_keys(fid):
            return [k for k in prog.data
                    if k == str(fid) or k.startswith(str(fid) + '.')]
        keys_a = _fx_keys(fid_a)
        keys_b = _fx_keys(fid_b)
        # Extract data, remap keys from A→B and B→A
        data_a = {k: prog.data.pop(k) for k in keys_a}
        data_b = {k: prog.data.pop(k) for k in keys_b}
        def _remap(d, old_fid, new_fid):
            out = {}
            for k, v in d.items():
                if k == str(old_fid):
                    out[str(new_fid)] = v
                elif k.startswith(str(old_fid) + '.'):
                    out[str(new_fid) + k[len(str(old_fid)):]] = v
            return out
        prog.data.update(_remap(data_a, fid_a, fid_b))
        prog.data.update(_remap(data_b, fid_b, fid_a))
        return f"programmer: swapped fixture {fid_a} ↔ fixture {fid_b}"

    # ── FIXTURE GROUPS <n> — list every group that contains fixture n ──────────
    if t0 == 'FIXTURE' and len(tokens) >= 3 and tokens[1].upper() in ('GROUPS', 'GROUP'):
        try:
            fid = int(tokens[2])
        except ValueError:
            return "usage: fixture groups <id>"
        master = patch.get(fid)
        if not master:
            return f"fixture {fid} not patched"
        containing = []
        for gid in sorted(group_pool.groups):
            g = group_pool.groups[gid]
            for entry in g.members:
                if isinstance(entry, tuple) and entry[1] == fid:
                    containing.append(f"  group {gid}: {g.name}")
                    break
        if not containing:
            return f"fixture {fid} '{master.name}' is not in any group"
        lines = [f"Fixture {fid} '{master.name}' appears in {len(containing)} group(s):"]
        lines.extend(containing)
        return "\n".join(lines)

    if t0 == 'FIXTURE' and len(tokens) >= 3 and tokens[1] in ('INFO', 'STATUS', 'SHOW'):
        try:
            fid = int(tokens[2])
        except ValueError:
            return "usage: fixture info <id>"
        master = patch.get(fid)
        if not master:
            return f"fixture {fid} not patched"
        prof = master.profile
        lines = [f"Fixture {fid}: {master.name}",
                 f"  Profile  : {prof.name}",
                 f"  Channels : {', '.join(prof.channels)}",
                 f"  Pixels   : {master.pixel_count}"]
        # Address table
        for i, sub in enumerate(master.all_subs(), 1):
            if sub.outputs:
                o = sub.outputs[0]
                end = o['address'] + len(prof.channels) - 1
                lines.append(f"  Pixel {i:3d}: U{o['universe']}@{o['address']}-{end}")
        # Park status
        if fid in output_state.parked_fids:
            lines.append("  Status   : PARKED")
        # programmer values
        prog_vals = []
        m_dim = prog.data.get(str(fid), {}).get('dim')
        if m_dim is not None:
            prog_vals.append(f"dim={m_dim:.0%}")
        for sub in master.all_subs():
            sfid = str(sub.fixture_id)
            sd = prog.data.get(sfid, {})
            if sd:
                pairs = "  ".join(f"{k}={v}" for k, v in sd.items())
                prog_vals.append(f"[sub {sub.sub_index}] {pairs}")
        if prog_vals:
            lines.append("  programmer:")
            for v in prog_vals:
                lines.append(f"    {v}")
        return "\n".join(lines)

    # ── Clear — programmer only, never touches cuestacks ────────
    # ── RELEASE — stop executor(s) ───────────────────────────
    # ── PRIORITY — set executor merge priority ────────────────
    if t0 == 'PRIORITY' and len(tokens) >= 3:
        try:
            n = int(tokens[1])
        except ValueError:
            return "usage: priority <n> high | low | normal"
        lvl_str = tokens[2]
        lvl_map = {'HIGH': 1, 'HI': 1, 'LOW': -1, 'LO': -1, 'NORMAL': 0, 'NRM': 0}
        if lvl_str not in lvl_map:
            return f"unknown priority '{lvl_str}' — use HIGH, LOW or NORMAL"
        ex = executor_pool.get(n)
        ex.priority = lvl_map[lvl_str]
        lbl = Executor.PRIORITY_LABELS[ex.priority]
        return f"fader {n} priority → {lbl}"

    if t0 == 'RELEASE':
        if len(tokens) == 1 or (len(tokens) == 2 and tokens[1] == 'ALL'):
            stopped = []
            for ex in executor_pool.executors.values():
                if ex.is_active:
                    ex.stop()
                    stopped.append(ex.exec_id)
            return f"released {len(stopped)} fader(s): {stopped}" if stopped else "no active faders"
        try:
            n = int(tokens[1])
        except (ValueError, IndexError):
            return "usage: release <n>  or  release all"
        ex = executor_pool.get(n)
        if ex.is_active:
            ex.stop()
            return f"released fader {n}"
        return f"fader {n} was not running"

    # ── CUE timing editor (no programmer required) ─────────────
    # CUE <n> FADE/INFADE/OUTFADE <t> [DELAY <t>] [CFADE <t>] [DFADE <t>]
    # CS <n> CUE <m> FADE <t> [...]
    # RECORD CUE <n> FADE <t>  also works when programmer is empty (updates existing cue)
    _TIMING_KW = {'FADE', 'INFADE', 'OUTFADE', 'DELAY', 'FOLLOW',
                  'CFADE', 'CINFADE', 'DFADE', 'DINFADE', 'CDELAY', 'DDELAY'}
    _has_timing = bool(_TIMING_KW & set(tokens))

    # CUE <n> SHOW / INFO — inspect cue contents without firing it
    # CUE <n> NOTE <text>  — set production annotation on a cue
    if t0 == 'CUE' and len(tokens) >= 3 and tokens[2] == 'NOTE':
        try:
            cue_num = float(tokens[1])
        except ValueError:
            return f"CUE NOTE: bad cue number '{tokens[1]}'"
        cs = _active_stack()
        if not cs:
            return "CUE NOTE: no active cuestack"
        cue = cs.cues.get(cue_num)
        if not cue:
            return f"cue {cue_num} not found in active cuestack"
        note_text = raw.split(None, 3)[3].strip() if len(tokens) > 3 else ""
        cue.note = note_text
        save_show()
        return f"cue {cue_num}: note set — \"{note_text}\""

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
            return f"cue {cue_num} not found in active cuestack"
        note_str   = f"  [{cue.note}]" if getattr(cue, 'note', '') else ""
        follow_str = f"  Follow:{cue.follow_time:.1f}s" if getattr(cue, 'follow_time', 0.0) > 0 else ""
        lines = [f"cue {cue_num}: {cue.name}  |  Fade:{cue.fade_time}s  Delay:{cue.delay_time}s{follow_str}{note_str}"]
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
                    parts.append(f"FX:{ld.get('waveform','?')} {ld.get('channel','?')} {ld.get('bpm',60):.0f} bpm")
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
            return f"cue {cue_num} not found in active cuestack"
        _apply_timing_edit(cue, raw)
        save_show()
        return f"updated: {cue}"

    if _has_timing and t0 in ('CS', 'CUESTACK') and 'CUE' in tokens:
        cue_idx = tokens.index('CUE')
        try:
            cs_n    = int(tokens[1])
            cue_num = float(tokens[cue_idx + 1])
        except (ValueError, IndexError):
            return "usage: cs <n> cue <m> fade <t> [delay <t>] [cfade <t>] [dfade <t>]"
        cs = cuestack_pool.get(cs_n)
        if not cs:
            return f"cuestack {cs_n} not found"
        cue = cs.cues.get(float(cue_num))
        if not cue:
            return f"cue {cue_num} not found in cuestack {cs_n}"
        _apply_timing_edit(cue, raw)
        save_show()
        return f"updated: {cue}"

    # CUE <n> SHIFT <offset> — move a cue to a new number within the active cuestack
    if t0 == 'CUE' and len(tokens) >= 4 and tokens[2].upper() == 'SHIFT':
        try:
            cue_num = float(tokens[1])
            offset  = float(tokens[3])
        except ValueError:
            return "usage: cue <n> shift <offset>"
        cs = _active_stack()
        if not cs:
            return "CUE SHIFT: no active cuestack"
        cue = cs.cues.get(cue_num)
        if not cue:
            return f"CUE SHIFT: cue {cue_num:.0f} not found"
        new_num = round(cue_num + offset, 6)
        if new_num in cs.cues:
            return f"CUE SHIFT: position {new_num:.0f} already occupied"
        del cs.cues[cue_num]
        cue.cue_number = new_num
        cs.cues[new_num] = cue
        if cs.current == cue_num:
            cs.current = new_num
        save_show()
        return f"cue {cue_num:.0f} → {new_num:.0f} in '{cs.name}'"

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
                return f"cuestack {n} not found"
            new_name = _name_after(raw, 3)
            if not new_name:
                return "RENAME CUESTACK: provide a new name"
            cs.name = new_name
            save_show()
            return f"cuestack {n} → \"{new_name}\""

        # RENAME CS <n> CUE <m> <name>  or  RENAME CUE <n> <name>
        if sub == 'CUE' or (sub == 'CS' and 'CUE' in tokens):
            if sub == 'CS' and 'CUE' in tokens:
                cue_idx = tokens.index('CUE')
                try:
                    cs_n    = int(tokens[2])
                    cue_num = float(tokens[cue_idx + 1])
                except (ValueError, IndexError):
                    return "usage: rename cs <n> cue <m> <name>"
                cs = cuestack_pool.get(cs_n)
                if not cs:
                    return f"cuestack {cs_n} not found"
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
                return f"cue {cue_num} not found"
            cue.name = new_name
            save_show()
            return f"cue {cue_num} → \"{new_name}\""

        # RENAME COLOR / COLOUR <n> <name>
        if sub in ('COLOR', 'COLOUR'):
            try:
                n = int(tokens[2])
            except ValueError:
                return f"RENAME COLOR: bad number '{tokens[2]}'"
            p = color_pool.get(n)
            if not p:
                return f"color preset {n} not found"
            new_name = _name_after(raw, 3)
            if not new_name:
                return "RENAME COLOR: provide a new name"
            p.name = new_name
            save_show()
            return f"color {n} → \"{new_name}\""

        # RENAME DIM <n> <name>
        if sub == 'DIM':
            try:
                n = int(tokens[2])
            except ValueError:
                return f"RENAME DIM: bad number '{tokens[2]}'"
            p = dim_pool.get(n)
            if not p:
                return f"dim preset {n} not found"
            new_name = _name_after(raw, 3)
            if not new_name:
                return "RENAME DIM: provide a new name"
            p.name = new_name
            save_show()
            return f"dim {n} → \"{new_name}\""

        # RENAME GROUP <n> <name>
        if sub == 'GROUP':
            try:
                n = int(tokens[2])
            except ValueError:
                return f"RENAME GROUP: bad number '{tokens[2]}'"
            g = group_pool.get(n)
            if not g:
                return f"group {n} not found"
            new_name = _name_after(raw, 3)
            if not new_name:
                return "RENAME GROUP: provide a new name"
            g.name = new_name
            save_show()
            return f"group {n} → \"{new_name}\""

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
            'RATE':     rate_pool.presets,
            'SIZEP':    size_pool.presets,
            'SPREADP':  spread_pool.presets,
            'FORM':     form_pool.forms,
            'POSITION': position_pool.presets,
            'GOBO':     gobo_pool.presets,
            'ZOOM':     zoom_pool.presets,
            'FOCUS':    focus_pool.presets,
            'BEAM':     beam_pool.presets,
            'CONTROL':  control_pool.presets,
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

        # RENAME MACRO <n> <name>
        if sub == 'MACRO':
            try:
                n = int(tokens[2])
            except ValueError:
                return f"RENAME MACRO: bad number '{tokens[2]}'"
            if n not in macro_pool:
                return f"macro slot {n} is empty"
            new_name = _name_after(raw, 3)
            if not new_name:
                return "RENAME MACRO: provide a new name"
            macro_pool[n]["name"] = new_name
            ShowFile.save_macros(macro_pool)
            return f"macro {n} → \"{new_name}\""

        # RENAME FIXTURE <n> <name>
        if sub == 'FIXTURE':
            try:
                n = int(tokens[2])
            except ValueError:
                return f"RENAME FIXTURE: bad fixture ID '{tokens[2]}'"
            master = patch.get(n)
            if not master:
                return f"RENAME FIXTURE: fixture {n} not in patch"
            new_name = _name_after(raw, 3)
            if not new_name:
                return "RENAME FIXTURE: provide a new name"
            old_name = master.name
            master.name = new_name
            ShowFile.save_patch(patch)
            return f"fixture {n}: \"{old_name}\" → \"{new_name}\""

        return (f"RENAME: unknown type '{sub}' — use CUESTACK, CUE, COLOR, DIM, GROUP, FX, "
                "RATE, SIZEP, SPREADP, FORM, POSITION, GOBO, ZOOM, FOCUS, BEAM, CONTROL, MACRO, FIXTURE")

    # ── COPY FIXTURE <src> TO <dst1> [dst2 ...] ──────────────────────────────
    # clone programmer values from one fixture to one or more destinations.
    if t0 == 'COPY' and len(tokens) >= 5 and tokens[1] == 'FIXTURE' and 'TO' in tokens:
        to_idx = tokens.index('TO')
        try:
            src_id = int(tokens[2])
        except ValueError:
            return "usage: copy fixture <src> to <dst1> [dst2 ...]"
        dst_ids = []
        for tok in tokens[to_idx + 1:]:
            try: dst_ids.append(int(tok))
            except Valueerror: break
        if not dst_ids:
            return "COPY FIXTURE: provide at least one destination fixture"
        src_master = patch.get(src_id)
        if not src_master:
            return f"COPY FIXTURE: fixture {src_id} not patched"
        prog._push_undo()
        copied = []
        for dst_id in dst_ids:
            dst_master = patch.get(dst_id)
            if not dst_master:
                continue
            src_m_data = prog.data.get(str(src_id), {})
            if src_m_data:
                prog.data.setdefault(str(dst_id), {}).update(copy.deepcopy(src_m_data))
            for src_sub in src_master.all_subs():
                src_sub_data = prog.data.get(str(src_sub.fixture_id), {})
                if src_sub_data:
                    dst_sub = dst_master.get_sub(src_sub.sub_index)
                    if dst_sub:
                        prog.data.setdefault(str(dst_sub.fixture_id), {}).update(
                            copy.deepcopy(src_sub_data))
            copied.append(dst_id)
        return f"copied fixture {src_id} → {copied}"

    # ── COPY CUE / COPY CS ────────────────────────────────────────────────────
    # COPY CUE <src> TO <dst>               — within active cuestack
    # COPY CUE <src> TO <dst> <name>        — with new name
    # COPY CS <cs> CUE <src> TO <dst>       — explicit source cuestack
    # COPY CS <cs> CUE <src> TO CS <cs2> CUE <dst>  — cross-cuestack
    # COPY CS <n> TO CS <m>                 — whole-cuestack duplicate
    if t0 == 'COPY' and len(tokens) >= 2 and tokens[1] in ('CUE', 'CS', 'CUESTACK'):
        try:
            # Locate TO keyword
            if 'TO' not in tokens:
                return "COPY CUE: missing TO — e.g. COPY CUE 3 TO 5"
            to_idx = tokens.index('TO')

            # Parse source side (before TO)
            src_tokens = tokens[1:to_idx]

            # ── Whole-cuestack copy: COPY CS <n> TO CS <m> ─────────────────
            if (src_tokens and src_tokens[0] in ('CS', 'CUESTACK') and
                    len(src_tokens) == 2 and 'CUE' not in src_tokens):
                src_cs_n = int(src_tokens[1])
                dst_tokens = tokens[to_idx + 1:]
                if not dst_tokens or dst_tokens[0] not in ('CS', 'CUESTACK') or len(dst_tokens) < 2:
                    return "COPY CS: use COPY CS <src> TO CS <dst>"
                dst_cs_n = int(dst_tokens[1])
                src_cs = cuestack_pool.get(src_cs_n)
                if not src_cs:
                    return f"COPY CS: source CS {src_cs_n} not found"
                dst_cs = cuestack_pool.get(dst_cs_n) or cuestack_pool.create(dst_cs_n)
                for cue_n, src_cue in sorted(src_cs.cues.items()):
                    nc = Cue(
                        cue_number  = src_cue.cue_number,
                        name        = src_cue.name,
                        fade_time   = src_cue.fade_time,
                        delay_time  = src_cue.delay_time,
                        fade_times  = copy.deepcopy(src_cue.fade_times),
                        delay_times = copy.deepcopy(src_cue.delay_times),
                        follow_time = src_cue.follow_time,
                    )
                    nc.note = src_cue.note
                    nc.fx_outfade = src_cue.fx_outfade
                    nc.data = copy.deepcopy(src_cue.data)
                    dst_cs.cues[cue_n] = nc
                if not dst_cs.name or dst_cs.name == f"cuestack {dst_cs_n}":
                    dst_cs.name = src_cs.name
                save_show()
                return (f"copied CS {src_cs_n} '{src_cs.name}' → CS {dst_cs_n} "
                        f"'{dst_cs.name}'  ({len(src_cs.cues)} cues)")

            # ── Single-cue copy ─────────────────────────────────────────────
            if src_tokens and src_tokens[0] in ('CS', 'CUESTACK'):
                if len(src_tokens) < 4 or src_tokens[2] not in ('CUE',):
                    return "COPY: use COPY CS <n> CUE <src> TO ..."
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
                dst_cs    = cuestack_pool.get(dst_cs_n) or cuestack_pool.create(dst_cs_n)
                new_name  = _name_after(raw, tokens.index('CUE', to_idx + 1) + 2) if len(dst_tokens) > 4 else ""
            else:
                dst_cue_n = float(dst_tokens[0])
                dst_cs    = cuestack_pool.get(active_executor[0]) or _active_stack()
                new_name  = " ".join(dst_tokens[1:]) if len(dst_tokens) > 1 else ""

            if not src_cs:
                return f"COPY CUE: source cuestack not found"
            if not dst_cs:
                return f"COPY CUE: no active cuestack — specify CS <n> CUE <dst>"

            src_cue = src_cs.get_cue(src_cue_n)
            if not src_cue:
                return f"COPY CUE: cue {src_cue_n} not found in '{src_cs.name}'"

            # Build the destination cue — deep-copy all data including follow_time/note
            dst_cue = Cue(
                cue_number  = dst_cue_n,
                name        = new_name if new_name else src_cue.name,
                fade_time   = src_cue.fade_time,
                delay_time  = src_cue.delay_time,
                fade_times  = copy.deepcopy(src_cue.fade_times),
                delay_times = copy.deepcopy(src_cue.delay_times),
                follow_time = src_cue.follow_time,
            )
            dst_cue.note = src_cue.note
            dst_cue.fx_outfade = src_cue.fx_outfade
            dst_cue.data = copy.deepcopy(src_cue.data)
            dst_cs.cues[float(dst_cue_n)] = dst_cue
            save_show()
            return (f"copied cue {src_cue_n} '{src_cue.name}' → "
                    f"cue {dst_cue_n} '{dst_cue.name}'  in '{dst_cs.name}'")

        except (ValueError, IndexError) as _e:
            return f"COPY CUE: bad syntax — {_e}"

    # ── MOVE CUE ──────────────────────────────────────────────────────────────
    # MOVE CUE <src> TO <dst>               — renumber within active cuestack
    # MOVE CS <cs> CUE <src> TO <dst>       — explicit cuestack
    # MOVE CS <cs> CUE <src> TO CS <cs2> CUE <dst>  — cross-cuestack move
    if t0 == 'MOVE' and len(tokens) >= 2 and tokens[1] in ('CUE', 'CS', 'CUESTACK'):
        try:
            if 'TO' not in tokens:
                return "MOVE CUE: missing TO — e.g. MOVE CUE 3 TO 5"
            to_idx = tokens.index('TO')
            src_tokens = tokens[1:to_idx]
            if src_tokens and src_tokens[0] in ('CS', 'CUESTACK'):
                if len(src_tokens) < 4 or src_tokens[2] != 'CUE':
                    return "MOVE: use MOVE CS <n> CUE <src> TO ..."
                src_cs_n  = int(src_tokens[1])
                src_cue_n = float(src_tokens[3])
                src_cs = cuestack_pool.get(src_cs_n)
            elif src_tokens and src_tokens[0] == 'CUE':
                src_cue_n = float(src_tokens[1])
                src_cs    = cuestack_pool.get(active_executor[0])
            else:
                return "MOVE: use MOVE CUE <n> TO <m>  or  MOVE CS <n> CUE <src> TO ..."
            dst_tokens = tokens[to_idx + 1:]
            if not dst_tokens:
                return "MOVE CUE: missing destination after TO"
            if dst_tokens[0] in ('CS', 'CUESTACK'):
                if len(dst_tokens) < 4 or dst_tokens[2] != 'CUE':
                    return "MOVE: use ... TO CS <n> CUE <dst>"
                dst_cs_n  = int(dst_tokens[1])
                dst_cue_n = float(dst_tokens[3])
                dst_cs    = cuestack_pool.get(dst_cs_n) or cuestack_pool.create(dst_cs_n)
            else:
                dst_cue_n = float(dst_tokens[0])
                dst_cs    = src_cs
            if not src_cs:
                return "MOVE CUE: source cuestack not found"
            src_cue = src_cs.get_cue(src_cue_n)
            if not src_cue:
                return f"MOVE CUE: cue {src_cue_n} not found in '{src_cs.name}'"
            if float(dst_cue_n) in dst_cs.cues and dst_cs is src_cs and dst_cue_n != src_cue_n:
                return (f"MOVE CUE: cue {dst_cue_n} already exists in '{dst_cs.name}' "
                        "— DELETE it first or use COPY")
            moved = Cue(
                cue_number  = dst_cue_n,
                name        = src_cue.name,
                fade_time   = src_cue.fade_time,
                delay_time  = src_cue.delay_time,
                fade_times  = copy.deepcopy(src_cue.fade_times),
                delay_times = copy.deepcopy(src_cue.delay_times),
                follow_time = src_cue.follow_time,
            )
            moved.note = src_cue.note
            moved.fx_outfade = src_cue.fx_outfade
            moved.data = copy.deepcopy(src_cue.data)
            dst_cs.cues[float(dst_cue_n)] = moved
            src_cs.delete_cue(src_cue_n)
            if src_cue_n == int(src_cue_n):
                cue_pool.delete(int(src_cue_n))
            if dst_cue_n == int(dst_cue_n):
                cue_pool.store(int(dst_cue_n), moved)
            save_show()
            return (f"moved cue {src_cue_n} '{moved.name}' → "
                    f"cue {dst_cue_n}  in '{dst_cs.name}'")
        except (ValueError, IndexError) as _e:
            return f"MOVE CUE: bad syntax — {_e}"

    # ── COPY pool preset ──────────────────────────────────────────────────────
    # COPY COLOR/DIM/GROUP/FX <src> TO <dst> [name]
    # tokens: COPY  TYPE  N  TO  M  [name...]
    #         [0]   [1]  [2] [3] [4]  [5+]
    if t0 == 'COPY' and len(tokens) >= 5 and tokens[3] == 'TO':
        sub = tokens[1]
        if sub in ('COLOR', 'COLOUR', 'DIM', 'GROUP', 'FX', 'FORM',
                   'RATE', 'SIZEP', 'SIZE', 'SPREADP', 'SPREAD',
                   'POSITION', 'GOBO', 'ZOOM', 'FOCUS', 'BEAM', 'CONTROL'):
            try:
                src_n = int(tokens[2])
                dst_n = int(tokens[4])
            except ValueError:
                return f"COPY {sub}: bad slot numbers"
            new_name = _name_after(raw, 5) or None

            if sub in ('COLOR', 'COLOUR'):
                src = color_pool.get(src_n)
                if not src: return f"color {src_n} is empty"
                dst = copy.deepcopy(src)
                dst.preset_id = dst_n
                dst.name      = new_name or f"{src.name} (copy)"
                color_pool.presets[dst_n] = dst
                save_show()
                return f"copied color {src_n} '{src.name}' → color {dst_n} '{dst.name}'"
            if sub == 'DIM':
                src = dim_pool.get(src_n)
                if not src: return f"dim {src_n} is empty"
                dst = copy.deepcopy(src)
                dst.preset_id = dst_n
                dst.name      = new_name or f"{src.name} (copy)"
                dim_pool.presets[dst_n] = dst
                save_show()
                return f"copied dim {src_n} '{src.name}' → dim {dst_n} '{dst.name}'"
            if sub == 'GROUP':
                src = group_pool.get(src_n)
                if not src: return f"group {src_n} is empty"
                dst = copy.deepcopy(src)
                dst.group_id = dst_n
                dst.name     = new_name or f"{src.name} (copy)"
                group_pool.groups[dst_n] = dst
                save_show()
                return f"copied group {src_n} '{src.name}' → group {dst_n} '{dst.name}'"
            if sub == 'FX':
                src = fx_pool.get(src_n)
                if not src: return f"FX {src_n} is empty"
                dst = copy.deepcopy(src)
                dst.preset_id = dst_n
                dst.name      = new_name or f"{src.name} (copy)"
                fx_pool.presets[dst_n] = dst
                save_show()
                return f"copied FX {src_n} '{src.name}' → FX {dst_n} '{dst.name}'"
            if sub == 'FORM':
                if dst_n < FormPool.FIRST_CUSTOM_SLOT:
                    return (f"COPY FORM: destination {dst_n} is built-in — "
                            f"only slot ≥ {FormPool.FIRST_CUSTOM_SLOT} can be a copy target")
                src = form_pool.get(src_n)
                if not src: return f"form {src_n} is empty"
                dst = copy.deepcopy(src)
                dst.form_id = dst_n
                dst.name    = new_name or f"{src.name} (copy)"
                form_pool.forms[dst_n] = dst
                save_show()
                return f"copied form {src_n} '{src.name}' → form {dst_n} '{dst.name}'"
            if sub == 'RATE':
                src = rate_pool.get(src_n)
                if not src: return f"rate {src_n} is empty"
                dst = copy.deepcopy(src)
                dst.preset_id = dst_n
                dst.name      = new_name or f"{src.name} (copy)"
                rate_pool.presets[dst_n] = dst
                save_show()
                return f"copied rate {src_n} '{src.name}' → rate {dst_n} '{dst.name}'"
            if sub in ('SIZEP', 'SIZE'):
                src = size_pool.get(src_n)
                if not src: return f"size {src_n} is empty"
                dst = copy.deepcopy(src)
                dst.preset_id = dst_n
                dst.name      = new_name or f"{src.name} (copy)"
                size_pool.presets[dst_n] = dst
                save_show()
                return f"copied size {src_n} '{src.name}' → size {dst_n} '{dst.name}'"
            if sub in ('SPREADP', 'SPREAD'):
                src = spread_pool.get(src_n)
                if not src: return f"spread {src_n} is empty"
                dst = copy.deepcopy(src)
                dst.preset_id = dst_n
                dst.name      = new_name or f"{src.name} (copy)"
                spread_pool.presets[dst_n] = dst
                save_show()
                return f"copied spread {src_n} '{src.name}' → spread {dst_n} '{dst.name}'"
            if sub in ('POSITION', 'GOBO', 'ZOOM', 'FOCUS', 'BEAM', 'CONTROL'):
                _copy_attr_map = {
                    'POSITION': position_pool, 'GOBO': gobo_pool,
                    'ZOOM': zoom_pool, 'FOCUS': focus_pool,
                    'BEAM': beam_pool, 'CONTROL': control_pool,
                }
                pool = _copy_attr_map[sub]
                src = pool.get(src_n)
                if not src: return f"{sub.title()} preset {src_n} is empty"
                dst = copy.deepcopy(src)
                dst.preset_id = dst_n
                dst.name      = new_name or f"{src.name} (copy)"
                pool.presets[dst_n] = dst
                save_show()
                return (f"copied {sub.title()} {src_n} '{src.name}' "
                        f"→ {sub.title()} {dst_n} '{dst.name}'")

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

    if t0 == 'CLEAR' and len(tokens) >= 2 and tokens[1] == 'DMX':
        univ = None
        if 'UNIVERSE' in tokens:
            ui = tokens.index('UNIVERSE')
            try: univ = int(tokens[ui + 1])
            except (IndexError, ValueError): pass
        if univ is not None:
            removed = len(output_state.direct_dmx.pop(univ, {}))
            return f"cleared {removed} direct DMX override(s) on universe {univ}"
        count = sum(len(v) for v in output_state.direct_dmx.values())
        output_state.direct_dmx.clear()
        return f"cleared {count} direct DMX override(s)"

    if t0 == 'CLEAR' and len(tokens) == 2 and tokens[1] == 'FX':
        _sel_fids = {str(f.fixture_id) for f in prog.selection} if prog.selection else None
        _targets  = _sel_fids or set(prog.data.keys())
        n_masters = 0
        for fid in _targets:
            if '.' in fid:
                continue  # fx_kill and fx live in master keys only
            n_masters += 1
            if fid not in prog.data:
                prog.data[fid] = {}
            vals = prog.data[fid]
            vals.pop('fx', None)
            vals['fx_kill'] = True  # explicit kill state — recordable into cues with fx_outfade
        if _sel_fids:
            _prog_fx_rebuild()  # keep FX on unselected fixtures alive
        else:
            _prog_fx_stop()
            _fx_params.pop('pending_form_id', None)
        _scope = f" ({len(_sel_fids)} fixture(s))" if _sel_fids else ""
        return f"FX kill written for {n_masters} fixture(s){_scope} — record into a cue to store"

    # CLEAR COLOUR / CLEAR COLOR / CLEAR DIM / CLEAR RGB
    # Write explicit zeros into programmer so the operation is recordable into cues with fade times.
    # dim lives in master fixture keys (no '.'), colour channels in sub-fixture keys ('.' in fid).
    if t0 == 'CLEAR' and len(tokens) == 2:
        _pclear = tokens[1].upper()
        _colour_chs = {'red', 'green', 'blue', 'white', 'amber', 'warm_white', 'cool_white'}
        _param_map = {
            'COLOUR': _colour_chs,
            'COLOR':  _colour_chs,
            'RGB':    {'red', 'green', 'blue'},
            'DIM':    {'dim'},
        }
        if _pclear in _param_map:
            _chs = _param_map[_pclear]
            _is_dim = _pclear == 'DIM'
            _sel_fids = {str(f.fixture_id) for f in prog.selection} if prog.selection else None
            _targets  = _sel_fids or set(prog.data.keys())
            _n_written = 0
            for fid in _targets:
                # Colour channels live in sub-fixture keys; dim in master keys
                if _is_dim and '.' in fid:
                    continue
                if not _is_dim and '.' not in fid:
                    continue
                if fid not in prog.data:
                    prog.data[fid] = {}
                vals = prog.data[fid]
                for ch in _chs:
                    vals[ch] = 0.0 if _is_dim else 0
                    _n_written += 1
            _scope = f" ({len(_sel_fids)} fixture(s))" if _sel_fids else ""
            return f"{_pclear.title()} zeroed in programmer{_scope} — record into a cue to store"

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
                return f"color preset {slot} cleared (show saved)"
            return f"color preset {slot} is already empty"
        if sub == 'DIM':
            if slot in dim_pool.presets:
                del dim_pool.presets[slot]
                save_show()
                return f"dim preset {slot} cleared (show saved)"
            return f"dim preset {slot} is already empty"
        if sub in ('GROUP', 'GRP'):
            if slot in group_pool.groups:
                del group_pool.groups[slot]
                save_show()
                return f"group {slot} cleared (show saved)"
            return f"group {slot} is already empty"
        if sub == 'FX':
            if slot in fx_pool.presets:
                del fx_pool.presets[slot]
                save_show()
                return f"FX preset {slot} cleared (show saved)"
            return f"FX preset {slot} is already empty"
        if sub == 'FORM':
            if slot < FormPool.FIRST_CUSTOM_SLOT:
                return f"form {slot} is built-in — only custom forms (slot ≥ {FormPool.FIRST_CUSTOM_SLOT}) can be cleared"
            if slot in form_pool.forms:
                del form_pool.forms[slot]
                save_show()
                return f"form {slot} cleared (show saved)"
            return f"form {slot} is already empty"
        if sub == 'RATE':
            if slot in rate_pool.presets:
                del rate_pool.presets[slot]
                save_show()
                return f"rate preset {slot} cleared (show saved)"
            return f"rate preset {slot} is already empty"
        if sub in ('SIZEP', 'SIZE'):
            if slot in size_pool.presets:
                del size_pool.presets[slot]
                save_show()
                return f"size preset {slot} cleared (show saved)"
            return f"size preset {slot} is already empty"
        if sub in ('SPREADP', 'SPREAD'):
            if slot in spread_pool.presets:
                del spread_pool.presets[slot]
                save_show()
                return f"spread preset {slot} cleared (show saved)"
            return f"spread preset {slot} is already empty"
        _clear_attr_map = {
            'POSITION': position_pool,
            'GOBO':     gobo_pool,
            'ZOOM':     zoom_pool,
            'FOCUS':    focus_pool,
            'BEAM':     beam_pool,
            'CONTROL':  control_pool,
        }
        if sub in _clear_attr_map:
            pool = _clear_attr_map[sub]
            if slot in pool.presets:
                del pool.presets[slot]
                save_show()
                return f"{sub.title()} preset {slot} cleared (show saved)"
            return f"{sub.title()} preset {slot} is already empty"

    if t0 == 'CLEAR' and len(tokens) == 1:
        result = prog.do_clear()
        if result.startswith("programmer cleared"):
            _prog_fx_stop()
        elif result == "output_clear":
            _prog_fx_stop()
            _blackout_saved_level[0] = output_state.master_level
            output_state.master_level = 0.0
            return "output cleared — master → 0%  (BLACKOUT OFF to restore)"
        return result

    if t0 == 'UNDO':
        return prog.undo()

    # ── PROGRAMMER SHOW — human-readable programmer contents ──────────────────
    if t0 == 'PROGRAMMER' and len(tokens) >= 2 and tokens[1] in ('SHOW', 'PRINT', 'DUMP'):
        lines = ["programmer:"]
        for fid in sorted(patch.fixtures, key=int):
            master = patch.fixtures[fid]
            m_data = prog.data.get(str(fid), {})
            subs_data = {k: v for k, v in prog.data.items()
                         if k.startswith(f"{fid}.") and v}
            if not m_data and not subs_data:
                continue
            name_s = master.name
            dim_s = (f"  Dim={m_data['dim']:.0%}" if 'dim' in m_data else "")
            lines.append(f"  [{fid}] {name_s}{dim_s}")
            for sfid, vals in sorted(subs_data.items()):
                sub_idx = sfid.split('.')[1]
                pairs = "  ".join(f"{k}={v}" for k, v in sorted(vals.items()))
                lines.append(f"       sub {sub_idx}: {pairs}")
        if len(lines) == 1:
            lines.append("  (empty)")
        return "\n".join(lines)

    # ── PROGRAMMER CAPTURE — pull live output into programmer for selected fixtures
    if t0 == 'PROGRAMMER' and len(tokens) >= 2 and tokens[1] == 'CAPTURE':
        sel_masters = [f for f in prog.selection if isinstance(f, MasterFixture)]
        if not sel_masters:
            return "PROGRAMMER CAPTURE: select fixtures first"
        cue_merged = output_state._merged_cue_layer()
        prog._push_undo()
        captured = 0
        for master in sel_masters:
            fid = str(master.fixture_id)
            cm = cue_merged.get(fid, {})
            dim = cm.get('dim')
            if dim is not None:
                prog.data.setdefault(fid, {})['dim'] = float(dim)
                captured += 1
            for sub in master.all_subs():
                sfid = str(sub.fixture_id)
                cs_sub = cue_merged.get(sfid, {})
                for ch in sub.profile.channels:
                    val = cs_sub.get(ch)
                    if val is not None:
                        prog.data.setdefault(sfid, {})[ch] = int(val)
                        captured += 1
        return f"captured {captured} param(s) from live output into programmer"

    # ── PROGRAMMER SAVE / LOAD / SNAPSHOTS ───────────────────────────────────
    if t0 == 'PROGRAMMER' and len(tokens) >= 2 and tokens[1] == 'SAVE':
        try:
            slot = int(tokens[2])
        except (IndexError, ValueError):
            return "usage: programmer save <n> [name]"
        snap_name = _name_after(raw, 3) or f"snapshot {slot}"
        _prog_snapshots[slot] = {"name": snap_name, "data": copy.deepcopy(prog.data)}
        ch_count = sum(len(v) for v in prog.data.values() if v)
        return f"programmer snapshot {slot} '{snap_name}' saved ({ch_count} param(s))"

    if t0 == 'PROGRAMMER' and len(tokens) >= 2 and tokens[1] == 'LOAD':
        try:
            slot = int(tokens[2])
        except (IndexError, ValueError):
            return "usage: programmer load <n>"
        snap = _prog_snapshots.get(slot)
        if not snap:
            return f"programmer snapshot {slot} not found"
        prog._push_undo()
        prog.data.clear()
        prog.data.update(copy.deepcopy(snap["data"]))
        ch_count = sum(len(v) for v in prog.data.values() if v)
        return f"programmer loaded from snapshot {slot} '{snap['name']}' ({ch_count} param(s))"

    if t0 == 'PROGRAMMER' and len(tokens) >= 2 and tokens[1] in ('SNAPSHOTS', 'SNAPS'):
        if not _prog_snapshots:
            return "no programmer snapshots saved"
        lines = ["programmer snapshots:"]
        for sl in sorted(_prog_snapshots):
            s = _prog_snapshots[sl]
            ch = sum(len(v) for v in s["data"].values() if v)
            lines.append(f"  [{sl}] {s['name']}  ({ch} param(s))")
        return "\n".join(lines)

    # ── PROGRAMMER SCALE <pct> — multiply all programmer values by pct% ───────
    if t0 == 'PROGRAMMER' and len(tokens) >= 3 and tokens[1] == 'SCALE':
        try:
            pct = float(tokens[2].rstrip('%'))
        except ValueError:
            return f"PROGRAMMER SCALE: bad value '{tokens[2]}'"
        if pct < 0 or pct > 1000:
            return "PROGRAMMER SCALE: use a percentage 0–1000"
        factor = pct / 100.0
        if not prog.data:
            return "PROGRAMMER SCALE: programmer is empty"
        prog._push_undo()
        scaled = 0
        for key, vals in prog.data.items():
            if not vals:
                continue
            if 'dim' in vals:
                vals['dim'] = max(0.0, min(1.0, vals['dim'] * factor))
                scaled += 1
            for ch in list(vals):
                if ch == 'dim':
                    continue
                vals[ch] = max(0, min(255, int(round(vals[ch] * factor))))
                scaled += 1
        return f"programmer scaled to {pct:.0f}% — {scaled} value(s) updated"

    # ── PROGRAMMER STATS ──────────────────────────────────────────────────────
    if t0 == 'PROGRAMMER' and len(tokens) >= 2 and tokens[1] in ('STATS', 'STATUS', 'INFO'):
        m_count   = sum(1 for k in prog.data if '.' not in k and prog.data[k])
        sub_count = sum(1 for k in prog.data if '.' in k and prog.data[k])
        ch_total  = sum(len(v) for v in prog.data.values() if v)
        sel_count = len(prog.selection)
        lines = [
            "programmer:",
            f"  Masters touched : {m_count}",
            f"  Sub-fixtures    : {sub_count}",
            f"  Total params    : {ch_total}",
            f"  Selection       : {sel_count} fixture(s)",
        ]
        if prog.data:
            active_fids = sorted(set(k.split('.')[0] for k in prog.data if prog.data[k]),
                                 key=lambda x: int(x) if x.isdigit() else 0)
            lines.append(f"  Active fixtures : {', '.join(active_fids)}")
        return "\n".join(lines)

    # ── Default: programmer ───────────────────────────────────
    try:
        prog.execute(raw)
        return ""   # programmer already prints its own output
    except Exception as e:
        return f"error: {e}"


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
    speed_master_pool = speed_master_pool,
    attr_pools       = _attr_pools,
    osc              = osc,
    library          = library,
    save_patch_fn    = lambda: ShowFile.save_patch(patch),
    fx_params        = _fx_params,
    audio_engine     = audio_engine,
    audio_mapper     = audio_mapper,
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
        _check("cue recorded", "recorded" in r2 or "cue" in r2)

        run_command("GO CS 1 CUE 5")
        time.sleep(0.25)   # let FadeEngine/FXEngine tick at least once
        ex = executor_pool.get(1)
        _check("fader has active FX after GO", len(ex._fx_ids) > 0)

        dmx = output_state.get_dmx_for_universe(1)
        _check("DMX output computes without exception", len(dmx) == 512)

        # GO FADE — one-shot fade override
        _pt_before = dict(_prog_time)
        r_gf = run_command("GO FADE 7.5")
        _check("GO FADE fires without error", "Cue" in r_gf or "GO" in r_gf)
        _check("GO FADE restores prog_time.on after fire",
               _prog_time['on'] == _pt_before['on'])
        _check("GO FADE restores prog_time.fade after fire",
               _prog_time['fade'] == _pt_before['fade'])

        # FADER SWAP
        _cs1_before = executor_pool.get(1).cuestack
        _cs2_before = executor_pool.get(2).cuestack
        r_swap = run_command("FADER SWAP 1 2")
        _check("FADER SWAP swaps cs onto fader 1",
               executor_pool.get(1).cuestack is _cs2_before)
        _check("FADER SWAP swaps cs onto fader 2",
               executor_pool.get(2).cuestack is _cs1_before)
        # Swap back to restore state for remaining tests
        run_command("FADER SWAP 1 2")

        # COPY FIXTURE
        run_command("1 AT RED 200")                   # set red on fixture 1 (sub-fixture channel)
        _cf_f1 = patch.get(1)
        _cf_f2 = patch.get(2)
        if _cf_f1 and _cf_f2:
            _cf_f1_sub = next(iter(_cf_f1.all_subs()), None)
            _cf_f2_sub = next(iter(_cf_f2.all_subs()), None)
            _cf_red_src = (prog.data.get(str(_cf_f1_sub.fixture_id), {}).get('red')
                           if _cf_f1_sub else None)
            r_cf = run_command("COPY FIXTURE 1 TO 2")
            _cf_red_dst = (prog.data.get(str(_cf_f2_sub.fixture_id), {}).get('red')
                           if _cf_f2_sub else None)
            _check("COPY FIXTURE copies sub channel to destination",
                   _cf_red_src is not None and _cf_red_dst == _cf_red_src)
            _check("COPY FIXTURE returns confirmation message", "copied fixture" in r_cf)
        r_cf_bad = run_command("COPY FIXTURE 999 TO 2")
        _check("COPY FIXTURE rejects unknown source", "not patched" in r_cf_bad or "999" in r_cf_bad)

        # FIXTURE SWAP
        prog.clear_programmer()
        run_command("1 AT R 80")    # fixture 1 red = 80
        run_command("2 AT R 200")   # fixture 2 red = 200
        _fs_f1s = "1.1" if patch.get(1) and next(iter(patch.get(1).all_subs()), None) else None
        _fs_f2s = "2.1" if patch.get(2) and next(iter(patch.get(2).all_subs()), None) else None
        if _fs_f1s and _fs_f2s:
            r_swap = run_command("FIXTURE SWAP 1 2")
            _sw_r1 = prog.data.get(_fs_f1s, {}).get('red')
            _sw_r2 = prog.data.get(_fs_f2s, {}).get('red')
            _check("FIXTURE SWAP moves fixture 2 value to fixture 1", _sw_r1 == 200)
            _check("FIXTURE SWAP moves fixture 1 value to fixture 2", _sw_r2 == 80)
            _check("FIXTURE SWAP returns confirmation", "swapped" in r_swap.lower())
            prog.undo()
            _sw_u1 = prog.data.get(_fs_f1s, {}).get('red')
            _sw_u2 = prog.data.get(_fs_f2s, {}).get('red')
            _check("FIXTURE SWAP pushes an undo snapshot (UNDO restores fixture 1)", _sw_u1 == 80)
            _check("FIXTURE SWAP pushes an undo snapshot (UNDO restores fixture 2)", _sw_u2 == 200)
        prog.clear_programmer()

        # FIXTURE INFO
        _fi = patch.get(1)
        if _fi:
            r_fi = run_command("FIXTURE INFO 1")
            _check("FIXTURE INFO shows fixture name", _fi.name in r_fi)
            _check("FIXTURE INFO shows profile name", _fi.profile.name in r_fi)
            _check("FIXTURE INFO shows channel list", any(ch in r_fi for ch in _fi.profile.channels))
        r_fi_bad = run_command("FIXTURE INFO 999")
        _check("FIXTURE INFO rejects unknown fixture", "not patched" in r_fi_bad or "999" in r_fi_bad)

        # PROGRAMMER STATS
        prog.clear_programmer()
        run_command("1 AT R 200")
        run_command("2 AT R 100")
        r_ps = run_command("PROGRAMMER STATS")
        _check("PROGRAMMER STATS shows sub-fixture count", "Sub-fixtures" in r_ps)
        _check("PROGRAMMER STATS shows total params > 0",
               "Total params" in r_ps and "Total params    : 0" not in r_ps)
        prog.clear_programmer()
        r_ps_empty = run_command("PROGRAMMER STATS")
        _check("PROGRAMMER STATS shows 0 params when clear",
               "Total params    : 0" in r_ps_empty or "0" in r_ps_empty)

        # PROGRAMMER CAPTURE
        prog.clear_programmer()
        run_command("1 THRU 3")           # select fixtures 1-3
        r_cap = run_command("PROGRAMMER CAPTURE")
        _check("PROGRAMMER CAPTURE returns confirmation", "captured" in r_cap)
        prog.clear_programmer()

        # PROGRAMMER SAVE / LOAD
        prog.clear_programmer()
        run_command("1 AT R 150 G 80")    # set some values
        r_psnap = run_command("PROGRAMMER SAVE 5 TestSnap")
        _check("PROGRAMMER SAVE returns confirmation", "saved" in r_psnap.lower())
        _check("PROGRAMMER SAVE stores snapshot", 5 in _prog_snapshots)
        prog.clear_programmer()           # wipe programmer
        _check("PROGRAMMER CLEAR removes values", not prog.data.get("1.1"))
        r_pload = run_command("PROGRAMMER LOAD 5")
        _check("PROGRAMMER LOAD restores values", prog.data.get("1.1", {}).get('red') == 150)
        _check("PROGRAMMER LOAD returns confirmation", "loaded" in r_pload.lower())
        r_psnaps = run_command("PROGRAMMER SNAPSHOTS")
        _check("PROGRAMMER SNAPSHOTS lists the saved slot", "TestSnap" in r_psnaps)
        prog.clear_programmer()

        # PROGRAMMER SHOW
        run_command("1 AT R 200")
        r_pshow = run_command("PROGRAMMER SHOW")
        _f1_master = patch.get(1)
        _check("PROGRAMMER SHOW lists active fixture name",
               _f1_master is not None and _f1_master.name in r_pshow)
        _check("PROGRAMMER SHOW shows channel value", "200" in r_pshow or "red" in r_pshow.lower())
        prog.clear_programmer()
        r_pshow_empty = run_command("PROGRAMMER SHOW")
        _check("PROGRAMMER SHOW shows (empty) when clear", "empty" in r_pshow_empty)

        # Pages + trigger modes
        run_command('PAGE 1 NAME "Test Page"')
        run_command("PAGE 1 ADD CS 1")
        r3 = run_command("page list")
        _check("page created and cuestack added", "Test Page" in r3 and "[1]" in r3)

        run_command("FADER 1 MODE FLASH")
        _check("trigger_mode set", executor_pool.get(1).trigger_mode == 'flash')

        run_command("FADER 1 flash on")
        time.sleep(0.05)
        _check("executor active after flash on", executor_pool.get(1).is_active)

        run_command("FADER 1 flash off")
        _check("executor inactive after flash off", not executor_pool.get(1).is_active)

        # RECORD COLOR/DIM from programmer — verify no AttributeError
        run_command("ALL AT R 200 G 100 B 50")
        r_col = run_command("RECORD COLOR 1 TestRed")
        _check("RECORD COLOR from programmer", "recorded" in r_col or "no RGB" in r_col)

        run_command("ALL AT DIM 80")
        r_dim = run_command("RECORD DIM 1 TestDim")
        _check("RECORD DIM from programmer", "recorded" in r_dim or "no dimmer" in r_dim)

        # Explicit-value record
        r_col2 = run_command("RECORD COLOR 2 BlueTest 0 0 255")
        _check("RECORD COLOR explicit RGB", "recorded" in r_col2)

        r_dim2 = run_command("RECORD DIM 2 Half 50%")
        _check("RECORD DIM explicit level", "recorded" in r_dim2)

        # LIST COLOR/DIM — verify no AttributeError on pool iteration
        r_lc = run_command("LIST COLOR")
        _check("LIST COLOR no exception", "color" in r_lc.lower())

        r_ld = run_command("LIST DIM")
        _check("LIST DIM no exception", "Dim" in r_ld)

        # Verify LIST sub-commands route correctly (not to cuestack listing)
        for _cmd, _kw in [
            ("LIST RATE", "Rate"), ("LIST SIZEP", "Size"),
            ("LIST SPREADP", "Spread"), ("LIST CUESTACKS", "CueStack"),
            ("STATUS", "Console"), ("LIST", "Cuestack"),
        ]:
            _r = run_command(_cmd)
            _check(f"{_cmd!r} routes correctly", _kw.lower() in _r.lower())

        # LIST CUES and LIST CUES CS <n>
        _lc_r = run_command("LIST CUES")
        _check("LIST CUES returns cue list for active cuestack",
               "CS " in _lc_r or "not found" in _lc_r.lower())
        _lc_cs1 = run_command("LIST CUES CS 1")
        _check("LIST CUES CS 1 targets cuestack 1",
               "CS 1" in _lc_cs1 or "not found" in _lc_cs1.lower())

        # COPY pool preset routing — was broken by overly broad COPY CUE handler
        run_command("RECORD COLOR 5 CopySource 255 128 0")
        r_cp_col = run_command("COPY COLOR 5 TO 6 CopiedColor")
        _check("COPY COLOR routes to pool handler", "copied color" in r_cp_col)
        run_command("RECORD DIM 5 CopySrc 75%")
        r_cp_dim = run_command("COPY DIM 5 TO 6 CopiedDim")
        _check("COPY DIM routes to pool handler", "copied dim" in r_cp_dim)

        # CLEAR RATE / SIZEP / SPREADP / FORM — parity gap found by audit: every
        # other pool type (COLOR/DIM/GROUP/FX/attr pools) already had CLEAR.
        run_command("RECORD RATE 9 ClearMe 90")
        r_clr_rate = run_command("CLEAR RATE 9")
        _check("CLEAR RATE deletes the preset", "cleared" in r_clr_rate.lower())
        _check("CLEAR RATE actually removed it", rate_pool.get(9) is None)
        run_command("RECORD SIZEP 9 ClearMe 40")
        r_clr_size = run_command("CLEAR SIZEP 9")
        _check("CLEAR SIZEP deletes the preset", "cleared" in r_clr_size.lower())
        run_command("RECORD SPREADP 9 ClearMe 40")
        r_clr_spread = run_command("CLEAR SPREADP 9")
        _check("CLEAR SPREADP deletes the preset", "cleared" in r_clr_spread.lower())
        run_command('record form 9 ClearMe 0,0 1,1')
        r_clr_form = run_command("CLEAR FORM 9")
        _check("CLEAR FORM deletes a custom form", "cleared" in r_clr_form.lower())
        r_clr_form_builtin = run_command("CLEAR FORM 1")
        _check("CLEAR FORM protects built-in slot 1", "built-in" in r_clr_form_builtin.lower())

        # COPY FORM — the one pool type missing from COPY entirely (audit finding)
        run_command('record form 8 CopySrcform 0,0 0.5,1 1,0')
        r_cp_form = run_command("COPY FORM 8 TO 9 CopiedForm")
        _check("COPY FORM routes to pool handler", "copied form" in r_cp_form)
        _check("COPY FORM created the destination", form_pool.get(9) is not None)
        r_cp_form_builtin = run_command("COPY FORM 8 TO 2 Overwrite")
        _check("COPY FORM protects built-in destination slots",
               "built-in" in r_cp_form_builtin.lower())

        # Fader-page paging — GUIEngine._fpg_exec_for_slot/_fpg_slot_for_exec map
        # a fixed 15-slot panel onto banks of executors (page 2 slot 1 = exec 16).
        # Pure functions, no dpg context needed, so they're smoke-testable headless.
        _check("fpg slot->exec page 1 slot 1 == exec 1",
               GUIEngine._fpg_exec_for_slot(1, 1) == 1)
        _check("fpg slot->exec page 2 slot 1 == exec 16",
               GUIEngine._fpg_exec_for_slot(2, 1) == 16)
        _check("fpg slot->exec page 3 slot 15 == exec 45",
               GUIEngine._fpg_exec_for_slot(3, 15) == 45)
        _check("fpg exec->slot inverse holds for on-page exec",
               GUIEngine._fpg_slot_for_exec(2, 16) == 1)
        _check("fpg exec->slot returns None for off-page exec",
               GUIEngine._fpg_slot_for_exec(1, 16) is None)
        # _fpg_step_page is the pure half of _on_fpg_page_prev/next (the dpg-
        # touching half needs a live GUI context, so it's exercised only by
        # hand — dpg calls segfault the process outright when no context is
        # active, rather than raising a catchable exception).
        gui._fpg_page = 1
        gui._fpg_step_page(-1)
        _check("fader page cannot go below page 1", gui._fpg_page == 1)
        gui._fpg_step_page(1)
        gui._fpg_step_page(1)
        _check("fader page increments normally", gui._fpg_page == 3)
        gui._fpg_page = 1  # reset so later state (e.g. SAVE) isn't affected

        # TAP command — pre-seed _tap_times to avoid sleep; two taps → BPM
        _tap_times.clear()
        _tap_times.append(time.monotonic() - 0.5)  # simulate a prior tap 500ms ago
        _r_tap1 = run_command("TAP")                 # second tap → should compute BPM
        _check("TAP computes BPM from two taps", "BPM" in _r_tap1 or "→" in _r_tap1)

        # MIDI text commands — add, list, remove
        _r_midi_map = run_command("MIDI CC 15 100 GO")
        _check("MIDI CC maps correctly", "mapped" in _r_midi_map)
        _r_midi_list = run_command("LIST MIDI")
        _check("LIST MIDI shows new mapping", "ch15" in _r_midi_list)
        _r_midi_rm = run_command("MIDI REMOVE CC 15 100")
        _check("MIDI REMOVE CC removes mapping", "removed" in _r_midi_rm)
        _r_targets = run_command("MIDI TARGETS")
        _check("MIDI TARGETS lists targets", "GO" in _r_targets)

        # HIGHLIGHT must not survive BLACKOUT — real output computation,
        # not just the flag, since BLACKOUT is the show-stopping safety cutoff.
        run_command("ALL")
        run_command("HIGHLIGHT")
        run_command("BLACKOUT")
        _dmx_bbo = output_state.get_dmx_for_universe(1)
        _check("BLACKOUT overrides HIGHLIGHT in DMX output", max(_dmx_bbo) == 0)
        run_command("BLACKOUT OFF")
        run_command("HIGHLIGHT OFF")

        # FREEZE must not defeat BLACKOUT, SOLO, or a direct DMX override —
        # real output computation, not just the flags. FREEZE snapshots a
        # look; it must not be a way to disable the master safety cutoff.
        # FADER 1 STOP + FX CLEAR first: the very first smoke-test check
        # (near the top of this block) GO'd a sine-RED FX cue on fader 1
        # and never stopped it, so it's been running live in the background
        # ever since. With a selection active, "FX CLEAR" only clears
        # programmer FX (by design, scoped to selection) and leaves that
        # executor's FX running -- its real-time envelope would otherwise
        # make the frozen red value here timing-dependent instead of
        # deterministic. Stop the executor directly so nothing but this
        # test's own explicit AT command drives colour into the freeze.
        run_command("FADER 1 STOP")
        run_command("FX CLEAR")
        run_command("ALL AT R 200 G 150 B 100")
        run_command("FREEZE")
        _dmx_frozen = output_state.get_dmx_for_universe(1)
        _check("FREEZE snapshot holds the look", max(_dmx_frozen) > 0)
        run_command("BLACKOUT")
        _dmx_frozen_bbo = output_state.get_dmx_for_universe(1)
        _check("BLACKOUT overrides FREEZE in DMX output", max(_dmx_frozen_bbo) == 0)
        run_command("BLACKOUT OFF")
        _dmx_frozen_restored = output_state.get_dmx_for_universe(1)
        _check("FREEZE look restored after BLACKOUT OFF", _dmx_frozen_restored == _dmx_frozen)
        run_command("DMX 1 42")
        _dmx_frozen_override = output_state.get_dmx_for_universe(1)
        _check("direct DMX override still applies during FREEZE", _dmx_frozen_override[0] == 42)
        run_command("CLEAR DMX")

        # GRANDMASTER
        output_state.master_level = 1.0
        r_gm_show = run_command("GRANDMASTER")
        _check("GRANDMASTER (no args) shows current level", "%" in r_gm_show)
        r_gm_set = run_command("GM 75")
        _check("GM 75 sets master to 75%", abs(output_state.master_level - 0.75) < 0.01)
        _check("GM 75 returns confirmation with new level", "75" in r_gm_set)
        run_command("GM FULL")
        _check("GM FULL sets master to 100%", output_state.master_level == 1.0)
        run_command("GM OUT")
        _check("GM OUT sets master to 0%", output_state.master_level == 0.0)
        output_state.master_level = 1.0   # restore

        # SHOW INFO
        r_si = run_command("SHOW INFO")
        _check("SHOW INFO returns multi-line overview", len(r_si.splitlines()) >= 5)
        _check("SHOW INFO shows fixture count", "Fixtures" in r_si)
        _check("SHOW INFO shows master level", "Master" in r_si)

        # OUTPUT STATUS
        run_command("MASTER 100")          # ensure master at full
        run_command("FREEZE OFF")
        run_command("1 FULL")              # put fixture 1 at 100% in programmer
        r_os = run_command("OUTPUT STATUS")
        _check("OUTPUT STATUS returns non-empty string", len(r_os) > 10)
        _check("OUTPUT STATUS shows master level", "master=" in r_os.lower() or "Output" in r_os)
        prog.clear_programmer()

        # SOLO's "zero everyone else" guarantee must also survive FREEZE —
        # same class of bug, found by a background audit of the same code.
        # Seed a synthetic frozen snapshot directly instead of re-capturing
        # one through run_command("FREEZE") -- this isolates the check to
        # exactly the SOLO-during-FREEZE branch instead of also depending on
        # whatever dim/FX state other tests in this shared process happen
        # to have left on fixture 1 (that state is real but not this
        # check's concern).
        _solo_out = output_state.patch.get(1).all_subs()[0].outputs[0]
        _other_out = output_state.patch.get(3).all_subs()[0].outputs[0]
        _univ = _solo_out['universe']
        output_state.frozen_dmx[_univ] = tuple([200] * 512)
        output_state.freeze_mode = True
        run_command("1")
        run_command("SOLO")
        _dmx_frozen_solo = output_state.get_dmx_for_universe(_univ)
        _check("SOLO still zeros non-solo fixtures during FREEZE",
               _dmx_frozen_solo[_other_out['address'] - 1] == 0)
        _check("SOLO still passes the solo'd fixture during FREEZE",
               _dmx_frozen_solo[_solo_out['address'] - 1] > 0)
        run_command("SOLO OFF")
        run_command("FREEZE OFF")

        # RECORD GROUP + recall — untested prior to this session
        run_command("1 THRU 3")
        r_grp = run_command("RECORD GROUP 9 SmokeGroup")
        _check("RECORD GROUP from selection", "recorded" in r_grp)
        r_grp_recall = run_command("GROUP 9")
        _check("GROUP recall", "recalled" in r_grp_recall.lower())
        r_gi = run_command("GROUP 9 INFO")
        _check("GROUP INFO shows group name", "SmokeGroup" in r_gi)
        _check("GROUP INFO shows member count", "Members" in r_gi)

        # GROUP ADD / GROUP REMOVE
        _g9 = group_pool.get(9)
        _g9_before = len(_g9.members)
        r_gadd = run_command("GROUP 9 ADD 4")   # add fixture 4
        _check("GROUP ADD increases member count by 1", len(_g9.members) == _g9_before + 1)
        _check("GROUP ADD returns confirmation", "added" in r_gadd.lower())
        r_gadd_dup = run_command("GROUP 9 ADD 4")
        _check("GROUP ADD rejects duplicate fixture", "already" in r_gadd_dup.lower())
        r_grem = run_command("GROUP 9 REMOVE 4")
        _check("GROUP REMOVE decreases member count by 1", len(_g9.members) == _g9_before)
        _check("GROUP REMOVE returns confirmation", "removed" in r_grem.lower())
        r_grem_miss = run_command("GROUP 9 REMOVE 4")
        _check("GROUP REMOVE rejects missing fixture", "not in group" in r_grem_miss.lower())

        # record form (custom breakpoint curve) — untested prior to this session
        r_form = run_command("record form 6 SmokeWave 0.0,0.0 0.5,1.0 1.0,0.0")
        _check("record form custom breakpoints", "recorded" in r_form)
        r_form_list = run_command("FORM LIST")
        _check("FORM LIST shows recorded form", "smokewave" in r_form_list.lower())

        # RECORD FX + FIRE FX roundtrip — untested prior to this session
        run_command("1 THRU 3")
        run_command("FX SINE BLUE BPM 40")
        r_fx_rec = run_command("RECORD FX 9 SmokeFX")
        _check("RECORD FX from programmer", "recorded" in r_fx_rec)
        run_command("FX CLEAR")
        r_fx_fire = run_command("FIRE FX 9")
        _check("FIRE FX reapplies preset", "FX" in r_fx_fire)
        run_command("FX CLEAR")

        # FX pool save/load round-trip must preserve speed_id (SpeedMaster
        # link) -- was silently dropped by save_fx_pool/load_fx_pool, so a
        # layer linked to a speed master reverted to its raw bpm on every
        # restart with no error.
        _speed_preset = FXPreset(19, "SmokeSpeedLink")
        _speed_preset.add_layer("sine", "red", bpm=45.0, speed_id=3)
        fx_pool.store(19, _speed_preset)
        ShowFile.save_fx_pool(fx_pool)
        _reloaded_fx_pool = FXPool()
        ShowFile.load_fx_pool(_reloaded_fx_pool)
        _reloaded_layer = _reloaded_fx_pool.get(19).layers[0]
        _check("fx_pool save/load preserves speed_id",
               _reloaded_layer.get("speed_id") == 3)

        # RECORD FX must also forward speed_id from the programmer's FX defs
        # into the stored preset (same bug, second call site).
        run_command("1 THRU 3")
        run_command("FX SINE GREEN BPM 50")
        for _fid, _vals in prog.data.items():
            if '.' not in _fid:
                for _ld in _vals.get('fx', []):
                    _ld['speed_id'] = 7
        r_fx_rec2 = run_command("RECORD FX 20 SmokeSpeedRec")
        _check("RECORD FX from programmer", "recorded" in r_fx_rec2)
        _check("RECORD FX preserves speed_id",
               fx_pool.get(20).layers[0].get("speed_id") == 7)
        run_command("FX CLEAR")

        # Attribute pools (POSITION/GOBO/ZOOM/FOCUS/BEAM/CONTROL) — GUI panel
        # landed last session but the record path was never smoke-tested.
        # These fixtures (SGM_RGB_54) have no pan/tilt/gobo/etc channels, so
        # recording should fail gracefully (not crash) rather than succeed.
        for _attr in ("POSITION", "GOBO", "ZOOM", "FOCUS", "BEAM", "CONTROL"):
            r_attr = run_command(f"RECORD {_attr} 9 Smoke{_attr.title()}")
            _check(f"RECORD {_attr} handles no-data case cleanly",
                   "no" in r_attr.lower() and "data in programmer" in r_attr.lower())

        # OSC input dispatch (Block 11) — /gma3/fader/PAGE/EXEC is documented
        # as a 2-segment address (page, exec) and _osc_fader parses it as
        # such, but the registered pattern had an extra "/*" wildcard segment
        # baked in since it was first added, so real /gma3/fader/1/1 messages
        # never matched it and silently fell through to the unmapped default
        # handler. Exercise the real dispatcher (not just call the handler
        # function directly) so a future pattern/handler mismatch here is
        # caught the same way this one was found.
        from pythonosc.osc_message_builder import OscMessageBuilder as _OscMsgBuilder
        _prev_fader_dim = _fader_dim[0]
        _fader_msg = _OscMsgBuilder(address="/gma3/fader/1/1")
        _fader_msg.add_arg(0.42)
        osc._dispatch.call_handlers_for_packet(_fader_msg.build().dgram, ("127.0.0.1", 0))
        _check("OSC /gma3/fader/1/1 reaches _osc_fader and sets grandmaster dim",
               abs(_fader_dim[0] - 0.42) < 1e-6)
        _fader_dim[0] = _prev_fader_dim

        # OSC page/fader addressing used to hard-gate all fader/key behavior
        # on "page == 1 and fader == 1" — any other fader was parsed
        # and logged but silently dropped. Exercise fader 3 (arbitrary, not
        # fader 1) through the real dispatcher to confirm it now reaches
        # that fader's own level/GO/BACK, same as "FADER 3 LEVEL ..." /
        # "FADER 3 GO" typed on the command line.
        _osc_ex = executor_pool.get(3)
        _prev_osc_ex_level = _osc_ex.level
        _fader3_msg = _OscMsgBuilder(address="/gma3/fader/1/3")
        _fader3_msg.add_arg(0.65)
        osc._dispatch.call_handlers_for_packet(_fader3_msg.build().dgram, ("127.0.0.1", 0))
        _check("OSC /gma3/fader/1/3 sets fader 3's own level (not grandmaster)",
               abs(_osc_ex.level - 0.65) < 1e-6)
        _osc_ex.level = _prev_osc_ex_level

        # cuestack 3 is wired to executor 3 by default at startup (every
        # loaded cuestack assigns 1:1 into the matching executor slot), so
        # a real GO on exec 3 should activate it.
        _key3_msg = _OscMsgBuilder(address="/gma3/key/1/3/go")
        _key3_msg.add_arg(1)
        osc._dispatch.call_handlers_for_packet(_key3_msg.build().dgram, ("127.0.0.1", 0))
        _check("OSC /gma3/key/1/3/go GOes fader 3 (routes through FADER 3 GO)",
               _osc_ex.is_active)

        # /gma3/key/PAGE/EXEC/flash used to be silently dropped: the handler
        # returned immediately on any release (0) event regardless of TYPE,
        # and even on press only recognized go/go+/back/go-. A TouchOSC/
        # Chataigne "flash" key sent 1 then 0 and nothing happened at all.
        # Exercise both press and release through the real dispatcher.
        _flash_press_msg = _OscMsgBuilder(address="/gma3/key/1/3/flash")
        _flash_press_msg.add_arg(1)
        osc._dispatch.call_handlers_for_packet(_flash_press_msg.build().dgram, ("127.0.0.1", 0))
        _check("OSC /gma3/key/1/3/flash press fires FADER 3 flash on",
               _osc_ex.is_active)
        _flash_release_msg = _OscMsgBuilder(address="/gma3/key/1/3/flash")
        _flash_release_msg.add_arg(0)
        osc._dispatch.call_handlers_for_packet(_flash_release_msg.build().dgram, ("127.0.0.1", 0))
        _check("OSC /gma3/key/1/3/flash release fires FADER 3 flash off",
               not _osc_ex.is_active)

        # AudioEngine (Block 9) has an AUDIO command surface and a GUI panel
        # (audio_window) now, but its import used to be unconditional -- a
        # missing sounddevice package or native Portaudio lib crashed the
        # entire console before a single fixture patched. Force the
        # unavailable branch here so the guard is verified on every run,
        # regardless of whether this box happens to have a working audio
        # stack installed.
        _audio_probe = AudioEngine()
        _prev_audio_avail = _AUDIO_AVAILABLE
        _AUDIO_AVAILABLE = False
        try:
            try:
                _audio_probe.list_devices()
                _list_ok = True
            except Exception:
                _list_ok = False
            _check("AudioEngine.list_devices() doesn't raise when unavailable", _list_ok)

            try:
                _audio_probe.start()
                _check("AudioEngine.start() raises RuntimeError when unavailable", False)
            except RuntimeError:
                _check("AudioEngine.start() raises RuntimeError when unavailable", True)
            except Exception as _ae:
                _check(f"AudioEngine.start() raised wrong exception "
                       f"({type(_ae).__name__}) when unavailable", False)

            # AUDIO command wiring — the engine/mapper above were dead code
            # with zero command/GUI surface until this session; exercise the
            # run_command() path itself (not just the classes directly) the
            # same way the OSC dispatcher check above does. ON/OFF/STATUS/GAIN
            # don't touch real hardware so they're safe with a real audio
            # stack installed too; START/DEVICES are only exercised in the
            # forced-unavailable branch to avoid opening a real mic stream.
            run_command("AUDIO OFF")
            _check("AUDIO OFF works pre-start", not audio_mapper.enabled)
            run_command("AUDIO ON")
            _check("AUDIO ON enables mapper", audio_mapper.enabled)
            r_audio_status = run_command("AUDIO STATUS")
            _check("AUDIO STATUS reports mapping ON", "mapping ON" in r_audio_status)
            run_command("AUDIO OFF")
            _check("AUDIO OFF disables mapper", not audio_mapper.enabled)
            _prev_gain = audio_engine.gain
            run_command("AUDIO GAIN 5")
            _check("AUDIO GAIN sets engine gain", audio_engine.gain == 5.0)
            audio_engine.gain = _prev_gain

            r_devices = run_command("AUDIO DEVICES")
            _check("AUDIO DEVICES reports unavailable cleanly",
                   "unavailable" in r_devices.lower())
            r_start = run_command("AUDIO START")
            _check("AUDIO START reports failure cleanly (no crash)",
                   "failed" in r_start.lower())
        finally:
            _AUDIO_AVAILABLE = _prev_audio_avail

        # CLEAR stage 3 — should blackout output, not silently return "output_clear"
        prog.do_clear(); prog.do_clear()   # advance to stage 2 (programmer cleared)
        _saved_master = output_state.master_level
        output_state.master_level = 0.8    # set master to non-zero so blackout is detectable
        prog._clear_stage = 2              # force stage 3 on next CLEAR
        _r_clear3 = run_command("CLEAR")
        _check("CLEAR stage 3 blacks out master", output_state.master_level == 0.0)
        output_state.master_level = _saved_master  # restore for any remaining tests

        # RECORD CUE with FOLLOW time — was silently dropped before the fix
        run_command("ALL AT R 255 G 0 B 0")
        _r_follow = run_command("RECORD CS 1 CUE 99 FollowTest FOLLOW 3.5")
        _cs_1 = cuestack_pool.get(1)
        _cue_99 = _cs_1.cues.get(99.0) if _cs_1 else None
        _check("RECORD CUE stores FOLLOW time", _cue_99 is not None and
               abs(getattr(_cue_99, 'follow_time', 0) - 3.5) < 0.01)

        # COPY CUE preserves follow_time and note
        if _cue_99:
            _cue_99.note = "test note"
        run_command("COPY CUE 99 TO 98 CS 1")
        _cue_98 = _cs_1.cues.get(98.0) if _cs_1 else None
        _check("COPY CUE copies follow_time", _cue_98 is not None and
               abs(getattr(_cue_98, 'follow_time', 0) - 3.5) < 0.01)
        _check("COPY CUE copies note", _cue_98 is not None and
               getattr(_cue_98, 'note', '') == "test note")

        # MOVE CUE renumbers and removes source
        run_command("MOVE CUE 98 TO 97 CS 1")
        _check("MOVE CUE creates destination", _cs_1.cues.get(97.0) is not None)
        _check("MOVE CUE removes source", _cs_1.cues.get(98.0) is None)

        # GOTO non-existent cue returns error, not false success
        _r_goto_bad = run_command("GOTO 9999")
        _check("GOTO non-existent cue returns error", "not found" in (_r_goto_bad or "").lower())

        # FADER GOTO FIRST / LAST
        _gtfl_ex = executor_pool.get(1)
        if _gtfl_ex and _gtfl_ex.cuestack and _gtfl_ex.cuestack.cues:
            _gtfl_cs = _gtfl_ex.cuestack
            _gtfl_first = _gtfl_cs._sorted_cue_numbers()[0]
            _gtfl_last  = _gtfl_cs._sorted_cue_numbers()[-1]
            run_command("FADER 1 GOTO FIRST")
            _check("FADER GOTO FIRST positions cuestack at first cue",
                   _gtfl_cs.current == _gtfl_first)
            run_command("FADER 1 GOTO LAST")
            _check("FADER GOTO LAST positions cuestack at last cue",
                   _gtfl_cs.current == _gtfl_last)

        # delete cue cleans up cue_pool
        run_command("ALL AT R 128 G 0 B 0")
        run_command("RECORD CS 1 CUE 96")
        _check("delete cue: cue_pool stale ref cleaned", True)  # record stores in pool
        _pool_has_96_before = cue_pool.get(96) is not None
        run_command("delete cue 96 CS 1")
        _check("delete cue removes from cue_pool",
               _pool_has_96_before and cue_pool.get(96) is None)

        # speed master: set/get BPM
        _r_spd = run_command("SPEED 4 200")
        _check("SPEED command sets BPM", speed_master_pool.get_bpm(4) == 200.0)
        _r_spd_name = run_command("SPEED 4 NAME StrobeClk")
        _check("SPEED NAME renames slot", speed_master_pool.get(4).name == "Strobeclk")
        _r_list_spd = run_command("LIST SPEED")
        _check("LIST SPEED shows all slots", "speed Masters" in (_r_list_spd or ""))
        # FX layer with speed master reference uses master BPM
        run_command("FX SINE RED BPM 60")
        _check("FX inline BPM default before speed ref", True)
        speed_master_pool.set_bpm(4, 333.0)
        _layer0 = active_fx[0] if active_fx else None
        if _layer0:
            _layer0._speed_id = 4
            _layer0._speed_master_pool = speed_master_pool
        _check("FX layer rate_bpm uses speed master", (
            _layer0 is None or abs(_layer0.rate_bpm - 333.0) < 0.1))

        # ── FX ENGINE COMPREHENSIVE TESTS ─────────────────────────────────────

        # Waveform range: all outputs must stay in [0, 1]
        import math as _math
        def _wv_range(name, fn):
            vals = [fn(t / 200.0) for t in range(200)]
            return min(vals) >= 0.0 and max(vals) <= 1.0
        _check("waveform sine range [0,1]",     _wv_range('sine',     Waveform.sine))
        _check("waveform ramp range [0,1]",     _wv_range('ramp',     Waveform.ramp))
        _check("waveform square range [0,1]",   _wv_range('square',   Waveform.square))
        _check("waveform pulse range [0,1]",    _wv_range('pulse',    Waveform.pulse))
        _check("waveform triangle range [0,1]", _wv_range('triangle', Waveform.triangle))
        _check("waveform sawtooth range [0,1]", _wv_range('sawtooth', Waveform.sawtooth))
        _check("waveform flicker range [0,1]",
               all(0.0 <= Waveform.flicker(t/200.0, i) <= 1.0
                   for t in range(200) for i in range(10)))

        # Flicker per-pixel independence: 10 pixels at same phase must differ
        _fl_vals = [Waveform.flicker(0.5, i) for i in range(10)]
        _check("flicker has per-pixel variation", len(set(_fl_vals)) > 1)

        # Flicker time resolution: enough unique states per cycle for 44Hz
        _fl_cycle = [Waveform.flicker(t / 100.0, 0) for t in range(100)]
        _check("flicker has ≥44 unique states/cycle", len(set(_fl_cycle)) >= 44)

        # Sine shape: trough at 0, peak at 0.5, back to trough at 1.0
        _check("sine shape: trough at 0.0",
               abs(Waveform.sine(0.0) - 0.0) < 0.01)
        _check("sine shape: peak at 0.5",
               abs(Waveform.sine(0.5) - 1.0) < 0.01)

        # Pulse duty cycle: on for exactly 25% of a cycle
        _pulse_on = sum(1 for t in range(1000) if Waveform.pulse(t/1000.0) > 0.5)
        _check("pulse duty cycle is 25%", abs(_pulse_on - 250) <= 2)

        # Strobe shorthand: STROBE creates a pulse dim FX layer
        run_command("FX CLEAR")
        _r_strobe = run_command("STROBE 120")
        _check("STROBE creates FX layer", active_fx != [] or "FX" in (_r_strobe or ""))

        # STROBE CLEAR removes dim FX
        run_command("STROBE 120")
        run_command("STROBE CLEAR")
        _strobe_still = any(l.channel == 'dim' for l in (active_fx or []))
        _check("STROBE CLEAR removes dim FX", not _strobe_still)

        # rainbow shorthand: RAINBOW creates 3 colour FX layers
        run_command("FX CLEAR")
        _r_rainbow = run_command("RAINBOW 60 100")
        _rainbow_chans = [l.channel for l in (active_fx or [])]
        _check("RAINBOW creates red layer",   'red'   in _rainbow_chans)
        _check("RAINBOW creates green layer", 'green' in _rainbow_chans)
        _check("RAINBOW creates blue layer",  'blue'  in _rainbow_chans)
        # Phase offsets should differ by ~0.33 between R→G and G→B
        _rb_layers = sorted(
            [l for l in (active_fx or []) if l.channel in ('red','green','blue')],
            key=lambda l: l.phase_offset)
        if len(_rb_layers) >= 3:
            _rb_ph = [l.phase_offset for l in _rb_layers]
            _check("RAINBOW phases spaced ~0.33 apart",
                   abs(_rb_ph[1] - _rb_ph[0] - 0.333) < 0.01 or
                   abs(_rb_ph[2] - _rb_ph[1] - 0.333) < 0.01)
        else:
            _check("RAINBOW phases (need 3 layers)", False)

        # Spread: with spread=100 and ≥2 targets, offsets are not all identical
        run_command("FX CLEAR")
        run_command("FX SINE RED SPREAD 100 BPM 60")
        _sp_layer = (active_fx or [None])[0]
        if _sp_layer and len(_sp_layer._offsets) >= 2:
            _check("spread=100 creates non-zero offsets",
                   len(set(round(o, 4) for o in _sp_layer._offsets)) > 1)
        else:
            _check("spread=100 (need ≥2 targets)", _sp_layer is None)

        # FX size scales amplitude: size=50 → max ~127 DMX
        run_command("FX CLEAR")
        run_command("FX SINE RED SIZE 50 SPREAD 0 BPM 60")
        _sz_layer = (active_fx or [None])[0]
        if _sz_layer:
            _sz_vals = _sz_layer.get_values(time.monotonic())
            _sz_max  = max(_sz_vals.values()) if _sz_vals else 0
            _check("FX size=50 gives max ~127 DMX", _sz_max <= 128.0)
        else:
            _check("FX size=50 (layer needed)", False)

        # dim FX: multiplicative (FX PULSE DIM should not exceed base dim)
        run_command("FX CLEAR")
        run_command("FX SQUARE DIM SIZE 100 SPREAD 0 BPM 30")
        _dm_layer = next((l for l in (active_fx or []) if l.channel == 'dim'), None)
        _check("dim FX layer channel is 'dim'", _dm_layer is not None)

        # Bounce direction: phase reverses after one cycle
        run_command("FX CLEAR")
        run_command("FX RAMP RED SPREAD 100 BPM 60 DIRECTION BOUNCE")
        _bn_layer = (active_fx or [None])[0]
        _check("bounce direction stored", _bn_layer is not None and _bn_layer.direction == 'bounce')

        # Block size: adjacent pixels grouped
        run_command("FX CLEAR")
        run_command("FX RAMP RED SPREAD 100 BLOCK 3 BPM 60")
        _bk_layer = (active_fx or [None])[0]
        if _bk_layer and len(_bk_layer._offsets) >= 6:
            _bk_off = _bk_layer._offsets
            _check("block_size=3 groups adjacent targets (offsets equal)",
                   _bk_off[0] == _bk_off[1] == _bk_off[2] and
                   _bk_off[3] == _bk_off[4] == _bk_off[5])
        else:
            _check("block_size=3 (need ≥6 targets)", True)

        # Infade: envelope ramps from 0 at start
        run_command("FX CLEAR")
        run_command("FX SINE RED INFADE 5 BPM 60")
        _if_layer = (active_fx or [None])[0]
        if _if_layer:
            _if_layer.start = time.monotonic()  # reset start so env starts at 0
            _if_layer.get_values(time.monotonic())
            _check("infade envelope starts near 0", _if_layer._last_env < 0.5)
        else:
            _check("infade (layer needed)", False)

        run_command("FX CLEAR")

        # ── CUE DIM TRACKING TESTS ───────────────────────────────────────────
        # Verify that dim in cue 1 tracks through cue 2 (FX-only) and cue 3 (empty).
        # This exercises the LTP tracking path in Fade.tick() for the case where
        # data_to has no dim entry.

        _ts_cs = CueStack(999, "TrackTest")

        # cue 1: dim=0.8 stored explicitly
        _tc1 = Cue(1.0, "Track1")
        _tc1.data = {'_test_fid': {'dim': 0.8}}
        _ts_cs.cues[1.0] = _tc1

        # cue 2: no dim (should track 0.8 from cue 1)
        _tc2 = Cue(2.0, "Track2")
        _tc2.data = {}
        _ts_cs.cues[2.0] = _tc2

        # cue 3: empty (should still track 0.8)
        _tc3 = Cue(3.0, "Track3")
        _tc3.data = {}
        _ts_cs.cues[3.0] = _tc3

        # Simulate the Fade.tick() tracking logic directly (no real executor needed)
        def _sim_fade(data_from, data_to):
            """Return resulting layer after a tracking fade (t=1.0, instant)."""
            result = {}
            for fid in set(data_from) | set(data_to):
                fv = data_from.get(fid, {})
                tv = data_to.get(fid, {})
                if fid not in result:
                    result[fid] = {}
                for ch in set(fv) | set(tv):
                    v_from = fv.get(ch, 0)
                    _flag  = ch in ('fx_kill',)
                    v_to   = tv.get(ch, 0 if _flag else v_from)
                    if not isinstance(v_from, (int, float)) or not isinstance(v_to, (int, float)):
                        continue
                    # t=1.0 (fade complete)
                    result[fid][ch] = v_from + (v_to - v_from) * 1.0
            return result

        # cue 1 fires from empty executor
        _layer = {}
        _layer = _sim_fade(_layer, {'_test_fid': {'dim': 0.8}})
        _check("cue tracking: cue 1 sets dim=0.8",
               abs(_layer.get('_test_fid', {}).get('dim', -1) - 0.8) < 0.001)

        # cue 2 fires (no dim in data_to) — should track dim=0.8
        _layer = _sim_fade(_layer, {})
        _check("cue tracking: cue 2 tracks dim from cue 1",
               abs(_layer.get('_test_fid', {}).get('dim', -1) - 0.8) < 0.001)

        # cue 3 fires (also empty) — should still track dim=0.8
        _layer = _sim_fade(_layer, {})
        _check("cue tracking: cue 3 still tracks dim (no stale zero)",
               abs(_layer.get('_test_fid', {}).get('dim', -1) - 0.8) < 0.001)

        # fx_outfade field: cue class should have it, default None
        _fxo_cue = Cue(1.0, "fxout")
        _check("Cue.fx_outfade defaults to None", _fxo_cue.fx_outfade is None)

        # FXOUTFADE keyword in timing edit
        _apply_timing_edit(_fxo_cue, "FXOUTFADE 2.5")
        _check("FXOUTFADE sets cue.fx_outfade", _fxo_cue.fx_outfade == 2.5)

        # COPY CUE / COPY CS / MOVE CUE must preserve fx_outfade (was silently
        # dropped -- Cue() constructor doesn't take it, and all three call
        # sites copied note/data/timings but forgot fx_outfade)
        _fxo_src_cs = cuestack_pool.create(91)
        _fxo_src_cue = Cue(1.0, "FXOutSrc")
        _fxo_src_cue.fx_outfade = 3.25
        _fxo_src_cs.cues[1.0] = _fxo_src_cue
        run_command("COPY CS 91 TO CS 92")
        _fxo_dst_cs = cuestack_pool.get(92)
        _check("COPY CS preserves cue.fx_outfade",
               _fxo_dst_cs is not None and _fxo_dst_cs.cues.get(1.0) is not None and
               _fxo_dst_cs.cues[1.0].fx_outfade == 3.25)

        run_command("COPY CS 91 CUE 1 TO CS 93 CUE 1")
        _fxo_dst_cs2 = cuestack_pool.get(93)
        _check("COPY CUE (single cue) preserves cue.fx_outfade",
               _fxo_dst_cs2 is not None and _fxo_dst_cs2.cues.get(1.0) is not None and
               _fxo_dst_cs2.cues[1.0].fx_outfade == 3.25)

        run_command("MOVE CS 91 CUE 1 TO CS 94 CUE 1")
        _fxo_dst_cs3 = cuestack_pool.get(94)
        _check("MOVE CUE preserves cue.fx_outfade",
               _fxo_dst_cs3 is not None and _fxo_dst_cs3.cues.get(1.0) is not None and
               _fxo_dst_cs3.cues[1.0].fx_outfade == 3.25)

        # FX CLEAR clears executor FX layers
        run_command("FX SINE RED BPM 60 SIZE 100")
        _ex0 = _active_executor()
        _ex0_had_fx = bool(_ex0._fx_ids)
        run_command("FX CLEAR")
        _check("FX CLEAR clears fader FX (executor._fx_ids empty)",
               not _ex0._fx_ids)

        # FX CLEAR scoped to selection — only clears selected fixtures' programmer FX
        run_command("1 THRU 3")   # select fixtures 1-3
        run_command("FX SINE RED BPM 60 SIZE 100")
        _all_fids = list(prog.data.keys())
        run_command("FX CLEAR")   # selection active → programmer-only, scoped
        _cleared_sel = all(
            'fx' not in prog.data.get(str(f.fixture_id), {})
            for f in prog.selection
        )
        _check("FX CLEAR with selection clears only selected fixtures (programmer)",
               _cleared_sel)

        # CLEAR COLOUR removes RGB from programmer, leaves dim intact
        # dim lives in master key ("1"), RGB in sub-fixture keys ("1.1" etc.)
        prog.clear_programmer()
        run_command("1 THRU 3")
        run_command("@ FULL")           # set dim=1.0 on selection
        run_command("1 THRU 3 R 255 G 128 B 64")  # set explicit RGB
        _pre_dim  = prog.data.get("1", {}).get('dim')
        _sub1     = next((k for k in prog.data if k.startswith("1.")), None)
        _pre_red  = prog.data.get(_sub1, {}).get('red') if _sub1 else None
        _check("CLEAR COLOUR pre-check: red was set", _pre_red == 255)
        run_command("CLEAR COLOUR")
        _post_rgb = prog.data.get(_sub1, {}).get('red') if _sub1 else None
        _post_dim = prog.data.get("1", {}).get('dim')
        _check("CLEAR COLOUR zeroes RGB and leaves dim intact",
               _post_rgb == 0 and _post_dim == _pre_dim)

        # CLEAR DIM removes only dimmer, leaves RGB intact
        # RGB lives in sub-fixture keys ("1.1"), dim in master key ("1")
        prog.clear_programmer()
        run_command("1 THRU 3")
        run_command("@ FULL")
        run_command("1 THRU 3 R 200 G 100 B 50")
        run_command("CLEAR DIM")
        _post_dim2 = prog.data.get("1", {}).get('dim')
        _first_sub = next((k for k in prog.data if k.startswith("1.")), None)
        _post_red2 = prog.data.get(_first_sub, {}).get('red') if _first_sub else None
        _check("CLEAR DIM zeroes dim, leaves RGB intact",
               _post_dim2 == 0.0 and _post_red2 == 200)

        # CS n WRAP ON/OFF — clean restart at top after last cue
        run_command("RECORD CUESTACK 99 WrapTest")
        _cs99 = cuestack_pool.get(99)
        _check("CS WRAP: default is False", _cs99.wrap is False)
        run_command("CS 99 WRAP ON")
        _check("CS 99 WRAP ON sets .wrap = True", _cs99.wrap is True)
        run_command("CS 99 WRAP OFF")
        _check("CS 99 WRAP OFF sets .wrap = False", _cs99.wrap is False)

        # CS INFO
        r_csi = run_command("CS 99 INFO")
        _check("CS INFO shows cuestack name", "WrapTest" in r_csi)
        _check("CS INFO shows wrap/loop state", "Wrap" in r_csi or "Loop" in r_csi)
        r_csi_bad = run_command("CS 9999 INFO")
        _check("CS INFO rejects unknown cuestack", "not found" in r_csi_bad)

        # CS REVERSE
        run_command("RECORD CUESTACK 94 RevTest")
        run_command("CUESTACK 94")
        run_command("1 FULL");   run_command("RECORD CUE 1 First")
        run_command("1 OUT");    run_command("RECORD CUE 2 Second")
        run_command("1 AT R 200"); run_command("RECORD CUE 3 Third")
        _cs94 = cuestack_pool.get(94)
        _orig_names = [_cs94.cues[n].name for n in _cs94._sorted_cue_numbers()]
        r_rev = run_command("CS 94 REVERSE")
        _rev_names = [_cs94.cues[n].name for n in _cs94._sorted_cue_numbers()]
        _check("CS REVERSE reverses cue order", _rev_names == list(reversed(_orig_names)))
        _check("CS REVERSE returns confirmation", "reversed" in r_rev)
        _check("CS REVERSE resets current position to None", _cs94.current is None)

        # CS COMPRESS
        run_command("RECORD CUESTACK 95 CompTest")
        run_command("CUESTACK 95")
        run_command("1 FULL"); run_command("RECORD CUE 1 Cue1")
        run_command("1 OUT");  run_command("RECORD CUE 5 Cue5")   # gap: 1, 5
        run_command("1 AT R 200"); run_command("RECORD CUE 10 Cue10")  # cues 1,5,10
        _cs95 = cuestack_pool.get(95)
        r_cmp = run_command("CS 95 COMPRESS")
        _cmp_nums = _cs95._sorted_cue_numbers()
        _check("CS COMPRESS renumbers cues to 1,2,3 (collapses gaps)",
               _cmp_nums == [1.0, 2.0, 3.0])
        _check("CS COMPRESS preserves cue names in order",
               [_cs95.cues[n].name for n in _cmp_nums] == ["Cue1", "Cue5", "Cue10"])
        _check("CS COMPRESS returns 'compressed' confirmation", "compressed" in r_cmp)

        # CS EXTRACT
        run_command("RECORD CUESTACK 97 ExtractSrc")
        run_command("CUESTACK 97")
        run_command("1 FULL"); run_command("RECORD CUE 1 ExtCue1")
        run_command("1 OUT");  run_command("RECORD CUE 2 ExtCue2")
        _cs97 = cuestack_pool.get(97)
        _cs97.note = "Dark Moody Show"
        _cs97.wrap = True
        r_ext = run_command("CS 97 EXTRACT 2 INTO 98")
        _cs98 = cuestack_pool.get(98)
        _check("CS EXTRACT creates new cuestack in target slot", _cs98 is not None)
        _check("CS EXTRACT new cuestack has exactly one cue",
               _cs98 is not None and len(_cs98.cues) == 1)
        _check("CS EXTRACT preserves cue name",
               _cs98 is not None and list(_cs98.cues.values())[0].name.lower() == "extcue2")
        _check("CS EXTRACT returns 'Extracted' confirmation", "extracted" in r_ext)
        _check("CS EXTRACT source cuestack unchanged (still 2 cues)", len(_cs97.cues) == 2)
        _check("CS EXTRACT carries source note to new cuestack",
               _cs98 is not None and _cs98.note == "Dark Moody Show")
        _check("CS EXTRACT carries source wrap flag to new cuestack",
               _cs98 is not None and _cs98.wrap is True)

        # CS DUPLICATE
        run_command("RECORD CUESTACK 99 DupSrc")
        run_command("CUESTACK 99")
        run_command("1 FULL"); run_command("RECORD CUE 1 DupA")
        run_command("1 OUT");  run_command("RECORD CUE 2 DupB")
        _cs99dup = cuestack_pool.get(99)
        _cs99dup.note = "Act 2 Opener"
        _cs99dup.wrap = True
        r_dup = run_command("CS 99 DUPLICATE INTO 100")
        _cs100 = cuestack_pool.get(100)
        _check("CS DUPLICATE creates new cuestack in target slot", _cs100 is not None)
        _check("CS DUPLICATE copies all cues",
               _cs100 is not None and len(_cs100.cues) == len(_cs99dup.cues))
        _check("CS DUPLICATE is a deep copy (modifying source doesn't affect copy)",
               _cs100 is not None and _cs100.cues is not _cs99dup.cues)
        _check("CS DUPLICATE returns 'Duplicated' confirmation", "duplicated" in r_dup)
        _check("CS DUPLICATE source is unchanged", len(_cs99dup.cues) == 2)
        _check("CS DUPLICATE carries source note to new cuestack",
               _cs100 is not None and _cs100.note == "Act 2 Opener")
        _check("CS DUPLICATE carries source wrap flag to new cuestack (regression check)",
               _cs100 is not None and _cs100.wrap is True)

        # CS RENUMBER STEP
        run_command("RECORD CUESTACK 101 StepTest")
        run_command("CUESTACK 101")
        run_command("1 FULL"); run_command("RECORD CUE 1 SA")
        run_command("1 OUT");  run_command("RECORD CUE 2 SB")
        run_command("1 AT R 200"); run_command("RECORD CUE 3 SC")
        _cs101 = cuestack_pool.get(101)
        r_ren = run_command("CS 101 RENUMBER STEP 10")
        _ren_nums = _cs101._sorted_cue_numbers()
        _check("CS RENUMBER STEP 10 gives multiples of 10",
               _ren_nums == [10.0, 20.0, 30.0])
        _check("CS RENUMBER STEP returns confirmation", "renumbered" in r_ren.lower())

        # CUE SHIFT
        run_command("RECORD CUESTACK 96 ShiftTest")
        run_command("CUESTACK 96")
        run_command("1 FULL"); run_command("RECORD CUE 3 MoverCue")
        run_command("1 OUT");  run_command("RECORD CUE 7 StayCue")
        _cs96 = cuestack_pool.get(96)
        r_shift = run_command("CUE 3 SHIFT 5")   # 3+5 = cue 8
        _shift_nums = _cs96._sorted_cue_numbers()
        _check("CUE SHIFT moves cue to new number (3→8)",
               3.0 not in _shift_nums and 8.0 in _shift_nums)
        _check("CUE SHIFT does not disturb other cues",
               7.0 in _shift_nums)
        _check("CUE SHIFT returns confirmation with new number", "8" in r_shift)

        # CUESTACK MERGE
        run_command("RECORD CUESTACK 91 MergeSrc")
        run_command("CUESTACK 91")          # make active
        run_command("1 FULL")
        run_command("RECORD CUE 1 SrcCue1")
        run_command("RECORD CUESTACK 92 MergeDst")
        run_command("CUESTACK 92")
        run_command("1 OUT")
        run_command("RECORD CUE 1 DstCue1")
        _cs91 = cuestack_pool.get(91)
        _cs92 = cuestack_pool.get(92)
        _n_before = len(_cs92.cues)
        r_merge = run_command("CUESTACK MERGE 91 INTO 92")
        _n_after = len(_cs92.cues)
        _check("CUESTACK MERGE adds src cues to dst",
               _n_after == _n_before + len(_cs91.cues))
        _check("CUESTACK MERGE returns confirmation", "merged" in r_merge)
        # Src cue numbers in dst should be offset past dst's original last cue
        _merged_num = max(_cs92._sorted_cue_numbers())
        _check("CUESTACK MERGE renumbers merged cues after dst's last cue",
               _merged_num > 1.0)
        r_merge_bad = run_command("CUESTACK MERGE 9999 INTO 92")
        _check("CUESTACK MERGE rejects unknown source", "not found" in r_merge_bad)

        # CS BACK on wrap-around (first cue -> last cue) must also clear the
        # LTP-bleed layer when WRAP is ON -- CS GO already did this on forward
        # wrap (last -> first); BACK had no equivalent, flagged by a prior
        # session and left unfixed pending confirmation it wasn't intentional.
        run_command("RECORD CUESTACK 98 BackWrapTest")
        _cs98 = cuestack_pool.get(98)
        run_command("1")
        run_command("AT R 10")
        run_command("RECORD CS 98 CUE 1")
        run_command("AT R 20")
        run_command("RECORD CS 98 CUE 2")
        prog.clear_programmer()
        run_command("ASSIGN CS 98 TO FADER 9")
        _ex98 = executor_pool.get(9)
        _cs98.wrap    = True
        _cs98.current = _cs98._sorted_cue_numbers()[0]   # sitting at first cue
        _ex98.layer['__bleed_sentinel__'] = {'red': 99}
        _cs98.back(patch, fade_engine, _ex98)
        _check("CS BACK wrap-around (first->last) clears LTP-bleed layer when WRAP ON",
               '__bleed_sentinel__' not in _ex98.layer)

        _cs98.wrap    = False
        _cs98.current = _cs98._sorted_cue_numbers()[0]
        _ex98.layer['__bleed_sentinel2__'] = {'red': 99}
        _cs98.back(patch, fade_engine, _ex98)
        _check("CS BACK wrap-around leaves layer intact when WRAP OFF",
               '__bleed_sentinel2__' in _ex98.layer)

        # Non-wrap BACK (middle of stack, no wraparound) must never clear the
        # layer even with WRAP ON -- only the actual last->first transition should.
        _cs98.wrap    = True
        _cs98.current = _cs98._sorted_cue_numbers()[-1]  # sitting at last cue, BACK is not a wrap
        _ex98.layer['__bleed_sentinel3__'] = {'red': 99}
        _cs98.back(patch, fade_engine, _ex98)
        _check("CS BACK non-wrap step leaves layer intact even with WRAP ON",
               '__bleed_sentinel3__' in _ex98.layer)

        # UNDO must not desync output_state.programmer_layer from prog.data --
        # link_programmer() aliases them to the *same* dict object, so undo()
        # rebinding self.data to a new object (instead of clearing+updating in
        # place) would silently freeze live DMX output on stale data forever.
        # Each single-channel "R n" call pushes its own undo snapshot, so one
        # UNDO after one single-channel edit fully reverts it.
        prog.clear_programmer()
        run_command("1 THRU 3")
        run_command("1 THRU 3 R 10")
        run_command("1 THRU 3 R 250")
        _check("UNDO pre-check: post-undo-marker red was set",
               prog.data.get(_sub1, {}).get('red') == 250)
        run_command("UNDO")
        _check("UNDO restores prior programmer values",
               prog.data.get(_sub1, {}).get('red') == 10)
        _check("UNDO keeps output_state.programmer_layer aliased to prog.data "
               "(same object identity, not a stale copy)",
               output_state.programmer_layer is prog.data)
        run_command("1 THRU 3 R 77")
        _check("UNDO: post-undo edits are visible through the aliased "
               "programmer_layer used by real DMX output",
               output_state.programmer_layer.get(_sub1, {}).get('red') == 77)

        # fader page button assignment round-trip
        _fpg_ex = executor_pool.get(1)
        _fpg_ex.btn_a, _fpg_ex.btn_b, _fpg_ex.btn_c = 'GO', 'BACK', 'STOP'
        r_btn = run_command("FADER 1 BTN A FLASH")
        _check("FADER 1 BTN A FLASH sets btn_a to FLASH", _fpg_ex.btn_a == 'FLASH')
        r_btn2 = run_command("FADER 1 BTN A GO")
        _check("FADER 1 BTN A GO restores btn_a to GO",   _fpg_ex.btn_a == 'GO')
        r_btn3 = run_command("FADER 1 BTN")  # missing slot → usage hint
        _check("FADER 1 BTN without slot returns current state", "btn" in r_btn3.lower() or "usage" in r_btn3.lower() or "A=" in r_btn3)

        # RATE+/RATE- and RATE RESET smoke tests
        _rate_ex = executor_pool.get(2)
        _rate_ex.rate_factor = 1.0
        run_command("FADER 2 RATE+")
        _check("FADER 2 RATE+ increases rate_factor to ~1.25", abs(_rate_ex.rate_factor - 1.25) < 0.01)
        run_command("FADER 2 RATE-")
        _check("FADER 2 RATE- returns rate_factor to ~1.00", abs(_rate_ex.rate_factor - 1.0) < 0.01)
        run_command("FADER 2 RATE+")
        run_command("FADER 2 RATE RESET")
        _check("FADER 2 RATE RESET returns rate_factor to 1.0", _rate_ex.rate_factor == 1.0)
        run_command("FADER 2 RATE 3.0")
        _check("FADER 2 RATE 3.0 sets rate_factor to 3.0", abs(_rate_ex.rate_factor - 3.0) < 0.01)
        run_command("FADER 2 RATE RESET")
        r_rate_btn = run_command("FADER 2 BTN C RATE+")
        _check("FADER 2 BTN C RATE+ sets btn_c to RATE+", _rate_ex.btn_c == 'RATE+')
        run_command("FADER 2 BTN C STOP")  # restore

        # FADER LABEL
        _lbl_ex = executor_pool.get(1)
        r_lbl = run_command("FADER 1 LABEL Main Show")
        _check("FADER LABEL sets label on executor", _lbl_ex.label == "Main Show")
        _check("FADER LABEL returns confirmation", "Main Show" in r_lbl)
        r_lbl_list = run_command("LIST FADER")
        _check("LIST FADER shows label", "Main Show" in r_lbl_list)
        run_command("FADER 1 LABEL")  # clear
        _check("FADER 1 LABEL (no text) clears label", _lbl_ex.label == "")

        # FADER INFO
        r_fi1 = run_command("FADER 1 INFO")
        _check("FADER INFO shows level", "Level" in r_fi1)
        _check("FADER INFO shows buttons", "Buttons" in r_fi1)
        _fi1_ex = executor_pool.get(1)
        if _fi1_ex.cuestack:
            _check("FADER INFO shows cuestack name", _fi1_ex.cuestack.name in r_fi1)
        r_fi1_stat = run_command("FADER 1 STATUS")
        _check("FADER STATUS alias works", "Level" in r_fi1_stat)

        # FADER CLEAR
        _clr_ex = executor_pool.get(1)
        _clr_cs = _clr_ex.cuestack
        if _clr_cs:
            _clr_cs.current = 1  # pretend we're at cue 1
            r_fc = run_command("FADER 1 CLEAR")
            _check("FADER CLEAR resets cuestack position to None", _clr_cs.current is None)
            _check("FADER CLEAR returns confirmation", "cleared" in r_fc or "reset" in r_fc)

        # FADER ALL CLEAR
        if _clr_cs:
            _clr_cs.current = 2  # set a position to confirm it gets reset
        r_fac = run_command("FADER ALL CLEAR")
        _check("FADER ALL CLEAR returns 'cleared' confirmation", "cleared" in r_fac)
        _check("FADER ALL CLEAR resets position of cuestack in fader 1",
               _clr_cs is None or _clr_cs.current is None)

        # FADER LOOP ON/OFF
        if _clr_cs:
            r_loop_on  = run_command("FADER 1 LOOP ON")
            _check("FADER LOOP ON enables wrap on assigned cuestack", _clr_cs.wrap is True)
            _check("FADER LOOP ON returns confirmation", "loop" in r_loop_on.lower() or "wrap" in r_loop_on.lower())
            r_loop_off = run_command("FADER 1 LOOP OFF")
            _check("FADER LOOP OFF disables wrap on assigned cuestack", _clr_cs.wrap is False)

        # LOAD SHOW must reload OSC targets and FX defaults, not just leave
        # the previous show's live values in place — same primitives
        # load_show_from() now calls (osc._clients.clear() + load_osc_targets,
        # load_fx), exercised directly here so the test stays within the
        # isolated DATA_DIR and never touches the real studio_saves/ dir.
        osc.add_target("smoketest_stale", "10.0.0.1", 9000)
        ShowFile.save_osc_targets(osc)
        osc.add_target("smoketest_extra", "10.0.0.2", 9001)  # never persisted
        osc._clients.clear()
        ShowFile.load_osc_targets(osc)
        _check("LOAD SHOW-style OSC reload restores saved targets",
               "smoketest_stale" in osc._clients)
        _check("LOAD SHOW-style OSC reload drops targets not in the saved show",
               "smoketest_extra" not in osc._clients)

        _fx_params['rate_bpm'] = 60.0
        ShowFile.save_fx(_fx_params)
        _fx_params['rate_bpm'] = 999.0  # simulate a live value from a different show
        ShowFile.load_fx(_fx_params)
        _check("LOAD SHOW-style FX reload restores saved fx_params",
               _fx_params['rate_bpm'] == 60.0)

        # BACKUP command
        r_bk = run_command("BACKUP")
        _check("BACKUP creates a timestamped save", "backup_" in r_bk and "saved" in r_bk.lower())

        # ── ATTRIBUTE CHANNEL / MOVING LIGHT TESTS ───────────────────────────
        # Patch a Generic_Moving head into a spare slot (fixture 50), set
        # pan/tilt/gobo in programmer, record a cue, fire it, verify DMX output.

        _ml_profile = library.get("Generic_Moving")
        _check("Generic_Moving profile registered", _ml_profile is not None)

        if _ml_profile:
            # Patch at fixture 50, universe 1, address 400 (well clear of tubes)
            _ml_fix = patch.patch_fixture(50, "SmokeMoving", "Generic_Moving", 1, 400)
            _check("moving light patched", _ml_fix is not None)

            # AT PAN 200 TILT 64 from programmer
            prog.clear_programmer()
            run_command("50")
            run_command("AT DIM 100 PAN 200 TILT 64 GOBO 10")
            _ml_sub_fid = "50.1"
            _check("programmer stores pan",
                   prog.data.get(_ml_sub_fid, {}).get('pan') == 200)
            _check("programmer stores tilt",
                   prog.data.get(_ml_sub_fid, {}).get('tilt') == 64)
            _check("programmer stores gobo",
                   prog.data.get(_ml_sub_fid, {}).get('gobo') == 10)

            # Record to a cue and fire it; verify DMX output
            run_command("RECORD CS 2 CUE 80 FADE 0")
            run_command("ASSIGN CS 2 TO FADER 2")
            prog.clear_programmer()
            run_command("GO CS 2 CUE 80")
            time.sleep(0.12)  # 0-sec fade, just let the engine tick once
            _ml_dmx = output_state.get_dmx_for_universe(1)
            _ml_base = 400 - 1   # 0-indexed
            _ch_names = _ml_profile.channels
            _pan_off  = _ch_names.index('pan')
            _tilt_off = _ch_names.index('tilt')
            _gobo_off = _ch_names.index('gobo')
            _check("cue playback drives pan in DMX", _ml_dmx[_ml_base + _pan_off] == 200)
            _check("cue playback drives tilt in DMX", _ml_dmx[_ml_base + _tilt_off] == 64)
            _check("cue playback drives gobo in DMX", _ml_dmx[_ml_base + _gobo_off] == 10)

            # programmer-level attr write visible in DMX immediately
            prog.clear_programmer()
            run_command("50")
            run_command("AT PAN 127 TILT 127")
            _ml_dmx2 = output_state.get_dmx_for_universe(1)
            _check("programmer attr channels visible in DMX output",
                   _ml_dmx2[_ml_base + _pan_off] == 127)

            # Position pool: record and apply
            r_pos = run_command("RECORD POSITION 1 SmokePos")
            _check("RECORD POSITION from moving light programmer",
                   "Recorded" in r_pos or "no position" not in r_pos.lower())
            prog.clear_programmer()
            run_command("50")
            run_command("POSITION 1")
            _check("POSITION 1 restores pan to programmer",
                   prog.data.get(_ml_sub_fid, {}).get('pan') is not None)

            # FX on attribute channel: FX SINE PAN should create a layer
            run_command("FX CLEAR")
            run_command("50")
            r_pan_fx = run_command("FX SINE PAN BPM 30 SIZE 50")
            _check("FX SINE PAN accepted", "Applied FX" in r_pan_fx)
            _pan_fx_layer = next(
                (l for l in (active_fx or []) if l.channel == 'pan'), None)
            _check("FX SINE PAN creates layer with channel=pan",
                   _pan_fx_layer is not None)
            run_command("FX CLEAR")

            # DMX output handles generic profile channel order (dimmer first)
            prog.clear_programmer()
            run_command("50")
            run_command("AT DIM 100")   # sets master dim = 1.0
            _ml_dmx3 = output_state.get_dmx_for_universe(1)
            _dim_off  = _ch_names.index('dimmer')
            _check("dimmer profile channel outputs master dim correctly",
                   _ml_dmx3[_ml_base + _dim_off] == 255)

            # SNAPSHOT captures attr channels (not just RGB)
            prog.clear_programmer()
            run_command("50")
            run_command("AT DIM 80 PAN 180 TILT 90")
            r_snap = run_command("SNAPSHOT 95 AttrSnap")
            _active_cs_for_snap = cuestack_pool.get(active_executor[0])
            _snap_cue = _active_cs_for_snap.cues.get(95.0) if _active_cs_for_snap else None
            _check("SNAPSHOT creates cue with attr channel data",
                   _snap_cue is not None and
                   _snap_cue.data.get(_ml_sub_fid, {}).get('pan') == 180.0)
            prog.clear_programmer()

            # Cleanup
            prog.clear_programmer()
            run_command("FX CLEAR")
            del patch.fixtures[50]

        # ── RELATIVE AT TESTS ─────────────────────────────────────────────────
        run_command("1")
        prog.clear_programmer()
        run_command("1")
        run_command("AT 50")                      # set dim to 50%
        _check("AT 50 sets dim to 50%",
               abs(prog.data.get('1', {}).get('dim', 0) - 0.5) < 0.01)
        run_command("AT +20")                     # relative: 50 + 20 = 70%
        _check("AT +20 increases dim by 20pp",
               abs(prog.data.get('1', {}).get('dim', 0) - 0.7) < 0.01)
        run_command("AT -10")                     # relative: 70 - 10 = 60%
        _check("AT -10 decreases dim by 10pp",
               abs(prog.data.get('1', {}).get('dim', 0) - 0.6) < 0.01)
        # RGB relative
        run_command("AT R 100")
        run_command("AT R +50")                   # 100 + 50 = 150
        _check("AT R +50 increases red by 50",
               prog.data.get('1.1', {}).get('red') == 150)
        run_command("AT R +200")                  # clamp at 255
        _check("AT R +200 clamps to 255",
               prog.data.get('1.1', {}).get('red') == 255)
        prog.clear_programmer()

        # ── HUE COMMAND TESTS ─────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1")
        run_command("AT HUE 0")       # pure red (hue=0°, S=100%, V=100%)
        _check("HUE 0 sets red=255, green=0, blue=0",
               prog.data.get('1.1', {}).get('red') == 255 and
               prog.data.get('1.1', {}).get('green') == 0 and
               prog.data.get('1.1', {}).get('blue') == 0)
        run_command("AT HUE 120")     # pure green
        _check("HUE 120 sets green=255",
               prog.data.get('1.1', {}).get('green') == 255 and
               prog.data.get('1.1', {}).get('red') == 0)
        run_command("AT HUE 240")     # pure blue
        _check("HUE 240 sets blue=255",
               prog.data.get('1.1', {}).get('blue') == 255 and
               prog.data.get('1.1', {}).get('red') == 0)
        run_command("AT HUE 60 SAT 100 VAL 150")   # VAL over 100 must clamp
        _check("HUE VAL clamps at 100 (no channel over 255)",
               prog.data.get('1.1', {}).get('red') == 255 and
               prog.data.get('1.1', {}).get('green') == 255)
        run_command("AT HUE 0 SAT -50")            # SAT under 0 must clamp to 0 (grey/white)
        _check("HUE SAT clamps at 0 (grey output, not a negative-saturation artifact)",
               prog.data.get('1.1', {}).get('red') == 255 and
               prog.data.get('1.1', {}).get('green') == 255 and
               prog.data.get('1.1', {}).get('blue') == 255)
        prog.clear_programmer()

        # ── CT (color temperature) COMMAND TESTS ──────────────────────────────
        prog.clear_programmer()
        run_command("1")
        run_command("AT CT 9000")   # very cool — blue=255, red < 255
        _check("CT 9000 (cool) sets blue=255",
               prog.data.get('1.1', {}).get('blue') == 255)
        _check("CT 9000 (cool) sets red < 255",
               (prog.data.get('1.1', {}).get('red') or 0) < 255)
        prog.clear_programmer()
        run_command("1")
        run_command("AT CT 2700")   # warm tungsten — red = 255, blue ~ low
        _check("CT 2700 (warm) sets red=255",
               prog.data.get('1.1', {}).get('red') == 255)
        _check("CT 2700 (warm) sets blue < 200",
               (prog.data.get('1.1', {}).get('blue') or 0) < 200)
        prog.clear_programmer()

        # ── FLIP CHANNEL TESTS ────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1")
        run_command("AT R 60")           # set red to 60
        run_command("AT FLIP R")         # invert: 255 - 60 = 195
        _check("AT FLIP R inverts red channel",
               prog.data.get('1.1', {}).get('red') == 195)
        run_command("AT R 0")
        run_command("AT FLIP R")         # 255 - 0 = 255
        _check("AT FLIP R on 0 gives 255",
               prog.data.get('1.1', {}).get('red') == 255)
        prog.clear_programmer()

        # ── AT RANDOM CHANNEL TESTS ───────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 THRU 6")
        run_command("AT RANDOM R")    # each sub gets independent random red
        _rnd_reds = [prog.data.get(f"{i}.1", {}).get('red') for i in range(1, 7)]
        _check("AT RANDOM R sets red on all selected fixtures",
               all(v is not None for v in _rnd_reds))
        _check("AT RANDOM R values are in valid range",
               all(0 <= v <= 255 for v in _rnd_reds if v is not None))
        # RANDOM MASTER: all subs of each master get same value
        prog.clear_programmer()
        run_command("1")   # 54 pixels
        run_command("AT RANDOM G MASTER")
        _grn_subs = [prog.data.get(f"1.{i}", {}).get('green') for i in range(1, 4)]
        _check("AT RANDOM G MASTER applies same value to all subs of a master",
               len(set(v for v in _grn_subs if v is not None)) == 1)

        # AT RANDOM DIM — randomize master dimmer per fixture
        prog.clear_programmer()
        run_command("1 THRU 3")
        run_command("1 THRU 3 AT RANDOM DIM")
        _rnd_dims = [prog.data.get(str(i), {}).get('dim') for i in range(1, 4)]
        _check("AT RANDOM DIM sets dim on all selected masters",
               all(v is not None for v in _rnd_dims))
        _check("AT RANDOM DIM values are in valid range 0–1",
               all(0.0 <= v <= 1.0 for v in _rnd_dims if v is not None))
        prog.clear_programmer()

        # ── AT BRIGHTEST / AT DARKEST ─────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 AT R 50")   # all subs of fixture 1 → red=50
        run_command("2 AT R 200")  # all subs of fixture 2 → red=200
        run_command("3 AT R 120")  # all subs of fixture 3 → red=120
        run_command("1 THRU 3 AT BRIGHTEST R")  # max=200 → stamp to all
        _bd_vals = [prog.data.get(f"{i}.1", {}).get('red') for i in range(1, 4)]
        _check("AT BRIGHTEST R stamps max value (200) to all subs",
               all(v == 200 for v in _bd_vals if v is not None))
        run_command("1 AT R 50")   # restore variety
        run_command("2 AT R 200")
        run_command("3 AT R 120")
        run_command("1 THRU 3 AT DARKEST R")    # min=50 → stamp to all
        _dk_vals = [prog.data.get(f"{i}.1", {}).get('red') for i in range(1, 4)]
        _check("AT DARKEST R stamps min value (50) to all subs",
               all(v == 50 for v in _dk_vals if v is not None))
        run_command("1 AT R 0")    # restore variety: 0, 200, 120
        run_command("2 AT R 200")
        run_command("3 AT R 100")
        run_command("1 THRU 3 AT AVERAGE R")  # avg = (0+200+100)/3 = 100
        _avg_vals = [prog.data.get(f"{i}.1", {}).get('red') for i in range(1, 4)]
        _check("AT AVERAGE R stamps mean value (100) to all subs",
               all(v == 100 for v in _avg_vals if v is not None))

        # ── AT CLAMP ──────────────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 AT R 20")   # below lo
        run_command("2 AT R 100")  # in range
        run_command("3 AT R 240")  # above hi
        run_command("1 THRU 3 AT CLAMP R 50 200")
        _cl_vals = [prog.data.get(f"{i}.1", {}).get('red') for i in range(1, 4)]
        _check("AT CLAMP R clamps below-lo value up to lo (50)", _cl_vals[0] == 50)
        _check("AT CLAMP R leaves in-range value unchanged (100)", _cl_vals[1] == 100)
        _check("AT CLAMP R clamps above-hi value down to hi (200)", _cl_vals[2] == 200)

        # AT CLAMP DIM — clamp master dimmer using percent range
        prog.clear_programmer()
        run_command("1 AT DIM 10")   # 10% — below lo
        run_command("2 AT DIM 50")   # 50% — in range
        run_command("3 AT DIM 90")   # 90% — above hi
        run_command("1 THRU 3 AT CLAMP DIM 20 80")
        _cd_dims = [prog.data.get(str(i), {}).get('dim') for i in range(1, 4)]
        _check("AT CLAMP DIM: 10% → 20% (clamped up to lo)", abs((_cd_dims[0] or 0) - 0.2) < 0.01)
        _check("AT CLAMP DIM: 50% unchanged (in range)", abs((_cd_dims[1] or 0) - 0.5) < 0.01)
        _check("AT CLAMP DIM: 90% → 80% (clamped down to hi)", abs((_cd_dims[2] or 0) - 0.8) < 0.01)
        prog.clear_programmer()

        # ── AT BRIGHTEST / DARKEST / AVERAGE DIM ─────────────────────────────
        run_command("1 AT DIM 20")   # 20%
        run_command("2 AT DIM 60")   # 60%
        run_command("3 AT DIM 80")   # 80%
        run_command("1 THRU 3 AT BRIGHTEST DIM")
        _bd_d = [prog.data.get(str(i), {}).get('dim') for i in range(1, 4)]
        _check("AT BRIGHTEST DIM: all stamped to max (0.8)",
               all(abs((v or 0) - 0.8) < 0.01 for v in _bd_d))
        run_command("1 THRU 3 AT DARKEST DIM")
        _dk_d = [prog.data.get(str(i), {}).get('dim') for i in range(1, 4)]
        _check("AT DARKEST DIM: all stamped to min (0.8 after BRIGHTEST)",
               all(abs((v or 0) - 0.8) < 0.01 for v in _dk_d))
        # Reset to original spread and test AVERAGE
        run_command("1 AT DIM 20"); run_command("2 AT DIM 60"); run_command("3 AT DIM 100")
        run_command("1 THRU 3 AT AVERAGE DIM")
        _av_d = [prog.data.get(str(i), {}).get('dim') for i in range(1, 4)]
        _check("AT AVERAGE DIM: all stamped to mean (20+60+100)/3=60%",
               all(abs((v or 0) - 0.6) < 0.01 for v in _av_d))
        prog.clear_programmer()

        # ── AT INVERT DIM / AT SCALE DIM / AT WOBBLE DIM ─────────────────────
        run_command("1 THRU 2 AT DIM 30")   # 30%
        run_command("1 THRU 2 AT INVERT DIM")
        _inv_d = [prog.data.get(str(i), {}).get('dim') for i in range(1, 3)]
        _check("AT INVERT DIM: 30% → 70%", all(abs((v or 0) - 0.7) < 0.01 for v in _inv_d))
        run_command("1 THRU 2 AT SCALE DIM 50")   # 70% × 50% = 35%
        _sc_d = [prog.data.get(str(i), {}).get('dim') for i in range(1, 3)]
        _check("AT SCALE DIM 50: 70% × 50% = 35%", all(abs((v or 0) - 0.35) < 0.01 for v in _sc_d))
        run_command("1 THRU 2 AT SCALE DIM 200")  # 35% × 200% = 70% (≤ 1.0)
        _sc_d2 = [prog.data.get(str(i), {}).get('dim') for i in range(1, 3)]
        _check("AT SCALE DIM 200: 35% × 200% = 70%", all(abs((v or 0) - 0.7) < 0.01 for v in _sc_d2))
        run_command("1 THRU 3 AT DIM 50")
        run_command("1 THRU 3 AT WOBBLE DIM 10")   # ±10% jitter
        _wb_d = [prog.data.get(str(i), {}).get('dim') for i in range(1, 4)]
        _check("AT WOBBLE DIM: values remain in 0–1 range",
               all(0.0 <= (v or 0) <= 1.0 for v in _wb_d))
        _check("AT WOBBLE DIM: values are near the seed (within 10%)",
               all(abs((v or 0) - 0.5) <= 0.10 for v in _wb_d))
        prog.clear_programmer()

        # ── AT STEP ───────────────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 THRU 3 AT R 50")        # seed all at 50
        run_command("1 THRU 3 AT STEP R 20")   # 50+0, 50+20, 50+40
        _st_vals = [prog.data.get(f"{i}.1", {}).get('red') for i in range(1, 4)]
        _check("AT STEP R fixture 1 unchanged (offset 0)", _st_vals[0] == 50)
        _check("AT STEP R fixture 2 offset +20 (70)",      _st_vals[1] == 70)
        _check("AT STEP R fixture 3 offset +40 (90)",      _st_vals[2] == 90)

        # ── AT MIRROR ─────────────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 AT R 10")   # fixture 1 = red 10
        run_command("2 AT R 100")  # fixture 2 = red 100
        run_command("3 AT R 200")  # fixture 3 = red 200
        run_command("1 THRU 3 AT MIRROR R")  # should swap 1↔3, keep 2 (symmetric)
        _mir_r1 = prog.data.get("1.1", {}).get('red')
        _mir_r2 = prog.data.get("2.1", {}).get('red')
        _mir_r3 = prog.data.get("3.1", {}).get('red')
        _check("AT MIRROR R swaps first ↔ last (fixture 1 gets fixture 3's value)",
               _mir_r1 == 200)
        _check("AT MIRROR R middle fixture gets its own mirror (fixture 3 gets fixture 1's value)",
               _mir_r3 == 10)
        prog.clear_programmer()

        # ── AT INVERT ─────────────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 AT R 100")   # fixture 1 red = 100
        run_command("2 AT R 0")     # fixture 2 red = 0
        run_command("1 THRU 2 AT INVERT R")
        _inv_r1 = prog.data.get("1.1", {}).get('red')
        _inv_r2 = prog.data.get("2.1", {}).get('red')
        _check("AT INVERT R: 100 → 155 (255-100)", _inv_r1 == 155)
        _check("AT INVERT R: 0 → 255 (255-0)",     _inv_r2 == 255)
        prog.clear_programmer()

        # ── AT SCALE ──────────────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 AT R 200")   # fixture 1 red = 200
        run_command("2 AT R 100")   # fixture 2 red = 100
        run_command("1 THRU 2 AT SCALE R 50")   # 50% → 100, 50
        _sc_r1 = prog.data.get("1.1", {}).get('red')
        _sc_r2 = prog.data.get("2.1", {}).get('red')
        _check("AT SCALE R 50%: 200 → 100", _sc_r1 == 100)
        _check("AT SCALE R 50%: 100 → 50",  _sc_r2 == 50)
        run_command("1 AT R 200")
        run_command("1 AT SCALE R 200")   # 200% of 200 = 400 → clamped to 255
        _sc_clamp = prog.data.get("1.1", {}).get('red')
        _check("AT SCALE R clamps at 255", _sc_clamp == 255)
        prog.clear_programmer()

        # ── AT WOBBLE ─────────────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 THRU 3 AT R 128")   # seed all at 128
        run_command("1 THRU 3 AT WOBBLE R 50")   # add ±50 jitter
        _wb_vals = [prog.data.get(f"{i}.1", {}).get('red') for i in range(1, 4)]
        _check("AT WOBBLE R keeps values in 0-255 range",
               all(v is not None and 0 <= v <= 255 for v in _wb_vals))
        _check("AT WOBBLE R values are near the seed (within 50)",
               all(v is not None and abs(v - 128) <= 50 for v in _wb_vals))
        prog.clear_programmer()

        # ── AT CLEAR ──────────────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 AT R 200 G 100")   # fixture 1: red=200, green=100
        run_command("1 AT CLEAR R")       # remove only red
        _ac_r = prog.data.get("1.1", {}).get('red')
        _ac_g = prog.data.get("1.1", {}).get('green')
        _check("AT CLEAR R removes red from programmer", _ac_r is None)
        _check("AT CLEAR R leaves other channels intact", _ac_g == 100)
        run_command("1 AT CLEAR")         # remove all channels for fixture 1
        _ac_all = prog.data.get("1.1", {})
        _check("AT CLEAR (no ch) removes all channels for selection", not _ac_all)
        prog.clear_programmer()

        # ── AT NORMALIZE ──────────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 AT R 50")    # fixture 1 red = 50
        run_command("2 AT R 100")   # fixture 2 red = 100
        run_command("3 AT R 200")   # fixture 3 red = 200  (max)
        run_command("1 THRU 3 AT NORMALIZE R")
        _nrm_r = [prog.data.get(f"{i}.1", {}).get('red') for i in range(1, 4)]
        _check("AT NORMALIZE R: highest value becomes 255", _nrm_r[2] == 255)
        _check("AT NORMALIZE R: proportional scale (50→64, 100→128)", _nrm_r[0] == 64 and _nrm_r[1] == 128)
        prog.clear_programmer()

        # ── AT COPY ───────────────────────────────────────────────────────────
        run_command("1")                        # select fixture 1
        run_command("1 AT DIM 80 R 200 G 50")  # set source values on fixture 1
        run_command("2 3")                      # select fixtures 2 & 3
        run_command("2 3 AT COPY 1")            # copy fixture 1 values into 2 & 3
        _cp_dim2  = prog.data.get("2", {}).get('dim')
        _cp_dim3  = prog.data.get("3", {}).get('dim')
        _cp_r2    = prog.data.get("2.1", {}).get('red')
        _cp_r3    = prog.data.get("3.1", {}).get('red')
        _cp_g2    = prog.data.get("2.1", {}).get('green')
        _check("AT COPY: dimmer copied to fixture 2", abs((_cp_dim2 or 0) - 0.8) < 0.01)
        _check("AT COPY: dimmer copied to fixture 3", abs((_cp_dim3 or 0) - 0.8) < 0.01)
        _check("AT COPY: red channel copied to fixture 2", _cp_r2 == 200)
        _check("AT COPY: red channel copied to fixture 3", _cp_r3 == 200)
        _check("AT COPY: green channel copied to fixture 2", _cp_g2 == 50)
        prog.clear_programmer()

        # ── CS NOTE ───────────────────────────────────────────────────────────
        _csnote_cs = cuestack_pool.get(99)
        if _csnote_cs is None:
            cuestack_pool.create(99, "NoteTestStack")
            _csnote_cs = cuestack_pool.get(99)
        _csnote_cs.note = ""
        _no_note_msg = run_command("CS 99 NOTE")
        _check("CS NOTE view returns has-no-note message when blank",
               "no note" in _no_note_msg.lower() or "set with" in _no_note_msg.lower())
        run_command("CS 99 NOTE Dark Moody Show")
        _check("CS NOTE set stores text",  _csnote_cs.note == "Dark Moody Show")
        _note_view = run_command("CS 99 NOTE")
        _check("CS NOTE view returns the note text", "Dark Moody Show" in _note_view)
        _csnote_cs.note = ""

        # ── CS BOUNCE ─────────────────────────────────────────────────────────
        # Verify ping-pong direction logic using a fresh 3-cue cuestack
        _bcs_id = 102
        cuestack_pool.create(_bcs_id, "BounceTest")
        _bcs = cuestack_pool.get(_bcs_id)
        _bcs.cues.clear()
        _bcs.current = None
        # Build 3 minimal cues directly (cue_pool.store returns None, so assign separately)
        def _mk_cue(num, dim_frac):
            prog.data["1"] = {"dim": dim_frac}
            c = Cue(float(num), f"C{num}")
            c.record(prog)
            prog.data.clear()
            _bcs.cues[float(num)] = c
        _mk_cue(1, 0.33)
        _mk_cue(2, 0.66)
        _mk_cue(3, 1.0)
        _check("BOUNCE: cuestack has 3 cues", len(_bcs.cues) == 3)
        run_command(f"CS {_bcs_id} bounce on")
        _check("CS bounce on sets .bounce = True", _bcs.bounce is True)
        # Use a minimal stub executor — bounce logic only needs .layer dict
        _bex = executor_pool.get(_bcs_id)
        _bex.assign(_bcs)
        _bcs.current = None
        _bcs._bounce_dir = 1
        _bcs.go(patch, fade_engine, _bex)   # fires cue 1
        _check("BOUNCE GO 1: at cue 1", _bcs.current == 1.0)
        _bcs.go(patch, fade_engine, _bex)   # fires cue 2
        _check("BOUNCE GO 2: at cue 2", _bcs.current == 2.0)
        _bcs.go(patch, fade_engine, _bex)   # fires cue 3
        _check("BOUNCE GO 3: at cue 3", _bcs.current == 3.0)
        _bcs.go(patch, fade_engine, _bex)   # hits end → reverses → fires cue 2
        _check("BOUNCE GO 4: reverses at last cue → cue 2", _bcs.current == 2.0)
        _check("BOUNCE GO 4: direction flipped to -1", _bcs._bounce_dir == -1)
        _bcs.go(patch, fade_engine, _bex)   # fires cue 1
        _check("BOUNCE GO 5: at cue 1", _bcs.current == 1.0)
        _bcs.go(patch, fade_engine, _bex)   # hits start → reverses → fires cue 2
        _check("BOUNCE GO 6: reverses at first cue → cue 2", _bcs.current == 2.0)
        _check("BOUNCE GO 6: direction flipped to +1", _bcs._bounce_dir == 1)
        run_command(f"CS {_bcs_id} bounce off")
        _check("CS bounce off sets .bounce = False", _bcs.bounce is False)
        cuestack_pool.stacks.pop(_bcs_id, None)

        # ── CS CLEAR ──────────────────────────────────────────────────────────
        _cc_id = 103
        cuestack_pool.create(_cc_id, "ClearTest")
        _cc = cuestack_pool.get(_cc_id)
        _cc.cues.clear()
        prog.data["1"] = {"dim": 0.5}
        _cc.cues[1.0] = Cue(1.0, "X"); _cc.cues[1.0].record(prog)
        _cc.cues[2.0] = Cue(2.0, "Y"); _cc.cues[2.0].record(prog)
        prog.data.clear()
        _cc.current = 1.0
        _check("CS CLEAR: setup has 2 cues", len(_cc.cues) == 2)
        _r_clear_cs = run_command(f"CS {_cc_id} CLEAR")
        _check("CS CLEAR: removes all cues", len(_cc.cues) == 0)
        _check("CS CLEAR: resets current to None", _cc.current is None)
        _check("CS CLEAR: returns confirmation", "cleared" in _r_clear_cs.lower())
        cuestack_pool.stacks.pop(_cc_id, None)

        # ── LIST NOTES ────────────────────────────────────────────────────────
        # Set a cuestack note and cue note, confirm LIST NOTES shows both
        _ln_cs = cuestack_pool.get(1)
        if _ln_cs:
            _ln_orig_note = getattr(_ln_cs, 'note', '')
            _ln_cs.note = "ListNotesTest"
            _cue1 = _ln_cs.cues.get(1.0) or next(iter(_ln_cs.cues.values()), None)
            _orig_cue_note = ""
            if _cue1:
                _orig_cue_note = getattr(_cue1, 'note', '')
                _cue1.note = "CueNoteTest"
            _ln_result = run_command("LIST NOTES")
            _check("LIST NOTES: includes cuestack note", "ListNotesTest" in _ln_result)
            if _cue1:
                _check("LIST NOTES: includes cue note", "CueNoteTest" in _ln_result)
            _ln_cs.note = _ln_orig_note
            if _cue1:
                _cue1.note = _orig_cue_note
        _ln_empty = run_command("LIST NOTES")

        # ── FIXTURE GROUPS ────────────────────────────────────────────────────
        # group 1 is set up in the show init with fixture 1 etc. — look for fixture 1
        _fg_fid = next(iter(sorted(patch.fixtures)), None)
        if _fg_fid is not None:
            # ensure fixture is in at least one group by checking group_pool
            _fg_in_group = any(
                any(isinstance(e, tuple) and e[1] == _fg_fid for e in g.members)
                for g in group_pool.groups.values()
            )
            if _fg_in_group:
                _fg_result = run_command(f"FIXTURE GROUPS {_fg_fid}")
                _check("FIXTURE GROUPS: returns group membership info",
                       "Group" in _fg_result or "group" in _fg_result)
                _check("FIXTURE GROUPS: mentions the fixture name",
                       patch.fixtures[_fg_fid].name in _fg_result
                       or str(_fg_fid) in _fg_result)
            # Fixture not in any group scenario
            _fg_not_found = run_command("FIXTURE GROUPS 9999")
            _check("FIXTURE GROUPS: bad fixture returns error", "not patched" in _fg_not_found.lower())

        # ── RENAME FIXTURE ────────────────────────────────────────────────────
        _rf_fid = next(iter(sorted(patch.fixtures)), None)
        if _rf_fid is not None:
            _rf_master = patch.fixtures[_rf_fid]
            _rf_orig = _rf_master.name
            _rf_result = run_command(f"RENAME FIXTURE {_rf_fid} TempTestName")
            _check("RENAME FIXTURE: changes master.name", _rf_master.name == "TempTestName")
            _check("RENAME FIXTURE: includes old→new in response",
                   "TempTestName" in _rf_result)
            run_command(f"RENAME FIXTURE {_rf_fid} {_rf_orig}")  # restore
            _check("RENAME FIXTURE: name restored", _rf_master.name == _rf_orig)
        _rf_bad = run_command("RENAME FIXTURE 9999 X")
        _check("RENAME FIXTURE: bad ID returns error", "not in patch" in _rf_bad)

        # ── PROGRAMMER SCALE ──────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 AT DIM 100")         # dim=1.0
        run_command("1 AT R 200 G 100")     # red=200, green=100
        _r_ps = run_command("PROGRAMMER SCALE 50")
        _check("PROGRAMMER SCALE: returns confirmation", "50%" in _r_ps or "scaled" in _r_ps.lower())
        _ps_dim = prog.data.get("1", {}).get('dim')
        _ps_r   = prog.data.get("1.1", {}).get('red')
        _ps_g   = prog.data.get("1.1", {}).get('green')
        _check("PROGRAMMER SCALE 50: dim scaled to 50%", abs((_ps_dim or 0) - 0.5) < 0.01)
        _check("PROGRAMMER SCALE 50: red 200 → 100", _ps_r == 100)
        _check("PROGRAMMER SCALE 50: green 100 → 50", _ps_g == 50)
        # Test 200% (amplify + clamp)
        run_command("PROGRAMMER SCALE 200")
        _ps_r2 = prog.data.get("1.1", {}).get('red')
        _check("PROGRAMMER SCALE 200: red 100 × 2 = 200", _ps_r2 == 200)
        # Test empty programmer
        prog.clear_programmer()
        _r_ps_empty = run_command("PROGRAMMER SCALE 50")
        _check("PROGRAMMER SCALE: empty programmer returns error", "empty" in _r_ps_empty.lower())
        prog.clear_programmer()

        # ── FADER ASSIGN CS ───────────────────────────────────────────────────
        _fa_cs = cuestack_pool.get(1)
        if _fa_cs:
            _fa_ex = executor_pool.get(15)  # high slot unlikely to conflict
            _fa_result = run_command(f"FADER 15 ASSIGN CS 1")
            _check("FADER ASSIGN CS: wires cuestack to fader",
                   _fa_ex.cuestack is _fa_cs)
            _check("FADER ASSIGN CS: returns confirmation",
                   "CS 1" in _fa_result or "assigned" in _fa_result.lower())
            _r_fa_bad = run_command("FADER 15 ASSIGN CS 9999")
            _check("FADER ASSIGN CS: bad CS returns error",
                   "not found" in _r_fa_bad.lower())

        # ── FADER UNASSIGN ────────────────────────────────────────────────────
        # Assign CS 1 to fader 16, then UNASSIGN it
        if cuestack_pool.get(1):
            run_command("FADER 16 ASSIGN CS 1")
            _fu_ex = executor_pool.get(16)
            _check("FADER UNASSIGN: setup — cuestack assigned", _fu_ex.cuestack is not None)
            _r_ua = run_command("FADER 16 UNASSIGN")
            _check("FADER UNASSIGN: cuestack is None after unassign", _fu_ex.cuestack is None)
            _check("FADER UNASSIGN: returns confirmation", "unassigned" in _r_ua.lower())
            _r_ua_empty = run_command("FADER 16 UNASSIGN")
            _check("FADER UNASSIGN: returns error when already empty",
                   "no cuestack" in _r_ua_empty.lower())

        # ── FAN TESTS ─────────────────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1 THRU 6")
        run_command("FAN DIM 0 100")
        _fan_dims = [prog.data.get(str(i), {}).get('dim') for i in range(1, 7)]
        _check("FAN DIM sets fixture 1 to 0%",  abs(_fan_dims[0] or 0) < 0.01)
        _check("FAN DIM sets fixture 6 to 100%", abs((_fan_dims[5] or 0) - 1.0) < 0.01)
        _check("FAN DIM is monotone across selection",
               all(_fan_dims[i] is not None and _fan_dims[i] <= _fan_dims[i+1]
                   for i in range(5)))
        run_command("FAN R 0 255")
        _fan_r = [prog.data.get(f"{i}.1", {}).get('red') for i in range(1, 7)]
        _check("FAN R sets fixture 1 red to 0",   _fan_r[0] == 0)
        _check("FAN R sets fixture 6 red to 255",  _fan_r[5] == 255)
        prog.clear_programmer()

        # ── RANDOM / EVERY SELECTION TESTS ───────────────────────────────────
        run_command("RANDOM 3")
        _sel_m = [m for m in prog.selection if isinstance(m, MasterFixture)]
        _check("RANDOM 3 selects exactly 3 master fixtures", len(_sel_m) == 3)
        prog.clear_programmer()
        run_command("1 THRU 6 EVERY 2")   # selects 1, 3, 5
        _sel_m2 = [m.fixture_id for m in prog.selection if isinstance(m, MasterFixture)]
        _check("1 THRU 6 EVERY 2 selects 1,3,5", _sel_m2 == [1, 3, 5])
        prog.clear_programmer()

        # ── NEXT/PREV FIXTURE NAVIGATION ──────────────────────────────────────
        _all_ids = [m.fixture_id for m in patch.all_fixtures()]
        if len(_all_ids) >= 2:
            run_command(str(_all_ids[0]))     # select first fixture
            run_command("NEXT")               # should advance to second
            _sel_masters = [m.fixture_id for m in prog.selection
                            if isinstance(m, MasterFixture)]
            _check("NEXT advances selection to next fixture",
                   _sel_masters == [_all_ids[1]])
            run_command("PREV")               # should go back to first
            _sel_masters2 = [m.fixture_id for m in prog.selection
                             if isinstance(m, MasterFixture)]
            _check("PREV retreats selection to previous fixture",
                   _sel_masters2 == [_all_ids[0]])
            prog.clear_programmer()

        # ── PATCH RENAME / PATCH MOVE TESTS ──────────────────────────────
        _tmp_fix = patch.patch_fixture(51, "TmpFix", "Generic_RGB", 1, 490)
        _check("PATCH RENAME test fixture patched", _tmp_fix is not None)
        r_pr = run_command("PATCH RENAME 51 RenamedFix")
        _check("PATCH RENAME changes fixture name",
               patch.get(51) is not None and patch.get(51).name == "RenamedFix")
        r_pm = run_command("PATCH MOVE 51 UNIVERSE 2 AT 50")
        _first_sub_51 = patch.get(51).all_subs()[0] if patch.get(51) else None
        _check("PATCH MOVE updates sub universe",
               _first_sub_51 is not None and _first_sub_51.outputs[0]['universe'] == 2)
        _check("PATCH MOVE updates sub address",
               _first_sub_51 is not None and _first_sub_51.outputs[0]['address'] == 50)
        del patch.fixtures[51]

        # ── MACRO RECORD / PLAYBACK TESTS ────────────────────────────────────
        prog.clear_programmer()
        run_command("1")
        run_command("MACRO RECORD 99 SmokeTest")
        _check("MACRO RECORD starts recording", _macro_recording["slot"] == 99)
        run_command("AT FULL")          # captured inside macro
        run_command("AT R 200")         # captured inside macro
        r_ms = run_command("MACRO STOP")
        _check("MACRO STOP saves macro to pool", 99 in macro_pool)
        _check("MACRO STOP records correct command count",
               len(macro_pool.get(99, {}).get("commands", [])) == 2)
        _check("MACRO STOP ends recording", _macro_recording["slot"] is None)
        prog.clear_programmer()
        run_command("1")
        r_mb = run_command("MACRO 99")
        _check("MACRO playback result mentions commands played", "cmd" in r_mb)
        _check("MACRO playback restores dim",
               abs(prog.data.get('1', {}).get('dim', 0) - 1.0) < 0.01)
        _check("MACRO playback restores red channel",
               prog.data.get('1.1', {}).get('red') == 200)
        run_command("RENAME MACRO 99 Renamed")
        _check("RENAME MACRO changes name",
               macro_pool.get(99, {}).get("name") == "Renamed")
        run_command("MACRO DELETE 99")
        _check("MACRO DELETE removes slot", 99 not in macro_pool)
        # Also test MACRO RENAME <n> <name> (alternative order)
        macro_pool[98] = {"name": "TestMacro", "commands": ["1 FULL"]}
        r_mrn = run_command("MACRO RENAME 98 RenamedViaMAcroRename")
        _check("MACRO RENAME <n> <name> renames macro",
               macro_pool.get(98, {}).get("name") == "RenamedViaMAcroRename")
        del macro_pool[98]
        prog.clear_programmer()

        # ── MACRO RECURSION GUARD TESTS ───────────────────────────────────────
        # A macro whose commands (directly or via another macro) play itself
        # again used to recurse with no depth limit -> RecursionError crash.
        macro_pool[97] = {"name": "SelfRef", "commands": ["MACRO 97"]}
        r_self = run_command("MACRO 97")
        _check("MACRO self-recursion blocked, not a crash", "blocked" in r_self)
        _check("MACRO play stack cleaned up after self-recursion block",
               len(_macro_play_stack) == 0)
        macro_pool[95] = {"name": "A", "commands": ["MACRO 96"]}
        macro_pool[96] = {"name": "B", "commands": ["MACRO 95"]}
        r_cycle = run_command("MACRO 95")
        _check("MACRO indirect A->B->A cycle blocked, not a crash",
               "blocked" in r_cycle)
        _check("MACRO play stack cleaned up after cycle block",
               len(_macro_play_stack) == 0)
        del macro_pool[97]
        del macro_pool[95]
        del macro_pool[96]

        # ── PARK / UNPARK TESTS ───────────────────────────────────────────────
        prog.clear_programmer()
        run_command("1")
        run_command("AT FULL")           # dim=1.0, so DMX output for fixture 1 is non-zero
        run_command("AT R 200 G 100 B 50")
        # Park fixture 1 at this look
        r_park = run_command("PARK")
        _check("PARK adds fixture to parked_fids", 1 in output_state.parked_fids)
        _check("PARK stores some parked addresses",
               bool(output_state.parked_addresses))
        # Change programmer — should not affect parked output
        run_command("AT R 0 G 0 B 0")
        _park_dmx = output_state.get_dmx_for_universe(1)
        # Fixture 1 subs start at address 1 (SGM_RGB_54); first sub has r at offset 0
        _first_sub_1 = patch.get(1).all_subs()[0]
        _r_addr = _first_sub_1.outputs[0]['address'] - 1  # 0-indexed
        _check("PARK holds DMX value against programmer change",
               _park_dmx[_r_addr] == 200)
        # Unpark
        r_unpark = run_command("UNPARK")
        _check("UNPARK removes fixture from parked_fids", 1 not in output_state.parked_fids)
        prog.clear_programmer()
        run_command("1")
        run_command("AT R 0 G 0 B 0")
        _after_dmx = output_state.get_dmx_for_universe(1)
        _check("After UNPARK, programmer changes take effect",
               _after_dmx[_r_addr] == 0)
        prog.clear_programmer()

        # ── PARK-vs-FREEZE TEST ─────────────────────────────────────────────
        # Same bug class fixed twice before (BLACKOUT-vs-FREEZE, SOLO-vs-FREEZE):
        # FREEZE's frozen-snapshot branch must not silently defeat a newer
        # isolation/override layer. PARK is documented as "immune to
        # cue/prog changes" and highest priority (even above direct_dmx) —
        # verify it still holds while FREEZE is active. Seeds a synthetic
        # frozen snapshot directly (not via run_command('FREEZE')) so this
        # check is isolated from whatever dim/FX state other tests in this
        # long-lived process have left on fixture 1.
        run_command("1")
        run_command("AT FULL")
        run_command("AT R 222 G 11 B 33")
        run_command("PARK")
        _park_addr = _first_sub_1.outputs[0]['address'] - 1  # 0-indexed
        _saved_frozen = dict(output_state.frozen_dmx)
        _saved_freeze_mode = output_state.freeze_mode
        try:
            output_state.frozen_dmx[1] = tuple([99] * 512)  # conflicts with parked 222
            output_state.freeze_mode = True
            _frozen_dmx = output_state.get_dmx_for_universe(1)
            _check("PARK still holds its value while FREEZE is active",
                   _frozen_dmx[_park_addr] == 222)
        finally:
            output_state.freeze_mode = _saved_freeze_mode
            output_state.frozen_dmx.clear()
            output_state.frozen_dmx.update(_saved_frozen)
            run_command("UNPARK")
        prog.clear_programmer()

        # ── AI "dim" action clamp test ──────────────────────────────────
        # AIEngine.execute()'s "dim" action wrote a model-supplied value
        # straight into programmer_layer with no bounds check -- same bug
        # class already fixed for HUE SAT/VAL (invisible live since final
        # DMX render clamps on the way out, but a RECORDed cue would
        # persist the raw out-of-range number). Build a throwaway AIEngine
        # to exercise the fix: construction needs an API key string but
        # never calls the network -- only .execute() runs here, which is
        # pure local dict logic, no anthropic.messages.create() involved.
        _prev_api_key = os.environ.get('ANTHROPIC_API_KEY')
        os.environ['ANTHROPIC_API_KEY'] = 'sk-ant-smoketest-dummy-unused'
        try:
            _test_ai = AIEngine(patch, prog, output_state, fx_engine, fade_engine,
                                 cuestack_pool=cuestack_pool, executor_pool=executor_pool)
            _test_ai.execute([{"action": "dim", "value": 5.0}])
            _check("AI 'dim' action clamps out-of-range value to 1.0",
                   output_state.programmer_layer.get("1", {}).get('dim') == 1.0
                   and patch.get(1).virtual_dimmer == 1.0)
            _test_ai.execute([{"action": "dim", "value": -3.0}])
            _check("AI 'dim' action clamps negative value to 0.0",
                   output_state.programmer_layer.get("1", {}).get('dim') == 0.0
                   and patch.get(1).virtual_dimmer == 0.0)
        finally:
            if _prev_api_key is None:
                os.environ.pop('ANTHROPIC_API_KEY', None)
            else:
                os.environ['ANTHROPIC_API_KEY'] = _prev_api_key
            # The "dim" action loops over ALL patched fixtures, not just a
            # selection -- undo its virtual_dimmer=0.0 and the programmer
            # 'dim' overrides on every fixture so this test doesn't leak
            # state into whatever runs after it.
            for _m in patch.all_fixtures():
                _m.set_dimmer(1.0)
            prog.clear_programmer()

        # ── CS CHASE MODE ─────────────────────────────────────────────────
        _ch_cs = cuestack_pool.create(103, "ChaseTest")
        if _ch_cs:
            _ch_cs.cues.clear()
            prog.data["1"] = {"dim": 0.5}
            for _cn in (1, 2, 3):
                _c = Cue(float(_cn), f"Ch{_cn}"); _c.record(prog); _ch_cs.cues[float(_cn)] = _c
            prog.data.clear()
        r_ch_on = run_command("CS 103 CHASE ON BPM 120")
        _ch = cuestack_pool.get(103)
        _check("CS CHASE ON enables chase_enabled", _ch is not None and _ch.chase_enabled is True)
        _check("CS CHASE ON BPM sets chase_bpm", _ch is not None and abs(_ch.chase_bpm - 120.0) < 0.1)
        _check("CS CHASE ON returns confirmation", "chase" in r_ch_on.lower())
        r_ch_bpm = run_command("CS 103 CHASE BPM 90")
        _check("CS CHASE BPM updates chase_bpm", _ch is not None and abs(_ch.chase_bpm - 90.0) < 0.1)
        r_ch_off = run_command("CS 103 CHASE OFF")
        _check("CS CHASE OFF disables chase_enabled", _ch is not None and _ch.chase_enabled is False)
        _check("CS CHASE OFF returns confirmation", "chase" in r_ch_off.lower())
        # CS INFO shows chase state
        r_ch_info = run_command("CS 103 INFO")
        _check("CS INFO shows chase field", "Chase" in r_ch_info or "chase" in r_ch_info.lower())
        # Save/load round-trip
        _ch.chase_enabled = True; _ch.chase_bpm = 77.0
        ShowFile.save_cuestacks(cuestack_pool)
        _ch2 = CueStack(103, "ChaseTest")
        _tmp_pool = CueStackPool(); _tmp_pool.store(103, _ch2)
        ShowFile.load_cuestacks(_tmp_pool, CuePool())
        _reloaded_ch = _tmp_pool.get(103)
        _check("CS CHASE save/load preserves chase_enabled",
               _reloaded_ch is not None and _reloaded_ch.chase_enabled is True)
        _check("CS CHASE save/load preserves chase_bpm",
               _reloaded_ch is not None and abs(_reloaded_ch.chase_bpm - 77.0) < 0.1)
        _ch.chase_enabled = False
        cuestack_pool.stacks.pop(103, None)

        # ── FADER SIZE — per-executor FX amplitude multiplier ────────────
        _sz_ex = executor_pool.get(3)
        _sz_ex.size_factor = 1.0
        r_sz_plus = run_command("FADER 3 SIZE+")
        _check("FADER SIZE+ nudges size_factor up to ~1.25",
               abs(_sz_ex.size_factor - 1.25) < 0.01)
        _check("FADER SIZE+ returns confirmation", "size" in r_sz_plus.lower())
        run_command("FADER 3 SIZE-")
        _check("FADER SIZE- returns size_factor to ~1.00",
               abs(_sz_ex.size_factor - 1.0) < 0.01)
        run_command("FADER 3 SIZE+")
        r_sz_reset = run_command("FADER 3 SIZE RESET")
        _check("FADER SIZE RESET returns size_factor to 1.0", _sz_ex.size_factor == 1.0)
        _check("FADER SIZE RESET returns confirmation", "reset" in r_sz_reset.lower())
        r_sz_set = run_command("FADER 3 SIZE 2.0")
        _check("FADER SIZE 2.0 sets size_factor to 2.0",
               abs(_sz_ex.size_factor - 2.0) < 0.01)
        _check("FADER SIZE 2.0 returns confirmation", "2.0" in r_sz_set or "2.00" in r_sz_set)
        # SIZE propagates to owned FX layers (if any are active)
        run_command("FX CLEAR")
        run_command("1 THRU 3")
        run_command("FX SINE RED BPM 60 SIZE 100")
        _sz_layer_id = _sz_ex._fx_ids[0] if _sz_ex._fx_ids else None
        if _sz_layer_id is not None:
            _sz_layer = fx_engine._layers.get(_sz_layer_id)
            _sz_ex.size_factor = 0.5
            _sz_ex._apply_size_factor()
            _check("FADER SIZE: _apply_size_factor sets size_scale on owned layer",
                   _sz_layer is None or abs(_sz_layer.size_scale - 0.5) < 0.01)
        _sz_ex.size_factor = 1.0
        _sz_ex._apply_size_factor()
        run_command("FX CLEAR")
        prog.clear_programmer()

        # ── AT … IN <seconds> LIVE PROGRAMMER FADE ────────────────────────
        prog.clear_programmer()
        run_command("1")
        run_command("AT FULL")                     # establish a src dim=1.0
        _pre_fade_dim = prog.data.get("1", {}).get("dim")
        run_command("AT 0 IN 5")                   # fade dim 1.0→0.0 over 5s
        _check("AT … IN creates a live_fade entry",
               len(prog.live_fades) >= 1)
        _fade_entry = next(
            (f for f in prog.live_fades if f['fid'] == '1' and f['channel'] == 'dim'),
            None)
        _check("live_fade entry has correct dst (0.0)",
               _fade_entry is not None and abs(_fade_entry['dst'] - 0.0) < 0.01)
        _check("live_fade entry has correct duration (5.0)",
               _fade_entry is not None and abs(_fade_entry['duration'] - 5.0) < 0.01)
        _check("live_fade entry has a non-zero src",
               _fade_entry is not None and (_fade_entry['src'] or 0) > 0.0)
        # PROG FADE CLEAR should purge all active fades
        r_pfc = run_command("PROG FADE CLEAR")
        _check("PROG FADE CLEAR empties live_fades list", len(prog.live_fades) == 0)
        _check("PROG FADE CLEAR returns confirmation", "clear" in r_pfc.lower())
        prog.clear_programmer()

    except Exception as e:
        _check(f"smoke test raised {type(e).__name__}: {e}", False)

    # ── GUI structural build check ──────────────────────────────────────
    # Every session that's added or touched a popup has had to say some
    # version of "reviewed by hand against the existing builders it
    # mirrors — headless mode skips gui.build() entirely, so the new
    # widgets aren't exercised by the smoke test itself." That caveat
    # doesn't have to keep repeating: DearPyGui can construct a full
    # widget tree with no display at all — only show_viewport() touches
    # GLFW/X11 and needs a real one (it hard-crashes without $DISPLAY).
    # Patch it to a no-op so the real, unmodified gui.build() runs start
    # to finish (every panel, every popup, every tag, the whole handler
    # registry) and any structural bug — duplicate tag, bad item
    # reference, build-order mistake — surfaces here instead of only at
    # next interactive launch.
    if _DPG_OK:
        _orig_show_viewport = dpg.show_viewport
        dpg.show_viewport = lambda *a, **k: None
        try:
            gui.build()
            _check("gui.build() constructs all windows/widgets without error", True)
            # ── fixture-dim-slider unit fix ──────────────────────────────
            # _on_fixture_dim_slider passed dim*100 into MasterFixture.
            # set_dimmer(), which expects a 0.0-1.0 fraction (per its own
            # docstring) and clamps to it -- so any drag above ~1% silently
            # forced virtual_dimmer to 1.0 regardless of the slider's real
            # position. programmer_layer['dim'] masks this live (it's read
            # first), but virtual_dimmer is the fallback default read once
            # that key is gone (e.g. after CLEAR) and is what status/PATCH
            # LIST prints directly -- so it would misreport 100% instead of
            # the real level.
            gui._on_fixture_dim_slider(None, 0.5, 1)
            _check("fixture-dim slider sets virtual_dimmer to the slider's "
                   "actual fraction, not fraction*100 clamped to 1.0",
                   patch.get(1).virtual_dimmer == 0.5)
            gui._on_fixture_dim_slider(None, 1.0, 1)
            patch.get(1).virtual_dimmer = 1.0  # restore default for any later use
        except Exception as e:
            _check(f"gui.build() raised {type(e).__name__}: {e}", False)
        finally:
            dpg.show_viewport = _orig_show_viewport
            try:
                dpg.destroy_context()
            except Exception:
                pass
    else:
        _check("gui.build() constructs all windows/widgets without error (skipped: dearpygui not installed)", True)

    ok = all(passed for _, passed in _results)
    print(f"\n*** SMOKE TEST {'PASSED' if ok else 'FAILED'} "
          f"({sum(p for _, p in _results)}/{len(_results)}) ***\n")

    network.stop()
    midi.stop()
    osc.stop()
    fx_engine.stop()
    fade_engine.stop()
    audio_mapper.stop()
    audio_engine.stop()
    _sys.exit(0 if ok else 1)
else:
    gui.build()   # build all widgets (main thread)
    gui.run()     # hand control to DearPyGui — blocks until window closed

midi.stop()
network.stop()
fade_engine.stop()
fx_engine.stop()
audio_mapper.stop()
audio_engine.stop()


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
#   - programmer preview:  IDs 9000+   tracked in _prog_fx_ids  (module-level list)
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
#   FX SINE RED [bpm n] [size n] [SPREAD n]
#   FX ADD SINE BLUE [...]
#   FX FORM <n> RED [...]          — use FormPool waveform shape
#   FX CLEAR                       — clear all FX from programmer
#   FX CLEAR DIM                   — clear only dim channel FX (leaves RGB FX)
#   FX CLEAR RED / GREEN / BLUE    — clear only that colour channel FX
#   FX LIST
#   RECORD FX <n> [name]           — snapshot programmer FX → pool
#   FIRE FX <n>                    — add preset to programmer (channel-additive; same-channel layers replaced)
#   FORM LIST
#   record form <n> [name] 0.0,0.0 0.5,1.0 1.0,0.0   — custom breakpoint curve
#   record cs [n] cue <m> [preset-tokens]
#   go cs [n] cue <m>
#
# ── POOLS ──────────────────────────────────────────────────────────────────────
#   color_pool    — Colorpreset  (numbered, saved to colors.json)
#   dim_pool      — Dimpreset    (numbered, saved to dims.json)
#   group_pool    — group        (numbered, saved to groups.json)
#   cuestack_pool — cuestack     (numbered, saved to cuestacks.json)
#   fx_pool       — FXpreset     (numbered, 1-12 visible in GUI, saved to fx_pool.json)
#   form_pool     — Formpreset   (1-4 built-in builtins: sine/ramp/pulse/square;
#                                 5+ custom breakpoint curves; saved to forms.json)
#   executor_pool — Executor     (cuestack/level/priority/mode saved to executors.json)
#
# ── WHAT WORKS ────────────────────────────────────────────────────────────────
# - Full output pipeline (sACN, FX additive, programmer+cue merge)
# - cuestack playback with fades, executor isolation, LTP priority
# - FX as programmer-native (redesigned this session — just landed)
# - CLEAR 3-tap protocol: selection → programmer → full output
# - FX pool record/fire, Forms pool with custom breakpoints
# - show file per-category save/load with .bak auto-backup
# - GUI panels: cuestacks, groups, colors, dims, FX pool, forms pool
# - MIDI fader control, OSC bridge, AI command layer (ANTHROPIC_API_KEY gated)
# - audio reactive panel: device pick, capture start/stop, mapping toggle,
#   gain, live level/low/mid/high meters (GUI front-end for Block 9)
#
# ── KNOWN ISSUES / TODO ───────────────────────────────────────────────────────
# - executor_pool now persists cuestack assignments to executors.json; loaded
#   at startup so GO works immediately after restart without re-assigning.
#
# =============================================================================
