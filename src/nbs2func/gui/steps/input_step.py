from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from nbs2func.gui.helpers import absolute_path_text
from nbs2func.gui.state import load_input_song
from nbs2func.gui.steps.base import WizardStep


def loaded_input_path(summary: dict[str, object] | None) -> Path | None:
    if summary is None:
        return None
    raw_path = summary.get("path")
    if not raw_path:
        return None
    return Path(str(raw_path)).expanduser().resolve()


def input_path_needs_reload(
    selected_text: str,
    summary: dict[str, object] | None,
) -> bool:
    if not selected_text.strip():
        return True
    return Path(selected_text).expanduser().resolve() != loaded_input_path(summary)


class InputStep(WizardStep):
    title_key = "step.input.name"
    help_key = "step.input.help"

    def __init__(self, parent, app) -> None:
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self.path_var = tk.StringVar()
        self.summary_var = tk.StringVar(value=self.app.tr("step.input.no_song"))
        self.error_var = tk.StringVar()

        ttk.Label(self, text=self.app.tr("step.input.heading")).grid(row=0, column=0, sticky="w")
        row = ttk.Frame(self)
        row.grid(row=1, column=0, sticky="ew", pady=(8, 12))
        row.columnconfigure(0, weight=1)
        path_entry = ttk.Entry(row, textvariable=self.path_var)
        path_entry.grid(row=0, column=0, sticky="ew")
        self.register_help(
            path_entry,
            self.app.tr("step.input.path_help"),
        )
        browse_button = ttk.Button(row, text=self.app.tr("common.browse"), command=self.browse)
        browse_button.grid(row=0, column=1, padx=(8, 0))
        self.register_help(browse_button, self.app.tr("step.input.browse_help"))
        load_button = ttk.Button(row, text=self.app.tr("step.input.load"), command=self.load_path)
        load_button.grid(row=0, column=2, padx=(8, 0))
        self.register_help(load_button, self.app.tr("step.input.load_help"))

        ttk.Label(self, textvariable=self.summary_var, justify="left").grid(
            row=2, column=0, sticky="nw"
        )
        ttk.Label(self, textvariable=self.error_var, foreground="#a00000").grid(
            row=3, column=0, sticky="w", pady=(12, 0)
        )

    def on_show(self) -> None:
        self.path_var.set(absolute_path_text(self.state.config.input_path))
        if self.state.input_song_summary is not None:
            self._render_summary()
        else:
            self.summary_var.set(self.app.tr("step.input.no_song"))

    def browse(self) -> None:
        path = filedialog.askopenfilename(
            title=self.app.tr("dialog.select_nbs.title"),
            filetypes=((self.app.tr("dialog.filetype.nbs"), "*.nbs"), (self.app.tr("dialog.filetype.all"), "*.*")),
        )
        if path:
            self.path_var.set(absolute_path_text(path))
            self.load_path()

    def load_path(self) -> bool:
        self.error_var.set("")
        raw_path = self.path_var.get().strip()
        if not raw_path:
            self.state.input_song_summary = None
            self.summary_var.set(self.app.tr("step.input.no_song"))
            self.error_var.set(self.app.tr("step.input.choose_first"))
            self.app._refresh_buttons()
            self.app._refresh_status()
            return False
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            self.state.input_song_summary = None
            self.summary_var.set(self.app.tr("step.input.no_song"))
            self.error_var.set(self.app.tr("step.input.not_exists", path=path))
            self.app._refresh_buttons()
            self.app._refresh_status()
            return False
        if not path.is_file():
            self.state.input_song_summary = None
            self.summary_var.set(self.app.tr("step.input.no_song"))
            self.error_var.set(self.app.tr("step.input.not_file", path=path))
            self.app._refresh_buttons()
            self.app._refresh_status()
            return False
        try:
            load_input_song(self.state, path)
        except Exception as exc:  # Keep GUI alive for malformed preview inputs.
            self.state.input_song_summary = None
            self.error_var.set(self.app.tr("step.input.read_error", error=exc))
            self.summary_var.set(self.app.tr("step.input.no_song"))
            self.app._refresh_buttons()
            self.app._refresh_status()
            return False
        self.path_var.set(self.state.config.input_path)
        self._render_summary()
        self.app.refresh()
        return True

    def _render_summary(self) -> None:
        summary = self.state.input_song_summary or {}
        instruments = summary.get("instrument_summary") or {}
        if isinstance(instruments, dict):
            instrument_text = ", ".join(
                f"{instrument}: {count}" for instrument, count in instruments.items()
            )
        else:
            instrument_text = self.app.tr("common.not_available")
        na = self.app.tr("common.not_available")
        self.summary_var.set(
            "\n".join(
                [
                    self.app.tr("step.input.summary.path", value=summary.get("path", "")),
                    self.app.tr("step.input.summary.name", value=summary.get("name", "")),
                    self.app.tr("step.input.summary.author", value=summary.get("author", "")),
                    self.app.tr("step.input.summary.length", value=summary.get("length", na)),
                    self.app.tr("step.input.summary.tempo", value=summary.get("tempo", na)),
                    self.app.tr("step.input.summary.layers", value=summary.get("layer_count", na)),
                    self.app.tr("step.input.summary.notes", value=summary.get("note_count", na)),
                    self.app.tr("step.input.summary.instruments", value=instrument_text or self.app.tr("common.none")),
                ]
            )
        )

    def apply(self) -> bool:
        if input_path_needs_reload(
            self.path_var.get(),
            self.state.input_song_summary,
        ):
            self.load_path()
        if not self.is_complete():
            messagebox.showerror(
                self.app.tr("dialog.input_required.title"),
                self.app.tr("dialog.input_required.message"),
            )
            return False
        return True

    def is_complete(self) -> bool:
        return self.state.input_song_summary is not None

    def status_text(self) -> str:
        return self.app.tr(self.help_key)
