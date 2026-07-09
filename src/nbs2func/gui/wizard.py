from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING

from nbs2func.config import load_config, save_config
from nbs2func.gui.state import (
    WizardState,
    create_default_state,
    create_state_from_config,
    load_input_song,
    validate_ready_to_generate,
)

if TYPE_CHECKING:
    from nbs2func.gui.steps.base import WizardStep


STEP_MODULES = (
    ("Input", "nbs2func.gui.steps.input_step", "InputStep"),
    ("Layout", "nbs2func.gui.steps.layout_step", "LayoutStep"),
    ("Layout Options", "nbs2func.gui.steps.layout_options_step", "LayoutOptionsStep"),
    ("Modules", "nbs2func.gui.steps.modules_step", "ModulesStep"),
    ("Output", "nbs2func.gui.steps.output_step", "OutputStep"),
    ("Summary", "nbs2func.gui.steps.summary_step", "SummaryStep"),
    ("Generate", "nbs2func.gui.steps.generate_step", "GenerateStep"),
)


class WizardApp(tk.Tk):
    def __init__(self, state: WizardState | None = None) -> None:
        super().__init__()
        self.title("nbs2func Preview Wizard")
        self.geometry("980x720")
        self.minsize(820, 560)

        self.state_data = state or create_default_state()
        self.current_index = 0
        self.max_unlocked_index = 0
        self.step_buttons: list[ttk.Button] = []
        self.steps: list[WizardStep] = []
        self.status_var = tk.StringVar(value="Select an NBS file to begin.")
        self.generate_unlocked = False
        self.generation_running = False

        self._configure_styles()
        self._build_menu()
        self._build_shell()
        self._load_steps()
        self._display_step(0)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.configure("Step.TButton", padding=(10, 6))
        style.configure("Current.Step.TButton", padding=(10, 6))

    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        self.file_menu = tk.Menu(menu, tearoff=False)
        self.file_menu.add_command(label="New", command=self.new_config)
        self.file_menu.add_command(label="Load Config", command=self.load_config_file)
        self.file_menu.add_command(label="Save Config", command=self.save_config_file)
        self.file_menu.add_command(label="Save Config As", command=self.save_config_as)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Exit", command=self.destroy)
        menu.add_cascade(label="File", menu=self.file_menu)

        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="About", command=self.show_about)
        menu.add_cascade(label="Help", menu=help_menu)
        self.config(menu=menu)

    def _build_shell(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self.step_bar = ttk.Frame(self, padding=(8, 8, 8, 4))
        self.step_bar.grid(row=0, column=0, sticky="ew")

        self.content = ttk.Frame(self, padding=(16, 10))
        self.content.grid(row=1, column=0, sticky="nsew")
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)

        status_frame = ttk.Frame(self, padding=(16, 6))
        status_frame.grid(row=2, column=0, sticky="ew")
        status_frame.columnconfigure(0, weight=1)
        ttk.Label(status_frame, textvariable=self.status_var, anchor="w").grid(
            row=0, column=0, sticky="ew"
        )

        nav = ttk.Frame(self, padding=(16, 8, 16, 14))
        nav.grid(row=3, column=0, sticky="ew")
        nav.columnconfigure(1, weight=1)
        self.back_button = ttk.Button(nav, text="< Back", command=self.back)
        self.back_button.grid(row=0, column=0, sticky="w")
        self.next_button = ttk.Button(nav, text="Next >", command=self.next)
        self.next_button.grid(row=0, column=2, sticky="e")

    def _load_steps(self) -> None:
        from importlib import import_module

        for index, (title, module_name, class_name) in enumerate(STEP_MODULES):
            button = ttk.Button(
                self.step_bar,
                text=f"{index + 1} {title}",
                style="Step.TButton",
                command=lambda i=index: self.on_step_button(i),
            )
            button.grid(row=0, column=index, padx=3, sticky="ew")
            self.step_bar.columnconfigure(index, weight=1)
            self.step_buttons.append(button)

            module = import_module(module_name)
            step_class = getattr(module, class_name)
            step = step_class(self.content, self)
            self.steps.append(step)

    def refresh(self) -> None:
        self.steps[self.current_index].on_show()
        self._refresh_buttons()
        self._refresh_status()

    def leave_current_step(self) -> bool:
        if self.generation_running:
            return False
        current = self.steps[self.current_index]
        try:
            ok = current.apply()
        except ValueError as exc:
            messagebox.showerror("Invalid value", str(exc))
            ok = False
        if not ok:
            self._refresh_status()
        return ok

    def show_step(self, index: int, *, apply_current: bool = True) -> None:
        if index < 0 or index >= len(self.steps):
            return
        if self.generation_running:
            messagebox.showinfo("Generation running", "Wait for generation to finish.")
            return
        if index > self.max_unlocked_index and not self._can_unlock_to(index):
            messagebox.showwarning(
                "Step locked",
                "Complete the previous required steps before opening this step.",
            )
            return
        if apply_current and index != self.current_index and not self.leave_current_step():
            return
        self._display_step(index)

    def _display_step(self, index: int) -> None:
        self.steps[self.current_index].grid_remove()
        self.current_index = index
        self.max_unlocked_index = max(self.max_unlocked_index, index)
        step = self.steps[index]
        step.grid(row=0, column=0, sticky="nsew")
        step.on_show()
        self._refresh_buttons()
        self._refresh_status()

    def on_step_button(self, index: int) -> None:
        if self.generation_running:
            return
        if index == len(self.steps) - 1 and not self.generate_unlocked:
            messagebox.showinfo(
                "Step locked",
                "Open Generate from the Summary step after reviewing the config.",
            )
            return
        if index <= self.max_unlocked_index or self._can_unlock_to(index):
            self.show_step(index)
        else:
            messagebox.showinfo(
                "Step locked",
                "This step is not available until the earlier steps are complete.",
            )

    def _can_unlock_to(self, target_index: int) -> bool:
        if target_index == len(self.steps) - 1:
            return self.generate_unlocked
        return all(self.steps[index].is_complete() for index in range(target_index))

    def _refresh_buttons(self) -> None:
        for index, button in enumerate(self.step_buttons):
            title = STEP_MODULES[index][0]
            if index == self.current_index:
                button.configure(text=f"> {index + 1} {title}")
                button.configure(style="Current.Step.TButton")
            elif index < self.current_index and self.steps[index].is_complete():
                button.configure(text=f"OK {index + 1} {title}")
                button.configure(style="Step.TButton")
            else:
                button.configure(text=f"{index + 1} {title}")
                button.configure(style="Step.TButton")
            if self.generation_running:
                button.state(["disabled"])
            elif index == len(self.steps) - 1 and not self.generate_unlocked:
                button.state(["disabled"])
            elif index <= self.max_unlocked_index or self._can_unlock_to(index):
                button.state(["!disabled"])
            else:
                button.state(["disabled"])

        self.back_button.state(
            ["!disabled"]
            if self.current_index > 0 and not self.generation_running
            else ["disabled"]
        )
        current = self.steps[self.current_index]
        if self.current_index == len(self.steps) - 2:
            self.next_button.configure(text="Generate", command=self.go_generate)
        elif self.current_index == len(self.steps) - 1:
            self.next_button.configure(
                text="Back to Summary",
                command=self.back_to_summary,
            )
        else:
            self.next_button.configure(text="Next >", command=self.next)
        self.next_button.state(
            ["!disabled"]
            if current.is_complete() and not self.generation_running
            else ["disabled"]
        )
        self._refresh_menu_state()

    def _refresh_status(self) -> None:
        self.status_var.set(self.steps[self.current_index].status_text())

    def set_help_text(self, text: str) -> None:
        self.status_var.set(text)

    def back(self) -> None:
        self.show_step(self.current_index - 1)

    def next(self) -> None:
        self.show_step(self.current_index + 1)

    def go_generate(self) -> None:
        if self.current_index != len(self.steps) - 2:
            return
        if not self.leave_current_step():
            return
        errors = validate_ready_to_generate(self.state_data)
        if errors:
            messagebox.showerror("Cannot generate", "\n".join(errors))
            return
        self.generate_unlocked = True
        self._display_step(len(self.steps) - 1)
        generate_step = self.steps[-1]
        if hasattr(generate_step, "start_generation"):
            generate_step.start_generation()

    def back_to_summary(self) -> None:
        self.show_step(len(self.steps) - 2)

    def new_config(self) -> None:
        if self.generation_running:
            return
        self.state_data = create_default_state()
        self.max_unlocked_index = 0
        self.generate_unlocked = False
        self._display_step(0)

    def load_config_file(self) -> None:
        if self.generation_running:
            return
        path = filedialog.askopenfilename(
            title="Load nbs2func config",
            filetypes=(("JSON config", "*.json"), ("All files", "*.*")),
        )
        if not path:
            return
        try:
            new_state = create_state_from_config(load_config(path), config_path=path)
            input_path = new_state.config.input_path
            if Path(input_path).is_file():
                try:
                    load_input_song(new_state, input_path)
                except Exception as exc:
                    new_state.input_song_summary = None
                    messagebox.showerror("Load Config", f"Could not read input: {exc}")
            self.state_data = new_state
        except (OSError, ValueError) as exc:
            messagebox.showerror("Load Config", str(exc))
            return
        self.max_unlocked_index = 1 if self.state_data.input_song_summary else 0
        self.generate_unlocked = False
        self._display_step(0)

    def save_config_file(self) -> None:
        if self.state_data.config_path is None:
            self.save_config_as()
            return
        if not self.leave_current_step():
            return
        self._save_to_path(self.state_data.config_path)

    def save_config_as(self) -> None:
        if not self.leave_current_step():
            return
        path = filedialog.asksaveasfilename(
            title="Save nbs2func config",
            defaultextension=".json",
            filetypes=(("JSON config", "*.json"), ("All files", "*.*")),
        )
        if not path:
            return
        self._save_to_path(path)
        self.state_data.config_path = path

    def _save_to_path(self, path: str | Path) -> None:
        try:
            save_config(self.state_data.config, path)
        except OSError as exc:
            messagebox.showerror("Save Config", str(exc))
            return
        self.status_var.set(f"Saved config: {path}")

    def show_about(self) -> None:
        messagebox.showinfo(
            "About nbs2func",
            "nbs2func v0.1.0-preview\nPreview wizard GUI for config-driven generation.",
        )

    def set_generation_running(self, running: bool) -> None:
        self.generation_running = running
        self._refresh_buttons()

    def generate_another(self) -> None:
        if self.generation_running:
            return
        self.state_data = create_default_state()
        self.max_unlocked_index = 0
        self.generate_unlocked = False
        self._display_step(0)

    def _refresh_menu_state(self) -> None:
        if not hasattr(self, "file_menu"):
            return
        state = "disabled" if self.generation_running else "normal"
        for index in range(4):
            self.file_menu.entryconfigure(index, state=state)
