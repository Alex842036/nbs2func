from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from nbs2func.gui.helpers import absolute_path_text
from nbs2func.gui.state import load_input_song
from nbs2func.gui.steps.base import WizardStep


class InputStep(WizardStep):
    title = "Input"
    help_text = "Choose an Open Note Block Studio .nbs file and load its song summary."

    def __init__(self, parent, app) -> None:
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self.path_var = tk.StringVar()
        self.summary_var = tk.StringVar(value="No song loaded.")
        self.error_var = tk.StringVar()

        ttk.Label(self, text="Input NBS file").grid(row=0, column=0, sticky="w")
        row = ttk.Frame(self)
        row.grid(row=1, column=0, sticky="ew", pady=(8, 12))
        row.columnconfigure(0, weight=1)
        path_entry = ttk.Entry(row, textvariable=self.path_var)
        path_entry.grid(row=0, column=0, sticky="ew")
        self.register_help(
            path_entry,
            "Full path to the .nbs song file to convert.",
        )
        browse_button = ttk.Button(row, text="Browse...", command=self.browse)
        browse_button.grid(row=0, column=1, padx=(8, 0))
        self.register_help(browse_button, "Open a file picker for .nbs input files.")
        load_button = ttk.Button(row, text="Load NBS", command=self.load_path)
        load_button.grid(row=0, column=2, padx=(8, 0))
        self.register_help(load_button, "Read the selected .nbs file and show its summary.")

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

    def browse(self) -> None:
        path = filedialog.askopenfilename(
            title="Select NBS file",
            filetypes=(("Open Note Block Studio", "*.nbs"), ("All files", "*.*")),
        )
        if path:
            self.path_var.set(absolute_path_text(path))
            self.load_path()

    def load_path(self) -> None:
        self.error_var.set("")
        try:
            load_input_song(self.state, self.path_var.get())
        except Exception as exc:  # Keep GUI alive for malformed preview inputs.
            self.state.input_song_summary = None
            self.error_var.set(f"Could not read NBS file: {exc}")
            self.summary_var.set("No song loaded.")
            self.app.refresh()
            return
        self.path_var.set(self.state.config.input_path)
        self._render_summary()
        self.app.refresh()

    def _render_summary(self) -> None:
        summary = self.state.input_song_summary or {}
        instruments = summary.get("instrument_summary") or {}
        if isinstance(instruments, dict):
            instrument_text = ", ".join(
                f"{instrument}: {count}" for instrument, count in instruments.items()
            )
        else:
            instrument_text = "n/a"
        self.summary_var.set(
            "\n".join(
                [
                    f"NBS file path: {summary.get('path', '')}",
                    f"Song name: {summary.get('name', '')}",
                    f"Author: {summary.get('author', '')}",
                    f"Song length / ticks: {summary.get('length', 'n/a')}",
                    f"Tempo: {summary.get('tempo', 'n/a')}",
                    f"Layer count: {summary.get('layer_count', 'n/a')}",
                    f"Note count: {summary.get('note_count', 'n/a')}",
                    f"Instrument summary: {instrument_text or 'none'}",
                ]
            )
        )

    def apply(self) -> bool:
        selected_path = Path(self.path_var.get()).expanduser().resolve()
        loaded_path = None
        if self.state.input_song_summary is not None:
            raw_loaded_path = self.state.input_song_summary.get("path")
            loaded_path = (
                Path(str(raw_loaded_path)).expanduser().resolve()
                if raw_loaded_path
                else None
            )
        if selected_path.is_file() and selected_path != loaded_path:
            self.load_path()
        if not self.is_complete():
            messagebox.showerror("Input required", "Select a readable .nbs file first.")
            return False
        return True

    def is_complete(self) -> bool:
        return self.state.input_song_summary is not None

    def status_text(self) -> str:
        return self.help_text
