from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from nbs2func.core.minecraft_version import (
    supported_minecraft_version_aliases,
    supported_minecraft_versions,
)
from nbs2func.gui.state import update_config
from nbs2func.gui.steps.base import WizardStep, labeled_entry, labeled_option


NOTE_PRESETS = {
    "safe": {
        "max_candidates_per_emitter": 128,
        "retry_max_candidates_per_emitter": 384,
        "max_candidate_y_layers": 10,
        "max_candidate_lateral_positions": 24,
        "radius_search_tolerance": 6.0,
        "enable_depth_mirror_candidates": True,
        "preferred_depth_sign": 1,
        "depth_mirror_penalty": 0.0,
    },
    "balanced": {
        "max_candidates_per_emitter": 64,
        "retry_max_candidates_per_emitter": 256,
        "max_candidate_y_layers": 8,
        "max_candidate_lateral_positions": 16,
        "radius_search_tolerance": 4.0,
        "enable_depth_mirror_candidates": True,
        "preferred_depth_sign": 1,
        "depth_mirror_penalty": 0.0,
    },
    "dense": {
        "max_candidates_per_emitter": 48,
        "retry_max_candidates_per_emitter": 192,
        "max_candidate_y_layers": 6,
        "max_candidate_lateral_positions": 12,
        "radius_search_tolerance": 3.0,
        "enable_depth_mirror_candidates": True,
        "preferred_depth_sign": 1,
        "depth_mirror_penalty": 0.25,
    },
}


class LayoutOptionsStep(WizardStep):
    title = "Options"

    def __init__(self, parent, app) -> None:
        super().__init__(parent, app)
        self.columnconfigure(0, weight=1)
        self.vars: dict[str, tk.Variable] = {}
        self.mode_label = tk.StringVar()
        self.profile_var = tk.StringVar(value="balanced")
        self.show_advanced_var = tk.BooleanVar(value=False)

        ttk.Label(self, textvariable=self.mode_label).grid(row=0, column=0, sticky="w")
        self.form = ttk.Frame(self)
        self.form.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.form.columnconfigure(1, weight=1)

    def on_show(self) -> None:
        self.mode_label.set(f"Layout options for {self.state.config.layout_mode}")
        self._build_form()

    def _var(self, field: str, var_type: type[tk.Variable] = tk.StringVar) -> tk.Variable:
        value = getattr(self.state.config, field)
        if var_type is tk.BooleanVar:
            variable = tk.BooleanVar(value=bool(value))
        else:
            variable = var_type(value="" if value is None else str(value))
        self.vars[field] = variable
        return variable

    def _build_form(self) -> None:
        for child in self.form.winfo_children():
            child.destroy()
        self.vars.clear()
        row = 0

        labeled_option(
            self.form,
            row,
            "Direction",
            self._var("direction"),
            ("east", "west", "south", "north", "x+", "x-", "z+", "z-"),
        )
        row += 1
        for field, label in (
            ("origin_x", "Origin X"),
            ("origin_y", "Origin Y"),
            ("origin_z", "Origin Z"),
        ):
            labeled_entry(self.form, row, label, self._var(field))
            row += 1
        labeled_option(
            self.form,
            row,
            "Minecraft version",
            self._var("minecraft_version"),
            supported_minecraft_versions() + supported_minecraft_version_aliases(),
        )
        row += 1

        mode = self.state.config.layout_mode
        if mode == "basic_linear":
            labeled_entry(self.form, row, "Track ID", self._var("track_id"))
        elif mode == "track_based_stereo":
            for field, label in (
                ("max_hearing_distance", "Max hearing distance"),
                ("min_distance", "Min distance"),
                ("max_stereo_angle_degrees", "Max stereo angle degrees"),
                ("center_split_policy", "Center split policy"),
                ("center_split_mode", "Center split mode"),
            ):
                labeled_entry(self.form, row, label, self._var(field))
                row += 1
            ttk.Checkbutton(
                self.form,
                text="Auto spread on collision",
                variable=self._var("enable_collision_resolver", tk.BooleanVar),
            ).grid(row=row, column=1, sticky="w", pady=3)
        elif mode == "note_based_stereo":
            labeled_option(
                self.form,
                row,
                "Profile",
                self.profile_var,
                ("safe", "balanced", "dense", "custom"),
            ).bind("<<ComboboxSelected>>", lambda _event: self._apply_profile())
            row += 1
            ttk.Checkbutton(
                self.form,
                text="Show advanced options",
                variable=self.show_advanced_var,
                command=self._build_form,
            ).grid(row=row, column=1, sticky="w", pady=3)
            row += 1
            if self.profile_var.get() == "custom" or self.show_advanced_var.get():
                advanced = (
                    ("max_candidates_per_emitter", "Max candidates per emitter"),
                    (
                        "retry_max_candidates_per_emitter",
                        "Retry max candidates per emitter",
                    ),
                    ("max_candidate_y_layers", "Max candidate Y layers"),
                    (
                        "max_candidate_lateral_positions",
                        "Max candidate lateral positions",
                    ),
                    ("radius_search_tolerance", "Radius search tolerance"),
                    ("preferred_depth_sign", "Preferred depth sign"),
                    ("depth_mirror_penalty", "Depth mirror penalty"),
                )
                for field, label in advanced:
                    labeled_entry(self.form, row, label, self._var(field))
                    row += 1
                ttk.Checkbutton(
                    self.form,
                    text="Depth mirror candidates",
                    variable=self._var("enable_depth_mirror_candidates", tk.BooleanVar),
                ).grid(row=row, column=1, sticky="w", pady=3)

    def _apply_profile(self) -> None:
        profile = self.profile_var.get()
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
            "max_hearing_distance",
            "min_distance",
            "max_stereo_angle_degrees",
            "radius_search_tolerance",
            "depth_mirror_penalty",
        }
        bool_fields = {"enable_collision_resolver", "enable_depth_mirror_candidates"}
        for field, variable in self.vars.items():
            value = variable.get()
            if field in bool_fields:
                updates[field] = bool(value)
            elif value == "" and field == "track_id":
                updates[field] = None
            elif field in int_fields:
                updates[field] = int(value)
            elif field in float_fields:
                updates[field] = float(value)
            else:
                updates[field] = str(value)
        update_config(self.state, updates)
        return True

    def status_text(self) -> str:
        config = self.state.config
        return (
            f"{config.layout_mode}: direction {config.direction}, "
            f"origin {config.origin_x},{config.origin_y},{config.origin_z}, "
            f"Minecraft {config.minecraft_version}"
        )
