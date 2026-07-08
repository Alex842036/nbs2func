from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from nbs2func.gui.helpers import (
    parse_int,
    resolve_gui_generation_config,
    resolved_command_module_origin,
    resolved_starter_origin,
    validate_module_coordinates,
)
from nbs2func.gui.state import update_config
from nbs2func.gui.steps.base import (
    ScrollableFrame,
    WizardStep,
    labeled_entry,
    labeled_option,
)


class ModulesStep(WizardStep):
    title = "Modules"
    help_text = "Configure optional runtime modules and tempo commands."

    def __init__(self, parent, app) -> None:
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.vars: dict[str, tk.Variable] = {}
        self.field_labels: dict[str, str] = {}
        self.starter_widgets: list[tk.Widget] = []
        self.playback_widgets: list[tk.Widget] = []
        self.scroll = ScrollableFrame(self)
        self.scroll.grid(row=0, column=0, sticky="nsew")
        self.form = self.scroll.inner
        self.form.columnconfigure(0, weight=1)

    def on_show(self) -> None:
        self._apply_module_defaults()
        self._build_form()

    def _apply_module_defaults(self) -> None:
        updates: dict[str, object] = {}
        if not self.state.starter_origin_user_modified:
            starter = resolved_starter_origin(self.state.config)
            updates.update(
                {
                    "command_block_x": starter[0],
                    "command_block_y": starter[1],
                    "command_block_z": starter[2],
                }
            )
        if updates:
            update_config(self.state, updates)
        if not self.state.command_module_origin_user_modified:
            command = resolved_command_module_origin(
                self.state.config,
                use_existing=False,
            )
            update_config(
                self.state,
                command_module_origin_x=command[0],
                command_module_origin_y=command[1],
                command_module_origin_z=command[2],
            )

    def _var(self, field: str, kind: type[tk.Variable] = tk.StringVar) -> tk.Variable:
        value = getattr(self.state.config, field)
        if kind is tk.BooleanVar:
            variable = tk.BooleanVar(value=bool(value))
        else:
            variable = tk.StringVar(value="" if value is None else str(value))
        self.vars[field] = variable
        return variable

    def _entry(
        self,
        parent: tk.Widget,
        row: int,
        field: str,
        label: str,
        widgets: list[tk.Widget] | None = None,
    ) -> None:
        self.field_labels[field] = label
        entry = labeled_entry(
            parent,
            row,
            label,
            self._var(field),
            help_text=HELP_TEXT_BY_FIELD.get(field),
            step=self,
        )
        if widgets is not None:
            widgets.append(entry)

    def _build_form(self) -> None:
        for child in self.form.winfo_children():
            child.destroy()
        self.vars.clear()
        self.field_labels.clear()
        self.starter_widgets.clear()
        self.playback_widgets.clear()

        starter = ttk.LabelFrame(self.form, text="Starter Module", padding=10)
        starter.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        starter.columnconfigure(1, weight=1)
        starter_check = ttk.Checkbutton(
            starter,
            text="Enable starter module",
            variable=self._var("enable_starter_module", tk.BooleanVar),
            command=self._sync_module_controls,
        )
        starter_check.grid(row=0, column=1, sticky="w", pady=3)
        self.register_help(starter_check, HELP_TEXT_BY_FIELD["enable_starter_module"])
        for row, (field, label) in enumerate(
            (
                ("command_block_x", "Starter origin X"),
                ("command_block_y", "Starter origin Y"),
                ("command_block_z", "Starter origin Z"),
            ),
            start=1,
        ):
            self._entry(starter, row, field, label, self.starter_widgets)

        playback = ttk.LabelFrame(self.form, text="Playback Assist", padding=10)
        playback.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        playback.columnconfigure(1, weight=1)
        playback_check = ttk.Checkbutton(
            playback,
            text="Enable playback assist",
            variable=self._var("enable_playback_assist", tk.BooleanVar),
            command=self._sync_module_controls,
        )
        playback_check.grid(row=0, column=1, sticky="w", pady=3)
        self.register_help(playback_check, HELP_TEXT_BY_FIELD["enable_playback_assist"])
        row = 1
        for field, label in (
            ("playback_player_name", "Playback player name"),
            ("playback_vehicle_tag", "Vehicle tag"),
            ("command_module_origin_x", "Command module origin X"),
            ("command_module_origin_y", "Command module origin Y"),
            ("command_module_origin_z", "Command module origin Z"),
        ):
            self._entry(playback, row, field, label, self.playback_widgets)
            row += 1
        check = ttk.Checkbutton(
            playback,
            text="Playback buttons",
            variable=self._var("generate_playback_buttons", tk.BooleanVar),
        )
        self.register_help(check, HELP_TEXT_BY_FIELD["generate_playback_buttons"])
        check.grid(row=row, column=1, sticky="w", pady=3)
        self.playback_widgets.append(check)

        tempo = ttk.LabelFrame(self.form, text="Tempo Control", padding=10)
        tempo.grid(row=2, column=0, sticky="ew")
        tempo.columnconfigure(1, weight=1)
        labeled_option(
            tempo,
            0,
            "Tempo control mode",
            self._var("tempo_control_mode"),
            ("none", "report", "command"),
            help_text=HELP_TEXT_BY_FIELD["tempo_control_mode"],
            step=self,
        )
        labeled_option(
            tempo,
            1,
            "Tempo backend",
            self._var("tempo_control_backend"),
            ("auto", "carpet", "vanilla"),
            help_text=HELP_TEXT_BY_FIELD["tempo_control_backend"],
            step=self,
        )
        self._entry(tempo, 2, "tempo_rate_decimals", "Tempo rate decimals")
        reset_check = ttk.Checkbutton(
            tempo,
            text="Reset tick rate after playback",
            variable=self._var("reset_tick_rate_after_playback", tk.BooleanVar),
        )
        reset_check.grid(row=3, column=1, sticky="w", pady=3)
        self.register_help(reset_check, HELP_TEXT_BY_FIELD["reset_tick_rate_after_playback"])
        ttk.Label(
            tempo,
            text="Recommended tick rate preview is printed during generation.",
        ).grid(row=4, column=1, sticky="w", pady=3)
        self._sync_module_controls()

    def _sync_module_controls(self) -> None:
        starter_state = (
            "normal" if bool(self.vars["enable_starter_module"].get()) else "disabled"
        )
        playback_state = (
            "normal" if bool(self.vars["enable_playback_assist"].get()) else "disabled"
        )
        for widget in self.starter_widgets:
            widget.configure(state=starter_state)
        for widget in self.playback_widgets:
            widget.configure(state=playback_state)

    def apply(self) -> bool:
        int_fields = {
            "command_block_x",
            "command_block_y",
            "command_block_z",
            "command_module_origin_x",
            "command_module_origin_y",
            "command_module_origin_z",
            "tempo_rate_decimals",
        }
        optional_int_fields = {
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
        previous_starter = (
            self.state.config.command_block_x,
            self.state.config.command_block_y,
            self.state.config.command_block_z,
        )
        previous_command = (
            self.state.config.command_module_origin_x,
            self.state.config.command_module_origin_y,
            self.state.config.command_module_origin_z,
        )
        for field, variable in self.vars.items():
            value = variable.get()
            if field in bool_fields:
                updates[field] = bool(value)
            elif field in int_fields:
                updates[field] = parse_int(
                    str(value),
                    self.field_labels.get(field, field),
                    allow_empty=field in optional_int_fields,
                )
            else:
                updates[field] = str(value)
        updates["game_ticks_per_song_tick"] = 4
        update_config(self.state, updates)
        current_starter = (
            self.state.config.command_block_x,
            self.state.config.command_block_y,
            self.state.config.command_block_z,
        )
        current_command = (
            self.state.config.command_module_origin_x,
            self.state.config.command_module_origin_y,
            self.state.config.command_module_origin_z,
        )
        if current_starter != previous_starter:
            self.state.starter_origin_user_modified = True
        if current_command != previous_command:
            self.state.command_module_origin_user_modified = True
        self.state.config = resolve_gui_generation_config(self.state.config)
        errors = validate_module_coordinates(self.state.config)
        if errors:
            raise ValueError("\n".join(errors))
        return True

    def status_text(self) -> str:
        return self.help_text


HELP_TEXT_BY_FIELD = {
    "enable_starter_module": "Starter module creates a synchronized start command block for the generated music.",
    "command_block_x": "Starter origin is the start command block X. It must be behind the layout origin for the selected direction.",
    "command_block_y": "Starter origin Y is the height of the start command block.",
    "command_block_z": "Starter origin is the start command block Z. It must be behind the layout origin for the selected direction.",
    "enable_playback_assist": "Playback assist adds minecart runtime logic for starting playback.",
    "playback_player_name": "Player name used by playback assist scoreboard commands.",
    "playback_vehicle_tag": "Entity tag assigned to the playback minecart.",
    "command_module_origin_x": "Command module origin is the playback assist command block area X. It must be further behind starter origin.",
    "command_module_origin_y": "Command module origin Y is the height of playback assist command blocks.",
    "command_module_origin_z": "Command module origin is the playback assist command block area Z. It must be further behind starter origin.",
    "generate_playback_buttons": "Generate prepare/start buttons next to playback assist command blocks.",
    "tempo_control_mode": "Tempo control can report or emit tick-rate commands without changing the tempo formula.",
    "tempo_control_backend": "Tempo backend selects Carpet or vanilla tick-rate command syntax where supported.",
    "tempo_rate_decimals": "Decimal places used when formatting recommended tick-rate commands.",
    "reset_tick_rate_after_playback": "Generate a reset command so tick rate returns to normal after playback.",
}
