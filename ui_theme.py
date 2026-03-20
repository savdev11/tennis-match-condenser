from __future__ import annotations

from PySide6.QtWidgets import QWidget

# Color tokens
bg0 = "#080808"
bg1 = "#131313"
bg2 = "#1A1A1A"
bg3 = "#222222"
bg4 = "#2C2C2C"
bg5 = "#363636"
bg6 = "#424242"

border1 = "#1E1E1E"
border2 = "#282828"
border3 = "#363636"
border4 = "#444444"

textPrimary = "#EDE8E0"
textSecondary = "#9B9088"
textMuted = "#7B7068"
textDisabled = "#4D4540"

clay = "#B5542A"
clayDark = "#8E3F1F"
clayLight = "#C9683E"
ballYellow = "#D6FF3F"
ballYellowDark = "#ABCC2F"
scoreBlue = "#1F5EFF"
danger = "#E03535"
success = "#22C55E"
warning = "#F59E0B"
highlight = "#FFB830"
recRed = "#FF3B30"

FONT_STACK = 'Inter, "SF Pro Text", "SF Pro Display", -apple-system, "Segoe UI", Arial, sans-serif'


def shell_stylesheet() -> str:
    return f"""
QWidget#shellRoot {{
    background: {bg2};
    color: {textPrimary};
    font-family: {FONT_STACK};
    font-size: 12px;
}}
QFrame#toolbarHost,
QFrame#statusHost {{
    background: {bg1};
    border: none;
    border-radius: 0px;
}}
QFrame#leftRail,
QFrame#centerPane,
QFrame#rightInspector {{
    background: {bg2};
    border: none;
    border-radius: 0px;
}}
QFrame#videoStage,
QFrame#timelineStage,
QFrame#leftPanelContainer,
QFrame#rightPanelContainer {{
    background: {bg2};
    border: none;
    border-radius: 0px;
}}
QFrame#transportGroup {{
    background: {bg2};
    border: none;
    border-radius: 6px;
}}
QFrame#emptyStateCard {{
    background: transparent;
    border: none;
}}
QFrame#panel {{
    background: {bg2};
    border: none;
    border-radius: 8px;
}}
QFrame#inspectorCard {{
    background: {bg2};
    border: none;
    border-radius: 10px;
}}
QFrame#rightInspector QLabel,
QTabWidget#rightTabs QLabel,
QFrame#inspectorCard QLabel {{
    color: #d8d0c7;
}}
QFrame#rightInspector QLabel#sectionTitle,
QTabWidget#rightTabs QLabel#sectionTitle,
QFrame#inspectorCard QLabel#sectionTitle {{
    color: {textPrimary};
    font-weight: 600;
}}
QFrame#rightInspector QLabel#metaLabel,
QTabWidget#rightTabs QLabel#metaLabel,
QFrame#inspectorCard QLabel#metaLabel {{
    color: #b9aea2;
}}
QFrame#rightInspector QCheckBox,
QTabWidget#rightTabs QCheckBox,
QFrame#inspectorCard QCheckBox {{
    color: #d8d0c7;
}}
QLabel#sectionTitle {{
    color: {textPrimary};
    font-size: 12px;
    font-weight: 600;
}}
QLabel#summaryCard {{
    background: {bg3};
    border: 1px solid {border2};
    border-radius: 8px;
    padding: 7px 9px;
    color: {textPrimary};
}}
QLabel#statusChip {{
    background: {bg3};
    border: 1px solid {border2};
    border-radius: 6px;
    color: {textSecondary};
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel#statusChip[chipState="active"] {{
    background: {clayDark};
    border-color: {clay};
    color: {textPrimary};
}}
QLabel#metaLabel {{
    color: {textSecondary};
    font-size: 11px;
    padding: 1px 2px;
}}
QLabel#statusLabel {{
    color: {textMuted};
    font-size: 11px;
    padding: 2px 8px;
    border: none;
}}
QLabel#statusValue {{
    color: {textPrimary};
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
}}
QLabel#dialogTitle {{
    color: {textPrimary};
    font-size: 14px;
    font-weight: 700;
}}
QLabel#emptyStateTitle {{
    color: {textPrimary};
    font-size: 20px;
    font-weight: 700;
}}
QToolButton#toolbarButton,
QPushButton#shellButton,
QPushButton {{
    background: {bg3};
    color: {textPrimary};
    border: 1px solid {border2};
    border-radius: 7px;
    min-height: 30px;
    padding: 0 10px;
}}
QToolButton#toolbarButton:hover,
QPushButton#shellButton:hover,
QPushButton:hover {{
    background: {bg4};
    border-color: {border4};
}}
QToolButton#toolbarButton:pressed,
QPushButton#shellButton:pressed,
QPushButton:pressed {{
    background: {bg5};
    border-color: {clayDark};
}}
QToolButton#toolbarButton:focus,
QPushButton#shellButton:focus,
QPushButton:focus {{
    border: 1px solid {clay};
}}
QToolButton#toolbarButton:disabled,
QPushButton#shellButton:disabled,
QPushButton:disabled {{
    color: {textDisabled};
    border-color: {border1};
    background: {bg2};
}}
QToolButton#toolbarButton[btnRole="primary"],
QPushButton[btnRole="primary"] {{
    background: {clayDark};
    border-color: {clay};
    color: {textPrimary};
}}
QToolButton#toolbarButton[btnRole="primary"]:hover,
QPushButton[btnRole="primary"]:hover {{
    background: {clay};
}}
QToolButton#toolbarButton[btnRole="active"],
QPushButton[btnRole="active"] {{
    background: {scoreBlue};
    border-color: #4a7bff;
    color: {textPrimary};
}}
QToolButton#toolbarButton[btnRole="active"]:hover,
QPushButton[btnRole="active"]:hover {{
    background: #3569f0;
}}
QToolButton#toolbarButton[btnRole="danger"],
QPushButton[btnRole="danger"] {{
    background: #3a1e1e;
    border-color: {danger};
    color: #ffb8b8;
}}
QToolButton#toolbarButton[btnRole="danger"]:hover,
QPushButton[btnRole="danger"]:hover {{
    background: #4a2323;
    color: #ffd6d6;
}}
QToolButton#toolbarButton[btnRole="subtle"],
QPushButton[btnRole="subtle"] {{
    background: {bg2};
    border-color: {border2};
    color: {textSecondary};
}}
QToolButton#toolbarButton[btnRole="subtle"]:hover,
QPushButton[btnRole="subtle"]:hover {{
    background: {bg3};
    color: {textPrimary};
}}
QToolBar#shellToolbar {{
    background: transparent;
    border: none;
    spacing: 6px;
    padding: 4px;
}}
QWidget#leftAccordion,
QWidget#rightAccordion {{
    background: transparent;
    border: none;
}}
QToolButton#accordionHeader {{
    text-align: left;
    background: {bg2};
    color: {textPrimary};
    border: 1px solid {border2};
    border-radius: 7px;
    min-height: 28px;
    padding: 4px 8px;
    font-weight: 600;
}}
QToolButton#accordionHeader:hover {{
    background: {bg3};
    border-color: {border3};
}}
QToolButton#accordionHeader:checked {{
    background: {bg3};
    border-color: {clayDark};
    color: {textPrimary};
}}
QFrame#accordionBody {{
    background: transparent;
    border: none;
    margin: 0 0 2px 0;
}}
QSplitter::handle {{
    background: {bg2};
    border: none;
    width: 1px;
}}
QSplitter::handle:hover {{
    background: {bg2};
}}
QListWidget {{
    background: {bg2};
    border: none;
    border-radius: 8px;
    outline: none;
    padding: 4px;
    alternate-background-color: #171717;
}}
QListWidget::item {{
    color: {textPrimary};
    padding: 8px 9px;
    border-radius: 6px;
    margin: 1px 0;
}}
QListWidget#segmentsList::item,
QListWidget#highlightsList::item {{
    padding: 5px 7px;
    margin: 0;
}}
QListWidget::item:selected {{
    background: #283242;
    color: {textPrimary};
}}
QListWidget::item:hover {{
    background: {bg3};
}}
QLineEdit, QComboBox, QKeySequenceEdit {{
    background: {bg3};
    color: {textPrimary};
    border: 1px solid {border3};
    border-radius: 6px;
    min-height: 24px;
    padding: 0 8px;
}}
QLineEdit:focus, QComboBox:focus, QKeySequenceEdit:focus {{
    border: 1px solid {clay};
}}
QComboBox QAbstractItemView {{
    background: {bg2};
    color: {textPrimary};
    border: 1px solid {border2};
    selection-background-color: {bg3};
}}
QCheckBox {{
    spacing: 6px;
}}
QMenuBar {{
    background: transparent;
    color: {textPrimary};
    border: none;
}}
QMenuBar::item {{
    background: transparent;
    padding: 4px 10px;
    border-radius: 5px;
}}
QMenuBar::item:selected {{
    background: {bg3};
}}
QMenu {{
    background: {bg2};
    color: {textPrimary};
    border: 1px solid {border3};
}}
QMenu::item:selected {{
    background: {bg3};
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QMessageBox {{
    background: {bg1};
    color: {textPrimary};
}}
QMessageBox QLabel {{
    color: {textPrimary};
    min-width: 300px;
}}
QMessageBox QPushButton {{
    min-width: 110px;
}}
QFileDialog {{
    background: {bg1};
    color: {textPrimary};
}}
QFileDialog QListView,
QFileDialog QTreeView {{
    background: {bg2};
    color: {textPrimary};
    border: 1px solid {border2};
    selection-background-color: {bg3};
}}
QFileDialog QLineEdit,
QFileDialog QComboBox {{
    background: {bg3};
    color: {textPrimary};
    border: 1px solid {border3};
}}
QScrollBar:vertical {{
    background: {bg1};
    width: 12px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {bg4};
    border-radius: 5px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{
    background: {bg5};
}}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    background: transparent;
    border: none;
}}
QScrollBar:horizontal {{
    background: {bg1};
    height: 12px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {bg4};
    border-radius: 5px;
    min-width: 28px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {bg5};
}}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {{
    background: transparent;
    border: none;
}}
QSlider::groove:horizontal {{
    height: 6px;
    border-radius: 3px;
    background: {bg4};
}}
QSlider::handle:horizontal {{
    width: 14px;
    margin: -4px 0;
    border-radius: 7px;
    background: {clay};
    border: 1px solid {clayLight};
}}
QSlider::handle:horizontal:hover {{
    background: {clayLight};
}}
QDialog {{
    background: {bg1};
    color: {textPrimary};
}}
QDialog#exportProgressDialog QLabel {{
    color: {textPrimary};
}}
QDialog#exportProgressDialog QLabel#metaLabel {{
    color: #c8bdb2;
}}
QDialog#exportProgressDialog QLabel#statusValue {{
    color: {textPrimary};
}}
QDialog#overlayPreviewDialog {{
    background: {bg1};
}}
QDialog#overlayPreviewDialog QLabel {{
    color: {textPrimary};
}}
QLabel#previewMetaLabel {{
    color: {textSecondary};
    font-size: 12px;
    padding: 0 2px 2px 2px;
}}
QFrame#previewImageContainer {{
    background: {bg2};
    border: 1px solid {border2};
    border-radius: 10px;
}}
QLabel#previewImageLabel {{
    background: transparent;
    color: {textPrimary};
}}
QProgressBar {{
    border: 1px solid {border2};
    border-radius: 7px;
    text-align: center;
    color: {textPrimary};
    font-weight: 600;
    background: {bg2};
    min-height: 16px;
}}
QProgressBar::chunk {{
    background: {clay};
    border-radius: 6px;
}}
QPlainTextEdit#exportLog {{
    background: {bg2};
    border: 1px solid {border1};
    border-radius: 8px;
    color: {textSecondary};
    padding: 6px;
}}
"""


def apply_app_theme(widget: QWidget) -> None:
    widget.setStyleSheet(shell_stylesheet())
