from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from nbs2func.gui.state import update_config
from nbs2func.gui.steps.base import WizardStep, bool_state, labeled_entry, labeled_option


class ModulesStep(WizardStep):
    title = "Modules"

    def __init__(self, parent, app) -> None:
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self.vars: dict[str, tk.Variable] = {}
        self.notice_var = tk.StringVar()
        ttk.Label(self, textvariable=self.notice_var, justify="left").grid(
            row=0, column=0, sticky="w"
        )
        self.form = ttk.Frame(self)
        self.form.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.form.columnconfigure(1, weight=1)

    def on_show(self) -> None:
        self._build_form()

    def _var(self, field: str, kind: type[tk.Variable] = tk.StringVar) -> tk.Variable:
        value = getattr(self.state.config, field)
        if kind is tk.BooleanVar:
            variable = tk.BooleanVar(value=bool(value))
        else:
            variable = tk.StringVar(value="" if value is None else str(value))
        self.vars[field] = variable
        return variable

    def _build_form(self) -> None:
        for child in self.form.winfo_children():
            child.destroy()
        self.vars.clear()
        config = self.state.config
        schem_only = config.output_format == "schem"
        enabled_state = bool_state(not schem_only)
        if schem_only:
            self.notice_var.set(
                "Starter module and playback assist are not available in schem-only output.\n"
                "Schematic output contains the main structure only."
            )
        elif config.output_format == "both":
            self.notice_var.set(
                "The .schem file places blocks.\n"
                "The mcfunction output provides runtime logic."
            )
        else:
            self.notice_var.set("Configure optional datapack runtime modules.")

        row = 0
        ttk.Checkbutton(
            self.form,
            text="Enable starter module",
            variable=self._var("enable_starter_module", tk.BooleanVar),
            state=enabled_state,
        ).grid(row=row, column=1, sticky="w", pady=3)
        row += 1
        for field, label in (
            ("command_block_x", "Starter origin X"),
            ("command_block_y", "Starter origin Y"),
            ("command_block_z", "Starter origin Z"),
        ):
            labeled_entry(self.form, row, label, self._var(field))
            self.form.grid_slaves(row=row, column=1)[0].configure(state=enabled_state)
            row += 1

        ttk.Separator(self.form).grid(row=row, column=0, columnspan=2, sticky="ew", pady=8)
        row += 1
        ttk.Checkbutton(
            self.form,
            text="Enable playback assist",
            variable=self._var("enable_playback_assist", tk.BooleanVar),
            state=enabled_state,
        ).grid(row=row, column=1, sticky="w", pady=3)
        row += 1
        for field, label in (
            ("playback_player_name", "Playback player name"),
            ("playback_vehicle_tag", "Vehicle tag"),
            ("music_start_x", "Music start X"),
            ("music_start_y", "Music start Y"),
            ("music_start_z", "Music start Z"),
            ("command_module_origin_x", "Command module origin X"),
            ("command_module_origin_y", "Command module origin Y"),
            ("command_module_origin_z", "Command module origin Z"),
        ):
            labeled_entry(self.form, row, label, self._var(field))
            self.form.grid_slaves(row=row, column=1)[0].configure(state=enabled_state)
            row += 1
        ttk.Checkbutton(
            self.form,
            text="Playback buttons",
            variable=self._var("generate_playback_buttons", tk.BooleanVar),
            state=enabled_state,
        ).grid(row=row, column=1, sticky="w", pady=3)
        row += 1

        ttk.Separator(self.form).grid(row=row, column=0, columnspan=2, sticky="ew", pady=8)
        row += 1
        labeled_option(
            self.form,
            row,
            "Tempo control mode",
            self._var("tempo_control_mode"),
            ("none", "report", "command"),
        )
        row += 1
        labeled_option(
            self.form,
            row,
            "Tempo backend",
            self._var("tempo_control_backend"),
            ("auto", "carpet", "vanilla"),
        )
        row += 1
        ttk.Checkbutton(
            self.form,
            text="Reset tick rate after playback",
            variable=self._var("reset_tick_rate_after_playback", tk.BooleanVar),
        ).grid(row=row, column=1, sticky="w", pady=3)
        row += 1
        ttk.Label(
            self.form,
            text="Recommended tick rate preview is printed during generation.",
        ).grid(row=row, column=1, sticky="w", pady=3)

    def apply(self) -> bool:
        int_fields = {
            "command_block_x",
            "command_block_y",
            "command_block_z",
            "music_start_x",
            "music_start_y",
            "music_start_z",
            "command_module_origin_x",
            "command_module_origin_y",
            "command_module_origin_z",
        }
        bool_fields = {
            "enable_starter_module",
            "enable_playback_assist",
            "generate_playback_buttons",
            "reset_tick_rate_after_playback",
        }
        updates: dict[str, object] = {}
        for field, variable in self.vars.items():
            value = variable.get()
            if field in bool_fields:
                updates[field] = bool(value)
            elif field in int_fields:
                updates[field] = None if value == "" else int(value)
            else:
                updates[field] = str(value)
        if self.state.config.output_format == "schem":
            updates["enable_starter_module"] = False
            updates["enable_playback_assist"] = False
        update_config(self.state, updates)
        return True

    def status_text(self) -> str:
        config = self.state.config
        return (
            f"Modules: starter={config.enable_starter_module}, "
            f"playback_assist={config.enable_playback_assist}, "
            f"tempo={config.tempo_control_mode}"
        )
