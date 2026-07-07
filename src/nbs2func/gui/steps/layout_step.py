from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from nbs2func.gui.state import set_layout_mode
from nbs2func.gui.steps.base import WizardStep


LAYOUT_DESCRIPTIONS = {
    "basic_linear": (
        "Simple and stable single-track linear layout.\n"
        "Recommended for quick tests and simple songs."
    ),
    "track_based_stereo": (
        "Places each track/layer according to volume and panning.\n"
        "Recommended for stable multi-track stereo generation."
    ),
    "note_based_stereo": (
        "Places individual note emitters according to note-level stereo information.\n"
        "More spatialized but more complex and slower for large songs."
    ),
}


class LayoutStep(WizardStep):
    title = "Layout"

    def __init__(self, parent, app) -> None:
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self.mode_var = tk.StringVar()
        self.description_var = tk.StringVar()

        ttk.Label(self, text="Layout mode").grid(row=0, column=0, sticky="w")
        modes = ttk.Frame(self)
        modes.grid(row=1, column=0, sticky="ew", pady=(8, 12))
        for index, mode in enumerate(LAYOUT_DESCRIPTIONS):
            ttk.Radiobutton(
                modes,
                text=mode,
                value=mode,
                variable=self.mode_var,
                command=self._on_change,
            ).grid(row=index, column=0, sticky="w", pady=3)
        ttk.Label(self, textvariable=self.description_var, justify="left").grid(
            row=2, column=0, sticky="nw"
        )

    def on_show(self) -> None:
        self.mode_var.set(self.state.config.layout_mode)
        self._render_description()

    def _on_change(self) -> None:
        set_layout_mode(self.state, self.mode_var.get())
        self._render_description()
        self.app.refresh()

    def _render_description(self) -> None:
        self.description_var.set(LAYOUT_DESCRIPTIONS.get(self.mode_var.get(), ""))

    def apply(self) -> bool:
        set_layout_mode(self.state, self.mode_var.get())
        return True

    def is_complete(self) -> bool:
        return self.mode_var.get() in LAYOUT_DESCRIPTIONS

    def status_text(self) -> str:
        return f"Selected layout mode: {self.state.config.layout_mode}"
