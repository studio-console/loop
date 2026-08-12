# Studio Console — Current State

**Date:** 2026-08-12  
**Version:** v0.21  
**Smoke test:** 456/456 PASS  
**Branch:** main, 2 commits ahead of origin (not pushed)

---

## What's working

- Full MA2/MA3-style fader page: 10 slots per page, cue list + thin fader side-by-side, priority badge (hi/nrm/lo), output-mode badge (nrm/moment/vfade)
- Faders: 0–255 integer resolution, dynamic resize with window
- Output modes: normal, moment (active only while level > 0), vfade (fader crossfades between two cues)
- Trigger modes: toggle, flash, moment (fade out on release via off_time)
- Priority: hi/nrm/lo — controls LTP merge order
- FX engine: sine/ramp/square/pulse/triangle/sawtooth/flicker waveforms, per-channel per-fixture
- Speed master: 16-slot BPM presets, MIDI-mappable
- Full attribute channel support: pan/tilt/gobo/zoom/focus/iris/strobe
- Moving light profiles (Generic_Moving, Generic_Moving_Wash)
- MIDI CC/note mapping (live, no code changes needed)
- OSC input: MA3-compatible `/gma3/fader/...` routes
- AI engine integration
- Save/load show, backup, named saves in `studio_saves/`

## Recent changes (this session)

1. **stk/fdr rename** (DeepSeek, 2026-08-12): Full executor→fader / cuestack→stack rename
   - Short aliases: `CS`/`EXEC` removed; now `stk`/`fdr`
   - Data files renamed: `stacks.json`, `faders.json`, `fader_pages.json`
   - Parser, help text, UI labels, changelog all updated
   - Commits: `e1a2026`, `1b265a2`

2. **GUI visual polish** (DeepSeek, 2026-08-12):
   - Font switched to Avenir 17px throughout (was mono 14px)
   - Rounded corners: 12px panels, 9px sliders
   - Deeper violet background, elevated card panels, inset input wells
   - Forms pool width fix (right edge now symmetric)
   - 6th fixture clipping fix in stage visualiser
   - STUDIO wordmark in header

3. **Test stacks 11–14** in `studio_data/stacks.json`:
   - 11: vFade A↔B (amber/cyan crossfade via fader level)
   - 12: Moment Flash (white, holds while button held, fades out in 0.8s)
   - 13: HI Override Blue (priority=1, dominates NRM stacks in LTP merge)
   - 14: FX Chase (3 FX looks, auto-advance every 5s, wrap=True)

## Known / pending

- Stacks 11–14 in show file need re-seeding after any headless smoke test run (smoke test SaveShow wipes them — known issue, not fixed yet)
- 2 local commits not pushed to remote
- File split planned: studio_project.py is 21k lines / ~319k tokens — expensive for AI context. Plan is to split into models / engine / commands / gui / drivers / show / tests / main
- No other known bugs

## How to hand off to another AI

Paste `CLAUDE.md` for architecture context, then this file for current state.  
Point the AI at the specific function/line rather than loading the whole file.
