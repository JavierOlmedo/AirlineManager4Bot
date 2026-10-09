"""Small custom widgets for the GUI: hover tooltips."""
from __future__ import annotations

import tkinter as tk
from typing import Optional

import customtkinter as ctk

UI_FONT = "Segoe UI"

TOOLTIP_THEME = {   # same palette as assets/theme.json
    "Light": {"bg": "#ffffff", "border": "#d0d7de", "ink": "#1f2328"},
    "Dark": {"bg": "#161b22", "border": "#30363d", "ink": "#e6edf3"},
}


class ToolTip:
    """Hover help for any widget: appears after a short delay, follows the theme."""

    def __init__(self, widget, text: str, delay_ms: int = 450, wrap: int = 340):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self.wrap = wrap
        self._after: Optional[str] = None
        self._tip: Optional[tk.Toplevel] = None
        targets = [widget]
        try:
            widget.bind("<Enter>", self._schedule, add="+")
        except (NotImplementedError, ValueError):
            # some customtkinter widgets (segmented button) do not support bind(): use their children
            targets = list(widget.winfo_children())
            for child in targets:
                child.bind("<Enter>", self._schedule, add="+")
        for target in targets:
            target.bind("<Leave>", self._hide, add="+")
            target.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None) -> None:
        self._cancel()
        self._after = self.widget.after(self.delay_ms, self._show)

    def _cancel(self) -> None:
        if self._after is not None:
            try:
                self.widget.after_cancel(self._after)
            except (tk.TclError, ValueError):
                pass
            self._after = None

    def _show(self) -> None:
        if self._tip is not None or not self.text:
            return
        colors = TOOLTIP_THEME["Dark" if ctk.get_appearance_mode() == "Dark" else "Light"]
        x = self.widget.winfo_pointerx() + 14
        y = self.widget.winfo_pointery() + 18
        self._tip = tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.attributes("-topmost", True)
        frame = tk.Frame(tip, bg=colors["border"], padx=1, pady=1)
        frame.pack()
        tk.Label(frame, text=self.text, justify="left", wraplength=self.wrap, bg=colors["bg"], fg=colors["ink"],
                 font=(UI_FONT, 9), padx=9, pady=6).pack()
        tip.update_idletasks()
        width = tip.winfo_width()
        tip.wm_geometry(f"+{min(x, tip.winfo_screenwidth() - width - 8)}+{y}")

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


def add_tooltip(widget, text: Optional[str]) -> None:
    if text:
        ToolTip(widget, text)
