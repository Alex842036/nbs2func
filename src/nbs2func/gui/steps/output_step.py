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


DATAPACK_BUILD_STYLE_CHOICES = ("simple_chain", "player_tp")


def output_datapack_controls_enabled(output_format: str) -> bool:
    return output_format in {"datapack", "both"}


class OutputStep(WizardStep):
    title_key = "step.output.name"
    help_key = "step.output.help"

    def __init__(self, parent, app) -> None:
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self.format_var = tk.StringVar()
        self.notice_var = tk.StringVar()
        self.vars: dict[str, tk.Variable] = {}
        self.format_buttons: dict[str, ttk.Radiobutton] = {}
        self.datapack_name_var = tk.StringVar()
        self.build_style_var = tk.StringVar(value="player_tp")
        self.datapack_name_entry: ttk.Entry | None = None
        self.datapack_widgets: list[tk.Widget] = []
        self.schematic_widgets: list[tk.Widget] = []
        self.origin_mode_choices: dict[str, str] = {}

        ttk.Label(self, text=self.app.tr("step.output.heading")).grid(row=0, column=0, sticky="w")
        choices = ttk.Frame(self)
        choices.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        for index, value in enumerate(OUTPUT_FORMAT_CHOICES):
            button = ttk.Radiobutton(
                choices,
                text=self.app.tr(f"step.output.format.{value}"),
                value=value,
                variable=self.format_var,
                command=self._on_format_change,
            )
            button.grid(row=0, column=index, sticky="w", padx=(0, 20))
            self.register_help(button, self.app.tr("step.output.format_help"))
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

    def _var(
        self,
        field: str,
        kind: type[tk.Variable] = tk.StringVar,
    ) -> tk.Variable:
        value = getattr(self.state.config, field)
        if field == "schematic_origin_mode" and self.origin_mode_choices:
            value = next(
                (label for label, canonical in self.origin_mode_choices.items() if canonical == value),
                value,
            )
        if kind is tk.BooleanVar:
            variable = tk.BooleanVar(value=bool(value))
        else:
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
            self.notice_var.set(self.app.tr("step.output.schem_disabled"))
        else:
            self.notice_var.set("")

    def _on_format_change(self) -> None:
        if not is_output_format_selectable(self.state.config, self.format_var.get()):
            self.format_var.set(fallback_output_format(self.state.config))
        set_output_format(self.state, self.format_var.get())
        values = {field: variable.get() for field, variable in self.vars.items()}
        datapack_name = self.datapack_name_var.get()
        build_style = self.build_style_var.get()
        self._build_form(values)
        self.datapack_name_var.set(datapack_name)
        self.build_style_var.set(build_style)
        self._sync_format_buttons()
        self.app._refresh_buttons()
        self.app._refresh_status()

    def _build_form(self, preserved_values: dict[str, object] | None = None) -> None:
        for child in self.form.winfo_children():
            child.destroy()
        self.vars.clear()
        self.datapack_widgets.clear()
        self.schematic_widgets.clear()
        self.origin_mode_choices = {
            self.app.tr(f"step.output.origin_mode.{value}"): value
            for value in ("generation_origin", "min_corner")
        }
        if (
            not self.state.datapack_name_user_modified
            and self.state.datapack_name in {"", default_datapack_folder_name(self.state.config)}
        ):
            self.state.datapack_name = default_datapack_folder_name(self.state.config)
        self.datapack_name_var.set(self.state.datapack_name)

        datapack = ttk.LabelFrame(
            self.form,
            text=self.app.tr("step.output.datapack_group"),
            padding=10,
        )
        datapack.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        datapack.columnconfigure(1, weight=1)
        output_entry = labeled_entry(
            datapack,
            0,
            self.app.tr("step.output.field.datapack_path"),
            self._var("output"),
            help_text=self.app.tr("step.output.help.datapack_path"),
            step=self,
        )
        self.datapack_widgets.append(output_entry)
        output_button = ttk.Button(
            datapack,
            text=self.app.tr("common.browse"),
            command=self._browse_output,
        )
        output_button.grid(row=0, column=2, padx=(8, 0))
        self.register_help(output_button, self.app.tr("step.output.help.browse_datapack"))
        self.datapack_widgets.append(output_button)
        name_entry = labeled_entry(
            datapack,
            1,
            self.app.tr("step.output.field.datapack_name"),
            self.datapack_name_var,
            help_text=self.app.tr("step.output.help.datapack_name"),
            step=self,
        )
        self.datapack_name_entry = name_entry
        self.datapack_widgets.append(name_entry)
        namespace = labeled_entry(
            datapack,
            2,
            self.app.tr("step.output.field.namespace"),
            self._var("function_namespace"),
            help_text=self.app.tr("step.output.help.namespace"),
            step=self,
        )
        self.datapack_widgets.append(namespace)

        build_style = ttk.LabelFrame(
            datapack,
            text=self.app.tr("step.output.build_style"),
            padding=8,
        )
        build_style.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        build_style.columnconfigure(1, weight=1)
        self.build_style_var.set(self.state.config.datapack_build_style)
        for row, value in enumerate(DATAPACK_BUILD_STYLE_CHOICES):
            radio = ttk.Radiobutton(
                build_style,
                text=self.app.tr(f"step.output.build_style.{value}"),
                value=value,
                variable=self.build_style_var,
            )
            radio.grid(row=row * 2, column=1, sticky="w", pady=(3, 0))
            self.register_help(radio, self.app.tr(f"step.output.build_help.{value}"))
            self.datapack_widgets.append(radio)
            label = ttk.Label(
                build_style,
                text=self.app.tr(f"step.output.build_help.{value}"),
                wraplength=600,
            )
            label.grid(row=row * 2 + 1, column=1, sticky="w", pady=(0, 8))
            self.datapack_widgets.append(label)

        schematic = ttk.LabelFrame(self.form, text=self.app.tr("step.output.schematic_group"), padding=10)
        schematic.grid(row=1, column=0, sticky="ew")
        schematic.columnconfigure(1, weight=1)
        schematic_output = labeled_entry(
            schematic,
            0,
            self.app.tr("step.output.field.schematic_path"),
            self._var("schematic_output"),
            help_text=self.app.tr("step.output.help.schematic_path"),
            step=self,
        )
        self.schematic_widgets.append(schematic_output)
        schematic_button = ttk.Button(
            schematic,
            text=self.app.tr("common.browse"),
            command=self._browse_schematic,
        )
        schematic_button.grid(row=0, column=2, padx=(8, 0))
        self.register_help(schematic_button, self.app.tr("step.output.help.browse_schematic"))
        self.schematic_widgets.append(schematic_button)
        schematic_name = labeled_entry(
            schematic,
            1,
            self.app.tr("step.output.field.schematic_name"),
            self._var("schematic_name"),
            help_text=self.app.tr("step.output.help.schematic_name"),
            step=self,
        )
        self.schematic_widgets.append(schematic_name)
        origin_mode = labeled_option(
            schematic,
            2,
            self.app.tr("step.output.field.origin_mode"),
            self._var("schematic_origin_mode"),
            tuple(self.origin_mode_choices),
            help_text=self.app.tr("step.output.help.origin_mode"),
            step=self,
        )
        self.schematic_widgets.append(origin_mode)
        ttk.Label(
            schematic,
            text=self.app.tr("step.output.worldedit_hint"),
        ).grid(row=3, column=1, sticky="w", pady=(8, 0))
        if preserved_values:
            for field, value in preserved_values.items():
                if field in self.vars:
                    self.vars[field].set(value)
        self._sync_group_states()

    def _sync_group_states(self) -> None:
        output_format = self.format_var.get()
        datapack_state = (
            "normal" if output_datapack_controls_enabled(output_format) else "disabled"
        )
        schematic_state = "normal" if output_format in {"schem", "both"} else "disabled"
        for widget in self.datapack_widgets:
            widget.configure(state=datapack_state)
        for widget in self.schematic_widgets:
            widget.configure(state=schematic_state)
        if self.datapack_name_entry is not None:
            self.datapack_name_entry.configure(state=datapack_state)

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(title=self.app.tr("dialog.select_datapack_folder.title"))
        if path and "output" in self.vars:
            self.vars["output"].set(absolute_path_text(path))

    def _browse_schematic(self) -> None:
        path = filedialog.askdirectory(title=self.app.tr("dialog.select_schematic_folder.title"))
        if path and "schematic_output" in self.vars:
            self.vars["schematic_output"].set(absolute_path_text(path))

    def apply(self) -> bool:
        output_format = self.format_var.get()
        if not is_output_format_selectable(self.state.config, output_format):
            output_format = fallback_output_format(self.state.config)
            self.format_var.set(output_format)
        updates: dict[str, object] = {"output_format": output_format}
        default_datapack_name = default_datapack_folder_name(self.state.config)
        self.state.datapack_name = self.datapack_name_var.get().strip() or default_datapack_name
        self.state.datapack_name_user_modified = (
            self.state.datapack_name != default_datapack_name
        )
        updates["datapack_name"] = self.state.datapack_name
        if output_datapack_controls_enabled(output_format):
            updates["datapack_build_style"] = self.build_style_var.get()
        for field, variable in self.vars.items():
            raw_value = variable.get()
            value = str(raw_value).strip()
            if field == "output":
                updates[field] = absolute_path_text(value)
            elif field == "schematic_output":
                updates[field] = absolute_path_text(value or self.state.config.output)
            elif field == "schematic_name":
                default_name = default_schematic_name(self.state.config)
                name = value or default_name
                updates[field] = name[:-6] if name.lower().endswith(".schem") else name
                self.state.schematic_name_user_modified = updates[field] != default_name
            elif field == "schematic_origin_mode":
                updates[field] = self.origin_mode_choices.get(value, value)
            else:
                updates[field] = value
        set_output_format(self.state, output_format)
        update_config(self.state, updates)
        self.state.config = normalize_gui_config(self.state.config)
        return True

    def is_complete(self) -> bool:
        return is_output_format_selectable(
            self.state.config,
            self.state.config.output_format,
        )

    def status_text(self) -> str:
        return self.app.tr(self.help_key)
