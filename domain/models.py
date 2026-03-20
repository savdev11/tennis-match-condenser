from dataclasses import dataclass, field


@dataclass
class OverlayState:
    player_a: str
    player_b: str
    sets_a: int
    sets_b: int
    games_a: int
    games_b: int
    points_a: str
    points_b: str
    server: str
    tournament: str
    overlay_corner: str
    overlay_scale: float
    set_col1_a: str
    set_col1_b: str
    set_col2_a: str
    set_col2_b: str
    alert_banner: str
    flag_a_code: str = ""
    flag_b_code: str = ""
    flag_a_path: str = ""
    flag_b_path: str = ""


@dataclass
class Segment:
    start: float
    end: float
    source_path: str
    overlay: OverlayState
    is_highlight: bool = False


@dataclass
class PointClip:
    start: float
    end: float
    source_path: str


@dataclass
class PointRecord:
    id: int
    winner: str | None
    is_highlight: bool
    clips: list[PointClip] = field(default_factory=list)
    overlay_at_start: OverlayState | None = None
    overlay_at_end: OverlayState | None = None


@dataclass
class MatchRuntimeState:
    starting_server: str
    current_server: str
    tiebreak_first_server: str | None
    points_a: int
    points_b: int
    tb_points_a: int
    tb_points_b: int
    games_a: int
    games_b: int
    sets_a: int
    sets_b: int
    completed_sets: list[tuple[int, int]]
    completed_set_tb_loser_points: list[int | None]
    in_tiebreak: bool
    tiebreak_target: int
    tiebreak_super: bool


@dataclass
class MatchSettingsSnapshot:
    player_a: str
    player_b: str
    rank_a: str
    rank_b: str
    tournament: str
    round_name: str
    best_of_index: int
    deciding_set_mode_index: int
    initial_server: str
    overlay_corner: str
    overlay_scale: float
    flag_a_code: str = ""
    flag_b_code: str = ""
    flag_a_path: str = ""
    flag_b_path: str = ""
