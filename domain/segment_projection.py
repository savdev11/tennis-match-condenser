from __future__ import annotations

from dataclasses import asdict

from domain.models import MatchSettingsSnapshot, OverlayState, PointRecord, Segment
from domain import runtime_overlay


def ordered_points(points: list[PointRecord]) -> list[PointRecord]:
    return sorted(points, key=lambda point: point.id)


def validate_clip_interval(start: float, end: float) -> bool:
    return (end - start) > 0


def _clone_overlay_state(state: OverlayState) -> OverlayState:
    return OverlayState(**asdict(state))


def flatten_points_to_segments(
    points: list[PointRecord],
    settings: MatchSettingsSnapshot,
    source_order: list[str] | None = None,
    durations: dict[str, float] | None = None,
    default_overlay: OverlayState | None = None,
) -> list[Segment]:
    # source_order/durations are accepted for explicit API completeness in multi-video contexts;
    # current deterministic behavior is editorial order by point id and clip insertion order.
    _ = source_order
    _ = durations

    flat: list[Segment] = []
    for point in ordered_points(points):
        overlay_ref = runtime_overlay.derive_overlay_state_before_point(points, settings, point.id)
        if overlay_ref is None:
            if default_overlay is None:
                continue
            overlay_ref = default_overlay
        for clip in point.clips:
            if not validate_clip_interval(clip.start, clip.end):
                continue
            flat.append(
                Segment(
                    start=clip.start,
                    end=clip.end,
                    source_path=clip.source_path,
                    overlay=_clone_overlay_state(overlay_ref),
                    is_highlight=point.is_highlight,
                )
            )
    return flat
