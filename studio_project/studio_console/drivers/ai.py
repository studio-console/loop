"""Studio Console AI driver — extracted verbatim from studio_project.py
(the "Block 12: AI Engine" section: AIEngine). Pure move, zero behavior
change, EXCEPT one deliberate addition: `_state()` now does a function-local
`from __main__ import Fader` instead of relying on a bare `Fader` name
resolved from studio_project.py's global scope (which is how it worked when
this class lived inside studio_project.py directly). `Fader` still lives in
studio_project.py — it isn't extracted until a later phase.

IMPORTANT: this must be `from __main__ import Fader`, NOT `from
studio_project import Fader`. studio_project.py has no `if __name__ ==
"__main__":` guard, so when it's run normally (`python3 studio_project.py`),
it registers itself in sys.modules as `__main__`, not as `studio_project`.
`from studio_project import Fader` would therefore not find the already-
running module — it would trigger Python to import studio_project.py fresh,
as a second, separate module object, re-executing every top-level
side-effecting line (engine construction, sockets, GUI build, the smoke
test) a second time. `from __main__ import Fader` reaches into the actual
running script's namespace via the `__main__` alias, which is always
already in sys.modules once the script has started — a pure lookup, no
re-execution. This import must stay deferred (inside the function, not at
module top) to avoid a circular-import ordering problem at load time either
way. Do not change it to import from studio_console.models — that path
doesn't exist yet.
"""

import os
import json
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
    - All stacks and their cues
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
{"action": "exec_level",  "fdr": 1, "level": 0.75}

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
- "stack" identifies a stack by id, not a fader slot — it is resolved
  to whichever fader that stack is currently assigned to.
- Only return the JSON array. No explanation, no markdown.
"""

    _CMD_HISTORY_MAX = 12

    # DeepSeek publishes an Anthropic-compatible endpoint (same
    # messages.create() shape, same response.content[0].text /
    # response.usage.input_tokens|output_tokens fields) — so switching
    # provider is just a different api_key/base_url/model, not a
    # different request/response code path. AI_PROVIDER picks which;
    # unset or unrecognized falls back to real Anthropic.
    _PROVIDERS = {
        "anthropic": {
            "env_key":  "ANTHROPIC_API_KEY",
            "base_url": None,
            "model":    "claude-haiku-4-5-20251001",
        },
        "deepseek": {
            "env_key":  "DEEPSEEK_API_KEY",
            "base_url": "https://api.deepseek.com/anthropic",
            "model":    "deepseek-v4-flash",
        },
    }

    def __init__(self, patch, prog, output_state, fx_engine, fade_engine,
                 stack_pool=None, fader_pool=None, cmd_fn=None, log_fn=None,
                 model=None):
        provider = os.environ.get("AI_PROVIDER", "anthropic").strip().lower()
        if provider not in self._PROVIDERS:
            provider = "anthropic"
        _cfg = self._PROVIDERS[provider]
        self._provider  = provider
        self._env_key   = _cfg["env_key"]   # readable even while disabled
        api_key = os.environ.get(_cfg["env_key"])
        if not api_key:
            print(f"  AI Engine: {_cfg['env_key']} not set — AI disabled.")
            print(f"  Run:  export {_cfg['env_key']}='...' "
                  f"(or add it to studio_data/.env)")
            self._enabled = False
            return
        self._client          = anthropic.Anthropic(api_key=api_key,
                                                      base_url=_cfg["base_url"])
        self._model           = model or _cfg["model"]
        self._patch          = patch
        self._prog           = prog
        self._output         = output_state
        self._fx             = fx_engine
        self._fade           = fade_engine
        # Live pool reference (not a snapshot) so newly created/loaded
        # stacks are visible without re-constructing the AI engine.
        self._stack_pool     = stack_pool
        self._fader_pool  = fader_pool
        self._cmd            = cmd_fn    # run_command — full console command parser
        self._log            = log_fn    # GUI log callback
        self._enabled        = True
        self._last_fade      = None      # pending fade_time override, consumed by the next cue fire
        self._cmd_history    = []        # last N commands for context
        self._token_cb       = None      # optional callback(in_tok, out_tok) for GUI
        print(f"  AI Engine: ready ({provider}: {self._model})")

    def push_cmd_history(self, cmd_str):
        """Call after each user command to feed recent context into AI prompts."""
        self._cmd_history.append(cmd_str)
        if len(self._cmd_history) > self._CMD_HISTORY_MAX:
            self._cmd_history = self._cmd_history[-self._CMD_HISTORY_MAX:]

    def _state(self):
        # Fader still lives in studio_project.py until a later phase moves it
        # to studio_console/models/presets.py — deferred (function-local)
        # import avoids a circular import at module load time. Must be
        # `from __main__`, not `from studio_project` — see the module
        # docstring above before changing this.
        from __main__ import Fader
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
        # Active faders
        active_execs = []
        if self._fader_pool:
            for eid, ex in sorted(self._fader_pool.faders.items()):
                if ex.is_active and ex.stack:
                    cur  = ex.stack.current
                    cue  = ex.stack.cues.get(cur) if cur is not None else None
                    active_execs.append({
                        "fdr": eid,
                        "stack": ex.stack.name,
                        "current_cue": cur,
                        "cue_name": cue.name if cue else None,
                        "level": round(ex.level, 2),
                        "priority": Fader.PRIORITY_LABELS.get(ex.priority, 'NRM'),
                    })
        return {
            "fixtures": fixtures,
            "stacks": stacks,
            "fx": fx_active,
            "programmer": prog_data,
            "active_faders": active_execs,
            "recent_commands": list(self._cmd_history),
        }

    def ask(self, prompt, execute=True):
        """
        Send a natural language prompt. Returns the list of actions
        and optionally executes them immediately.
        """
        if not self._enabled:
            print(f"  AI disabled — set {self._env_key} first.")
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
                messages=[{"role": "user", "content": user_msg}],
                timeout=30.0,
                # DeepSeek's models think by default (unlike Claude, where
                # it's opt-in) — a ThinkingBlock then leads resp.content,
                # which has no .text attribute at all, so a bare
                # content[0].text would AttributeError on every DeepSeek
                # request. We want fast, deterministic JSON here, not
                # chain-of-thought, so disable it outright; harmless
                # no-op against real Anthropic, which already defaults
                # to this for a non-extended-thinking model.
                thinking={"type": "disabled"},
            )
            _text_block = next(
                (b for b in resp.content if getattr(b, "text", None) is not None),
                None)
            if _text_block is None:
                raise ValueError(f"no text block in response: {resp.content!r}")
            raw = _text_block.text.strip()
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
        Resolve a stack id (as used in ACTION_SCHEMA's "stack" field and
        in _state()'s stacks section) to the fader slot it's actually
        assigned to. Falls back to a same-numbered fader slot if no
        fader currently has that stack assigned (preserves the
        default 1:1 stack/fader wiring set up at startup).
        """
        if not self._fader_pool:
            return None
        for ex in self._fader_pool.faders.values():
            if ex.stack and ex.stack.stack_id == stack_id:
                return ex
        return self._fader_pool.get(stack_id)

    def _fire(self, ex, fire_fn, *args):
        """
        Fire a cue via one of Fader.go/back/goto, applying a pending
        fade_time override (if any) for just this one fire, then logging
        the result (including failures like 'no stack assigned', which
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
                        self._fader_pool.bump_priority(ex.fdr_id)
                        self._fire(ex, ex.goto, a["num"], self._patch, self._fade)
                elif act == "cue_go":
                    ex = self._exec_for_stack(a.get("stack", 1))
                    if ex:
                        self._fader_pool.bump_priority(ex.fdr_id)
                        self._fire(ex, ex.go, self._patch, self._fade)
                elif act == "cue_back":
                    ex = self._exec_for_stack(a.get("stack", 1))
                    if ex:
                        self._fader_pool.bump_priority(ex.fdr_id)
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
                        self._fader_pool.bump_priority(ex.fdr_id)
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
                    if self._fader_pool and self._cmd:
                        self._cmd(f"FADER {a.get('fdr', 1)} LEVEL {float(a.get('level', 1.0)) * 100:.0f}")
                elif act == "fx_clear":
                    # Route through the real FX CLEAR handler — it both stops
                    # the FX engine layers *and* clears the programmer's
                    # pending 'fx' defs, so a rebuild tick can't resurrect
                    # them. self._fx.clear() alone did neither correctly:
                    # it also wiped fader-owned cue FX layers whose ids
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


__all__ = ["AIEngine"]