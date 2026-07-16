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


def normalize_module_toggles(
    enable_starter_module: bool,
    enable_playback_assist: bool,
) -> tuple[bool, bool]:
    if not enable_starter_module:
        return False, False
    return True, bool(enable_playback_assist)


def module_int_fields_to_parse(
    *,
    enable_starter_module: bool,
    enable_playback_assist: bool,
) -> set[str]:
    fields = {"tempo_rate_decimals"}
    if enable_starter_module:
        fields.update(
            {
                "command_block_x",
                "command_block_y",
                "command_block_z",
            }
        )
    if enable_playback_assist:
        fields.update(
            {
                "command_module_origin_x",
                "command_module_origin_y",
                "command_module_origin_z",
            }
        )
    return fields


class ModulesStep(WizardStep):
    title_key = "step.modules.name"
    help_key = "step.modules.help"

    def __init__(self, parent, app) -> None:
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.vars: dict[str, tk.Variable] = {}
        self.field_labels: dict[str, str] = {}
        self.starter_widgets: list[tk.Widget] = []
        self.playback_widgets: list[tk.Widget] = []
        self.choice_maps: dict[str, dict[str, str]] = {}
        self.scroll = ScrollableFrame(self)
        self.scroll.grid(row=0, column=0, sticky="nsew")
        self.form = self.scroll.inner
        self.form.columnconfigure(0, weight=1)

    def on_show(self) -> None:
        self._apply_module_defaults()
        self._build_form()

    def _build_choice_maps(self) -> None:
        self.choice_maps = {
            "tempo_control_mode": {
                self.app.tr(f"step.modules.mode.{value}"): value
                for value in ("none", "report", "command")
            },
            "tempo_control_backend": {
                self.app.tr(f"step.modules.backend.{value}"): value
                for value in ("auto", "carpet", "vanilla")
            },
        }

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
        if field in self.choice_maps:
            value = next(
                (label for label, canonical in self.choice_maps[field].items() if canonical == value),
                value,
            )
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
            help_text=(
                self.app.tr(HELP_KEYS_BY_FIELD[field])
                if field in HELP_KEYS_BY_FIELD
                else None
            ),
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
        self._build_choice_maps()

        starter = ttk.LabelFrame(self.form, text=self.app.tr("step.modules.starter"), padding=10)
        starter.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        starter.columnconfigure(1, weight=1)
        starter_check = ttk.Checkbutton(
            starter,
            text=self.app.tr("step.modules.enable_starter"),
            variable=self._var("enable_starter_module", tk.BooleanVar),
            command=self._sync_module_controls,
        )
        starter_check.grid(row=0, column=1, sticky="w", pady=3)
        self.register_help(starter_check, self.app.tr(HELP_KEYS_BY_FIELD["enable_starter_module"]))
        for row, (field, label) in enumerate(
            (
                ("command_block_x", "step.modules.field.command_block_x"),
                ("command_block_y", "step.modules.field.command_block_y"),
                ("command_block_z", "step.modules.field.command_block_z"),
            ),
            start=1,
        ):
            self._entry(starter, row, field, self.app.tr(label), self.starter_widgets)

        playback = ttk.LabelFrame(self.form, text=self.app.tr("step.modules.playback"), padding=10)
        playback.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        playback.columnconfigure(1, weight=1)
        playback_check = ttk.Checkbutton(
            playback,
            text=self.app.tr("step.modules.enable_playback"),
            variable=self._var("enable_playback_assist", tk.BooleanVar),
            command=self._sync_module_controls,
        )
        self.playback_check = playback_check
        playback_check.grid(row=0, column=1, sticky="w", pady=3)
        self.register_help(playback_check, self.app.tr(HELP_KEYS_BY_FIELD["enable_playback_assist"]))
        row = 1
        for field, label in (
            ("playback_player_name", "step.modules.field.playback_player_name"),
            ("playback_vehicle_tag", "step.modules.field.playback_vehicle_tag"),
            ("command_module_origin_x", "step.modules.field.command_module_origin_x"),
            ("command_module_origin_y", "step.modules.field.command_module_origin_y"),
            ("command_module_origin_z", "step.modules.field.command_module_origin_z"),
        ):
            self._entry(playback, row, field, self.app.tr(label), self.playback_widgets)
            row += 1
        check = ttk.Checkbutton(
            playback,
            text=self.app.tr("step.modules.playback_buttons"),
            variable=self._var("generate_playback_buttons", tk.BooleanVar),
        )
        self.register_help(check, self.app.tr(HELP_KEYS_BY_FIELD["generate_playback_buttons"]))
        check.grid(row=row, column=1, sticky="w", pady=3)
        self.playback_widgets.append(check)

        tempo = ttk.LabelFrame(self.form, text=self.app.tr("step.modules.tempo"), padding=10)
        tempo.grid(row=2, column=0, sticky="ew")
        tempo.columnconfigure(1, weight=1)
        labeled_option(
            tempo,
            0,
            self.app.tr("step.modules.field.tempo_control_mode"),
            self._var("tempo_control_mode"),
            tuple(self.choice_maps["tempo_control_mode"]),
            help_text=self.app.tr(HELP_KEYS_BY_FIELD["tempo_control_mode"]),
            step=self,
        )
        labeled_option(
            tempo,
            1,
            self.app.tr("step.modules.field.tempo_control_backend"),
            self._var("tempo_control_backend"),
            tuple(self.choice_maps["tempo_control_backend"]),
            help_text=self.app.tr(HELP_KEYS_BY_FIELD["tempo_control_backend"]),
            step=self,
        )
        self._entry(tempo, 2, "tempo_rate_decimals", self.app.tr("step.modules.field.tempo_rate_decimals"))
        reset_check = ttk.Checkbutton(
            tempo,
            text=self.app.tr("step.modules.reset_tick_rate"),
            variable=self._var("reset_tick_rate_after_playback", tk.BooleanVar),
        )
        reset_check.grid(row=3, column=1, sticky="w", pady=3)
        self.register_help(reset_check, self.app.tr(HELP_KEYS_BY_FIELD["reset_tick_rate_after_playback"]))
        ttk.Label(
            tempo,
            text=self.app.tr("step.modules.tick_preview"),
        ).grid(row=4, column=1, sticky="w", pady=3)
        self._sync_module_controls()

    def _sync_module_controls(self) -> None:
        starter_enabled = bool(self.vars["enable_starter_module"].get())
        if not starter_enabled:
            self.vars["enable_playback_assist"].set(False)
        playback_enabled = starter_enabled and bool(
            self.vars["enable_playback_assist"].get()
        )
        starter_state = "normal" if starter_enabled else "disabled"
        playback_state = "normal" if playback_enabled else "disabled"
        self.playback_check.configure(
            state="normal" if starter_enabled else "disabled"
        )
        for widget in self.starter_widgets:
            widget.configure(state=starter_state)
        for widget in self.playback_widgets:
            widget.configure(state=playback_state)

    def apply(self) -> bool:
        starter_enabled, playback_enabled = normalize_module_toggles(
            bool(self.vars["enable_starter_module"].get()),
            bool(self.vars["enable_playback_assist"].get()),
        )
        if bool(self.vars["enable_playback_assist"].get()) and not starter_enabled:
            self.app.status_var.set(
                self.app.tr("validation.playback_requires_starter")
            )
        int_fields = module_int_fields_to_parse(
            enable_starter_module=starter_enabled,
            enable_playback_assist=playback_enabled,
        )
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
                if field == "enable_starter_module":
                    updates[field] = starter_enabled
                elif field == "enable_playback_assist":
                    updates[field] = playback_enabled
                else:
                    updates[field] = bool(value)
            elif field in int_fields:
                updates[field] = parse_int(
                    str(value),
                    self.field_labels.get(field, field),
                    allow_empty=field in optional_int_fields,
                    translate=self.app.tr,
                )
            elif field in self.choice_maps:
                updates[field] = self.choice_maps[field].get(str(value), str(value))
            elif field not in {
                "command_block_x",
                "command_block_y",
                "command_block_z",
                "command_module_origin_x",
                "command_module_origin_y",
                "command_module_origin_z",
            }:
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
        errors = validate_module_coordinates(self.state.config, self.app.tr)
        if errors:
            raise ValueError("\n".join(errors))
        return True

    def status_text(self) -> str:
        return self.app.tr(self.help_key)


HELP_KEYS_BY_FIELD = {
    field: f"step.modules.help.{field}"
    for field in (
        "enable_starter_module", "command_block_x", "command_block_y",
        "command_block_z", "enable_playback_assist", "playback_player_name",
        "playback_vehicle_tag", "command_module_origin_x",
        "command_module_origin_y", "command_module_origin_z",
        "generate_playback_buttons", "tempo_control_mode",
        "tempo_control_backend", "tempo_rate_decimals",
        "reset_tick_rate_after_playback",
    )
}
