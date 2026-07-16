from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from nbs2func.gui.helpers import (
    GUI_MINECRAFT_VERSION_CHOICES,
    NOTE_PRESETS,
    apply_track_based_gui_defaults,
    infer_note_profile,
    localized_direction_choices,
    localized_direction_value_to_display,
    parse_float,
    parse_int,
    validate_layout_options,
)
from nbs2func.config import config_from_dict, config_to_dict
from nbs2func.gui.state import update_config
from nbs2func.gui.steps.base import (
    ScrollableFrame,
    WizardStep,
    labeled_entry,
    labeled_option,
)


NOTE_ADVANCED_FIELDS = (
    ("max_candidates_per_emitter", "step.layout_options.field.max_candidates_per_emitter", "int"),
    ("retry_max_candidates_per_emitter", "step.layout_options.field.retry_max_candidates_per_emitter", "int"),
    ("max_candidate_y_layers", "step.layout_options.field.max_candidate_y_layers", "int"),
    ("max_candidate_lateral_positions", "step.layout_options.field.max_candidate_lateral_positions", "int"),
    ("radius_search_tolerance", "step.layout_options.field.radius_search_tolerance", "float"),
    ("preferred_depth_sign", "step.layout_options.field.preferred_depth_sign", "int"),
    ("depth_mirror_penalty", "step.layout_options.field.depth_mirror_penalty", "float"),
)


class LayoutOptionsStep(WizardStep):
    title_key = "step.layout_options.name"
    help_key = "step.layout_options.help"

    def __init__(self, parent, app) -> None:
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.vars: dict[str, tk.Variable] = {}
        self.field_labels: dict[str, str] = {}
        self.mode_label = tk.StringVar()
        self.profile_var = tk.StringVar(value="balanced")
        self.direction_choices: dict[str, str] = {}
        self.profile_choices: dict[str, str] = {}

        ttk.Label(self, textvariable=self.mode_label).grid(row=0, column=0, sticky="w")
        self.scroll = ScrollableFrame(self)
        self.scroll.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.form = self.scroll.inner
        self.form.columnconfigure(1, weight=1)

    def on_show(self) -> None:
        mode = self.state.config.layout_mode
        self.mode_label.set(
            self.app.tr(
                "step.layout_options.for_mode",
                mode=self.app.tr(f"step.layout.mode.{mode}"),
            )
        )
        if self.state.config.layout_mode == "note_based_stereo":
            self.state.note_based_profile = infer_note_profile(
                self.state.config,
                self.state.note_based_profile,
            )
            self._build_choice_maps()
            self.profile_var.set(self._display_for(self.profile_choices, self.state.note_based_profile))
        self._build_form()

    def _build_choice_maps(self) -> None:
        self.direction_choices = localized_direction_choices(self.app.tr)
        self.profile_choices = {
            self.app.tr(f"step.layout_options.profile.{value}"): value
            for value in ("safe", "balanced", "dense", "custom")
        }

    @staticmethod
    def _display_for(choices: dict[str, str], value: str) -> str:
        return next((label for label, canonical in choices.items() if canonical == value), value)

    def _var(self, field: str, var_type: type[tk.Variable] = tk.StringVar) -> tk.Variable:
        value = getattr(self.state.config, field)
        if field == "direction":
            value = localized_direction_value_to_display(str(value), self.app.tr)
        if var_type is tk.BooleanVar:
            variable = tk.BooleanVar(value=bool(value))
        else:
            variable = var_type(value="" if value is None else str(value))
        self.vars[field] = variable
        return variable

    def _remember_label(self, field: str, label: str) -> None:
        self.field_labels[field] = label

    def _entry(self, row: int, field: str, label: str) -> ttk.Entry:
        self._remember_label(field, label)
        help_key = HELP_KEYS_BY_FIELD.get(field)
        return labeled_entry(
            self.form,
            row,
            label,
            self._var(field),
            help_text=self.app.tr(help_key) if help_key else None,
            step=self,
        )

    def _build_form(self) -> None:
        for child in self.form.winfo_children():
            child.destroy()
        self.vars.clear()
        self.field_labels.clear()
        self._build_choice_maps()
        row = 0

        labeled_option(
            self.form,
            row,
            self.app.tr("step.layout_options.field.direction"),
            self._var("direction"),
            tuple(self.direction_choices),
            help_text=self.app.tr(HELP_KEYS_BY_FIELD["direction"]),
            step=self,
        )
        self._remember_label("direction", self.app.tr("step.layout_options.field.direction"))
        row += 1
        for field, label in (
            ("origin_x", "step.layout_options.field.origin_x"),
            ("origin_y", "step.layout_options.field.origin_y"),
            ("origin_z", "step.layout_options.field.origin_z"),
        ):
            self._entry(row, field, self.app.tr(label))
            row += 1
        labeled_option(
            self.form,
            row,
            self.app.tr("step.layout_options.field.minecraft_version"),
            self._var("minecraft_version"),
            GUI_MINECRAFT_VERSION_CHOICES,
            help_text=self.app.tr(HELP_KEYS_BY_FIELD["minecraft_version"]),
            step=self,
        )
        self._remember_label("minecraft_version", self.app.tr("step.layout_options.field.minecraft_version"))
        row += 1

        mode = self.state.config.layout_mode
        if mode == "basic_linear":
            self._entry(row, "track_id", self.app.tr("step.layout_options.field.track_id"))
        elif mode == "track_based_stereo":
            self._entry(row, "min_distance", self.app.tr("step.layout_options.field.min_distance"))
        elif mode == "note_based_stereo":
            combo = labeled_option(
                self.form,
                row,
                self.app.tr("step.layout_options.field.profile"),
                self.profile_var,
                tuple(self.profile_choices),
                help_text=self.app.tr(HELP_KEYS_BY_FIELD["note_profile"]),
                step=self,
            )
            combo.bind("<<ComboboxSelected>>", lambda _event: self._on_profile_change())
            row += 1
            readonly = self.profile_choices.get(self.profile_var.get()) != "custom"
            for field, label_key, _kind in NOTE_ADVANCED_FIELDS:
                entry = self._entry(row, field, self.app.tr(label_key))
                if readonly:
                    entry.configure(state="disabled")
                row += 1
            check = ttk.Checkbutton(
                self.form,
                text=self.app.tr("step.layout_options.depth_mirror"),
                variable=self._var("enable_depth_mirror_candidates", tk.BooleanVar),
            )
            self.register_help(check, self.app.tr(HELP_KEYS_BY_FIELD["enable_depth_mirror_candidates"]))
            if readonly:
                check.configure(state="disabled")
            check.grid(row=row, column=1, sticky="w", pady=3)

    def _on_profile_change(self) -> None:
        profile = self.profile_choices.get(self.profile_var.get(), "custom")
        self.state.note_based_profile = profile
        if profile in NOTE_PRESETS:
            update_config(self.state, NOTE_PRESETS[profile])
        self._build_form()
        self.app.refresh()

    def apply(self) -> bool:
        updates: dict[str, object] = {}
        int_fields = {
            "origin_x",
            "origin_y",
            "origin_z",
            "track_id",
            "max_candidates_per_emitter",
            "retry_max_candidates_per_emitter",
            "max_candidate_y_layers",
            "max_candidate_lateral_positions",
            "preferred_depth_sign",
        }
        float_fields = {
            "min_distance",
            "radius_search_tolerance",
            "depth_mirror_penalty",
        }
        bool_fields = {"enable_collision_resolver", "enable_depth_mirror_candidates"}
        for field, variable in self.vars.items():
            value = variable.get()
            label = self.field_labels.get(field, field)
            if field in bool_fields:
                updates[field] = bool(value)
            elif field == "direction":
                updates[field] = self.direction_choices.get(str(value), str(value))
            elif field == "track_id":
                updates[field] = parse_int(
                    str(value), label, allow_empty=True, translate=self.app.tr
                )
            elif field in int_fields:
                updates[field] = parse_int(
                    str(value),
                    label,
                    min_value=_INT_MIN_VALUES.get(field),
                    translate=self.app.tr,
                )
            elif field in float_fields:
                updates[field] = parse_float(
                    str(value),
                    label,
                    min_value=_FLOAT_MIN_VALUES.get(field),
                    translate=self.app.tr,
                )
            else:
                updates[field] = str(value)
        self.state.note_based_profile = self.profile_choices.get(
            self.profile_var.get(), "custom"
        )
        candidate = config_from_dict({**config_to_dict(self.state.config), **updates})
        if candidate.layout_mode == "track_based_stereo":
            candidate = apply_track_based_gui_defaults(candidate)
        errors = validate_layout_options(candidate, self.app.tr)
        if errors:
            raise ValueError("\n".join(errors))
        self.state.config = candidate
        return True

    def status_text(self) -> str:
        return self.app.tr(self.help_key)


HELP_KEYS_BY_FIELD = {
    field: f"step.layout_options.help.{field}"
    for field in (
        "direction", "origin_x", "origin_y", "origin_z", "minecraft_version",
        "track_id", "min_distance", "note_profile", "max_candidates_per_emitter",
        "retry_max_candidates_per_emitter", "max_candidate_y_layers",
        "max_candidate_lateral_positions", "radius_search_tolerance",
        "preferred_depth_sign", "depth_mirror_penalty",
        "enable_depth_mirror_candidates",
    )
}


_INT_MIN_VALUES = {
    "max_candidates_per_emitter": 1,
    "retry_max_candidates_per_emitter": 1,
    "max_candidate_y_layers": 1,
    "max_candidate_lateral_positions": 1,
}

_FLOAT_MIN_VALUES = {
    "min_distance": 0.0,
    "radius_search_tolerance": 0.0,
}
