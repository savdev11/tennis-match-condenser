import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QImage, QPixmap
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from domain.models import OverlayState


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
