from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk

from nbs2func.gui.helpers import (
    OUTPUT_FORMAT_CHOICES,
    fallback_output_format,
    is_output_format_selectable,
    modules_require_runtime_logic,
)
from nbs2func.gui.state import set_output_format, update_config
from nbs2func.gui.steps.base import WizardStep, labeled_entry, labeled_option


OUTPUT_DESCRIPTIONS = {
    "datapack": (
        "Generates a datapack / mcfunction build output.\n"
        "Supports starter module, playback assist, scoreboard, summon, and runtime commands.\n"
        "Datapack/mcfunction output will be generated under the output folder."
    ),
    "schem": (
        "Generates a .schem file for WorldEdit/Litematica.\n"
        "Contains the main redstone note block structure only.\n"
        "Starter and playback assist are not included."
    ),
    "both": (
        "Generates both:\n"
        "- .schem for placing blocks\n"
        "- mcfunction/datapack for runtime logic"
    ),
}


class OutputStep(WizardStep):
    title = "Output"

    def __init__(self, parent, app) -> None:
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self.format_var = tk.StringVar()
        self.description_var = tk.StringVar()
        self.notice_var = tk.StringVar()
        self.vars: dict[str, tk.Variable] = {}
        self.format_buttons: dict[str, ttk.Radiobutton] = {}

        ttk.Label(self, text="Output format").grid(row=0, column=0, sticky="w")
        choices = ttk.Frame(self)
        choices.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        for index, value in enumerate(OUTPUT_FORMAT_CHOICES):
            button = ttk.Radiobutton(
                choices,
                text=value,
                value=value,
                variable=self.format_var,
                command=self._on_format_change,
            )
            button.grid(row=0, column=index, sticky="w", padx=(0, 20))
            self.format_buttons[value] = button
        ttk.Label(self, textvariable=self.notice_var, foreground="#8a5a00").grid(
            row=2, column=0, sticky="w"
        )
        ttk.Label(self, textvariable=self.description_var, justify="left").grid(
            row=3, column=0, sticky="w", pady=(8, 10)
        )

        self.form = ttk.Frame(self)
        self.form.grid(row=4, column=0, sticky="ew")
        self.form.columnconfigure(1, weight=1)

    def on_show(self) -> None:
        output_format = fallback_output_format(self.state.config)
        self.format_var.set(output_format)
        if output_format != self.state.config.output_format:
            set_output_format(self.state, output_format)
        self._sync_format_buttons()
        self._render_description()
        self._build_form()

    def _var(self, field: str) -> tk.StringVar:
        value = getattr(self.state.config, field)
        variable = tk.StringVar(value="" if value is None else str(value))
        self.vars[field] = variable
        return variable

    def _sync_format_buttons(self) -> None:
        for value, button in self.format_buttons.items():
            state = (
                "normal"
                if is_output_format_selectable(self.state.config, value)
                else "disabled"
            )
            button.configure(state=state)
        if modules_require_runtime_logic(self.state.config):
            self.notice_var.set(
                "Schem-only is disabled because starter/playback assist requires "
                "mcfunction runtime logic. Use \"both\" if you want schematic blocks "
                "plus runtime commands."
            )
        else:
            self.notice_var.set("")

    def _on_format_change(self) -> None:
        if not is_output_format_selectable(self.state.config, self.format_var.get()):
            self.format_var.set(fallback_output_format(self.state.config))
        set_output_format(self.state, self.format_var.get())
        self._render_description()
        self._build_form()
        self.app.refresh()

    def _render_description(self) -> None:
        text = OUTPUT_DESCRIPTIONS.get(self.format_var.get(), "")
        if self.format_var.get() in {"schem", "both"}:
            text += (
                "\n\nFor WorldEdit, place .schem files in:\n"
                ".minecraft/config/worldedit/schematics/"
            )
        self.description_var.set(text)

    def _build_form(self) -> None:
        for child in self.form.winfo_children():
            child.destroy()
        self.vars.clear()
        row = 0
        labeled_entry(self.form, row, "Output folder", self._var("output"))
        ttk.Button(self.form, text="Browse...", command=self._browse_output).grid(
            row=row, column=2, padx=(8, 0)
        )
        row += 1
        labeled_entry(self.form, row, "Namespace", self._var("function_namespace"))
        row += 1

        if self.format_var.get() in {"schem", "both"}:
            ttk.Separator(self.form).grid(
                row=row,
                column=0,
                columnspan=3,
                sticky="ew",
                pady=8,
            )
            row += 1
            labeled_entry(self.form, row, "Schematic file name", self._var("schematic_name"))
            row += 1
            labeled_entry(
                self.form,
                row,
                "Schematic output path",
                self._var("schematic_output"),
            )
            ttk.Button(self.form, text="Browse...", command=self._browse_schematic).grid(
                row=row, column=2, padx=(8, 0)
            )
            row += 1
            labeled_option(
                self.form,
                row,
                "Schematic origin mode",
                self._var("schematic_origin_mode"),
                ("generation_origin", "min_corner"),
            )

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(title="Select output folder")
        if path and "output" in self.vars:
            self.vars["output"].set(path)

    def _browse_schematic(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Select schematic output",
            defaultextension=".schem",
            filetypes=(("Schematic", "*.schem"), ("All files", "*.*")),
        )
        if path and "schematic_output" in self.vars:
            self.vars["schematic_output"].set(path)

    def apply(self) -> bool:
        output_format = self.format_var.get()
        if not is_output_format_selectable(self.state.config, output_format):
            output_format = fallback_output_format(self.state.config)
            self.format_var.set(output_format)
        updates: dict[str, object] = {"output_format": output_format}
        for field, variable in self.vars.items():
            value = variable.get().strip()
            if field in {"schematic_output", "schematic_name"}:
                updates[field] = value or None
            else:
                updates[field] = value
        set_output_format(self.state, output_format)
        update_config(self.state, updates)
        return True

    def is_complete(self) -> bool:
        return is_output_format_selectable(self.state.config, self.format_var.get())

    def status_text(self) -> str:
        return f"Output format: {self.state.config.output_format}"
