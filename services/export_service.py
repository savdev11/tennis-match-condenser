from __future__ import annotations

from dataclasses import dataclass

from domain.models import OverlayState, PointClip, PointRecord, Segment


@dataclass
class ExportPreparationResult:
    export_segments: list[Segment]
    intro_clip: dict | None
    outro_clip: dict | None
    error: str | None = None


def _clone_overlay_for_export(overlay: OverlayState, export_corner: str, export_scale: float) -> OverlayState:
    return OverlayState(
        player_a=overlay.player_a,
        player_b=overlay.player_b,
        sets_a=overlay.sets_a,
        sets_b=overlay.sets_b,
        games_a=overlay.games_a,
        games_b=overlay.games_b,
        points_a=overlay.points_a,
        points_b=overlay.points_b,
        server=overlay.server,
        tournament=overlay.tournament,
        overlay_corner=export_corner,
        overlay_scale=export_scale,
        set_col1_a=overlay.set_col1_a,
        set_col1_b=overlay.set_col1_b,
        set_col2_a=overlay.set_col2_a,
        set_col2_b=overlay.set_col2_b,
        alert_banner=overlay.alert_banner,
        flag_a_code=overlay.flag_a_code,
        flag_b_code=overlay.flag_b_code,
        flag_a_path=overlay.flag_a_path,
        flag_b_path=overlay.flag_b_path,
    )


def build_export_segments_for_render(
    source_segments: list[Segment],
    *,
    export_corner: str,
    export_scale: float,
) -> list[Segment]:
    export_segments: list[Segment] = []
    for seg in source_segments:
        export_segments.append(
            Segment(
                start=seg.start,
                end=seg.end,
                source_path=seg.source_path,
                overlay=_clone_overlay_for_export(seg.overlay, export_corner, export_scale),
                is_highlight=seg.is_highlight,
            )
        )
    return export_segments


def select_highlight_segments(segments: list[Segment]) -> list[Segment]:
    return [seg for seg in segments if seg.is_highlight]


def _clip_matches_segment(clip: PointClip, segment: Segment, eps: float = 1e-6) -> bool:
    return (
        clip.source_path == segment.source_path
        and abs(clip.start - segment.start) < eps
        and abs(clip.end - segment.end) < eps
    )


def select_segments_for_point(point: PointRecord, flat_segments: list[Segment]) -> list[Segment]:
    selected: list[Segment] = []
    for seg in flat_segments:
        if any(_clip_matches_segment(clip, seg) for clip in point.clips):
            selected.append(seg)
    return selected


def prepare_export_payload(
    source_segments: list[Segment],
    *,
    export_corner: str,
    export_scale: float,
    include_intro: bool,
    include_outro: bool,
    intro_cfg: dict | None,
    outro_cfg: dict | None,
) -> ExportPreparationResult:
    if include_intro and intro_cfg is None:
        return ExportPreparationResult([], None, None, error="missing_intro")
    if include_outro and outro_cfg is None:
        return ExportPreparationResult([], None, None, error="missing_outro")

    export_segments = build_export_segments_for_render(
        source_segments,
        export_corner=export_corner,
        export_scale=export_scale,
    )
    return ExportPreparationResult(
        export_segments=export_segments,
        intro_clip=intro_cfg,
        outro_clip=outro_cfg,
        error=None,
    )
