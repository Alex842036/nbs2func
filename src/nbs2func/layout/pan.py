from __future__ import annotations

import math
import warnings

PAN_ZONES: tuple[tuple[str, float, float], ...] = (
    ("L_EDGE", 0, 33),
    ("L_MID", 34, 66),
    ("L_INNER", 67, 89),
    ("CENTER", 90, 110),
    ("R_INNER", 111, 133),
    ("R_MID", 134, 166),
    ("R_EDGE", 167, 200),
)


def _clamp_max_stereo_angle(max_stereo_angle_degrees: float) -> float:
    if max_stereo_angle_degrees > 90:
        warnings.warn(
            "max_stereo_angle_degrees must be <= 90 for TrackBasedStereoLayout; "
            "clamping to 90 to avoid mirrored positions collapsing onto the center line.",
            stacklevel=2,
        )
        return 90

    return max_stereo_angle_degrees


def _pan_zone_for_panning(panning: float) -> str:
    clamped = max(0.0, min(200.0, panning))
    for zone, pan_min, pan_max in PAN_ZONES:
        if pan_min <= clamped <= pan_max:
            return zone
    return "CENTER"


def _pan_zone_for_angle(angle_degrees: float) -> str:
    if angle_degrees < -40:
        return "L_EDGE"
    if angle_degrees < -20:
        return "L_MID"
    if angle_degrees < -10:
        return "L_INNER"
    if angle_degrees <= 10:
        return "CENTER"
    if angle_degrees <= 20:
        return "R_INNER"
    if angle_degrees <= 40:
        return "R_MID"
    return "R_EDGE"


def _pan_zone_angle_range(
    zone: str,
    max_stereo_angle_degrees: float,
) -> tuple[float, float]:
    max_angle = max(40.0, _clamp_max_stereo_angle(max_stereo_angle_degrees))
    ranges = {
        "L_EDGE": (-max_angle, -40.0001),
        "L_MID": (-40, -20.0001),
        "L_INNER": (-20, -10.0001),
        "CENTER": (-10, 10),
        "R_INNER": (10.0001, 20),
        "R_MID": (20.0001, 40),
        "R_EDGE": (40.0001, max_angle),
    }
    return ranges.get(zone, (-10, 10))


def _representative_angle_for_zone(
    zone: str,
    max_stereo_angle_degrees: float,
) -> float:
    max_angle = max(40.0, _clamp_max_stereo_angle(max_stereo_angle_degrees))
    representatives = {
        "L_EDGE": -(40 + max_angle) / 2,
        "L_MID": -30,
        "L_INNER": -15,
        "CENTER": 0,
        "R_INNER": 15,
        "R_MID": 30,
        "R_EDGE": (40 + max_angle) / 2,
    }
    return representatives.get(zone, 0)


def _angle_values_for_pan_zones(
    zones: tuple[str, ...],
    target_angle: float,
    max_stereo_angle_degrees: float,
    max_count: int,
) -> tuple[float, ...]:
    values: list[float] = []
    for zone in zones:
        start, end = _pan_zone_angle_range(zone, max_stereo_angle_degrees)
        representative = _representative_angle_for_zone(
            zone,
            max_stereo_angle_degrees,
        )
        center = max(start, min(end, target_angle))
        integer_start = math.ceil(start)
        integer_end = math.floor(end)
        candidates = sorted(
            range(integer_start, integer_end + 1),
            key=lambda value: (
                abs(value - center),
                abs(value - representative),
                abs(value),
                value,
            ),
        )
        for value in candidates:
            angle = float(value)
            if angle not in values:
                values.append(angle)
            if len(values) >= max_count:
                return tuple(values)
    return tuple(values)


def _angle_error_inside_zone(
    angle_degrees: float,
    zone: str,
    max_stereo_angle_degrees: float,
) -> float:
    start, end = _pan_zone_angle_range(zone, max_stereo_angle_degrees)
    if not start <= angle_degrees <= end:
        distance = min(abs(angle_degrees - start), abs(angle_degrees - end))
        return 1 + distance / max(1.0, end - start)
    representative = _representative_angle_for_zone(zone, max_stereo_angle_degrees)
    width = max(1.0, end - start)
    return abs(angle_degrees - representative) / width


def _panning_from_angle(
    angle_degrees: float,
    max_stereo_angle_degrees: float,
) -> float:
    max_angle = _clamp_max_stereo_angle(max_stereo_angle_degrees)
    if max_angle <= 0:
        return 100
    return max(0.0, min(200.0, 100 + angle_degrees / max_angle * 100))


def _offset_from_radius_angle_values(
    radius: float,
    angle_degrees: float,
) -> tuple[int, int]:
    angle = math.radians(angle_degrees)
    return (
        round(math.cos(angle) * radius),
        round(math.sin(angle) * radius),
    )


def _pan_zone_lateral_range(
    zone: str,
    max_lateral_distance: int,
) -> tuple[int, int]:
    max_lateral = max(18, abs(max_lateral_distance))
    ranges = {
        "L_EDGE": (-max_lateral, -18),
        "L_MID": (-17, -10),
        "L_INNER": (-9, -4),
        "CENTER": (-3, 3),
        "R_INNER": (4, 9),
        "R_MID": (10, 17),
        "R_EDGE": (18, max_lateral),
    }
    return ranges.get(zone, (-3, 3))


def _pan_zone_for_lateral(
    offset_lateral: int,
    max_lateral_distance: int,
) -> str:
    for zone, _, _ in PAN_ZONES:
        start, end = _pan_zone_lateral_range(zone, max_lateral_distance)
        if start <= offset_lateral <= end:
            return zone
    return "CENTER"


def _representative_lateral_for_zone(
    zone: str,
    max_lateral_distance: int,
) -> int:
    max_lateral = max(18, abs(max_lateral_distance))
    edge_abs = min(max_lateral, 30)
    representatives = {
        "L_EDGE": -edge_abs,
        "L_MID": -13,
        "L_INNER": -6,
        "CENTER": 0,
        "R_INNER": 6,
        "R_MID": 13,
        "R_EDGE": edge_abs,
    }
    return representatives.get(zone, 0)


def _representative_panning_for_zone(zone: str) -> float:
    for candidate_zone, pan_min, pan_max in PAN_ZONES:
        if candidate_zone == zone:
            return (pan_min + pan_max) / 2
    return 100


def _lateral_values_for_pan_zones(
    zones: tuple[str, ...],
    max_lateral_distance: int,
    max_count: int,
) -> tuple[int, ...]:
    values: list[int] = []
    for zone in zones:
        start, end = _pan_zone_lateral_range(zone, max_lateral_distance)
        representative = _representative_lateral_for_zone(zone, max_lateral_distance)
        zone_values = sorted(
            range(start, end + 1),
            key=lambda value: (
                abs(value - representative),
                abs(value),
                value,
            ),
        )
        for value in zone_values:
            if value not in values:
                values.append(value)
            if len(values) >= max_count:
                return tuple(values)
    return tuple(values)


def _lateral_error_inside_zone(
    offset_lateral: int,
    zone: str,
    max_lateral_distance: int,
) -> float:
    start, end = _pan_zone_lateral_range(zone, max_lateral_distance)
    if start > end:
        return 1
    if not start <= offset_lateral <= end:
        distance = min(abs(offset_lateral - start), abs(offset_lateral - end))
        return 1 + distance / max(1, end - start + 1)
    representative = _representative_lateral_for_zone(zone, max_lateral_distance)
    width = max(1, end - start)
    return abs(offset_lateral - representative) / width


def _candidate_pan_zones(
    pan_zone: str,
    allow_adjacent_fallback: bool,
) -> tuple[str, ...]:
    zone_names = [zone for zone, _, _ in PAN_ZONES]
    if pan_zone not in zone_names:
        return ("CENTER",)
    if not allow_adjacent_fallback:
        return (pan_zone,)

    index = zone_names.index(pan_zone)
    zones = [pan_zone]
    if index > 0:
        zones.append(zone_names[index - 1])
    if index < len(zone_names) - 1:
        zones.append(zone_names[index + 1])
    return tuple(zones)


def _failed_retry_pan_zones(pan_zone: str) -> tuple[str, ...]:
    same_side = {
        "L_EDGE": ("L_EDGE", "L_MID"),
        "L_MID": ("L_MID", "L_INNER", "L_EDGE"),
        "L_INNER": ("L_INNER", "L_MID", "L_EDGE"),
        "CENTER": ("CENTER",),
        "R_INNER": ("R_INNER", "R_MID", "R_EDGE"),
        "R_MID": ("R_MID", "R_INNER", "R_EDGE"),
        "R_EDGE": ("R_EDGE", "R_MID"),
    }
    return same_side.get(pan_zone, (pan_zone,))


def _pan_error_inside_zone(
    ideal_panning: float,
    candidate_panning: float,
    pan_zone: str,
) -> float:
    for zone, pan_min, pan_max in PAN_ZONES:
        if zone == pan_zone:
            zone_width = max(1.0, pan_max - pan_min)
            return abs(candidate_panning - ideal_panning) / zone_width
    return abs(candidate_panning - ideal_panning) / 200
