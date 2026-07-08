from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from nbs2func.generation import (
    GenerationEvent,
    GenerationResult,
    generate_from_config,
)
from nbs2func.gui.helpers import resolve_gui_generation_config
from nbs2func.gui.state import append_log, clear_log
from nbs2func.gui.steps.base import WizardStep


def format_generation_event(event: GenerationEvent) -> str:
    labels = {
        "phase": "Phase",
        "notice": "Notice",
        "warning": "Warning",
        "output": "Output",
        "error": "Error",
        "done": "Done",
    }
    label = labels.get(event.kind, event.kind.title())
    if event.detail:
        return f"[{label}] {event.message} {event.detail}"
    return f"[{label}] {event.message}"


class GenerateStep(WizardStep):
    title = "Generate"

    def __init__(self, parent, app) -> None:
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self.status_var = tk.StringVar(value="Ready to generate.")
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.thread: threading.Thread | None = None
        self.result: GenerationResult | None = None
        self._saw_error_event = False

        ttk.Label(self, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.grid(row=1, column=0, sticky="ew", pady=(6, 0))

        log_frame = ttk.Frame(self)
        log_frame.grid(row=2, column=0, sticky="nsew", pady=(8, 8))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, height=24, wrap="word")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scrollbar.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        buttons = ttk.Frame(self)
        buttons.grid(row=3, column=0, sticky="ew")
        self.open_datapack_button = ttk.Button(
            buttons,
            text="Open datapack/mcfunction folder",
            command=self.open_datapack_folder,
            state="disabled",
        )
        self.open_datapack_button.grid(row=0, column=0, sticky="w")
        self.open_schematic_button = ttk.Button(
            buttons,
            text="Open schematic folder",
            command=self.open_schematic_folder,
            state="disabled",
        )
        self.open_schematic_button.grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Button(
            buttons,
            text="Generate another",
            command=self.generate_another,
        ).grid(row=0, column=2, sticky="w", padx=(8, 0))

    def on_show(self) -> None:
        if self.thread is not None and self.thread.is_alive():
            return
        self._render_log()
        self._sync_open_buttons()

    def start_generation(self) -> None:
        if self.thread is not None and self.thread.is_alive():
            return
        self.state.config = resolve_gui_generation_config(self.state.config)
        clear_log(self.state)
        self.result = None
        self._saw_error_event = False
        self._set_open_buttons(False, False)
        self.status_var.set("Generating...")
        self._render_log()
        self.progress.start()
        self.app.set_generation_running(True)
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()
        self.after(100, self._poll_events)

    def _worker(self) -> None:
        def emit_to_queue(event: GenerationEvent) -> None:
            self.events.put(("event", event))

        try:
            result = generate_from_config(
                self.state.config,
                progress_callback=emit_to_queue,
                include_diagnostics=False,
            )
            self.events.put(("result", result))
        except Exception as exc:
            self.events.put(("exception", exc))

    def _poll_events(self) -> None:
        collected: list[tuple[str, object]] = []
        while True:
            try:
                collected.append(self.events.get_nowait())
            except queue.Empty:
                break

        lines: list[str] = []
        for kind, payload in collected:
            if kind == "event":
                event = payload
                assert isinstance(event, GenerationEvent)
                if event.kind == "error":
                    self._saw_error_event = True
                line = format_generation_event(event)
                append_log(self.state, line)
                lines.append(line)
            elif kind == "result":
                result = payload
                assert isinstance(result, GenerationResult)
                self.result = result
                self.status_var.set("Generation succeeded.")
                self.progress.stop()
                self.app.set_generation_running(False)
                self._sync_open_buttons()
            elif kind == "exception":
                exc = payload
                assert isinstance(exc, Exception)
                if not self._saw_error_event:
                    line = format_generation_event(
                        GenerationEvent("error", str(exc))
                    )
                    append_log(self.state, line)
                    lines.append(line)
                self.status_var.set("Generation failed.")
                self.progress.stop()
                self.app.set_generation_running(False)
                self._sync_open_buttons()
                messagebox.showerror("Generate", str(exc))

        if lines:
            self._append_lines(lines)

        if self.thread is not None and self.thread.is_alive():
            self.after(100, self._poll_events)

    def _render_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        if self.state.output_log:
            self.log.insert("end", "\n".join(self.state.output_log) + "\n")
            self.log.see("end")
        self.log.configure(state="disabled")

    def _append_lines(self, lines: list[str]) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", "\n".join(lines) + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _absolute_path(self, path: Path) -> Path:
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[4] / path
        return path

    def _set_open_buttons(self, datapack_enabled: bool, schematic_enabled: bool) -> None:
        self.open_datapack_button.configure(
            state="normal" if datapack_enabled else "disabled"
        )
        self.open_schematic_button.configure(
            state="normal" if schematic_enabled else "disabled"
        )

    def _sync_open_buttons(self) -> None:
        datapack_path = self.result.datapack_path if self.result is not None else None
        schematic_path = self.result.schematic_path if self.result is not None else None
        self._set_open_buttons(
            datapack_path is not None and datapack_path.exists(),
            schematic_path is not None and schematic_path.exists(),
        )

    def _open_folder(self, path: Path | None) -> None:
        if path is None:
            messagebox.showerror("Open folder", "No output path is available yet.")
            return
        path = self._absolute_path(path)
        folder = path.parent if path.is_file() else path
        if not folder.exists():
            messagebox.showerror("Open folder", f"Folder does not exist: {folder}")
            return
        try:
            os.startfile(folder)  # type: ignore[attr-defined]
        except OSError as exc:
            messagebox.showerror("Open folder", str(exc))

    def open_datapack_folder(self) -> None:
        path = self.result.datapack_path if self.result is not None else None
        self._open_folder(path)

    def open_schematic_folder(self) -> None:
        path = self.result.schematic_path if self.result is not None else None
        self._open_folder(path)

    def generate_another(self) -> None:
        self.app.generate_another()

    def is_complete(self) -> bool:
        return True

    def status_text(self) -> str:
        return self.status_var.get()
