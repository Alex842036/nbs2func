from __future__ import annotations

import os
import queue
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from nbs2func.config import save_config
from nbs2func.gui.state import append_log, clear_log
from nbs2func.gui.steps.base import WizardStep


class GenerateStep(WizardStep):
    title = "Generate"

    def __init__(self, parent, app) -> None:
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.status_var = tk.StringVar(value="Ready to generate.")
        self.events: queue.Queue[tuple[str, str | int]] = queue.Queue()
        self.thread: threading.Thread | None = None

        ttk.Label(self, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        self.log = tk.Text(self, height=24, wrap="word")
        self.log.grid(row=1, column=0, sticky="nsew", pady=(8, 8))
        buttons = ttk.Frame(self)
        buttons.grid(row=2, column=0, sticky="ew")
        self.open_button = ttk.Button(
            buttons,
            text="Open output folder",
            command=self.open_output_folder,
            state="disabled",
        )
        self.open_button.grid(row=0, column=0, sticky="w")
        ttk.Button(
            buttons,
            text="Generate another",
            command=self.app.back_to_summary,
        ).grid(row=0, column=1, sticky="w", padx=(8, 0))

    def on_show(self) -> None:
        self._render_log()

    def start_generation(self) -> None:
        if self.thread is not None and self.thread.is_alive():
            return
        clear_log(self.state)
        self.open_button.configure(state="disabled")
        self.status_var.set("Generating...")
        self._render_log()
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()
        self.after(100, self._poll_events)

    def _worker(self) -> None:
        repo_root = Path(__file__).resolve().parents[4]
        try:
            self.events.put(("log", "Saving temporary config..."))
            with tempfile.TemporaryDirectory(prefix="nbs2func-gui-") as temp_dir:
                config_path = Path(temp_dir) / "config.json"
                save_config(self.state.config, config_path)
                self.events.put(("log", "Reading NBS..."))
                self.events.put(("log", "Generating layout..."))
                self.events.put(("log", "Building blocks and writing outputs..."))
                env = os.environ.copy()
                src_path = str(repo_root / "src")
                current_pythonpath = env.get("PYTHONPATH")
                env["PYTHONPATH"] = (
                    src_path
                    if not current_pythonpath
                    else os.pathsep.join([src_path, current_pythonpath])
                )
                command = [
                    sys.executable,
                    str(repo_root / "main.py"),
                    "--config",
                    str(config_path),
                ]
                process = subprocess.Popen(
                    command,
                    cwd=str(repo_root),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                assert process.stdout is not None
                for line in process.stdout:
                    self.events.put(("log", line.rstrip()))
                return_code = process.wait()
                self.events.put(("done", return_code))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _poll_events(self) -> None:
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                append_log(self.state, str(payload))
                self._append_line(str(payload))
            elif kind == "done":
                if int(payload) == 0:
                    append_log(self.state, "Done.")
                    self._append_line("Done.")
                    self.status_var.set("Generation succeeded.")
                    self.open_button.configure(state="normal")
                else:
                    self.status_var.set(f"Generation failed with exit code {payload}.")
            elif kind == "error":
                self.status_var.set("Generation failed.")
                self._append_line(f"Error: {payload}")
                messagebox.showerror("Generate", str(payload))
        if self.thread is not None and self.thread.is_alive():
            self.after(100, self._poll_events)
        self.app.refresh()

    def _render_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        if self.state.output_log:
            self.log.insert("end", "\n".join(self.state.output_log) + "\n")
        self.log.configure(state="disabled")

    def _append_line(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def open_output_folder(self) -> None:
        path = Path(self.state.config.output)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[4] / path
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except OSError as exc:
            messagebox.showerror("Open output folder", str(exc))

    def is_complete(self) -> bool:
        return True

    def status_text(self) -> str:
        return self.status_var.get()
