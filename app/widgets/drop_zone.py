from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFileDialog, QFrame, QLabel, QVBoxLayout


class DropZone(QFrame):
    """Click-to-browse + drag-and-drop target. Always emits a list of paths,
    even in single-file mode, so callers have one code path to handle."""

    filesSelected = Signal(list)

    def __init__(self, extensions, file_filter, prompt, multiple=False):
        super().__init__()

        self.extensions = [e.lower() for e in extensions]
        self.file_filter = file_filter
        self.multiple = multiple

        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(150)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        self.label = QLabel(prompt)
        self.label.setObjectName("dropZoneLabel")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setWordWrap(True)

        layout.addWidget(self.label)

    def setPrompt(self, text):
        self.label.setText(text)

    def setMultiple(self, multiple):
        self.multiple = multiple

    def _is_valid(self, path):
        return Path(path).suffix.lower() in self.extensions

    def mouseReleaseEvent(self, event):
        if self.rect().contains(event.pos()):
            if self.multiple:
                paths, _ = QFileDialog.getOpenFileNames(self, "Select files", "", self.file_filter)
            else:
                path, _ = QFileDialog.getOpenFileName(self, "Select file", "", self.file_filter)
                paths = [path] if path else []
            if paths:
                self.filesSelected.emit(paths)
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        valid = [u.toLocalFile() for u in urls if self._is_valid(u.toLocalFile())]
        if valid:
            self._set_active(True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._set_active(False)

    def dropEvent(self, event):
        self._set_active(False)
        urls = event.mimeData().urls()
        valid = [u.toLocalFile() for u in urls if self._is_valid(u.toLocalFile())]
        if valid:
            paths = valid if self.multiple else valid[:1]
            self.filesSelected.emit(paths)
            event.acceptProposedAction()

    def _set_active(self, active):
        self.setProperty("dragActive", active)
        self.style().unpolish(self)
        self.style().polish(self)
