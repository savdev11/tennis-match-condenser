import os
import re
import subprocess
import sys
import tempfile
import json
import time
from dataclasses import asdict, dataclass

import imageio_ffmpeg
from PySide6.QtCore import QThread, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QKeySequence, QShortcut, QFont, QPixmap
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
    QPushButton,
    QScrollArea,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QKeySequenceEdit,
)

APP_VERSION = "1.5"


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


@dataclass
class Segment:
    start: float
    end: float
    source_path: str
    overlay: OverlayState
    is_highlight: bool = False


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


def detect_fontfile() -> str:
    candidates = [
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


def build_overlay_filter(ov: OverlayState) -> str:
    scale = max(0.7, min(ov.overlay_scale, 2.0))
    t_font = int(17 * scale)
    name_font = int(24 * scale)
    num_font = int(27 * scale)
    banner_font = int(15 * scale)
    line_thick = max(1, int(2 * scale))
    header_h = int(28 * scale)
    row_h = int(42 * scale)
    table_top = int(34 * scale)
    col_name_w = int(328 * scale)
    col_w = int(74 * scale)
    # Keep overlay canvas larger than internal grid at all scales.
    table_w = col_name_w + col_w * 3
    box_w = max(int(560 * scale), table_w + int(20 * scale))
    box_h = table_top + header_h + row_h * 2 + int(10 * scale)

    if ov.overlay_corner == "Top Right":
        base_x = f"iw-{box_w}-20"  # drawbox expression
        base_y = "20"  # drawbox expression
        text_base_x = f"w-{box_w}-20"  # drawtext expression
        text_base_y = "20"  # drawtext expression
    elif ov.overlay_corner == "Bottom Left":
        base_x = "20"
        base_y = f"ih-{box_h}-20"
        text_base_x = "20"
        text_base_y = f"h-{box_h}-20"
    elif ov.overlay_corner == "Bottom Right":
        base_x = f"iw-{box_w}-20"
        base_y = f"ih-{box_h}-20"
        text_base_x = f"w-{box_w}-20"
        text_base_y = f"h-{box_h}-20"
    else:
        base_x = "20"
        base_y = "20"
        text_base_x = "20"
        text_base_y = "20"

    title = ffmpeg_escape_text(ov.tournament.upper())
    name_a = ffmpeg_escape_text((ov.player_a or "Giocatore A")[:14])
    name_b = ffmpeg_escape_text((ov.player_b or "Giocatore B")[:14])
    set1_a = ffmpeg_escape_text(str(ov.set_col1_a))
    set1_b = ffmpeg_escape_text(str(ov.set_col1_b))
    set2_a = ffmpeg_escape_text(str(ov.set_col2_a))
    set2_b = ffmpeg_escape_text(str(ov.set_col2_b))
    pts_a = ffmpeg_escape_text(str(ov.points_a))
    pts_b = ffmpeg_escape_text(str(ov.points_b))
    banner = ffmpeg_escape_text(ov.alert_banner)
    # Parenthesize base expressions to keep ffmpeg parser happy when using arithmetic.
    bx = f"({text_base_x})"
    by = f"({text_base_y})"
    bbx = f"({base_x})"
    bby = f"({base_y})"
    table_x0 = f"{bbx}+10"
    table_x1 = f"{bbx}+{10 + col_name_w}"
    table_x2 = f"{bbx}+{10 + col_name_w + col_w}"
    table_x3 = f"{bbx}+{10 + col_name_w + col_w * 2}"
    table_x4 = f"{bbx}+{10 + col_name_w + col_w * 3}"
    table_text_x1 = f"{bx}+{10 + col_name_w}"
    table_text_x2 = f"{bx}+{10 + col_name_w + col_w}"
    table_text_x3 = f"{bx}+{10 + col_name_w + col_w * 2}"
    table_y0 = f"{bby}+{table_top}"
    table_y1 = f"{bby}+{table_top + header_h}"
    table_y2 = f"{bby}+{table_top + header_h + row_h}"
    table_y3 = f"{bby}+{table_top + header_h + row_h * 2}"
    header_y = f"{by}+{table_top + int(5 * scale)}"
    row_a_y = f"{by}+{table_top + header_h + int(8 * scale)}"
    row_b_y = f"{by}+{table_top + header_h + row_h + int(8 * scale)}"
    name_x = f"{bx}+{int(20 * scale)}"
    set1_x = f"{table_text_x1}+{int(24 * scale)}"
    set2_x = f"{table_text_x2}+{int(24 * scale)}"
    pts_x = f"{table_text_x3}+{int(18 * scale)}"
    filters = [
        f"drawbox=x={base_x}:y={base_y}:w={box_w}:h={box_h}:color=#10263acc:t=fill",
        f"drawbox=x={base_x}:y={base_y}:w={box_w}:h={box_h}:color=#ffffff66:t=2",
        f"drawtext=text='{title}':x={bx}+12:y={by}+8:fontcolor=#b7e0ff:fontsize={t_font}{FONT_OPT}",
        f"drawbox=x={table_x0}:y={table_y0}:w={col_name_w + col_w * 3}:h={line_thick}:color=#ffffff88:t=fill",
        f"drawbox=x={table_x0}:y={table_y1}:w={col_name_w + col_w * 3}:h={line_thick}:color=#ffffff66:t=fill",
        f"drawbox=x={table_x0}:y={table_y2}:w={col_name_w + col_w * 3}:h={line_thick}:color=#ffffff66:t=fill",
        f"drawbox=x={table_x0}:y={table_y3}:w={col_name_w + col_w * 3}:h={line_thick}:color=#ffffff88:t=fill",
        f"drawbox=x={table_x0}:y={table_y0}:w={line_thick}:h={header_h + row_h * 2}:color=#ffffff88:t=fill",
        f"drawbox=x={table_x1}:y={table_y0}:w={line_thick}:h={header_h + row_h * 2}:color=#ffffff66:t=fill",
        f"drawbox=x={table_x2}:y={table_y0}:w={line_thick}:h={header_h + row_h * 2}:color=#ffffff66:t=fill",
        f"drawbox=x={table_x3}:y={table_y0}:w={line_thick}:h={header_h + row_h * 2}:color=#ffffff66:t=fill",
        f"drawbox=x={table_x4}:y={table_y0}:w={line_thick}:h={header_h + row_h * 2}:color=#ffffff88:t=fill",
        f"drawtext=text='SET 1':x={table_text_x1}+{int(8 * scale)}:y={header_y}:fontcolor=#9fd2ff:fontsize={int(15 * scale)}{FONT_OPT}",
        f"drawtext=text='SET 2':x={table_text_x2}+{int(8 * scale)}:y={header_y}:fontcolor=#9fd2ff:fontsize={int(15 * scale)}{FONT_OPT}",
        f"drawtext=text='PTS':x={table_text_x3}+{int(15 * scale)}:y={header_y}:fontcolor=#9fd2ff:fontsize={int(15 * scale)}{FONT_OPT}",
        f"drawtext=text='{name_a}':x={name_x}:y={row_a_y}:fontcolor=white:fontsize={name_font}{FONT_OPT}",
        f"drawtext=text='{name_b}':x={name_x}:y={row_b_y}:fontcolor=white:fontsize={name_font}{FONT_OPT}",
        f"drawtext=text='{set1_a}':x={set1_x}:y={row_a_y}:fontcolor=white:fontsize={num_font}{FONT_OPT}",
        f"drawtext=text='{set1_b}':x={set1_x}:y={row_b_y}:fontcolor=white:fontsize={num_font}{FONT_OPT}",
        f"drawtext=text='{set2_a}':x={set2_x}:y={row_a_y}:fontcolor=white:fontsize={num_font}{FONT_OPT}",
        f"drawtext=text='{set2_b}':x={set2_x}:y={row_b_y}:fontcolor=white:fontsize={num_font}{FONT_OPT}",
        f"drawtext=text='{pts_a}':x={pts_x}:y={row_a_y}:fontcolor=white:fontsize={num_font}{FONT_OPT}",
        f"drawtext=text='{pts_b}':x={pts_x}:y={row_b_y}:fontcolor=white:fontsize={num_font}{FONT_OPT}",
    ]

    # Serve indicator: yellow left border on server row.
    serve_x = f"{table_x0}+{int(3 * scale)}"
    serve_w = max(4, int(6 * scale))
    serve_h = max(24, int(28 * scale))
    serve_a_y = f"{bby}+{table_top + header_h + int(7 * scale)}"
    serve_b_y = f"{bby}+{table_top + header_h + row_h + int(7 * scale)}"
    if ov.server == "A":
        filters.append(
            f"drawbox=x={serve_x}:y={serve_a_y}:w={serve_w}:h={serve_h}:color=#ffd76a:t=fill"
        )
    elif ov.server == "B":
        filters.append(
            f"drawbox=x={serve_x}:y={serve_b_y}:w={serve_w}:h={serve_h}:color=#ffd76a:t=fill"
        )
    if banner:
        banner_w = int(220 * scale)
        banner_h = int(26 * scale)
        banner_x = f"{base_x}+{int(12 * scale)}"
        banner_y = f"{base_y}+{int(2 * scale)}"
        banner_text_x = f"{bx}+{int(12 * scale)}"
        banner_text_y = f"{by}+{int(2 * scale)}"
        filters.append(
            f"drawbox=x={banner_x}:y={banner_y}:w={banner_w}:h={banner_h}:color=#ffd84a:t=fill"
        )
        filters.append(
            f"drawtext=text='{banner}':x={banner_text_x}+{int(11 * scale)}:y={banner_text_y}+{int(5 * scale)}:"
            f"fontcolor=#0b4fa6:fontsize={banner_font}{FONT_OPT}"
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
        self.root.setContentsMargins(10, 8, 10, 10)
        self.root.setSpacing(6)
        self.font_specs: dict[QLabel, tuple[int, int, str]] = {}

        self.alert_label = QLabel("")
        self.alert_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._register_label(self.alert_label, 10, 800, "#0b4fa6")
        self.alert_label.setVisible(False)
        self.root.addWidget(self.alert_label)

        self.tournament_label = QLabel("AMATEUR TENNIS TOUR")
        self._register_label(self.tournament_label, 11, 700, "#cbe4ff")
        self.root.addWidget(self.tournament_label)

        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(0)
        self.grid.setVerticalSpacing(0)
        self.root.addLayout(self.grid)

        headers = ["", "SET 1", "SET 2", "PTS"]
        for col, txt in enumerate(headers):
            cell = QLabel(txt)
            self._register_label(cell, 10, 700, "#9fd2ff")
            cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.grid.addWidget(cell, 0, col)

        self.player_a_name = QLabel("Giocatore A")
        self.player_b_name = QLabel("Giocatore B")
        self._register_label(self.player_a_name, 15, 700, "#f8fcff")
        self._register_label(self.player_b_name, 15, 700, "#f8fcff")

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
            self._register_label(label, 16, 800, "#ffffff")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.serv_bar_a = QFrame()
        self.serv_bar_b = QFrame()
        self.serv_bar_a.setFixedWidth(5)
        self.serv_bar_b.setFixedWidth(5)
        row_a = QWidget()
        row_a_layout = QHBoxLayout(row_a)
        row_a_layout.setContentsMargins(0, 2, 0, 2)
        row_a_layout.setSpacing(8)
        row_a_layout.addWidget(self.serv_bar_a)
        row_a_layout.addWidget(self.player_a_name)
        row_a_layout.addStretch()

        row_b = QWidget()
        row_b_layout = QHBoxLayout(row_b)
        row_b_layout.setContentsMargins(0, 2, 0, 2)
        row_b_layout.setSpacing(8)
        row_b_layout.addWidget(self.serv_bar_b)
        row_b_layout.addWidget(self.player_b_name)
        row_b_layout.addStretch()

        self.grid.addWidget(row_a, 1, 0)
        self.grid.addWidget(self.player_a_set1, 1, 1)
        self.grid.addWidget(self.player_a_set2, 1, 2)
        self.grid.addWidget(self.player_a_pts, 1, 3)

        self.grid.addWidget(row_b, 2, 0)
        self.grid.addWidget(self.player_b_set1, 2, 1)
        self.grid.addWidget(self.player_b_set2, 2, 2)
        self.grid.addWidget(self.player_b_pts, 2, 3)

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
        margin_h = int(10 * self.scale_factor)
        margin_v = int(8 * self.scale_factor)
        self.root.setContentsMargins(margin_h, margin_v, margin_h, int(10 * self.scale_factor))
        self.root.setSpacing(max(3, int(6 * self.scale_factor)))
        line = max(1, int(1 * self.scale_factor))
        self.grid.setHorizontalSpacing(0)
        self.grid.setVerticalSpacing(0)
        self.grid.setColumnMinimumWidth(0, int(320 * self.scale_factor))
        self.grid.setColumnMinimumWidth(1, int(72 * self.scale_factor))
        self.grid.setColumnMinimumWidth(2, int(72 * self.scale_factor))
        self.grid.setColumnMinimumWidth(3, int(72 * self.scale_factor))
        self.grid.setColumnStretch(0, 1)

        radius = int(10 * self.scale_factor)
        serv_color = "rgba(255,215,106,255)"
        self.serv_bar_a.setStyleSheet(f"background: {serv_color}; border-radius: 2px;")
        self.serv_bar_b.setStyleSheet(f"background: {serv_color}; border-radius: 2px;")
        self.serv_bar_a.setFixedWidth(max(4, int(5 * self.scale_factor)))
        self.serv_bar_b.setFixedWidth(max(4, int(5 * self.scale_factor)))
        self.alert_label.setStyleSheet(
            f"background: #ffd84a; border-radius: {int(6 * self.scale_factor)}px; padding: {max(2, int(3 * self.scale_factor))}px;"
            "color: #0b4fa6; font-weight: 800;"
        )
        self.setStyleSheet(
            f"""
            #scoreboard {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(22, 30, 48, 220),
                    stop:1 rgba(10, 86, 119, 220));
                border: 1px solid rgba(255,255,255,80);
                border-radius: {radius}px;
            }}
            #scoreboard QLabel {{
                padding: {max(2, int(4 * self.scale_factor))}px;
            }}
            """
        )
        self.grid.setContentsMargins(line, line, line, line)
        for label, (base_size, weight, color) in self.font_specs.items():
            font = QFont("Segoe UI", max(7, int(base_size * self.scale_factor)))
            font.setWeight(self._qt_font_weight(weight))
            label.setFont(font)
            label.setStyleSheet(f"color: {color};")

        self.setFixedWidth(int(540 * self.scale_factor))
        self.adjustSize()

    def apply_state(self, state: OverlayState) -> None:
        self.tournament_label.setText(state.tournament.upper())
        self.player_a_name.setText(state.player_a)
        self.player_b_name.setText(state.player_b)
        self.player_a_set1.setText(str(state.set_col1_a))
        self.player_b_set1.setText(str(state.set_col1_b))
        self.player_a_set2.setText(str(state.set_col2_a))
        self.player_b_set2.setText(str(state.set_col2_b))
        self.player_a_pts.setText(state.points_a)
        self.player_b_pts.setText(state.points_b)
        self.serv_bar_a.setVisible(state.server == "A")
        self.serv_bar_b.setVisible(state.server == "B")
        self.alert_label.setVisible(bool(state.alert_banner))
        self.alert_label.setText(state.alert_banner)


class ExportWorker(QThread):
    finished_ok = Signal(str, int)
    failed = Signal(str)
    progress = Signal(int, float, float, str)

    def __init__(self, output_path: str, segments: list[Segment], include_overlay: bool) -> None:
        super().__init__()
        self.output_path = output_path
        self.segments = segments
        self.include_overlay = include_overlay
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
                if total_tasks <= 0:
                    total_tasks = 1
                done_tasks = 0
                self.progress.emit(0, 0.0, 0.0, "Preparazione export...")
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
                        cmd += ["-vf", build_overlay_filter(segment.overlay)]

                    cmd += [
                        "-c:v",
                        "libx264",
                        "-preset",
                        "veryfast",
                        "-crf",
                        "21",
                        "-c:a",
                        "aac",
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


class ExportProgressDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export in corso")
        self.setModal(True)
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        self.status_label = QLabel("Preparazione export...")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.elapsed_label = QLabel("Tempo trascorso: 0:00")
        self.eta_label = QLabel("Tempo stimato rimanente: --:--")
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.elapsed_label)
        layout.addWidget(self.eta_label)

    def set_progress(self, percent: int, elapsed_sec: float, eta_sec: float, status: str) -> None:
        self.progress_bar.setValue(max(0, min(100, percent)))
        self.status_label.setText(status)
        self.elapsed_label.setText(f"Tempo trascorso: {format_time(elapsed_sec)}")
        if eta_sec <= 0.1:
            self.eta_label.setText("Tempo stimato rimanente: 0:00")
        else:
            self.eta_label.setText(f"Tempo stimato rimanente: {format_time(eta_sec)}")


class MainWindow(QMainWindow):
    POINT_VALUES = [0, 15, 30, 40, "AD"]

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Tennis Match Condenser v{APP_VERSION} (Python)")
        self.resize(1360, 860)

        self.input_path: str | None = None
        self.input_paths: list[str] = []
        self.pending_point_start: float | None = None
        self.pending_point_source_path: str | None = None
        self.clip_duration_cache: dict[str, float] = {}
        self.segments: list[Segment] = []
        self.undo_stack: list[dict] = []
        self.export_worker: ExportWorker | None = None
        self.export_progress_dialog: ExportProgressDialog | None = None
        self.current_export_kind = "condensato"
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
        self.play_pause_btn = QPushButton("Play/Pausa")
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
        self.overlay_scale_combo.setCurrentText("160%")
        self.active_clip_combo = QComboBox()
        self.active_clip_combo.currentIndexChanged.connect(self.on_active_clip_changed)

        self.sets_a_input = QLineEdit("0")
        self.sets_b_input = QLineEdit("0")
        self.games_a_input = QLineEdit("0")
        self.games_b_input = QLineEdit("0")

        for field in [
            self.tournament_input,
            self.player_a_input,
            self.player_b_input,
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

        self.server_combo.currentIndexChanged.connect(self.on_server_selection_changed)
        self.overlay_corner_combo.currentTextChanged.connect(self.on_overlay_corner_changed)
        self.overlay_scale_combo.currentTextChanged.connect(self.on_overlay_scale_changed)

        self.point_a_btn = QPushButton("Punto A")
        self.point_b_btn = QPushButton("Punto B")
        self.add_last_highlight_btn = QPushButton("Aggiungi ultimo punto agli highlight")
        self.add_last_highlight_btn.setEnabled(False)
        self.add_last_highlight_btn.clicked.connect(self.add_last_point_to_highlights)
        self.reset_score_btn = QPushButton("Reset score")
        self.point_a_btn.clicked.connect(lambda: self.tennis_point_winner("A"))
        self.point_b_btn.clicked.connect(lambda: self.tennis_point_winner("B"))
        self.reset_score_btn.clicked.connect(self.reset_score)
        self.include_overlay = QCheckBox("Includi overlay nell'export")
        self.include_overlay.setChecked(True)
        self.preview_by_timeline = QCheckBox("Preview scoreboard da timeline")
        self.preview_by_timeline.setChecked(True)
        self.preview_by_timeline.stateChanged.connect(self.update_overlay)

        self.segments_list = QListWidget()
        self.highlights_list = QListWidget()
        self.highlights_list.currentRowChanged.connect(lambda _row: self.update_highlight_controls())
        self.remove_highlight_btn = QPushButton("Rimuovi highlight selezionato")
        self.remove_highlight_btn.setEnabled(False)
        self.remove_highlight_btn.clicked.connect(self.remove_selected_highlight)
        self.clear_segments_btn = QPushButton("Svuota")
        self.clear_segments_btn.clicked.connect(self.clear_segments)
        self.undo_btn = QPushButton("Undo")
        self.undo_btn.clicked.connect(self.undo_last_action)
        self.export_btn = QPushButton("Esporta condensato")
        self.export_btn.clicked.connect(self.export_condensed)
        self.export_highlights_btn = QPushButton("Esporta highlights")
        self.export_highlights_btn.clicked.connect(self.export_highlights)
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
        self.reset_score()
        self.refresh_segments()
        self.video_container.clicked.connect(self.clear_edit_focus)
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(15000)
        self.autosave_timer.timeout.connect(self.autosave_project)
        self.autosave_timer.start()
        self.try_restore_autosave()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        root.setStyleSheet(
            """
            QWidget {
                font-family: "Segoe UI";
                font-size: 13px;
            }
            QFrame#panel {
                border: 1px solid #4f5661;
                border-radius: 10px;
                background: #ffffff;
            }
            QSplitter::handle {
                background: #6b7280;
                border: 1px solid #3f4651;
                border-radius: 4px;
            }
            QSplitter::handle:hover {
                background: #545b68;
            }
            QSplitter::handle:pressed {
                background: #3f4651;
            }
            """
        )

        main_layout = QVBoxLayout(root)
        top = QHBoxLayout()
        top.addWidget(QLabel("<h2>Tennis Match Condenser</h2>"))
        top.addStretch()
        top.addWidget(self.open_project_btn)
        top.addWidget(self.save_project_btn)
        top.addWidget(self.load_btn)
        main_layout.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(16)
        main_layout.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_splitter = QSplitter(Qt.Orientation.Vertical)
        left_splitter.setChildrenCollapsible(False)
        left_splitter.setHandleWidth(16)
        left_layout.addWidget(left_splitter, 1)

        video_area = QWidget()
        video_area_layout = QVBoxLayout(video_area)
        video_area_layout.setContentsMargins(0, 0, 0, 0)
        video_area_layout.setSpacing(6)
        video_area_layout.addWidget(self.video_container, 1)

        timeline_row = QHBoxLayout()
        timeline_row.setContentsMargins(0, 0, 0, 0)
        timeline_row.addWidget(self.timeline_slider, 1)
        timeline_row.addWidget(self.time_label)
        video_area_layout.addLayout(timeline_row)

        controls_area = QWidget()
        controls_layout = QVBoxLayout(controls_area)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(6)

        jumps = QHBoxLayout()
        for btn in self.jump_buttons:
            jumps.addWidget(btn)
        controls_layout.addLayout(jumps)

        marks = QHBoxLayout()
        marks.addWidget(self.mark_start_btn)
        marks.addWidget(self.mark_end_btn)
        marks.addWidget(self.play_pause_btn)
        controls_layout.addLayout(marks)
        controls_layout.addWidget(self.status_label)
        controls_layout.addStretch()

        left_splitter.addWidget(video_area)
        left_splitter.addWidget(controls_area)
        left_splitter.setSizes([620, 170])
        left_splitter.setStretchFactor(0, 5)
        left_splitter.setStretchFactor(1, 1)
        splitter.addWidget(left)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_scroll.setWidget(right)
        splitter.addWidget(right_scroll)
        splitter.setSizes([980, 380])
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 2)

        score_panel = QFrame()
        score_panel.setObjectName("panel")
        score_layout = QVBoxLayout(score_panel)
        score_layout.addWidget(QLabel("<b>Scoreboard overlay</b>"))

        grid = QGridLayout()
        grid.addWidget(QLabel("Torneo"), 0, 0)
        grid.addWidget(self.tournament_input, 0, 1)
        grid.addWidget(QLabel("Giocatore A"), 1, 0)
        grid.addWidget(self.player_a_input, 1, 1)
        grid.addWidget(QLabel("Giocatore B"), 2, 0)
        grid.addWidget(self.player_b_input, 2, 1)
        grid.addWidget(QLabel("Formato"), 3, 0)
        grid.addWidget(self.best_of, 3, 1)
        grid.addWidget(QLabel("Set decisivo"), 4, 0)
        grid.addWidget(self.deciding_set_mode, 4, 1)
        grid.addWidget(QLabel("Clip attiva"), 5, 0)
        grid.addWidget(self.active_clip_combo, 5, 1)
        grid.addWidget(QLabel("Servizio"), 6, 0)
        grid.addWidget(self.server_combo, 6, 1)
        grid.addWidget(QLabel("Posizione overlay"), 7, 0)
        grid.addWidget(self.overlay_corner_combo, 7, 1)
        grid.addWidget(QLabel("Scala overlay"), 8, 0)
        grid.addWidget(self.overlay_scale_combo, 8, 1)
        grid.addWidget(QLabel("Set A / B"), 9, 0)
        set_wrap = QHBoxLayout()
        set_wrap.addWidget(self.sets_a_input)
        set_wrap.addWidget(self.sets_b_input)
        set_widget = QWidget()
        set_widget.setLayout(set_wrap)
        grid.addWidget(set_widget, 9, 1)
        grid.addWidget(QLabel("Game A / B"), 10, 0)
        game_wrap = QHBoxLayout()
        game_wrap.addWidget(self.games_a_input)
        game_wrap.addWidget(self.games_b_input)
        game_widget = QWidget()
        game_widget.setLayout(game_wrap)
        grid.addWidget(game_widget, 10, 1)
        score_layout.addLayout(grid)

        point_row = QHBoxLayout()
        point_row.addWidget(self.point_a_btn)
        point_row.addWidget(self.point_b_btn)
        point_row.addWidget(self.reset_score_btn)
        score_layout.addLayout(point_row)
        score_layout.addWidget(self.add_last_highlight_btn)
        score_layout.addWidget(self.preview_overlay_btn)
        score_layout.addWidget(self.score_preview_label)
        score_layout.addWidget(self.export_length_label)
        score_layout.addWidget(self.include_overlay)
        score_layout.addWidget(self.preview_by_timeline)
        right_layout.addWidget(score_panel)

        points_panel = QFrame()
        points_panel.setObjectName("panel")
        points_layout = QVBoxLayout(points_panel)
        points_layout.addWidget(QLabel("<b>Punti selezionati</b>"))
        points_layout.addWidget(self.segments_list)
        points_btns = QHBoxLayout()
        points_btns.addWidget(self.undo_btn)
        points_btns.addWidget(self.clear_segments_btn)
        points_btns.addWidget(self.export_btn)
        points_layout.addLayout(points_btns)
        highlights_title = QLabel("<b>Highlights</b>")
        points_layout.addWidget(highlights_title)
        points_layout.addWidget(self.highlights_list)
        highlight_btns = QHBoxLayout()
        highlight_btns.addWidget(self.remove_highlight_btn)
        highlight_btns.addWidget(self.export_highlights_btn)
        points_layout.addLayout(highlight_btns)
        right_layout.addWidget(points_panel)

        self.hotkeys_panel = QFrame()
        self.hotkeys_panel.setObjectName("panel")
        self.hotkeys_layout = QGridLayout(self.hotkeys_panel)
        self.hotkeys_layout.addWidget(QLabel("<b>Hotkeys configurabili</b>"), 0, 0, 1, 2)
        right_layout.addWidget(self.hotkeys_panel)
        right_layout.addStretch()

    def _setup_hotkey_ui(self) -> None:
        label_map = {
            "play_pause": "Play/Pausa",
            "jump_back_5": "Indietro 5s",
            "jump_fwd_5": "Avanti 5s",
            "jump_back_10": "Indietro 10s",
            "jump_fwd_10": "Avanti 10s",
            "jump_back_30": "Indietro 30s",
            "jump_fwd_30": "Avanti 30s",
            "mark_start": "Inizio punto",
            "mark_end": "Pausa clip",
            "point_a": "Punto A",
            "point_b": "Punto B",
            "undo": "Undo",
            "clear_focus": "Rilascia focus",
        }
        row = 1
        for action, default_seq in self.hotkey_defaults.items():
            edit = QKeySequenceEdit(QKeySequence(default_seq))
            edit.keySequenceChanged.connect(self._bind_shortcuts)
            self.hotkeys_layout.addWidget(QLabel(label_map[action]), row, 0)
            self.hotkeys_layout.addWidget(edit, row, 1)
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

    def _run_shortcut_action(self, callback) -> None:
        focus = self.focusWidget()
        if isinstance(focus, QKeySequenceEdit):
            return
        callback()

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
        )

    def _server_from_combo(self) -> str:
        return "A" if self.server_combo.currentIndex() == 0 else "B"

    def _set_server_combo(self, server: str) -> None:
        self.server_combo.blockSignals(True)
        self.server_combo.setCurrentIndex(0 if server == "A" else 1)
        self.server_combo.blockSignals(False)

    def _opponent(self, side: str) -> str:
        return "B" if side == "A" else "A"

    def on_server_selection_changed(self) -> None:
        # The dropdown sets who starts serving; auto-switch logic keeps advancing it.
        selected = self._server_from_combo()
        self.starting_server = selected
        self.current_server = selected
        self.tiebreak_first_server = None
        self.update_overlay()

    def update_overlay(self) -> None:
        self.overlay_widget.apply_state(self.current_overlay_state())
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

    def update_score_preview_label(self) -> None:
        state = self.current_overlay_state()
        prefix = "Corrente"
        if self.preview_by_timeline.isChecked():
            preview = self.overlay_state_for_current_position()
            if preview is not None:
                state = preview
                prefix = "Timeline"
            else:
                last_state = self.last_overlay_state_for_active_clip()
                if last_state is not None:
                    state = last_state
                    prefix = "Ultimo segmento"
        else:
            # Se il progetto caricato non ha stato live coerente, usa almeno l'ultimo score registrato.
            if (
                self.segments
                and self.points_a == 0
                and self.points_b == 0
                and self.tb_points_a == 0
                and self.tb_points_b == 0
            ):
                last_state = self.last_overlay_state_for_active_clip()
                if last_state is not None:
                    state = last_state
                    prefix = "Ultimo segmento"
        self.score_preview_label.setText(
            f"Preview {prefix}: Game {state.games_a}-{state.games_b} | Pts {state.points_a}-{state.points_b}"
        )

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
                "-vf",
                build_overlay_filter(overlay_state),
                out_png,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0 or not os.path.exists(out_png):
                QMessageBox.critical(self, "Errore preview", res.stderr.strip() or "Preview fallita.")
                return

            dialog = QDialog(self)
            dialog.setWindowTitle("Preview grafica overlay")
            dialog.setMinimumSize(900, 560)
            layout = QVBoxLayout(dialog)
            info = QLabel(
                f"Frame a {format_time(t)} | Posizione {overlay_state.overlay_corner} | Scala {int(overlay_state.overlay_scale * 100)}%"
            )
            img = QLabel()
            pix = QPixmap(out_png)
            img.setPixmap(
                pix.scaled(
                    1280,
                    720,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            layout.addWidget(info)
            layout.addWidget(img, 1)
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
        self.sets_a_input.setText(str(self.sets_a))
        self.sets_b_input.setText(str(self.sets_b))
        self.games_a_input.setText(str(self.games_a))
        self.games_b_input.setText(str(self.games_b))
        self.update_overlay()

    def on_overlay_corner_changed(self, corner: str) -> None:
        self.video_container.set_overlay_corner(corner)

    def on_overlay_scale_changed(self, value: str) -> None:
        scale = value.replace("%", "").strip()
        try:
            factor = int(scale) / 100.0
        except ValueError:
            factor = 1.0
        self.overlay_widget.apply_scale(factor)
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

    def on_player_position_changed(self, position_ms: int) -> None:
        if not self.is_scrubbing:
            self.timeline_slider.setValue(position_ms)
        self._update_time_label(position_ms, self.player.duration())
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
        self.export_length_label.setText(
            f"Durata export stimata: {format_time(self.estimated_export_duration())}"
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
        self.clip_duration_cache.clear()
        self.segments.clear()
        self.undo_stack.clear()
        self.refresh_segments()
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
        if self.pending_point_start is not None:
            self.set_status(
                f"Clip attiva: {os.path.basename(self.input_path)} (punto in corso, chiudilo con Pausa clip o Punto A/B)."
            )
        else:
            self.set_status(f"Clip attiva: {os.path.basename(self.input_path)}")

    def _set_scale_combo_from_factor(self, factor: float) -> None:
        percent = int(round(max(0.7, min(factor, 2.0)) * 100))
        options = [80, 100, 120, 140, 160]
        nearest = min(options, key=lambda v: abs(v - percent))
        self.overlay_scale_combo.setCurrentText(f"{nearest}%")

    def _project_payload(self) -> dict:
        current_clip_index = self.active_clip_combo.currentIndex()
        return {
            "version": 3,
            "input_paths": self.input_paths,
            "current_clip_index": current_clip_index,
            "pending_point_start": self.pending_point_start,
            "pending_point_source_path": self.pending_point_source_path,
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
                "in_tiebreak": self.in_tiebreak,
                "tiebreak_target": self.tiebreak_target,
                "tiebreak_super": self.tiebreak_super,
                "starting_server": self.starting_server,
                "current_server": self.current_server,
                "tiebreak_first_server": self.tiebreak_first_server,
                "tournament": self.tournament_input.text(),
                "player_a": self.player_a_input.text(),
                "player_b": self.player_b_input.text(),
                "best_of_index": self.best_of.currentIndex(),
                "deciding_set_mode_index": self.deciding_set_mode.currentIndex(),
                "server_index": self.server_combo.currentIndex(),
                "overlay_corner": self.overlay_corner_combo.currentText(),
                "overlay_scale": self.overlay_widget.scale_factor,
                "include_overlay": self.include_overlay.isChecked(),
                "preview_by_timeline": self.preview_by_timeline.isChecked(),
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
            QMessageBox.critical(self, "Errore salvataggio", str(exc))

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
        choice = QMessageBox.question(
            self,
            "Ripristino autosave",
            "Trovato un autosave progetto. Vuoi ripristinarlo?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if choice != QMessageBox.StandardButton.Yes:
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
            QMessageBox.critical(self, "Errore caricamento progetto", str(exc))

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
        self.in_tiebreak = bool(state.get("in_tiebreak", False))
        self.tiebreak_target = int(state.get("tiebreak_target", 7))
        self.tiebreak_super = bool(state.get("tiebreak_super", False))
        self.starting_server = str(state.get("starting_server", "A"))
        self.current_server = str(state.get("current_server", self.starting_server))
        self.tiebreak_first_server = state.get("tiebreak_first_server")

        self.tournament_input.setText(str(state.get("tournament", "Amateur Tennis Tour")))
        self.player_a_input.setText(str(state.get("player_a", "Giocatore A")))
        self.player_b_input.setText(str(state.get("player_b", "Giocatore B")))
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
        self.sets_a_input.setText(str(self.sets_a))
        self.sets_b_input.setText(str(self.sets_b))
        self.games_a_input.setText(str(self.games_a))
        self.games_b_input.setText(str(self.games_b))

        self.pending_point_start = data.get("pending_point_start")
        raw_pending_source = data.get("pending_point_source_path")
        if isinstance(raw_pending_source, str) and raw_pending_source:
            self.pending_point_source_path = raw_pending_source
        else:
            self.pending_point_source_path = self.input_path if self.pending_point_start is not None else None
        raw_segments = data.get("segments", [])
        parsed_segments: list[Segment] = []
        for seg in raw_segments:
            src = seg.get("source_path")
            ov = seg.get("overlay", {})
            if not src or not os.path.exists(src):
                continue
            parsed_segments.append(
                Segment(
                    start=float(seg.get("start", 0.0)),
                    end=float(seg.get("end", 0.0)),
                    source_path=src,
                    overlay=OverlayState(
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
                    ),
                    is_highlight=bool(seg.get("is_highlight", False)),
                )
            )
        self.segments = parsed_segments
        self.undo_stack.clear()
        self.refresh_segments()
        self.update_overlay()
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
        self.push_undo_state()
        self.pending_point_start = self.current_time_sec()
        self.pending_point_source_path = self.input_path
        self.update_highlight_controls()
        self.set_status(f"Inizio punto marcato a {format_time(self.pending_point_start)}.")

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

    def close_current_point(self) -> bool:
        if self.pending_point_start is None:
            return False
        if not self.input_path:
            return False

        start_path = self.pending_point_source_path or self.input_path
        end_path = self.input_path
        if self.input_paths:
            try:
                start_idx = self.input_paths.index(start_path)
                end_idx = self.input_paths.index(end_path)
            except ValueError:
                if start_path != end_path:
                    self.set_status("Punto cross-clip non valido: clip sorgente o destinazione non trovata.")
                    return False
                start_idx = end_idx = 0
        else:
            start_idx = end_idx = 0

        if end_idx < start_idx:
            self.set_status("Fine punto su clip precedente non supportata. Chiudi il punto nella clip corrente o successiva.")
            return False

        created_segments = 0
        for idx in range(start_idx, end_idx + 1):
            clip_path = self.input_paths[idx] if self.input_paths else end_path
            seg_start = self.pending_point_start if idx == start_idx else 0.0
            if idx == end_idx:
                seg_end = self.current_time_sec()
            else:
                duration = self._probe_clip_duration(clip_path)
                if duration is None:
                    self.set_status(f"Impossibile leggere la durata clip: {os.path.basename(clip_path)}")
                    return False
                seg_end = duration

            start = min(seg_start, seg_end)
            final_end = max(seg_start, seg_end)
            if final_end - start < 0.15:
                continue
            self.segments.append(
                Segment(
                    start=start,
                    end=final_end,
                    source_path=clip_path,
                    overlay=self.current_overlay_state(),
                    is_highlight=False,
                )
            )
            created_segments += 1

        if created_segments == 0:
            self.set_status("Durata punto troppo corta.")
            return False

        self.pending_point_start = None
        self.pending_point_source_path = None
        self.refresh_segments()
        self.set_status(f"Punto aggiunto su {created_segments} clip.")
        self.autosave_project()
        return True

    def mark_end(self) -> None:
        if not self.input_path:
            return
        self.push_undo_state()
        if not self.close_current_point():
            if self.pending_point_start is None:
                self.set_status("Segna prima un inizio punto.")

    def refresh_segments(self) -> None:
        self.segments_list.clear()
        if not self.segments:
            self.segments_list.addItem("Nessun punto selezionato.")
            self.refresh_highlights_list()
            self.update_highlight_controls()
            self.update_export_length_label()
            return
        for idx, seg in enumerate(self.segments, 1):
            score = f"{seg.overlay.points_a}-{seg.overlay.points_b}"
            hl = " | HIGHLIGHT" if seg.is_highlight else ""
            row = (
                f"#{idx} {format_time(seg.start)} - {format_time(seg.end)} | "
                f"game {seg.overlay.games_a}-{seg.overlay.games_b} | pts {score} | "
                f"{os.path.basename(seg.source_path)}{hl}"
            )
            self.segments_list.addItem(QListWidgetItem(row))
        self.refresh_highlights_list()
        self.update_highlight_controls()
        self.update_export_length_label()

    def refresh_highlights_list(self) -> None:
        self.highlights_list.clear()
        for idx, seg in enumerate(self.segments):
            if not seg.is_highlight:
                continue
            row = (
                f"#{idx + 1} {format_time(seg.start)} - {format_time(seg.end)} | "
                f"{os.path.basename(seg.source_path)}"
            )
            item = QListWidgetItem(row)
            item.setData(Qt.ItemDataRole.UserRole, idx)
            self.highlights_list.addItem(item)

    def update_highlight_controls(self) -> None:
        can_add = self.pending_point_start is None and len(self.segments) > 0
        if can_add and self.segments[-1].is_highlight:
            can_add = False
        self.add_last_highlight_btn.setEnabled(can_add)
        self.export_highlights_btn.setEnabled(any(seg.is_highlight for seg in self.segments))
        self.remove_highlight_btn.setEnabled(self.highlights_list.currentRow() >= 0)

    def add_last_point_to_highlights(self) -> None:
        if self.pending_point_start is not None:
            self.set_status("Chiudi prima il punto corrente.")
            return
        if not self.segments:
            self.set_status("Nessun punto disponibile da marcare.")
            return
        if self.segments[-1].is_highlight:
            self.set_status("L'ultimo punto e' gia' un highlight.")
            self.update_highlight_controls()
            return
        self.push_undo_state()
        self.segments[-1].is_highlight = True
        self.refresh_segments()
        self.set_status("Ultimo punto aggiunto agli highlight.")
        self.autosave_project()

    def remove_selected_highlight(self) -> None:
        item = self.highlights_list.currentItem()
        if item is None:
            return
        idx_data = item.data(Qt.ItemDataRole.UserRole)
        if idx_data is None:
            return
        idx = int(idx_data)
        if idx < 0 or idx >= len(self.segments):
            return
        if not self.segments[idx].is_highlight:
            self.refresh_segments()
            return
        self.push_undo_state()
        self.segments[idx].is_highlight = False
        self.refresh_segments()
        self.set_status(f"Highlight rimosso dal punto #{idx + 1}.")
        self.autosave_project()

    def clear_segments(self) -> None:
        self.push_undo_state()
        self.segments.clear()
        self.pending_point_start = None
        self.pending_point_source_path = None
        self.refresh_segments()
        self.set_status("Lista punti svuotata.")
        self.autosave_project()

    def push_undo_state(self) -> None:
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
        if not self.undo_stack:
            self.set_status("Nessuna azione da annullare.")
            return
        snap = self.undo_stack.pop()
        self.pending_point_start = snap["pending_point_start"]
        self.pending_point_source_path = snap.get("pending_point_source_path")
        self.segments = snap["segments"]
        self.points_a = snap["points_a"]
        self.points_b = snap["points_b"]
        self.games_a = snap["games_a"]
        self.games_b = snap["games_b"]
        self.sets_a = snap["sets_a"]
        self.sets_b = snap["sets_b"]
        self.completed_sets = list(snap.get("completed_sets", []))
        self.tb_points_a = snap["tb_points_a"]
        self.tb_points_b = snap["tb_points_b"]
        self.in_tiebreak = snap["in_tiebreak"]
        self.tiebreak_target = snap["tiebreak_target"]
        self.tiebreak_super = snap["tiebreak_super"]
        self.starting_server = snap["starting_server"]
        self.current_server = snap["current_server"]
        self.tiebreak_first_server = snap["tiebreak_first_server"]
        self._set_server_combo(self.current_server)
        self.sets_a_input.setText(str(self.sets_a))
        self.sets_b_input.setText(str(self.sets_b))
        self.games_a_input.setText(str(self.games_a))
        self.games_b_input.setText(str(self.games_b))
        self.refresh_segments()
        self.update_overlay()
        self.set_status("Ultima azione annullata.")
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
            final_games = (1, 0) if side == "A" else (0, 1)
        else:
            final_games = (7, 6) if side == "A" else (6, 7)
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
            self.sets_a += 1
            self.games_a = 0
            self.games_b = 0
            set_ended = True
        elif self.games_b >= 6 and self.games_b - self.games_a >= 2:
            self.completed_sets.append((self.games_a, self.games_b))
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

    def tennis_point_winner(self, side: str) -> None:
        if not self.input_path:
            return
        self.push_undo_state()

        # Quando assegni un punto (bottone o hotkey), chiudi automaticamente la clip corrente.
        self.close_current_point()

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
        else:
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
            else:
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

        self.update_overlay()
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
        self.games_a = self._int_or_default(self.games_a_input.text(), 0)
        self.games_b = self._int_or_default(self.games_b_input.text(), 0)
        self.sets_a = self._int_or_default(self.sets_a_input.text(), 0)
        self.sets_b = self._int_or_default(self.sets_b_input.text(), 0)
        self.update_overlay()
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
                    ),
                    is_highlight=seg.is_highlight,
                )
            )
        return export_segments

    def _start_export_job(self, output_path: str, source_segments: list[Segment], export_kind: str) -> None:
        self.current_export_kind = export_kind
        self.export_btn.setEnabled(False)
        self.export_highlights_btn.setEnabled(False)
        self.set_status(f"Export {export_kind} in corso...")
        self.export_progress_dialog = ExportProgressDialog(self)
        self.export_progress_dialog.set_progress(0, 0.0, 0.0, "Preparazione export...")
        self.export_progress_dialog.show()
        export_segments = self._build_export_segments(source_segments)
        self.export_worker = ExportWorker(
            output_path=output_path,
            segments=export_segments,
            include_overlay=self.include_overlay.isChecked(),
        )
        self.export_worker.progress.connect(self.on_export_progress)
        self.export_worker.finished_ok.connect(self.on_export_ok)
        self.export_worker.failed.connect(self.on_export_failed)
        self.export_worker.start()

    def export_condensed(self) -> None:
        if not self.input_path:
            QMessageBox.warning(self, "Errore", "Carica un video prima di esportare.")
            return
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

    def on_export_progress(self, percent: int, elapsed_sec: float, eta_sec: float, status: str) -> None:
        if self.export_progress_dialog is not None:
            self.export_progress_dialog.set_progress(percent, elapsed_sec, eta_sec, status)

    def on_export_ok(self, output_path: str, chunks: int) -> None:
        self.export_btn.setEnabled(True)
        self.update_highlight_controls()
        if self.export_progress_dialog is not None:
            self.export_progress_dialog.close()
            self.export_progress_dialog = None
        self.set_status(f"Export {self.current_export_kind} completato: {output_path} ({chunks} clip).")
        QMessageBox.information(self, "Completato", f"Video esportato:\n{output_path}")

    def on_export_failed(self, message: str) -> None:
        self.export_btn.setEnabled(True)
        self.update_highlight_controls()
        if self.export_progress_dialog is not None:
            self.export_progress_dialog.close()
            self.export_progress_dialog = None
        self.set_status(f"Export {self.current_export_kind} fallito: {message}")
        QMessageBox.critical(self, "Errore export", message)

    def clear_edit_focus(self) -> None:
        for field in [
            self.tournament_input,
            self.player_a_input,
            self.player_b_input,
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
