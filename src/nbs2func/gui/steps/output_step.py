from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk

from nbs2func.gui.helpers import (
    OUTPUT_FORMAT_CHOICES,
    absolute_path_text,
    default_datapack_folder_name,
    default_schematic_name,
    fallback_output_format,
    is_output_format_selectable,
    modules_require_runtime_logic,
    normalize_gui_config,
)
from nbs2func.gui.state import set_output_format, update_config
from nbs2func.gui.steps.base import WizardStep, labeled_entry, labeled_option


OUTPUT_FORMAT_HELP = (
    "datapack generates mcfunction build logic; schem generates a WorldEdit "
    "schematic; both combines schematic blocks with mcfunction runtime logic."
)


class OutputStep(WizardStep):
    title = "Output"
    help_text = "Choose output backends and where generated files should be written."

    def __init__(self, parent, app) -> None:
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self.format_var = tk.StringVar()
        self.notice_var = tk.StringVar()
        self.vars: dict[str, tk.Variable] = {}
        self.format_buttons: dict[str, ttk.Radiobutton] = {}
        self.datapack_name_var = tk.StringVar()
        self.datapack_name_entry: ttk.Entry | None = None
        self.datapack_widgets: list[tk.Widget] = []
        self.schematic_widgets: list[tk.Widget] = []

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
            self.register_help(button, OUTPUT_FORMAT_HELP)
            self.format_buttons[value] = button
        ttk.Label(self, textvariable=self.notice_var, foreground="#8a5a00").grid(
            row=2, column=0, sticky="w"
        )

        self.form = ttk.Frame(self)
        self.form.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        self.form.columnconfigure(0, weight=1)

    def on_show(self) -> None:
        self.state.config = normalize_gui_config(self.state.config)
        output_format = fallback_output_format(self.state.config)
        self.format_var.set(output_format)
        if output_format != self.state.config.output_format:
            set_output_format(self.state, output_format)
        self._sync_format_buttons()
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
        self._build_form()
        self.app.refresh()

    def _build_form(self) -> None:
        for child in self.form.winfo_children():
            child.destroy()
        self.vars.clear()
        self.datapack_widgets.clear()
        self.schematic_widgets.clear()
        self.datapack_name_var.set(default_datapack_folder_name(self.state.config))

        datapack = ttk.LabelFrame(
            self.form,
            text="Datapack / mcfunction output",
            padding=10,
        )
        datapack.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        datapack.columnconfigure(1, weight=1)
        output_entry = labeled_entry(
            datapack,
            0,
            "Datapack output path",
            self._var("output"),
            help_text=(
                "Parent folder where the generated datapack folder will be written."
            ),
            step=self,
        )
        self.datapack_widgets.append(output_entry)
        output_button = ttk.Button(
            datapack,
            text="Browse...",
            command=self._browse_output,
        )
        output_button.grid(row=0, column=2, padx=(8, 0))
        self.register_help(output_button, "Choose the parent output folder.")
        self.datapack_widgets.append(output_button)
        name_entry = labeled_entry(
            datapack,
            1,
            "Datapack file/folder name",
            self.datapack_name_var,
            help_text=(
                "Datapack folder name is derived from the input NBS file name."
            ),
            step=self,
        )
        self.datapack_name_entry = name_entry
        name_entry.configure(state="disabled")
        self.datapack_widgets.append(name_entry)
        namespace = labeled_entry(
            datapack,
            2,
            "Namespace",
            self._var("function_namespace"),
            help_text="Function namespace used for generated mcfunction commands.",
            step=self,
        )
        self.datapack_widgets.append(namespace)

        schematic = ttk.LabelFrame(self.form, text="Schematic output", padding=10)
        schematic.grid(row=1, column=0, sticky="ew")
        schematic.columnconfigure(1, weight=1)
        schematic_output = labeled_entry(
            schematic,
            0,
            "Schematic output path",
            self._var("schematic_output"),
            help_text="Folder where the .schem file will be written.",
            step=self,
        )
        self.schematic_widgets.append(schematic_output)
        schematic_button = ttk.Button(
            schematic,
            text="Browse...",
            command=self._browse_schematic,
        )
        schematic_button.grid(row=0, column=2, padx=(8, 0))
        self.register_help(schematic_button, "Choose the schematic output folder.")
        self.schematic_widgets.append(schematic_button)
        schematic_name = labeled_entry(
            schematic,
            1,
            "Schematic file name",
            self._var("schematic_name"),
            help_text=(
                "Schematic file name defaults to the input NBS file name without "
                "the .nbs suffix."
            ),
            step=self,
        )
        self.schematic_widgets.append(schematic_name)
        origin_mode = labeled_option(
            schematic,
            2,
            "Schematic origin mode",
            self._var("schematic_origin_mode"),
            ("generation_origin", "min_corner"),
            help_text="Controls how world coordinates are converted into schematic coordinates.",
            step=self,
        )
        self.schematic_widgets.append(origin_mode)
        ttk.Label(
            schematic,
            text=(
                "For WorldEdit, place .schem files in: "
                ".minecraft/config/worldedit/schematics/"
            ),
        ).grid(row=3, column=1, sticky="w", pady=(8, 0))
        self._sync_group_states()

    def _sync_group_states(self) -> None:
        output_format = self.format_var.get()
        datapack_state = "normal" if output_format in {"datapack", "both"} else "disabled"
        schematic_state = "normal" if output_format in {"schem", "both"} else "disabled"
        for widget in self.datapack_widgets:
            widget.configure(state=datapack_state)
        for widget in self.schematic_widgets:
            widget.configure(state=schematic_state)
        if self.datapack_name_entry is not None:
            self.datapack_name_entry.configure(state="disabled")

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(title="Select datapack output folder")
        if path and "output" in self.vars:
            self.vars["output"].set(absolute_path_text(path))

    def _browse_schematic(self) -> None:
        path = filedialog.askdirectory(title="Select schematic output folder")
        if path and "schematic_output" in self.vars:
            self.vars["schematic_output"].set(absolute_path_text(path))

    def apply(self) -> bool:
        output_format = self.format_var.get()
        if not is_output_format_selectable(self.state.config, output_format):
            output_format = fallback_output_format(self.state.config)
            self.format_var.set(output_format)
        updates: dict[str, object] = {"output_format": output_format}
        for field, variable in self.vars.items():
            value = variable.get().strip()
            if field == "output":
                updates[field] = absolute_path_text(value)
            elif field == "schematic_output":
                updates[field] = absolute_path_text(value or self.state.config.output)
            elif field == "schematic_name":
                default_name = default_schematic_name(self.state.config)
                name = value or default_name
                updates[field] = name[:-6] if name.lower().endswith(".schem") else name
                self.state.schematic_name_user_modified = updates[field] != default_name
            else:
                updates[field] = value
        set_output_format(self.state, output_format)
        update_config(self.state, updates)
        self.state.config = normalize_gui_config(self.state.config)
        return True

    def is_complete(self) -> bool:
        return is_output_format_selectable(self.state.config, self.format_var.get())

    def status_text(self) -> str:
        return self.help_text
