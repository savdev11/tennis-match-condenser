from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


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

        self.left_tabs = QTabWidget(self.left_rail)
        self.left_tabs.setObjectName("leftTabs")
        self.left_tabs.tabBar().setObjectName("leftTabBar")
        self.left_tabs.tabBar().setElideMode(Qt.TextElideMode.ElideNone)
        self.left_sources_page = QFrame(self.left_tabs)
        self.left_clips_page = QFrame(self.left_tabs)
        self.left_highlights_page = QFrame(self.left_tabs)
        self.left_tabs.addTab(self.left_sources_page, "Source")
        self.left_tabs.addTab(self.left_clips_page, "Clips")
        self.left_tabs.addTab(self.left_highlights_page, "Highlights")
        left_layout.addWidget(self.left_tabs, 1)

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

        self.right_tabs = QTabWidget(self.right_inspector)
        self.right_tabs.setObjectName("rightTabs")
        self.right_tabs.tabBar().setObjectName("rightTabBar")
        self.right_tabs.tabBar().setElideMode(Qt.TextElideMode.ElideNone)

        self.right_score_page = QFrame(self.right_tabs)
        self.right_intro_outro_page = QFrame(self.right_tabs)
        self.right_hotkeys_page = QFrame(self.right_tabs)
        self.right_export_page = QFrame(self.right_tabs)
        self.right_tabs.addTab(self.right_score_page, "Score")
        self.right_tabs.addTab(self.right_intro_outro_page, "Intro-Outro")
        self.right_tabs.addTab(self.right_hotkeys_page, "Hotkeys")
        self.right_tabs.addTab(self.right_export_page, "Export")
        right_layout.addWidget(self.right_tabs, 1)

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
        self._make_action("load_video", "Load Video")
        self._make_action("save_project", "Save Project")
        self._make_action("mark_start", "Mark Start")
        self._make_action("mark_end", "Mark End")
        self._make_action("point_a", "Point A")
        self._make_action("point_b", "Point B")
        self._make_action("undo", "Undo")
        self._make_action("highlight", "Highlight")
        self._make_action("play_pause", "Play/Pause")
        self._make_action("export", "Export")

        # Additional actions (for native menu wiring from MainWindow).
        self._make_action("open_project", "Open Project")
        self._make_action("clear_focus", "Clear Focus")
        self._make_action("toggle_score_preview", "Preview Scoreboard")
        self._make_action("export_highlights", "Export Highlights")
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
        self.left_clips_page.setLayout(QVBoxLayout())
        self.left_clips_page.layout().setContentsMargins(6, 6, 6, 6)
        self.left_highlights_page.setLayout(QVBoxLayout())
        self.left_highlights_page.layout().setContentsMargins(6, 6, 6, 6)

        self.right_score_page.setLayout(QVBoxLayout())
        self.right_score_page.layout().setContentsMargins(6, 6, 6, 6)
        self.right_intro_outro_page.setLayout(QVBoxLayout())
        self.right_intro_outro_page.layout().setContentsMargins(6, 6, 6, 6)
        self.right_hotkeys_page.setLayout(QVBoxLayout())
        self.right_hotkeys_page.layout().setContentsMargins(6, 6, 6, 6)
        self.right_export_page.setLayout(QVBoxLayout())
        self.right_export_page.layout().setContentsMargins(6, 6, 6, 6)
