from __future__ import annotations

from domain.models import MatchRuntimeState, MatchSettingsSnapshot, OverlayState, PointRecord
from domain.enums import CaptureState
from domain import scoring_engine


def points_text(points: int) -> str:
    if points <= 0:
        return "0"
    if points == 1:
        return "15"
    if points == 2:
        return "30"
    if points == 3:
        return "40"
    return "AD"


def runtime_active_points_text(state: MatchRuntimeState) -> tuple[str, str]:
    if state.in_tiebreak:
        return str(state.tb_points_a), str(state.tb_points_b)
    return points_text(state.points_a), points_text(state.points_b)


def overlay_set_columns_from_runtime(state: MatchRuntimeState) -> tuple[str, str, str, str]:
    set1_a = ""
    set1_b = ""
    set2_a = ""
    set2_b = ""
    if len(state.completed_sets) >= 1:
        set1_a = str(state.completed_sets[0][0])
        set1_b = str(state.completed_sets[0][1])
    else:
        set1_a = str(state.games_a)
        set1_b = str(state.games_b)
    if len(state.completed_sets) >= 2:
        set2_a = str(state.completed_sets[1][0])
        set2_b = str(state.completed_sets[1][1])
    elif len(state.completed_sets) == 1:
        set2_a = str(state.games_a)
        set2_b = str(state.games_b)
    return set1_a, set1_b, set2_a, set2_b


def wins_game_on_point_runtime(side: str, state: MatchRuntimeState) -> bool:
    if state.in_tiebreak:
        return False
    if side == "A":
        if state.points_a <= 2:
            return False
        if state.points_a == 3 and state.points_b <= 2:
            return True
        return state.points_a == 4
    if state.points_b <= 2:
        return False
    if state.points_b == 3 and state.points_a <= 2:
        return True
    return state.points_b == 4


def set_winner_if_point_won_runtime(side: str, state: MatchRuntimeState) -> str | None:
    if state.in_tiebreak:
        a_tb = state.tb_points_a + (1 if side == "A" else 0)
        b_tb = state.tb_points_b + (1 if side == "B" else 0)
        if a_tb >= state.tiebreak_target and a_tb - b_tb >= 2:
            return "A"
        if b_tb >= state.tiebreak_target and b_tb - a_tb >= 2:
            return "B"
        return None
    if not wins_game_on_point_runtime(side, state):
        return None
    new_games_a = state.games_a + (1 if side == "A" else 0)
    new_games_b = state.games_b + (1 if side == "B" else 0)
    if new_games_a >= 6 and new_games_a - new_games_b >= 2:
        return "A"
    if new_games_b >= 6 and new_games_b - new_games_a >= 2:
        return "B"
    return None


def match_winner_if_point_won_runtime(side: str, state: MatchRuntimeState, settings: MatchSettingsSnapshot) -> str | None:
    set_winner = set_winner_if_point_won_runtime(side, state)
    if not set_winner:
        return None
    needed_sets = 2 if settings.best_of_index == 0 else 3
    new_sets_a = state.sets_a + (1 if set_winner == "A" else 0)
    new_sets_b = state.sets_b + (1 if set_winner == "B" else 0)
    if new_sets_a >= needed_sets:
        return "A"
    if new_sets_b >= needed_sets:
        return "B"
    return None


def alert_banner_from_runtime(state: MatchRuntimeState, settings: MatchSettingsSnapshot) -> str:
    if match_winner_if_point_won_runtime("A", state, settings) or match_winner_if_point_won_runtime("B", state, settings):
        return "MATCH POINT"
    if set_winner_if_point_won_runtime("A", state) or set_winner_if_point_won_runtime("B", state):
        return "SET POINT"
    receiver = scoring_engine.opponent(state.current_server)
    if wins_game_on_point_runtime(receiver, state):
        return "BREAK POINT"
    return ""


def overlay_state_from_runtime(state: MatchRuntimeState, settings: MatchSettingsSnapshot) -> OverlayState:
    points_a_text, points_b_text = runtime_active_points_text(state)
    set1_a, set1_b, set2_a, set2_b = overlay_set_columns_from_runtime(state)
    return OverlayState(
        player_a=settings.player_a,
        player_b=settings.player_b,
        sets_a=state.sets_a,
        sets_b=state.sets_b,
        games_a=state.games_a,
        games_b=state.games_b,
        points_a=points_a_text,
        points_b=points_b_text,
        server=state.current_server,
        tournament=settings.tournament,
        overlay_corner=settings.overlay_corner,
        overlay_scale=settings.overlay_scale,
        set_col1_a=set1_a,
        set_col1_b=set1_b,
        set_col2_a=set2_a,
        set_col2_b=set2_b,
        alert_banner=alert_banner_from_runtime(state, settings),
        flag_a_code=settings.flag_a_code,
        flag_b_code=settings.flag_b_code,
        flag_a_path=settings.flag_a_path,
        flag_b_path=settings.flag_b_path,
    )


def point_source_bounds(point: PointRecord, source_path: str) -> tuple[float, float] | None:
    source_clips = [clip for clip in point.clips if clip.source_path == source_path]
    if not source_clips:
        return None
    start = min(clip.start for clip in source_clips)
    end = max(clip.end for clip in source_clips)
    return (start, end)


def resolve_point_selection_for_position(points: list[PointRecord], source_path: str, local_t: float) -> int | None:
    source_entries: list[tuple[int, float, float]] = []
    for idx, point in enumerate(points):
        bounds = point_source_bounds(point, source_path)
        if bounds is None:
            continue
        source_entries.append((idx, bounds[0], bounds[1]))
    if not source_entries:
        return None
    source_entries.sort(key=lambda item: (item[1], points[item[0]].id))
    first_idx, first_start, _ = source_entries[0]
    if local_t < first_start:
        return None
    prev_idx = first_idx
    for idx, start, end in source_entries:
        if start <= local_t <= end:
            return idx
        if local_t < start:
            return prev_idx
        prev_idx = idx
    return prev_idx


def derive_overlay_state_before_point(points: list[PointRecord], settings: MatchSettingsSnapshot, point_id: int) -> OverlayState:
    state = scoring_engine.derive_match_state_before_point(points, settings, point_id)
    return overlay_state_from_runtime(state, settings)


def derive_overlay_state_after_point(points: list[PointRecord], settings: MatchSettingsSnapshot, point_id: int) -> OverlayState:
    state = scoring_engine.derive_match_state_after_point(points, settings, point_id)
    return overlay_state_from_runtime(state, settings)


def derive_overlay_state_for_position(
    points: list[PointRecord],
    source_path: str,
    local_time: float,
    settings: MatchSettingsSnapshot,
    capture_state: str,
    open_point_id: int | None,
    live_overlay_state: OverlayState,
) -> OverlayState | None:
    point_idx = resolve_point_selection_for_position(points, source_path, local_time)
    if point_idx is None or point_idx < 0 or point_idx >= len(points):
        return None
    point = points[point_idx]
    if point.winner in ("A", "B"):
        bounds = point_source_bounds(point, source_path)
        if bounds is None:
            return derive_overlay_state_before_point(points, settings, point.id)
        point_start, point_end = bounds
        if point_start <= local_time <= point_end:
            return derive_overlay_state_before_point(points, settings, point.id)
        if local_time > point_end:
            return derive_overlay_state_after_point(points, settings, point.id)
        return derive_overlay_state_before_point(points, settings, point.id)
    if capture_state in (CaptureState.RECORDING.value, CaptureState.PAUSED_WITHIN_POINT.value) and open_point_id == point.id:
        return live_overlay_state
    return derive_overlay_state_before_point(points, settings, point.id)
