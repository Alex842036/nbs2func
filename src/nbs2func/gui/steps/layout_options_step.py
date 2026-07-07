from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from nbs2func.gui.helpers import (
    CENTER_SPLIT_MODE_CHOICES,
    CENTER_SPLIT_POLICY_CHOICES,
    DIRECTION_DISPLAY_TO_VALUE,
    GUI_MINECRAFT_VERSION_CHOICES,
    NOTE_PRESETS,
    direction_display_to_value,
    direction_value_to_display,
    infer_note_profile,
    parse_float,
    parse_int,
)
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
        return labeled_entry(self.form, row, label, self._var(field))

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
        )
        self._remember_label("minecraft_version", "Minecraft version")
        row += 1

        mode = self.state.config.layout_mode
        if mode == "basic_linear":
            self._entry(row, "track_id", "Track ID")
        elif mode == "track_based_stereo":
            ttk.Label(
                self.form,
                text="Minecraft note block hearing distance is treated as 48 blocks.",
            ).grid(row=row, column=1, sticky="w", pady=(8, 3))
            row += 1
            for field, label in (
                ("min_distance", "Min distance"),
                ("max_stereo_angle_degrees", "Max stereo angle degrees"),
            ):
                self._entry(row, field, label)
                row += 1
            labeled_option(
                self.form,
                row,
                "Center split policy",
                self._var("center_split_policy"),
                CENTER_SPLIT_POLICY_CHOICES,
            )
            self._remember_label("center_split_policy", "Center split policy")
            row += 1
            labeled_option(
                self.form,
                row,
                "Center split mode",
                self._var("center_split_mode"),
                CENTER_SPLIT_MODE_CHOICES,
            )
            self._remember_label("center_split_mode", "Center split mode")
            row += 1
            ttk.Checkbutton(
                self.form,
                text="Auto spread on collision",
                variable=self._var("enable_collision_resolver", tk.BooleanVar),
            ).grid(row=row, column=1, sticky="w", pady=3)
        elif mode == "note_based_stereo":
            combo = labeled_option(
                self.form,
                row,
                "Profile",
                self.profile_var,
                ("safe", "balanced", "dense", "custom"),
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
            "max_stereo_angle_degrees",
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
                updates[field] = parse_int(str(value), label)
            elif field in float_fields:
                updates[field] = parse_float(str(value), label)
            else:
                updates[field] = str(value)
        self.state.note_based_profile = self.profile_var.get()
        update_config(self.state, updates)
        return True

    def status_text(self) -> str:
        config = self.state.config
        return (
            f"{config.layout_mode}: direction {config.direction}, "
            f"origin {config.origin_x},{config.origin_y},{config.origin_z}, "
            f"Minecraft {config.minecraft_version}"
        )
