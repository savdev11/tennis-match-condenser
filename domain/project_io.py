from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import os

from domain.models import OverlayState, PointClip, PointRecord, Segment
from domain.enums import CaptureState, normalize_capture_state


@dataclass
class ProjectDocument:
    input_paths: list[str]
    current_clip_index: int
    pending_point_start: float | None
    pending_point_source_path: str | None
    next_point_id: int
    selected_point_id: int | None
    capture_state: str
    points: list[PointRecord]
    segments: list[Segment]
    state: dict[str, Any]
    version: int = 4


@dataclass
class LoadedProjectState:
    input_paths: list[str]
    current_clip_index: int
    pending_point_start: float | None
    pending_point_source_path: str | None
    points: list[PointRecord]
    next_point_id: int
    selected_point_id: int | None
    capture_state: str
    state: dict[str, Any]
    payload_version: int
    warnings: list[str]
    requires_reset_open_session: bool


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "true", "yes", "on"}:
            return True
        if v in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def overlay_to_dict(ov: OverlayState) -> dict[str, Any]:
    return {
        "player_a": ov.player_a,
        "player_b": ov.player_b,
        "sets_a": ov.sets_a,
        "sets_b": ov.sets_b,
        "games_a": ov.games_a,
        "games_b": ov.games_b,
        "points_a": ov.points_a,
        "points_b": ov.points_b,
        "server": ov.server,
        "tournament": ov.tournament,
        "overlay_corner": ov.overlay_corner,
        "overlay_scale": ov.overlay_scale,
        "set_col1_a": ov.set_col1_a,
        "set_col1_b": ov.set_col1_b,
        "set_col2_a": ov.set_col2_a,
        "set_col2_b": ov.set_col2_b,
        "alert_banner": ov.alert_banner,
        "flag_a_code": ov.flag_a_code,
        "flag_b_code": ov.flag_b_code,
        "flag_a_path": ov.flag_a_path,
        "flag_b_path": ov.flag_b_path,
    }


def overlay_from_dict(raw: dict[str, Any] | None) -> OverlayState:
    ov = raw or {}
    return OverlayState(
        player_a=str(ov.get("player_a", "Giocatore A")),
        player_b=str(ov.get("player_b", "Giocatore B")),
        sets_a=_to_int(ov.get("sets_a", 0), 0),
        sets_b=_to_int(ov.get("sets_b", 0), 0),
        games_a=_to_int(ov.get("games_a", 0), 0),
        games_b=_to_int(ov.get("games_b", 0), 0),
        points_a=str(ov.get("points_a", "0")),
        points_b=str(ov.get("points_b", "0")),
        server=str(ov.get("server", "A")),
        tournament=str(ov.get("tournament", "Amateur Tennis Tour")),
        overlay_corner=str(ov.get("overlay_corner", "Top Left")),
        overlay_scale=_to_float(ov.get("overlay_scale", 1.0), 1.0),
        set_col1_a=str(ov.get("set_col1_a", ov.get("games_a", "0"))),
        set_col1_b=str(ov.get("set_col1_b", ov.get("games_b", "0"))),
        set_col2_a=str(ov.get("set_col2_a", "")),
        set_col2_b=str(ov.get("set_col2_b", "")),
        alert_banner=str(ov.get("alert_banner", "")),
        flag_a_code=str(ov.get("flag_a_code", "")),
        flag_b_code=str(ov.get("flag_b_code", "")),
        flag_a_path=str(ov.get("flag_a_path", "")),
        flag_b_path=str(ov.get("flag_b_path", "")),
    )


def clip_to_dict(clip: PointClip) -> dict[str, Any]:
    return {
        "start": clip.start,
        "end": clip.end,
        "source_path": clip.source_path,
    }


def clip_from_dict(raw: dict[str, Any] | None, *, require_existing_source: bool = True) -> PointClip | None:
    if not isinstance(raw, dict):
        return None
    src = raw.get("source_path")
    if not isinstance(src, str) or not src:
        return None
    if require_existing_source and not os.path.exists(src):
        return None
    start = _to_float(raw.get("start", 0.0), 0.0)
    end = _to_float(raw.get("end", 0.0), 0.0)
    if end - start <= 0:
        return None
    return PointClip(start=start, end=end, source_path=src)


def point_to_dict(point: PointRecord) -> dict[str, Any]:
    # Keep overlay_* fields serialized for backward compatibility with old
    # project payloads. They are not authoritative runtime state.
    return {
        "id": point.id,
        "winner": point.winner,
        "is_highlight": point.is_highlight,
        "clips": [clip_to_dict(clip) for clip in point.clips],
        "overlay_at_start": overlay_to_dict(point.overlay_at_start) if point.overlay_at_start else None,
        "overlay_at_end": overlay_to_dict(point.overlay_at_end) if point.overlay_at_end else None,
    }


def point_from_dict(
    raw: dict[str, Any] | None,
    *,
    fallback_id: int,
    require_existing_source: bool = True,
) -> tuple[PointRecord | None, int, list[str]]:
    warnings: list[str] = []
    if not isinstance(raw, dict):
        return None, fallback_id, ["point_entry_invalid"]

    parsed_clips: list[PointClip] = []
    raw_clips = raw.get("clips", [])
    if isinstance(raw_clips, list):
        for raw_clip in raw_clips:
            parsed = clip_from_dict(raw_clip, require_existing_source=require_existing_source)
            if parsed is None:
                warnings.append("clip_skipped_invalid")
                continue
            parsed_clips.append(parsed)
    if not parsed_clips:
        return None, fallback_id, warnings + ["point_skipped_no_valid_clips"]

    raw_id = raw.get("id")
    point_id = _to_int(raw_id, fallback_id)
    next_fallback = fallback_id
    if raw_id is None:
        point_id = fallback_id
        next_fallback = fallback_id + 1
    else:
        try:
            int(raw_id)
        except (TypeError, ValueError):
            point_id = fallback_id
            next_fallback = fallback_id + 1

    winner = raw.get("winner") if raw.get("winner") in ("A", "B") else None
    point = PointRecord(
        id=point_id,
        winner=winner,
        is_highlight=_to_bool(raw.get("is_highlight", False), False),
        clips=parsed_clips,
        overlay_at_start=overlay_from_dict(raw.get("overlay_at_start")),
        overlay_at_end=overlay_from_dict(raw.get("overlay_at_end")) if raw.get("overlay_at_end") is not None else None,
    )
    return point, next_fallback, warnings


def segment_to_dict(seg: Segment) -> dict[str, Any]:
    return {
        "start": seg.start,
        "end": seg.end,
        "source_path": seg.source_path,
        "overlay": overlay_to_dict(seg.overlay),
        "is_highlight": seg.is_highlight,
    }


def segment_from_dict(raw: dict[str, Any] | None, *, require_existing_source: bool = True) -> Segment | None:
    if not isinstance(raw, dict):
        return None
    src = raw.get("source_path")
    if not isinstance(src, str) or not src:
        return None
    if require_existing_source and not os.path.exists(src):
        return None
    start = _to_float(raw.get("start", 0.0), 0.0)
    end = _to_float(raw.get("end", 0.0), 0.0)
    if end - start <= 0:
        return None
    return Segment(
        start=start,
        end=end,
        source_path=src,
        overlay=overlay_from_dict(raw.get("overlay", {})),
        is_highlight=_to_bool(raw.get("is_highlight", False), False),
    )


def infer_next_point_id(points: list[PointRecord], loaded_next_point_id: Any) -> int:
    loaded = _to_int(loaded_next_point_id, 1)
    if points:
        inferred_next = max(point.id for point in points) + 1
        return max(loaded, inferred_next)
    return max(1, loaded)


def infer_selected_point_id(raw_selected_point_id: Any, points: list[PointRecord]) -> int | None:
    try:
        selected = int(raw_selected_point_id) if raw_selected_point_id is not None else None
    except (TypeError, ValueError):
        return None
    return selected


def _normalize_state(state: dict[str, Any] | None) -> dict[str, Any]:
    src = state or {}
    raw_completed_sets = src.get("completed_sets", [])
    parsed_completed_sets: list[tuple[int, int]] = []
    if isinstance(raw_completed_sets, list):
        for item in raw_completed_sets:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                try:
                    parsed_completed_sets.append((int(item[0]), int(item[1])))
                except (TypeError, ValueError):
                    continue

    raw_tb_loser_points = src.get("completed_set_tb_loser_points", [])
    parsed_tb_loser_points: list[int | None] = []
    if isinstance(raw_tb_loser_points, list):
        for item in raw_tb_loser_points:
            if item is None:
                parsed_tb_loser_points.append(None)
            else:
                try:
                    parsed_tb_loser_points.append(int(item))
                except (TypeError, ValueError):
                    parsed_tb_loser_points.append(None)
    while len(parsed_tb_loser_points) < len(parsed_completed_sets):
        parsed_tb_loser_points.append(None)

    normalized = dict(src)
    normalized.update(
        {
            "points_a": _to_int(src.get("points_a", 0), 0),
            "points_b": _to_int(src.get("points_b", 0), 0),
            "tb_points_a": _to_int(src.get("tb_points_a", 0), 0),
            "tb_points_b": _to_int(src.get("tb_points_b", 0), 0),
            "games_a": _to_int(src.get("games_a", 0), 0),
            "games_b": _to_int(src.get("games_b", 0), 0),
            "sets_a": _to_int(src.get("sets_a", 0), 0),
            "sets_b": _to_int(src.get("sets_b", 0), 0),
            "completed_sets": parsed_completed_sets,
            "completed_set_tb_loser_points": parsed_tb_loser_points[: len(parsed_completed_sets)],
            "in_tiebreak": _to_bool(src.get("in_tiebreak", False), False),
            "tiebreak_target": _to_int(src.get("tiebreak_target", 7), 7),
            "tiebreak_super": _to_bool(src.get("tiebreak_super", False), False),
            "starting_server": str(src.get("starting_server", "A")),
            "current_server": str(src.get("current_server", src.get("starting_server", "A"))),
            "tiebreak_first_server": src.get("tiebreak_first_server"),
        }
    )
    return normalized


def serialize_project_document(doc: ProjectDocument) -> dict[str, Any]:
    return {
        "version": doc.version,
        "input_paths": list(doc.input_paths),
        "current_clip_index": int(doc.current_clip_index),
        "pending_point_start": doc.pending_point_start,
        "pending_point_source_path": doc.pending_point_source_path,
        "next_point_id": int(doc.next_point_id),
        "selected_point_id": doc.selected_point_id,
        "capture_state": str(doc.capture_state),
        "points": [point_to_dict(point) for point in doc.points],
        "segments": [segment_to_dict(seg) for seg in doc.segments],
        "state": dict(doc.state),
    }


def deserialize_project_document(data: dict[str, Any], *, require_existing_source: bool = True) -> LoadedProjectState:
    warnings: list[str] = []
    input_paths = data.get("input_paths", [])
    if not isinstance(input_paths, list):
        raise ValueError("Formato progetto non valido: input_paths.")
    existing_paths = [p for p in input_paths if isinstance(p, str) and (os.path.exists(p) if require_existing_source else True)]
    if not existing_paths:
        raise ValueError("Nessun file video sorgente trovato sul disco.")

    clip_index = _to_int(data.get("current_clip_index", 0), 0)
    clip_index = min(max(0, clip_index), len(existing_paths) - 1)

    points: list[PointRecord] = []
    fallback_id = 1
    raw_points = data.get("points", [])
    if isinstance(raw_points, list) and raw_points:
        for raw_point in raw_points:
            point, fallback_id, point_warnings = point_from_dict(
                raw_point,
                fallback_id=fallback_id,
                require_existing_source=require_existing_source,
            )
            warnings.extend(point_warnings)
            if point is not None:
                points.append(point)
    else:
        raw_segments = data.get("segments", [])
        if isinstance(raw_segments, list):
            for raw_seg in raw_segments:
                seg = segment_from_dict(raw_seg, require_existing_source=require_existing_source)
                if seg is None:
                    warnings.append("legacy_segment_skipped_invalid")
                    continue
                point = PointRecord(
                    id=fallback_id,
                    winner=None,
                    is_highlight=bool(seg.is_highlight),
                    clips=[PointClip(start=seg.start, end=seg.end, source_path=seg.source_path)],
                    overlay_at_start=seg.overlay,
                    overlay_at_end=None,
                )
                fallback_id += 1
                points.append(point)

    next_point_id = infer_next_point_id(points, data.get("next_point_id", 1))
    selected_point_id = infer_selected_point_id(data.get("selected_point_id"), points)
    capture_state = normalize_capture_state(data.get("capture_state", CaptureState.IDLE.value)).value

    state = _normalize_state(data.get("state", {}))
    payload_version = _to_int(data.get("version", 0), 0)

    pending_point_start = data.get("pending_point_start")
    pending_point_source_path = data.get("pending_point_source_path")
    if pending_point_start is not None:
        pending_point_start = _to_float(pending_point_start, 0.0)
    if pending_point_source_path is not None and not isinstance(pending_point_source_path, str):
        pending_point_source_path = None

    return LoadedProjectState(
        input_paths=existing_paths,
        current_clip_index=clip_index,
        pending_point_start=pending_point_start,
        pending_point_source_path=pending_point_source_path,
        points=points,
        next_point_id=next_point_id,
        selected_point_id=selected_point_id,
        capture_state=capture_state,
        state=state,
        payload_version=payload_version,
        warnings=warnings,
        requires_reset_open_session=(capture_state != CaptureState.IDLE.value),
    )
