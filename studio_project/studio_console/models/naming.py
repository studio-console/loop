"""Shared name-normalization descriptor.

Every user-nameable thing the console can RECORD/RENAME/COPY (colour,
dimmer, group, cue, stack, fx, attribute presets, form/rate/size/spread
presets, speed masters, patched fixtures) stores its display name
through this descriptor instead of a plain attribute, so there is no
code path — command line, GUI, AI, or a future one nobody's written yet
— that can leave a capital letter in a saved name. Enforced once at the
model layer instead of at each RECORD/RENAME/COPY call site, so it can't
be missed at any of them (and loading an old show with capitalized names
already saved normalizes them in memory the moment they're read back in).

Deliberately NOT applied to FixtureProfile.name — that's GDTF library
metadata (real manufacturer/fixture-type names for display), not a
pool the operator names themselves.
"""


class LowercaseName:
    def __set_name__(self, owner, attr):
        self._attr = "_" + attr

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return getattr(obj, self._attr, "")

    def __set__(self, obj, value):
        setattr(obj, self._attr, value.lower() if isinstance(value, str) else value)
