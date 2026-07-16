from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from nbs2func.gui.state import summary_lines, validate_ready_to_generate
from nbs2func.gui.steps.base import WizardStep


class SummaryStep(WizardStep):
    title_key = "step.summary.name"

    def __init__(self, parent, app) -> None:
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.text = tk.Text(self, height=24, wrap="word")
        self.text.grid(row=0, column=0, sticky="nsew")
        actions = ttk.Frame(self)
        actions.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(actions, text=self.app.tr("common.save_config"), command=self.save_config).grid(
            row=0, column=0, sticky="w"
        )

    def on_show(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("end", "\n".join(summary_lines(self.state, self.app.tr)))
        errors = validate_ready_to_generate(self.state, self.app.tr)
        if errors:
            self.text.insert("end", f"\n\n{self.app.tr('step.summary.errors')}\n")
            self.text.insert("end", "\n".join(f"- {error}" for error in errors))
        self.text.configure(state="disabled")

    def save_config(self) -> None:
        self.app.save_config_file()

    def is_complete(self) -> bool:
        return not validate_ready_to_generate(self.state, self.app.tr)

    def status_text(self) -> str:
        errors = validate_ready_to_generate(self.state, self.app.tr)
        if errors:
            return errors[0]
        return self.app.tr("step.summary.review")
