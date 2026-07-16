from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from nbs2func.gui.state import set_layout_mode
from nbs2func.gui.steps.base import WizardStep


LAYOUT_MODES = ("basic_linear", "track_based_stereo", "note_based_stereo")


class LayoutStep(WizardStep):
    title_key = "step.layout.name"
    help_key = "step.layout.help"

    def __init__(self, parent, app) -> None:
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self.mode_var = tk.StringVar()
        self.description_var = tk.StringVar()

        ttk.Label(self, text=self.app.tr("step.layout.heading")).grid(row=0, column=0, sticky="w")
        modes = ttk.Frame(self)
        modes.grid(row=1, column=0, sticky="ew", pady=(8, 12))
        for index, mode in enumerate(LAYOUT_MODES):
            button = ttk.Radiobutton(
                modes,
                text=self.app.tr(f"step.layout.mode.{mode}"),
                value=mode,
                variable=self.mode_var,
                command=self._on_change,
            )
            button.grid(row=index, column=0, sticky="w", pady=3)
            self.register_help(
                button,
                self.app.tr(self.help_key),
            )
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
        mode = self.mode_var.get()
        self.description_var.set(
            self.app.tr(f"step.layout.description.{mode}") if mode in LAYOUT_MODES else ""
        )

    def apply(self) -> bool:
        set_layout_mode(self.state, self.mode_var.get())
        return True

    def is_complete(self) -> bool:
        return self.mode_var.get() in LAYOUT_MODES

    def status_text(self) -> str:
        return self.app.tr(self.help_key)
