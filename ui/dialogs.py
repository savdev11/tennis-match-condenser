from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout, QWidget


def _format_time(seconds: float) -> str:
    total = max(0, int(seconds))
    hours = total // 3600
    mins = (total % 3600) // 60
    secs = total % 60
    if hours > 0:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


class ExportProgressDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("exportProgressDialog")
        self.setWindowTitle("Esportazione")
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
        self.elapsed_label.setText(f"Tempo trascorso: {_format_time(elapsed_sec)}")
        if eta_sec <= 0.1:
            self.eta_label.setText("Tempo stimato rimanente: 0:00")
        else:
            self.eta_label.setText(f"Tempo stimato rimanente: {_format_time(eta_sec)}")
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
        self.setWindowTitle("Esportazione completata")
        self.title_label.setText("Esportazione completata")
        self.status_label.setText(f"Completato: {chunks} clip ({mode})")
        self.progress_bar.setValue(100)
        self.eta_label.setText("Tempo stimato rimanente: 0:00")
        self.summary_label.setText(f"Output: {output_path}")
        self.log_box.appendPlainText(f"Esportazione completata: {output_path}")
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
        self.setWindowTitle("Esportazione fallita")
        self.title_label.setText("Esportazione fallita")
        self.status_label.setText(f"Errore durante export {mode}")
        self.log_box.appendPlainText(message.strip() or "Errore sconosciuto")
        self.close_btn.setEnabled(True)

    def closeEvent(self, event) -> None:
        if self._state == "progress":
            event.ignore()
            return
        super().closeEvent(event)
