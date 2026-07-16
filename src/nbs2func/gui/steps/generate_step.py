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
    monotonic_overall_progress,
)
from nbs2func.gui.helpers import resolve_gui_generation_config
from nbs2func.gui.i18n import Translator
from nbs2func.gui.state import append_generation_event, append_log, clear_log
from nbs2func.gui.steps.base import WizardStep


def format_generation_event(
    event: GenerationEvent,
    translator: Translator | None = None,
) -> str:
    labels = {
        "phase": "Phase",
        "notice": "Notice",
        "warning": "Warning",
        "output": "Output",
        "error": "Error",
        "done": "Done",
    }
    if translator is None:
        label = labels.get(event.kind, event.kind.title())
        message = event.message
    else:
        label = translator.gettext(f"generation.kind.{event.kind}")
        message = translator.event_message(
            event.message, event.i18n_key, event.i18n_params
        )
    if event.detail:
        return f"[{label}] {message} {event.detail}"
    return f"[{label}] {message}"


def format_progress_event(
    event: GenerationEvent,
    translator: Translator | None = None,
) -> str:
    message = (
        event.message
        if translator is None
        else translator.event_message(event.message, event.i18n_key, event.i18n_params)
    )
    if event.total == 0:
        if translator is not None:
            return translator.gettext("generation.skipped", message=message)
        return f"Skipped: {message}"
    if event.current is not None and event.total is not None:
        unit = event.unit
        if translator is not None and unit and translator.has_key(f"unit.{unit}"):
            unit = translator.gettext(f"unit.{unit}")
        suffix = f" {unit}" if unit else ""
        if translator is not None:
            return translator.gettext(
                "generation.progress",
                message=message,
                current=event.current,
                total=event.total,
                unit=suffix,
            )
        return f"{message}: {event.current} / {event.total}{suffix}"
    return message


def format_overall_progress(
    percent: float,
    translator: Translator | None = None,
) -> str:
    if translator is not None:
        return translator.gettext("step.generate.overall", percent=percent)
    return f"Overall progress: {percent:.0f}%"


def should_continue_polling(thread_alive: bool, queue_empty: bool) -> bool:
    return thread_alive or not queue_empty


class GenerateStep(WizardStep):
    title_key = "step.generate.name"

    def __init__(self, parent, app) -> None:
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(6, weight=1)
        self.status_var = tk.StringVar(value=self.app.tr("step.generate.ready"))
        self.overall_progress_var = tk.StringVar(
            value=format_overall_progress(0, self.app.translator)
        )
        self.current_stage_var = tk.StringVar(value=self.app.tr("step.generate.current_stage"))
        self.progress_detail_var = tk.StringVar(value="")
        self._overall_percent = 0.0
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.thread: threading.Thread | None = None
        self.result: GenerationResult | None = self.state.generation_result
        self._saw_error_event = False

        ttk.Label(self, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        ttk.Label(self, textvariable=self.overall_progress_var).grid(
            row=1,
            column=0,
            sticky="w",
            pady=(6, 0),
        )
        self.overall_progress = ttk.Progressbar(self, mode="determinate", maximum=100)
        self.overall_progress.grid(row=2, column=0, sticky="ew", pady=(2, 0))
        ttk.Label(self, textvariable=self.current_stage_var).grid(
            row=3,
            column=0,
            sticky="w",
            pady=(8, 0),
        )
        self.current_progress = ttk.Progressbar(self, mode="indeterminate")
        self.current_progress.grid(row=4, column=0, sticky="ew", pady=(2, 0))
        ttk.Label(self, textvariable=self.progress_detail_var).grid(
            row=5,
            column=0,
            sticky="w",
            pady=(4, 0),
        )

        log_frame = ttk.Frame(self)
        log_frame.grid(row=6, column=0, sticky="nsew", pady=(8, 8))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, height=24, wrap="word")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scrollbar.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        buttons = ttk.Frame(self)
        buttons.grid(row=7, column=0, sticky="ew")
        self.open_datapack_button = ttk.Button(
            buttons,
            text=self.app.tr("step.generate.open_datapack"),
            command=self.open_datapack_folder,
            state="disabled",
        )
        self.open_datapack_button.grid(row=0, column=0, sticky="w")
        self.open_schematic_button = ttk.Button(
            buttons,
            text=self.app.tr("step.generate.open_schematic"),
            command=self.open_schematic_folder,
            state="disabled",
        )
        self.open_schematic_button.grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Button(
            buttons,
            text=self.app.tr("step.generate.another"),
            command=self.generate_another,
        ).grid(row=0, column=2, sticky="w", padx=(8, 0))

    def on_show(self) -> None:
        if self.thread is not None and self.thread.is_alive():
            return
        self.result = self.state.generation_result
        self._render_log()
        self._sync_open_buttons()

    def start_generation(self) -> None:
        if self.thread is not None and self.thread.is_alive():
            return
        self.state.config = resolve_gui_generation_config(self.state.config)
        clear_log(self.state)
        self.result = None
        self.state.generation_result = None
        self._saw_error_event = False
        self._overall_percent = 0.0
        self.overall_progress_var.set(format_overall_progress(0.0, self.app.translator))
        self.overall_progress.configure(value=0)
        self.current_stage_var.set(self.app.tr("step.generate.current_stage"))
        self.progress_detail_var.set("")
        self._set_open_buttons(False, False)
        self.status_var.set(self.app.tr("step.generate.generating"))
        self._render_log()
        self.current_progress.configure(mode="indeterminate")
        self.current_progress.start()
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
            self.events.put(("event", GenerationEvent(
                "done", "Generation finished.", i18n_key="generation.done"
            )))
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
        last_progress: GenerationEvent | None = None
        terminal_event = False
        for kind, payload in collected:
            if kind == "event":
                event = payload
                assert isinstance(event, GenerationEvent)
                if event.kind == "progress":
                    last_progress = event
                    continue
                if event.kind == "error":
                    self._saw_error_event = True
                    terminal_event = True
                    self._reset_current_progress()
                elif event.kind == "phase":
                    self._reset_current_progress()
                elif event.kind == "done":
                    terminal_event = True
                    self._set_overall_percent(100.0)
                    self._set_finished_progress()
                line = format_generation_event(event, self.app.translator)
                append_generation_event(self.state, event)
                append_log(self.state, line)
                lines.append(line)
            elif kind == "result":
                result = payload
                assert isinstance(result, GenerationResult)
                self.result = result
                self.state.generation_result = result
                self.status_var.set(self.app.tr("step.generate.succeeded"))
                terminal_event = True
                self._set_finished_progress()
                self.app.set_generation_running(False)
                self._sync_open_buttons()
            elif kind == "exception":
                exc = payload
                assert isinstance(exc, Exception)
                if not self._saw_error_event:
                    error_event = GenerationEvent("error", str(exc))
                    line = format_generation_event(error_event, self.app.translator)
                    append_generation_event(self.state, error_event)
                    append_log(self.state, line)
                    lines.append(line)
                self.status_var.set(self.app.tr("step.generate.failed"))
                terminal_event = True
                self._reset_current_progress()
                self.app.set_generation_running(False)
                self._sync_open_buttons()
                messagebox.showerror(self.app.tr("dialog.generate.title"), str(exc))

        if lines:
            self._append_lines(lines)
        if last_progress is not None and not terminal_event:
            self._update_progress_detail(last_progress)

        thread_alive = self.thread is not None and self.thread.is_alive()
        if should_continue_polling(thread_alive, self.events.empty()):
            self.after(100, self._poll_events)

    def _update_progress_detail(self, event: GenerationEvent) -> None:
        if event.total == 0:
            return
        if event.overall_percent is not None:
            self._set_overall_percent(event.overall_percent)
        self.current_stage_var.set(self.app.tr("step.generate.current_stage"))
        self.progress_detail_var.set(self.app.tr(
            "step.generate.current",
            detail=format_progress_event(event, self.app.translator),
        ))
        if event.current is not None and event.total is not None and event.total > 0:
            self.current_progress.stop()
            self.current_progress.configure(
                mode="determinate",
                maximum=event.total,
                value=event.current,
            )
        else:
            if self.current_progress.cget("mode") != "indeterminate":
                self.current_progress.configure(mode="indeterminate")
                self.current_progress.start()

    def _reset_current_progress(self) -> None:
        self.current_stage_var.set(self.app.tr("step.generate.current_stage"))
        self.progress_detail_var.set("")
        self.current_progress.stop()
        self.current_progress.configure(mode="indeterminate", value=0)

    def _set_finished_progress(self) -> None:
        self.current_stage_var.set(self.app.tr("step.generate.finished_stage"))
        self.progress_detail_var.set(self.app.tr("step.generate.finished"))
        self.current_progress.stop()
        self.current_progress.configure(
            mode="determinate",
            maximum=100,
            value=100,
        )

    def _set_overall_percent(self, percent: float) -> None:
        self._overall_percent = monotonic_overall_progress(
            self._overall_percent,
            percent,
        )
        self.overall_progress_var.set(
            format_overall_progress(self._overall_percent, self.app.translator)
        )
        self.overall_progress.configure(value=self._overall_percent)

    def _render_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        if self.state.generation_events:
            lines = [
                format_generation_event(event, self.app.translator)
                for event in self.state.generation_events
            ]
            self.log.insert("end", "\n".join(lines) + "\n")
            self.log.see("end")
        elif self.state.output_log:
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
            messagebox.showerror(
                self.app.tr("dialog.open_folder.title"),
                self.app.tr("dialog.open_folder.no_path"),
            )
            return
        path = self._absolute_path(path)
        folder = path.parent if path.is_file() else path
        if not folder.exists():
            messagebox.showerror(
                self.app.tr("dialog.open_folder.title"),
                self.app.tr("dialog.open_folder.missing", path=folder),
            )
            return
        try:
            os.startfile(folder)  # type: ignore[attr-defined]
        except AttributeError:
            messagebox.showerror(
                self.app.tr("dialog.open_folder.title"),
                self.app.tr("dialog.open_folder.platform"),
            )
        except OSError as exc:
            messagebox.showerror(
                self.app.tr("dialog.open_folder.title"),
                self.app.tr("dialog.open_folder.error", error=exc),
            )

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
