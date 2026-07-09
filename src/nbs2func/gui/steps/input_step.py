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
        else:
            self.summary_var.set("No song loaded.")

    def browse(self) -> None:
        path = filedialog.askopenfilename(
            title="Select NBS file",
            filetypes=(("Open Note Block Studio", "*.nbs"), ("All files", "*.*")),
        )
        if path:
            self.path_var.set(absolute_path_text(path))
            self.load_path()

    def load_path(self) -> bool:
        self.error_var.set("")
        raw_path = self.path_var.get().strip()
        if not raw_path:
            self.state.input_song_summary = None
            self.summary_var.set("No song loaded.")
            self.error_var.set("Choose an .nbs file before loading.")
            self.app._refresh_buttons()
            self.app._refresh_status()
            return False
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            self.state.input_song_summary = None
            self.summary_var.set("No song loaded.")
            self.error_var.set(f"NBS file does not exist: {path}")
            self.app._refresh_buttons()
            self.app._refresh_status()
            return False
        if not path.is_file():
            self.state.input_song_summary = None
            self.summary_var.set("No song loaded.")
            self.error_var.set(f"NBS path is not a file: {path}")
            self.app._refresh_buttons()
            self.app._refresh_status()
            return False
        try:
            load_input_song(self.state, path)
        except Exception as exc:  # Keep GUI alive for malformed preview inputs.
            self.state.input_song_summary = None
            self.error_var.set(f"Could not read NBS file: {exc}")
            self.summary_var.set("No song loaded.")
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
        if input_path_needs_reload(
            self.path_var.get(),
            self.state.input_song_summary,
        ):
            self.load_path()
        if not self.is_complete():
            messagebox.showerror("Input required", "Select a readable .nbs file first.")
            return False
        return True

    def is_complete(self) -> bool:
        return self.state.input_song_summary is not None

    def status_text(self) -> str:
        return self.help_text
