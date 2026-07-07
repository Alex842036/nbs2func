from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nbs2func.gui.wizard import WizardApp


class WizardStep(ttk.Frame):
    title = ""

    def __init__(self, parent: tk.Widget, app: WizardApp) -> None:
        super().__init__(parent)
        self.app = app

    @property
    def state(self):
        return self.app.state_data

    def on_show(self) -> None:
        pass

    def apply(self) -> bool:
        return True

    def is_complete(self) -> bool:
        return True

    def status_text(self) -> str:
        return ""


def labeled_entry(
    parent: tk.Widget,
    row: int,
    label: str,
    variable: tk.Variable,
    width: int = 28,
) -> ttk.Entry:
    ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=3)
    entry = ttk.Entry(parent, textvariable=variable, width=width)
    entry.grid(row=row, column=1, sticky="ew", pady=3)
    return entry


def labeled_option(
    parent: tk.Widget,
    row: int,
    label: str,
    variable: tk.Variable,
    values: tuple[str, ...] | list[str],
) -> ttk.Combobox:
    ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=3)
    combo = ttk.Combobox(parent, textvariable=variable, values=tuple(values), state="readonly")
    combo.grid(row=row, column=1, sticky="ew", pady=3)
    return combo


def bool_state(enabled: bool) -> str:
    return "normal" if enabled else "disabled"
