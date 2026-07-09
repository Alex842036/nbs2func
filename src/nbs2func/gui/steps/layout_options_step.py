from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from nbs2func.gui.helpers import (
    DIRECTION_DISPLAY_TO_VALUE,
    GUI_MINECRAFT_VERSION_CHOICES,
    NOTE_PRESETS,
    apply_track_based_gui_defaults,
    direction_display_to_value,
    direction_value_to_display,
    infer_note_profile,
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
    ("max_candidates_per_emitter", "Max candidates per emitter", "int"),
    ("retry_max_candidates_per_emitter", "Retry max candidates per emitter", "int"),
    ("max_candidate_y_layers", "Max candidate Y layers", "int"),
    ("max_candidate_lateral_positions", "Max candidate lateral positions", "int"),
    ("radius_search_tolerance", "Radius search tolerance", "float"),
    ("preferred_depth_sign", "Preferred depth sign", "int"),
    ("depth_mirror_penalty", "Depth mirror penalty", "float"),
)


class LayoutOptionsStep(WizardStep):
    title = "Layout Options"
    help_text = "Set placement direction, origin, Minecraft version, and mode-specific layout options."

    def __init__(self, parent, app) -> None:
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.vars: dict[str, tk.Variable] = {}
        self.field_labels: dict[str, str] = {}
        self.mode_label = tk.StringVar()
        self.profile_var = tk.StringVar(value="balanced")

        ttk.Label(self, textvariable=self.mode_label).grid(row=0, column=0, sticky="w")
        self.scroll = ScrollableFrame(self)
        self.scroll.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.form = self.scroll.inner
        self.form.columnconfigure(1, weight=1)

    def on_show(self) -> None:
        self.mode_label.set(f"Layout options for {self.state.config.layout_mode}")
        if self.state.config.layout_mode == "note_based_stereo":
            self.state.note_based_profile = infer_note_profile(
                self.state.config,
                self.state.note_based_profile,
            )
            self.profile_var.set(self.state.note_based_profile)
        self._build_form()

    def _var(self, field: str, var_type: type[tk.Variable] = tk.StringVar) -> tk.Variable:
        value = getattr(self.state.config, field)
        if field == "direction":
            value = direction_value_to_display(str(value))
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
        help_text = HELP_TEXT_BY_FIELD.get(field)
        return labeled_entry(
            self.form,
            row,
            label,
            self._var(field),
            help_text=help_text,
            step=self,
        )

    def _build_form(self) -> None:
        for child in self.form.winfo_children():
            child.destroy()
        self.vars.clear()
        self.field_labels.clear()
        row = 0

        labeled_option(
            self.form,
            row,
            "Direction",
            self._var("direction"),
            tuple(DIRECTION_DISPLAY_TO_VALUE),
            help_text=HELP_TEXT_BY_FIELD["direction"],
            step=self,
        )
        self._remember_label("direction", "Direction")
        row += 1
        for field, label in (
            ("origin_x", "Origin X"),
            ("origin_y", "Origin Y"),
            ("origin_z", "Origin Z"),
        ):
            self._entry(row, field, label)
            row += 1
        labeled_option(
            self.form,
            row,
            "Minecraft version",
            self._var("minecraft_version"),
            GUI_MINECRAFT_VERSION_CHOICES,
            help_text=HELP_TEXT_BY_FIELD["minecraft_version"],
            step=self,
        )
        self._remember_label("minecraft_version", "Minecraft version")
        row += 1

        mode = self.state.config.layout_mode
        if mode == "basic_linear":
            self._entry(row, "track_id", "Track ID")
        elif mode == "track_based_stereo":
            self._entry(row, "min_distance", "Min distance")
        elif mode == "note_based_stereo":
            combo = labeled_option(
                self.form,
                row,
                "Profile",
                self.profile_var,
                ("safe", "balanced", "dense", "custom"),
                help_text=HELP_TEXT_BY_FIELD["note_profile"],
                step=self,
            )
            combo.bind("<<ComboboxSelected>>", lambda _event: self._on_profile_change())
            row += 1
            readonly = self.profile_var.get() != "custom"
            for field, label, _kind in NOTE_ADVANCED_FIELDS:
                entry = self._entry(row, field, label)
                if readonly:
                    entry.configure(state="disabled")
                row += 1
            check = ttk.Checkbutton(
                self.form,
                text="Depth mirror candidates",
                variable=self._var("enable_depth_mirror_candidates", tk.BooleanVar),
            )
            self.register_help(check, HELP_TEXT_BY_FIELD["enable_depth_mirror_candidates"])
            if readonly:
                check.configure(state="disabled")
            check.grid(row=row, column=1, sticky="w", pady=3)

    def _on_profile_change(self) -> None:
        profile = self.profile_var.get()
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
                updates[field] = direction_display_to_value(str(value))
            elif field == "track_id":
                updates[field] = parse_int(str(value), label, allow_empty=True)
            elif field in int_fields:
                updates[field] = parse_int(
                    str(value),
                    label,
                    min_value=_INT_MIN_VALUES.get(field),
                )
            elif field in float_fields:
                updates[field] = parse_float(
                    str(value),
                    label,
                    min_value=_FLOAT_MIN_VALUES.get(field),
                )
            else:
                updates[field] = str(value)
        self.state.note_based_profile = self.profile_var.get()
        candidate = config_from_dict({**config_to_dict(self.state.config), **updates})
        if candidate.layout_mode == "track_based_stereo":
            candidate = apply_track_based_gui_defaults(candidate)
        errors = validate_layout_options(candidate)
        if errors:
            raise ValueError("\n".join(errors))
        self.state.config = candidate
        return True

    def status_text(self) -> str:
        return self.help_text


HELP_TEXT_BY_FIELD = {
    "direction": "Select the direction the redstone track advances from the layout origin.",
    "origin_x": "Layout origin X is the first music structure position in world coordinates.",
    "origin_y": "Layout origin Y is the build height for the generated music structure.",
    "origin_z": "Layout origin Z is the first music structure position in world coordinates.",
    "minecraft_version": "Choose the exact Minecraft Java profile used for datapack and block compatibility.",
    "track_id": "Basic linear mode can generate one selected track when the song has multiple tracks.",
    "min_distance": "Minimum stereo distance keeps track-based stereo placements away from the center line.",
    "note_profile": "Preset profiles lock advanced note-based parameters; custom allows editing them.",
    "max_candidates_per_emitter": "Maximum candidate positions considered for each note emitter.",
    "retry_max_candidates_per_emitter": "Candidate count used when retrying failed note emitter placement.",
    "max_candidate_y_layers": "Maximum vertical layers scanned for note-based placement candidates.",
    "max_candidate_lateral_positions": "Maximum lateral positions scanned for note-based placement candidates.",
    "radius_search_tolerance": "Allowed distance error while matching note-level stereo radius.",
    "preferred_depth_sign": "Preferred vertical depth direction before mirror fallback.",
    "depth_mirror_penalty": "Extra placement cost for mirrored depth candidates.",
    "enable_depth_mirror_candidates": "Allow mirrored vertical candidates when placing note emitters.",
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
