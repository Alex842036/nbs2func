from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk

from nbs2func.gui.state import set_output_format, update_config
from nbs2func.gui.steps.base import WizardStep, labeled_entry, labeled_option


OUTPUT_DESCRIPTIONS = {
    "datapack": (
        "Generates a datapack / mcfunction build output.\n"
        "Supports starter module, playback assist, scoreboard, summon, and runtime commands."
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
        self.vars: dict[str, tk.Variable] = {}

        ttk.Label(self, text="Output format").grid(row=0, column=0, sticky="w")
        choices = ttk.Frame(self)
        choices.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        for index, value in enumerate(("datapack", "schem", "both")):
            ttk.Radiobutton(
                choices,
                text=value,
                value=value,
                variable=self.format_var,
                command=self._on_format_change,
            ).grid(row=0, column=index, sticky="w", padx=(0, 20))
        ttk.Label(self, textvariable=self.description_var, justify="left").grid(
            row=2, column=0, sticky="w", pady=(0, 10)
        )

        self.form = ttk.Frame(self)
        self.form.grid(row=3, column=0, sticky="ew")
        self.form.columnconfigure(1, weight=1)

    def on_show(self) -> None:
        self.format_var.set(self.state.config.output_format)
        self._render_description()
        self._build_form()

    def _var(self, field: str) -> tk.StringVar:
        value = getattr(self.state.config, field)
        variable = tk.StringVar(value="" if value is None else str(value))
        self.vars[field] = variable
        return variable

    def _on_format_change(self) -> None:
        set_output_format(self.state, self.format_var.get())
        self._render_description()
        self._build_form()
        self.app.refresh()

    def _render_description(self) -> None:
        text = OUTPUT_DESCRIPTIONS.get(self.format_var.get(), "")
        if self.format_var.get() in {"schem", "both"}:
            text += (
                "\n\nFor WorldEdit 1.16.5, place .schem files in:\n"
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
        labeled_entry(self.form, row, "Output name / schematic name", self._var("schematic_name"))
        row += 1
        labeled_entry(self.form, row, "Namespace", self._var("function_namespace"))
        row += 1
        labeled_entry(self.form, row, "Schematic output path / name", self._var("schematic_output"))
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
        updates: dict[str, object] = {
            "output_format": self.format_var.get(),
        }
        for field, variable in self.vars.items():
            value = variable.get().strip()
            updates[field] = value or None if field in {"schematic_output", "schematic_name"} else value
        set_output_format(self.state, self.format_var.get())
        update_config(self.state, updates)
        return True

    def is_complete(self) -> bool:
        return self.format_var.get() in OUTPUT_DESCRIPTIONS

    def status_text(self) -> str:
        return f"Output format: {self.state.config.output_format}"
