import os
import re
import subprocess
import sys
import tempfile
import json
import time
from dataclasses import asdict, dataclass, field
import urllib.error
import urllib.request
import ssl
from typing import Literal

import imageio_ffmpeg
from PySide6.QtCore import QStandardPaths, QThread, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QKeySequence, QShortcut, QFont, QPixmap, QImage
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QKeySequenceEdit,
    QStackedLayout,
    QDialogButtonBox,
)
from ui_shell import UIShell
from ui_theme import apply_app_theme

APP_VERSION = "1.6.0"
OVERLAY_SCALE_PRESETS = {
    "80%": 1.10,
    "100%": 1.35,
    "120%": 1.60,
    "140%": 1.80,
    "160%": 2.00,
}


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


def format_time(seconds: float) -> str:
    total = max(0, int(seconds))
    hours = total // 3600
    mins = (total % 3600) // 60
    secs = total % 60
    if hours > 0:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


def ffmpeg_escape_text(text: str) -> str:
    escaped = text.replace("\\", "\\\\")
    escaped = escaped.replace(":", r"\:")
    escaped = escaped.replace("'", r"\'")
    escaped = escaped.replace("%", r"\%")
    escaped = escaped.replace(",", r"\,")
    return escaped


def ffmpeg_escape_path(path: str) -> str:
    escaped = path.replace("\\", "\\\\")
    escaped = escaped.replace(":", r"\:")
    escaped = escaped.replace("'", r"\'")
    return escaped


def normalize_flag_code(value: str) -> str:
    clean = re.sub(r"[^A-Za-z]", "", (value or "").strip())
    if len(clean) < 2:
        return ""
    return clean[:2].upper()


def detect_fontfile() -> str:
    candidates = [
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return ""


FONTFILE = detect_fontfile()
FONT_OPT = f":fontfile={FONTFILE}" if FONTFILE else ""


def detect_mono_fontfile() -> str:
    candidates = [
        "/System/Library/Fonts/Supplemental/Menlo.ttc",
        "/System/Library/Fonts/Supplemental/Courier New Bold.ttf",
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/cour.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return ""


MONO_FONTFILE = detect_mono_fontfile()
MONO_FONT_OPT = f":fontfile={MONO_FONTFILE}" if MONO_FONTFILE else FONT_OPT


def build_overlay_filter(ov: OverlayState) -> str:
    scale = max(0.7, min(ov.overlay_scale, 2.0))
    title_font = int(14 * scale)
    name_font = int(22 * scale)
    num_font = int(28 * scale)
    banner_font = int(18 * scale)
    line_thick = max(1, int(1 * scale))
    row_h = int(52 * scale)
    row_gap = int(1 * scale)
    title_h = int(28 * scale)
    table_top = title_h
    col_name_w = int(392 * scale)
    col_w = int(86 * scale)
    flag_w = int(52 * scale)
    flag_h = row_h
    box_w = col_name_w + col_w * 3
    banner_h = int(34 * scale)
    banner_gap = int(8 * scale)
    box_h = table_top + row_h * 2 + row_gap
    banner_extra = banner_gap + banner_h if ov.alert_banner else 0
    total_h = box_h + banner_extra

    if ov.overlay_corner == "Top Right":
        base_x = f"iw-{box_w}-20"  # drawbox expression
        base_y = "20"  # drawbox expression
        text_base_x = f"w-{box_w}-20"  # drawtext expression
        text_base_y = "20"  # drawtext expression
        ov_base_x = f"W-{box_w}-20"  # overlay filter expression
        ov_base_y = "20"  # overlay filter expression
    elif ov.overlay_corner == "Bottom Left":
        base_x = "20"
        base_y = f"ih-{total_h}-20"
        text_base_x = "20"
        text_base_y = f"h-{total_h}-20"
        ov_base_x = "20"
        ov_base_y = f"H-{total_h}-20"
    elif ov.overlay_corner == "Bottom Right":
        base_x = f"iw-{box_w}-20"
        base_y = f"ih-{total_h}-20"
        text_base_x = f"w-{box_w}-20"
        text_base_y = f"h-{total_h}-20"
        ov_base_x = f"W-{box_w}-20"
        ov_base_y = f"H-{total_h}-20"
    else:
        base_x = "20"
        base_y = "20"
        text_base_x = "20"
        text_base_y = "20"
        ov_base_x = "20"
        ov_base_y = "20"

    title = ffmpeg_escape_text(ov.tournament.upper())
    name_a = ffmpeg_escape_text((ov.player_a or "Giocatore A").upper()[:18])
    name_b = ffmpeg_escape_text((ov.player_b or "Giocatore B").upper()[:18])
    set1_a = ffmpeg_escape_text(str(ov.set_col1_a))
    set1_b = ffmpeg_escape_text(str(ov.set_col1_b))
    set2_a = ffmpeg_escape_text(str(ov.set_col2_a))
    set2_b = ffmpeg_escape_text(str(ov.set_col2_b))
    pts_a = ffmpeg_escape_text(str(ov.points_a))
    pts_b = ffmpeg_escape_text(str(ov.points_b))
    banner = ffmpeg_escape_text(ov.alert_banner)
    bx = f"({text_base_x})"
    by = f"({text_base_y})"
    bbx = f"({base_x})"
    bby = f"({base_y})"
    obx = f"({ov_base_x})"
    oby = f"({ov_base_y})"
    table_x0 = bbx
    table_x1 = f"{bbx}+{col_name_w}"
    table_x2 = f"{bbx}+{col_name_w + col_w}"
    table_x3 = f"{bbx}+{col_name_w + col_w * 2}"
    table_x4 = f"{bbx}+{col_name_w + col_w * 3}"
    text_table_x0 = bx
    text_table_x1 = f"{bx}+{col_name_w}"
    text_table_x2 = f"{bx}+{col_name_w + col_w}"
    text_table_x3 = f"{bx}+{col_name_w + col_w * 2}"
    table_y1 = f"{bby}+{table_top}"
    table_y2 = f"{bby}+{table_top + row_h + row_gap}"
    text_table_y1 = f"{by}+{table_top}"
    text_table_y2 = f"{by}+{table_top + row_h + row_gap}"
    row_a_name_y = f"{by}+{table_top + int(14 * scale)}"
    row_b_name_y = f"{by}+{table_top + row_h + row_gap + int(14 * scale)}"
    row_a_num_y = f"{text_table_y1}+({row_h}-text_h)/2"
    row_b_num_y = f"{text_table_y2}+({row_h}-text_h)/2"
    serve_w = max(4, int(6 * scale))
    flag_a_x = f"{obx}+{serve_w}"
    flag_b_x = f"{obx}+{serve_w}"
    flag_a_y = f"{oby}+{table_top + int(0 * scale)}"
    flag_b_y = f"{oby}+{table_top + row_h + row_gap + int(0 * scale)}"
    name_x = f"{text_table_x0}+{int(68 * scale)}"
    set1_x = f"{text_table_x1}+({col_w}-text_w)/2"
    set2_x = f"{text_table_x2}+({col_w}-text_w)/2"
    pts_x = f"{text_table_x3}+({col_w}-text_w)/2"
    base_filters = [
        f"drawbox=x={base_x}:y={base_y}:w={box_w}:h={title_h}:color=#8e3f1f@0.95:t=fill",
        f"drawbox=x={base_x}:y={base_y}:w={box_w}:h={title_h}:color=#b5542a@0.95:t=1",
        f"drawtext=text='{title}':x={bx}+{int(10 * scale)}:y={by}+({title_h}-text_h)/2:fontcolor=#ede8e0:fontsize={title_font}{FONT_OPT}",
        f"drawbox=x={table_x0}:y={table_y1}:w={col_name_w + col_w * 3}:h={row_h}:color=#111318@0.88:t=fill",
        f"drawbox=x={table_x0}:y={table_y2}:w={col_name_w + col_w * 3}:h={row_h}:color=#181c22@0.88:t=fill",
        f"drawbox=x={table_x3}:y={table_y1}:w={col_w}:h={row_h}:color=#222831@0.95:t=fill",
        f"drawbox=x={table_x3}:y={table_y2}:w={col_w}:h={row_h}:color=#222831@0.95:t=fill",
        f"drawbox=x={table_x0}:y={table_y1}+{row_h}:w={col_name_w + col_w * 3}:h={line_thick}:color=#2c333d:t=fill",
        f"drawbox=x={table_x1}:y={table_y1}:w={line_thick}:h={row_h * 2 + row_gap}:color=#2c333d:t=fill",
        f"drawbox=x={table_x2}:y={table_y1}:w={line_thick}:h={row_h * 2 + row_gap}:color=#2c333d:t=fill",
        f"drawbox=x={table_x3}:y={table_y1}:w={line_thick}:h={row_h * 2 + row_gap}:color=#2c333d:t=fill",
        f"drawbox=x={table_x4}:y={table_y1}:w={line_thick}:h={row_h * 2 + row_gap}:color=#2c333d:t=fill",
        f"drawbox=x={table_x0}:y={table_y2}+{row_h}:w={col_name_w + col_w * 3}:h={line_thick}:color=#2c333d:t=fill",
        f"drawtext=text='{name_a}':x={name_x}:y={row_a_name_y}:fontcolor=#ede8e0:fontsize={name_font}{FONT_OPT}",
        f"drawtext=text='{name_b}':x={name_x}:y={row_b_name_y}:fontcolor=#ede8e0:fontsize={name_font}{FONT_OPT}",
        f"drawtext=text='{set1_a}':x={set1_x}:y={row_a_num_y}:fontcolor=#5d86ff:fontsize={num_font}{FONT_OPT}",
        f"drawtext=text='{set1_b}':x={set1_x}:y={row_b_num_y}:fontcolor=#5d86ff:fontsize={num_font}{FONT_OPT}",
        f"drawtext=text='{set2_a}':x={set2_x}:y={row_a_num_y}:fontcolor=#5d86ff:fontsize={num_font}{FONT_OPT}",
        f"drawtext=text='{set2_b}':x={set2_x}:y={row_b_num_y}:fontcolor=#5d86ff:fontsize={num_font}{FONT_OPT}",
        f"drawtext=text='{pts_a}':x={pts_x}:y={row_a_num_y}:fontcolor=#ede8e0:fontsize={num_font}{FONT_OPT}",
        f"drawtext=text='{pts_b}':x={pts_x}:y={row_b_num_y}:fontcolor=#ede8e0:fontsize={num_font}{FONT_OPT}",
    ]

    # Serve indicator (with neutral line on non-server side for symmetry).
    serve_x = table_x0
    serve_h = row_h
    serve_a_y = table_y1
    serve_b_y = table_y2
    serve_a_color = "#d6ff3f" if ov.server == "A" else "#1d2128"
    serve_b_color = "#d6ff3f" if ov.server == "B" else "#1d2128"
    base_filters.append(
        f"drawbox=x={serve_x}:y={serve_a_y}:w={serve_w}:h={serve_h}:color={serve_a_color}:t=fill"
    )
    base_filters.append(
        f"drawbox=x={serve_x}:y={serve_b_y}:w={serve_w}:h={serve_h}:color={serve_b_color}:t=fill"
    )

    flag_a = ov.flag_a_path if ov.flag_a_path and os.path.exists(ov.flag_a_path) else ""
    flag_b = ov.flag_b_path if ov.flag_b_path and os.path.exists(ov.flag_b_path) else ""
    if banner:
        banner_w = col_name_w + col_w * 3
        banner_x = table_x0
        banner_y = f"{bby}+{box_h}+{banner_gap}"
        banner_text_x = f"{text_table_x0}+({banner_w}-text_w)/2"
        banner_text_y = f"{by}+{box_h}+{banner_gap}+({banner_h}-text_h)/2"
        base_filters.append(
            f"drawbox=x={banner_x}:y={banner_y}:w={banner_w}:h={banner_h}:color=#f8d24a@0.96:t=fill"
        )
        base_filters.append(
            f"drawtext=text='{banner}':x={banner_text_x}:y={banner_text_y}:"
            f"fontcolor=#1e2532:fontsize={banner_font}{FONT_OPT}"
        )
    parts = [f"[0:v]{','.join(base_filters)}[base]"]
    current = "base"
    if flag_a:
        parts.append(f"movie='{ffmpeg_escape_path(flag_a)}',scale={flag_w}:{flag_h}[flagA]")
        parts.append(f"[{current}][flagA]overlay=x={flag_a_x}:y={flag_a_y}[base1]")
        current = "base1"
    if flag_b:
        parts.append(f"movie='{ffmpeg_escape_path(flag_b)}',scale={flag_w}:{flag_h}[flagB]")
        parts.append(f"[{current}][flagB]overlay=x={flag_b_x}:y={flag_b_y}[base2]")
        current = "base2"
    parts.append(f"[{current}]null[out]")
    return ";".join(parts)


def build_title_card_filter(lines: list[str]) -> str:
    clean_lines = [ffmpeg_escape_text(line) for line in lines if line and line.strip()]
    if not clean_lines:
        clean_lines = [ffmpeg_escape_text("Tennis Match")]
    line_count = min(len(clean_lines), 14)
    first_size = 50 if line_count <= 6 else 42
    second_size = 30
    other_size = 26
    step = 44 if line_count <= 8 else 36
    block_h = 210 + line_count * step
    block_y = max(100, int((1080 - block_h) / 2))
    text_start = block_y + 56
    filters = [
        "scale=1920:1080:force_original_aspect_ratio=increase",
        "crop=1920:1080",
        f"drawbox=x=90:y={block_y}:w=1740:h={block_h}:color=white@0.78:t=fill",
        f"drawbox=x=90:y={block_y}:w=1740:h={block_h}:color=#d4dbea:t=2",
    ]
    for idx, line in enumerate(clean_lines[:14]):
        if idx == 0:
            size = first_size
            color = "#1f2d3d"
        elif idx == 1:
            size = second_size
            color = "#44526a"
        else:
            size = other_size
            color = "#1f4fcb"
        y = text_start + idx * step
        filters.append(
            f"drawtext=text='{line}':x=(w-text_w)/2:y={y}:fontcolor={color}:fontsize={size}{FONT_OPT}"
        )
    return ",".join(filters)


class VideoOverlayContainer(QWidget):
    clicked = Signal()

    def __init__(self, video_widget: QVideoWidget, overlay_widget: QWidget) -> None:
        super().__init__()
        self.video_widget = video_widget
        self.overlay_widget = overlay_widget
        self.overlay_corner = "Top Left"
        self.video_widget.setParent(self)
        self.overlay_widget.setParent(self)
        self.overlay_widget.raise_()
        self.overlay_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def resizeEvent(self, event) -> None:  # noqa: N802
        self.video_widget.setGeometry(self.rect())
        self.overlay_widget.adjustSize()
        self.position_overlay()
        super().resizeEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.clicked.emit()
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        super().mousePressEvent(event)

    def set_overlay_corner(self, corner: str) -> None:
        self.overlay_corner = corner
        self.position_overlay()

    def position_overlay(self) -> None:
        margin_x = 20
        margin_y = 18
        ow = self.overlay_widget.width()
        oh = self.overlay_widget.height()
        w = self.width()
        h = self.height()
        if self.overlay_corner == "Top Right":
            x = max(0, w - ow - margin_x)
            y = margin_y
        elif self.overlay_corner == "Bottom Left":
            x = margin_x
            y = max(0, h - oh - margin_y)
        elif self.overlay_corner == "Bottom Right":
            x = max(0, w - ow - margin_x)
            y = max(0, h - oh - margin_y)
        else:
            x = margin_x
            y = margin_y
        self.overlay_widget.move(x, y)


class ScoreboardOverlayWidget(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("scoreboard")
        self.scale_factor = 1.0

        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(0, 0, 0, 0)
        self.root.setSpacing(0)
        self.font_specs: dict[QLabel, tuple[int, int, str]] = {}

        self.table_card = QFrame()
        self.table_card.setObjectName("scoreboard_card")
        self.card_layout = QVBoxLayout(self.table_card)
        self.card_layout.setContentsMargins(0, 0, 0, 0)
        self.card_layout.setSpacing(0)

        self.alert_label = QLabel("")
        self.alert_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._register_label(self.alert_label, 10, 800, "#173067")
        self.alert_label.setVisible(False)

        self.tournament_label = QLabel("AMATEUR TENNIS TOUR")
        self._register_label(self.tournament_label, 13, 700, "#2f394a")
        self.root.addWidget(self.tournament_label)
        self.root.addWidget(self.table_card)
        self.root.addWidget(self.alert_label)

        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(0)
        self.grid.setVerticalSpacing(0)
        self.card_layout.addLayout(self.grid)

        self.player_a_name = QLabel("Giocatore A")
        self.player_b_name = QLabel("Giocatore B")
        self._register_label(self.player_a_name, 15, 700, "#1f2d3d")
        self._register_label(self.player_b_name, 15, 700, "#1f2d3d")
        self.player_a_name.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.player_b_name.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.player_a_set1 = QLabel("0")
        self.player_b_set1 = QLabel("0")
        self.player_a_set2 = QLabel("")
        self.player_b_set2 = QLabel("")
        self.player_a_pts = QLabel("0")
        self.player_b_pts = QLabel("0")
        numeric_labels = [
            self.player_a_set1,
            self.player_b_set1,
            self.player_a_set2,
            self.player_b_set2,
            self.player_a_pts,
            self.player_b_pts,
        ]
        for label in numeric_labels:
            self._register_label(label, 21, 800, "#1b4fd8")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.flag_a_label = QLabel("")
        self.flag_b_label = QLabel("")
        self.flag_a_label.setFixedSize(50, 48)
        self.flag_b_label.setFixedSize(50, 48)
        self.flag_a_label.setScaledContents(True)
        self.flag_b_label.setScaledContents(True)
        self.flag_a_label.setContentsMargins(0, 0, 0, 0)
        self.flag_b_label.setContentsMargins(0, 0, 0, 0)

        self.serv_bar_a = QFrame()
        self.serv_bar_b = QFrame()
        self.serv_bar_a.setFixedWidth(3)
        self.serv_bar_b.setFixedWidth(3)
        self.row_a = QWidget()
        self.row_b = QWidget()
        row_a = QWidget()
        row_a_layout = QHBoxLayout(row_a)
        row_a_layout.setContentsMargins(0, 0, 0, 0)
        row_a_layout.setSpacing(0)
        row_a_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        row_a_layout.addWidget(self.serv_bar_a)
        row_a_layout.addWidget(self.flag_a_label)
        row_a_layout.addSpacing(6)
        row_a_layout.addWidget(self.player_a_name)
        row_a_layout.addStretch()

        row_b = QWidget()
        row_b_layout = QHBoxLayout(row_b)
        row_b_layout.setContentsMargins(0, 0, 0, 0)
        row_b_layout.setSpacing(0)
        row_b_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        row_b_layout.addWidget(self.serv_bar_b)
        row_b_layout.addWidget(self.flag_b_label)
        row_b_layout.addSpacing(6)
        row_b_layout.addWidget(self.player_b_name)
        row_b_layout.addStretch()
        self.row_a = row_a
        self.row_b = row_b

        self.grid.addWidget(row_a, 0, 0)
        self.grid.addWidget(self.player_a_set1, 0, 1)
        self.grid.addWidget(self.player_a_set2, 0, 2)
        self.grid.addWidget(self.player_a_pts, 0, 3)

        self.grid.addWidget(row_b, 1, 0)
        self.grid.addWidget(self.player_b_set1, 1, 1)
        self.grid.addWidget(self.player_b_set2, 1, 2)
        self.grid.addWidget(self.player_b_pts, 1, 3)

        self.apply_scale(1.0)

    def _register_label(self, label: QLabel, size: int, weight: int, color: str) -> None:
        self.font_specs[label] = (size, weight, color)

    def _qt_font_weight(self, weight: int) -> QFont.Weight:
        if weight >= 800:
            return QFont.Weight.Black
        if weight >= 700:
            return QFont.Weight.Bold
        if weight >= 600:
            return QFont.Weight.DemiBold
        return QFont.Weight.Normal

    def apply_scale(self, factor: float) -> None:
        self.scale_factor = max(0.7, min(factor, 2.0))
        self.card_layout.setContentsMargins(0, 0, 0, 0)
        self.card_layout.setSpacing(0)
        self.root.setSpacing(0)
        self.grid.setHorizontalSpacing(0)
        self.grid.setVerticalSpacing(0)
        self.grid.setColumnMinimumWidth(0, int(370 * self.scale_factor))
        self.grid.setColumnMinimumWidth(1, int(84 * self.scale_factor))
        self.grid.setColumnMinimumWidth(2, int(84 * self.scale_factor))
        self.grid.setColumnMinimumWidth(3, int(84 * self.scale_factor))
        self.grid.setColumnStretch(0, 1)
        table_w = int((370 + 84 + 84 + 84) * self.scale_factor)

        radius = int(4 * self.scale_factor)
        self.serv_bar_a.setFixedWidth(max(4, int(6 * self.scale_factor)))
        self.serv_bar_b.setFixedWidth(max(4, int(6 * self.scale_factor)))
        row_h_px = int(50 * self.scale_factor)
        flag_h_px = max(20, row_h_px)
        self.flag_a_label.setFixedSize(int(50 * self.scale_factor), flag_h_px)
        self.flag_b_label.setFixedSize(int(50 * self.scale_factor), flag_h_px)
        self.tournament_label.setFixedWidth(table_w)
        self.tournament_label.setMinimumHeight(int(28 * self.scale_factor))
        self.tournament_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.alert_label.setStyleSheet(
            f"background: #f8d24a; border-radius: {int(2 * self.scale_factor)}px; padding: {max(4, int(6 * self.scale_factor))}px;"
            "color: #1e2532; font-weight: 800;"
        )
        self.setStyleSheet(
            f"""
            #scoreboard {{
                background: transparent;
                border: none;
            }}
            #scoreboard_card {{
                background: transparent;
                border: none;
                border-radius: {radius}px;
            }}
            #scoreboard_card QLabel {{
                padding: {max(1, int(2 * self.scale_factor))}px;
            }}
            """
        )
        row_a_style = "background: rgba(17,19,24,224); border: 1px solid #2c333d;"
        row_b_style = "background: rgba(24,28,34,224); border: 1px solid #2c333d;"
        self.row_a.setStyleSheet(row_a_style)
        self.row_b.setStyleSheet(row_b_style)
        self.row_a.setFixedHeight(row_h_px)
        self.row_b.setFixedHeight(row_h_px)
        self.player_a_pts.setMinimumHeight(row_h_px)
        self.player_b_pts.setMinimumHeight(row_h_px)
        self.alert_label.setFixedWidth(table_w)
        self.alert_label.setMinimumHeight(int(30 * self.scale_factor))
        self.grid.setRowMinimumHeight(0, 0)
        self.grid.setContentsMargins(0, 0, 0, 0)
        for label, (base_size, weight, color) in self.font_specs.items():
            font = QFont("Helvetica Neue", max(7, int(base_size * self.scale_factor)))
            font.setWeight(self._qt_font_weight(weight))
            label.setFont(font)
            label.setStyleSheet(f"color: {color};")
        self.player_a_name.setStyleSheet("color: #ede8e0; padding: 0px; margin-top: 2px;")
        self.player_b_name.setStyleSheet("color: #ede8e0; padding: 0px; margin-top: 2px;")
        pad = max(2, int(2 * self.scale_factor))
        num_cell_style = f"padding: 0px; margin: 0px; border: 1px solid #2c333d;"
        self.player_a_set1.setStyleSheet(f"color: #5d86ff; {num_cell_style}")
        self.player_b_set1.setStyleSheet(f"color: #5d86ff; {num_cell_style}")
        self.player_a_set2.setStyleSheet(f"color: #5d86ff; {num_cell_style}")
        self.player_b_set2.setStyleSheet(f"color: #5d86ff; {num_cell_style}")
        self.player_a_pts.setStyleSheet(f"color: #ede8e0; background: #222831; padding: {pad}px; margin: 0px; border: 1px solid #2c333d;")
        self.player_b_pts.setStyleSheet(f"color: #ede8e0; background: #222831; padding: {pad}px; margin: 0px; border: 1px solid #2c333d;")
        self.tournament_label.setStyleSheet(
            f"background: #8e3f1f; border: 1px solid #b5542a; border-bottom: 0px; border-radius: 0px; "
            f"padding-left: {int(10 * self.scale_factor)}px; color: #ede8e0;"
        )

        self.setFixedWidth(int(690 * self.scale_factor))
        self.adjustSize()

    def apply_state(self, state: OverlayState) -> None:
        self.tournament_label.setText(state.tournament.upper())
        self.player_a_name.setText(state.player_a.upper())
        self.player_b_name.setText(state.player_b.upper())
        self.player_a_set1.setText(str(state.set_col1_a))
        self.player_b_set1.setText(str(state.set_col1_b))
        self.player_a_set2.setText(str(state.set_col2_a))
        self.player_b_set2.setText(str(state.set_col2_b))
        self.player_a_pts.setText(state.points_a)
        self.player_b_pts.setText(state.points_b)
        self.serv_bar_a.setVisible(True)
        self.serv_bar_b.setVisible(True)
        self.serv_bar_a.setStyleSheet(
            "background: #d6ff3f; border-radius: 0px;" if state.server == "A" else "background: #1d2128; border-radius: 0px;"
        )
        self.serv_bar_b.setStyleSheet(
            "background: #d6ff3f; border-radius: 0px;" if state.server == "B" else "background: #1d2128; border-radius: 0px;"
        )
        self.row_a.setStyleSheet("background: rgba(17,19,24,224); border: 1px solid #2c333d;")
        self.row_b.setStyleSheet("background: rgba(24,28,34,224); border: 1px solid #2c333d;")
        self.alert_label.setVisible(bool(state.alert_banner))
        self.alert_label.setText(state.alert_banner)
        self._apply_flag_pixmap(self.flag_a_label, state.flag_a_path)
        self._apply_flag_pixmap(self.flag_b_label, state.flag_b_path)

    def _apply_flag_pixmap(self, target: QLabel, flag_path: str) -> None:
        if not flag_path or not os.path.exists(flag_path):
            target.clear()
            target.setStyleSheet("background: #1d2128; border: none;")
            return
        pix = QPixmap(flag_path)
        if pix.isNull():
            target.clear()
            target.setStyleSheet("background: #1d2128; border: none;")
            return
        target.setStyleSheet("border: none;")
        target.setPixmap(self._center_crop_pixmap(pix, target.width(), target.height()))

    def _center_crop_pixmap(self, pix: QPixmap, target_w: int, target_h: int) -> QPixmap:
        if target_w <= 0 or target_h <= 0 or pix.isNull():
            return pix
        src = pix
        # Trim transparent borders if present (some flag assets include transparent padding).
        img = src.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        bbox = self._non_transparent_bbox(img)
        if bbox is not None:
            src = QPixmap.fromImage(img.copy(*bbox))
        sw = src.width()
        sh = src.height()
        if sw <= 0 or sh <= 0:
            return pix
        target_ratio = target_w / target_h
        src_ratio = sw / sh
        if src_ratio > target_ratio:
            scaled_h = target_h
            scaled_w = int(round(scaled_h * src_ratio))
        else:
            scaled_w = target_w
            scaled_h = int(round(scaled_w / src_ratio))
        scaled = src.scaled(
            max(1, scaled_w),
            max(1, scaled_h),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = max(0, int((scaled.width() - target_w) / 2))
        y = max(0, int((scaled.height() - target_h) / 2))
        return scaled.copy(x, y, target_w, target_h)

    def _non_transparent_bbox(self, image: QImage) -> tuple[int, int, int, int] | None:
        w = image.width()
        h = image.height()
        min_x = w
        min_y = h
        max_x = -1
        max_y = -1
        for y in range(h):
            for x in range(w):
                if image.pixelColor(x, y).alpha() > 0:
                    if x < min_x:
                        min_x = x
                    if y < min_y:
                        min_y = y
                    if x > max_x:
                        max_x = x
                    if y > max_y:
                        max_y = y
        if max_x < min_x or max_y < min_y:
            return None
        return (min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)


class ExportWorker(QThread):
    finished_ok = Signal(str, int)
    failed = Signal(str)
    progress = Signal(int, float, float, str)

    def __init__(
        self,
        output_path: str,
        segments: list[Segment],
        include_overlay: bool,
        intro_clip: dict | None = None,
        outro_clip: dict | None = None,
    ) -> None:
        super().__init__()
        self.output_path = output_path
        self.segments = segments
        self.include_overlay = include_overlay
        self.intro_clip = intro_clip
        self.outro_clip = outro_clip
        self.ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()

    def run(self) -> None:
        try:
            started_at = time.monotonic()
            with tempfile.TemporaryDirectory(prefix="tennis-condense-") as temp_dir:
                chunk_paths: list[str] = []
                valid_segments = []
                for segment in self.segments:
                    start = max(0.0, float(segment.start))
                    end = max(start, float(segment.end))
                    duration = end - start
                    if duration > 0.05:
                        valid_segments.append((segment, start, end, duration))
                total_tasks = len(valid_segments)
                if self.intro_clip:
                    total_tasks += 1
                if self.outro_clip:
                    total_tasks += 1
                if total_tasks <= 0:
                    total_tasks = 1
                done_tasks = 0
                source_path_for_fps = (
                    valid_segments[0][0].source_path
                    if valid_segments
                    else (self.segments[0].source_path if self.segments else "")
                )
                target_fps = self._probe_source_fps(source_path_for_fps) or 50.0
                target_fps_txt = f"{target_fps:.6f}".rstrip("0").rstrip(".")
                self.progress.emit(0, 0.0, 0.0, "Preparazione export...")

                if self.intro_clip:
                    intro_chunk = os.path.join(temp_dir, "chunk_intro.mp4")
                    self._render_title_chunk(intro_chunk, self.intro_clip, target_fps_txt)
                    chunk_paths.append(intro_chunk)
                    done_tasks += 1
                    ratio = min(1.0, done_tasks / total_tasks)
                    elapsed = max(0.0, time.monotonic() - started_at)
                    eta = (elapsed / ratio - elapsed) if ratio > 0 else 0.0
                    self.progress.emit(int(ratio * 90), elapsed, max(0.0, eta), "Rendering intro...")

                for idx, (segment, start, _end, duration) in enumerate(valid_segments):
                    chunk_path = os.path.join(temp_dir, f"chunk_{idx:04d}.mp4")
                    cmd = [
                        self.ffmpeg_bin,
                        "-y",
                        "-ss",
                        f"{start:.3f}",
                        "-i",
                        segment.source_path,
                        "-t",
                        f"{duration:.3f}",
                    ]

                    if self.include_overlay:
                        overlay_graph = build_overlay_filter(segment.overlay)
                        cmd += [
                            "-filter_complex",
                            f"{overlay_graph};[out]fps={target_fps_txt}[outv]",
                            "-map",
                            "[outv]",
                            "-map",
                            "0:a?",
                        ]
                    else:
                        cmd += ["-vf", f"fps={target_fps_txt}"]

                    cmd += [
                        "-c:v",
                        "libx264",
                        "-preset",
                        "veryfast",
                        "-crf",
                        "21",
                        "-r",
                        target_fps_txt,
                        "-c:a",
                        "aac",
                        "-ar",
                        "48000",
                        "-ac",
                        "2",
                        "-movflags",
                        "+faststart",
                        chunk_path,
                    ]
                    self._run_cmd(cmd)
                    chunk_paths.append(chunk_path)
                    done_tasks += 1
                    elapsed = max(0.0, time.monotonic() - started_at)
                    ratio = min(1.0, done_tasks / total_tasks)
                    eta = (elapsed / ratio - elapsed) if ratio > 0 else 0.0
                    self.progress.emit(
                        int(ratio * 90),
                        elapsed,
                        max(0.0, eta),
                        f"Rendering clip {idx + 1}/{len(valid_segments)}",
                    )

                if self.outro_clip:
                    outro_chunk = os.path.join(temp_dir, "chunk_outro.mp4")
                    self._render_title_chunk(outro_chunk, self.outro_clip, target_fps_txt)
                    chunk_paths.append(outro_chunk)
                    done_tasks += 1
                    ratio = min(1.0, done_tasks / total_tasks)
                    elapsed = max(0.0, time.monotonic() - started_at)
                    eta = (elapsed / ratio - elapsed) if ratio > 0 else 0.0
                    self.progress.emit(int(ratio * 90), elapsed, max(0.0, eta), "Rendering outro...")

                if not chunk_paths:
                    raise RuntimeError("Nessun segmento valido da esportare.")

                concat_file = os.path.join(temp_dir, "concat.txt")
                with open(concat_file, "w", encoding="utf-8") as f:
                    for path in chunk_paths:
                        safe_path = path.replace("'", "'\\''")
                        f.write(f"file '{safe_path}'\n")

                self._run_cmd(
                    [
                        self.ffmpeg_bin,
                        "-y",
                        "-f",
                        "concat",
                        "-safe",
                        "0",
                        "-i",
                        concat_file,
                        "-c:v",
                        "libx264",
                        "-preset",
                        "veryfast",
                        "-crf",
                        "21",
                        "-r",
                        target_fps_txt,
                        "-c:a",
                        "aac",
                        "-movflags",
                        "+faststart",
                        self.output_path,
                    ]
                )
                elapsed = max(0.0, time.monotonic() - started_at)
                self.progress.emit(100, elapsed, 0.0, "Export completato.")
                self.finished_ok.emit(self.output_path, len(chunk_paths))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))

    def _run_cmd(self, cmd: list[str]) -> None:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Errore FFmpeg")

    def _render_title_chunk(self, output_path: str, cfg: dict, target_fps_txt: str) -> None:
        bg = cfg.get("background_path")
        duration = float(cfg.get("duration", 5.0))
        lines = cfg.get("lines", [])
        if not bg or duration <= 0:
            raise RuntimeError("Configurazione intro/outro non valida.")

        vf = build_title_card_filter(lines)
        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-framerate",
            target_fps_txt,
            "-loop",
            "1",
            "-i",
            bg,
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-t",
            f"{duration:.3f}",
            "-vf",
            vf,
            "-shortest",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "21",
            "-r",
            target_fps_txt,
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            output_path,
        ]
        self._run_cmd(cmd)

    def _probe_source_fps(self, path: str) -> float | None:
        if not path:
            return None
        candidates = [os.path.join(os.path.dirname(self.ffmpeg_bin), "ffprobe"), "ffprobe"]
        for ffprobe_bin in candidates:
            try:
                res = subprocess.run(
                    [
                        ffprobe_bin,
                        "-v",
                        "error",
                        "-select_streams",
                        "v:0",
                        "-show_entries",
                        "stream=avg_frame_rate,r_frame_rate",
                        "-of",
                        "default=noprint_wrappers=1:nokey=1",
                        path,
                    ],
                    capture_output=True,
                    text=True,
                )
                if res.returncode != 0:
                    continue
                for line in (res.stdout or "").splitlines():
                    fps = self._parse_fps_value(line.strip())
                    if fps and fps > 1.0:
                        return fps
            except Exception:  # noqa: BLE001
                continue

        # Fallback parse from ffmpeg stderr (e.g. "... 50 fps ...")
        try:
            res = subprocess.run([self.ffmpeg_bin, "-i", path], capture_output=True, text=True)
            m = re.search(r"(\d+(?:\.\d+)?)\s*fps", res.stderr or "")
            if m:
                fps = float(m.group(1))
                if fps > 1.0:
                    return fps
        except Exception:  # noqa: BLE001
            pass
        return None

    def _parse_fps_value(self, raw: str) -> float | None:
        if not raw:
            return None
        if "/" in raw:
            num, den = raw.split("/", 1)
            try:
                n = float(num)
                d = float(den)
                if d == 0:
                    return None
                val = n / d
                return val if val > 0 else None
            except ValueError:
                return None
        try:
            val = float(raw)
            return val if val > 0 else None
        except ValueError:
            return None


class ExportProgressDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("exportProgressDialog")
        self.setWindowTitle("Export")
        self.setModal(True)
        self.setMinimumSize(520, 320)
        self._last_status = ""
        self._state = "idle"
        self.output_path = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        self.title_label = QLabel("Esportazione in corso")
        self.title_label.setObjectName("dialogTitle")
        self.mode_label = QLabel("Modalita': --")
        self.mode_label.setObjectName("metaLabel")
        self.status_label = QLabel("Preparazione export...")
        self.status_label.setObjectName("statusValue")
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("exportProgressBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.elapsed_label = QLabel("Tempo trascorso: 0:00")
        self.elapsed_label.setObjectName("metaLabel")
        self.eta_label = QLabel("Tempo stimato rimanente: --:--")
        self.eta_label.setObjectName("metaLabel")
        self.summary_label = QLabel("Output: --")
        self.summary_label.setObjectName("metaLabel")
        self.log_label = QLabel("Dettagli")
        self.log_label.setObjectName("sectionTitle")
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumBlockCount(200)
        self.log_box.setObjectName("exportLog")
        self.close_btn = QPushButton("Chiudi")
        self.close_btn.setObjectName("shellButton")
        self.close_btn.setProperty("btnRole", "secondary")
        self.close_btn.setEnabled(False)
        self.close_btn.clicked.connect(self.accept)

        layout.addWidget(self.title_label)
        layout.addWidget(self.mode_label)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.elapsed_label)
        layout.addWidget(self.eta_label)
        layout.addWidget(self.log_label)
        layout.addWidget(self.log_box, 1)
        layout.addWidget(self.close_btn, 0, Qt.AlignmentFlag.AlignRight)

    def set_mode(self, export_kind: str, output_path: str) -> None:
        if export_kind == "condensato":
            mode = "Condensato"
        elif export_kind == "highlights":
            mode = "Highlights"
        elif export_kind == "punto":
            mode = "Punto selezionato"
        else:
            mode = export_kind
        self.mode_label.setText(f"Modalita': {mode}")
        self.output_path = output_path
        self.summary_label.setText(f"Output: {output_path}")
        self.log_box.appendPlainText(f"Avvio export {mode}")

    def set_progress(self, percent: int, elapsed_sec: float, eta_sec: float, status: str) -> None:
        self._state = "progress"
        self.close_btn.setEnabled(False)
        self.progress_bar.setValue(max(0, min(100, percent)))
        self.status_label.setText(status)
        self.title_label.setText("Esportazione in corso")
        self.elapsed_label.setText(f"Tempo trascorso: {format_time(elapsed_sec)}")
        if eta_sec <= 0.1:
            self.eta_label.setText("Tempo stimato rimanente: 0:00")
        else:
            self.eta_label.setText(f"Tempo stimato rimanente: {format_time(eta_sec)}")
        if status and status != self._last_status:
            self._last_status = status
            self.log_box.appendPlainText(f"[{percent:3d}%] {status}")

    def set_success(self, export_kind: str, output_path: str, chunks: int) -> None:
        self._state = "success"
        if export_kind == "condensato":
            mode = "condensato"
        elif export_kind == "highlights":
            mode = "highlights"
        elif export_kind == "punto":
            mode = "punto selezionato"
        else:
            mode = export_kind
        self.setWindowTitle("Export completato")
        self.title_label.setText("Export completato")
        self.status_label.setText(f"Completato: {chunks} clip ({mode})")
        self.progress_bar.setValue(100)
        self.eta_label.setText("Tempo stimato rimanente: 0:00")
        self.summary_label.setText(f"Output: {output_path}")
        self.log_box.appendPlainText(f"Export completato: {output_path}")
        self.close_btn.setEnabled(True)

    def set_error(self, export_kind: str, message: str) -> None:
        self._state = "error"
        if export_kind == "condensato":
            mode = "condensato"
        elif export_kind == "highlights":
            mode = "highlights"
        elif export_kind == "punto":
            mode = "punto selezionato"
        else:
            mode = export_kind
        self.setWindowTitle("Export fallito")
        self.title_label.setText("Export fallito")
        self.status_label.setText(f"Errore durante export {mode}")
        self.log_box.appendPlainText(message.strip() or "Errore sconosciuto")
        self.close_btn.setEnabled(True)

    def closeEvent(self, event) -> None:
        if self._state == "progress":
            event.ignore()
            return
        super().closeEvent(event)


class CollapsiblePanel(QWidget):
    def __init__(self, title: str, expanded: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.toggle_btn = QPushButton()
        self.toggle_btn.setFlat(True)
        self.toggle_btn.setStyleSheet("text-align: left; font-weight: 700;")
        self.toggle_btn.clicked.connect(self._toggle)
        self.content = QWidget()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.toggle_btn)
        layout.addWidget(self.content)

        self.title = title
        self.expanded = expanded
        self._refresh()

    def set_content_layout(self, content_layout) -> None:
        self.content.setLayout(content_layout)

    def _toggle(self) -> None:
        self.expanded = not self.expanded
        self._refresh()

    def _refresh(self) -> None:
        symbol = "▼" if self.expanded else "▶"
        self.toggle_btn.setText(f"{symbol} {self.title}")
        self.content.setVisible(self.expanded)


class MainWindow(QMainWindow):
    POINT_VALUES = [0, 15, 30, 40, "AD"]

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Tennis Match Condenser v{APP_VERSION} (Python)")
        self.resize(1360, 860)

        self.input_path: str | None = None
        self.input_paths: list[str] = []
        self.pending_point_start: float | None = None  # legacy compatibility surface
        self.pending_point_source_path: str | None = None  # legacy compatibility surface
        self.points: list[PointRecord] = []
        self.selected_point_index: int | None = None
        self.selected_point_id: int | None = None
        self.capture_state: Literal["IDLE", "RECORDING", "PAUSED_WITHIN_POINT"] = "IDLE"
        self.open_point_id: int | None = None
        self.open_clip_start: float | None = None
        self.open_clip_source_path: str | None = None
        self.next_point_id: int = 1
        self.clip_duration_cache: dict[str, float] = {}
        self.source_fps_cache: dict[str, float] = {}
        self.segments: list[Segment] = []
        self.undo_stack: list[dict] = []
        self.export_worker: ExportWorker | None = None
        self.export_progress_dialog: ExportProgressDialog | None = None
        self.current_export_kind = "condensato"
        self._ephemeral_export_frames: list[str] = []
        self.session_temp_dir = tempfile.TemporaryDirectory(prefix="tennis-session-")

        self.points_a = 0
        self.points_b = 0
        self.tb_points_a = 0
        self.tb_points_b = 0
        self.games_a = 0
        self.games_b = 0
        self.sets_a = 0
        self.sets_b = 0
        self.completed_sets: list[tuple[int, int]] = []
        self.completed_set_tb_loser_points: list[int | None] = []
        self.in_tiebreak = False
        self.tiebreak_target = 7
        self.tiebreak_super = False
        self.starting_server = "A"
        self.current_server = "A"
        self.tiebreak_first_server: str | None = None
        self.autosave_path = os.path.join(os.getcwd(), "autosave_tennis_project.json")

        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.positionChanged.connect(self.on_player_position_changed)
        self.player.durationChanged.connect(self.on_player_duration_changed)

        self.video_widget = QVideoWidget()
        self.player.setVideoOutput(self.video_widget)

        self.overlay_widget = ScoreboardOverlayWidget()
        self.video_container = VideoOverlayContainer(self.video_widget, self.overlay_widget)

        self.status_label = QLabel("Nessun video caricato.")
        self.score_preview_label = QLabel("Preview score: Game 0-0 | Pts 0-0")
        self.export_length_label = QLabel("Durata export stimata: 0:00")
        self.timeline_slider = QSlider(Qt.Orientation.Horizontal)
        self.timeline_slider.setRange(0, 0)
        self.timeline_slider.sliderPressed.connect(self.on_timeline_pressed)
        self.timeline_slider.sliderReleased.connect(self.on_timeline_released)
        self.timeline_slider.sliderMoved.connect(self.on_timeline_moved)
        self.time_label = QLabel("0:00 / 0:00")
        self.is_scrubbing = False

        self.load_btn = QPushButton("Carica video(s)")
        self.load_btn.clicked.connect(self.load_videos)
        self.save_project_btn = QPushButton("Salva progetto")
        self.save_project_btn.clicked.connect(self.save_project)
        self.open_project_btn = QPushButton("Carica progetto")
        self.open_project_btn.clicked.connect(self.load_project)
        self.mark_start_btn = QPushButton("Inizio punto")
        self.mark_end_btn = QPushButton("Pausa clip")
        self.play_pause_btn = QPushButton("Play/Pause")
        self.mark_start_btn.clicked.connect(self.mark_start)
        self.mark_end_btn.clicked.connect(self.mark_end)
        self.play_pause_btn.clicked.connect(self.toggle_play_pause)

        self.jump_buttons = []
        for sec in (-30, -10, -5, 5, 10, 30):
            btn = QPushButton(f"{sec:+d}s")
            btn.clicked.connect(lambda _=False, s=sec: self.jump(s))
            self.jump_buttons.append(btn)

        self.tournament_input = QLineEdit("Amateur Tennis Tour")
        self.player_a_input = QLineEdit("Giocatore A")
        self.player_b_input = QLineEdit("Giocatore B")
        self.rank_a_input = QLineEdit("")
        self.rank_b_input = QLineEdit("")
        self.flag_a_code_input = QLineEdit("IT")
        self.flag_b_code_input = QLineEdit("ES")
        self.flags_download_btn = QPushButton("Scarica/Aggiorna bandiere")
        self.flags_status_label = QLabel("Bandiere: non scaricate")
        self.flag_a_path = ""
        self.flag_b_path = ""
        self.round_input = QLineEdit("Round of 32")
        self.best_of = QComboBox()
        self.best_of.addItems(["Best of 3", "Best of 5"])
        self.deciding_set_mode = QComboBox()
        self.deciding_set_mode.addItems(["3° set normale", "Super tie-break a 10"])
        self.server_combo = QComboBox()
        self.server_combo.addItems(["Servizio: A", "Servizio: B"])
        self.overlay_corner_combo = QComboBox()
        self.overlay_corner_combo.addItems(["Top Left", "Top Right", "Bottom Left", "Bottom Right"])
        self.overlay_scale_combo = QComboBox()
        self.overlay_scale_combo.addItems(["80%", "100%", "120%", "140%", "160%"])
        self.overlay_scale_combo.setCurrentText("100%")
        self.active_clip_combo = QComboBox()
        self.active_clip_combo.currentIndexChanged.connect(self.on_active_clip_changed)
        self.enable_intro_checkbox = QCheckBox("Intro automatica")
        self.enable_outro_checkbox = QCheckBox("Outro automatica")
        self.use_intro_bg_for_outro = QCheckBox("Usa lo stesso frame dell'intro")
        self.intro_duration_input = QLineEdit("5")
        self.outro_duration_input = QLineEdit("5")
        self.intro_bg_path: str | None = None  # retained for backward compatibility in loaded projects
        self.outro_bg_path: str | None = None  # retained for backward compatibility in loaded projects
        self.intro_frame_ref: dict | None = None
        self.outro_frame_ref: dict | None = None
        self.intro_bg_label = QLabel("Intro: timestamp non selezionato")
        self.outro_bg_label = QLabel("Outro: timestamp non selezionato")
        self.capture_intro_bg_btn = QPushButton("Usa timestamp corrente per intro")
        self.capture_outro_bg_btn = QPushButton("Usa timestamp corrente per outro")
        self.capture_intro_bg_btn.clicked.connect(self.set_intro_timestamp_from_current)
        self.capture_outro_bg_btn.clicked.connect(self.set_outro_timestamp_from_current)
        self.enable_intro_checkbox.stateChanged.connect(self.on_intro_toggled)
        self.enable_outro_checkbox.stateChanged.connect(self.on_outro_toggled)
        self.use_intro_bg_for_outro.stateChanged.connect(self.on_use_intro_bg_for_outro_toggled)

        self.sets_a_input = QLineEdit("0")
        self.sets_b_input = QLineEdit("0")
        self.games_a_input = QLineEdit("0")
        self.games_b_input = QLineEdit("0")

        for field in [
            self.tournament_input,
            self.player_a_input,
            self.player_b_input,
            self.rank_a_input,
            self.rank_b_input,
            self.flag_a_code_input,
            self.flag_b_code_input,
            self.round_input,
            self.intro_duration_input,
            self.outro_duration_input,
            self.sets_a_input,
            self.sets_b_input,
            self.games_a_input,
            self.games_b_input,
        ]:
            field.editingFinished.connect(self.sync_overlay_state_from_inputs)
            field.editingFinished.connect(field.clearFocus)
            field.editingFinished.connect(field.deselect)
        self.player_a_input.textChanged.connect(self.update_overlay)
        self.player_b_input.textChanged.connect(self.update_overlay)
        self.flag_a_code_input.editingFinished.connect(self.on_flag_codes_changed)
        self.flag_b_code_input.editingFinished.connect(self.on_flag_codes_changed)
        self.flags_download_btn.clicked.connect(self.download_flags)

        self.server_combo.currentIndexChanged.connect(self.on_server_selection_changed)
        self.overlay_corner_combo.currentTextChanged.connect(self.on_overlay_corner_changed)
        self.overlay_scale_combo.currentTextChanged.connect(self.on_overlay_scale_changed)

        self.point_a_btn = QPushButton("Punto A")
        self.point_b_btn = QPushButton("Punto B")
        self.add_last_highlight_btn = QPushButton("Highlight")
        self.add_last_highlight_btn.setEnabled(False)
        self.add_last_highlight_btn.clicked.connect(self.add_last_point_to_highlights)
        self.reset_score_btn = QPushButton("Reset Score")
        self.apply_server_to_all_btn = QPushButton("Applica servitore corrente a tutti i segmenti")
        self.point_a_btn.clicked.connect(lambda: self.tennis_point_winner("A"))
        self.point_b_btn.clicked.connect(lambda: self.tennis_point_winner("B"))
        self.reset_score_btn.clicked.connect(self.reset_score)
        self.apply_server_to_all_btn.clicked.connect(self.apply_server_to_all_segments)
        self.include_overlay = QCheckBox("Includi overlay nell'export")
        self.include_overlay.setChecked(True)
        self.preview_by_timeline = QCheckBox("Preview scoreboard da timeline")
        self.preview_by_timeline.setChecked(True)
        self.preview_by_timeline.stateChanged.connect(self.update_overlay)

        self.segments_list = QListWidget()
        self.segments_list.currentRowChanged.connect(self.on_segment_row_changed)
        self.points_list = QListWidget()
        self.points_list.setObjectName("pointsList")
        self.points_list.currentRowChanged.connect(self.on_points_list_row_changed)
        self.highlights_list = QListWidget()
        self.highlights_list.currentRowChanged.connect(lambda _row: self.update_highlight_controls())
        self.highlights_list.currentRowChanged.connect(self.on_highlight_row_changed)
        self.remove_highlight_btn = QPushButton("Rimuovi highlight selezionato")
        self.remove_highlight_btn.setEnabled(False)
        self.remove_highlight_btn.clicked.connect(self.remove_selected_highlight)
        self.remove_point_btn = QPushButton("Rimuovi punto")
        self.remove_point_btn.setProperty("btnRole", "danger")
        self.remove_point_btn.setEnabled(False)
        self.remove_point_btn.clicked.connect(self.remove_last_point)
        self.clear_segments_btn = QPushButton("Svuota clip")
        self.clear_segments_btn.clicked.connect(self.clear_segments)
        self.undo_btn = QPushButton("Undo")
        self.undo_btn.clicked.connect(self.undo_last_action)
        self.export_btn = QPushButton("Esporta condensato")
        self.export_btn.clicked.connect(self.export_condensed)
        self.export_highlights_btn = QPushButton("Esporta highlights")
        self.export_highlights_btn.clicked.connect(self.export_highlights)
        self.export_selected_point_btn = QPushButton("Export punto selezionato")
        self.export_selected_point_btn.setEnabled(False)
        self.export_selected_point_btn.clicked.connect(self.export_selected_point)
        self.preview_overlay_btn = QPushButton("Preview grafica overlay")
        self.preview_overlay_btn.clicked.connect(self.preview_overlay_frame)

        self.hotkey_defaults = {
            "play_pause": "Space",
            "jump_back_5": "Left",
            "jump_fwd_5": "Right",
            "jump_back_10": "Shift+Left",
            "jump_fwd_10": "Shift+Right",
            "jump_back_30": "Alt+Left",
            "jump_fwd_30": "Alt+Right",
            "mark_start": "O",
            "mark_end": "P",
            "point_a": "Q",
            "point_b": "W",
            "undo": "Ctrl+Z",
            "clear_focus": "Esc",
        }
        self.hotkey_edits: dict[str, QKeySequenceEdit] = {}
        self.shortcuts: dict[str, QShortcut] = {}

        self._build_ui()
        self._setup_hotkey_ui()
        self._bind_shortcuts()
        self.on_overlay_scale_changed(self.overlay_scale_combo.currentText())
        self.on_flag_codes_changed()
        self.reset_score()
        self.refresh_segments()
        self._refresh_intro_outro_labels()
        self.video_container.clicked.connect(self.clear_edit_focus)
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(15000)
        self.autosave_timer.timeout.connect(self.autosave_project)
        self.autosave_timer.start()
        self.try_restore_autosave()

    def _build_ui(self) -> None:
        self.ui_shell = UIShell(self)
        self.setCentralWidget(self.ui_shell)
        apply_app_theme(self)

        # Keep the legacy status field target so controller methods remain unchanged.
        self.status_label = self.ui_shell.project_status_label

        # Center stage with polished empty-state overlay.
        self.video_stage_host = QWidget()
        self.video_stage_stack = QStackedLayout(self.video_stage_host)
        self.video_stage_stack.setContentsMargins(0, 0, 0, 0)
        self.video_stage_stack.setStackingMode(QStackedLayout.StackingMode.StackAll)

        self.video_stage_stack.addWidget(self.video_container)
        empty_state = QFrame()
        empty_state.setObjectName("emptyStateCard")
        empty_state_layout = QVBoxLayout(empty_state)
        empty_state_layout.setContentsMargins(24, 24, 24, 24)
        empty_state_layout.setSpacing(8)
        self.empty_state_title = QLabel("No Video Loaded")
        self.empty_state_title.setObjectName("emptyStateTitle")
        self.empty_state_hint = QLabel("Load a single video or a split sequence to start editing.")
        self.empty_state_hint.setObjectName("metaLabel")
        self.empty_state_load_btn = QPushButton("Carica Video")
        self.empty_state_load_btn.setProperty("btnRole", "primary")
        self.empty_state_load_btn.clicked.connect(self.load_videos)
        empty_state_layout.addStretch(1)
        empty_state_layout.addWidget(self.empty_state_title, 0, Qt.AlignmentFlag.AlignHCenter)
        empty_state_layout.addWidget(self.empty_state_hint, 0, Qt.AlignmentFlag.AlignHCenter)
        empty_state_layout.addWidget(self.empty_state_load_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        empty_state_layout.addStretch(1)
        self.video_stage_stack.addWidget(empty_state)
        self.ui_shell.center_video_layout.addWidget(self.video_stage_host, 1)

        controls_host = QWidget()
        controls_layout = QVBoxLayout(controls_host)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(6)

        timeline_row = QHBoxLayout()
        timeline_row.setContentsMargins(0, 0, 0, 0)
        timeline_row.setSpacing(8)
        timeline_row.addWidget(self.timeline_slider, 1)
        timeline_row.addWidget(self.time_label)
        controls_layout.addLayout(timeline_row)

        transport_row = QHBoxLayout()
        transport_row.setContentsMargins(0, 0, 0, 0)
        transport_row.setSpacing(6)

        self.transport_status_chip = QLabel("Idle")
        self.transport_status_chip.setObjectName("statusChip")

        playback_group = QWidget()
        playback_layout = QHBoxLayout(playback_group)
        playback_layout.setContentsMargins(6, 4, 6, 4)
        playback_layout.setSpacing(6)
        playback_group.setObjectName("transportGroup")
        playback_layout.addWidget(self.play_pause_btn)

        seek_group = QWidget()
        seek_layout = QHBoxLayout(seek_group)
        seek_layout.setContentsMargins(6, 4, 6, 4)
        seek_layout.setSpacing(4)
        seek_group.setObjectName("transportGroup")
        for btn in self.jump_buttons:
            seek_layout.addWidget(btn)

        capture_group = QWidget()
        capture_layout = QHBoxLayout(capture_group)
        capture_layout.setContentsMargins(6, 4, 6, 4)
        capture_layout.setSpacing(6)
        capture_group.setObjectName("transportGroup")
        capture_layout.addWidget(self.mark_start_btn)
        capture_layout.addWidget(self.mark_end_btn)

        scoring_group = QWidget()
        scoring_layout = QHBoxLayout(scoring_group)
        scoring_layout.setContentsMargins(6, 4, 6, 4)
        scoring_layout.setSpacing(6)
        scoring_group.setObjectName("transportGroup")
        scoring_layout.addWidget(self.undo_btn)
        scoring_layout.addWidget(self.point_a_btn)
        scoring_layout.addWidget(self.point_b_btn)
        scoring_layout.addWidget(self.add_last_highlight_btn)

        transport_row.addWidget(playback_group)
        transport_row.addWidget(seek_group)
        transport_row.addWidget(capture_group)
        transport_row.addWidget(scoring_group)
        transport_row.addStretch(1)
        transport_row.addWidget(self.transport_status_chip)
        controls_layout.addLayout(transport_row)
        self.ui_shell.center_timeline_layout.addWidget(controls_host)

        # Left rail: source / points / clips / highlights.
        source_panel = QFrame()
        source_panel.setObjectName("panel")
        source_controls_layout = QVBoxLayout(source_panel)
        source_controls_layout.setContentsMargins(8, 8, 8, 8)
        source_controls_layout.setSpacing(8)
        source_title = QLabel("Active Source")
        source_title.setObjectName("sectionTitle")
        source_controls_layout.addWidget(source_title)
        source_controls_layout.addWidget(self.active_clip_combo)
        self.source_empty_label = QLabel("Nessun video caricato")
        self.source_empty_label.setObjectName("metaLabel")
        source_controls_layout.addWidget(self.source_empty_label)
        self.ui_shell.left_sources_page.layout().addWidget(source_panel, 0)
        self.ui_shell.left_sources_page.layout().addStretch(1)

        points_panel = QFrame()
        points_panel.setObjectName("panel")
        points_layout = QVBoxLayout(points_panel)
        points_layout.setContentsMargins(8, 8, 8, 8)
        points_layout.setSpacing(8)
        points_layout.addWidget(self.points_list, 1)
        self.points_empty_label = QLabel("Nessun punto registrato")
        self.points_empty_label.setObjectName("metaLabel")
        points_layout.addWidget(self.points_empty_label)
        points_btns = QHBoxLayout()
        points_btns.setSpacing(6)
        points_btns.addWidget(self.remove_point_btn)
        points_layout.addLayout(points_btns)
        self.ui_shell.left_points_page.layout().addWidget(points_panel, 1)

        clips_panel = QFrame()
        clips_panel.setObjectName("panel")
        clips_layout = QVBoxLayout(clips_panel)
        clips_layout.setContentsMargins(8, 8, 8, 8)
        clips_layout.setSpacing(8)
        self.segments_list.setObjectName("segmentsList")
        self.segments_list.setWordWrap(True)
        self.segments_list.setAlternatingRowColors(True)
        clips_layout.addWidget(self.segments_list, 1)
        self.segments_empty_label = QLabel("Nessun punto selezionato")
        self.segments_empty_label.setObjectName("metaLabel")
        clips_layout.addWidget(self.segments_empty_label)
        clips_btns = QHBoxLayout()
        clips_btns.setSpacing(6)
        clips_btns.addWidget(self.clear_segments_btn)
        clips_layout.addLayout(clips_btns)
        self.ui_shell.left_clips_page.layout().addWidget(clips_panel, 1)

        highlights_panel = QFrame()
        highlights_panel.setObjectName("panel")
        highlights_layout = QVBoxLayout(highlights_panel)
        highlights_layout.setContentsMargins(8, 8, 8, 8)
        highlights_layout.setSpacing(8)
        self.highlights_list.setObjectName("highlightsList")
        self.highlights_list.setWordWrap(True)
        self.highlights_list.setAlternatingRowColors(True)
        highlights_layout.addWidget(self.highlights_list, 1)
        self.highlights_empty_label = QLabel("Nessun highlight")
        self.highlights_empty_label.setObjectName("metaLabel")
        highlights_layout.addWidget(self.highlights_empty_label)
        highlights_btns = QHBoxLayout()
        highlights_btns.setSpacing(6)
        highlights_btns.addWidget(self.remove_highlight_btn)
        highlights_btns.addWidget(self.export_highlights_btn)
        highlights_layout.addLayout(highlights_btns)
        self.ui_shell.left_highlights_page.layout().addWidget(highlights_panel, 1)

        # Right inspector tabs.
        score_tab = self.ui_shell.right_score_page.layout()
        score_tab.setSpacing(8)

        live_card = QFrame()
        live_card.setObjectName("inspectorCard")
        live_layout = QVBoxLayout(live_card)
        live_layout.setContentsMargins(10, 10, 10, 10)
        live_layout.setSpacing(8)
        live_title = QLabel("Live Score / Inspector")
        live_title.setObjectName("sectionTitle")
        live_layout.addWidget(live_title)

        self.score_summary_card = QLabel("A 0-0 0 | B 0-0 0")
        self.score_summary_card.setObjectName("summaryCard")
        live_layout.addWidget(self.score_summary_card)

        chips_row = QHBoxLayout()
        chips_row.setContentsMargins(0, 0, 0, 0)
        chips_row.setSpacing(6)
        self.server_status_chip = QLabel("Server: A")
        self.server_status_chip.setObjectName("statusChip")
        self.point_open_chip = QLabel("Idle")
        self.point_open_chip.setObjectName("statusChip")
        chips_row.addWidget(self.server_status_chip)
        chips_row.addWidget(self.point_open_chip)
        chips_row.addStretch(1)
        live_layout.addLayout(chips_row)

        live_layout.addWidget(self.score_preview_label)
        score_tab.addWidget(live_card)

        players_card = QFrame()
        players_card.setObjectName("inspectorCard")
        players_layout = QVBoxLayout(players_card)
        players_layout.setContentsMargins(10, 10, 10, 10)
        players_layout.setSpacing(8)
        players_title = QLabel("Players")
        players_title.setObjectName("sectionTitle")
        players_layout.addWidget(players_title)
        players_grid = QGridLayout()
        players_grid.setHorizontalSpacing(8)
        players_grid.setVerticalSpacing(8)
        players_grid.addWidget(QLabel("Nome A"), 0, 0)
        players_grid.addWidget(self.player_a_input, 0, 1)
        players_grid.addWidget(QLabel("Nome B"), 0, 2)
        players_grid.addWidget(self.player_b_input, 0, 3)
        players_grid.addWidget(QLabel("Flag A"), 1, 0)
        players_grid.addWidget(self.flag_a_code_input, 1, 1)
        players_grid.addWidget(QLabel("Flag B"), 1, 2)
        players_grid.addWidget(self.flag_b_code_input, 1, 3)
        players_grid.addWidget(QLabel("Ranking A"), 2, 0)
        players_grid.addWidget(self.rank_a_input, 2, 1)
        players_grid.addWidget(QLabel("Ranking B"), 2, 2)
        players_grid.addWidget(self.rank_b_input, 2, 3)
        players_grid.setColumnStretch(1, 1)
        players_grid.setColumnStretch(3, 1)
        players_layout.addLayout(players_grid)
        players_layout.addWidget(self.flags_download_btn)
        players_layout.addWidget(self.flags_status_label)
        score_tab.addWidget(players_card)

        match_card = QFrame()
        match_card.setObjectName("inspectorCard")
        match_layout = QVBoxLayout(match_card)
        match_layout.setContentsMargins(10, 10, 10, 10)
        match_layout.setSpacing(8)
        match_title = QLabel("Match Info")
        match_title.setObjectName("sectionTitle")
        match_layout.addWidget(match_title)
        match_grid = QGridLayout()
        match_grid.setHorizontalSpacing(10)
        match_grid.setVerticalSpacing(8)
        match_grid.setColumnStretch(1, 1)
        match_grid.addWidget(QLabel("Torneo"), 0, 0)
        match_grid.addWidget(self.tournament_input, 0, 1)
        match_grid.addWidget(QLabel("Round"), 1, 0)
        match_grid.addWidget(self.round_input, 1, 1)
        match_grid.addWidget(QLabel("Formato"), 2, 0)
        match_grid.addWidget(self.best_of, 2, 1)
        match_grid.addWidget(QLabel("Set decisivo"), 3, 0)
        match_grid.addWidget(self.deciding_set_mode, 3, 1)
        match_grid.addWidget(QLabel("Servizio"), 4, 0)
        match_grid.addWidget(self.server_combo, 4, 1)
        match_layout.addLayout(match_grid)
        match_layout.addWidget(self.apply_server_to_all_btn)
        score_tab.addWidget(match_card)
        score_tab.addStretch(1)

        overlay_tab = self.ui_shell.right_overlay_page.layout()
        overlay_tab.setSpacing(8)
        overlay_card = QFrame()
        overlay_card.setObjectName("inspectorCard")
        overlay_layout = QVBoxLayout(overlay_card)
        overlay_layout.setContentsMargins(10, 10, 10, 10)
        overlay_layout.setSpacing(8)
        overlay_title = QLabel("Overlay")
        overlay_title.setObjectName("sectionTitle")
        overlay_layout.addWidget(overlay_title)
        overlay_layout.addWidget(QLabel("Posizione"))
        overlay_layout.addWidget(self.overlay_corner_combo)
        overlay_layout.addWidget(QLabel("Scala"))
        overlay_layout.addWidget(self.overlay_scale_combo)
        overlay_layout.addWidget(self.preview_overlay_btn)
        overlay_layout.addWidget(self.include_overlay)
        overlay_tab.addWidget(overlay_card)
        overlay_tab.addStretch(1)

        intro_outro_panel = QFrame()
        intro_outro_panel.setObjectName("inspectorCard")
        intro_outro_layout = QVBoxLayout(intro_outro_panel)
        intro_outro_layout.setContentsMargins(10, 10, 10, 10)
        intro_outro_layout.setSpacing(10)
        intro_outro_tab = self.ui_shell.right_intro_outro_page.layout()
        intro_outro_tab.setSpacing(8)

        shared_card = QFrame()
        shared_card.setObjectName("panel")
        shared_layout = QVBoxLayout(shared_card)
        shared_layout.setContentsMargins(8, 8, 8, 8)
        shared_layout.setSpacing(6)
        shared_title = QLabel("Shared")
        shared_title.setObjectName("sectionTitle")
        shared_layout.addWidget(shared_title)
        shared_layout.addWidget(self.use_intro_bg_for_outro)
        intro_outro_layout.addWidget(shared_card)

        intro_card = QFrame()
        intro_card.setObjectName("panel")
        intro_card_layout = QGridLayout(intro_card)
        intro_card_layout.setContentsMargins(8, 8, 8, 8)
        intro_card_layout.setHorizontalSpacing(8)
        intro_card_layout.setVerticalSpacing(8)
        intro_title = QLabel("Intro")
        intro_title.setObjectName("sectionTitle")
        intro_card_layout.addWidget(intro_title, 0, 0, 1, 2)
        intro_card_layout.addWidget(self.enable_intro_checkbox, 1, 0, 1, 2)
        intro_card_layout.addWidget(QLabel("Durata (s)"), 2, 0)
        intro_card_layout.addWidget(self.intro_duration_input, 2, 1)
        intro_card_layout.addWidget(self.capture_intro_bg_btn, 3, 0, 1, 2)
        intro_card_layout.addWidget(self.intro_bg_label, 4, 0, 1, 2)
        intro_outro_layout.addWidget(intro_card)

        outro_card = QFrame()
        outro_card.setObjectName("panel")
        outro_card_layout = QGridLayout(outro_card)
        outro_card_layout.setContentsMargins(8, 8, 8, 8)
        outro_card_layout.setHorizontalSpacing(8)
        outro_card_layout.setVerticalSpacing(8)
        outro_title = QLabel("Outro")
        outro_title.setObjectName("sectionTitle")
        outro_card_layout.addWidget(outro_title, 0, 0, 1, 2)
        outro_card_layout.addWidget(self.enable_outro_checkbox, 1, 0, 1, 2)
        outro_card_layout.addWidget(QLabel("Durata (s)"), 2, 0)
        outro_card_layout.addWidget(self.outro_duration_input, 2, 1)
        outro_card_layout.addWidget(self.capture_outro_bg_btn, 3, 0, 1, 2)
        outro_card_layout.addWidget(self.outro_bg_label, 4, 0, 1, 2)
        intro_outro_layout.addWidget(outro_card)
        intro_outro_tab.addWidget(intro_outro_panel)
        intro_outro_tab.addStretch(1)

        export_panel = QFrame()
        export_panel.setObjectName("inspectorCard")
        export_layout = QVBoxLayout(export_panel)
        export_layout.setContentsMargins(10, 10, 10, 10)
        export_layout.setSpacing(8)
        export_tab = self.ui_shell.right_export_page.layout()
        export_tab.setSpacing(8)

        export_title = QLabel("Export")
        export_title.setObjectName("sectionTitle")
        export_layout.addWidget(export_title)
        export_btn_row = QHBoxLayout()
        export_btn_row.setSpacing(6)
        export_btn_row.addWidget(self.export_btn)
        export_btn_row.addWidget(self.export_highlights_btn)
        export_btn_row.addWidget(self.export_selected_point_btn)
        export_layout.addLayout(export_btn_row)
        export_layout.addWidget(self.export_length_label)
        export_layout.addWidget(QLabel("Riepilogo output"))
        self.export_summary_label = QLabel("Condensato e highlights disponibili.")
        self.export_summary_label.setObjectName("metaLabel")
        export_layout.addWidget(self.export_summary_label)
        export_tab.addWidget(export_panel)
        export_tab.addStretch(1)

        self.hotkeys_panel = QFrame()
        self.hotkeys_panel.setObjectName("inspectorCard")
        self.hotkeys_layout = QGridLayout(self.hotkeys_panel)
        self.hotkeys_layout.setContentsMargins(10, 10, 10, 10)
        self.hotkeys_layout.setHorizontalSpacing(10)
        self.hotkeys_layout.setVerticalSpacing(8)
        self.hotkeys_layout.addWidget(QLabel("Hotkeys configurabili"), 0, 0, 1, 2)
        self.hotkeys_group_widgets = {}
        for row_idx, (key, title) in enumerate(
            [("playback", "Playback"), ("marking", "Point Editing"), ("utility", "Utility")],
            start=1,
        ):
            card = QFrame()
            card.setObjectName("panel")
            card_layout = QGridLayout(card)
            card_layout.setContentsMargins(8, 8, 8, 8)
            card_layout.setHorizontalSpacing(8)
            card_layout.setVerticalSpacing(6)
            section = QLabel(title)
            section.setObjectName("sectionTitle")
            card_layout.addWidget(section, 0, 0, 1, 2)
            self.hotkeys_group_widgets[key] = card_layout
            self.hotkeys_layout.addWidget(card, row_idx, 0, 1, 2)
        self.ui_shell.right_hotkeys_page.layout().setSpacing(8)
        self.ui_shell.right_hotkeys_page.layout().addWidget(self.hotkeys_panel)
        self.ui_shell.right_hotkeys_page.layout().addStretch(1)

        self._wire_shell_actions()
        self._apply_button_roles()
        self._refresh_shell_empty_states()

    def _bind_shell_action(self, action_key: str, callback) -> bool:
        action = self.ui_shell.actions.get(action_key)
        if not action or callback is None:
            if action:
                action.setEnabled(False)
            return False
        action.triggered.connect(callback)
        action.setEnabled(True)
        return True

    def _apply_button_roles(self) -> None:
        role_map = {
            self.play_pause_btn: "primary",
            self.mark_start_btn: "secondary",
            self.mark_end_btn: "secondary",
            self.point_a_btn: "active",
            self.point_b_btn: "active",
            self.add_last_highlight_btn: "secondary",
            self.undo_btn: "subtle",
            self.clear_segments_btn: "danger",
            self.remove_highlight_btn: "danger",
            self.export_btn: "primary",
            self.export_highlights_btn: "secondary",
            self.preview_overlay_btn: "subtle",
            self.flags_download_btn: "subtle",
            self.capture_intro_bg_btn: "secondary",
            self.capture_outro_bg_btn: "secondary",
            self.load_btn: "primary",
            self.open_project_btn: "secondary",
            self.save_project_btn: "secondary",
            self.reset_score_btn: "danger",
            self.apply_server_to_all_btn: "secondary",
            self.empty_state_load_btn: "primary",
            self.remove_point_btn: "danger",
            self.export_selected_point_btn: "secondary",
        }
        for btn, role in role_map.items():
            btn.setProperty("btnRole", role)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _build_native_menu(self) -> None:
        menu_bar = self.menuBar()
        menu_bar.clear()
        menu_bar.setNativeMenuBar(True)

        file_menu = menu_bar.addMenu("File")
        file_menu.addAction(self.ui_shell.actions["load_video"])
        file_menu.addAction(self.ui_shell.actions["open_project"])
        file_menu.addAction(self.ui_shell.actions["save_project"])

        edit_menu = menu_bar.addMenu("Edit")
        edit_menu.addAction(self.ui_shell.actions["undo"])
        edit_menu.addAction(self.ui_shell.actions["clear_focus"])

        view_menu = menu_bar.addMenu("View")
        view_menu.addAction(self.ui_shell.actions["toggle_score_preview"])

        clip_menu = menu_bar.addMenu("Clip")
        clip_menu.addAction(self.ui_shell.actions["mark_start"])
        clip_menu.addAction(self.ui_shell.actions["mark_end"])
        clip_menu.addAction(self.ui_shell.actions["highlight"])

        score_menu = menu_bar.addMenu("Score")
        score_menu.addAction(self.ui_shell.actions["point_a"])
        score_menu.addAction(self.ui_shell.actions["point_b"])

        export_menu = menu_bar.addMenu("Export")
        export_menu.addAction(self.ui_shell.actions["export"])
        export_menu.addAction(self.ui_shell.actions["export_highlights"])

        help_menu = menu_bar.addMenu("Help")
        help_menu.addAction(self.ui_shell.actions["about"])

    def _show_themed_question(self, title: str, text: str, yes_label: str = "Yes", no_label: str = "No") -> bool:
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        dialog.setMinimumWidth(420)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        title_label = QLabel(title)
        title_label.setObjectName("dialogTitle")
        body_label = QLabel(text)
        body_label.setWordWrap(True)
        body_label.setObjectName("statusValue")
        btns = QDialogButtonBox(dialog)
        yes_btn = btns.addButton(yes_label, QDialogButtonBox.ButtonRole.AcceptRole)
        no_btn = btns.addButton(no_label, QDialogButtonBox.ButtonRole.RejectRole)
        yes_btn.setProperty("btnRole", "primary")
        no_btn.setProperty("btnRole", "secondary")
        yes_btn.clicked.connect(dialog.accept)
        no_btn.clicked.connect(dialog.reject)
        layout.addWidget(title_label)
        layout.addWidget(body_label)
        layout.addWidget(btns)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def _show_themed_error(self, title: str, text: str) -> None:
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Critical)
        dialog.setWindowTitle(title)
        dialog.setText(text)
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        dialog.exec()

    def _wire_shell_actions(self) -> None:
        self._bind_shell_action("load_video", getattr(self, "load_videos", None))
        self._bind_shell_action("open_project", getattr(self, "load_project", None))
        self._bind_shell_action("save_project", getattr(self, "save_project", None))
        self._bind_shell_action("mark_start", getattr(self, "mark_start", None))
        self._bind_shell_action("mark_end", getattr(self, "mark_end", None))
        self._bind_shell_action("undo", getattr(self, "undo_last_action", None))
        self._bind_shell_action("play_pause", getattr(self, "toggle_play_pause", None))
        self._bind_shell_action("highlight", getattr(self, "add_last_point_to_highlights", None))
        self._bind_shell_action("export", getattr(self, "export_condensed", None))
        self._bind_shell_action("export_highlights", getattr(self, "export_highlights", None))
        self._bind_shell_action("clear_focus", getattr(self, "clear_edit_focus", None))

        if "toggle_score_preview" in self.ui_shell.actions:
            self.ui_shell.actions["toggle_score_preview"].setCheckable(False)
            self.ui_shell.actions["toggle_score_preview"].setEnabled(False)

        if "point_a" in self.ui_shell.actions:
            self.ui_shell.actions["point_a"].setEnabled(True)
            self.ui_shell.actions["point_a"].triggered.connect(lambda: self.tennis_point_winner("A"))
        if "point_b" in self.ui_shell.actions:
            self.ui_shell.actions["point_b"].setEnabled(True)
            self.ui_shell.actions["point_b"].triggered.connect(lambda: self.tennis_point_winner("B"))

        # Explicitly keep non-implemented UI actions disabled.
        if "about" in self.ui_shell.actions:
            self.ui_shell.actions["about"].setEnabled(False)

        self._build_native_menu()

    def _setup_hotkey_ui(self) -> None:
        label_map = {
            "play_pause": "Play/Pause",
            "jump_back_5": "Indietro 5s",
            "jump_fwd_5": "Avanti 5s",
            "jump_back_10": "Indietro 10s",
            "jump_fwd_10": "Avanti 10s",
            "jump_back_30": "Indietro 30s",
            "jump_fwd_30": "Avanti 30s",
            "mark_start": "Inizio punto",
            "mark_end": "Pausa/Riprendi clip",
            "point_a": "Punto A",
            "point_b": "Punto B",
            "undo": "Undo",
            "clear_focus": "Rilascia focus",
        }
        group_map = {
            "play_pause": "playback",
            "jump_back_5": "playback",
            "jump_fwd_5": "playback",
            "jump_back_10": "playback",
            "jump_fwd_10": "playback",
            "jump_back_30": "playback",
            "jump_fwd_30": "playback",
            "mark_start": "marking",
            "mark_end": "marking",
            "point_a": "marking",
            "point_b": "marking",
            "undo": "utility",
            "clear_focus": "utility",
        }
        group_row = {"playback": 1, "marking": 1, "utility": 1}
        row = 1
        for action, default_seq in self.hotkey_defaults.items():
            edit = QKeySequenceEdit(QKeySequence(default_seq))
            edit.keySequenceChanged.connect(self._bind_shortcuts)
            target_group = group_map.get(action, "utility")
            target_layout = self.hotkeys_group_widgets.get(target_group, self.hotkeys_layout)
            target_row = group_row.get(target_group, row)
            target_layout.addWidget(QLabel(label_map[action]), target_row, 0)
            target_layout.addWidget(edit, target_row, 1)
            group_row[target_group] = target_row + 1
            self.hotkey_edits[action] = edit
            row += 1

    def _bind_shortcuts(self) -> None:
        for shortcut in self.shortcuts.values():
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self.shortcuts.clear()

        actions = {
            "play_pause": self.toggle_play_pause,
            "jump_back_5": lambda: self.jump(-5),
            "jump_fwd_5": lambda: self.jump(5),
            "jump_back_10": lambda: self.jump(-10),
            "jump_fwd_10": lambda: self.jump(10),
            "jump_back_30": lambda: self.jump(-30),
            "jump_fwd_30": lambda: self.jump(30),
            "mark_start": self.mark_start,
            "mark_end": self.mark_end,
            "point_a": lambda: self.tennis_point_winner("A"),
            "point_b": lambda: self.tennis_point_winner("B"),
            "undo": self.undo_last_action,
            "clear_focus": self.clear_edit_focus,
        }

        for key, callback in actions.items():
            seq = self.hotkey_edits[key].keySequence()
            if seq.isEmpty():
                continue
            shortcut = QShortcut(seq, self)
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            shortcut.activated.connect(lambda cb=callback: self._run_shortcut_action(cb))
            self.shortcuts[key] = shortcut
        if hasattr(self, "ui_shell"):
            self.ui_shell.hotkeys_state_label.setText("Hotkeys: active")

    def _run_shortcut_action(self, callback) -> None:
        focus = self.focusWidget()
        if isinstance(focus, QKeySequenceEdit):
            return
        callback()

    def _refresh_point_open_chip(self) -> None:
        if hasattr(self, "server_status_chip"):
            self.server_status_chip.setText(f"Server: {self.current_server}")
        self._sync_legacy_pending_fields()
        if hasattr(self, "point_open_chip"):
            if self.capture_state != "IDLE" and self.pending_point_start is not None:
                self.point_open_chip.setText(f"PUNTO APERTO {format_time(self.pending_point_start)}")
                self.point_open_chip.setProperty("chipState", "active")
            else:
                self.point_open_chip.setText("Idle")
                self.point_open_chip.setProperty("chipState", "idle")
            self.point_open_chip.style().unpolish(self.point_open_chip)
            self.point_open_chip.style().polish(self.point_open_chip)
        if hasattr(self, "transport_status_chip"):
            if self.capture_state != "IDLE" and self.pending_point_start is not None:
                self.transport_status_chip.setText(f"REC {format_time(self.pending_point_start)}")
                self.transport_status_chip.setProperty("chipState", "active")
            else:
                self.transport_status_chip.setText("Ready")
                self.transport_status_chip.setProperty("chipState", "idle")
            self.transport_status_chip.style().unpolish(self.transport_status_chip)
            self.transport_status_chip.style().polish(self.transport_status_chip)

    def _refresh_shell_empty_states(self) -> None:
        has_video = bool(self.input_path)
        if hasattr(self, "video_stage_stack"):
            # 0: video stage, 1: empty state surface
            self.video_stage_stack.widget(1).setVisible(not has_video)
        if hasattr(self, "empty_state_load_btn"):
            self.empty_state_load_btn.setEnabled(True)
        if hasattr(self, "source_empty_label"):
            if len(self.input_paths) == 0:
                self.source_empty_label.setText("No source loaded")
                self.source_empty_label.setVisible(True)
            else:
                active_name = os.path.basename(self.input_path) if self.input_path else os.path.basename(self.input_paths[0])
                self.source_empty_label.setText(f"Active: {active_name}")
                self.source_empty_label.setVisible(True)
        if hasattr(self, "segments_empty_label"):
            self.segments_empty_label.setVisible(len(self.segments) == 0)
        if hasattr(self, "points_empty_label"):
            self.points_empty_label.setVisible(len(self.points) == 0)
        if hasattr(self, "highlights_empty_label"):
            has_highlights = any(point.is_highlight for point in self.points)
            self.highlights_empty_label.setVisible(not has_highlights)
        self._refresh_point_open_chip()

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def points_text(self, points: int) -> str:
        if points <= 3:
            return str(self.POINT_VALUES[points])
        return "AD"

    def active_points_text(self) -> tuple[str, str]:
        if self.in_tiebreak:
            return str(self.tb_points_a), str(self.tb_points_b)
        return self.points_text(self.points_a), self.points_text(self.points_b)

    def _overlay_set_columns(self) -> tuple[str, str, str, str]:
        # Overlay shows only first two set columns for readability.
        set1_a = ""
        set1_b = ""
        set2_a = ""
        set2_b = ""
        if len(self.completed_sets) >= 1:
            set1_a = str(self.completed_sets[0][0])
            set1_b = str(self.completed_sets[0][1])
        else:
            set1_a = str(self.games_a)
            set1_b = str(self.games_b)

        if len(self.completed_sets) >= 2:
            set2_a = str(self.completed_sets[1][0])
            set2_b = str(self.completed_sets[1][1])
        elif len(self.completed_sets) == 1:
            set2_a = str(self.games_a)
            set2_b = str(self.games_b)
        return set1_a, set1_b, set2_a, set2_b

    def _wins_game_on_point(self, side: str, points_a: int, points_b: int, in_tiebreak: bool) -> bool:
        if in_tiebreak:
            return False
        if side == "A":
            if points_a <= 2:
                return False
            if points_a == 3 and points_b <= 2:
                return True
            if points_a == 4:
                return True
            return False
        if points_b <= 2:
            return False
        if points_b == 3 and points_a <= 2:
            return True
        if points_b == 4:
            return True
        return False

    def _set_winner_if_point_won(self, side: str) -> str | None:
        if self.in_tiebreak:
            a_tb = self.tb_points_a + (1 if side == "A" else 0)
            b_tb = self.tb_points_b + (1 if side == "B" else 0)
            if a_tb >= self.tiebreak_target and a_tb - b_tb >= 2:
                return "A"
            if b_tb >= self.tiebreak_target and b_tb - a_tb >= 2:
                return "B"
            return None

        if not self._wins_game_on_point(side, self.points_a, self.points_b, False):
            return None

        new_games_a = self.games_a + (1 if side == "A" else 0)
        new_games_b = self.games_b + (1 if side == "B" else 0)
        if new_games_a >= 6 and new_games_a - new_games_b >= 2:
            return "A"
        if new_games_b >= 6 and new_games_b - new_games_a >= 2:
            return "B"
        return None

    def _match_winner_if_point_won(self, side: str) -> str | None:
        set_winner = self._set_winner_if_point_won(side)
        if not set_winner:
            return None
        needed_sets = 2 if self.best_of.currentIndex() == 0 else 3
        new_sets_a = self.sets_a + (1 if set_winner == "A" else 0)
        new_sets_b = self.sets_b + (1 if set_winner == "B" else 0)
        if new_sets_a >= needed_sets:
            return "A"
        if new_sets_b >= needed_sets:
            return "B"
        return None

    def _current_alert_banner(self) -> str:
        if self._match_winner_if_point_won("A") or self._match_winner_if_point_won("B"):
            return "MATCH POINT"
        if self._set_winner_if_point_won("A") or self._set_winner_if_point_won("B"):
            return "SET POINT"
        receiver = self._opponent(self.current_server)
        if self._wins_game_on_point(receiver, self.points_a, self.points_b, self.in_tiebreak):
            return "BREAK POINT"
        return ""

    def current_overlay_state(self) -> OverlayState:
        points_a_text, points_b_text = self.active_points_text()
        set1_a, set1_b, set2_a, set2_b = self._overlay_set_columns()
        return OverlayState(
            player_a=self.player_a_input.text().strip() or "Giocatore A",
            player_b=self.player_b_input.text().strip() or "Giocatore B",
            sets_a=self.sets_a,
            sets_b=self.sets_b,
            games_a=self.games_a,
            games_b=self.games_b,
            points_a=points_a_text,
            points_b=points_b_text,
            server=self.current_server,
            tournament=self.tournament_input.text().strip() or "Amateur Tennis Tour",
            overlay_corner=self.overlay_corner_combo.currentText(),
            overlay_scale=self.overlay_widget.scale_factor,
            set_col1_a=set1_a,
            set_col1_b=set1_b,
            set_col2_a=set2_a,
            set_col2_b=set2_b,
            alert_banner=self._current_alert_banner(),
            flag_a_code=normalize_flag_code(self.flag_a_code_input.text()),
            flag_b_code=normalize_flag_code(self.flag_b_code_input.text()),
            flag_a_path=self.flag_a_path,
            flag_b_path=self.flag_b_path,
        )

    def _clone_overlay_state(self, state: OverlayState) -> OverlayState:
        return OverlayState(**asdict(state))

    def _get_open_point_index(self) -> int | None:
        if self.open_point_id is None:
            return None
        for idx, point in enumerate(self.points):
            if point.id == self.open_point_id:
                return idx
        return None

    def _sync_legacy_pending_fields(self) -> None:
        if self.capture_state == "IDLE":
            self.pending_point_start = None
            self.pending_point_source_path = None
            return
        idx = self._get_open_point_index()
        if idx is None:
            self.pending_point_start = None
            self.pending_point_source_path = None
            return
        point = self.points[idx]
        first_clip = point.clips[0] if point.clips else None
        self.pending_point_start = (
            self.open_clip_start
            if self.capture_state == "RECORDING" and self.open_clip_start is not None
            else (first_clip.start if first_clip else self.current_time_sec())
        )
        self.pending_point_source_path = (
            self.open_clip_source_path
            if self.capture_state == "RECORDING" and self.open_clip_source_path
            else (first_clip.source_path if first_clip else self.input_path)
        )

    def _point_source_bounds(self, point: PointRecord, source_path: str) -> tuple[float, float] | None:
        source_clips = [clip for clip in point.clips if clip.source_path == source_path]
        if not source_clips:
            return None
        start = min(clip.start for clip in source_clips)
        end = max(clip.end for clip in source_clips)
        return (start, end)

    def _resolve_point_selection_for_position(self, source_path: str, local_t: float) -> int | None:
        source_entries: list[tuple[int, float, float]] = []
        for idx, point in enumerate(self.points):
            bounds = self._point_source_bounds(point, source_path)
            if bounds is None:
                continue
            source_entries.append((idx, bounds[0], bounds[1]))
        if not source_entries:
            return None
        source_entries.sort(key=lambda item: (item[1], self.points[item[0]].id))
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

    def _sync_selected_point_from_timeline(self) -> None:
        if not self.input_path:
            self.selected_point_index = None
            self.selected_point_id = None
            self._sync_points_list_selection()
            return
        idx = self._resolve_point_selection_for_position(self.input_path, self.current_time_sec())
        if idx is None:
            self.selected_point_index = None
            self.selected_point_id = None
            self._sync_points_list_selection()
            return
        self.selected_point_index = idx
        self.selected_point_id = self.points[idx].id
        self._sync_points_list_selection()

    def _sync_selected_point_index_from_id(self) -> None:
        if self.selected_point_id is None:
            self.selected_point_index = None
            return
        for idx, point in enumerate(self.points):
            if point.id == self.selected_point_id:
                self.selected_point_index = idx
                return
        self.selected_point_index = None
        self.selected_point_id = None

    def _sync_points_list_selection(self) -> None:
        if not hasattr(self, "points_list"):
            return
        self.points_list.blockSignals(True)
        if self.selected_point_id is None:
            self.points_list.clearSelection()
        else:
            found_row = -1
            for row in range(self.points_list.count()):
                item = self.points_list.item(row)
                try:
                    if int(item.data(Qt.ItemDataRole.UserRole)) == self.selected_point_id:
                        found_row = row
                        break
                except (TypeError, ValueError):
                    continue
            if found_row >= 0:
                self.points_list.setCurrentRow(found_row)
            else:
                self.points_list.clearSelection()
        self.points_list.blockSignals(False)

    def _flatten_points_to_segments(self) -> list[Segment]:
        flat: list[Segment] = []
        ordered_points = sorted(self.points, key=lambda p: p.id)
        for point in ordered_points:
            overlay_ref = point.overlay_at_start or point.overlay_at_end or self.current_overlay_state()
            for clip in point.clips:
                if clip.end - clip.start <= 0:
                    continue
                flat.append(
                    Segment(
                        start=clip.start,
                        end=clip.end,
                        source_path=clip.source_path,
                        overlay=self._clone_overlay_state(overlay_ref),
                        is_highlight=point.is_highlight,
                    )
                )
        return flat

    def _rebuild_segments_from_points(self) -> None:
        self.segments = self._flatten_points_to_segments()

    def _append_clip_interval(
        self,
        point: PointRecord,
        start_source: str,
        start_time: float,
        end_source: str,
        end_time: float,
    ) -> int:
        if not self.input_paths:
            self.input_paths = [start_source]
        try:
            start_idx = self.input_paths.index(start_source)
            end_idx = self.input_paths.index(end_source)
        except ValueError:
            if start_source != end_source:
                self.set_status("Intervallo clip non valido: sorgente iniziale/finale non trovata.")
                return 0
            start_idx = end_idx = 0
        if end_idx < start_idx:
            self.set_status("Intervallo clip non valido: la sorgente finale precede quella iniziale.")
            return 0
        created = 0
        min_duration = 0.15
        for idx in range(start_idx, end_idx + 1):
            source_path = self.input_paths[idx] if self.input_paths else start_source
            seg_start = start_time if idx == start_idx else 0.0
            if idx == end_idx:
                seg_end = end_time
            else:
                duration = self._probe_clip_duration(source_path)
                if duration is None:
                    self.set_status(f"Impossibile leggere la durata clip: {os.path.basename(source_path)}")
                    return created
                seg_end = duration
            start = min(seg_start, seg_end)
            end = max(seg_start, seg_end)
            if end - start < min_duration:
                continue
            point.clips.append(PointClip(start=start, end=end, source_path=source_path))
            created += 1
        return created

    def _replay_score_from_points(self) -> None:
        self.starting_server = self._server_from_combo()
        self.current_server = self.starting_server
        self.tiebreak_first_server = None
        self.points_a = 0
        self.points_b = 0
        self.tb_points_a = 0
        self.tb_points_b = 0
        self.in_tiebreak = False
        self.tiebreak_target = 7
        self.tiebreak_super = False
        self.completed_sets = []
        self.completed_set_tb_loser_points = []
        self.games_a = 0
        self.games_b = 0
        self.sets_a = 0
        self.sets_b = 0
        for point in sorted(self.points, key=lambda p: p.id):
            if point.winner in ("A", "B"):
                self._apply_point_winner_to_score(point.winner)
        self._set_server_combo(self.current_server)
        self.sets_a_input.setText(str(self.sets_a))
        self.sets_b_input.setText(str(self.sets_b))
        self.games_a_input.setText(str(self.games_a))
        self.games_b_input.setText(str(self.games_b))

    def _server_from_combo(self) -> str:
        return "A" if self.server_combo.currentIndex() == 0 else "B"

    def _set_server_combo(self, server: str) -> None:
        self.server_combo.blockSignals(True)
        self.server_combo.setCurrentIndex(0 if server == "A" else 1)
        self.server_combo.blockSignals(False)

    def _opponent(self, side: str) -> str:
        return "B" if side == "A" else "A"

    def on_server_selection_changed(self, _index: int | None = None) -> None:
        # The dropdown sets who starts serving; auto-switch logic keeps advancing it.
        selected = self._server_from_combo()
        self.starting_server = selected
        self.current_server = selected
        self.tiebreak_first_server = None
        self.update_overlay()

    def update_overlay(self) -> None:
        self.overlay_widget.apply_state(self.current_overlay_state())
        # Reposition after state changes (e.g. banner shown/hidden) so bottom corners stay in-frame.
        self.video_container.position_overlay()
        self.update_point_buttons()
        self.update_score_preview_label()

    def _short_player_name(self, raw: str, fallback: str) -> str:
        name = raw.strip() or fallback
        return name if len(name) <= 14 else f"{name[:14]}..."

    def update_point_buttons(self) -> None:
        name_a = self._short_player_name(self.player_a_input.text(), "A")
        name_b = self._short_player_name(self.player_b_input.text(), "B")
        self.point_a_btn.setText(f"Punto {name_a}")
        self.point_b_btn.setText(f"Punto {name_b}")
        is_idle = self.capture_state == "IDLE"
        self.mark_start_btn.setEnabled(bool(self.input_path) and is_idle)
        if self.capture_state == "RECORDING":
            self.mark_end_btn.setText("Pausa clip")
            self.mark_end_btn.setEnabled(True)
        elif self.capture_state == "PAUSED_WITHIN_POINT":
            self.mark_end_btn.setText("Riprendi clip")
            self.mark_end_btn.setEnabled(True)
        else:
            self.mark_end_btn.setText("Pausa clip")
            self.mark_end_btn.setEnabled(False)
        can_award = self.capture_state in ("RECORDING", "PAUSED_WITHIN_POINT")
        if self.capture_state == "PAUSED_WITHIN_POINT":
            idx = self._get_open_point_index()
            can_award = idx is not None and len(self.points[idx].clips) > 0
        self.point_a_btn.setEnabled(can_award)
        self.point_b_btn.setEnabled(can_award)

    def update_score_preview_label(self) -> None:
        state = self.current_overlay_state()
        prefix = "Timeline"
        preview = self.overlay_state_for_current_position()
        if preview is not None:
            state = preview
        else:
            last_state = self.last_overlay_state_for_active_clip()
            if last_state is not None:
                state = last_state
                prefix = "Ultimo punto"
        self.score_preview_label.setText(
            f"Preview {prefix}: Game {state.games_a}-{state.games_b} | Pts {state.points_a}-{state.points_b}"
        )
        if hasattr(self, "score_summary_card"):
            name_a = self._short_player_name(state.player_a, "A")
            name_b = self._short_player_name(state.player_b, "B")
            self.score_summary_card.setText(
                f"{name_a}  S{state.sets_a} G{state.games_a} P{state.points_a}    "
                f"{name_b}  S{state.sets_b} G{state.games_b} P{state.points_b}"
            )
        self._refresh_point_open_chip()

    def overlay_state_for_current_position(self) -> OverlayState | None:
        if not self.input_path or not self.segments:
            return None
        now = self.current_time_sec()
        matches = [s for s in self.segments if s.source_path == self.input_path and s.start <= now]
        if not matches:
            return None
        matches.sort(key=lambda s: s.start)
        return matches[-1].overlay

    def last_overlay_state_for_active_clip(self) -> OverlayState | None:
        if not self.input_path or not self.segments:
            return None
        matches = [s for s in self.segments if s.source_path == self.input_path]
        if not matches:
            return None
        matches.sort(key=lambda s: s.start)
        return matches[-1].overlay

    def preview_overlay_frame(self) -> None:
        if not self.input_path:
            QMessageBox.warning(self, "Errore", "Carica prima un video.")
            return

        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        t = max(0.0, self.current_time_sec())
        overlay_state = self.current_overlay_state()
        with tempfile.TemporaryDirectory(prefix="overlay-preview-") as td:
            out_png = os.path.join(td, "preview.png")
            cmd = [
                ffmpeg_bin,
                "-y",
                "-ss",
                f"{t:.3f}",
                "-i",
                self.input_path,
                "-frames:v",
                "1",
                "-filter_complex",
                build_overlay_filter(overlay_state),
                "-map",
                "[out]",
                out_png,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0 or not os.path.exists(out_png):
                QMessageBox.critical(self, "Errore preview", res.stderr.strip() or "Preview fallita.")
                return

            dialog = QDialog(self)
            dialog.setObjectName("overlayPreviewDialog")
            dialog.setWindowTitle("Preview grafica overlay")
            dialog.setMinimumSize(900, 560)
            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(14, 14, 14, 14)
            layout.setSpacing(10)
            title = QLabel("Preview grafica overlay")
            title.setObjectName("dialogTitle")
            scale_label = self.overlay_scale_combo.currentText().strip() or f"{int(overlay_state.overlay_scale * 100)}%"
            info = QLabel(
                f"Frame a {format_time(t)} | Posizione {overlay_state.overlay_corner} | Scala {scale_label}"
            )
            info.setObjectName("previewMetaLabel")
            img_wrap = QFrame()
            img_wrap.setObjectName("previewImageContainer")
            img_wrap_layout = QVBoxLayout(img_wrap)
            img_wrap_layout.setContentsMargins(10, 10, 10, 10)
            img_wrap_layout.setSpacing(0)
            img = QLabel()
            img.setObjectName("previewImageLabel")
            img.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pix = QPixmap(out_png)
            img.setPixmap(
                pix.scaled(
                    1280,
                    720,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            img_wrap_layout.addWidget(img, 1)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dialog)
            buttons.rejected.connect(dialog.reject)
            buttons.accepted.connect(dialog.accept)
            layout.addWidget(title)
            layout.addWidget(info)
            layout.addWidget(img_wrap, 1)
            layout.addWidget(buttons)
            dialog.exec()

    def sync_overlay_state_from_inputs(self) -> None:
        prev_sets = (self.sets_a, self.sets_b)
        prev_games = (self.games_a, self.games_b)
        self.sets_a = self._int_or_default(self.sets_a_input.text(), self.sets_a)
        self.sets_b = self._int_or_default(self.sets_b_input.text(), self.sets_b)
        self.games_a = self._int_or_default(self.games_a_input.text(), self.games_a)
        self.games_b = self._int_or_default(self.games_b_input.text(), self.games_b)
        if (self.sets_a, self.sets_b) != prev_sets or (self.games_a, self.games_b) != prev_games:
            # Manual override invalidates reconstructed set history.
            self.completed_sets = []
            self.completed_set_tb_loser_points = []
        self.sets_a_input.setText(str(self.sets_a))
        self.sets_b_input.setText(str(self.sets_b))
        self.games_a_input.setText(str(self.games_a))
        self.games_b_input.setText(str(self.games_b))
        self.update_overlay()

    def _flags_cache_dir(self) -> str:
        # Use an app-writable location; bundled macOS apps may run with a read-only cwd.
        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        if not base:
            base = os.path.join(os.path.expanduser("~"), ".tennis-match-condenser")
        path = os.path.join(base, "flags_cache")
        os.makedirs(path, exist_ok=True)
        return path

    def _resolve_local_flag_path(self, code: str) -> str:
        if not code:
            return ""
        cached = os.path.join(self._flags_cache_dir(), f"{code.lower()}.png")
        return cached if os.path.exists(cached) else ""

    def on_flag_codes_changed(self) -> None:
        self.flag_a_code_input.setText(normalize_flag_code(self.flag_a_code_input.text()))
        self.flag_b_code_input.setText(normalize_flag_code(self.flag_b_code_input.text()))
        self.flag_a_path = self._resolve_local_flag_path(self.flag_a_code_input.text())
        self.flag_b_path = self._resolve_local_flag_path(self.flag_b_code_input.text())
        if self.flag_a_path or self.flag_b_path:
            self.flags_status_label.setText("Bandiere locali caricate dalla cache.")
        else:
            self.flags_status_label.setText("Bandiere non presenti in cache. Clicca download.")
        self.update_overlay()

    def download_flags(self) -> None:
        code_a = normalize_flag_code(self.flag_a_code_input.text())
        code_b = normalize_flag_code(self.flag_b_code_input.text())
        if not code_a and not code_b:
            QMessageBox.warning(self, "Bandiere", "Inserisci almeno un codice paese ISO2 (es. IT, ES).")
            return
        cache_dir = self._flags_cache_dir()
        downloaded: list[str] = []
        failed: list[str] = []
        failures_detail: dict[str, str] = {}
        ssl_ctx = ssl.create_default_context()
        for code in [code_a, code_b]:
            if not code:
                continue
            target = os.path.join(cache_dir, f"{code.lower()}.png")
            candidates = [
                f"https://raw.githubusercontent.com/ashleedawg/flags/master/{code}.png",
                f"https://raw.githubusercontent.com/ashleedawg/flags/master/{code.lower()}.png",
                f"https://raw.githubusercontent.com/ashleedawg/flags/main/{code}.png",
                f"https://raw.githubusercontent.com/ashleedawg/flags/main/{code.lower()}.png",
            ]
            last_error = "not found"
            ok = False
            for url in candidates:
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "tennis-match-condenser/1.5"})
                    with urllib.request.urlopen(req, timeout=15, context=ssl_ctx) as response:
                        payload = response.read()
                    if not payload:
                        raise RuntimeError("empty file")
                    with open(target, "wb") as out:
                        out.write(payload)
                    downloaded.append(code)
                    ok = True
                    break
                except urllib.error.HTTPError as exc:
                    last_error = f"HTTP {exc.code}"
                except urllib.error.URLError as exc:
                    last_error = f"network {exc.reason}"
                except ssl.SSLError as exc:
                    last_error = f"ssl {exc}"
                except (TimeoutError, OSError, RuntimeError) as exc:
                    last_error = str(exc)
            if not ok:
                failed.append(code)
                failures_detail[code] = last_error
        self.flag_a_path = self._resolve_local_flag_path(code_a)
        self.flag_b_path = self._resolve_local_flag_path(code_b)
        if downloaded and not failed:
            self.flags_status_label.setText(f"Bandiere scaricate: {', '.join(downloaded)}")
        elif downloaded and failed:
            self.flags_status_label.setText(
                f"Scaricate: {', '.join(downloaded)} | Fallite: {', '.join(failed)}"
            )
        else:
            detail_txt = "; ".join(f"{k} ({v})" for k, v in failures_detail.items()) or ", ".join(failed)
            self.flags_status_label.setText(f"Download fallito per: {detail_txt}")
            QMessageBox.warning(
                self,
                "Bandiere",
                f"Download non riuscito.\nDettaglio: {detail_txt}\nVerifica connessione o codici ISO2.",
            )
        self.update_overlay()

    def on_overlay_corner_changed(self, corner: str) -> None:
        self.video_container.set_overlay_corner(corner)

    def on_overlay_scale_changed(self, value: str) -> None:
        try:
            key = str(value or "").strip()
            factor = OVERLAY_SCALE_PRESETS.get(key)
            if factor is None:
                # Fallback for unexpected combo text, e.g. "100 %" or custom locale formatting.
                digits = re.sub(r"[^0-9]", "", key)
                factor = (int(digits) / 100.0) if digits else 1.0
            factor = max(0.7, min(float(factor), 2.0))
            self.overlay_widget.apply_scale(factor)
            self.video_container.position_overlay()
        except Exception:
            # Never crash UI from a combo value parsing issue.
            self.overlay_widget.apply_scale(1.0)
            self.video_container.position_overlay()

    def _int_or_default(self, text: str, default: int) -> int:
        try:
            return max(0, int(text.strip()))
        except ValueError:
            return default

    def on_player_duration_changed(self, duration_ms: int) -> None:
        self.timeline_slider.setRange(0, max(0, duration_ms))
        self._update_time_label(self.player.position(), duration_ms)
        if self.input_path and duration_ms > 0:
            self.clip_duration_cache[self.input_path] = duration_ms / 1000.0
            self._update_source_fps_status(self.input_path)

    def on_player_position_changed(self, position_ms: int) -> None:
        if not self.is_scrubbing:
            self.timeline_slider.setValue(position_ms)
        self._update_time_label(position_ms, self.player.duration())
        self._sync_selected_point_from_timeline()
        self.update_overlay()

    def on_timeline_pressed(self) -> None:
        self.is_scrubbing = True

    def on_timeline_moved(self, value: int) -> None:
        self._update_time_label(value, self.player.duration())

    def on_timeline_released(self) -> None:
        self.is_scrubbing = False
        self.player.setPosition(self.timeline_slider.value())

    def _update_time_label(self, position_ms: int, duration_ms: int) -> None:
        cur = format_time(position_ms / 1000.0)
        total = format_time(duration_ms / 1000.0) if duration_ms > 0 else "0:00"
        self.time_label.setText(f"{cur} / {total}")

    def estimated_export_duration(self) -> float:
        total = 0.0
        for seg in self.segments:
            total += max(0.0, float(seg.end) - float(seg.start))
        return total

    def update_export_length_label(self) -> None:
        eta_txt = format_time(self.estimated_export_duration())
        self.export_length_label.setText(f"Durata export stimata: {eta_txt}")
        if hasattr(self, "ui_shell"):
            self.ui_shell.export_estimate_label.setText(f"Export: {eta_txt}")
        if hasattr(self, "export_summary_label"):
            hl_count = sum(1 for point in self.points if point.is_highlight)
            self.export_summary_label.setText(
                f"Clip: {len(self.segments)} | Punti highlight: {hl_count}"
            )

    def load_videos(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Seleziona video partita (uno o più file)",
            "",
            "Video Files (*.mp4 *.mov *.mkv *.avi)",
        )
        if not paths:
            return

        self.clear_edit_focus()
        self.input_paths = sorted(list(paths), key=lambda p: os.path.basename(p).lower())
        self.active_clip_combo.blockSignals(True)
        self.active_clip_combo.clear()
        for idx, path in enumerate(self.input_paths, 1):
            self.active_clip_combo.addItem(f"{idx}. {os.path.basename(path)}", path)
        self.active_clip_combo.blockSignals(False)
        self.active_clip_combo.setCurrentIndex(0)

        self.input_path = self.input_paths[0]
        self.player.setSource(QUrl.fromLocalFile(self.input_path))
        self.pending_point_start = None
        self.pending_point_source_path = None
        self.capture_state = "IDLE"
        self.open_point_id = None
        self.open_clip_start = None
        self.open_clip_source_path = None
        self.points.clear()
        self.selected_point_index = None
        self.selected_point_id = None
        self.next_point_id = 1
        self.intro_bg_path = None
        self.outro_bg_path = None
        self.intro_frame_ref = None
        self.outro_frame_ref = None
        self.clip_duration_cache.clear()
        self.segments.clear()
        self.undo_stack.clear()
        self.refresh_segments()
        self._refresh_intro_outro_labels()
        if hasattr(self, "ui_shell"):
            self.ui_shell.source_fps_label.setText("FPS: --")
        self._update_source_fps_status(self.input_path)
        self._refresh_shell_empty_states()
        if len(self.input_paths) == 1:
            self.set_status(f"Video caricato: {self.input_paths[0]}")
        else:
            self.set_status(
                f"{len(self.input_paths)} video caricati senza copie: seleziona la clip attiva e marca i punti. "
                "La concatenazione avviene solo in export."
            )
        self.autosave_project()

    def on_active_clip_changed(self, index: int) -> None:
        if index < 0:
            return
        data = self.active_clip_combo.itemData(index)
        if not data:
            return
        self.input_path = str(data)
        self.player.setSource(QUrl.fromLocalFile(self.input_path))
        self._update_source_fps_status(self.input_path)
        self._sync_selected_point_from_timeline()
        self._refresh_shell_empty_states()
        if self.capture_state != "IDLE":
            self.set_status(
                f"Clip attiva: {os.path.basename(self.input_path)} (punto in corso, chiudilo con Pausa clip o Punto A/B)."
            )
        else:
            self.set_status(f"Clip attiva: {os.path.basename(self.input_path)}")

    def _refresh_intro_outro_labels(self) -> None:
        if self.intro_frame_ref:
            intro_txt = f"{os.path.basename(self.intro_frame_ref['source_path'])} @ {format_time(self.intro_frame_ref['time'])}"
        elif self.intro_bg_path:
            intro_txt = f"legacy frame ({os.path.basename(self.intro_bg_path)})"
        else:
            intro_txt = "timestamp non selezionato"
        if self.use_intro_bg_for_outro.isChecked():
            outro_txt = "usa stesso timestamp intro"
        elif self.outro_frame_ref:
            outro_txt = f"{os.path.basename(self.outro_frame_ref['source_path'])} @ {format_time(self.outro_frame_ref['time'])}"
        elif self.outro_bg_path:
            outro_txt = f"legacy frame ({os.path.basename(self.outro_bg_path)})"
        else:
            outro_txt = "timestamp non selezionato"
        self.intro_bg_label.setText(f"Intro: {intro_txt}")
        self.outro_bg_label.setText(f"Outro: {outro_txt}")
        self.capture_outro_bg_btn.setEnabled(not self.use_intro_bg_for_outro.isChecked())

    def set_intro_timestamp_from_current(self) -> None:
        if not self.input_path:
            QMessageBox.warning(self, "Errore", "Carica prima un video.")
            return
        self.intro_frame_ref = {"source_path": self.input_path, "time": self.current_time_sec()}
        if self.use_intro_bg_for_outro.isChecked():
            self.outro_frame_ref = dict(self.intro_frame_ref)
        self._refresh_intro_outro_labels()
        self.set_status("Timestamp intro impostato dal frame corrente.")

    def set_outro_timestamp_from_current(self) -> None:
        if self.use_intro_bg_for_outro.isChecked():
            self.outro_frame_ref = dict(self.intro_frame_ref) if self.intro_frame_ref else None
            self._refresh_intro_outro_labels()
            return
        if not self.input_path:
            QMessageBox.warning(self, "Errore", "Carica prima un video.")
            return
        self.outro_frame_ref = {"source_path": self.input_path, "time": self.current_time_sec()}
        self._refresh_intro_outro_labels()
        self.set_status("Timestamp outro impostato dal frame corrente.")

    def _capture_frame_to_path(self, target_name: str) -> str | None:
        if not self.input_path:
            QMessageBox.warning(self, "Errore", "Carica prima un video.")
            return None
        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        t = max(0.0, self.current_time_sec())
        out_png = os.path.join(self.session_temp_dir.name, f"{target_name}_{time.time_ns()}.png")
        cmd = [
            ffmpeg_bin,
            "-y",
            "-ss",
            f"{t:.3f}",
            "-i",
            self.input_path,
            "-frames:v",
            "1",
            out_png,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0 or not os.path.exists(out_png):
            QMessageBox.critical(self, "Errore", res.stderr.strip() or "Impossibile catturare il frame.")
            return None
        return out_png

    def capture_intro_background(self) -> None:
        self.set_intro_timestamp_from_current()

    def capture_outro_background(self) -> None:
        self.set_outro_timestamp_from_current()

    def on_intro_toggled(self, _state: int | None = None) -> None:
        if self.enable_intro_checkbox.isChecked() and not self.intro_bg_path:
            choice = QMessageBox.question(
                self,
                "Frame intro",
                "Vuoi catturare subito il frame di background per l'intro dal tempo corrente?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if choice == QMessageBox.StandardButton.Yes:
                self.capture_intro_background()
        self._refresh_intro_outro_labels()

    def on_outro_toggled(self, _state: int | None = None) -> None:
        if self.enable_outro_checkbox.isChecked() and not self.use_intro_bg_for_outro.isChecked() and not self.outro_bg_path:
            choice = QMessageBox.question(
                self,
                "Frame outro",
                "Vuoi catturare subito il frame di background per l'outro dal tempo corrente?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if choice == QMessageBox.StandardButton.Yes:
                self.capture_outro_background()
        self._refresh_intro_outro_labels()

    def on_use_intro_bg_for_outro_toggled(self, _state: int | None = None) -> None:
        if self.use_intro_bg_for_outro.isChecked():
            self.outro_frame_ref = dict(self.intro_frame_ref) if self.intro_frame_ref else None
        self._refresh_intro_outro_labels()

    def _frame_from_ref(self, ref: dict | None, target_name: str) -> str | None:
        if not ref:
            return None
        src = ref.get("source_path")
        timestamp = float(ref.get("time", 0.0))
        if not src or not os.path.exists(src):
            return None
        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        out_png = os.path.join(self.session_temp_dir.name, f"{target_name}_{time.time_ns()}.png")
        cmd = [
            ffmpeg_bin,
            "-y",
            "-ss",
            f"{max(0.0, timestamp):.3f}",
            "-i",
            src,
            "-frames:v",
            "1",
            out_png,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0 or not os.path.exists(out_png):
            return None
        self._ephemeral_export_frames.append(out_png)
        return out_png

    def _duration_from_input(self, field: QLineEdit, default: float = 5.0) -> float:
        try:
            value = float(field.text().strip())
            return max(0.5, min(value, 60.0))
        except ValueError:
            return default

    def _intro_config(self) -> dict | None:
        if not self.enable_intro_checkbox.isChecked():
            return None
        bg = self._frame_from_ref(self.intro_frame_ref, "intro_bg")
        if not bg and self.intro_bg_path and os.path.exists(self.intro_bg_path):
            bg = self.intro_bg_path
        if not bg:
            QMessageBox.warning(self, "Intro", "Seleziona un timestamp per l'intro.")
            return None
        player_a = self.player_a_input.text().strip() or "Giocatore A"
        player_b = self.player_b_input.text().strip() or "Giocatore B"
        rank_a = self.rank_a_input.text().strip()
        rank_b = self.rank_b_input.text().strip()
        round_name = self.round_input.text().strip() or "Round"
        lines = [
            self.tournament_input.text().strip() or "Amateur Tennis Tour",
            round_name,
            f"{player_a}{f' (#{rank_a})' if rank_a else ''}",
            f"{player_b}{f' (#{rank_b})' if rank_b else ''}",
        ]
        return {
            "background_path": bg,
            "duration": self._duration_from_input(self.intro_duration_input, 5.0),
            "lines": lines,
        }

    def _superscript_digits(self, value: int) -> str:
        mapping = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")
        return str(value).translate(mapping)

    def _final_score_lines(self) -> list[str]:
        player_a = (self.player_a_input.text().strip() or "Player A")[:16]
        player_b = (self.player_b_input.text().strip() or "Player B")[:16]
        set_scores = list(self.completed_sets)
        if self.games_a > 0 or self.games_b > 0:
            set_scores.append((self.games_a, self.games_b))
        if not set_scores:
            set_scores = [(0, 0)]

        set_cols = max(3, len(set_scores))
        a_cells = []
        b_cells = []
        for idx in range(set_cols):
            if idx < len(set_scores):
                a_g, b_g = set_scores[idx]
                a_txt = str(a_g)
                b_txt = str(b_g)
                tb_loser = self.completed_set_tb_loser_points[idx] if idx < len(self.completed_set_tb_loser_points) else None
                if tb_loser is not None:
                    sup = self._superscript_digits(tb_loser)
                    if a_g > b_g:
                        a_txt = f"{a_txt}{sup}"
                    else:
                        b_txt = f"{b_txt}{sup}"
                a_cells.append(a_txt)
                b_cells.append(b_txt)
            else:
                a_cells.append("")
                b_cells.append("")

        name_w = max(len(player_a), len(player_b), 12)
        sets_w = max(len(str(self.sets_a)), len(str(self.sets_b)), 1)
        cell_w = 4
        row_a = f"{player_a:<{name_w}}  {self.sets_a:>{sets_w}} | " + " ".join(
            f"{v:>{cell_w}}" for v in a_cells
        )
        row_b = f"{player_b:<{name_w}}  {self.sets_b:>{sets_w}} | " + " ".join(
            f"{v:>{cell_w}}" for v in b_cells
        )
        lines = [
            "FINAL RESULT",
            row_a,
            row_b,
        ]
        return lines

    def _outro_config(self) -> dict | None:
        if not self.enable_outro_checkbox.isChecked():
            return None
        ref = self.intro_frame_ref if self.use_intro_bg_for_outro.isChecked() else self.outro_frame_ref
        bg = self._frame_from_ref(ref, "outro_bg")
        if not bg:
            legacy_bg = self.intro_bg_path if self.use_intro_bg_for_outro.isChecked() else self.outro_bg_path
            if legacy_bg and os.path.exists(legacy_bg):
                bg = legacy_bg
        if not bg:
            QMessageBox.warning(self, "Outro", "Seleziona un timestamp per l'outro (o usa quello dell'intro).")
            return None
        round_name = self.round_input.text().strip() or "Round"
        lines = [
            self.tournament_input.text().strip() or "Amateur Tennis Tour",
            round_name,
        ]
        lines.extend(self._final_score_lines())
        return {
            "background_path": bg,
            "duration": self._duration_from_input(self.outro_duration_input, 5.0),
            "lines": lines,
        }

    def _set_scale_combo_from_factor(self, factor: float) -> None:
        clamped = max(0.7, min(factor, 2.0))
        nearest_label = min(
            OVERLAY_SCALE_PRESETS.keys(),
            key=lambda label: abs(OVERLAY_SCALE_PRESETS[label] - clamped),
        )
        self.overlay_scale_combo.blockSignals(True)
        self.overlay_scale_combo.setCurrentText(nearest_label)
        self.overlay_scale_combo.blockSignals(False)

    def _project_payload(self) -> dict:
        self._sync_legacy_pending_fields()
        self._rebuild_segments_from_points()
        current_clip_index = self.active_clip_combo.currentIndex()
        return {
            "version": 4,
            "input_paths": self.input_paths,
            "current_clip_index": current_clip_index,
            "pending_point_start": self.pending_point_start,
            "pending_point_source_path": self.pending_point_source_path,
            "next_point_id": self.next_point_id,
            "selected_point_id": self.selected_point_id,
            "capture_state": self.capture_state,
            "points": [
                {
                    "id": point.id,
                    "winner": point.winner,
                    "is_highlight": point.is_highlight,
                    "clips": [asdict(clip) for clip in point.clips],
                    "overlay_at_start": asdict(point.overlay_at_start) if point.overlay_at_start else None,
                    "overlay_at_end": asdict(point.overlay_at_end) if point.overlay_at_end else None,
                }
                for point in self.points
            ],
            "segments": [asdict(seg) for seg in self.segments],
            "state": {
                "points_a": self.points_a,
                "points_b": self.points_b,
                "tb_points_a": self.tb_points_a,
                "tb_points_b": self.tb_points_b,
                "games_a": self.games_a,
                "games_b": self.games_b,
                "sets_a": self.sets_a,
                "sets_b": self.sets_b,
                "completed_sets": self.completed_sets,
                "completed_set_tb_loser_points": self.completed_set_tb_loser_points,
                "in_tiebreak": self.in_tiebreak,
                "tiebreak_target": self.tiebreak_target,
                "tiebreak_super": self.tiebreak_super,
                "starting_server": self.starting_server,
                "current_server": self.current_server,
                "tiebreak_first_server": self.tiebreak_first_server,
                "tournament": self.tournament_input.text(),
                "player_a": self.player_a_input.text(),
                "player_b": self.player_b_input.text(),
                "rank_a": self.rank_a_input.text(),
                "rank_b": self.rank_b_input.text(),
                "flag_a_code": self.flag_a_code_input.text(),
                "flag_b_code": self.flag_b_code_input.text(),
                "round_name": self.round_input.text(),
                "best_of_index": self.best_of.currentIndex(),
                "deciding_set_mode_index": self.deciding_set_mode.currentIndex(),
                "server_index": self.server_combo.currentIndex(),
                "overlay_corner": self.overlay_corner_combo.currentText(),
                "overlay_scale": self.overlay_widget.scale_factor,
                "include_overlay": self.include_overlay.isChecked(),
                "preview_by_timeline": self.preview_by_timeline.isChecked(),
                "enable_intro": self.enable_intro_checkbox.isChecked(),
                "enable_outro": self.enable_outro_checkbox.isChecked(),
                "use_intro_bg_for_outro": self.use_intro_bg_for_outro.isChecked(),
                "intro_duration": self.intro_duration_input.text(),
                "outro_duration": self.outro_duration_input.text(),
                "intro_bg_path": self.intro_bg_path,
                "outro_bg_path": self.outro_bg_path,
                "intro_frame_ref": self.intro_frame_ref,
                "outro_frame_ref": self.outro_frame_ref,
            },
        }

    def save_project(self) -> None:
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Salva progetto",
            "tennis_project.json",
            "JSON (*.json)",
        )
        if not output_path:
            return
        if not output_path.lower().endswith(".json"):
            output_path += ".json"
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(self._project_payload(), f, indent=2, ensure_ascii=False)
            self.set_status(f"Progetto salvato: {output_path}")
            self.autosave_project()
        except Exception as exc:  # noqa: BLE001
            self._show_themed_error("Errore salvataggio", str(exc))

    def autosave_project(self) -> None:
        if not self.input_paths and not self.segments:
            return
        try:
            with open(self.autosave_path, "w", encoding="utf-8") as f:
                json.dump(self._project_payload(), f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def try_restore_autosave(self) -> None:
        if not os.path.exists(self.autosave_path):
            return
        accepted = self._show_themed_question(
            "Ripristino autosave",
            "Trovato un autosave progetto. Vuoi ripristinarlo?",
            "Ripristina",
            "Ignora",
        )
        if not accepted:
            return
        try:
            with open(self.autosave_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._load_project_data(data, self.autosave_path)
        except Exception:
            pass

    def load_project(self) -> None:
        input_path, _ = QFileDialog.getOpenFileName(
            self,
            "Carica progetto",
            "",
            "JSON (*.json)",
        )
        if not input_path:
            return
        try:
            with open(input_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._load_project_data(data, input_path)
        except Exception as exc:  # noqa: BLE001
            self._show_themed_error("Errore caricamento progetto", str(exc))

    def _load_project_data(self, data: dict, source_label: str) -> None:
        input_paths = data.get("input_paths", [])
        if not isinstance(input_paths, list):
            raise ValueError("Formato progetto non valido: input_paths.")
        existing_paths = [p for p in input_paths if isinstance(p, str) and os.path.exists(p)]
        if not existing_paths:
            raise ValueError("Nessun file video sorgente trovato sul disco.")

        self.input_paths = existing_paths
        self.active_clip_combo.blockSignals(True)
        self.active_clip_combo.clear()
        for idx, path in enumerate(self.input_paths, 1):
            self.active_clip_combo.addItem(f"{idx}. {os.path.basename(path)}", path)
        self.active_clip_combo.blockSignals(False)

        clip_index = int(data.get("current_clip_index", 0))
        clip_index = min(max(0, clip_index), len(self.input_paths) - 1)
        self.active_clip_combo.setCurrentIndex(clip_index)
        self.input_path = self.input_paths[clip_index]
        self.player.setSource(QUrl.fromLocalFile(self.input_path))
        self._update_source_fps_status(self.input_path)

        state = data.get("state", {})
        self.points_a = int(state.get("points_a", 0))
        self.points_b = int(state.get("points_b", 0))
        self.tb_points_a = int(state.get("tb_points_a", 0))
        self.tb_points_b = int(state.get("tb_points_b", 0))
        self.games_a = int(state.get("games_a", 0))
        self.games_b = int(state.get("games_b", 0))
        self.sets_a = int(state.get("sets_a", 0))
        self.sets_b = int(state.get("sets_b", 0))
        raw_completed_sets = state.get("completed_sets", [])
        parsed_completed_sets: list[tuple[int, int]] = []
        if isinstance(raw_completed_sets, list):
            for item in raw_completed_sets:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    try:
                        parsed_completed_sets.append((int(item[0]), int(item[1])))
                    except (TypeError, ValueError):
                        continue
        self.completed_sets = parsed_completed_sets
        raw_tb_loser_points = state.get("completed_set_tb_loser_points", [])
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
        while len(parsed_tb_loser_points) < len(self.completed_sets):
            parsed_tb_loser_points.append(None)
        self.completed_set_tb_loser_points = parsed_tb_loser_points[: len(self.completed_sets)]
        self.in_tiebreak = bool(state.get("in_tiebreak", False))
        self.tiebreak_target = int(state.get("tiebreak_target", 7))
        self.tiebreak_super = bool(state.get("tiebreak_super", False))
        self.starting_server = str(state.get("starting_server", "A"))
        self.current_server = str(state.get("current_server", self.starting_server))
        self.tiebreak_first_server = state.get("tiebreak_first_server")

        self.tournament_input.setText(str(state.get("tournament", "Amateur Tennis Tour")))
        self.player_a_input.setText(str(state.get("player_a", "Giocatore A")))
        self.player_b_input.setText(str(state.get("player_b", "Giocatore B")))
        self.rank_a_input.setText(str(state.get("rank_a", "")))
        self.rank_b_input.setText(str(state.get("rank_b", "")))
        self.flag_a_code_input.setText(str(state.get("flag_a_code", "IT")))
        self.flag_b_code_input.setText(str(state.get("flag_b_code", "ES")))
        self.on_flag_codes_changed()
        self.round_input.setText(str(state.get("round_name", "Round of 32")))
        self.best_of.setCurrentIndex(int(state.get("best_of_index", 0)))
        self.deciding_set_mode.setCurrentIndex(int(state.get("deciding_set_mode_index", 0)))
        saved_server_idx = int(state.get("server_index", 0))
        self._set_server_combo("A" if saved_server_idx == 0 else "B")
        # Keep dropdown aligned with current server shown in overlay.
        self._set_server_combo(self.current_server)
        self.overlay_corner_combo.setCurrentText(str(state.get("overlay_corner", "Top Left")))
        self._set_scale_combo_from_factor(float(state.get("overlay_scale", 1.0)))
        self.include_overlay.setChecked(bool(state.get("include_overlay", True)))
        self.preview_by_timeline.setChecked(bool(state.get("preview_by_timeline", True)))
        self.enable_intro_checkbox.setChecked(bool(state.get("enable_intro", False)))
        self.enable_outro_checkbox.setChecked(bool(state.get("enable_outro", False)))
        self.use_intro_bg_for_outro.setChecked(bool(state.get("use_intro_bg_for_outro", False)))
        self.intro_duration_input.setText(str(state.get("intro_duration", "5")))
        self.outro_duration_input.setText(str(state.get("outro_duration", "5")))
        intro_path = state.get("intro_bg_path")
        outro_path = state.get("outro_bg_path")
        self.intro_bg_path = intro_path if isinstance(intro_path, str) and os.path.exists(intro_path) else None
        self.outro_bg_path = outro_path if isinstance(outro_path, str) and os.path.exists(outro_path) else None
        intro_ref = state.get("intro_frame_ref")
        outro_ref = state.get("outro_frame_ref")
        self.intro_frame_ref = intro_ref if isinstance(intro_ref, dict) else None
        self.outro_frame_ref = outro_ref if isinstance(outro_ref, dict) else None
        self._refresh_intro_outro_labels()
        self.sets_a_input.setText(str(self.sets_a))
        self.sets_b_input.setText(str(self.sets_b))
        self.games_a_input.setText(str(self.games_a))
        self.games_b_input.setText(str(self.games_b))

        def _parse_overlay(raw: dict | None) -> OverlayState:
            ov = raw or {}
            return OverlayState(
                player_a=str(ov.get("player_a", "Giocatore A")),
                player_b=str(ov.get("player_b", "Giocatore B")),
                sets_a=int(ov.get("sets_a", 0)),
                sets_b=int(ov.get("sets_b", 0)),
                games_a=int(ov.get("games_a", 0)),
                games_b=int(ov.get("games_b", 0)),
                points_a=str(ov.get("points_a", "0")),
                points_b=str(ov.get("points_b", "0")),
                server=str(ov.get("server", "A")),
                tournament=str(ov.get("tournament", "Amateur Tennis Tour")),
                overlay_corner=str(ov.get("overlay_corner", "Top Left")),
                overlay_scale=float(ov.get("overlay_scale", 1.0)),
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

        self.points = []
        raw_points = data.get("points", [])
        if isinstance(raw_points, list) and raw_points:
            for raw_point in raw_points:
                clips: list[PointClip] = []
                for raw_clip in raw_point.get("clips", []):
                    src = raw_clip.get("source_path")
                    if not src or not os.path.exists(src):
                        continue
                    start = float(raw_clip.get("start", 0.0))
                    end = float(raw_clip.get("end", 0.0))
                    if end - start <= 0:
                        continue
                    clips.append(PointClip(start=start, end=end, source_path=src))
                if not clips:
                    continue
                raw_id = raw_point.get("id")
                try:
                    point_id = int(raw_id)
                except (TypeError, ValueError):
                    point_id = self.next_point_id
                    self.next_point_id += 1
                point = PointRecord(
                    id=point_id,
                    winner=raw_point.get("winner") if raw_point.get("winner") in ("A", "B") else None,
                    is_highlight=bool(raw_point.get("is_highlight", False)),
                    clips=clips,
                    overlay_at_start=_parse_overlay(raw_point.get("overlay_at_start")),
                    overlay_at_end=_parse_overlay(raw_point.get("overlay_at_end"))
                    if raw_point.get("overlay_at_end") is not None
                    else None,
                )
                self.points.append(point)
        else:
            # Legacy migration rule: 1 segment -> 1 point with one clip.
            raw_segments = data.get("segments", [])
            for raw_seg in raw_segments:
                src = raw_seg.get("source_path")
                if not src or not os.path.exists(src):
                    continue
                start = float(raw_seg.get("start", 0.0))
                end = float(raw_seg.get("end", 0.0))
                if end - start <= 0:
                    continue
                ov = _parse_overlay(raw_seg.get("overlay", {}))
                point = PointRecord(
                    id=self.next_point_id,
                    winner=None,
                    is_highlight=bool(raw_seg.get("is_highlight", False)),
                    clips=[PointClip(start=start, end=end, source_path=src)],
                    overlay_at_start=ov,
                    overlay_at_end=None,
                )
                self.next_point_id += 1
                self.points.append(point)

        raw_next_point_id = data.get("next_point_id", 1)
        try:
            loaded_next_point_id = int(raw_next_point_id)
        except (TypeError, ValueError):
            loaded_next_point_id = 1
        if self.points:
            inferred_next = max(point.id for point in self.points) + 1
            self.next_point_id = max(loaded_next_point_id, inferred_next)
        else:
            self.next_point_id = max(1, loaded_next_point_id)

        self.capture_state = "IDLE"
        self.open_point_id = None
        self.open_clip_start = None
        self.open_clip_source_path = None
        selected_point_id = data.get("selected_point_id")
        try:
            self.selected_point_id = int(selected_point_id) if selected_point_id is not None else None
        except (TypeError, ValueError):
            self.selected_point_id = None
        self._sync_selected_point_index_from_id()
        self._sync_selected_point_from_timeline()
        self._sync_legacy_pending_fields()
        self._rebuild_segments_from_points()
        self.undo_stack.clear()
        self.refresh_segments()
        self.update_overlay()
        self._refresh_shell_empty_states()
        self.set_status(f"Progetto caricato: {source_label}")
        self.autosave_project()

    def current_time_sec(self) -> float:
        return self.player.position() / 1000.0

    def duration_sec(self) -> float:
        return max(0.0, self.player.duration() / 1000.0)

    def clamp_time(self, sec: float) -> float:
        max_sec = self.duration_sec()
        return max(0.0, min(sec, max_sec if max_sec > 0 else sec))

    def jump(self, sec_delta: float) -> None:
        if not self.input_path:
            return
        self.player.setPosition(int(self.clamp_time(self.current_time_sec() + sec_delta) * 1000))

    def toggle_play_pause(self) -> None:
        if not self.input_path:
            return
        state = self.player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def mark_start(self) -> None:
        if not self.input_path:
            return
        if self.capture_state != "IDLE":
            self.set_status("C'e' gia' un punto in registrazione.")
            return
        now = self.current_time_sec()
        point = PointRecord(
            id=self.next_point_id,
            winner=None,
            is_highlight=False,
            clips=[],
            overlay_at_start=self._clone_overlay_state(self.current_overlay_state()),
            overlay_at_end=None,
        )
        self.next_point_id += 1
        self.points.append(point)
        self.open_point_id = point.id
        self.open_clip_start = now
        self.open_clip_source_path = self.input_path
        self.capture_state = "RECORDING"
        self.selected_point_index = len(self.points) - 1
        self.selected_point_id = point.id
        self._sync_legacy_pending_fields()
        self.update_highlight_controls()
        self._refresh_point_open_chip()
        self.set_status(f"Inizio punto marcato a {format_time(now)}.")
        self.update_overlay()
        self.autosave_project()

    def _probe_clip_duration(self, path: str) -> float | None:
        if not path:
            return None
        if path in self.clip_duration_cache:
            return self.clip_duration_cache[path]
        if self.input_path == path and self.player.duration() > 0:
            sec = self.player.duration() / 1000.0
            self.clip_duration_cache[path] = sec
            return sec
        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        candidates = [os.path.join(os.path.dirname(ffmpeg_bin), "ffprobe"), "ffprobe"]
        for ffprobe_bin in candidates:
            cmd = [
                ffprobe_bin,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path,
            ]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode != 0:
                    continue
                sec = float((res.stdout or "").strip())
                if sec > 0:
                    self.clip_duration_cache[path] = sec
                    return sec
            except Exception:  # noqa: BLE001
                continue

        # Fallback: parse "Duration: HH:MM:SS.xx" from ffmpeg stderr output.
        try:
            res = subprocess.run([ffmpeg_bin, "-i", path], capture_output=True, text=True)
            match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", res.stderr or "")
            if match:
                hrs = int(match.group(1))
                mins = int(match.group(2))
                secs = float(match.group(3))
                total = hrs * 3600 + mins * 60 + secs
                if total > 0:
                    self.clip_duration_cache[path] = total
                    return total
        except Exception:  # noqa: BLE001
            pass
        return None

    def _update_source_fps_status(self, path: str | None = None) -> None:
        if not hasattr(self, "ui_shell"):
            return
        src = path or self.input_path
        if not src:
            self.ui_shell.source_fps_label.setText("FPS: --")
            return
        fps = self.source_fps_cache.get(src)
        if fps is None:
            fps = self._probe_source_fps(src)
            if fps:
                self.source_fps_cache[src] = fps
        if fps and fps > 0:
            self.ui_shell.source_fps_label.setText(f"FPS: {fps:.2f}")
        else:
            self.ui_shell.source_fps_label.setText("FPS: --")

    def _close_open_clip(self) -> bool:
        if self.capture_state != "RECORDING":
            return False
        if not self.input_path or self.open_clip_start is None or not self.open_clip_source_path:
            return False
        point_idx = self._get_open_point_index()
        if point_idx is None:
            return False
        point = self.points[point_idx]
        start_path = self.open_clip_source_path
        end_path = self.input_path
        created = self._append_clip_interval(
            point=point,
            start_source=start_path,
            start_time=self.open_clip_start,
            end_source=end_path,
            end_time=self.current_time_sec(),
        )
        if created <= 0:
            self.set_status("Durata clip troppo corta.")
            return False
        self.open_clip_start = None
        self.open_clip_source_path = None
        self.capture_state = "PAUSED_WITHIN_POINT"
        self._sync_legacy_pending_fields()
        self._rebuild_segments_from_points()
        self.refresh_segments()
        return True

    def close_current_point(self) -> bool:
        # Compatibility entry-point used by old call sites; now it finalizes only when recording.
        if self.capture_state not in ("RECORDING", "PAUSED_WITHIN_POINT"):
            return False
        point_idx = self._get_open_point_index()
        if point_idx is None:
            return False
        if self.capture_state == "RECORDING":
            if not self._close_open_clip():
                return False
        point = self.points[point_idx]
        if len(point.clips) == 0:
            self.set_status("Impossibile chiudere un punto vuoto.")
            return False
        self.capture_state = "IDLE"
        self.open_point_id = None
        self.open_clip_start = None
        self.open_clip_source_path = None
        self._sync_legacy_pending_fields()
        self._rebuild_segments_from_points()
        self.refresh_segments()
        self.autosave_project()
        return True

    def mark_end(self) -> None:
        if not self.input_path:
            return
        if self.capture_state == "IDLE":
            self.set_status("Segna prima un inizio punto.")
            return
        if self.capture_state == "RECORDING":
            if self._close_open_clip():
                self.set_status("Clip in pausa. Premi Riprendi clip per continuare il punto.")
                self.update_overlay()
                self.autosave_project()
            return
        # PAUSED_WITHIN_POINT -> RECORDING
        point_idx = self._get_open_point_index()
        if point_idx is None:
            self.capture_state = "IDLE"
            self._sync_legacy_pending_fields()
            self.set_status("Stato punto non valido, reset a IDLE.")
            self.update_overlay()
            return
        self.open_clip_start = self.current_time_sec()
        self.open_clip_source_path = self.input_path
        self.capture_state = "RECORDING"
        self._sync_legacy_pending_fields()
        self.set_status("Clip ripresa.")
        self.update_overlay()

    def refresh_segments(self) -> None:
        self._rebuild_segments_from_points()
        self.refresh_points_list()
        self.segments_list.clear()
        if not self.points:
            self.refresh_highlights_list()
            self.update_highlight_controls()
            self.update_export_length_label()
            self._refresh_shell_empty_states()
            return
        for idx, seg in enumerate(self.segments, 1):
            point_idx = None
            point_id = None
            for p_idx, point in enumerate(self.points):
                if any(
                    clip.source_path == seg.source_path and abs(clip.start - seg.start) < 1e-6 and abs(clip.end - seg.end) < 1e-6
                    for clip in point.clips
                ):
                    point_idx = p_idx
                    point_id = point.id
                    break
            score = f"{seg.overlay.points_a}-{seg.overlay.points_b}"
            badge = "★ HIGHLIGHT" if seg.is_highlight else "CLIP"
            point_text = f"Punto #{point_id}" if point_id is not None else "Punto ?"
            row = (
                f"#{idx}  {format_time(seg.start)} - {format_time(seg.end)}\n"
                f"{badge} | {point_text} | S {seg.overlay.sets_a}-{seg.overlay.sets_b}  G {seg.overlay.games_a}-{seg.overlay.games_b}  P {score}  SRV {seg.overlay.server}\n"
                f"{os.path.basename(seg.source_path)}"
            )
            item = QListWidgetItem(row)
            item.setData(Qt.ItemDataRole.UserRole, point_idx if point_idx is not None else -1)
            item.setToolTip(f"Clip #{idx} - {os.path.basename(seg.source_path)}")
            self.segments_list.addItem(item)
        self.refresh_highlights_list()
        self.update_highlight_controls()
        self.update_export_length_label()
        self._refresh_shell_empty_states()

    def refresh_points_list(self) -> None:
        self.points_list.blockSignals(True)
        self.points_list.clear()
        ordered_points = sorted(self.points, key=lambda p: p.id)
        for idx, point in enumerate(ordered_points):
            if not point.clips:
                continue
            first_clip = point.clips[0]
            last_clip = point.clips[-1]
            ov = point.overlay_at_end or point.overlay_at_start or self.current_overlay_state()
            winner = point.winner if point.winner in ("A", "B") else "?"
            hl = "★" if point.is_highlight else ""
            row = (
                f"Punto #{point.id} {hl}  ({winner})  {format_time(first_clip.start)} - {format_time(last_clip.end)}\n"
                f"S {ov.sets_a}-{ov.sets_b}  G {ov.games_a}-{ov.games_b}  P {ov.points_a}-{ov.points_b}\n"
                f"{os.path.basename(first_clip.source_path)}"
            )
            item = QListWidgetItem(row)
            item.setData(Qt.ItemDataRole.UserRole, point.id)
            self.points_list.addItem(item)
        self.points_list.blockSignals(False)
        self._sync_points_list_selection()

    def refresh_highlights_list(self) -> None:
        self.highlights_list.clear()
        for idx, point in enumerate(self.points):
            if not point.is_highlight:
                continue
            if not point.clips:
                continue
            first_clip = point.clips[0]
            last_clip = point.clips[-1]
            ov = point.overlay_at_start or point.overlay_at_end or self.current_overlay_state()
            row = (
                f"★ Punto #{point.id}  {format_time(first_clip.start)} - {format_time(last_clip.end)}\n"
                f"S {ov.sets_a}-{ov.sets_b}  G {ov.games_a}-{ov.games_b}  "
                f"P {ov.points_a}-{ov.points_b}\n"
                f"{os.path.basename(first_clip.source_path)}"
            )
            item = QListWidgetItem(row)
            item.setData(Qt.ItemDataRole.UserRole, point.id)
            item.setToolTip(f"Highlight punto #{point.id}")
            self.highlights_list.addItem(item)
        self._refresh_shell_empty_states()

    def on_segment_row_changed(self, _row: int) -> None:
        item = self.segments_list.currentItem()
        if item is None:
            self.update_highlight_controls()
            return
        point_idx = item.data(Qt.ItemDataRole.UserRole)
        if point_idx is None:
            self.update_highlight_controls()
            return
        try:
            idx = int(point_idx)
        except (TypeError, ValueError):
            self.update_highlight_controls()
            return
        if idx < 0 or idx >= len(self.points):
            self.update_highlight_controls()
            return
        self.selected_point_index = idx
        self.selected_point_id = self.points[idx].id
        self.update_highlight_controls()

    def on_points_list_row_changed(self, _row: int) -> None:
        item = self.points_list.currentItem()
        if item is None:
            self.update_highlight_controls()
            return
        point_id = item.data(Qt.ItemDataRole.UserRole)
        if point_id is None:
            self.update_highlight_controls()
            return
        try:
            point_id_i = int(point_id)
        except (TypeError, ValueError):
            self.update_highlight_controls()
            return
        point_idx = next((idx for idx, point in enumerate(self.points) if point.id == point_id_i), None)
        if point_idx is None:
            self.update_highlight_controls()
            return
        point = self.points[point_idx]
        if not point.clips:
            self.update_highlight_controls()
            return
        first_clip = point.clips[0]
        self.selected_point_index = point_idx
        self.selected_point_id = point.id
        self.player.pause()
        if first_clip.source_path != self.input_path:
            target_idx = self.active_clip_combo.findData(first_clip.source_path)
            if target_idx >= 0:
                self.active_clip_combo.setCurrentIndex(target_idx)
        self.player.setPosition(int(max(0.0, first_clip.start) * 1000))
        self.update_highlight_controls()

    def on_highlight_row_changed(self, _row: int) -> None:
        item = self.highlights_list.currentItem()
        if item is None:
            self.update_highlight_controls()
            return
        point_id = item.data(Qt.ItemDataRole.UserRole)
        if point_id is None:
            self.update_highlight_controls()
            return
        try:
            point_id_i = int(point_id)
        except (TypeError, ValueError):
            self.update_highlight_controls()
            return
        for idx, point in enumerate(self.points):
            if point.id == point_id_i:
                self.selected_point_index = idx
                self.selected_point_id = point.id
                break
        self.update_highlight_controls()

    def update_highlight_controls(self) -> None:
        self._sync_selected_point_index_from_id()
        selected_point = (
            self.points[self.selected_point_index]
            if self.selected_point_index is not None and 0 <= self.selected_point_index < len(self.points)
            else None
        )
        can_toggle = self.capture_state == "IDLE" and selected_point is not None
        if selected_point is not None and selected_point.is_highlight:
            self.add_last_highlight_btn.setText("Rimuovi dagli highlights")
        else:
            self.add_last_highlight_btn.setText("Aggiungi agli highlights")
        self.add_last_highlight_btn.setEnabled(can_toggle)
        self.export_highlights_btn.setEnabled(any(point.is_highlight for point in self.points))
        self.remove_highlight_btn.setEnabled(self.highlights_list.currentRow() >= 0)
        can_remove_last = (
            selected_point is not None
            and self.capture_state == "IDLE"
            and len(self.points) > 0
            and self.points[-1].id == selected_point.id
        )
        self.remove_point_btn.setEnabled(can_remove_last)
        self.export_selected_point_btn.setEnabled(selected_point is not None and self.capture_state == "IDLE")

    def add_last_point_to_highlights(self) -> None:
        if self.capture_state != "IDLE":
            self.set_status("Chiudi prima il punto corrente.")
            return
        self._sync_selected_point_index_from_id()
        if self.selected_point_index is None or self.selected_point_index >= len(self.points):
            self.set_status("Seleziona un punto per gestire gli highlights.")
            return
        point = self.points[self.selected_point_index]
        point.is_highlight = not point.is_highlight
        self.refresh_segments()
        if point.is_highlight:
            self.set_status(f"Punto #{point.id} aggiunto agli highlights.")
        else:
            self.set_status(f"Punto #{point.id} rimosso dagli highlights.")
        self.autosave_project()

    def remove_selected_highlight(self) -> None:
        item = self.highlights_list.currentItem()
        if item is None:
            return
        point_id = item.data(Qt.ItemDataRole.UserRole)
        if point_id is None:
            return
        target = next((p for p in self.points if p.id == int(point_id)), None)
        if target is None:
            return
        target.is_highlight = False
        self.refresh_segments()
        self.set_status(f"Highlight rimosso dal punto #{target.id}.")
        self.autosave_project()

    def clear_segments(self) -> None:
        self.capture_state = "IDLE"
        self.open_point_id = None
        self.open_clip_start = None
        self.open_clip_source_path = None
        self._sync_legacy_pending_fields()
        self.points.clear()
        self.selected_point_index = None
        self.selected_point_id = None
        self.next_point_id = 1
        self.segments.clear()
        self.refresh_segments()
        self.set_status("Lista punti svuotata.")
        self.autosave_project()

    def push_undo_state(self) -> None:
        # Legacy stack retained for backward compatibility with older call sites.
        # The new workflow uses undo only to cancel the currently open point.
        snapshot = {
            "pending_point_start": self.pending_point_start,
            "pending_point_source_path": self.pending_point_source_path,
            "segments": [
                Segment(
                    start=s.start,
                    end=s.end,
                    source_path=s.source_path,
                    overlay=OverlayState(
                        player_a=s.overlay.player_a,
                        player_b=s.overlay.player_b,
                        sets_a=s.overlay.sets_a,
                        sets_b=s.overlay.sets_b,
                        games_a=s.overlay.games_a,
                        games_b=s.overlay.games_b,
                        points_a=s.overlay.points_a,
                        points_b=s.overlay.points_b,
                        server=s.overlay.server,
                        tournament=s.overlay.tournament,
                        overlay_corner=s.overlay.overlay_corner,
                        overlay_scale=s.overlay.overlay_scale,
                        set_col1_a=s.overlay.set_col1_a,
                        set_col1_b=s.overlay.set_col1_b,
                        set_col2_a=s.overlay.set_col2_a,
                        set_col2_b=s.overlay.set_col2_b,
                        alert_banner=s.overlay.alert_banner,
                        flag_a_code=s.overlay.flag_a_code,
                        flag_b_code=s.overlay.flag_b_code,
                        flag_a_path=s.overlay.flag_a_path,
                        flag_b_path=s.overlay.flag_b_path,
                    ),
                    is_highlight=s.is_highlight,
                )
                for s in self.segments
            ],
            "points_a": self.points_a,
            "points_b": self.points_b,
            "games_a": self.games_a,
            "games_b": self.games_b,
            "sets_a": self.sets_a,
            "sets_b": self.sets_b,
            "completed_sets": list(self.completed_sets),
            "completed_set_tb_loser_points": list(self.completed_set_tb_loser_points),
            "tb_points_a": self.tb_points_a,
            "tb_points_b": self.tb_points_b,
            "in_tiebreak": self.in_tiebreak,
            "tiebreak_target": self.tiebreak_target,
            "tiebreak_super": self.tiebreak_super,
            "starting_server": self.starting_server,
            "current_server": self.current_server,
            "tiebreak_first_server": self.tiebreak_first_server,
        }
        self.undo_stack.append(snapshot)
        if len(self.undo_stack) > 100:
            self.undo_stack.pop(0)

    def undo_last_action(self) -> None:
        if self.capture_state == "IDLE":
            self.set_status("Nessun punto in corso da annullare.")
            return
        open_idx = self._get_open_point_index()
        if open_idx is not None:
            del self.points[open_idx]
        self.capture_state = "IDLE"
        self.open_point_id = None
        self.open_clip_start = None
        self.open_clip_source_path = None
        self._sync_legacy_pending_fields()
        self._sync_selected_point_from_timeline()
        self._rebuild_segments_from_points()
        self.refresh_segments()
        self.update_overlay()
        self.set_status("Registrazione punto annullata. Stato IDLE.")
        self.autosave_project()

    def remove_last_point(self) -> None:
        if not self.points:
            self.set_status("Nessun punto da rimuovere.")
            return
        self._sync_selected_point_index_from_id()
        if self.selected_point_index is None:
            self.set_status("Seleziona il punto da rimuovere.")
            return
        if self.selected_point_index != len(self.points) - 1:
            self.set_status("E' possibile rimuovere solo l'ultimo punto.")
            return
        removed = self.points.pop()
        self.capture_state = "IDLE"
        self.open_point_id = None
        self.open_clip_start = None
        self.open_clip_source_path = None
        if self.points:
            self.selected_point_index = len(self.points) - 1
            self.selected_point_id = self.points[-1].id
        else:
            self.selected_point_index = None
            self.selected_point_id = None
        self._sync_legacy_pending_fields()
        self._replay_score_from_points()
        self._rebuild_segments_from_points()
        self.refresh_segments()
        self.update_overlay()
        self.set_status(f"Punto #{removed.id} rimosso.")
        self.autosave_project()

    def _start_tiebreak(self, target: int, super_mode: bool) -> None:
        self.in_tiebreak = True
        self.tiebreak_target = target
        self.tiebreak_super = super_mode
        # The tie-break starts with the player who would serve the next game.
        self.tiebreak_first_server = self.current_server
        self.points_a = 0
        self.points_b = 0
        self.tb_points_a = 0
        self.tb_points_b = 0

    def _award_set_from_tiebreak(self, side: str) -> None:
        if self.tiebreak_super:
            final_games = (self.tb_points_a, self.tb_points_b)
            self.completed_set_tb_loser_points.append(None)
        else:
            final_games = (7, 6) if side == "A" else (6, 7)
            loser_tb = self.tb_points_b if side == "A" else self.tb_points_a
            self.completed_set_tb_loser_points.append(loser_tb)
        self.completed_sets.append(final_games)
        if side == "A":
            self.sets_a += 1
        else:
            self.sets_b += 1
        self.games_a = 0
        self.games_b = 0
        self.points_a = 0
        self.points_b = 0
        self.tb_points_a = 0
        self.tb_points_b = 0
        self.in_tiebreak = False
        self.tiebreak_super = False
        self.tiebreak_target = 7
        # Next set starts serving the player who did NOT start the tie-break.
        if self.tiebreak_first_server in ("A", "B"):
            self.current_server = self._opponent(self.tiebreak_first_server)
        self.tiebreak_first_server = None
        self._set_server_combo(self.current_server)
        self.sets_a_input.setText(str(self.sets_a))
        self.sets_b_input.setText(str(self.sets_b))
        self.games_a_input.setText(str(self.games_a))
        self.games_b_input.setText(str(self.games_b))

    def _award_game(self, side: str) -> None:
        if side == "A":
            self.games_a += 1
        else:
            self.games_b += 1
        self.points_a = 0
        self.points_b = 0
        # Service alternates every game.
        self.current_server = self._opponent(self.current_server)
        self._set_server_combo(self.current_server)

        # Tie-break standard sul 6-6.
        if self.games_a == 6 and self.games_b == 6:
            self._start_tiebreak(7, False)
            self.games_a_input.setText(str(self.games_a))
            self.games_b_input.setText(str(self.games_b))
            return

        set_ended = False
        if self.games_a >= 6 and self.games_a - self.games_b >= 2:
            self.completed_sets.append((self.games_a, self.games_b))
            self.completed_set_tb_loser_points.append(None)
            self.sets_a += 1
            self.games_a = 0
            self.games_b = 0
            set_ended = True
        elif self.games_b >= 6 and self.games_b - self.games_a >= 2:
            self.completed_sets.append((self.games_a, self.games_b))
            self.completed_set_tb_loser_points.append(None)
            self.sets_b += 1
            self.games_a = 0
            self.games_b = 0
            set_ended = True

        # Super tie-break al posto del terzo set (solo Best of 3) all'inizio del set decisivo.
        if (
            set_ended
            and self.best_of.currentIndex() == 0
            and self.deciding_set_mode.currentIndex() == 1
            and self.sets_a == 1
            and self.sets_b == 1
        ):
            self._start_tiebreak(10, True)

        self.sets_a_input.setText(str(self.sets_a))
        self.sets_b_input.setText(str(self.sets_b))
        self.games_a_input.setText(str(self.games_a))
        self.games_b_input.setText(str(self.games_b))

    def _apply_point_winner_to_score(self, side: str) -> None:
        if self.in_tiebreak:
            if side == "A":
                self.tb_points_a += 1
            else:
                self.tb_points_b += 1

            a_tb, b_tb = self.tb_points_a, self.tb_points_b
            total_tb_points = a_tb + b_tb
            if a_tb >= self.tiebreak_target and a_tb - b_tb >= 2:
                self._award_set_from_tiebreak("A")
            elif b_tb >= self.tiebreak_target and b_tb - a_tb >= 2:
                self._award_set_from_tiebreak("B")
            else:
                # In tie-break: first server serves 1 point, then service changes every 2 points.
                if total_tb_points % 2 == 1:
                    self.current_server = self._opponent(self.current_server)
                    self._set_server_combo(self.current_server)
            return

        if side == "A":
            a, b = self.points_a, self.points_b
            if a <= 2:
                self.points_a += 1
            elif a == 3 and b <= 2:
                self._award_game("A")
            elif a == 3 and b == 3:
                self.points_a = 4
            elif a == 4:
                self._award_game("A")
            elif b == 4:
                self.points_b = 3
            return

        a, b = self.points_a, self.points_b
        if b <= 2:
            self.points_b += 1
        elif b == 3 and a <= 2:
            self._award_game("B")
        elif b == 3 and a == 3:
            self.points_b = 4
        elif b == 4:
            self._award_game("B")
        elif a == 4:
            self.points_a = 3

    def tennis_point_winner(self, side: str) -> None:
        if not self.input_path:
            return
        if self.capture_state not in ("RECORDING", "PAUSED_WITHIN_POINT"):
            self.set_status("Avvia prima un punto con Inizio punto.")
            return
        point_idx = self._get_open_point_index()
        if point_idx is None:
            self.capture_state = "IDLE"
            self._sync_legacy_pending_fields()
            self.set_status("Stato punto non valido, reset a IDLE.")
            self.update_overlay()
            return
        if self.capture_state == "RECORDING":
            if not self._close_open_clip():
                return
            # _close_open_clip porta lo stato in PAUSED_WITHIN_POINT
            point_idx = self._get_open_point_index()
            if point_idx is None:
                self.set_status("Errore interno nel completamento del punto.")
                return
        point = self.points[point_idx]
        if len(point.clips) == 0:
            self.set_status("Impossibile assegnare il punto: nessuna clip valida registrata.")
            return
        point.winner = side
        self._apply_point_winner_to_score(side)
        point.overlay_at_end = self._clone_overlay_state(self.current_overlay_state())
        self.capture_state = "IDLE"
        self.open_point_id = None
        self.open_clip_start = None
        self.open_clip_source_path = None
        self.selected_point_index = point_idx
        self.selected_point_id = point.id
        self._sync_legacy_pending_fields()
        self._rebuild_segments_from_points()
        self.refresh_segments()
        self.update_overlay()
        self.set_status(f"Punto #{point.id} assegnato al giocatore {side}.")
        self.autosave_project()

    def reset_score(self) -> None:
        self.push_undo_state()
        self.starting_server = self._server_from_combo()
        self.current_server = self.starting_server
        self.tiebreak_first_server = None
        self.points_a = 0
        self.points_b = 0
        self.tb_points_a = 0
        self.tb_points_b = 0
        self.in_tiebreak = False
        self.tiebreak_target = 7
        self.tiebreak_super = False
        self.completed_sets = []
        self.completed_set_tb_loser_points = []
        self.games_a = self._int_or_default(self.games_a_input.text(), 0)
        self.games_b = self._int_or_default(self.games_b_input.text(), 0)
        self.sets_a = self._int_or_default(self.sets_a_input.text(), 0)
        self.sets_b = self._int_or_default(self.sets_b_input.text(), 0)
        self.update_overlay()
        self.autosave_project()

    def apply_server_to_all_segments(self) -> None:
        if not self.points:
            self.set_status("Nessun punto disponibile.")
            return
        server = self.current_server
        if not self._show_themed_question(
            "Conferma modifica servitore",
            (
                f"Vuoi applicare il servitore {server} a tutti i segmenti esistenti? "
                "L'operazione e' annullabile con Undo."
            ),
            "Applica",
            "Annulla",
        ):
            return
        for point in self.points:
            if point.overlay_at_start is not None:
                point.overlay_at_start.server = server
            if point.overlay_at_end is not None:
                point.overlay_at_end.server = server
        self._rebuild_segments_from_points()
        self.refresh_segments()
        self.update_overlay()
        self.set_status(f"Servitore {server} applicato a {len(self.points)} punti.")
        self.autosave_project()

    def _build_export_segments(self, source_segments: list[Segment]) -> list[Segment]:
        export_corner = self.overlay_corner_combo.currentText()
        export_scale = self.overlay_widget.scale_factor
        export_segments: list[Segment] = []
        for seg in source_segments:
            export_segments.append(
                Segment(
                    start=seg.start,
                    end=seg.end,
                    source_path=seg.source_path,
                    overlay=OverlayState(
                        player_a=seg.overlay.player_a,
                        player_b=seg.overlay.player_b,
                        sets_a=seg.overlay.sets_a,
                        sets_b=seg.overlay.sets_b,
                        games_a=seg.overlay.games_a,
                        games_b=seg.overlay.games_b,
                        points_a=seg.overlay.points_a,
                        points_b=seg.overlay.points_b,
                        server=seg.overlay.server,
                        tournament=seg.overlay.tournament,
                        overlay_corner=export_corner,
                        overlay_scale=export_scale,
                        set_col1_a=seg.overlay.set_col1_a,
                        set_col1_b=seg.overlay.set_col1_b,
                        set_col2_a=seg.overlay.set_col2_a,
                        set_col2_b=seg.overlay.set_col2_b,
                        alert_banner=seg.overlay.alert_banner,
                        flag_a_code=seg.overlay.flag_a_code,
                        flag_b_code=seg.overlay.flag_b_code,
                        flag_a_path=seg.overlay.flag_a_path,
                        flag_b_path=seg.overlay.flag_b_path,
                    ),
                    is_highlight=seg.is_highlight,
                )
            )
        return export_segments

    def _start_export_job(self, output_path: str, source_segments: list[Segment], export_kind: str) -> None:
        self.current_export_kind = export_kind
        for frame_path in list(self._ephemeral_export_frames):
            try:
                if os.path.exists(frame_path):
                    os.remove(frame_path)
            except OSError:
                pass
        self._ephemeral_export_frames.clear()
        self.export_btn.setEnabled(False)
        self.export_highlights_btn.setEnabled(False)
        self.export_selected_point_btn.setEnabled(False)
        self.set_status(f"Export {export_kind} in corso...")
        if self.export_progress_dialog is not None:
            self.export_progress_dialog.close()
            self.export_progress_dialog = None
        self.export_progress_dialog = ExportProgressDialog(self)
        self.export_progress_dialog.finished.connect(self._on_export_dialog_closed)
        self.export_progress_dialog.set_mode(export_kind, output_path)
        self.export_progress_dialog.set_progress(0, 0.0, 0.0, "Preparazione export...")
        self.export_progress_dialog.show()
        export_segments = self._build_export_segments(source_segments)
        intro_cfg = None
        outro_cfg = None
        if export_kind in {"condensato", "highlights", "punto"}:
            intro_cfg = self._intro_config()
            if self.enable_intro_checkbox.isChecked() and intro_cfg is None:
                self.export_btn.setEnabled(True)
                self.update_highlight_controls()
                if self.export_progress_dialog is not None:
                    self.export_progress_dialog.close()
                    self.export_progress_dialog = None
                return
            outro_cfg = self._outro_config()
            if self.enable_outro_checkbox.isChecked() and outro_cfg is None:
                self.export_btn.setEnabled(True)
                self.update_highlight_controls()
                if self.export_progress_dialog is not None:
                    self.export_progress_dialog.close()
                    self.export_progress_dialog = None
                return
        self.export_worker = ExportWorker(
            output_path=output_path,
            segments=export_segments,
            include_overlay=self.include_overlay.isChecked(),
            intro_clip=intro_cfg,
            outro_clip=outro_cfg,
        )
        self.export_worker.progress.connect(self.on_export_progress)
        self.export_worker.finished_ok.connect(self.on_export_ok)
        self.export_worker.failed.connect(self.on_export_failed)
        self.export_worker.start()

    def _on_export_dialog_closed(self) -> None:
        self.export_progress_dialog = None

    def export_condensed(self) -> None:
        if not self.input_path:
            QMessageBox.warning(self, "Errore", "Carica un video prima di esportare.")
            return
        self._rebuild_segments_from_points()
        if not self.segments:
            QMessageBox.warning(self, "Errore", "Nessun punto selezionato.")
            return

        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Salva video condensato",
            os.path.splitext(os.path.basename(self.input_path))[0] + "_condensato.mp4",
            "MP4 (*.mp4)",
        )
        if not output_path:
            return
        if not output_path.lower().endswith(".mp4"):
            output_path += ".mp4"
        self._start_export_job(output_path, self.segments, "condensato")

    def export_highlights(self) -> None:
        if not self.input_path:
            QMessageBox.warning(self, "Errore", "Carica un video prima di esportare.")
            return
        self._rebuild_segments_from_points()
        highlight_segments = [seg for seg in self.segments if seg.is_highlight]
        if not highlight_segments:
            QMessageBox.warning(self, "Errore", "Nessun highlight selezionato.")
            return
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Salva video highlights",
            os.path.splitext(os.path.basename(self.input_path))[0] + "_highlights.mp4",
            "MP4 (*.mp4)",
        )
        if not output_path:
            return
        if not output_path.lower().endswith(".mp4"):
            output_path += ".mp4"
        self._start_export_job(output_path, highlight_segments, "highlights")

    def export_selected_point(self) -> None:
        if not self.input_path:
            QMessageBox.warning(self, "Errore", "Carica un video prima di esportare.")
            return
        self._sync_selected_point_index_from_id()
        if self.selected_point_index is None or self.selected_point_index >= len(self.points):
            QMessageBox.warning(self, "Errore", "Seleziona un punto da esportare.")
            return
        point = self.points[self.selected_point_index]
        if not point.clips:
            QMessageBox.warning(self, "Errore", "Il punto selezionato non contiene clip valide.")
            return
        self._rebuild_segments_from_points()
        selected_segments = [
            seg
            for seg in self._flatten_points_to_segments()
            if any(
                clip.source_path == seg.source_path and abs(clip.start - seg.start) < 1e-6 and abs(clip.end - seg.end) < 1e-6
                for clip in point.clips
            )
        ]
        if not selected_segments:
            QMessageBox.warning(self, "Errore", "Nessun segmento valido per il punto selezionato.")
            return
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Salva punto selezionato",
            os.path.splitext(os.path.basename(self.input_path))[0] + f"_punto_{point.id}.mp4",
            "MP4 (*.mp4)",
        )
        if not output_path:
            return
        if not output_path.lower().endswith(".mp4"):
            output_path += ".mp4"
        self._start_export_job(output_path, selected_segments, "punto")

    def on_export_progress(self, percent: int, elapsed_sec: float, eta_sec: float, status: str) -> None:
        if self.export_progress_dialog is not None:
            self.export_progress_dialog.set_progress(percent, elapsed_sec, eta_sec, status)

    def on_export_ok(self, output_path: str, chunks: int) -> None:
        for frame_path in list(self._ephemeral_export_frames):
            try:
                if os.path.exists(frame_path):
                    os.remove(frame_path)
            except OSError:
                pass
        self._ephemeral_export_frames.clear()
        self.export_btn.setEnabled(True)
        self.update_highlight_controls()
        if self.export_progress_dialog is not None:
            self.export_progress_dialog.set_success(self.current_export_kind, output_path, chunks)
        self.set_status(f"Export {self.current_export_kind} completato: {output_path} ({chunks} clip).")

    def on_export_failed(self, message: str) -> None:
        for frame_path in list(self._ephemeral_export_frames):
            try:
                if os.path.exists(frame_path):
                    os.remove(frame_path)
            except OSError:
                pass
        self._ephemeral_export_frames.clear()
        self.export_btn.setEnabled(True)
        self.update_highlight_controls()
        if self.export_progress_dialog is not None:
            self.export_progress_dialog.set_error(self.current_export_kind, message)
        self.set_status(f"Export {self.current_export_kind} fallito: {message}")

    def clear_edit_focus(self) -> None:
        for field in [
            self.tournament_input,
            self.player_a_input,
            self.player_b_input,
            self.rank_a_input,
            self.rank_b_input,
            self.flag_a_code_input,
            self.flag_b_code_input,
            self.round_input,
            self.intro_duration_input,
            self.outro_duration_input,
            self.sets_a_input,
            self.sets_b_input,
            self.games_a_input,
            self.games_b_input,
        ]:
            field.deselect()
            field.clearFocus()
        self.video_container.setFocus(Qt.FocusReason.OtherFocusReason)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.autosave_project()
        try:
            self.session_temp_dir.cleanup()
        except Exception:  # noqa: BLE001
            pass
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
