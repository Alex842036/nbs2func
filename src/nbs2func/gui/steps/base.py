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


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(
            self,
            orient="vertical",
            command=self.canvas.yview,
        )
        self.inner = ttk.Frame(self.canvas)
        self.inner.columnconfigure(0, weight=1)
        self.window_id = self.canvas.create_window(
            (0, 0),
            window=self.inner,
            anchor="nw",
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

    def _on_inner_configure(self, _event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self.window_id, width=event.width)


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
