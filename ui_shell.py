from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class SingleOpenAccordion(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("accordion")
        self._sections: list[tuple[QToolButton, QWidget]] = []
        self._active_index = -1
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)

    def add_section(self, title: str, content: QWidget) -> int:
        idx = len(self._sections)
        header = QToolButton(self)
        header.setObjectName("accordionHeader")
        header.setCheckable(True)
        header.setChecked(False)
        header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        header.setAutoRaise(False)
        header.clicked.connect(lambda _checked=False, i=idx: self.set_active(i))
        body = QFrame(self)
        body.setObjectName("accordionBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        content.setParent(body)
        body_layout.addWidget(content)
        self._layout.addWidget(header)
        self._layout.addWidget(body)
        self._sections.append((header, body))
        self._sync_header_text(idx, title, expanded=False)
        body.setVisible(False)
        if self._active_index < 0:
            self.set_active(0)
        return idx

    def set_active(self, index: int) -> None:
        if index < 0 or index >= len(self._sections):
            return
        for idx, (header, body) in enumerate(self._sections):
            expanded = idx == index
            header.setChecked(expanded)
            body.setVisible(expanded)
            title = str(header.property("title") or "")
            self._sync_header_text(idx, title, expanded)
        self._active_index = index

    def _sync_header_text(self, index: int, title: str, expanded: bool) -> None:
        arrow = "▾" if expanded else "▸"
        header, _body = self._sections[index]
        header.setProperty("title", title)
        header.setText(f"{arrow}  {title}")


class UIShell(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("shellRoot")

        self.actions: dict[str, QAction] = {}
        self.toolbar_buttons: dict[str, QToolButton] = {}
        self._build()

    def _make_action(self, key: str, text: str, enabled: bool = False) -> QAction:
        action = QAction(text, self)
        action.setEnabled(enabled)
        self.actions[key] = action
        return action

    def _add_toolbar_action(self, key: str) -> None:
        btn = QToolButton(self)
        btn.setObjectName("toolbarButton")
        btn.setProperty("btnRole", "secondary")
        if key in {"export"}:
            btn.setProperty("btnRole", "primary")
        elif key == "undo":
            btn.setProperty("btnRole", "subtle")
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        btn.setAutoRaise(False)
        btn.setDefaultAction(self.actions[key])
        self.toolbar.addWidget(btn)
        self.toolbar_buttons[key] = btn

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.toolbar_host = QFrame(self)
        self.toolbar_host.setObjectName("toolbarHost")
        toolbar_host_layout = QVBoxLayout(self.toolbar_host)
        toolbar_host_layout.setContentsMargins(6, 3, 6, 3)
        toolbar_host_layout.setSpacing(0)

        self.toolbar = QToolBar(self.toolbar_host)
        self.toolbar.setObjectName("shellToolbar")
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
        toolbar_host_layout.addWidget(self.toolbar)
        root.addWidget(self.toolbar_host)

        self.content_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.content_splitter.setChildrenCollapsible(False)
        self.content_splitter.setHandleWidth(1)

        self.left_rail = QFrame(self)
        self.left_rail.setObjectName("leftRail")
        self.left_rail.setMinimumWidth(230)
        self.left_rail.setMaximumWidth(300)
        left_layout = QVBoxLayout(self.left_rail)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(8)

        self.left_sources_page = QFrame(self.left_rail)
        self.left_points_page = QFrame(self.left_rail)
        self.left_clips_page = QFrame(self.left_rail)
        self.left_highlights_page = QFrame(self.left_rail)
        self.left_accordion = SingleOpenAccordion(self.left_rail)
        self.left_accordion.setObjectName("leftAccordion")
        self.left_accordion.add_section("Sorgente", self.left_sources_page)
        self.left_accordion.add_section("Punti", self.left_points_page)
        self.left_accordion.add_section("Clip", self.left_clips_page)
        self.left_accordion.add_section("Highlights", self.left_highlights_page)
        self.left_tabs = self.left_accordion  # compatibility alias
        left_layout.addWidget(self.left_accordion, 1)

        self.left_panel_container = QFrame(self.left_rail)
        self.left_panel_container.setObjectName("leftPanelContainer")
        self.left_panel_container_layout = QVBoxLayout(self.left_panel_container)
        self.left_panel_container_layout.setContentsMargins(6, 6, 6, 6)
        self.left_panel_container_layout.setSpacing(6)
        self.left_panel_container.setVisible(False)
        left_layout.addWidget(self.left_panel_container)

        self.center_pane = QFrame(self)
        self.center_pane.setObjectName("centerPane")
        center_layout = QVBoxLayout(self.center_pane)
        center_layout.setContentsMargins(6, 6, 6, 6)
        center_layout.setSpacing(6)

        self.center_video_container = QFrame(self.center_pane)
        self.center_video_container.setObjectName("videoStage")
        self.center_video_layout = QVBoxLayout(self.center_video_container)
        self.center_video_layout.setContentsMargins(4, 4, 4, 4)
        self.center_video_layout.setSpacing(0)

        self.center_timeline_container = QFrame(self.center_pane)
        self.center_timeline_container.setObjectName("timelineStage")
        self.center_timeline_layout = QVBoxLayout(self.center_timeline_container)
        self.center_timeline_layout.setContentsMargins(8, 8, 8, 8)
        self.center_timeline_layout.setSpacing(6)

        center_layout.addWidget(self.center_video_container, 1)
        center_layout.addWidget(self.center_timeline_container, 0)

        self.right_inspector = QFrame(self)
        self.right_inspector.setObjectName("rightInspector")
        self.right_inspector.setMinimumWidth(330)
        self.right_inspector.setMaximumWidth(460)
        right_layout = QVBoxLayout(self.right_inspector)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(8)

        self.right_score_page = QFrame(self.right_inspector)
        self.right_overlay_page = QFrame(self.right_inspector)
        self.right_intro_outro_page = QFrame(self.right_inspector)
        self.right_hotkeys_page = QFrame(self.right_inspector)
        self.right_export_page = QFrame(self.right_inspector)
        self.right_accordion = SingleOpenAccordion(self.right_inspector)
        self.right_accordion.setObjectName("rightAccordion")
        self.right_accordion.add_section("Punteggio", self.right_score_page)
        self.right_accordion.add_section("Overlay", self.right_overlay_page)
        self.right_accordion.add_section("Intro-Outro", self.right_intro_outro_page)
        self.right_accordion.add_section("Export", self.right_export_page)
        self.right_accordion.add_section("Hotkeys", self.right_hotkeys_page)
        self.right_tabs = self.right_accordion  # compatibility alias
        right_layout.addWidget(self.right_accordion, 1)

        self.right_panel_container = QFrame(self.right_inspector)
        self.right_panel_container.setObjectName("rightPanelContainer")
        self.right_panel_layout = QVBoxLayout(self.right_panel_container)
        self.right_panel_layout.setContentsMargins(6, 6, 6, 6)
        self.right_panel_layout.setSpacing(6)
        self.right_panel_container.setVisible(False)
        right_layout.addWidget(self.right_panel_container)

        self.content_splitter.addWidget(self.left_rail)
        self.content_splitter.addWidget(self.center_pane)
        self.content_splitter.addWidget(self.right_inspector)
        self.content_splitter.setStretchFactor(0, 0)
        self.content_splitter.setStretchFactor(1, 1)
        self.content_splitter.setStretchFactor(2, 0)
        self.content_splitter.setSizes([300, 860, 460])
        root.addWidget(self.content_splitter, 1)

        self.status_container = QFrame(self)
        self.status_container.setObjectName("statusHost")
        status_layout = QHBoxLayout(self.status_container)
        status_layout.setContentsMargins(8, 3, 8, 3)
        status_layout.setSpacing(10)

        self.project_status_label = QLabel("Project: not loaded", self.status_container)
        self.project_status_label.setObjectName("statusValue")
        self.source_fps_label = QLabel("FPS: --", self.status_container)
        self.source_fps_label.setObjectName("statusLabel")
        self.export_estimate_label = QLabel("Export: --", self.status_container)
        self.export_estimate_label.setObjectName("statusLabel")
        self.hotkeys_state_label = QLabel("Hotkeys: active", self.status_container)
        self.hotkeys_state_label.setObjectName("statusLabel")

        status_layout.addWidget(self.project_status_label, 2)
        status_layout.addWidget(self.source_fps_label, 1)
        status_layout.addWidget(self.export_estimate_label, 1)
        status_layout.addWidget(self.hotkeys_state_label, 1)
        root.addWidget(self.status_container)

        self._build_actions()

    def _build_actions(self) -> None:
        # Shared actions (menu + toolbar) to avoid duplicate trigger wiring.
        self._make_action("load_video", "Carica video")
        self._make_action("save_project", "Salva progetto")
        self._make_action("mark_start", "Inizio punto")
        self._make_action("mark_end", "Pausa/Riprendi clip")
        self._make_action("point_a", "Punto A")
        self._make_action("point_b", "Punto B")
        self._make_action("undo", "Undo")
        self._make_action("highlight", "Highlights")
        self._make_action("play_pause", "Play/Pause")
        self._make_action("export", "Export")

        # Additional actions (for native menu wiring from MainWindow).
        self._make_action("open_project", "Carica progetto")
        self._make_action("clear_focus", "Rilascia focus")
        self._make_action("toggle_score_preview", "Preview scoreboard")
        self._make_action("export_highlights", "Export highlights")
        self._make_action("about", "About")

        for key in [
            "load_video",
            "save_project",
            "undo",
            "export",
        ]:
            self._add_toolbar_action(key)

        # Disabled by default until MainWindow wires exact methods.
        for action in self.actions.values():
            action.setEnabled(False)

        self.left_sources_page.setLayout(QVBoxLayout())
        self.left_sources_page.layout().setContentsMargins(6, 6, 6, 6)
        self.left_points_page.setLayout(QVBoxLayout())
        self.left_points_page.layout().setContentsMargins(6, 6, 6, 6)
        self.left_clips_page.setLayout(QVBoxLayout())
        self.left_clips_page.layout().setContentsMargins(6, 6, 6, 6)
        self.left_highlights_page.setLayout(QVBoxLayout())
        self.left_highlights_page.layout().setContentsMargins(6, 6, 6, 6)

        self.right_score_page.setLayout(QVBoxLayout())
        self.right_score_page.layout().setContentsMargins(6, 6, 6, 6)
        self.right_overlay_page.setLayout(QVBoxLayout())
        self.right_overlay_page.layout().setContentsMargins(6, 6, 6, 6)
        self.right_intro_outro_page.setLayout(QVBoxLayout())
        self.right_intro_outro_page.layout().setContentsMargins(6, 6, 6, 6)
        self.right_hotkeys_page.setLayout(QVBoxLayout())
        self.right_hotkeys_page.layout().setContentsMargins(6, 6, 6, 6)
        self.right_export_page.setLayout(QVBoxLayout())
        self.right_export_page.layout().setContentsMargins(6, 6, 6, 6)
