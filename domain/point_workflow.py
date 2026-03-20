from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from domain.enums import CaptureState
from domain.models import OverlayState, PointClip, PointRecord


@dataclass
class WorkflowState:
    points: list[PointRecord]
    selected_point_id: int | None
    capture_state: str
    open_point_id: int | None
    open_clip_start: float | None
    open_clip_source_path: str | None
    next_point_id: int


@dataclass
class WorkflowResult:
    state: WorkflowState
    allowed: bool
    changed: bool
    reason: str
    finalized_point_id: int | None = None
    removed_point_id: int | None = None


def clone_state(state: WorkflowState) -> WorkflowState:
    return WorkflowState(
        points=deepcopy(state.points),
        selected_point_id=state.selected_point_id,
        capture_state=str(state.capture_state),
        open_point_id=state.open_point_id,
        open_clip_start=state.open_clip_start,
        open_clip_source_path=state.open_clip_source_path,
        next_point_id=state.next_point_id,
    )


def ordered_points(points: list[PointRecord]) -> list[PointRecord]:
    return sorted(points, key=lambda point: point.id)


def get_open_point_index(points: list[PointRecord], open_point_id: int | None) -> int | None:
    if open_point_id is None:
        return None
    for idx, point in enumerate(points):
        if point.id == open_point_id:
            return idx
    return None


def reset_open_capture_fields(state: WorkflowState) -> None:
    state.open_point_id = None
    state.open_clip_start = None
    state.open_clip_source_path = None


def is_point_finalizable(points: list[PointRecord], open_point_id: int | None) -> bool:
    idx = get_open_point_index(points, open_point_id)
    if idx is None:
        return False
    return len(points[idx].clips) > 0


def can_remove_last_point(points: list[PointRecord], selected_point_id: int | None, capture_state: str) -> bool:
    if capture_state != CaptureState.IDLE.value:
        return False
    if not points or selected_point_id is None:
        return False
    return points[-1].id == selected_point_id


def _append_clip_interval(
    point: PointRecord,
    *,
    start_source: str,
    start_time: float,
    end_source: str,
    end_time: float,
    source_order: list[str],
    source_duration_map: dict[str, float],
    min_duration: float = 0.15,
) -> tuple[int, str]:
    if not source_order:
        source_order = [start_source]
    try:
        start_idx = source_order.index(start_source)
        end_idx = source_order.index(end_source)
    except ValueError:
        if start_source != end_source:
            return (0, "invalid_source_range")
        start_idx = end_idx = 0
    if end_idx < start_idx:
        return (0, "invalid_source_order")

    created = 0
    for idx in range(start_idx, end_idx + 1):
        source_path = source_order[idx] if source_order else start_source
        seg_start = start_time if idx == start_idx else 0.0
        if idx == end_idx:
            seg_end = end_time
        else:
            duration = source_duration_map.get(source_path)
            if duration is None:
                return (created, "missing_duration")
            seg_end = duration
        start = min(seg_start, seg_end)
        end = max(seg_start, seg_end)
        if end - start < min_duration:
            continue
        point.clips.append(PointClip(start=start, end=end, source_path=source_path))
        created += 1

    if created <= 0:
        return (0, "clip_too_short")
    return (created, "ok")


def start_point_session(
    state: WorkflowState,
    *,
    now: float,
    source_path: str,
    overlay_at_start: OverlayState,
) -> WorkflowResult:
    new_state = clone_state(state)
    if new_state.capture_state != CaptureState.IDLE.value:
        return WorkflowResult(new_state, allowed=False, changed=False, reason="already_in_progress")

    point = PointRecord(
        id=new_state.next_point_id,
        winner=None,
        is_highlight=False,
        clips=[],
        overlay_at_start=deepcopy(overlay_at_start),
        overlay_at_end=None,
    )
    new_state.next_point_id += 1
    new_state.points.append(point)
    new_state.open_point_id = point.id
    new_state.open_clip_start = now
    new_state.open_clip_source_path = source_path
    new_state.capture_state = CaptureState.RECORDING.value
    new_state.selected_point_id = point.id
    return WorkflowResult(new_state, allowed=True, changed=True, reason="started")


def pause_clip_session(
    state: WorkflowState,
    *,
    now: float,
    end_source: str,
    source_order: list[str],
    source_duration_map: dict[str, float],
    min_duration: float = 0.15,
) -> WorkflowResult:
    new_state = clone_state(state)
    if new_state.capture_state != CaptureState.RECORDING.value:
        return WorkflowResult(new_state, allowed=False, changed=False, reason="not_recording")
    if new_state.open_clip_start is None or not new_state.open_clip_source_path:
        return WorkflowResult(new_state, allowed=False, changed=False, reason="invalid_open_clip")

    point_idx = get_open_point_index(new_state.points, new_state.open_point_id)
    if point_idx is None:
        return WorkflowResult(new_state, allowed=False, changed=False, reason="invalid_open_point")

    point = new_state.points[point_idx]
    created, reason = _append_clip_interval(
        point,
        start_source=new_state.open_clip_source_path,
        start_time=new_state.open_clip_start,
        end_source=end_source,
        end_time=now,
        source_order=source_order,
        source_duration_map=source_duration_map,
        min_duration=min_duration,
    )
    if created <= 0:
        return WorkflowResult(new_state, allowed=False, changed=False, reason=reason)

    new_state.open_clip_start = None
    new_state.open_clip_source_path = None
    new_state.capture_state = CaptureState.PAUSED_WITHIN_POINT.value
    return WorkflowResult(new_state, allowed=True, changed=True, reason="paused")


def resume_clip_session(state: WorkflowState, *, now: float, source_path: str) -> WorkflowResult:
    new_state = clone_state(state)
    if new_state.capture_state != CaptureState.PAUSED_WITHIN_POINT.value:
        return WorkflowResult(new_state, allowed=False, changed=False, reason="not_paused")

    point_idx = get_open_point_index(new_state.points, new_state.open_point_id)
    if point_idx is None:
        return WorkflowResult(new_state, allowed=False, changed=False, reason="invalid_open_point")

    new_state.open_clip_start = now
    new_state.open_clip_source_path = source_path
    new_state.capture_state = CaptureState.RECORDING.value
    return WorkflowResult(new_state, allowed=True, changed=True, reason="resumed")


def finalize_point_session(
    state: WorkflowState,
    *,
    winner: str,
    now: float,
    end_source: str,
    source_order: list[str],
    source_duration_map: dict[str, float],
    min_duration: float = 0.15,
) -> WorkflowResult:
    new_state = clone_state(state)
    if winner not in ("A", "B"):
        return WorkflowResult(new_state, allowed=False, changed=False, reason="invalid_winner")
    if new_state.capture_state not in (CaptureState.RECORDING.value, CaptureState.PAUSED_WITHIN_POINT.value):
        return WorkflowResult(new_state, allowed=False, changed=False, reason="not_in_progress")

    if new_state.capture_state == CaptureState.RECORDING.value:
        paused = pause_clip_session(
            new_state,
            now=now,
            end_source=end_source,
            source_order=source_order,
            source_duration_map=source_duration_map,
            min_duration=min_duration,
        )
        if not paused.allowed:
            return WorkflowResult(new_state, allowed=False, changed=False, reason=paused.reason)
        new_state = paused.state

    point_idx = get_open_point_index(new_state.points, new_state.open_point_id)
    if point_idx is None:
        return WorkflowResult(new_state, allowed=False, changed=False, reason="invalid_open_point")
    point = new_state.points[point_idx]
    if len(point.clips) == 0:
        return WorkflowResult(new_state, allowed=False, changed=False, reason="empty_point")

    point.winner = winner
    finalized_id = point.id
    new_state.capture_state = CaptureState.IDLE.value
    reset_open_capture_fields(new_state)
    new_state.selected_point_id = finalized_id
    return WorkflowResult(
        new_state,
        allowed=True,
        changed=True,
        reason="finalized",
        finalized_point_id=finalized_id,
    )


def cancel_open_point_session(state: WorkflowState) -> WorkflowResult:
    new_state = clone_state(state)
    if new_state.capture_state == CaptureState.IDLE.value:
        return WorkflowResult(new_state, allowed=False, changed=False, reason="nothing_to_cancel")

    open_idx = get_open_point_index(new_state.points, new_state.open_point_id)
    if open_idx is not None:
        del new_state.points[open_idx]

    new_state.capture_state = CaptureState.IDLE.value
    reset_open_capture_fields(new_state)
    return WorkflowResult(new_state, allowed=True, changed=True, reason="cancelled")


def remove_last_point(state: WorkflowState) -> WorkflowResult:
    new_state = clone_state(state)
    if not new_state.points:
        return WorkflowResult(new_state, allowed=False, changed=False, reason="no_points")
    if not can_remove_last_point(new_state.points, new_state.selected_point_id, new_state.capture_state):
        return WorkflowResult(new_state, allowed=False, changed=False, reason="remove_not_allowed")

    removed = new_state.points.pop()
    new_state.capture_state = CaptureState.IDLE.value
    reset_open_capture_fields(new_state)
    if new_state.points:
        new_state.selected_point_id = new_state.points[-1].id
    else:
        new_state.selected_point_id = None

    return WorkflowResult(
        new_state,
        allowed=True,
        changed=True,
        reason="removed_last_point",
        removed_point_id=removed.id,
    )
