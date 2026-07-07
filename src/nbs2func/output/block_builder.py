from __future__ import annotations

from typing import TYPE_CHECKING

from ..core.instrument_mapping import get_instrument_block, get_required_support_block
from ..layout.geometry import (
    DIRECTION_VECTORS,
    BlockPosition,
    _right_hand_lateral_vector,
    _scale_vector,
    add_vector,
    add_y,
    below,
    normalize_direction,
    opposite_direction,
    repeater_position_from_note_position,
)
from ..layout.models import (
    LayoutCell,
    LayoutResult,
    NoteBasedStereoRailLayoutPreview,
    SlotAssignment,
)
from ..modules.playback_assist import (
    PlaybackAssistModuleConfig,
    build_playback_assist_plan,
    total_track_length_from_layout,
)
from ..modules.starter import StarterModuleConfig, build_starter_plan
from .models import (
    GeneratedBuildItem,
    GeneratedComment,
    GeneratedCommand,
    GeneratedBuildPlan,
    GeneratedBuildSection,
    PlacedBlock,
)

if TYPE_CHECKING:
    from .command_writer import CommandWriterConfig


def build_generated_plan(
    layout: LayoutResult,
    config: CommandWriterConfig,
) -> GeneratedBuildPlan:
    """Build structured block placements and non-block commands for a layout."""

    sections: list[GeneratedBuildSection] = []
    warnings: list[str] = []

    starter_plan = build_starter_plan(
        layout,
        StarterModuleConfig(
            enable_starter_module=(
                config.enable_starter_module
                or config.enable_playback_assist
            ),
            emit_command_block=not config.enable_playback_assist,
            command_block_position=config.command_block_position,
            starter_tag=config.starter_tag,
            starter_track_block=config.starter_track_block,
            starter_cell_offset=config.starter_cell_offset,
            minecraft_version_profile=config.minecraft_version_profile,
        ),
        default_track_block=config.track_block,
        repeater_block=config.repeater_block,
    )
    sections.extend(starter_plan.sections)
    warnings.extend(starter_plan.warnings)

    if layout.note_based_preview is not None:
        sections.extend(_note_based_preview_sections(layout.note_based_preview, config))
    else:
        sections.extend(_cell_sections(layout.cells, config))

    playback_plan = build_playback_assist_plan(
        PlaybackAssistModuleConfig(
            enable_playback_assist=config.enable_playback_assist,
            player_name=config.playback_player_name,
            playback_vehicle_tag=config.playback_vehicle_tag,
            starter_tag=config.starter_tag,
            count_objective=config.count_objective,
            vehicle_spawn_position=config.vehicle_spawn_position,
            music_start_position=config.music_start_position,
            command_module_origin=config.command_module_origin,
            track_direction=config.playback_track_direction,
            total_track_length=(
                config.playback_total_track_length
                if config.playback_total_track_length is not None
                else total_track_length_from_layout(
                    layout,
                    config.playback_track_direction,
                    config.music_start_position,
                )
            ),
            generate_playback_buttons=config.generate_playback_buttons,
            playback_button_block=config.playback_button_block,
            prepare_button_position=config.prepare_button_position,
            start_button_position=config.start_button_position,
            minecraft_version_profile=config.minecraft_version_profile,
            tempo_control_mode=config.tempo_control_mode,
            tempo_control_report=config.tempo_control_report,
            reset_tick_rate_after_playback=config.reset_tick_rate_after_playback,
        )
    )
    sections.extend(playback_plan.sections)
    warnings.extend(playback_plan.warnings)

    blocks = tuple(
        item
        for section in sections
        for item in section.items
        if isinstance(item, PlacedBlock)
    )
    commands = tuple(
        item
        for section in sections
        for item in section.items
        if isinstance(item, GeneratedCommand)
    )
    return GeneratedBuildPlan(
        blocks=blocks,
        commands=commands,
        warnings=tuple(warnings),
        sections=tuple(sections),
    )


def _cell_sections(
    cells: tuple[LayoutCell, ...],
    config: CommandWriterConfig,
) -> tuple[GeneratedBuildSection, ...]:
    return tuple(_section_for_cell(cell, config) for cell in cells)


def _section_for_cell(
    cell: LayoutCell,
    config: CommandWriterConfig,
) -> GeneratedBuildSection:
    items: list[GeneratedBuildItem] = [
        _placed_block(
            cell.track_block_position,
            config.track_block,
            "layout.cell.track_block",
        ),
        _placed_block(
            cell.repeater_position,
            f"{config.repeater_block}[facing={cell.repeater_facing},delay=2]",
            "layout.cell.repeater",
        ),
    ]

    comments = [f"# tick={cell.tick} track={cell.track_id}"]
    if cell.note is None:
        items.extend(
            [
                _placed_block(
                    cell.note_block_position,
                    config.track_block,
                    "layout.cell.empty_note_position",
                ),
                _placed_block(
                    cell.instrument_block_position,
                    config.track_block,
                    "layout.cell.empty_instrument_position",
                ),
            ]
        )
        return GeneratedBuildSection(comments=tuple(comments), items=tuple(items))

    note_value = _minecraft_note_value(cell.note.key)
    instrument_block = get_instrument_block(cell.note.instrument)
    support_block = get_required_support_block(
        instrument_block,
        config.track_block,
    )
    if cell.gravity_support_block_position is not None and support_block is not None:
        items.append(
            _placed_block(
                cell.gravity_support_block_position,
                support_block,
                "layout.cell.gravity_support_block",
            )
        )

    items.append(
        GeneratedComment(
            f"# note layer={cell.note.layer} instrument={cell.note.instrument} "
            f"key={cell.note.key} final_volume={cell.note.final_volume:.2f} "
            f"final_panning={cell.note.final_panning:.2f}"
        )
    )
    items.extend(
        [
            _placed_block(
                cell.instrument_block_position,
                instrument_block,
                "layout.cell.instrument_block",
            ),
            _placed_block(
                cell.note_block_position,
                f"note_block[note={note_value}]",
                "layout.cell.note_block",
            ),
        ]
    )
    return GeneratedBuildSection(comments=tuple(comments), items=tuple(items))


def _note_based_preview_sections(
    report: NoteBasedStereoRailLayoutPreview,
    config: CommandWriterConfig,
) -> tuple[GeneratedBuildSection, ...]:
    sections: list[GeneratedBuildSection] = [
        GeneratedBuildSection(
            comments=(
                "# Note-based stereo rail layout",
                f"# rails={report.total_activation_rails}",
                f"# emitters={len(report.assignments)}",
            ),
            items=(),
            trailing_blank=False,
        )
    ]
    assignments_by_rail_tick: dict[tuple[str, int], list[SlotAssignment]] = {}
    rails_by_id = {
        assignment.rail.rail_id: assignment.rail
        for assignment in report.assignments
    }

    for assignment in report.assignments:
        assignments_by_rail_tick.setdefault(
            (assignment.rail.rail_id, assignment.emitter.tick),
            [],
        ).append(assignment)

    for rail_id, rail in sorted(rails_by_id.items()):
        rail_ticks = [
            tick
            for assignment_rail_id, tick in assignments_by_rail_tick
            if assignment_rail_id == rail_id
        ]
        if not rail_ticks:
            continue

        sections.append(
            GeneratedBuildSection(
                comments=(
                    f"# rail={rail_id} offset_y={rail.offset_y} "
                    f"offset_lateral={rail.offset_lateral}",
                ),
                items=(),
                trailing_blank=False,
            )
        )
        for tick in range(max(rail_ticks) + 1):
            cell_assignments = assignments_by_rail_tick.get((rail_id, tick), [])
            center_assignment = next(
                (
                    assignment
                    for assignment in cell_assignments
                    if assignment.slot.slot_index == 0
                ),
                None,
            )
            rail_center = _note_based_position(
                report,
                tick,
                rail.offset_y,
                rail.offset_lateral,
            )
            repeater_position = repeater_position_from_note_position(
                rail_center,
                report.track_direction,
            )
            items: list[GeneratedBuildItem] = [
                _placed_block(
                    below(repeater_position),
                    config.track_block,
                    "layout.note_based.repeater_support_block",
                ),
                _placed_block(
                    repeater_position,
                    (
                        f"{config.repeater_block}"
                        f"[facing={_repeater_facing(report)},delay=2]"
                    ),
                    "layout.note_based.repeater",
                ),
            ]

            if center_assignment is None:
                items.extend(
                    [
                        _placed_block(
                            rail_center,
                            config.track_block,
                            "layout.note_based.empty_rail_center",
                        ),
                        _placed_block(
                            below(rail_center),
                            config.track_block,
                            "layout.note_based.empty_rail_center_support",
                        ),
                    ]
                )
            else:
                items.extend(_note_based_emitter_items(center_assignment, config))

            for assignment in cell_assignments:
                if assignment.slot.slot_index == 0:
                    continue
                items.extend(_note_based_emitter_items(assignment, config))

            sections.append(
                GeneratedBuildSection(
                    comments=(f"# tick={tick} rail={rail_id}",),
                    items=tuple(items),
                )
            )

    return tuple(sections)


def _note_based_emitter_items(
    assignment: SlotAssignment,
    config: CommandWriterConfig,
) -> tuple[GeneratedBuildItem, ...]:
    emitter = assignment.emitter
    note_value = _minecraft_note_value(emitter.key)
    instrument_block = get_instrument_block(emitter.instrument)
    instrument_position = below(assignment.slot.position)
    support_block = get_required_support_block(
        instrument_block,
        config.track_block,
    )
    items: list[GeneratedBuildItem] = [
        GeneratedComment(
            f"# emitter={emitter.emitter_id} rail={assignment.rail.rail_id} "
            f"slot={assignment.slot.slot_index} layer={emitter.layer} "
            f"instrument={emitter.instrument} key={emitter.key} "
            f"final_volume={emitter.final_volume:.2f} "
            f"final_panning={emitter.final_panning:.2f}"
        )
    ]
    if support_block is not None:
        items.append(
            _placed_block(
                below(instrument_position),
                support_block,
                "layout.note_based.gravity_support_block",
            )
        )
    items.extend(
        [
            _placed_block(
                instrument_position,
                instrument_block,
                "layout.note_based.instrument_block",
            ),
            _placed_block(
                assignment.slot.position,
                f"note_block[note={note_value}]",
                "layout.note_based.note_block",
            ),
        ]
    )
    return tuple(items)


def _placed_block(position: BlockPosition, block: str, source: str) -> PlacedBlock:
    return PlacedBlock(
        x=position.x,
        y=position.y,
        z=position.z,
        block=_block_id(block),
        source=source,
    )


def _block_id(block: str) -> str:
    if block.startswith("minecraft:"):
        return block
    return f"minecraft:{block}"


def _minecraft_note_value(key: int) -> int:
    return min(24, max(0, key - 33))


def _note_based_position(
    report: NoteBasedStereoRailLayoutPreview,
    tick: int,
    offset_y: int,
    offset_lateral: int,
) -> BlockPosition:
    track_direction = normalize_direction(report.track_direction)
    track_vector = DIRECTION_VECTORS[track_direction]
    lateral_vector = _right_hand_lateral_vector(track_direction)
    cell_origin = add_vector(
        report.origin,
        _scale_vector(track_vector, tick * report.tick_spacing),
    )
    return add_vector(
        add_y(cell_origin, offset_y),
        _scale_vector(lateral_vector, offset_lateral),
    )


def _repeater_facing(report: NoteBasedStereoRailLayoutPreview) -> str:
    return opposite_direction(report.track_direction)
