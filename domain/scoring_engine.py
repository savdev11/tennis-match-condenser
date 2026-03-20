from __future__ import annotations

from domain.models import MatchRuntimeState, MatchSettingsSnapshot, PointRecord


def opponent(side: str) -> str:
    return "B" if side == "A" else "A"


def initial_runtime_state(settings: MatchSettingsSnapshot) -> MatchRuntimeState:
    initial_server = settings.initial_server if settings.initial_server in ("A", "B") else "A"
    return MatchRuntimeState(
        starting_server=initial_server,
        current_server=initial_server,
        tiebreak_first_server=None,
        points_a=0,
        points_b=0,
        tb_points_a=0,
        tb_points_b=0,
        games_a=0,
        games_b=0,
        sets_a=0,
        sets_b=0,
        completed_sets=[],
        completed_set_tb_loser_points=[],
        in_tiebreak=False,
        tiebreak_target=7,
        tiebreak_super=False,
    )


def runtime_start_tiebreak(state: MatchRuntimeState, target: int, super_mode: bool) -> None:
    state.in_tiebreak = True
    state.tiebreak_target = target
    state.tiebreak_super = super_mode
    state.tiebreak_first_server = state.current_server
    state.points_a = 0
    state.points_b = 0
    state.tb_points_a = 0
    state.tb_points_b = 0


def runtime_award_set_from_tiebreak(state: MatchRuntimeState, side: str) -> None:
    if state.tiebreak_super:
        final_games = (state.tb_points_a, state.tb_points_b)
        state.completed_set_tb_loser_points.append(None)
    else:
        final_games = (7, 6) if side == "A" else (6, 7)
        loser_tb = state.tb_points_b if side == "A" else state.tb_points_a
        state.completed_set_tb_loser_points.append(loser_tb)
    state.completed_sets.append(final_games)
    if side == "A":
        state.sets_a += 1
    else:
        state.sets_b += 1
    state.games_a = 0
    state.games_b = 0
    state.points_a = 0
    state.points_b = 0
    state.tb_points_a = 0
    state.tb_points_b = 0
    state.in_tiebreak = False
    state.tiebreak_super = False
    state.tiebreak_target = 7
    if state.tiebreak_first_server in ("A", "B"):
        state.current_server = opponent(state.tiebreak_first_server)
    state.tiebreak_first_server = None


def runtime_award_game(state: MatchRuntimeState, side: str, settings: MatchSettingsSnapshot) -> None:
    if side == "A":
        state.games_a += 1
    else:
        state.games_b += 1
    state.points_a = 0
    state.points_b = 0
    state.current_server = opponent(state.current_server)
    if state.games_a == 6 and state.games_b == 6:
        runtime_start_tiebreak(state, 7, False)
        return
    set_ended = False
    if state.games_a >= 6 and state.games_a - state.games_b >= 2:
        state.completed_sets.append((state.games_a, state.games_b))
        state.completed_set_tb_loser_points.append(None)
        state.sets_a += 1
        state.games_a = 0
        state.games_b = 0
        set_ended = True
    elif state.games_b >= 6 and state.games_b - state.games_a >= 2:
        state.completed_sets.append((state.games_a, state.games_b))
        state.completed_set_tb_loser_points.append(None)
        state.sets_b += 1
        state.games_a = 0
        state.games_b = 0
        set_ended = True
    if (
        set_ended
        and settings.best_of_index == 0
        and settings.deciding_set_mode_index == 1
        and state.sets_a == 1
        and state.sets_b == 1
    ):
        runtime_start_tiebreak(state, 10, True)


def runtime_apply_point_winner(state: MatchRuntimeState, side: str, settings: MatchSettingsSnapshot) -> None:
    if state.in_tiebreak:
        if side == "A":
            state.tb_points_a += 1
        else:
            state.tb_points_b += 1
        a_tb, b_tb = state.tb_points_a, state.tb_points_b
        total_tb_points = a_tb + b_tb
        if a_tb >= state.tiebreak_target and a_tb - b_tb >= 2:
            runtime_award_set_from_tiebreak(state, "A")
        elif b_tb >= state.tiebreak_target and b_tb - a_tb >= 2:
            runtime_award_set_from_tiebreak(state, "B")
        elif total_tb_points % 2 == 1:
            state.current_server = opponent(state.current_server)
        return
    if side == "A":
        a, b = state.points_a, state.points_b
        if a <= 2:
            state.points_a += 1
        elif a == 3 and b <= 2:
            runtime_award_game(state, "A", settings)
        elif a == 3 and b == 3:
            state.points_a = 4
        elif a == 4:
            runtime_award_game(state, "A", settings)
        elif b == 4:
            state.points_b = 3
        return
    a, b = state.points_a, state.points_b
    if b <= 2:
        state.points_b += 1
    elif b == 3 and a <= 2:
        runtime_award_game(state, "B", settings)
    elif b == 3 and a == 3:
        state.points_b = 4
    elif b == 4:
        runtime_award_game(state, "B", settings)
    elif a == 4:
        state.points_a = 3


def replay_runtime_state(
    points: list[PointRecord],
    settings: MatchSettingsSnapshot,
    stop_before_point_id: int | None = None,
    stop_after_point_id: int | None = None,
) -> MatchRuntimeState:
    state = initial_runtime_state(settings)
    ordered_points = sorted(points, key=lambda point: point.id)
    for point in ordered_points:
        if point.winner not in ("A", "B"):
            continue
        if stop_before_point_id is not None and point.id >= stop_before_point_id:
            break
        runtime_apply_point_winner(state, point.winner, settings)
        if stop_after_point_id is not None and point.id == stop_after_point_id:
            break
    return state


def derive_match_state_before_point(points: list[PointRecord], settings: MatchSettingsSnapshot, point_id: int) -> MatchRuntimeState:
    return replay_runtime_state(points, settings, stop_before_point_id=point_id)


def derive_match_state_after_point(points: list[PointRecord], settings: MatchSettingsSnapshot, point_id: int) -> MatchRuntimeState:
    return replay_runtime_state(points, settings, stop_after_point_id=point_id)


def get_server_for_point(points: list[PointRecord], settings: MatchSettingsSnapshot, point_id: int) -> str:
    return derive_match_state_before_point(points, settings, point_id).current_server
