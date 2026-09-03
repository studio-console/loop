"""GUIEngine's AI history/prompts/chip-bar popups.

Part of the GUIEngine mixin split — see studio_project.py for how this
combines with the other gui/*.py mixins into the final GUIEngine class via
multiple inheritance.
"""

import threading

from studio_console.gui.theme import *  # noqa: F401,F403
from studio_console.show import ShowFile


class GUIEngineAIPopups:
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
                dpg.focus_item("cmd_input")
                self._ai_end_conversation()
            else:
                dpg.show_item("ai_bar_window")
                dpg.focus_item("ai_input")
        except Exception:
            pass
    def _on_ai_bar_close(self, *_):
        """Native window-X close — same cleanup as the header toggle button,
        plus handing focus back to cmd_input (see _on_ai_send)."""
        self._save_popup_layout()
        try:
            dpg.focus_item("cmd_input")
        except Exception:
            pass
        self._ai_end_conversation()
    def _ai_end_conversation(self):
        """Closing the AI window ends the conversation — the next prompt
        starts fresh rather than dragging in an old, unrelated exchange."""
        if self._ai:
            try:
                self._ai.clear_chat_history()
            except Exception:
                pass
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
        if not getattr(self._ai, '_enabled', False):
            _env_key = getattr(self._ai, '_env_key', 'ANTHROPIC_API_KEY')
            try:
                dpg.configure_item("ai_status",
                                   default_value=f"ai disabled — set {_env_key}",
                                   color=(220, 80, 80, 255))
            except Exception:
                pass
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
        # Keep the cursor in the ai window while it's in use, rather than
        # letting it fall back to cmd_input — on_enter submission in DPG
        # drops native focus off the input_text, and with nothing focused
        # the global key handlers (_on_global_char etc.) route the next
        # keystroke to cmd_input by default. Re-claim focus immediately,
        # and again once the (threaded, possibly slow) request finishes,
        # in case the wait itself let focus drift. Only closing the ai
        # window (see _on_ai_bar_close/_on_ai_bar_toggle) or a manual
        # click elsewhere should send focus back to cmd_input.
        try:
            dpg.focus_item("ai_input")
        except Exception:
            pass

        def _run():
            try:
                actions = self._ai.ask(prompt)
            except Exception as _ae:
                actions = []
                try:
                    self._log(f"ai error: {_ae}")
                except Exception:
                    pass
            finally:
                try:
                    dpg.configure_item("ai_status", default_value="", color=_C_DIM)
                except Exception:
                    pass
                try:
                    if dpg.is_item_shown("ai_bar_window"):
                        dpg.focus_item("ai_input")
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
