from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from nbs2func.gui.helpers import parse_int
from nbs2func.gui.state import update_config
from nbs2func.gui.steps.base import (
    ScrollableFrame,
    WizardStep,
    labeled_entry,
    labeled_option,
)


class ModulesStep(WizardStep):
    title = "Modules"

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
        self._build_form()

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
        entry = labeled_entry(parent, row, label, self._var(field))
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
        ttk.Checkbutton(
            starter,
            text="Enable starter module",
            variable=self._var("enable_starter_module", tk.BooleanVar),
            command=self._sync_module_controls,
        ).grid(row=0, column=1, sticky="w", pady=3)
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
        ttk.Checkbutton(
            playback,
            text="Enable playback assist",
            variable=self._var("enable_playback_assist", tk.BooleanVar),
            command=self._sync_module_controls,
        ).grid(row=0, column=1, sticky="w", pady=3)
        row = 1
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
            self._entry(playback, row, field, label, self.playback_widgets)
            row += 1
        check = ttk.Checkbutton(
            playback,
            text="Playback buttons",
            variable=self._var("generate_playback_buttons", tk.BooleanVar),
        )
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
        )
        labeled_option(
            tempo,
            1,
            "Tempo backend",
            self._var("tempo_control_backend"),
            ("auto", "carpet", "vanilla"),
        )
        self._entry(tempo, 2, "tempo_rate_decimals", "Tempo rate decimals")
        self._entry(
            tempo,
            3,
            "game_ticks_per_song_tick",
            "Game ticks per song tick",
        )
        ttk.Checkbutton(
            tempo,
            text="Reset tick rate after playback",
            variable=self._var("reset_tick_rate_after_playback", tk.BooleanVar),
        ).grid(row=4, column=1, sticky="w", pady=3)
        ttk.Label(
            tempo,
            text="Recommended tick rate preview is printed during generation.",
        ).grid(row=5, column=1, sticky="w", pady=3)
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
            "music_start_x",
            "music_start_y",
            "music_start_z",
            "command_module_origin_x",
            "command_module_origin_y",
            "command_module_origin_z",
            "tempo_rate_decimals",
            "game_ticks_per_song_tick",
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
        update_config(self.state, updates)
        return True

    def status_text(self) -> str:
        config = self.state.config
        return (
            f"Modules: starter={config.enable_starter_module}, "
            f"playback_assist={config.enable_playback_assist}, "
            f"tempo={config.tempo_control_mode}"
        )
